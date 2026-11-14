"""Matter storage: encrypted at rest, atomic, version-checked.

THREE RULES, EACH FROM A REPRODUCED DEFECT
------------------------------------------
1. AN UNCONFIGURED KEY IS A HARD FAILURE. Making matters durable once wrote
   them to disk in PLAINTEXT because encryption was a silent no-op when
   unconfigured -- and it returned ciphertext-as-plaintext without complaint.
2. THE COMMIT IS ATOMIC. Write to a temp file and replace. There is no state in
   which half a turn has been applied.
3. THE COMMIT IS VERSION-CHECKED. If the matter moved between load and commit,
   refuse -- two turns interleaving on one derivation graph would each compute
   from a state neither of them saw.

The cipher is Fernet when `cryptography` is installed, and otherwise an
explicitly-labelled XOR keystream. The fallback is NOT presented as security:
it exists so the encryption PATH is always exercised, because a code path that
only runs in production is a code path nobody has tested.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from nm.shared.names_contracts import discard
from nm.shared.operation_contracts import save_stamp
from nm.shared.storage_errors_port import StoredObjectUnreadable
from nm.shared.store_envelope import KeyUnavailable
from nm.shared.store_port import MatterList, StaleWrite
from nm.shared.store_sealing import MatterSealer, is_envelope
from nm.shared.text_contracts import blank
from nm.shared.traceability_contracts import implements
from nm.work_the_file.matter_contracts import (
    Fact,
    Matter,
    MatterId,
)


class EncryptionNotConfigured(RuntimeError):
    """Raised loudly, for a missing key AND for a missing cipher.

    It said *never degraded into writing plaintext*, which was true of
    plaintext and not of the keystream XOR this fell back to when
    `cryptography` was absent -- silently, on a deployment that would then
    serve privileged client material under it (BK-16).
    """


#: Plan AN.50 (50g, D193; the review's F-34): the shape of a saved matter, as a
#: number each saved matter says. MOVE IT ON BY ONE whenever a field is added
#: to, taken from or renamed in any type a matter is rebuilt from (`_decode`):
#: tests/test_a_saved_matter_says_its_format.py pins the shape of each number
#: and fails when the shape has changed and the number has not. Code that
#: reads a lower number reads it as that number's code wrote it; it never
#: opens a higher one.
MATTER_FORMAT = 1
_FORMAT_KEY = "stored_format"


class SavedMatterUnreadable(StoredObjectUnreadable, ValueError):
    """A saved matter's file will not open (plan AN.53, 53j4).

    THE STORE'S OWN ERROR, AND ONE A FAILED READING IS ALREADY CAUGHT AS. Every
    place that reads a matter and can fail catches the disk's error and a
    record that does not read as one (a ValueError); a file that would not
    open was neither, so each caller that had not been told of it answered an
    advocate's damaged conversation with a server error. This is both, so no
    caller has to be told. A key that cannot be reached (KeyUnavailable) is an
    installation's failure, not one file's damage, and is never made this.
    """


_AS_A_FAILED_READING: dict[type, type] = {}


def _as_a_failed_reading(exc: StoredObjectUnreadable) -> StoredObjectUnreadable:
    """The same error, still of its own kind - a caller or a test that names
    WrappedKeyUnreadable or an unknown sealed format still has exactly that -
    and also a SavedMatterUnreadable."""
    kind = _AS_A_FAILED_READING.get(type(exc))
    if kind is None:
        kind = _AS_A_FAILED_READING[type(exc)] = type(
            type(exc).__name__, (SavedMatterUnreadable, type(exc)), {"__module__": type(exc).__module__})
    return kind(*exc.args)


class SavedShapeUnknown(ValueError):
    """The saved matter holds what this code would drop: it says a format newer
    than this code reads, or says this code's format and holds a field this
    code does not declare. It is refused - not opened, so never saved back
    without what the newer code kept in it (plan AN.50, 50g, D193; P46)."""


_STORAGE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _storage_component(value: str, *, kind: str) -> str:
    """Keep every caller-supplied identifier inside its one storage name.

    Matter and turn IDs are opaque identifiers, never paths or glob patterns.
    The same rule applies to reads, writes, locks and transcript discovery so
    a new caller cannot accidentally reopen a traversal through another door.
    """
    if not isinstance(value, str) or _STORAGE_COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{kind} must be an opaque storage identifier")
    return value


def _transcript_component(value: str) -> str:
    """Case-insensitive, reversible name for an opaque transcript component."""
    return base64.b32encode(value.encode("ascii")).decode("ascii").rstrip("=")


def _read_transcript_component(value: str) -> str:
    if not re.fullmatch(r"[A-Z2-7]{2,208}", value):
        raise ValueError("the encoded transcript identifier is invalid")
    try:
        decoded = base64.b32decode(value + "=" * (-len(value) % 8)).decode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("the encoded transcript identifier is unreadable") from exc
    _storage_component(decoded, kind="turn ID")
    if _transcript_component(decoded) != value:
        raise ValueError("the encoded transcript identifier is not canonical")
    return decoded


class _Cipher:
    def __init__(self, key: str) -> None:
        if not key or not key.strip():
            raise EncryptionNotConfigured(
                "NM_MATTER_KEY is not set. Matter state is sealed with it, and an "
                "unconfigured key is a HARD FAILURE -- never a silent no-op that "
                "writes privileged client material to disk in plaintext."
            )
        self._raw = key.encode("utf8")
        self._fernet = None
        #: What this cipher raises for bytes it will not open; its users say it in their own words (plan AN.53, 53j1).
        self.will_not_open: tuple[type[Exception], ...] = ()
        try:
            from cryptography.fernet import Fernet, InvalidToken

            self.will_not_open = (InvalidToken,)
            digest = hashlib.sha256(self._raw).digest()
            self._fernet = Fernet(base64.urlsafe_b64encode(digest))
            self.scheme = "fernet"
        except ImportError:
            # REFUSED, NOT CHOSEN (BK-16).
            #
            # This downgraded silently to a keystream XOR and served. The
            # scheme was named NOT-SECURE and `/api/health` disclosed it,
            # so it was honest -- and nothing REFUSED it, while both
            # neighbouring degradations are hard failures: a missing key
            # raises above, and the authority index will not fall back to
            # a scan with different recall because *a fallback swapped in
            # silently is the three-stores defect wearing a helpful face*.
            #
            # The same argument applies here and applies harder. Keystream
            # XOR under a REUSED key is trivially broken: two ciphertexts
            # XORed together cancel the keystream, and every matter on a
            # deployment shares one key.
            #
            # THE OPT-IN IS DELIBERATE AND UGLY. It exists so a developer
            # without the wheel can still run the suite, and it is named
            # so nobody sets it by accident or by copying a deploy script
            # without reading it.
            if os.environ.get("NM_ALLOW_INSECURE_CIPHER") != "yes-i-know":
                raise EncryptionNotConfigured(
                    "`cryptography` is not installed, so the only cipher "
                    "available is a keystream XOR -- which is not "
                    "encryption under a key every matter shares. Install "
                    "it:  pip install cryptography\n\n"
                    "To run WITHOUT it anyway -- never with a real matter "
                    "-- set NM_ALLOW_INSECURE_CIPHER=yes-i-know.") from None
            self.scheme = "xor-keystream(NOT-SECURE)"

    def encrypt(self, data: bytes) -> bytes:
        if self._fernet is not None:
            return self._fernet.encrypt(data)
        return base64.b64encode(self._xor(data))

    def decrypt(self, blob: bytes) -> bytes:
        if self._fernet is not None:
            return self._fernet.decrypt(blob)
        return self._xor(base64.b64decode(blob))

    def _xor(self, data: bytes) -> bytes:
        out = bytearray()
        stream = hashlib.sha256(self._raw).digest()
        i = 0
        for b in data:
            if i and i % len(stream) == 0:
                stream = hashlib.sha256(stream).digest()
            out.append(b ^ stream[i % len(stream)])
            i += 1
        return bytes(out)


# ----------------------------------------------------- (de)serialisation ---


def _enc(obj):
    if is_dataclass(obj):
        return {k: _enc(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (list, tuple, set, frozenset)):
        # SETS TOO. `Screen.covers` is a `frozenset[str]` and reached
        # `json.dumps` unencoded the day screens were persisted, which
        # failed twelve served-path tests with a TypeError from inside
        # starlette and nothing naming the cause.
        #
        # SORTED, so a set writes the same bytes every time. An
        # unordered dump makes two identical matters differ on disk, and
        # a diff nobody can explain is one nobody trusts.
        seq = sorted(obj, key=repr) if isinstance(obj, (set, frozenset)) \
            else obj
        return [_enc(v) for v in seq]
    if isinstance(obj, dict):
        return {k: _enc(v) for k, v in obj.items()}
    return obj


def _decode(cls, value, strict=False):
    """Rebuild a dataclass from its own field list, not from a hand-written one.

    `_enc` uses `asdict` and therefore encodes every field a type has. The
    decoder used to name its fields by hand, so a field added later was encoded
    faithfully and dropped on read, with nothing failing -- `client_described_as`
    was recorded on one turn and gone by the next, and every field added
    alongside it went the same way.

    Deriving the fields from the class is what makes the two halves incapable
    of drifting. `tests/test_store_roundtrip.py` populates every field of every
    persisted type and asserts equality, so the day one stops surviving is the
    day the build goes red.

    strict (plan AN.50, 50g): the record says it is of this code's own format,
    so a saved field this code does not declare is REFUSED and never dropped.
    Without it - a matter saved before matters said their format, or of an
    earlier format - a field this code does not declare is left behind as it
    always was: it cannot be told from one this code's authors took away.
    """
    if value is None:
        return None

    origin = get_origin(cls)
    if origin in (Union, UnionType):
        inner = [a for a in get_args(cls) if a is not type(None)]
        return _decode(inner[0], value, strict) if inner else value
    if origin in (tuple, list, set, frozenset):
        args = get_args(cls)
        item = args[0] if args else None
        seq = [_decode(item, v, strict) if item else v for v in value]
        # BACK TO THE DECLARED TYPE. A field declared `frozenset[str]`
        # that returns a list is the exact shape this decoder was
        # rewritten to prevent -- encoded faithfully, restored as
        # something else, and nothing failing until a set operation
        # somewhere far away.
        if origin is frozenset:
            return frozenset(seq)
        if origin is set:
            return set(seq)
        return tuple(seq) if origin is tuple else seq
    if origin is dict:
        return dict(value)

    if isinstance(cls, type):
        if is_dataclass(cls):
            if getattr(cls, "__stored_fields_closed__", False) is True:
                declared = {field.name for field in fields(cls)}
                if not isinstance(value, dict) or set(value) != declared:
                    raise ValueError(f"{cls.__name__} stored fields do not match its closed schema")
            if strict and isinstance(value, dict):
                unknown = sorted(set(value) - {field.name for field in fields(cls)})
                if unknown:
                    # The names only: what a field holds may be client words.
                    raise SavedShapeUnknown(
                        f"a saved {cls.__name__} holds fields this code does not declare "
                        f"({', '.join(map(str, unknown))}) in a matter that says it is format "
                        f"{MATTER_FORMAT}: it is not opened, so they are not dropped")
            hints = get_type_hints(cls)
            return cls(**{f.name: _decode(hints.get(f.name, object),
                                          value.get(f.name), strict)
                          for f in fields(cls) if f.name in value})
        if issubclass(cls, Enum):
            return cls(value)
        if cls is date:
            return date.fromisoformat(value) if isinstance(value, str) else value
    return value


def _fact(d: dict) -> Fact:
    return _decode(Fact, d)


def _said_format(document):
    """A saved matter's document without the format it says, and whether it is
    of this code's own format (plan AN.50, 50g). A matter saved before matters
    said their format says none and is read as it always was."""
    if not isinstance(document, dict) or _FORMAT_KEY not in document:
        return document, False
    said = document[_FORMAT_KEY]
    if type(said) is not int or said < 1:
        raise SavedShapeUnknown("the saved matter's format is not a number this code knows")
    if said > MATTER_FORMAT:
        raise SavedShapeUnknown(
            f"this matter was saved as format {said} and this code reads up to format "
            f"{MATTER_FORMAT}: newer code saved it. It is not opened by this version, so "
            "nothing the newer code kept in it is dropped; run the version that saved it")
    return {key: value for key, value in document.items() if key != _FORMAT_KEY}, said == MATTER_FORMAT


def _matter(d: dict, strict: bool = False) -> Matter:
    """THE SAME SYMMETRY, at the top level.

    This was a hand-written field list for one release longer than the
    inner types were, and it failed in exactly the way the inner ones had:
    the ask ledger was encoded on every commit and dropped on every load,
    so a question answered before a restart would be asked again after it.

    There is now no hand-written decoder anywhere in this module.
    """
    return _decode(Matter, d, strict)


# ------------------------------------------------------------------ store ---


#: Separates the matter from the turn in a transcript filename.
#:
#: Two underscores, because a MatterId is `mat_<hex>` and a single one would
#: split at the wrong place. The name has to be parseable WITHOUT THE KEY --
#: that is the whole point of putting the matter in it.
#: How long a commit waits for another turn to finish writing the SAME
#: matter. Long enough that an ordinary turn never meets it, short
#: enough that a live holder that hangs does not stall a practice (a
#: holder that dies lets the lock go at once: `claim`).
_LOCK_TIMEOUT = 10.0
_LOCK_POLL = 0.02


class Claim:
    """A process's hold on one file: an operating-system lock that closing
    the file lets go, and that the death of the process lets go too, so a
    server killed in the middle of a save leaves nothing behind (plan AN.50,
    D187; the mechanism the account claim uses, store_directory)."""

    def __init__(self, handle) -> None:
        self._handle = handle

    def release(self) -> None:
        if self._handle.closed:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            # Closing lets the lock go even where unlocking it failed.
            self._handle.close()


def claim(path: Path) -> Claim | None:
    """This process's claim on `path`, or None while another holds it.

    The file is made where it is missing and is never removed: its being
    there means nothing, and only the lock on its first byte is the claim.
    NOTHING IS WRITTEN TO IT. The lock may lie beyond the end of an empty
    file; a first byte written by each new claimant raced on Windows, where
    one claimant's write fell inside the other's lock and was refused
    (measured 13 Nov 2026, two password resets at once). A failure to open
    the file is raised as itself, never taken for another holder.
    """
    handle = path.open("a+b")
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:  # held by another (BlockingIOError is an OSError)
            handle.close()
            return None
    except BaseException:
        handle.close()
        raise
    return Claim(handle)


#: Plan AN.50 (50h, D194; the review's F-36): how long the rename that puts a
#: finished file in its place waits, on Windows, for a reader to let go of the
#: file it replaces. A reader holds a matter for the moment it takes to read.
_PUBLISH_WAIT = 2.0
_WINDOWS = os.name == "nt"


def publish(finished: str | Path, path: str | Path) -> None:
    """Put the finished file in place of `path`: the whole new file or the
    whole old one, never a mixture, and (plan AN.50, 50h) durably.

    ON WINDOWS a rename onto a file is refused while any reader has that file
    open, so a save that met a reader was reported as not made (measured, 11
    Nov 2026). The rename is tried again for a bounded moment; a file still
    held after it refuses the save as before, and nothing is left behind.

    ELSEWHERE no reader refuses the rename, and the folder is flushed after
    it. The file's bytes were flushed before the rename, but the name they are
    published under is the folder's, and until the folder is flushed a save
    the advocate was told of can be gone after a power loss. Windows offers no
    way to flush a folder. NOT RUN ON LINUX YET: nothing in this project has
    been; the hosted machine is where this half is first exercised.
    """
    if _WINDOWS:
        deadline = time.monotonic() + _PUBLISH_WAIT
        while True:
            try:
                os.replace(finished, path)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(_LOCK_POLL)
    os.replace(finished, path)
    folder = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def read_published(path: Path) -> bytes:
    """The bytes of a file that `publish` puts in place (plan AN.50, 50h3). ON WINDOWS a read that meets the rename
    putting a new file there is refused for that instant, as the rename is by a reader: the reader's side of the same
    finding (seen 13 Nov 2026: a matter read while another thread saved it failed with a permission error). It is
    tried again for the same bounded moment; a file still refused after it raises as before."""
    if not _WINDOWS:
        return path.read_bytes()
    deadline = time.monotonic() + _PUBLISH_WAIT
    while True:
        try:
            return path.read_bytes()
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_LOCK_POLL)


#: Plan AN.50 (50d1, D190): the folder of a store where each server and step
#: worker working on it holds a file of its own for its life, and the file a
#: key rotation holds while it has the store to itself.
ALIVE = "alive"
REKEYING = "rekeying.lock"


def hold_alive(root: str | Path, kind: str) -> Claim:
    """Mark this process alive on the store at `root` for as long as it keeps
    the returned claim (plan AN.50, 50d1, D190). The operating system lets go
    of it when the process ends, however it ends, so nothing is left to mean
    "alive" after a crash. kind: what the process is, as a word ("server",
    "worker"). Each claim has a file of its own, so a reused process number
    never meets an ended process's file."""
    if not re.fullmatch(r"[a-z]+", kind):
        raise ValueError("what is alive is named by one lower-case word")
    folder = Path(root) / ALIVE
    folder.mkdir(parents=True, exist_ok=True)
    held = claim(folder / f"{kind}-{os.getpid()}-{os.urandom(4).hex()}.lock")
    if held is None:
        raise OSError("this process's own mark of being alive is held by another")
    return held


