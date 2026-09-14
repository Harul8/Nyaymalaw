"""The curated element table, served through the port. D5.

A CLASS AROUND TWO FUNCTIONS, and it earns its place: `nm.core` may not import
`nm.knowledge`, so something in the adapter layer has to join them. Making it
an object rather than a module of functions is what lets a test hand the turn
a table of its own without touching the curated one -- which is how the proof
read is exercised on a cause that does not exist.
"""
from __future__ import annotations

from nm.domain.matter import CauseOfAction
from nm.domain.traceability import implements
from nm.knowledge import elements as curated
from nm.ports.elements import Elements


class CuratedElements:
    """`nm.knowledge.elements`, behind `ElementsPort`."""

    @implements("D5")
    def elements_for(self, cause: CauseOfAction) -> Elements | None:
        return curated.elements_for(cause)

    @implements("D5")
    def why_not(self, cause: CauseOfAction) -> str:
        return curated.why_not(cause)
