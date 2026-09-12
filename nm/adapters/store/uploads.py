"""Sealed immutable upload chunks, with no second receipt/locking authority.

Unique objects are fully written before the existing matter CAS names them.
A failed CAS can leave an unreferenced sealed object; it cannot expose a
partial receipt or plaintext. This slice does not claim garbage collection.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePath, PureWindowsPath

from nm.adapters.store.sealing import MatterSealer
from nm.domain.intake import MAX_CHUNK_BYTES


def _containment_identity(path: PurePath) -> PurePath:
    """Compare resolved Windows paths without discarding namespace semantics.

    During directory creation Python's non-strict realpath can retain the
    extended prefix on only one result (missing parent becomes missing leaf).
    Promote the ordinary spelling instead of stripping a prefix: stripping
    could change the meaning of a genuine extended trailing-dot/space name.
    This function does not resolve links; callers must resolve the filesystem
    path first so a junction/symlink escape remains an actual outside path.
    """
    if not isinstance(path, PureWindowsPath) or str(path).startswith("\\\\?\\"):
        return path
    if str(path).startswith("\\\\.\\"):
        raise ValueError("device namespace is not an upload storage path")
    if path.drive.startswith("\\\\"):
        return PureWindowsPath("\\\\?\\UNC\\" + str(path)[2:])
    return PureWindowsPath("\\\\?\\" + str(path))


def _resolved_is_within(path: PurePath, root: PurePath) -> bool:
    """Containment for already-resolved absolute paths in the same flavour."""
    if not path.is_absolute() or not root.is_absolute():
        return False
    if isinstance(path, PureWindowsPath) != isinstance(root, PureWindowsPath):
        return False
    return _containment_identity(path).is_relative_to(_containment_identity(root))


class SealedUploadStore:
    def __init__(self, root: Path, sealer: MatterSealer) -> None:
        self._root = (root / "uploads").resolve()
        self._sealer = sealer

    def _path(self, matter_id: str, object_id: str) -> Path:
        for value in (matter_id, object_id):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                raise ValueError("invalid opaque upload identifier")
        path = (self._root / matter_id / (object_id + ".nm")).resolve()
        if not _resolved_is_within(path, self._root):
            raise ValueError("upload object is outside its storage root")
        return path

    def put(self, matter_id: str, object_id: str, data: bytes) -> None:
        if not 0 < len(data) <= MAX_CHUNK_BYTES:
            raise ValueError("upload chunk exceeds the observed-byte bound")
        path = self._path(matter_id, object_id)
        sealed = self._sealer.seal(matter_id, data)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never replace an object another receipt could already reference.
        with path.open("xb") as handle:
            handle.write(sealed)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self, matter_id: str, object_id: str) -> bytes:
        path = self._path(matter_id, object_id)
        # Bound the encrypted read as well as the plaintext, including damage.
        with path.open("rb") as handle:
            sealed = handle.read(MAX_CHUNK_BYTES * 2 + 1)
        if len(sealed) > MAX_CHUNK_BYTES * 2:
            raise ValueError("sealed upload object exceeds its bound")
        data = self._sealer.open(matter_id, sealed)
        if not 0 < len(data) <= MAX_CHUNK_BYTES:
            raise ValueError("opened upload chunk exceeds its bound")
        return data