def alive_on(root: str | Path) -> list[str]:
    """What is alive on the store at `root`: the name of each file a server or
    worker holds (plan AN.50, 50d1). A file nobody holds was left by a process
    that ended, and is removed."""
    folder = Path(root) / ALIVE
    found = []
    for path in sorted(folder.glob("*.lock")) if folder.is_dir() else ():
        held = claim(path)
        if held is None:
            found.append(path.stem)
            continue
        held.release()
        discard(path)  # where it could not be removed, it is removed when next looked at
    return found


def rekeying(root: str | Path) -> bool:
    """Whether a key rotation has the store at `root` to itself now (plan
    AN.50, 50d1): a server or worker that marked itself alive and then finds
    this refuses to start, and the rotation refuses while anything is alive,
    so the two never work on the store together."""
    path = Path(root) / REKEYING
    if not path.exists():
        return False
    held = claim(path)
    if held is None:
        return True
    held.release()
    return False


_SEP = "__"


def _legacy_split_positions(stem: str) -> tuple[int, ...]:
    """Every possible delimiter, including overlaps in runs of underscores."""
    return tuple(index for index in range(len(stem) - 1)
                 if stem[index:index + len(_SEP)] == _SEP)


def _transcript_payload(blob: bytes) -> dict:
    """Read a historical archive safely without inventing release evidence.

    Old archives need not have today's answer schema, but consumers still need
    attributable string identities and a sortable timestamp when one is present.
    JSON decoding alone proves none of those things.
    """
    document = json.loads(blob)
    if not isinstance(document, dict):
        raise ValueError("the transcript payload is not an object")
    if any(not isinstance(document.get(key), str) or blank(document[key])
           for key in ("matter_id", "turn_id")):
        raise ValueError("the transcript payload lacks attributable string identities")
    if "at" in document and not isinstance(document["at"], str):
        raise ValueError("the transcript timestamp is not text")
    return document


