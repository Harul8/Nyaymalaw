"""The curated pre-institution table, served through the port. LB-121.

`nm.core` may not import `nm.knowledge`, so something in the adapter layer has
to join them -- the same arrangement `CuratedElements` already uses, and an
object rather than a module of functions for the same reason: a test can hand
the turn a table of its own without touching the curated one.
"""
from __future__ import annotations

from nm.domain.matter import CauseOfAction
from nm.domain.traceability import implements
from nm.knowledge import institution as curated
from nm.ports.institution import Against, Condition, Engagement


class CuratedPreInstitution:
    """`nm.knowledge.institution`, behind `PreInstitutionPort`."""

    @implements("D1")
    def engaged(self, cause: CauseOfAction,
                against: Against) -> tuple[Engagement, ...]:
        return curated.engaged(cause, against)

    @implements("D1")
    def undecided(self, cause: CauseOfAction,
                  against: Against) -> tuple[Condition, ...]:
        return curated.undecided(cause, against)
