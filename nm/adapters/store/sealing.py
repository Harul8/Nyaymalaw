"""Sealing a matter's bytes, wherever they are about to be put. P07, P10.

    sealer = MatterSealer(seal="...", keys=Path(".nm/keys"))
    blob = sealer.seal(matter_id, data)
    data = sealer.open(matter_id, blob)

WHY THIS IS NOT INSIDE THE FILE STORE
---------------------------------------
Because a second store arrived. `nm/adapters/store/postgres.py` holds the same
privileged bytes and must seal them the same way, and the moment two adapters
each contain "get this matter's data key and encrypt with it" there are two
owners of one decision -- the shape CLAUDE.md section 4 records, and the one
that produced a grounding gate and an evidence adapter with different ideas
about the same provision reference.

So the decision lives here once. An adapter chooses WHERE the bytes go; it
does not get an opinion about how they are sealed.

WHAT A SEALER DOES NOT DO
---------------------------
It does not decide whether a caller may read the matter. Scope is enforced by
the wrap -- a data key for one matter does not open another -- and authority
is a question for the store's own tenant filter. Both are needed and neither
substitutes for the other.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet

from nm.adapters.store.envelope import (
    CrossMatterAccess,
    KeyUnavailable,
    LocalKeyRing,
    WrappedKey,
    WrappedKeyUnreadable,
    new_data_key,
)

#: How long a loser waits for the winner to finish writing a data-key record.
#: One small write, so this is generous rather than tight.
KEY_RECORD_TIMEOUT = 5.0
_POLL = 0.02


def is_envelope(blob: bytes) -> bool:
    """Whether these bytes CLAIM to be a sealed record.

    Cheap and structural. A Fernet token is base64 beginning `gAAAAA`; a
    sealed record is JSON whose first key says what it is. Deciding by format
    means a CORRUPT record is opened as what it claims to be and fails as
    that, rather than being handed to another reader and reported as a record
    of a kind it never was.
    """
    return blob[:64].lstrip().startswith(b"{") and b'"envelope"' in blob[:64]


class MatterSealer:
    """One data key per matter, wrapped under the installation seal."""

    def __init__(self, seal: str, keys: Path, *, kek_id: str = "matter-store"):
        self._keys = Path(keys)
        self._ring = LocalKeyRing(seal, kek_id=kek_id)

    @property
    def scheme(self) -> str:
        return f"envelope({self._ring.scheme})"

    # ----------------------------------------------------------- the key ----

    def matter_key(self, matter_id: str) -> tuple[WrappedKey, bytes]:
        """This matter's data key, created once and wrapped on disk.

        NO `exists()` FIRST. A check and then a create is two steps with an
        interval between them, and the interval is the defect: the loser saw
        the file the winner had created and not yet written, read nothing, and
        failed on empty JSON. The exclusive create IS the question, so it is
        the only thing asked.
        """
        self._keys.mkdir(parents=True, exist_ok=True)
        path = self._keys / f"{matter_id}.key"
        fresh = new_data_key()
        try:
            wrapped = self._ring.wrap(matter_id, fresh)
            with path.open("xb") as handle:
                handle.write(json.dumps(wrapped.as_dict()).encode("utf8"))
                handle.flush()
                os.fsync(handle.fileno())
            return wrapped, fresh
        except FileExistsError:
            pass                          # somebody else won; read theirs
        return self._read_key(matter_id, path)

    def _read_key(self, matter_id: str, path: Path) -> tuple[WrappedKey, bytes]:
        """The winner's key record, waiting for it to be COMPLETE.

        A BOUNDED WAIT, NOT A SPIN WITHOUT AN END. The winner creates the file
        and then writes it, so a loser arriving between those two moments sees
        a real path holding nothing -- and "nothing" must not read as a
        corrupt key record, because the response to those two is different:
        one is a millisecond, the other is a restore.

        It expires into an explicit failure rather than into a fresh key.
        Minting a second key here is the one outcome that must never happen:
        it would replace the winner's and every record already written under
        it would stop opening.
        """
        deadline = time.monotonic() + KEY_RECORD_TIMEOUT
        while True:
            body = path.read_bytes() if path.exists() else b""
            if body.strip():
                wrapped = WrappedKey.from_dict(json.loads(body))
                return wrapped, self._ring.unwrap(matter_id, wrapped)
            if time.monotonic() >= deadline:
                raise WrappedKeyUnreadable(
                    f"the data-key record for {matter_id} is empty after "
                    f"{KEY_RECORD_TIMEOUT}s. Another writer created it and "
                    f"did not finish; the matter is not readable until that "
                    f"record is restored, and minting a new key here would "
                    f"make every record already written under the old one "
                    f"permanently unreadable.")
            time.sleep(_POLL)

    @staticmethod
    def _cipher(data_key: bytes) -> Fernet:
        """AT MODULE SCOPE, NOT IN HERE. `matter_key` is called from worker
        threads, and an import executed under concurrency can observe a
        half-initialised module -- which surfaces far away as a dataclass
        refusing to be built, not as an import error."""
        return Fernet(base64.urlsafe_b64encode(data_key))

    # --------------------------------------------------------- the bytes ----

    def seal(self, matter_id: str, data: bytes) -> bytes:
        """Seal under THIS matter's key. THE KEY IS NOT IN HERE.

        An earlier draft embedded the wrapped key in every record as well as
        in the key record, which made rotation two populations instead of one
        -- and the one nobody updated would have been unreadable for good. The
        record says what FORMAT it is and which MATTER it belongs to, and that
        is all it needs to say: both are things a reader must know before it
        can ask for a key, and neither is a key.
        """
        _, data_key = self.matter_key(matter_id)
        return json.dumps({
            "envelope": 1,
            "matter_id": matter_id,
            "ciphertext": base64.b64encode(
                self._cipher(data_key).encrypt(data)).decode("ascii"),
        }, indent=2).encode("utf8")

    def open(self, matter_id: str, blob: bytes) -> bytes:
        """Open a sealed record, or say precisely why it will not open."""
        try:
            doc = json.loads(blob.decode("utf8"))
            belongs_to = str(doc["matter_id"])
            ciphertext = base64.b64decode(doc["ciphertext"], validate=True)
        except Exception as exc:  # noqa: BLE001 -- unreadable is not empty
            raise WrappedKeyUnreadable(
                f"sealed record is unreadable: {exc}") from exc
        if belongs_to != str(matter_id):
            # THE RECORD NAMES ITS OWN MATTER, so a record moved under another
            # matter's name is caught here rather than producing a confusing
            # decryption failure two steps later.
            raise CrossMatterAccess(
                f"this record was sealed for {belongs_to!r} and was read as "
                f"{matter_id!r}")
        path = self._keys / f"{matter_id}.key"
        if not path.exists():
            # NOT AN EMPTY MATTER. A sealed record whose key is gone is
            # unreadable, and saying so is the whole difference between a
            # restore and a shrug.
            raise KeyUnavailable(
                f"the data key for {matter_id} is missing, so this record "
                f"cannot be opened. There is deliberately no plaintext path.")
        _, data_key = self._read_key(str(matter_id), path)
        return self._cipher(data_key).decrypt(ciphertext)
