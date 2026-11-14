"""Sealing a matter's bytes, wherever they are about to be put. P07, P10.

    sealer = MatterSealer(seal="...", keys=Path(".nm/keys"))
    blob = sealer.seal(matter_id, data)
    data = sealer.open(matter_id, blob)

WHY THIS IS NOT INSIDE THE FILE STORE
---------------------------------------
Because a second store arrived. `nm/shared/store_postgres.py` holds the same
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

from nm.shared.names_contracts import discard
from nm.shared.storage_errors_port import StoredObjectUnreadable
from nm.shared.store_envelope import (
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

#: The format a sealed record says it is: written by `seal`, checked by `open`
#: (plan AN.50, 50g, D193). Every sealed record has carried it since there were
#: any, so a record without it was not written by `seal`.
SEALED_FORMAT = 1


class SealedFormatUnknown(StoredObjectUnreadable):
    """The sealed record says it is of a format this code does not read: code
    newer than this one wrote it. It is refused, never opened as if it were the
    format this code knows (plan AN.50, 50g; the review's F-34)."""


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

        THE RECORD IS WHOLE BEFORE IT HAS ITS NAME (plan AN.50, 50h, D194). It
        was created under its name and then written, so a process that ended
        between the two left an empty record: every later use of that matter's
        identifier waited and was refused, and no new key may be made over a
        record that exists. It is now written and flushed beside its name and
        given the name in one step that fails where the name is taken - still
        the one question asked - so the name is never there half-written.
        """
        self._keys.mkdir(parents=True, exist_ok=True)
        path = self._keys / f"{matter_id}.key"
        fresh = new_data_key()
        wrapped = self._ring.wrap(matter_id, fresh)
        record = json.dumps(wrapped.as_dict()).encode("utf8")
        beside = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.new")
        try:
            with beside.open("xb") as handle:
                handle.write(record)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(beside, path)     # fails where the name is taken
            except FileExistsError:
                return self._read_key(matter_id, path)   # somebody else won; read theirs
            except OSError:
                # A folder that gives no second name to a file (some shared
                # and removable drives): the record is made under its name as
                # it was before this piece, where the same question is asked.
                try:
                    with path.open("xb") as handle:
                        handle.write(record)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError:
                    return self._read_key(matter_id, path)
            return wrapped, fresh
        finally:
            discard(beside)

    def destroy(self, matter_id: str) -> bool:
        """DESTROY THIS MATTER'S KEY (plan AN.53, D241): the first step of erasing a conversation, so that every record sealed under
        it - wherever a copy of one is left, a backup included - can never be opened again (open() says the key is missing; nothing
        makes a new one in its place). True where there was a key, False where there was none. A key that cannot be removed raises,
        and the caller then removes nothing else (FileMatterStore.erase)."""
        for stray in self._keys.glob(f"{matter_id}.key.*.new"):  # a key record a process was writing when it ended
            if not discard(stray):
                raise OSError(f"a key record of matter {matter_id} could not be removed: nothing of it is erased")
        key = self._keys / f"{matter_id}.key"
        if not key.exists():
            return False
        if not discard(key):
            raise OSError(f"the key of matter {matter_id} could not be destroyed: nothing of it is erased")
        if os.name != "nt":  # the removal is the folder's, flushed as a save's rename is (store_file_store.publish)
            folder = os.open(str(self._keys), os.O_RDONLY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
        return True

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
                    f"permanently unreadable. Where nothing of this matter "
                    f"was ever saved - a start that ended as it made the "
                    f"record, before records were written whole - the empty "
                    f"file may be deleted by the operator, and is never "
                    f"deleted here.")
            time.sleep(_POLL)

    @staticmethod
    def _cipher(data_key: bytes) -> Fernet:
        """AT MODULE SCOPE, NOT IN HERE. `matter_key` is called from worker
        threads, and an import executed under concurrency can observe a
        half-initialised module -- which surfaces far away as a dataclass
        refusing to be built, not as an import error."""
        return Fernet(base64.urlsafe_b64encode(data_key))

    # --------------------------------------------------------- the bytes ----

    def seal(self, matter_id: str, data: bytes, *, create_key: bool = True) -> bytes:
        """Seal under THIS matter's key. THE KEY IS NOT IN HERE.

        An earlier draft embedded the wrapped key in every record as well as
        in the key record, which made rotation two populations instead of one
        -- and the one nobody updated would have been unreadable for good. The
        record says what FORMAT it is and which MATTER it belongs to, and that
        is all it needs to say: both are things a reader must know before it
        can ask for a key, and neither is a key.
        """
        if create_key:
            _, data_key = self.matter_key(matter_id)
        else:
            path = self._keys / f"{matter_id}.key"
            if not path.is_file():
                raise KeyUnavailable("The matter key is unavailable; no new key was created.")
            _, data_key = self._read_key(matter_id, path)
        return json.dumps({
            "envelope": SEALED_FORMAT,
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
        said = doc.get("envelope") if isinstance(doc, dict) else None
        if type(said) is not int or said != SEALED_FORMAT:
            # THE NUMBER WAS WRITTEN AND NEVER READ (F-34). A record of another
            # format opened as this one is read by rules it was not written to.
            raise SealedFormatUnknown(
                f"this sealed record says it is format {said!r} and this code reads "
                f"format {SEALED_FORMAT}: it was not written by this version of NM and "
                "is not opened as if it had been")
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
