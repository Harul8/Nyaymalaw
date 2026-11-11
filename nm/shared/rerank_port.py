"""Plan AN.48, D176 (pieces 48f7-48f8, owner decisions of 11 Nov 2026): the search's reranking done by NM's own graphics machine, and
what research does when that machine cannot be had.

On the hosted installation the reranker runs on a graphics machine of its own, which sleeps when it is not used and is woken by NM.
Where it cannot be woken - AWS cannot start it, or this month's budget has stopped it - a search must not go on unranked as if
nothing had happened: the owner's decision is that research pauses. The adapter that talks to the machine raises ResearchPaused; the
search lets it through; the turn stops there, keeping everything it finished, and Continue takes it up (AN.41).

A port: the engine imports only this, never the adapter.
"""
from __future__ import annotations

#: Why research paused. The words the advocate reads are the turn's (turn.STOPS); the adapter only names which.
GRAPHICS_UNAVAILABLE = "graphics_unavailable"
BUDGET_PAUSED = "budget_paused"
CODES = (GRAPHICS_UNAVAILABLE, BUDGET_PAUSED)


class ResearchPaused(Exception):
    """The search's graphics machine cannot rerank now. Not a search failure to be recorded and passed over: the turn stops,
    keeping everything finished, and Continue takes it up (D176). code: one of CODES."""

    def __init__(self, code: str, detail: str = ""):
        if code not in CODES:
            raise ValueError(f"Unknown reason for pausing research: {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        #: For the operator's log only: never shown to the advocate, never matter text.
        self.detail = detail
