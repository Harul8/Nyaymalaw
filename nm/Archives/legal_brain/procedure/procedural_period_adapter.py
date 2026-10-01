"""The curated procedural periods, served through the port. LB-124.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement `CuratedElements`, `CuratedPreInstitution`,
`CuratedGoverningLaw`, `CuratedAuthorityWeight` and `CuratedInterimRelief`
already use.
"""
from __future__ import annotations

from nm.Archives.legal_brain.common.curation_contracts import Curation
from nm.Archives.legal_brain.procedure import procedural_period_sources as curated
from nm.Archives.legal_brain.procedure.procedural_period_port import Period, Running, Track
from nm.shared.traceability_contracts import implements
from nm.work_the_file.matter_contracts import Role


class CuratedProceduralPeriods:
    """`nm.Archives.legal_brain.procedure.procedural_period_sources`, behind `ProceduralPeriodPort`."""

    @implements("D3")
    def engaged(self, role: Role, track: Track) -> tuple[Running, ...]:
        return curated.engaged(role, track)

    @implements("D3")
    def undecided(self, role: Role, track: Track) -> tuple[Period, ...]:
        return curated.undecided(role, track)

    @implements("D3")
    def coverage(self, role: Role) -> Curation:
        return curated.coverage(role)
