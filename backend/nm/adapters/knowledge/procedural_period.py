"""The curated procedural periods, served through the port. LB-124.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement `CuratedElements`, `CuratedPreInstitution`,
`CuratedGoverningLaw`, `CuratedAuthorityWeight` and `CuratedInterimRelief`
already use.
"""
from __future__ import annotations

from nm.domain.matter import Role
from nm.domain.traceability import implements
from nm.knowledge import procedural_period as curated
from nm.ports.procedural_period import Period, Running, Track


class CuratedProceduralPeriods:
    """`nm.knowledge.procedural_period`, behind `ProceduralPeriodPort`."""

    @implements("D3")
    def engaged(self, role: Role, track: Track) -> tuple[Running, ...]:
        return curated.engaged(role, track)

    @implements("D3")
    def undecided(self, role: Role, track: Track) -> tuple[Period, ...]:
        return curated.undecided(role, track)
