"""Relative authority weight, served through the port. LB-122.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement `CuratedElements`, `CuratedPreInstitution` and
`CuratedGoverningLaw` already use.

IT HOLDS THE INDEX, not a copy of the rule. The identity index is the same one
the evidence adapter reads, and both reach it through `IdentityIndex`, which
answers NOT-KNOWN for every method when the index is absent. An unbuilt index
therefore ranks nothing rather than ranking wrongly.
"""
from __future__ import annotations

from pathlib import Path

from nm.domain.traceability import implements
from nm.knowledge import authority_weight as curated
from nm.knowledge.identity import IdentityIndex
from nm.ports.authority_weight import Weighing


class CuratedAuthorityWeight:
    """`nm.knowledge.authority_weight`, behind `AuthorityWeightPort`."""

    def __init__(self, index_path: Path | str = "nonexistent") -> None:
        """`IdentityIndex` TAKES A PATH AND HAS NO DEFAULT, deliberately, and
        the string it is given when nothing is configured is the same one the
        evidence adapter uses: an installation with no index is one whose
        index does not exist, said in the one way both readers spell it."""
        self._index = IdentityIndex(index_path)

    @implements("D3")
    def weigh(self, locators: tuple[str, ...]) -> tuple[Weighing, ...]:
        if not self._index.available:
            # AN UNBUILT INDEX RANKS NOTHING. It must not be able to report
            # that two authorities could not be compared either, because that
            # reads as a fact about the judgments rather than about this
            # installation -- the coverage disclosure owns that statement.
            return ()
        return curated.weigh(locators, self._index)
