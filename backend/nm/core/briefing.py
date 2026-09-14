"""The interactive briefing: readiness is not turn completion. P24.

    from nm.core.briefing import readiness, refuse_completion, live_gaps, next_step

BK-54-AC3 and BK-91-AC3, and the close of C1 NEVER[4]:

    Never equate completing a conversation turn with completing intake. Never
    promote an unknown answer to no, re-ask a confirmed fact without a new
    reason, or loop indefinitely on unavailable material.

WHY A TURN COMPLETING IS NOT INTAKE COMPLETING
------------------------------------------------
Every turn produces an answer -- that is the turn contract. It does not follow
that the file is ready for the task: a controlling gap can remain open while the
turn answered perfectly on what it had. So readiness is derived from the OPEN
GAPS, never from the fact that a turn finished, and `refuse_completion` returns a
reason whenever a gap is still open. That is the sentence C1 forbids being
written, made unwritable.

UNAVAILABLE IS PAUSED, NOT LOOPED
-----------------------------------
A need the advocate cannot obtain is PAUSED on the matter (`Matter.pause_need`).
`live_gaps` drops paused needs from what is asked, so the same question is not
put a third time; and readiness reports `blocked` -- a stop/resume decision is
owed -- rather than `open`, which would invite the re-ask. The resume trigger is
recorded, so a pause is a decision with a way back, not a thing forgotten. A
paused need is NOT answered: intake stays incomplete on it, because promoting an
unavailable answer to a settled one is the other half of what C1 forbids.

THE LEAD CHOOSES THE NEXT MOVE
--------------------------------
`next_step` hands the live gaps to `nm.core.lead.propose`, so the briefing's next
action is the adaptive lead's -- retrieve, ask, or stop from the state, not a
fixed questionnaire. This is how P46 reaches the actual briefing interaction.
"""
from __future__ import annotations

from nm.core import lead
from nm.domain.lead import Plan


def live_gaps(gap_whats: tuple[str, ...],
              paused: frozenset[str]) -> tuple[str, ...]:
    """The gaps that may still be asked -- the current gaps minus the ones the
    advocate marked unavailable. Order preserved, so the smallest useful ask is
    still the highest-ranked live gap."""
    return tuple(g for g in gap_whats if g not in paused)


def readiness(gap_whats: tuple[str, ...],
              paused: frozenset[str]) -> lead.Readiness:
    """Intake readiness, in the lead's own vocabulary. `ready` only when no gap
    is open; `open` while an obtainable gap remains; `blocked` when every
    remaining gap is unavailable and a stop/resume decision is owed. NEVER
    derived from a turn having finished -- the gaps are the population."""
    live = live_gaps(gap_whats, paused)
    stalled = tuple(g for g in gap_whats if g in paused)
    if live:
        return lead.Readiness("open", "a controlling gap is still open and "
                              "obtainable", live)
    if stalled:
        return lead.Readiness(
            "blocked", "every remaining gap is unavailable; a stop or resume "
            "decision is owed", stalled)
    return lead.Readiness("ready", "no controlling gap remains", ())


def refuse_completion(gap_whats: tuple[str, ...],
                      paused: frozenset[str]) -> str:
    """Why intake may NOT be reported complete, or an empty string. C1 NEVER[4]:
    a turn finishing does not close intake while a gap is open. The served
    response consults this before it could ever mark intake done."""
    state = readiness(gap_whats, paused)
    if state.state == "ready":
        return ""
    if state.state == "blocked":
        return ("intake is not complete: every remaining gap is unavailable and "
                "awaits a stop or resume decision — "
                + "; ".join(state.open_predicates))
    return ("intake is not complete: a controlling gap remains open — "
            + "; ".join(state.open_predicates))


def block(matter) -> dict:
    """The served intake-readiness block for one matter. ONE OWNER, so the turn
    response and the byte boundary cannot disagree about whether intake is ready
    -- the S9 shape this project keeps refusing. `matter` may be None on the
    non-matter route, which is `not_assessed`, not ready."""
    if matter is None:
        return {"state": "not_assessed", "why": "no matter on this route",
                "open_needs": [], "paused": [], "intake_complete_refused": ""}
    gap_whats = tuple(
        (g.get("what") if isinstance(g, dict) else getattr(g, "what", ""))
        for t in matter.threads for g in (getattr(t, "gaps", ()) or ()))
    gap_whats = tuple(w for w in gap_whats if w)
    paused = matter.paused_need_texts
    state = readiness(gap_whats, paused)
    # THE LEAD CHOOSES THE NEXT MOVE (P46). The briefing does not walk a fixed
    # questionnaire: the adaptive lead reads the live gaps and proposes the next
    # action -- retrieve/ask when a gap is open, stop when none is. This is how
    # the lead reaches the actual briefing interaction, and its production path.
    step = next_step(gap_whats, paused)
    return {
        "state": state.state, "why": state.why,
        "open_needs": list(live_gaps(gap_whats, paused)),
        "paused": [{"need": p.get("need"), "resume_when": p.get("resume_when", "")}
                   for p in matter.paused_needs if isinstance(p, dict)],
        "intake_complete_refused": refuse_completion(gap_whats, paused),
        "next_step": {"action": step.action.value, "rationale": step.rationale},
    }


def next_step(gap_whats: tuple[str, ...], paused: frozenset[str], *,
              side: str = "", opposing_party: str = "", objective: str = "",
              wants_draft: bool = False) -> lead.StepProposal:
    """The next briefing move, chosen by the adaptive lead from the LIVE gaps.
    Paused needs are not offered, so the lead never proposes to re-ask an
    unavailable one; when nothing is live it proposes to draft or stop rather
    than manufacturing a question."""
    live = live_gaps(gap_whats, paused)
    plan = Plan(snapshot_version=0, open_needs=live)
    return lead.propose(plan, side=side, opposing_party=opposing_party,
                        objective=objective, wants_draft=wants_draft)