#: The shape of a kept history line's own record, changed when that shape changes; what the line
#: says is versioned by the code that derives it (the API), not here.
_LINE_FORMAT = 1

#: The scheme name `_Cipher` reports when it fell back. The envelope is NOT
#: built on that path: the opt-in exists so a developer with no `cryptography`
#: wheel can run the suite, and dressing that in envelope encryption would
#: make an explicitly insecure mode look like the secure one.
_INSECURE = "xor-keystream(NOT-SECURE)"

#: Plan AN.50 (50e, D191): the folder of a store where each matter's last
#: save is recorded beside it - its version and a hash of what was saved -
#: and the shape of that record.
_SAVED = "saved-versions"
_SAVED_FORMAT = 1
#: The store's own folders, never removed by an erasure that empties them (plan AN.53, D241).
_KEPT_FOLDERS = frozenset({"matters", "history-lines", "transcripts", "v2", "feedback", "saved-versions", "matter-owners", "keys",
                           "deleted"})
#: Plan AN.53 (D241's second piece): the folder where each conversation its advocate deleted is marked, the shape of a mark, and
#: how many days a deleted conversation can be put back before the sweep erases it.
_DELETED = "deleted"
_DELETED_FORMAT = 1
PUT_BACK_DAYS = 30
#: A deletion mark that is there and cannot be read: the conversation stays deleted - read by nothing, written by nothing - and
#: is never erased on it.
_UNREADABLE_MARK = object()

#: Plan AN.53 (53b, D217): the folder of a store where each matter's owner is
#: recorded beside it, and the shape of that record.
_OWNERS = "matter-owners"
_OWNER_FORMAT = 1


def owner_mark(advocate_id: str) -> str:
    """What an owner record holds of an advocate: a hash of the account's
    identifier, so the record names nobody. It is compared, never read back."""
    return hashlib.sha256(b"nm-matter-owner\0" + str(advocate_id).encode("utf8")).hexdigest()


class ErasureRefused(ValueError):
    """A conversation is not erased on a guess (plan AN.53, D241): one that cannot be opened and that nobody is recorded as
    owning cannot be known to be the asking advocate's."""


class RolledBack(ValueError):
    """The matter file on disk is not the one this store last saved: an older
    copy has been put in its place, or another file at the same version (plan
    AN.50, 50e, D191; the review's F-13). It is refused, never loaded as the
    current conversation and never saved over."""




