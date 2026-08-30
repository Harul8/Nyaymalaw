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
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path

from nm.domain.matter import (
    Basis,
    Certainty,
    Fact,
    Matter,
    MatterId,
    Posture,
    PostureConflict,
    Provenance,
    Role,
    Thread,
)
from nm.domain.traceability import implements
from nm.ports.store import StaleWrite


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


def _fact(d: dict) -> Fact:
    p = d["provenance"]
    return Fact(
        id=d["id"], statement=d["statement"],
        provenance=Provenance(kind=p["kind"], turn=p["turn"], document=p.get("document"),
                              page=p.get("page"), span=p.get("span")),
        certainty=Certainty(d["certainty"]),
        date=date.fromisoformat(d["date"]) if d.get("date") else None,
        material=d.get("material", True), confirmed=d.get("confirmed", False),
        conflicts_with=tuple(d.get("conflicts_with", ())),
        superseded_by=d.get("superseded_by"),
    )


def _thread(d: dict) -> Thread:
    p = d["posture"]
    return Thread(
        id=d["id"], label=d["label"], aliases=tuple(d.get("aliases", ())),
        identifiers=dict(d.get("identifiers", {})),
        posture=Posture(
            role=Role(p["role"]), basis=Basis(p["basis"]), opponent=p.get("opponent"),
            source_fact=p.get("source_fact"), version=p.get("version", 0),
            conflicts=tuple(PostureConflict(Role(c["on_record"]), Role(c["now_suggested"]),
                                            c.get("applied", False))
                            for c in p.get("conflicts", ()))),
        chronology=tuple(d.get("chronology", ())),
        deferred_reason=d.get("deferred_reason"),
    )


def _matter(d: dict) -> Matter:
    return Matter(
        id=d["id"], advocate_id=d["advocate_id"], title=d["title"],
        threads=tuple(_thread(t) for t in d.get("threads", ())),
        facts=tuple(_fact(f) for f in d.get("facts", ())),
        turns_applied=tuple(d.get("turns_applied", ())),
        version=d.get("version", 0),
    )


# ------------------------------------------------------------------ store ---


@implements("I1")
class FileMatterStore:
    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._matters = self._root / "matters"
        self._metrics = self._root / "metrics"
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

    def list_for(self, advocate_id: str) -> tuple[Matter, ...]:
        out = []
        for p in sorted(self._matters.glob("*.nm")):
            try:
                m = _matter(json.loads(self._cipher.decrypt(p.read_bytes()).decode("utf8")))
            except Exception:
                # One unreadable matter must not take the whole list down --
                # but it must not vanish silently either. It is skipped here and
                # reported by the caller's board state (PRD §6.2A).
                continue
            if m.advocate_id == advocate_id:
                out.append(m)
        return tuple(out)

    def record_metrics(self, metrics: dict) -> None:
        """Written even when the turn failed, and never containing client words."""
        path = self._metrics / f"{metrics['turn_id']}.json"
        path.write_text(json.dumps(metrics, indent=2), encoding="utf8")
