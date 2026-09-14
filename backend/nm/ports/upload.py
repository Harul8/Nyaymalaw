"""Immutable original-byte objects. Receipt metadata belongs to StorePort.

Only the composition root chooses the storage destination; every call is
policed. An object is not admitted media, a parsed document or a legal fact.
"""
from __future__ import annotations

from typing import Protocol


class UploadPort(Protocol):
    def put(self, matter_id: str, object_id: str, data: bytes) -> None:
        """Durably seal a new immutable object, or raise before publication."""
        ...

    def read(self, matter_id: str, object_id: str) -> bytes:
        """Open one bounded object in the named matter's key scope, or raise."""
        ...
