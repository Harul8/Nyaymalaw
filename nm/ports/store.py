"""The store port.

`commit` is deliberately conditional on the version the turn derived from. If
the matter moved underneath, the commit is REFUSED rather than overwriting --
two turns interleaving invalidations on one derivation graph would compute both
answers from a state neither of them saw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nm.domain.matter import Matter, MatterId


class StaleWrite(Exception):
    """The matter moved between load and commit. Re-derive, never overwrite."""


@dataclass(frozen=True)
class MatterList:
    """A list read, and an honest account of what it could not read.

    THREE STATES FOR A COLLECTION, the same discipline every other result
    in this product carries: complete, incomplete AND SAID SO, or
    unbuildable. The middle one is what a bare tuple cannot express.
    """

    matters: tuple[Matter, ...] = ()
    unreadable: tuple[str, ...] = ()
    """Ids that are on disk and could not be decoded. Named, not counted,
    so the advocate can say which file to look at."""

    @property
    def complete(self) -> bool:
        return not self.unreadable

    def __iter__(self):
        """Iterating yields the matters, so existing call sites read the
        same -- but they can no longer do so WITHOUT the failure being
        available, which is the point."""
        return iter(self.matters)

    def __len__(self) -> int:
        return len(self.matters)


@runtime_checkable
class StorePort(Protocol):
    def load(self, matter_id: MatterId) -> Matter | None: ...

    def commit(self, matter: Matter, *, expected_version: int) -> Matter:
        """Persist atomically, or raise. There is no partial application."""
        ...

    def list_for(self, advocate_id: str) -> "MatterList":
        """The advocate's matters, AND what could not be read.

        Not a bare tuple. A bare tuple cannot distinguish six matters from
        seven with one corrupt, so an unreadable file vanished from the
        list and the advocate was told they had six -- the seventh, with
        its deadlines, simply absent.

        `unbuildable()` already covered the board that could not be built
        at all. This is the more dangerous case, because it looks complete.
        """
        ...

    def record_metrics(self, metrics: dict) -> None:
        """Written even when the turn failed."""
        ...
