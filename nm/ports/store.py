"""The store port.

`commit` is deliberately conditional on the version the turn derived from. If
the matter moved underneath, the commit is REFUSED rather than overwriting --
two turns interleaving invalidations on one derivation graph would compute both
answers from a state neither of them saw.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from nm.domain.matter import Matter, MatterId


class StaleWrite(Exception):
    """The matter moved between load and commit. Re-derive, never overwrite."""


@runtime_checkable
class StorePort(Protocol):
    def load(self, matter_id: MatterId) -> Matter | None: ...

    def commit(self, matter: Matter, *, expected_version: int) -> Matter:
        """Persist atomically, or raise. There is no partial application."""
        ...

    def list_for(self, advocate_id: str) -> tuple[Matter, ...]: ...

    def record_metrics(self, metrics: dict) -> None:
        """Written even when the turn failed."""
        ...
