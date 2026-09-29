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
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from nm.shared.names_contracts import discard
from nm.shared.operation_contracts import save_stamp
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
        try:
            from cryptography.fernet import Fernet

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


def _decode(cls, value):
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
    """
    if value is None:
        return None

    origin = get_origin(cls)
    if origin in (Union, UnionType):
        inner = [a for a in get_args(cls) if a is not type(None)]
        return _decode(inner[0], value) if inner else value
    if origin in (tuple, list, set, frozenset):
        args = get_args(cls)
        item = args[0] if args else None
        seq = [_decode(item, v) if item else v for v in value]
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
            hints = get_type_hints(cls)
            return cls(**{f.name: _decode(hints.get(f.name, object),
                                          value.get(f.name))
                          for f in fields(cls) if f.name in value})
        if issubclass(cls, Enum):
            return cls(value)
        if cls is date:
            return date.fromisoformat(value) if isinstance(value, str) else value
    return value


def _fact(d: dict) -> Fact:
    return _decode(Fact, d)


def _matter(d: dict) -> Matter:
    """THE SAME SYMMETRY, at the top level.

    This was a hand-written field list for one release longer than the
    inner types were, and it failed in exactly the way the inner ones had:
    the ask ledger was encoded on every commit and dropped on every load,
    so a question answered before a restart would be asked again after it.

    There is now no hand-written decoder anywhere in this module.
    """
    return _decode(Matter, d)


# ------------------------------------------------------------------ store ---


#: Separates the matter from the turn in a transcript filename.
#:
#: Two underscores, because a MatterId is `mat_<hex>` and a single one would
#: split at the wrong place. The name has to be parseable WITHOUT THE KEY --
#: that is the whole point of putting the matter in it.
#: How long a commit waits for another turn to finish writing the SAME
#: matter. Long enough that an ordinary turn never meets it, short
#: enough that a crashed holder does not stall a practice.
_LOCK_TIMEOUT = 10.0
_LOCK_POLL = 0.02


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


#: The scheme name `_Cipher` reports when it fell back. The envelope is NOT
#: built on that path: the opt-in exists so a developer with no `cryptography`
#: wheel can run the suite, and dressing that in envelope encryption would
#: make an explicitly insecure mode look like the secure one.
_INSECURE = "xor-keystream(NOT-SECURE)"




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
        self._keys = self._root / "keys"
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
            return self._cipher.decrypt(blob)
        return self._sealer.open(str(matter_id), blob)

    def _path(self, matter_id: MatterId) -> Path:
        return self._matters / f"{_storage_component(matter_id, kind='matter ID')}.nm"

    def load(self, matter_id: MatterId) -> Matter | None:
        p = self._path(matter_id)
        if not p.exists():
            return None
        matter = _matter(json.loads(
            self._open(str(matter_id), p.read_bytes()).decode("utf8")))
        if matter.id != matter_id:
            raise ValueError("the saved matter identity conflicts with its storage name")
        return matter

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
            blob = self._seal(
                str(matter.id), json.dumps(_enc(matter)).encode("utf8"),
                create_key=current is None)
            # Atomic: a crash mid-write leaves the previous file intact.
            fd, tmp = tempfile.mkstemp(dir=str(self._matters), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(blob)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, p)
            except BaseException:
                # A ROLLBACK: the write failed, so the partial temporary must
                # go. Routed through `discard` so a failure removing it cannot
                # replace the exception that says what actually went wrong.
                discard(Path(tmp))
                raise
            return matter

    @contextmanager
    def _locked(self, matter_id: MatterId):
        """Exclusive access to one matter, for the length of a commit.

        `O_CREAT | O_EXCL` is atomic on POSIX and on Windows, needs no
        third-party library, and behaves the same on the junction-mounted
        paths this project already uses.

        THE LOCK NAMES ITS HOLDER. A lock file carrying nothing is one
        nobody can reason about when it is found at 3am: this one holds
        the pid and the time it was taken, so a stale lock is identifiable
        rather than guessed at.

        A WAIT THAT NEVER ENDS IS A HANG, so it gives up and says so. The
        caller sees `StaleWrite`, which is already the answer to `somebody
        else is writing this matter` -- a new exception type would be a
        second name for one condition.
        """
        lock = self._matters / f"{_storage_component(matter_id, kind='matter ID')}.lock"
        deadline = time.monotonic() + _LOCK_TIMEOUT
        fd = None
        while fd is None:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise StaleWrite(
                        f"matter {matter_id} is being written by another "
                        f"turn and did not become free within "
                        f"{_LOCK_TIMEOUT}s. Re-derive and try again; the "
                        f"lock file is {lock.name} and names its holder."
                    ) from None
                time.sleep(_LOCK_POLL)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(f"pid={os.getpid()} at={time.time():.3f}")
            yield
        finally:
            # HOUSEKEEPING. The commit inside the block either happened or it
            # did not, and releasing the lock does not change which -- so a
            # failure here must never surface as a failed save the caller
            # retries against a matter that was already written. A lock that
            # could not be released stays, and the next writer's `StaleWrite`
            # already names its holder.
            discard(lock)

    def list_for(self, advocate_id: str) -> MatterList:
        out, unreadable, saved_at = [], [], []
        for p in sorted(self._matters.glob("*.nm")):
            try:
                _storage_component(p.stem, kind="matter ID")
                m = _matter(json.loads(
                    self._open(p.stem, p.read_bytes()).decode("utf8")))
                if m.id != p.stem:
                    raise ValueError("the saved matter identity conflicts with its storage name")
            except Exception:  # noqa: BLE001 -- named, never swallowed
                # One unreadable matter must not take the whole list down, and
                # it must not VANISH either. It used to `continue` here with a
                # comment claiming the caller reported it; the caller received a
                # bare tuple and could not tell six matters from seven with one
                # corrupt. The id is carried out so the board can say so.
                unreadable.append(p.stem)
                continue
            if m.advocate_id == advocate_id:
                out.append(m)
                # F-B-14. WHEN IT WAS LAST SAVED is the file's own write time:
                # every commit replaces the file whole, so this moves on every
                # kind of change and on nothing else.
                saved_at.append((str(m.id), save_stamp(
                    datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc))))
        return MatterList(tuple(out), tuple(unreadable), tuple(saved_at))

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
