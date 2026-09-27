"""The curated pre-institution table, served through the port. LB-121.

`nm.core` may not import `nm.knowledge`, so something in the adapter layer has
to join them -- the same arrangement `CuratedElements` already uses, and an
object rather than a module of functions for the same reason: a test can hand
the turn a table of its own without touching the curated one.
"""
from __future__ import annotations

from nm.legal_brain import institution_sources as curated
from nm.legal_brain.curation_contracts import Curation
from nm.legal_brain.institution_port import Against, Condition, Engagement
from nm.shared.traceability_contracts import implements
from nm.work_the_file.matter_contracts import CauseOfAction


class CuratedPreInstitution:
    """`nm.legal_brain.institution_sources`, behind `PreInstitutionPort`."""

    @implements("D1")
    def engaged(self, cause: CauseOfAction,
                against: Against) -> tuple[Engagement, ...]:
        return curated.engaged(cause, against)

    @implements("D1")
    def undecided(self, cause: CauseOfAction,
                  against: Against) -> tuple[Condition, ...]:
        return curated.undecided(cause, against)

    @implements("D1")
    def coverage(self, cause: CauseOfAction) -> Curation:
        return curated.coverage(cause)
