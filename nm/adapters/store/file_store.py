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
from dataclasses import asdict, fields, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from nm.domain.matter import (
    Fact,
    Matter,
    MatterId,
)
from nm.domain.traceability import implements
from nm.ports.store import MatterList, StaleWrite


class EncryptionNotConfigured(RuntimeError):
    """Raised loudly. Never degraded into writing plaintext."""


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
    if isinstance(obj, (list, tuple)):
        return [_enc(v) for v in obj]
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
    if origin in (tuple, list):
        args = get_args(cls)
        item = args[0] if args else None
        seq = [_decode(item, v) if item else v for v in value]
        return tuple(seq) if origin is tuple else seq
    if origin is dict:
        return dict(value)

    if isinstance(cls, type):
        if is_dataclass(cls):
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


@implements("I1")
class FileMatterStore:
    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._matters = self._root / "matters"
        self._metrics = self._root / "metrics"
        self._transcripts = self._root / "transcripts"
        self._matters.mkdir(parents=True, exist_ok=True)
        self._metrics.mkdir(parents=True, exist_ok=True)
        self._cipher = _Cipher(
            key if key is not None else os.environ.get("NM_MATTER_KEY", ""))

    @property
    def scheme(self) -> str:
        return self._cipher.scheme

    def _path(self, matter_id: MatterId) -> Path:
        return self._matters / f"{matter_id}.nm"

    def load(self, matter_id: MatterId) -> Matter | None:
        p = self._path(matter_id)
        if not p.exists():
            return None
        return _matter(json.loads(self._cipher.decrypt(p.read_bytes()).decode("utf8")))

    def commit(self, matter: Matter, *, expected_version: int) -> Matter:
        p = self._path(matter.id)
        if p.exists():
            current = self.load(matter.id)
            if current is not None and current.version > expected_version:
                raise StaleWrite(
                    f"matter {matter.id} moved from version {expected_version} to "
                    f"{current.version} while this turn was deriving. Re-derive "
                    f"against the current state rather than overwriting it."
                )
        blob = self._cipher.encrypt(json.dumps(_enc(matter)).encode("utf8"))
        # Atomic: a crash mid-write leaves the previous file intact.
        fd, tmp = tempfile.mkstemp(dir=str(self._matters), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return matter

    def list_for(self, advocate_id: str) -> MatterList:
        out, unreadable = [], []
        for p in sorted(self._matters.glob("*.nm")):
            try:
                m = _matter(json.loads(self._cipher.decrypt(p.read_bytes()).decode("utf8")))
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
        """
        self._transcripts.mkdir(parents=True, exist_ok=True)
        path = self._transcripts / f"{transcript['turn_id']}.nm"
        blob = self._cipher.encrypt(
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
        for p in sorted(self._transcripts.glob("*.nm")):
            try:
                doc = json.loads(
                    self._cipher.decrypt(p.read_bytes()).decode("utf8"))
            except Exception as exc:  # noqa: BLE001 -- reported, never dropped
                out.append({"turn_id": p.stem, "unreadable": True,
                            "why": f"{type(exc).__name__}: {exc}"})
                continue
            if doc.get("matter_id") == matter_id:
                out.append(doc)
        return tuple(sorted(out, key=lambda d: d.get("at", "")))
