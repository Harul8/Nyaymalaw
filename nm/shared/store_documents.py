"""Immutable document derivatives sealed under the existing per-matter custody.

No filenames or model-selected paths. Receipt metadata lives in StorePort, not
here. Restored ciphertext can only be used after the service checks current
admission/permission/tombstones against the owning matter.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from cryptography.exceptions import InvalidTag

from nm.open_matter.matter_documents_port import MAX_DERIVATIVE_BYTES
from nm.shared.names_contracts import discard
from nm.shared.storage_errors_port import StoredObjectUnreadable
from nm.shared.store_sealing import MatterSealer
from nm.shared.store_uploads import _resolved_is_within


class SealedDocumentStore:
    def __init__(self, root: Path, sealer: MatterSealer):
        self._root = (root / "document-text").resolve()
        self._sealer = sealer

    def _path(self, matter_id, object_id):
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value)
            for value in (matter_id, object_id)
        ):
            raise ValueError("invalid opaque matter-document identifier")
        path = (self._root / matter_id / (object_id + ".nm")).resolve()
        if not _resolved_is_within(path, self._root):
            raise ValueError("the derivative is outside its configured storage root")
        return path

    @staticmethod
    def _digest(sha256):
        if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ValueError("the derivative requires an exact SHA-256 identity")

    def put(self, matter_id, object_id, data):
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_DERIVATIVE_BYTES:
            raise ValueError("the derivative is empty or exceeds its byte bound")
        path = self._path(matter_id, object_id)
        sealed = self._sealer.seal(matter_id, data, create_key=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A failed write is unpublished; it may leave a sealed orphan but may
        # never overwrite another accepted object's identity.
        try:
            with path.open("xb") as handle:
                handle.write(sealed)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if self.read(matter_id, object_id, hashlib.sha256(data).hexdigest()) != data:
                raise ValueError("an immutable derivative already holds different bytes") from None

    def read(self, matter_id, object_id, sha256):
        self._digest(sha256)
        path = self._path(matter_id, object_id)
        with path.open("rb") as handle:
            sealed = handle.read(MAX_DERIVATIVE_BYTES * 2 + 1)
        if len(sealed) > MAX_DERIVATIVE_BYTES * 2:
            raise ValueError("the sealed derivative exceeds its byte bound")
        try:
            data = self._sealer.open(matter_id, sealed)
        except InvalidTag as exc:
            raise StoredObjectUnreadable("the sealed derivative failed authentication") from exc
        if not 0 < len(data) <= MAX_DERIVATIVE_BYTES:
            raise ValueError("the opened derivative exceeds its byte bound")
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("the derivative does not match its published identity")
        return data

    def forget(self, matter_id, object_id, sha256):
        path = self._path(matter_id, object_id)
        self._digest(sha256)
        try:
            self.read(matter_id, object_id, sha256)
        except FileNotFoundError:
            return True
        return discard(path)
