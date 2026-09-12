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
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, fields, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from nm.adapters.store.sealing import MatterSealer, is_envelope
from nm.domain.matter import (
    Fact,
    Matter,
    MatterId,
)
from nm.domain.text import blank
from nm.domain.traceability import implements
from nm.infrastructure.cleanup import discard
from nm.ports.store import MatterList, StaleWrite


class EncryptionNotConfigured(RuntimeError):
    """Raised loudly, for a missing key AND for a missing cipher.

    It said *never degraded into writing plaintext*, which was true of
    plaintext and not of the keystream XOR this fell back to when
    `cryptography` was absent -- silently, on a deployment that would then
    serve privileged client material under it (BK-16).
    """


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
        from nm.adapters.store.uploads import SealedUploadStore

        if self._sealer is None:
            raise EncryptionNotConfigured("original-byte uploads require the sealed store")
        return SealedUploadStore(self._root, self._sealer)

    # ------------------------------------------------------- the envelope ---

    def _seal(self, matter_id: str, data: bytes) -> bytes:
        if self._sealer is None:
            return self._cipher.encrypt(data)
        return self._sealer.seal(matter_id, data)

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
        return self._matters / f"{matter_id}.nm"

    def load(self, matter_id: MatterId) -> Matter | None:
        p = self._path(matter_id)
        if not p.exists():
            return None
        return _matter(json.loads(
            self._open(str(matter_id), p.read_bytes()).decode("utf8")))

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
                str(matter.id), json.dumps(_enc(matter)).encode("utf8"))
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
        lock = self._matters / f"{matter_id}.lock"
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
        out, unreadable = [], []
        for p in sorted(self._matters.glob("*.nm")):
            try:
                m = _matter(json.loads(
                    self._open(p.stem, p.read_bytes()).decode("utf8")))
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
        return MatterList(tuple(out), tuple(unreadable))

    def record_metrics(self, metrics: dict) -> None:
        """Written even when the turn failed, and never containing client words."""
        path = self._metrics / f"{metrics['turn_id']}.json"
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
        self._transcripts.mkdir(parents=True, exist_ok=True)
        matter = str(transcript.get("matter_id") or "unattributed")
        path = self._transcripts / f"{matter}{_SEP}{transcript['turn_id']}.nm"
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
        if not self._transcripts.exists():
            return ()
        out: list[dict] = []

        # THE FILES THIS MATTER OWNS, by name. An unreadable one among these
        # is genuinely this matter's and is reported as missing FROM THIS
        # RECORD; an unreadable file belonging to another matter is not.
        for p in sorted(self._transcripts.glob(f"{matter_id}{_SEP}*.nm")):
            try:
                document = _transcript_payload(self._open(str(matter_id), p.read_bytes()))
                owned_turn = p.name.split(_SEP, 1)[1][:-3]
                if document["matter_id"] != matter_id or document["turn_id"] != owned_turn:
                    raise ValueError("the transcript identity conflicts with its archive name")
                out.append(document)
            except Exception as exc:  # noqa: BLE001 -- reported, never dropped
                out.append({"turn_id": p.name.split(_SEP, 1)[1][:-3],
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
                continue
            try:
                _transcript_payload(self._cipher.decrypt(p.read_bytes()))
            except Exception:  # noqa: BLE001 -- that IS the finding
                lost.append(p.stem)
        return tuple(lost)
