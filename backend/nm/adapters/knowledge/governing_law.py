"""The curated successions, served through the port. LB-120.

`nm.core` may not import `nm.knowledge`, so something in the adapter layer has
to join them -- the same arrangement `CuratedElements` and
`CuratedPreInstitution` already use.
"""
from __future__ import annotations

from datetime import date

from nm.domain.traceability import implements
from nm.knowledge import governing_law as curated
from nm.ports.governing_law import Governing, Limb, Pending, Succession


class CuratedGoverningLaw:
    """`nm.knowledge.governing_law`, behind `GoverningLawPort`."""

    @implements("D4")
    def governing(self, limb: Limb, on: date | None,
                  pending: Pending) -> Governing:
        return curated.governing(limb, on, pending)

    @implements("D4")
    def successions(self) -> tuple[Succession, ...]:
        return curated.successions()
