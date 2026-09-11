"""One data key per matter, wrapped by a key nobody in this process holds.

BK-85-AC2, BK-21-AC1, BK-21-AC2.

    from nm.adapters.store.envelope import Envelope, CrossMatterAccess

WHAT `_Cipher` DOES AND WHY IT IS NOT ENOUGH
----------------------------------------------
`_Cipher` seals bytes under one key derived from `NM_MATTER_KEY`, and it
refuses to run without it -- which is right and is the reason a missing key is
a hard failure rather than a silent plaintext write. What it cannot do is
answer three questions this criterion asks:

    WHOSE KEY OPENED THIS?      Every matter on a deployment shares one key, so
                                a process that can read any matter can read all
                                of them. There is no decrypt authority to scope.
    HOW IS IT ROTATED?          Rotating `NM_MATTER_KEY` re-encrypts every
                                matter or locks every advocate out. It did the
                                second on 7 September 2026.
    WHAT SEPARATES THE KEYS?    The credential store, the provider secret and
                                the matter seal were the same key once, which
                                is what BK-21 exists to have undone.

ENVELOPE ENCRYPTION ANSWERS ALL THREE WITH ONE INDIRECTION. Each matter gets
its own random data key. The data key is never stored: what is stored is the
data key WRAPPED under a key-encrypting key, and only the KEK holder can
unwrap it. Rotation re-wraps a few hundred small wrapped keys and touches no
ciphertext. Scope is the wrap itself -- a wrapped key for one matter does not
open another, and that is enforced cryptographically rather than by a check
somebody can forget.

THE BINDING IS THE WHOLE CONTROL
----------------------------------
A wrapped key that is merely *labelled* with its matter id can be relabelled.
The matter id is bound into the wrap as associated data, so presenting matter
A's wrapped key while claiming to be matter B does not produce a wrong answer
-- it fails to unwrap at all. `CrossMatterAccess` is raised on that failure and
never on a corrupt blob, because the two need different responses: one is an
attack or a bug, the other is a disk.

NO PLAINTEXT FALLBACK, AT ANY STEP
------------------------------------
If the KEK is unavailable the read fails. It does not return the ciphertext, it
does not return an empty matter, and it does not write anything. `docs/BASELINE
.md` records what a silent fallback with different behaviour costs: it is the
three-stores defect wearing a helpful face, and here it would be the same defect
holding privileged client material.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from nm.domain.text import refuses_blank_text


class KeyUnavailable(RuntimeError):
    """The key-encrypting key cannot be reached. NEVER a plaintext path."""


class CrossMatterAccess(RuntimeError):
    """A wrapped key was presented for a matter it does not belong to.

    DISTINCT FROM CORRUPTION on purpose. A blob that will not decrypt is a
    disk; a blob that will not decrypt *because it belongs to another matter*
    is an attack or a routing bug, and an operator who cannot tell them apart
    will treat the second as the first and restore from backup.
    """


class WrappedKeyUnreadable(RuntimeError):
    """The wrapped key is corrupt or truncated. Not a cross-matter attempt."""


#: The key-encrypting key's identity travels with every wrap, so a wrapped key
#: says which KEK opens it. Rotation writes a new generation beside the old and
#: re-wraps; nothing has to guess which era a stored key belongs to.
@refuses_blank_text()
@dataclass(frozen=True)
class KeyRef:
    kek_id: str
    generation: int

    def as_dict(self) -> dict:
        return {"kek_id": self.kek_id, "generation": self.generation}


@refuses_blank_text()
@dataclass(frozen=True)
class WrappedKey:
    """What is stored. The data key itself never is."""

    matter_id: str
    key_ref: KeyRef
    ciphertext: str
    wrapped_at: str

    def as_dict(self) -> dict:
        return {"matter_id": self.matter_id, "key_ref": self.key_ref.as_dict(),
                "ciphertext": self.ciphertext, "wrapped_at": self.wrapped_at}

    @classmethod
    def from_dict(cls, blob: dict) -> WrappedKey:
        try:
            ref = blob["key_ref"]
            return cls(matter_id=blob["matter_id"],
                       key_ref=KeyRef(ref["kek_id"], int(ref["generation"])),
                       ciphertext=blob["ciphertext"],
                       wrapped_at=blob["wrapped_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WrappedKeyUnreadable(f"wrapped key is unreadable: {exc}") from exc


class LocalKeyRing:
    """A KEK holder for controlled local operation. NOT a KMS.

    IT SAYS SO IN ITS NAME AND IN `scheme`, because the criterion asks for
    KMS-backed envelope encryption and this is not that. What it IS is the same
    key SHAPE -- separate KEK, per-matter DEK, bound wrap, audited rotation --
    so the KMS adapter replaces one class and no caller changes. A local
    stand-in that had a different shape would make the real thing a rewrite,
    and a rewrite scheduled after a deadline is a rewrite that does not happen.
    """

    scheme = "local-hkdf(NOT-KMS)"

    def __init__(self, secret: str | None = None, *, kek_id: str = "local",
                 generation: int = 1, accepts: tuple[int, ...] = ()) -> None:
        """`accepts` is the rotation window, and it is EXPLICIT.

        The first version derived the unwrapping key from the generation
        recorded IN THE WRAPPED KEY, so any ring with the same `kek_id` opened
        every generation and rotation was cosmetic for access control. An
        operator rotating because a generation had leaked would still have been
        exposed -- caught by a probe of my own code, not by reading it.

        A prior generation is readable only while somebody says so, and that is
        what makes retiring one mean anything.
        """
        raw = secret if secret is not None else os.environ.get("NM_KEK", "")
        if not (raw or "").strip():
            # FAIL CLOSED. The whole point of BK-21-AC1 is that an
            # unconfigured key is a refusal and never a quiet plaintext path.
            raise KeyUnavailable(
                "NM_KEK is not set. Matter data keys are wrapped with it, and "
                "an unconfigured key-encrypting key is a HARD FAILURE -- there "
                "is deliberately no plaintext fallback.")
        self._raw = raw.encode("utf8")
        self.ref = KeyRef(kek_id, generation)
        self.accepts = tuple(sorted({generation, *accepts}))

    def _derive(self, matter_id: str, generation: int) -> bytes:
        """The wrapping key for ONE matter under ONE generation.

        The matter id is an input, not a label. That is what makes a wrapped
        key for matter A useless against matter B -- there is no check to
        forget, because the wrong key simply does not open it.
        """
        return hmac.new(
            self._raw,
            f"nm-kek:{self.ref.kek_id}:{generation}:{matter_id}".encode(),
            hashlib.sha256).digest()

    def wrap(self, matter_id: str, data_key: bytes,
             now: datetime | None = None) -> WrappedKey:
        if not (matter_id or "").strip():
            raise CrossMatterAccess("a data key cannot be wrapped for no matter")
        stream = self._derive(matter_id, self.ref.generation)
        sealed = bytes(a ^ b for a, b in zip(data_key, stream, strict=True))
        tag = hmac.new(stream, sealed, hashlib.sha256).digest()[:16]
        return WrappedKey(
            matter_id=matter_id, key_ref=self.ref,
            ciphertext=base64.b64encode(sealed + tag).decode("ascii"),
            wrapped_at=(now or datetime.now(timezone.utc)).isoformat(
                timespec="seconds"))

    def unwrap(self, matter_id: str, wrapped: WrappedKey) -> bytes:
        """The data key, or a refusal that says WHICH KIND of refusal it is."""
        if wrapped.key_ref.kek_id != self.ref.kek_id:
            raise KeyUnavailable(
                f"this key ring holds {self.ref.kek_id!r} and the key was "
                f"wrapped under {wrapped.key_ref.kek_id!r}")
        if wrapped.key_ref.generation not in self.accepts:
            # A RETIRED GENERATION IS RETIRED. Deriving from whatever
            # generation the ciphertext claims would let a rotated-away key
            # open everything it ever wrapped, which is the opposite of what
            # a rotation is for.
            raise KeyUnavailable(
                f"generation {wrapped.key_ref.generation} is not in this "
                f"ring's accepted window {list(self.accepts)}")
        try:
            blob = base64.b64decode(wrapped.ciphertext, validate=True)
        except Exception as exc:  # noqa: BLE001 -- a corrupt blob is a disk
            raise WrappedKeyUnreadable("wrapped key is not decodable") from exc
        if len(blob) < 17:
            raise WrappedKeyUnreadable("wrapped key is truncated")
        sealed, tag = blob[:-16], blob[-16:]
        stream = self._derive(matter_id, wrapped.key_ref.generation)
        if not hmac.compare_digest(
                tag, hmac.new(stream, sealed, hashlib.sha256).digest()[:16]):
            # THE ID IS AN INPUT TO THE DERIVATION, so a mismatch here is
            # either the wrong matter or a tampered blob -- and the wrapped
            # key states which matter it was made for, so we can say.
            if wrapped.matter_id != matter_id:
                raise CrossMatterAccess(
                    f"this key was wrapped for {wrapped.matter_id!r} and was "
                    f"presented for {matter_id!r}")
            raise WrappedKeyUnreadable("wrapped key does not authenticate")
        if wrapped.matter_id != matter_id:
            # Belt and braces: unreachable while the id is bound into the
            # derivation, and it stays here because a future KEK that binds
            # the id differently would otherwise silently lose this property.
            raise CrossMatterAccess(
                f"this key was wrapped for {wrapped.matter_id!r}")
        return bytes(a ^ b for a, b in zip(sealed, stream, strict=True))

    def rotated(self) -> LocalKeyRing:
        """The next generation. Re-wrapping is the caller's, and audited."""
        ring = LocalKeyRing.__new__(LocalKeyRing)
        ring._raw = self._raw
        ring.ref = KeyRef(self.ref.kek_id, self.ref.generation + 1)
        # THE NEW RING DOES NOT READ THE OLD GENERATION. `rewrap_all` takes
        # both rings precisely so the old one is used to unwrap and the new one
        # only to wrap -- the rotation window is the caller holding two
        # objects, not a ring that quietly accepts its own past.
        ring.accepts = (ring.ref.generation,)
        return ring


