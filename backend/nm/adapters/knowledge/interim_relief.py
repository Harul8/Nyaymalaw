"""The curated interim tests, served through the port. LB-123.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement `CuratedElements`, `CuratedPreInstitution`,
`CuratedGoverningLaw` and `CuratedAuthorityWeight` already use.
"""
from __future__ import annotations

from nm.domain.traceability import implements
from nm.knowledge import interim_relief as curated
from nm.ports.interim_relief import Assessment, InterimRelief, Test


class CuratedInterimRelief:
    """`nm.knowledge.interim_relief`, behind `InterimReliefPort`."""

    @implements("D1")
    def test_for(self, relief: InterimRelief) -> Test | None:
        return curated.test_for(relief)

    @implements("D1")
    def assess(self, relief: InterimRelief) -> Assessment:
        return curated.assess(relief)
