"""Ranked discovery of held provision wording, never Act selection or legal support.

An exact ``read_provision(act, section, as_of)`` remains necessary before a
candidate can support a proposition. Search has no governing date and cannot
decide which Act applies, even when an ``act`` filter narrows its scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, Origin


@dataclass(frozen=True)
class ProvisionCandidate:
    act: str
    section: str
    locator: str
    rank: int
    matched_terms: tuple[str, ...]
    origin: Origin = Origin.SEARCHED

    def __post_init__(self) -> None:
        if (not self.act.strip() or not self.section.strip()
                or not self.locator.strip() or self.rank < 1):
            raise ValueError("a ranked provision needs an Act, section, locator and rank")
        if not self.matched_terms or self.origin is not Origin.SEARCHED:
            raise ValueError("provision discovery may return only matched, searched candidates")


@dataclass(frozen=True)
class ProvisionSearchResult:
    query: str
    requested_act: str | None
    index: str
    coverage: Coverage
    searched_stores: tuple[str, ...] = ()
    sections_scanned: int = 0
    excluded_atoms: int = 0
    candidates: tuple[ProvisionCandidate, ...] = ()
    snapshot_id: str | None = None
    why: str = ""

    def __post_init__(self) -> None:
        if not self.index.strip() or self.sections_scanned < 0 or self.excluded_atoms < 0:
            raise ValueError("provision search must name its index and actual scan counts")
        if bool(self.candidates) != (self.coverage is Coverage.ANSWERED):
            raise ValueError("only an answered provision search may carry candidates")
        if any(row.rank != position for position, row in enumerate(self.candidates, 1)):
            raise ValueError("provision search ranks must be contiguous and ordered")
        if self.coverage is not Coverage.ANSWERED and not self.why:
            raise ValueError("an empty or unavailable search needs an explicit explanation")


@runtime_checkable
class ProvisionSearchPort(Protocol):
    def search_provisions(
        self, query: str, act: str | None = None, limit: int = 20
    ) -> ProvisionSearchResult: ...