@refuses_blank_text()
@dataclass(frozen=True)
class RotationRecord:
    """What a rotation did, for the audit. NEVER a key, wrapped or otherwise."""

    kek_id: str
    from_generation: int
    to_generation: int
    matters: int
    at: str

    def as_line(self) -> str:
        return (f"rekey kek={self.kek_id} {self.from_generation}->"
                f"{self.to_generation} matters={self.matters} at={self.at}")


def new_data_key() -> bytes:
    return secrets.token_bytes(32)


def rewrap_all(old: LocalKeyRing, new: LocalKeyRing,
               wrapped: dict[str, WrappedKey],
               now: datetime | None = None) -> tuple[dict[str, WrappedKey],
                                                     RotationRecord]:
    """Re-wrap every data key under the new generation. Touches no ciphertext.

    ALL OR NOTHING. A rotation that re-wrapped half the matters would leave the
    other half openable only by a KEK generation the operator is about to
    retire, and the failure surfaces later as an unreadable matter rather than
    now as a failed rotation.
    """
    out: dict[str, WrappedKey] = {}
    for matter_id, key in wrapped.items():
        out[matter_id] = new.wrap(matter_id, old.unwrap(matter_id, key), now)
    return out, RotationRecord(
        kek_id=new.ref.kek_id, from_generation=old.ref.generation,
        to_generation=new.ref.generation, matters=len(out),
        at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"))


def envelope_blob(wrapped: WrappedKey, ciphertext: bytes) -> bytes:
    """What lands on disk: the wrapped key beside the sealed record."""
    return json.dumps({
        "envelope": 1,
        "wrapped_key": wrapped.as_dict(),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }, indent=2).encode("utf8")


def read_envelope(blob: bytes) -> tuple[WrappedKey, bytes]:
    try:
        doc = json.loads(blob.decode("utf8"))
        if doc.get("envelope") != 1:
            raise WrappedKeyUnreadable("not an envelope record")
        return (WrappedKey.from_dict(doc["wrapped_key"]),
                base64.b64decode(doc["ciphertext"], validate=True))
    except WrappedKeyUnreadable:
        raise
    except Exception as exc:  # noqa: BLE001 -- unreadable is not empty
        raise WrappedKeyUnreadable(f"envelope record is unreadable: {exc}") from exc
