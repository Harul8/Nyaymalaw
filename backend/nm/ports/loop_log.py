"""Append-before-use audit storage. Sensitive receipts belong in the sealed file."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from nm.domain.file_mutation import FileMutation

from nm.domain.loop import LoopEvent, LoopIdentity, LoopRecord


class LoopLogPort(Protocol):
    def read(self, identity: LoopIdentity) -> LoopRecord | None: ...

    def append(self, identity: LoopIdentity, event: LoopEvent) -> LoopRecord:
        """Atomically append exactly the next event, or refuse; never overwrite."""
        ...

    def append_mutation(self, identity: LoopIdentity, event: LoopEvent,
                        mutation: FileMutation) -> LoopRecord:
        """Commit checked file changes and their exact journal receipt atomically."""
        ...
