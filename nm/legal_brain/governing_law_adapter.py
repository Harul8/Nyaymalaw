"""The curated successions, served through the port. LB-120.

`nm.core` may not import `nm.knowledge`, so something in the adapter layer has
to join them -- the same arrangement `CuratedElements` and
`CuratedPreInstitution` already use.
"""
from __future__ import annotations

from datetime import date

from nm.legal_brain import governing_law_sources as curated
from nm.legal_brain.curation_contracts import Curation
from nm.legal_brain.governing_law_port import Governing, Limb, Pending, Succession
from nm.shared.traceability_contracts import implements


class CuratedGoverningLaw:
    """`nm.legal_brain.governing_law_sources`, behind `GoverningLawPort`."""

    @implements("D4")
    def governing(self, limb: Limb, on: date | None,
                  pending: Pending) -> Governing:
        return curated.governing(limb, on, pending)

    @implements("D4")
    def successions(self) -> tuple[Succession, ...]:
        return curated.successions()

    @implements("D4")
    def coverage(self, limb: Limb) -> Curation:
        return curated.coverage(limb)