@implements("I1")
class FileMatterStore:
    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._matters = self._root / "matters"
        self._metrics = self._root / "metrics"
        self._transcripts = self._root / "transcripts"
        # Made on the first rating, like the transcripts: an installation
        # nobody has rated a reply on keeps the directories it had.
        self._feedback = self._root / "feedback"
        # Made on the first line kept, like the transcripts (P35, O29).
        self._lines = self._root / "history-lines"
        self._keys = self._root / "keys"
        # Plan AN.53 (53b): the owner records this process has read or written.
        # A matter's owner never changes, so a record once known is not read again.
        self._owner_marks: dict[str, str] = {}
        self._matters.mkdir(parents=True, exist_ok=True)
        self._metrics.mkdir(parents=True, exist_ok=True)
        seal = key if key is not None else os.environ.get("NM_MATTER_KEY", "")
        self._cipher = _Cipher(seal)
        # THE SEAL BECOMES A KEY-ENCRYPTING KEY. P07, BK-85-AC2.
        #
        # It used to BE the data key, so every matter on an installation was
        # sealed with one value: a process that could read any matter could
        # read all of them, and rotating the seal meant re-encrypting every
        # matter or locking every advocate out. It did the second on 7
        # September 2026.
        #
        # Now each matter has its own random data key, wrapped under this and
        # never stored unwrapped. Rotation rewraps a few small records and
        # touches no ciphertext, and scope is the wrap itself -- a wrapped key
        # for one matter does not open another, enforced cryptographically
        # rather than by a check somebody can forget.
        self._sealer: MatterSealer | None = None
        if self._cipher.scheme != _INSECURE:
            self._sealer = MatterSealer(seal, self._keys)

    @property
    def scheme(self) -> str:
        """WHAT ACTUALLY SEALS THESE FILES, for `/api/health`.

        Both halves, because they are two different keys doing two different
        jobs and an operator reading one name would not know the other exists.
        """
        if self._sealer is None:
            return self._cipher.scheme
        return f"{self._cipher.scheme}+{self._sealer.scheme}"

    def upload_storage(self):
        """Composition-only factory: original bytes share this root and key scope.

        The returned adapter MUST be wrapped as UploadPort by composition.
        Insecure test ciphers never acquire an original-byte store.
        """
        from nm.shared.store_uploads import SealedUploadStore

        if self._sealer is None:
            raise EncryptionNotConfigured("original-byte uploads require the sealed store")
        return SealedUploadStore(self._root, self._sealer)

    def prepare_custody(self, matter_id: str) -> None:
        """Create a matter's data key once, for material stored before any record
        (an advocate's document space, 15 Oct 2026); an existing key is kept."""
        if self._sealer is None:
            raise EncryptionNotConfigured("sealed material requires the sealed store")
        self._sealer.matter_key(matter_id)

    def document_storage(self):
        """Composition-only derivative factory, using the same per-matter keys."""
        from nm.shared.store_documents import SealedDocumentStore

        if self._sealer is None:
            raise EncryptionNotConfigured("document derivatives require the sealed store")
        return SealedDocumentStore(self._root, self._sealer)

    # ------------------------------------------------------- the envelope ---

    def _seal(self, matter_id: str, data: bytes, *, create_key: bool = False) -> bytes:
        if self._sealer is None:
            return self._cipher.encrypt(data)
        return self._sealer.seal(matter_id, data, create_key=create_key)

    def _open(self, matter_id: str, blob: bytes) -> bytes:
        """A sealed record, or one written before there were any.

        THIS IS A FORMAT DISCRIMINATOR AND NOT A FALLBACK, and the difference
        matters enough to say so. `docs/BASELINE.md` records what a silent
        fallback with different behaviour costs -- the three-stores defect
        wearing a helpful face -- and that is a fallback whose RECALL differs.
        This one reads the same bytes either way and is decided by what the
        record says it is, so a CORRUPT SEALED RECORD IS NEVER RETRIED AS
        LEGACY: it raises, because a damaged record must not be reported as a
        record of another kind that also would not open.
        """
        if self._sealer is None or not is_envelope(blob):
            try:
                return self._cipher.decrypt(blob)
            except self._cipher.will_not_open as exc:
                # ONE ERROR FOR A RECORD THAT WILL NOT OPEN (plan AN.53, 53j1). An envelope that will not open raises
                # StoredObjectUnreadable; this path let the cipher library's own error out, which no caller names, so
                # an emptied or overwritten file was a different failure from a truncated one.
                raise StoredObjectUnreadable("a saved record could not be opened") from exc
        return self._sealer.open(str(matter_id), blob)

    def _path(self, matter_id: MatterId) -> Path:
        return self._matters / f"{_storage_component(matter_id, kind='matter ID')}.nm"

    def load(self, matter_id: MatterId) -> Matter | None:
        p = self._path(matter_id)
        if not p.exists() or self._deleted_mark(str(matter_id)) is not None:
            # A conversation its advocate deleted is read by nothing until it is put back (plan AN.53, D241).
            return None
        return self._read(str(matter_id), p)

    def _read(self, matter_id: str, path: Path) -> Matter:
        """One saved matter file, opened, checked to be the matter its name
        says and (plan AN.50, 50e) the file this store last saved there."""
        # THE RECORD IS READ BEFORE THE FILE (found 13 Nov 2026 by many reads beside many saves). A save puts the file
        # in place and then its record; a reader outside the save's lock that read the file first could then read the
        # record of the NEXT save and take its own, current file for an older copy. Read in this order, a record of
        # save N means the file of save N was already in place, so the file read after it is N or later.
        known = self._last_saved(matter_id)
        try:
            data = self._open(matter_id, read_published(path))
        except KeyUnavailable:
            raise
        except StoredObjectUnreadable as exc:
            raise _as_a_failed_reading(exc) from exc
        matter = _matter(*_said_format(json.loads(data.decode("utf8"))))
        if matter.id != matter_id:
            raise ValueError("the saved matter identity conflicts with its storage name")
        self._check_last_saved(matter_id, matter.version, data, known)
        self._record_owner(matter_id, matter.advocate_id)
        return matter

    # ------------------------------------------- the record of the last save ---
    #
    # AN OLDER COPY IS NOTICED (plan AN.50, 50e, D191; the review's F-13). The
    # only evidence of which save a matter file is was the version number
    # inside it, so an older copy put back in its place - by a restore of some
    # files and not others, a copying tool, a hand - loaded cleanly as the
    # current conversation and accepted new saves on top (measured, 11 Nov
    # 2026). Each save now leaves a small record beside the matter, written
    # inside the save's own lock: the version saved and a hash of what was
    # saved. A file below its record is refused.
    #
    # THE HASH IS OF WHAT WAS SAVED, BEFORE SEALING, so sealing the same matter
    # again under a new secret (the key rotation, 50d) leaves it the file that
    # was saved. The record holds no client words and is not sealed, like the
    # metrics.
    #
    # WHAT IT IS NOT. It is not a seal against tampering: whoever can replace
    # the file can remove the record. It notices accidents. A matter with no
    # record (saved before there were any), or one whose record cannot be
    # read, is NOT ASSESSED and loads as it did; its next save writes the
    # record. A folder restored whole brings its records with it and loads as
    # the backup left it: that is a restore, and the operator chose it.

    def _saved_path(self, matter_id: str) -> Path:
        return self._root / _SAVED / f"{_storage_component(matter_id, kind='matter ID')}.json"

    def _last_saved(self, matter_id: str) -> tuple[int, str] | None:
        """The version and hash this store last saved for the matter, or None
        where that is not known."""
        try:
            record = json.loads(self._saved_path(matter_id).read_text(encoding="utf8"))
        except (OSError, ValueError):
            return None
        if (not isinstance(record, dict) or record.get("format") != _SAVED_FORMAT
                or type(record.get("version")) is not int or not isinstance(record.get("sha256"), str)):
            return None
        return record["version"], record["sha256"]

    def _check_last_saved(self, matter_id: str, version: int, data: bytes, known: tuple[int, str] | None) -> None:
        """known: the record of the last save, read BEFORE the file was (see `_read`)."""
        if known is None or version > known[0]:
            # Not assessed, or AHEAD of its record: a save whose record was not
            # written (the process ended between the two, or code from before
            # there were records saved it). Forward is never a rollback.
            return
        if version < known[0]:
            raise RolledBack(
                f"matter {matter_id} was last saved at version {known[0]} and the file "
                f"in its place is version {version}: an older copy. It is not loaded as "
                "current. Put back the file that was saved; or, where the older copy is "
                f"the one meant, stop the server and remove {_SAVED}/{matter_id}.json.")
        if hashlib.sha256(data).hexdigest() != known[1]:
            raise RolledBack(
                f"matter {matter_id} is at version {version}, as last saved, and is not "
                "the file that was saved: another copy has been put in its place. It is "
                "not loaded as current.")

    def _record_last_saved(self, matter_id: str, version: int, data: bytes) -> None:
        """Called inside the matter's lock, after its file is in place. A
        record that could not be written leaves the file ahead of its record,
        which loads and which the next save mends - so it never fails a save
        that has happened."""
        path = self._saved_path(matter_id)
        record = json.dumps({"format": _SAVED_FORMAT, "version": version,
                             "sha256": hashlib.sha256(data).hexdigest()}).encode("utf8")
        tmp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(record)
                fh.flush()
                os.fsync(fh.fileno())
            publish(tmp, path)
        except OSError:
            if tmp is not None:
                discard(Path(tmp))

    # ---------------------------------------------- the record of the owner ---
    #
    # THE STORE KNOWS WHOSE EACH MATTER IS (plan AN.53, 53b, D217; the review's
    # F-21). Whose a saved file is was known only by opening it. So a listing
    # did work for every advocate's file on behalf of one, each caller had to
    # remember to compare the owner, and a file that could not be opened had
    # no owner at all: the history named it to every advocate and marked
    # every advocate's history as partial.
    #
    # Each matter now has a small record beside it of its owner, written when
    # the matter is first saved and whenever it is read and has none. It
    # holds a hash of the account's identifier and nothing else, and is not
    # sealed, like the record of the last save.
    #
    # WHAT IT IS NOT. It is not what decides whose a matter is: the sealed
    # file is, and every load for an advocate still compares the file's own
    # owner. The record only lets the store leave a file alone - not open
    # it, not name it - for an advocate it is recorded as not belonging to.
    # A matter with no record, or one that cannot be read, is NOT KNOWN: it
    # is offered to the caller as such, opened to learn whose it is, and a
    # file like that which cannot be opened is named to no advocate (see
    # `unowned_unreadable` for the operator's side).

    def _owner_path(self, matter_id: str) -> Path:
        return self._root / _OWNERS / f"{_storage_component(matter_id, kind='matter ID')}.json"

    def _owner_mark(self, matter_id: str) -> str | None:
        """The mark of the matter's recorded owner, or None where it is not known."""
        known = self._owner_marks.get(matter_id)
        if known is not None:
            return known
        try:
            record = json.loads(self._owner_path(matter_id).read_text(encoding="utf8"))
        except (OSError, ValueError):
            return None
        if (not isinstance(record, dict) or record.get("format") != _OWNER_FORMAT
                or not isinstance(record.get("owner"), str) or not record["owner"]):
            return None
        self._owner_marks[matter_id] = record["owner"]
        return record["owner"]

    def _record_owner(self, matter_id: str, advocate_id: str) -> None:
        """Called with what a file that was just saved or opened says of its
        owner. Written once: a record that already says so is left alone. A
        record that could not be written leaves the owner not known, which
        the next read mends - so it never fails a save or a read."""
        mark = owner_mark(advocate_id)
        tmp = None
        try:
            if self._owner_mark(matter_id) == mark:
                return
            path = self._owner_path(matter_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(json.dumps({"format": _OWNER_FORMAT, "owner": mark}).encode("utf8"))
                fh.flush()
                os.fsync(fh.fileno())
            publish(tmp, path)
            self._owner_marks[matter_id] = mark
        except OSError:
            if tmp is not None:
                discard(Path(tmp))

    def load_for(self, matter_id: MatterId, advocate_id: str) -> Matter | None:
        """The advocate's own matter, or None: where there is none, and where
        it is another's - which is then neither opened nor, if it cannot be
        opened, said to be damaged. A matter of the advocate's own, or one
        nobody is recorded as owning, that cannot be opened raises as `load`
        does."""
        mark = self._owner_mark(str(matter_id))
        if mark is not None and mark != owner_mark(advocate_id):
            return None
        matter = self.load(matter_id)
        return matter if matter is not None and matter.advocate_id == advocate_id else None

    def saved_files_for(self, advocate_id: str) -> tuple[tuple[str, tuple[int, int], str, bool | None], ...]:
        """`saved_files`, without the files recorded as another advocate's,
        each with whether it is known to be this advocate's: True, or None
        where no owner is recorded and the file itself must say."""
        mine, out = owner_mark(advocate_id), []
        for matter_id, signature, saved_at in self.saved_files():
            try:
                mark = self._owner_mark(matter_id)
            except ValueError:  # a file whose name is no matter's: not known, and its reading says why
                mark = None
            if (mark is None or mark == mine) and not self._deleted_path(matter_id).exists():
                # D241: a deleted conversation leaves the history at once, whoever's it is.
                out.append((matter_id, signature, saved_at, True if mark == mine else None))
        return tuple(out)

    def unowned_unreadable(self) -> tuple[str, ...]:
        """The saved files that cannot be opened and that nobody is recorded
        as owning: named to no advocate, and so listed here for the operator.
        It opens each file that has no owner record."""
        out = []
        for matter_id, _signature, _saved_at in self.saved_files():
            try:
                if self._owner_mark(matter_id) is None:
                    self._read(matter_id, self._matters / f"{matter_id}.nm")
            except Exception:  # noqa: BLE001 -- named, never swallowed
                out.append(matter_id)
        return tuple(out)

    # ------------------------------------------------------------------ erasure ---
    #
    # THE STORE'S ONE DELETE (plan AN.53, D241's first piece; the review's F-35). Nothing in NM could delete anything. D241, the
    # owner's policy, lets an advocate delete a conversation of their own with everything that belongs to it; this erases what
    # the store keeps of it - the conversation, its turns' records, its ratings, its line in the history, and the records of its
    # last save and of its owner. Its papers are kept in the advocate's document space, shared by their conversations, and go
    # after it (D244): the caller is given a LAST LOOK at the conversation - its owner, and its saved record as read before its
    # key went - once it is erased, and never for one whose erasure failed; and asks NAMING which of the papers it named another
    # conversation of the advocate's still names.
    #
    # THE KEY FIRST. The conversation's own data key is destroyed before any file is removed, so that whatever is left of it
    # anywhere - a copy, a backup, a file that could not be removed - can never be read. A key that cannot be destroyed removes
    # nothing. A conversation from before there were keys of their own has none to destroy: its files are removed, and the
    # receipt says so.
    #
    # ONLY THE ADVOCATE'S OWN, and never on a guess: another's conversation is not there for them (None, nothing changes), and
    # one that cannot be opened is erased by its owner only where the owner record says it is theirs.

    def erase(self, matter_id: MatterId, advocate_id: str, *, look=None) -> dict | None:
        """Erase the advocate's own conversation; None where there is none of theirs. Returns {matter_id, own_key,
        key_destroyed, left}: left names any file that could not be removed, which can no longer be read. look(owner, record),
        where given, is the last look at it (D244): the advocate, and its saved record as read before its key went, or None where
        the record could not be opened - given once it is erased, and never where the erasure fails."""
        matter_id = _storage_component(str(matter_id), kind="matter ID")
        with self._locked(matter_id):
            if not self._whose(matter_id, advocate_id):
                return None
            looked = self._looked_at(matter_id) if look is not None else None
            receipt = self._erase(matter_id)
            if look is not None:
                look(advocate_id, looked[1] if looked is not None and looked[0] == advocate_id else None)
            return receipt

    def _looked_at(self, matter_id: str) -> tuple[str, bytes] | None:
        """A saved conversation's owner, as its record says, and the record itself (D244); None where it cannot be opened."""
        try:
            data = self._open(matter_id, read_published(self._path(matter_id)))
            owner = json.loads(data.decode("utf8")).get("advocate_id")
        except Exception:  # noqa: BLE001 -- whatever stops it opening, what it names cannot be known
            return None
        return (owner, data) if isinstance(owner, str) else None

    def naming(self, advocate_id: str, papers) -> tuple[frozenset[str], int]:
        """Which of these papers a conversation the advocate keeps names - one in use, or one deleted and not yet erased - and how
        many of the conversations that may be theirs could not be read (plan AN.53, D244): a paper goes with the last
        conversation that names it, and none on a guess. Read from each record's text by the paper's own name; a name found
        inside a longer one only keeps that paper longer. Nothing is shown or changed."""
        wanted, named, unread, mine = {str(paper) for paper in papers}, set(), 0, owner_mark(advocate_id)
        for matter_id, _signature, _saved_at in self.saved_files():
            if not wanted - named:
                break
            try:
                mark = self._owner_mark(matter_id)
            except ValueError:  # a file whose name is no matter's: whose it is, its reading says
                mark = None
            if mark is not None and mark != mine:
                continue
            looked = self._looked_at(matter_id)
            if looked is None:
                try:
                    unread += self._path(matter_id).exists()  # one erased meanwhile names nothing
                except ValueError:  # a file whose name is no matter's and that will not open: whose it is cannot be known
                    unread += 1
                continue
            if looked[0] == advocate_id:
                named |= {paper for paper in wanted if paper.encode("utf8") in looked[1]}
        return frozenset(named), unread

    def _whose(self, matter_id: str, advocate_id: str) -> bool | None:
        """True where the conversation is the advocate's own, False where it is another's, None where there is none. Its owner
        record says; where there is none, the file itself, which must open. Raises ErasureRefused where it cannot be opened and
        nobody is recorded as owning it: nothing is done to a conversation on a guess."""
        mark = self._owner_mark(matter_id)
        if mark is not None:
            return mark == owner_mark(advocate_id)
        path = self._path(matter_id)
        if not path.exists():
            return None
        try:
            return self._read(matter_id, path).advocate_id == advocate_id
        except Exception as exc:  # noqa: BLE001 -- whatever stops it opening, whose it is cannot be known
            raise ErasureRefused(f"matter {matter_id} cannot be opened and nobody is recorded as owning it: nothing is done "
                                 "to it") from exc

    def _erase(self, matter_id: str) -> dict:
        """Called inside the matter's lock, its owner decided: the key first, then every file."""
        own_key = self._sealer is not None and (self._keys / f"{matter_id}.key").exists()
        destroyed = self._sealer.destroy(matter_id) if self._sealer is not None else False
        left = [str(target.relative_to(self._root)) for target in self._erasable(matter_id) if not self._remove(target)]
        self._owner_marks.pop(matter_id, None)
        return {"matter_id": matter_id, "own_key": own_key, "key_destroyed": destroyed, "left": left}

    # ------------------------------------------------------- deleted, and put back ---
    #
    # DELETE, AS AN ADVOCATE DOES (plan AN.53, D241's second piece). A conversation its advocate deletes leaves their history at
    # once and, for PUT_BACK_DAYS, can be put back: for an advocate an accidental deletion of a client's matter is the likelier
    # harm than a late erasure. After that the sweep erases it, its own key first. NM NEVER DELETES A CONVERSATION BY ITSELF:
    # only one its advocate deleted is ever swept. While it is deleted nothing reads it (load) and nothing writes to it (commit),
    # so a stale page's message neither brings it back nor is erased with it. The mark beside it holds a hash of its owner and
    # the moment it was deleted, nothing else, and is not sealed, like the owner record.

    def _deleted_path(self, matter_id: str) -> Path:
        return self._root / _DELETED / f"{_storage_component(matter_id, kind='matter ID')}.json"

    def _deleted_mark(self, matter_id: str):
        """The deletion mark ({owner, at}), None where the conversation is not deleted, or _UNREADABLE_MARK."""
        try:
            record = json.loads(self._deleted_path(matter_id).read_text(encoding="utf8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return _UNREADABLE_MARK
        try:
            if (not isinstance(record, dict) or record.get("format") != _DELETED_FORMAT
                    or not isinstance(record.get("owner"), str) or not isinstance(record.get("at"), str)):
                return _UNREADABLE_MARK
            at = datetime.fromisoformat(record["at"])
        except ValueError:
            return _UNREADABLE_MARK
        return _UNREADABLE_MARK if at.utcoffset() is None else {"owner": record["owner"], "at": at}

    @staticmethod
    def _deleted_said(matter_id: str, at: datetime) -> dict:
        return {"matter_id": matter_id, "deleted_at": at.isoformat(),
                "erased_after": (at + timedelta(days=PUT_BACK_DAYS)).isoformat()}

    def mark_deleted(self, matter_id: MatterId, advocate_id: str, at: datetime) -> dict | None:
        """Delete the advocate's own conversation, to be put back within PUT_BACK_DAYS; None where there is none of theirs. A
        conversation deleted again keeps its first date: the days run from the first deletion."""
        matter_id = _storage_component(str(matter_id), kind="matter ID")
        if at.utcoffset() is None:
            raise ValueError("a deletion is dated with its offset")
        with self._locked(matter_id):
            if not self._whose(matter_id, advocate_id):
                return None
            existing = self._deleted_mark(matter_id)
            if isinstance(existing, dict):
                return self._deleted_said(matter_id, existing["at"])
            path = self._deleted_path(matter_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(json.dumps({"format": _DELETED_FORMAT, "owner": owner_mark(advocate_id),
                                         "at": at.isoformat()}).encode("utf8"))
                    fh.flush()
                    os.fsync(fh.fileno())
                publish(tmp, path)
            except BaseException:
                discard(Path(tmp))
                raise
            return self._deleted_said(matter_id, at)

    def put_back(self, matter_id: MatterId, advocate_id: str) -> bool:
        """Put back the advocate's own deleted conversation, as it was deleted; False where there is none of theirs to put back."""
        matter_id = _storage_component(str(matter_id), kind="matter ID")
        with self._locked(matter_id):
            if self._deleted_mark(matter_id) is None or not self._whose(matter_id, advocate_id):
                return False
            return self._remove(self._deleted_path(matter_id))

    def deleted_for(self, advocate_id: str) -> tuple[dict, ...]:
        """The advocate's own deleted conversations, each with when it was deleted and when it will be erased; oldest first."""
        mine, out = owner_mark(advocate_id), []
        folder = self._root / _DELETED
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
            mark = self._deleted_mark(path.stem)
            if isinstance(mark, dict) and mark["owner"] == mine:
                out.append(self._deleted_said(path.stem, mark["at"]))
        return tuple(sorted(out, key=lambda said: (said["deleted_at"], said["matter_id"])))

    def sweep_deleted(self, now: datetime, *, look=None) -> tuple[str, ...]:
        """Erase every conversation its advocate deleted PUT_BACK_DAYS or more before now, its own key first; returns which. One
        whose mark cannot be read is never erased on it; one whose owner record, or whose own record, names someone else than
        its mark is left. look(owner, record), where given, is the last look at each (D244): its owner and its saved record as
        read before its key went, or (None, None) where the record could not be opened - given once it is erased, and never for
        one whose erasure failed."""
        erased = []
        folder = self._root / _DELETED
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
            matter_id = path.stem
            try:
                _storage_component(matter_id, kind="matter ID")
            except ValueError:
                continue
            with self._locked(matter_id):
                mark = self._deleted_mark(matter_id)
                if not isinstance(mark, dict) or now < mark["at"] + timedelta(days=PUT_BACK_DAYS):
                    continue
                recorded = self._owner_mark(matter_id)
                if recorded is not None and recorded != mark["owner"]:
                    continue
                looked = self._looked_at(matter_id)
                if looked is not None and owner_mark(looked[0]) != mark["owner"]:
                    continue
                self._erase(matter_id)
                erased.append(matter_id)
                if look is not None:
                    look(*(looked if looked is not None else (None, None)))
        return tuple(erased)

    def _erasable(self, matter_id: str) -> list[Path]:
        """Every file the store keeps of one conversation, the conversation first and its owner record last - so that an erasure
        cut off part-way can be asked for again by the same advocate."""
        found = [self._path(matter_id), self._line_path(matter_id)]
        named = self._transcripts / "v2" / _transcript_component(matter_id)
        if named.is_dir():
            found += sorted(named.glob("*.nm"))
        if self._transcripts.is_dir():
            found += [p for p in sorted(self._transcripts.glob(f"{matter_id}{_SEP}*.nm"))
                      if len(_legacy_split_positions(p.stem)) == 1]
        rated = self._feedback / matter_id
        if rated.is_dir():
            found += sorted(rated.glob("*/*.json"))
        # The owner record, then the deletion mark, last: an erasure cut off part-way can be asked for again, and swept again.
        return [*found, self._saved_path(matter_id), self._owner_path(matter_id), self._deleted_path(matter_id)]

    def _remove(self, path: Path) -> bool:
        """Remove one file, and the folders it leaves empty below the store's own; True where it is gone."""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        for folder in (path.parent, path.parent.parent):
            if folder != self._root and self._root in folder.parents and folder.name not in _KEPT_FOLDERS:
                try:
                    folder.rmdir()
                except OSError:
                    break  # not empty, or not a folder this erasure made empty
        return True

    def commit(self, matter: Matter, *, expected_version: int) -> Matter:
        """Write the matter, or refuse because the file moved underneath.

        HELD UNDER A PER-MATTER LOCK, across the read AND the replace.
        `os.replace` below is atomic and makes this crash-safe; it does
        nothing about two writers. Both could load version N, both find
        the version check satisfied, both encrypt, and the second replace
        would silently discard the first turn's work.

        The lock is the smallest thing that closes that. A real
        transactional store is the right long-run answer and is a
        migration; this does not pretend to be one.
        """
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a nonnegative integer")
        p = self._path(matter.id)
        with self._locked(matter.id):
            if self._deleted_mark(str(matter.id)) is not None:
                # Plan AN.53 (D241): nothing writes to a conversation its advocate deleted - a stale page's save must neither
                # bring it back nor be erased with it, and nothing new is begun under its name until it is put back or erased.
                raise StaleWrite(f"matter {matter.id} was deleted by its advocate and is not written to; put it back first.")
            current = self.load(matter.id)
            if current is None and expected_version != 0:
                # Absence is an initial-create precondition, not permission
                # to resurrect a previously loaded matter from a stale turn.
                raise StaleWrite(
                    f"matter {matter.id} was expected at version {expected_version} "
                    "and is absent. Re-derive against the current state."
                )
            # `!=`, NOT `>`. A writer holding a stale HIGHER version --
            # from a restored file or a bug -- must also be refused.
            if current is not None and current.version != expected_version:
                raise StaleWrite(
                    f"matter {matter.id} moved from version {expected_version} to "
                    f"{current.version} while this turn was deriving. Re-derive "
                    f"against the current state rather than overwriting it."
                )
            data = json.dumps({**_enc(matter), _FORMAT_KEY: MATTER_FORMAT}).encode("utf8")
            blob = self._seal(str(matter.id), data, create_key=current is None)
            # Atomic: a crash mid-write leaves the previous file intact.
            fd, tmp = tempfile.mkstemp(dir=str(self._matters), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(blob)
                    fh.flush()
                    os.fsync(fh.fileno())
                publish(tmp, p)
            except BaseException:
                # A ROLLBACK: the write failed, so the partial temporary must
                # go. Routed through `discard` so a failure removing it cannot
                # replace the exception that says what actually went wrong.
                discard(Path(tmp))
                raise
            self._record_last_saved(str(matter.id), matter.version, data)
            self._record_owner(str(matter.id), matter.advocate_id)
            return matter

    @contextmanager
    def _locked(self, matter_id: MatterId):
        """Exclusive access to one matter, for the length of a commit.

        THE LOCK IS THE OPERATING SYSTEM'S (plan AN.50, D187): a `claim` on
        the matter's lock file, which its holder's death lets go. It was the
        lock file's existence, made by an exclusive create and removed
        after; a server killed between the two left the file, and every
        later save of that matter waited and was refused until someone
        removed it by hand (F-08). Now a killed holder leaves nothing that
        refuses the next save, and no sweeper is needed beside the lock.

        A WAIT THAT NEVER ENDS IS A HANG, so it gives up and says so. The
        caller sees `StaleWrite`, which is already the answer to `somebody
        else is writing this matter` -- a new exception type would be a
        second name for one condition.
        """
        lock = self._matters / f"{_storage_component(matter_id, kind='matter ID')}.lock"
        deadline = time.monotonic() + _LOCK_TIMEOUT
        held = claim(lock)
        while held is None:
            if time.monotonic() >= deadline:
                raise StaleWrite(
                    f"matter {matter_id} is being written by another "
                    f"turn and did not become free within "
                    f"{_LOCK_TIMEOUT}s. Re-derive and try again."
                )
            time.sleep(_LOCK_POLL)
            held = claim(lock)
        try:
            yield
        finally:
            # HOUSEKEEPING. The commit inside the block either happened or it
            # did not, and releasing the lock does not change which -- so a
            # failure here must never surface as a failed save the caller
            # retries against a matter that was already written. A lock that
            # could not be unlocked is let go when its file is closed.
            try:
                held.release()
            except OSError:
                pass

    def list_for(self, advocate_id: str) -> MatterList:
        out, unreadable, saved_at = [], [], []
        # Plan AN.53 (53b): only the files not recorded as another advocate's.
        for matter_id, _signature, stamp, owned in self.saved_files_for(advocate_id):
            try:
                _storage_component(matter_id, kind="matter ID")
                m = self._read(matter_id, self._matters / f"{matter_id}.nm")
            except Exception:  # noqa: BLE001 -- named, never swallowed
                # One unreadable matter must not take the whole list down, and
                # it must not VANISH either. It used to `continue` here with a
                # comment claiming the caller reported it; the caller received a
                # bare tuple and could not tell six matters from seven with one
                # corrupt. The id is carried out so the board can say so - to
                # the advocate it is recorded as belonging to, and to no other:
                # one nobody is recorded as owning is in `unowned_unreadable`.
                if owned:
                    unreadable.append(matter_id)
                continue
            if m.advocate_id == advocate_id:
                out.append(m)
                # F-B-14. WHEN IT WAS LAST SAVED is the file's own write time:
                # every commit replaces the file whole, so this moves on every
                # kind of change and on nothing else.
                saved_at.append((str(m.id), stamp))
        return MatterList(tuple(out), tuple(unreadable), tuple(saved_at))

    def signature(self, matter_id: MatterId) -> tuple[int, int] | None:
        """WHETHER A SAVED MATTER HAS CHANGED, without opening it: its file's write time and
        size, or None when there is no such file. Every commit replaces the file whole, so a
        read made of an unchanged file is still a read of what is saved (P35, 21 Oct 2026:
        reading one long conversation again took seconds each time it was opened)."""
        try:
            stat = self._path(matter_id).stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def saved_files(self) -> tuple[tuple[str, tuple[int, int], str], ...]:
        """Every saved matter's id, signature and when it was last saved, without opening any
        (P35): a listing reopens only the files that changed since it last read them."""
        out = []
        for p in sorted(self._matters.glob("*.nm")):
            try:
                stat = p.stat()
            except FileNotFoundError:
                continue
            out.append((p.stem, (stat.st_mtime_ns, stat.st_size),
                        save_stamp(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))))
        return tuple(out)

    # ------------------------------------------------ the history's kept lines ---
    #
    # THE HISTORY'S LINE FOR EACH SAVED FILE (P35, O29, 26 Oct 2026). Whose a saved file is, and
    # what the history shows of it, is known only by opening it - and a long conversation is
    # tens of megabytes, so listing a store opened and checked every file, seconds on each first
    # call. One small line per file, derived once per version of the file (its write time and
    # size), lets the history read lines and open a large file only when it has changed.
    #
    # A LINE CARRIES CLIENT WORDS (the first message), so it is sealed as the matter is: under the
    # matter's own key, which means erasing a matter's key makes its line unreadable too, or under
    # the installation seal for a record saved before there were keys of their own. It is kept
    # BESIDE the matter and never in it: a line written into the file would change the file's
    # signature, and the signature is what says a line is still current.

    def _line_path(self, matter_id: MatterId) -> Path:
        return self._lines / f"{_storage_component(matter_id, kind='matter ID')}.nm"

    def kept_line(self, matter_id: MatterId, signature: tuple[int, int]) -> dict | None:
        """The line kept for exactly this version of this saved matter, or None.

        NONE IS NEVER AN ERROR AND NEVER A STATEMENT ABOUT THE MATTER. A line is derived data: one
        that is missing, was kept for another version of the file, will not open or is not what it
        should be is simply no line, and the caller derives it again from the file itself - which
        is where a real fault in the matter surfaces."""
        path = self._line_path(matter_id)
        try:
            document = json.loads(self._open(str(matter_id), path.read_bytes()).decode("utf8"))
        except Exception:  # noqa: BLE001 -- derived data that will not open is no line
            return None
        if (not isinstance(document, dict) or document.get("format") != _LINE_FORMAT
                or document.get("matter_id") != str(matter_id)
                or document.get("signature") != [signature[0], signature[1]]
                or not isinstance(document.get("line"), dict)):
            return None
        return document["line"]

    def keep_line(self, matter_id: MatterId, signature: tuple[int, int], line: dict) -> None:
        """Keep a line derived from this version of this saved matter. It never creates a key.

        A matter saved before there were keys of their own has none, and its line is sealed as its
        file is. A matter whose file IS sealed under a key that is now gone has been erased: its
        line is not kept under the installation seal, which would leave its first message readable
        after the matter itself could not be."""
        path = self._line_path(matter_id)
        data = json.dumps({"format": _LINE_FORMAT, "matter_id": str(matter_id),
                           "signature": [signature[0], signature[1]], "line": line}).encode("utf8")
        try:
            blob = self._seal(str(matter_id), data)
        except KeyUnavailable:
            with open(self._path(matter_id), "rb") as fh:
                if is_envelope(fh.read(64)):
                    raise
            blob = self._cipher.encrypt(data)
        self._lines.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._lines), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
            publish(tmp, path)
        except BaseException:
            discard(Path(tmp))
            raise

    def record_metrics(self, metrics: dict) -> None:
        """Written even when the turn failed, and never containing client words.

        THE SECOND HALF WAS A CLAIM AND IS NOW A CONTROL. It held only while no
        gate detail quoted the matter, and P22's limitation reasoning ended
        that: `G-PREMISE` fires naming the chronology entry the period was run
        from, which is a sentence the advocate typed. It is `TurnMetrics
        .as_dict` -- the REDACTED projection, and the default for exactly this
        reason -- that makes the line true; the full record is `as_served`, and
        it goes to the advocate over an authenticated response and never here.
        """
        turn_id = _storage_component(metrics['turn_id'], kind="turn ID")
        path = self._metrics / f"{turn_id}.json"
        path.write_text(json.dumps(metrics, indent=2), encoding="utf8")

    def sweep_metrics(self, before: datetime) -> int:
        """Every turn's metrics written before `before` go (plan AN.53, D241: the counts and timings of turns, which hold no
        content, are kept two years); returns how many. Aged by when each was last written; one that cannot be removed is left
        for the next sweep."""
        if before.utcoffset() is None:
            raise ValueError("a sweep is dated with its offset")
        cut, gone = before.timestamp(), 0
        for path in sorted(self._metrics.glob("*.json")):
            try:
                if path.stat().st_mtime < cut:
                    path.unlink()
                    gone += 1
            except OSError:  # gone meanwhile, or it will not go now: the next sweep sees it again
                continue
        return gone

    # ------------------------------------------------------- transcripts ---
    #
    # A TRANSCRIPT IS NOT A METRIC, and the difference decides how it is
    # written. `record_metrics` is plaintext BECAUSE it carries no client
    # words; a transcript is the advocate's own message and the answer served
    # back, so it is privileged material and gets the matter cipher.
    #
    # Writing them beside the metrics as JSON would have been the obvious
    # move and would have put client instructions on disk in the clear, in a
    # directory whose whole convention is that its contents are safe to read.

    def record_turn(self, transcript: dict) -> None:
        """The served turn, in full, for later review.

        Nothing else keeps it. The matter holds facts and questions, the
        metrics hold counts, and the ANSWER -- the thing the advocate actually
        read -- was held by neither, so a run could be inspected only while its
        stdout was still on screen.

        Sealed with the same key as the matter, because a transcript nobody
        can open is useless and one anybody can open is a disclosure.

        THE MATTER IS IN THE FILENAME, and that is not a convenience.

        It was keyed by turn id alone, so the only way to learn which matter a
        transcript belonged to was to DECRYPT it -- and a transcript that
        cannot be decrypted is exactly the one whose attribution matters.
        `transcripts_for` therefore had to append every undecryptable file to
        whichever matter was being asked about, so a single corrupt turn
        marked EVERY matter `incomplete` and put a stranger's turn id on each
        of them.

        Attribution must not depend on being able to read the payload.
        """
        matter = str(transcript.get("matter_id") or "unattributed")
        matter = _storage_component(matter, kind="matter ID")
        turn_id = _storage_component(transcript['turn_id'], kind="turn ID")
        self._transcripts.mkdir(parents=True, exist_ok=True)
        if (_SEP in matter or _SEP in turn_id
                or matter.endswith("_") or turn_id.startswith("_")):
            # A flat `matter__turn` name has more than one possible split.
            # Keep simple historical names readable, but write ambiguous new
            # pairs under two canonical, individually bounded components.
            path = (self._transcripts / "v2" / _transcript_component(matter)
                    / f"{_transcript_component(turn_id)}.nm")
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path = self._transcripts / f"{matter}{_SEP}{turn_id}.nm"
        blob = self._seal(
            matter,
            json.dumps(transcript, indent=2, default=str).encode("utf8"))
        path.write_bytes(blob)

    def transcripts_for(self, matter_id: MatterId) -> tuple[dict, ...]:
        """Every recorded turn on one matter, oldest first.

        AN UNREADABLE TRANSCRIPT IS SKIPPED AND SAID SO, in the same shape
        `list_for` reports an unreadable matter: it carries `unreadable: True`
        and the reason rather than vanishing, because a review that silently
        drops the turn it could not decrypt is reviewing a different
        conversation from the one that ran.
        """
        matter_id = _storage_component(matter_id, kind="matter ID")
        if not self._transcripts.exists():
            return ()
        out: list[dict] = []

        encoded = self._transcripts / "v2" / _transcript_component(matter_id)
        if encoded.exists():
            for p in sorted(encoded.glob("*.nm")):
                owned_turn = p.stem
                try:
                    owned_turn = _read_transcript_component(p.stem)
                    document = _transcript_payload(self._open(matter_id, p.read_bytes()))
                    if document["matter_id"] != matter_id or document["turn_id"] != owned_turn:
                        raise ValueError("the transcript identity conflicts with its archive name")
                    out.append(document)
                except Exception as exc:  # noqa: BLE001 -- reported, never dropped
                    out.append({"turn_id": owned_turn, "matter_id": matter_id,
                                "unreadable": True, "why": f"{type(exc).__name__}: {exc}"})

        # THE FILES THIS MATTER OWNS, by name. An unreadable one among these
        # is genuinely this matter's and is reported as missing FROM THIS
        # RECORD; an unreadable file belonging to another matter is not.
        for p in sorted(self._transcripts.glob(f"{matter_id}{_SEP}*.nm")):
            if len(_legacy_split_positions(p.stem)) > 1:
                # An old name with several separators cannot attribute a
                # corrupt blob. A readable payload can resolve the split;
                # otherwise `unattributable()` counts it once, never on both
                # possible matters' histories.
                document = self._legacy_ambiguous_transcript(p)
                if document is not None and document["matter_id"] == matter_id:
                    out.append(document)
                continue
            owned_turn = p.stem[len(matter_id) + len(_SEP):]
            try:
                document = _transcript_payload(self._open(str(matter_id), p.read_bytes()))
                if document["matter_id"] != matter_id or document["turn_id"] != owned_turn:
                    raise ValueError("the transcript identity conflicts with its archive name")
                out.append(document)
            except Exception as exc:  # noqa: BLE001 -- reported, never dropped
                out.append({"turn_id": owned_turn,
                            "matter_id": matter_id, "unreadable": True,
                            "why": f"{type(exc).__name__}: {exc}"})

        # TRANSCRIPTS WRITTEN BEFORE THE NAME CARRIED THE MATTER. Their
        # attribution still requires decryption, and one that fails is
        # UNATTRIBUTABLE -- so it is reported by `unattributable()`, once,
        # rather than added to whichever matter happened to ask.
        for p in sorted(self._transcripts.glob("*.nm")):
            if _SEP in p.name:
                continue
            try:
                doc = _transcript_payload(self._cipher.decrypt(p.read_bytes()))
            except Exception:  # noqa: BLE001 -- counted by unattributable()
                continue
            if doc.get("matter_id") == matter_id:
                out.append(doc)

        return tuple(sorted(out, key=lambda d: d.get("at", "")))

    def _legacy_ambiguous_transcript(self, path: Path) -> dict | None:
        """Resolve an old multi-separator name only from a matching payload.

        No candidate receives an unreadable row: without the payload there is
        no sound way to say which of its possible matter prefixes owned it.
        """
        try:
            blob = path.read_bytes()
        except OSError:
            return None
        stem = path.stem
        for position in _legacy_split_positions(stem):
            matter, turn = stem[:position], stem[position + len(_SEP):]
            if not turn or _STORAGE_COMPONENT.fullmatch(matter) is None:
                continue
            try:
                document = _transcript_payload(self._open(matter, blob))
            except Exception:  # noqa: BLE001 -- a possible split is not an attribution
                continue
            if document["matter_id"] == matter and document["turn_id"] == turn:
                return document
        return None

    def unattributable(self) -> tuple[str, ...]:
        """Transcripts on disk that belong to NO KNOWN MATTER.

        A legacy file that will not decrypt cannot be attributed at all -- its
        matter is inside the ciphertext. Silently dropping it would be the
        absent-input shape, and adding it to every matter's record was the
        defect this replaced. So it is neither: it is counted here, and the
        edge discloses it as a fact about the STORE rather than about any one
        conversation.
        """
        if not self._transcripts.exists():
            return ()
        lost: list[str] = []
        for p in sorted(self._transcripts.glob("*.nm")):
            if _SEP in p.name:
                if (len(_legacy_split_positions(p.stem)) > 1
                        and self._legacy_ambiguous_transcript(p) is None):
                    lost.append(p.stem)
                continue
            try:
                _transcript_payload(self._cipher.decrypt(p.read_bytes()))
            except Exception:  # noqa: BLE001 -- that IS the finding
                lost.append(p.stem)
        return tuple(lost)

    # ---------------------------------------------------------- feedback ---
    #
    # A RATING IS NOT A CHANGE TO THE MATTER (LB-56, LB-83). It is kept beside
    # the file, like the metrics, so rating a reply never moves the matter's
    # version. It carries identifiers, a rating and a time -- no client words --
    # so, like the metrics, it is not sealed.

    def record_feedback(self, feedback: dict) -> None:
        """Add one rating. NOTHING IS OVERWRITTEN: each rating is its own file,
        so a changed mind keeps its history.

        The reply is the folder and the entry's place in the reply's sequence
        is the name, so which reply an entry rates, and in what order, is known
        even for an entry that cannot be read back -- the lesson `record_turn`
        records. THE ORDER IS A SEQUENCE, NOT THE CLOCK: two clicks inside one
        clock tick must not come back in either order. Each number is claimed
        by an exclusive create, so two writers cannot take the same one.
        """
        matter = _storage_component(feedback["matter_id"], kind="matter ID")
        turn = _storage_component(feedback["turn_id"], kind="turn ID")
        folder = self._feedback / matter / turn
        folder.mkdir(parents=True, exist_ok=True)
        data = json.dumps(feedback).encode("utf8")
        while True:
            taken = [int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()]
            path = folder / f"{max(taken, default=0) + 1:06d}.json"
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                             | getattr(os, "O_BINARY", 0))
            except FileExistsError:
                continue
            break
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())

    def feedback_for(self, matter_id: MatterId) -> tuple[dict, ...]:
        """Every rating on one matter; each reply's in the order recorded.

        AN ENTRY THAT CANNOT BE READ COMES BACK NAMED, with the reply it
        belongs to, rather than vanishing: a lost thumbs-down must not read as
        no rating at all. A write interrupted part-way reads the same way.
        """
        matter = _storage_component(matter_id, kind="matter ID")
        root = self._feedback / matter
        if not root.is_dir():
            return ()
        named = []
        for p in root.glob("*/*.json"):
            turn = p.parent.name
            try:
                row = json.loads(p.read_text(encoding="utf8"))
                if (not isinstance(row, dict) or row.get("matter_id") != matter
                        or row.get("turn_id") != turn):
                    raise ValueError("the rating's identity conflicts with where it is kept")
            except (OSError, ValueError) as exc:
                row = {"matter_id": matter, "turn_id": turn, "unreadable": True,
                       "why": f"{type(exc).__name__}: {exc}"}
            named.append(((turn, int(p.stem) if p.stem.isdigit() else 0, p.name), row))
        return tuple(row for _, row in sorted(named, key=lambda pair: pair[0]))
