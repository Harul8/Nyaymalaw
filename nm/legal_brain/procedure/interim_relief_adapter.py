"""The curated interim tests, served through the port. LB-123.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement `CuratedElements`, `CuratedPreInstitution`,
`CuratedGoverningLaw` and `CuratedAuthorityWeight` already use.
"""
from __future__ import annotations

from nm.legal_brain.common.curation_contracts import Curation
from nm.legal_brain.procedure import interim_relief_sources as curated
from nm.legal_brain.procedure.interim_relief_port import Assessment, InterimRelief, Test
from nm.shared.traceability_contracts import implements


class CuratedInterimRelief:
    """`nm.legal_brain.procedure.interim_relief_sources`, behind `InterimReliefPort`."""

    @implements("D1")
    def test_for(self, relief: InterimRelief) -> Test | None:
        return curated.test_for(relief)

    @implements("D1")
    def assess(self, relief: InterimRelief) -> Assessment:
        return curated.assess(relief)

    @implements("D1")
    def coverage(self, relief: InterimRelief) -> Curation:
        return curated.coverage(relief)
