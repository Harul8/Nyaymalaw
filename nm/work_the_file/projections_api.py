"""Historical projection helpers. The former matter board is explicitly retired.

No current HTTP route uses these projections. Do not reconnect the board until
its owned state, source and replay contracts are implemented and verified.
The following notes describe the earlier PRD §6.2A projection design.

THERE ARE TWO OF THEM, AND CONFLATING THEM IS A REAL DEFECT
-----------------------------------------------------------
An advocate holds many MATTERS; a matter holds many THREADS. The landing
surface answers *which of my files needs me?* and the in-conversation surface
answers *where does each dispute in this file stand?*

Those are different rows and, crucially, DIFFERENT ARITY BOUNDS:

    matter list  -> bounded by MATTER count
    thread board -> bounded by THREAD count

Give them one name and one bound and the board eventually scales on the wrong
axis, which is the exact regression the board-discipline rule exists to prevent.

Neither board computes anything. Both are projections, and both hold NOTHING
the underlying state does not -- because a board that disagrees with the answer
is worse than either alone: the advocate cannot tell which is stale.
"""
from __future__ import annotations

from nm.shared.clock_contracts import today as forum_today
from nm.work_the_file.matter_contracts import Matter, Role


def _saved(matters, matter) -> str:
    """When the store last saved this matter (`MatterList.saved_at`), or empty."""
    saved = getattr(matters, "saved", None)
    return saved(matter.id) if callable(saved) else ""


def latest_first(matters) -> list:
    """F-B-14's ordering for My work: the latest updated matter first.

    Owner, 28 September 2026: *"sort the matters based on the last updated
    date, with latest updated at the top."* The key is when the STORE last
    saved each file (`MatterList.saved_at`) -- every save goes through it, so a
    message, a correction, a board edit and an upload all count and no writer
    can forget. A matter the store cannot date falls back to the day it was
    last worked, which sorts below any timed save on that day. Never worked
    and undated sorts last.

    Deadlines no longer order this list (PRD A2 revised the same day); each
    row still carries its deadline. The thread board keeps `nearest_first`.
    """
    return sorted(matters, key=lambda m: _saved(matters, m) or m.last_activity or "",
                  reverse=True)


def _currency_of(ledger, thread_id: str, deadline) -> tuple[str, str]:
    """Whether one register row may be shown as current. THREE STATES.

    `current`         the ledger holds the node and nothing it rests on moved
    `stale`           something moved and it has not been recomputed (or was
                      recomputed and failed, or is being recomputed now)
    `not_established` no node is recorded for it -- a register written before
                      the ledger existed, or a kind the ledger does not track

    The third is a VALUE and it is rendered, because the two failures it
    stands between are opposite: a stale deadline the advocate acts on, and a
    real deadline the board hides because nobody recorded its inputs.
    """
    from nm.work_the_file.deadline_proposals import deadline_proposal_currency
    from nm.work_the_file.deadlines import DeadlineKind
    from nm.work_the_file.dependency import Currency, names_for, presentable

    proposal_currency = deadline_proposal_currency(ledger, deadline)
    if proposal_currency is not None:
        return proposal_currency
    if getattr(deadline, "kind", None) is not DeadlineKind.LIMITATION:
        return "not_established", "the ledger does not track this kind of deadline"
    name = names_for(thread_id).deadline
    node = ledger.node(name)
    if node is None:
        return ("not_established",
                "no dependency record exists for this deadline, so whether it "
                "is still current has not been established")
    ok, why = presentable(ledger, name)
    if ok:
        return "current", ""
    state = ("stale" if node.currency in (Currency.STALE, Currency.REWORKING)
             else "not_established")
    return state, why


def _deadline_window(deadlines, today, *, thread_id=None, currency=None) -> dict:
    """One deadline and currency rule shared by list, board and cover."""
    from nm.work_the_file.deadlines import (
        DeadlineKind,
        DeadlineStatus,
        RegisterRead,
        passed,
        register,
        upcoming,
    )
    from nm.work_the_file.dependency import Ledger

    if isinstance(deadlines, RegisterRead):
        held = tuple(d for d in deadlines.rows if thread_id is None or d.thread == thread_id)
        unreadable = [{"thread": p.thread, "index": p.index, "reason": p.reason}
                      for p in deadlines.unreadable
                      if thread_id is None or p.thread in (None, thread_id)]
        unassessed = [t for t in deadlines.unassessed if thread_id is None or t == thread_id]
        assessed = [t for t in deadlines.assessed if thread_id is None or t == thread_id]
        complete = bool(assessed) and not unreadable and not unassessed
    else:
        held = tuple(d for d in (deadlines or ()) if thread_id is None or d.thread == thread_id)
        unreadable, unassessed, assessed = [], [], []
        complete = deadlines is not None

    # An advocate's promised document belongs on the follow-up list, not in
    # legal urgency, deadline assessment or the nearest filing-date summary.
    followups = register(tuple(d for d in held
                               if d.kind is DeadlineKind.INFORMATION_FOLLOWUP), today)
    held = tuple(d for d in held if d.kind is not DeadlineKind.INFORMATION_FOLLOWUP)
    ledger = Ledger.from_stored(currency)
    judged = {id(d): _currency_of(ledger, d.thread, d) for d in held}
    current = tuple(d for d in held if judged[id(d)][0] != "stale")
    stale = register(tuple(d for d in held if judged[id(d)][0] == "stale"), today)
    ordered = register(current, today)
    all_ordered = register(held, today)
    live, gone = upcoming(ordered, today), passed(ordered, today)
    unknown = tuple(d for d in ordered if d.status(today) is DeadlineStatus.NOT_COMPUTED)
    assessment = ("assessed" if complete else "incomplete"
                  if held or unreadable or assessed else "not_assessed")

    def row(d):
        state, why = judged[id(d)]
        return {"thread": d.thread, "on": d.on.isoformat() if d.on else None,
                "conditional_on": (d.conditional_on.isoformat()
                                   if d.conditional_on else None),
                "action": d.action, "owner": d.owner, "source": d.source,
                "consequence": d.consequence, "status": d.status(today).value,
                "currency": state, "currency_reason": why}

    status = (live[0].status(today).value if live else "stale" if stale else
              # A known obligation whose date is not established is not a
              # clean sheet. A separately labelled conditional calculation
              # remains visible in `uncomputed_deadlines`, never promoted to
              # `next_deadline`.
              "passed" if gone else "not_computed" if unknown else
              "not_assessed" if not complete else "none_on_this_thread"
              if thread_id is not None else "none_on_this_matter")
    return {
        "next_deadline": live[0].on.isoformat() if live else None,
        "next_deadline_status": status,
        "next_deadline_currency": judged[id(live[0])][0] if live else None,
        "stale_deadline": stale[0].on.isoformat() if stale and stale[0].on else None,
        "stale_deadlines": len(stale),
        "deadline_assessment": assessment,
        "deadline_unreadable": unreadable,
        "deadline_unassessed": unassessed,
        "passed_deadlines": ([{**row(d), "days_ago": -d.days(today)} for d in gone]
                             if held or complete else None),
        "uncomputed_deadlines": [row(d) for d in unknown],
        "deadline_entries": [row(d) for d in all_ordered],
        "information_followups": [
            {"thread": d.thread, "on": d.on.isoformat() if d.on else None,
             "action": d.action, "owner": d.owner, "source": d.source,
             "status": ("date_not_given" if d.on is None else
                        "due" if d.on <= today else "upcoming")}
            for d in followups],
    }


#: WHAT A BOARD ROW CARRIES FROM THE DEADLINE WINDOW. An ALLOWLIST, and the
#: switch from a denylist is the fix rather than an implementation detail.
#:
#: THE MEASURED DEFECT, 22 September 2026. Both board projections said
#: `window.pop("deadline_entries")` and then `**window` -- naming the one key
#: that must not pass and admitting everything else. That is a denylist, and a
#: denylist FAILS OPEN for the key added after it was written. D-INFO added
#: `information_followups` to `_deadline_window`, nothing popped it, and an
#: analysis list -- what to chase, from whom -- landed on every thread row of
#: a board whose whole rule is that it carries status and never analysis.
#:
#: A2's NEVER clause is not a style preference: a board is what the advocate
#: scans to choose a file, so a conclusion sitting on it is one they act on
#: without the reasoning that produced it.
#:
#: Stated positively, a key added to the window tomorrow does NOT reach the
#: board, and whoever wants it there adds it here -- where
#: `test_neither_board_carries_analysis` asks them to justify it. That test
#: keeps its OWN copy of this set on purpose: a control that reads the
#: production list would ratify whatever production says.
_BOARD_WINDOW = (
    "next_deadline", "next_deadline_status", "next_deadline_currency",
    "stale_deadline", "stale_deadlines", "deadline_assessment",
    "deadline_unreadable", "deadline_unassessed", "passed_deadlines",
    "uncomputed_deadlines",
)


def _board_window(window: dict) -> dict:
    """The status fields of a deadline window, and nothing else.

    ONE OWNER FOR TWO BOARDS. The thread board and the matter listing had the
    same `pop`-and-spread in two places, so the leak arrived on both at once
    and either could have been fixed without the other.
    """
    return {key: window[key] for key in _BOARD_WINDOW if key in window}


def _thread_row(thread, deadlines, today=None, currency=None) -> dict:
    """Six fields. One row. No analysis.

    A line that is a conclusion, a reason, or a piece of reasoning does not
    belong here -- that is the test for status versus analysis, and it applies
    without judging importance.

    `deadlines` IS REQUIRED AND HAS THREE STATES. It defaulted to `()`, and the
    served board never passed one -- so every row rendered `next_deadline:
    null` and an advocate reading it saw a file with no deadlines on it. That
    is defect shape S1: the absent input produced the shape of a clean result,
    and `()` could not be told from "nobody computed a register".

    `currency` IS THE MATTER'S DEPENDENCY LEDGER (P18). A deadline whose
    node is STALE is not the nearest live deadline however near its date: it
    is listed, labelled, and kept out of `next_deadline`, because the one
    thing the board must never do is put a date the advocate has corrected
    at the top of their day.

    A deadline whose currency is NOT_ESTABLISHED -- a register written before
    the ledger existed -- stays in the running and carries the label. The two
    are different facts: stale is a FINDING that an input moved, and
    not-established is a GAP in what was recorded. Hiding a real window
    because nobody recorded its inputs is the opposite failure, and the
    label is what keeps the gap from reading as a clean sheet.
    """

    today = today or forum_today()   # BK-14: the forum's date
    window = _deadline_window(
        deadlines, today, thread_id=thread.id, currency=currency)
    posture = thread.posture
    unresolved = not posture.resolved
    return {
        "thread_id": thread.id,
        "thread": thread.label,
        # `unknown` renders as a VALUE, never as an empty field: an empty cell
        # reads as "not important yet".
        "our_client_is": posture.role.value if posture.role is not Role.UNKNOWN else "unknown",
        "side": posture.side.value,
        "against": posture.opponent or "unknown",
        "forum": "not established",
        "stage": "opening",
        **_board_window(window),
        # Rendered LOUDLY by the client, and never collapsed.
        "loud": unresolved or bool(posture.conflicts),
        "conflict": bool(posture.conflicts),
        "deferred_reason": thread.deferred_reason,
    }


def board_projection(matter: Matter, deadlines, today=None, *, source_current=None,
                     checklist_projections=None, prior_conversation=()) -> dict:
    """Retired board boundary; current owned projections must be built before reuse.

    Removed brain state modules cannot safely reconstruct saved disputes,
    material or requirements. Refuse explicitly without reading or mutating the
    matter instead of returning an empty board that looks successfully assessed.
    The retained deadline/list/cover helpers remain independently importable.
    """
    raise NotImplementedError(
        "The historical matter board is retired; owned projection and replay "
        "contracts must be implemented before reopening it.")


def _party(matter, side: str) -> str:
    """The first party on this side, from intake or from the threads.

    INTAKE FIRST, because it is what the advocate typed and the threads hold
    what was read. Where a matter predates intake the thread posture is less
    and is not nothing.
    """
    for name, recorded in (getattr(matter, "intake_parties", None) or {}).items():
        if recorded == side:
            return str(name)
    if side == "client":
        from nm.open_matter.engagement_contracts import from_stored

        engagement = from_stored(matter.engagement)
        if engagement is not None and engagement.client:
            return engagement.client
    for thread in getattr(matter, "threads", ()):
        for name, recorded in (getattr(thread, "parties", None) or {}).items():
            if recorded == side:
                return str(name)
        if side == "adverse":
            opponent = getattr(getattr(thread, "posture", None), "opponent", "")
            if opponent:
                return str(opponent)
    return ""


# ============================== the matter cover ============================
#
# BK-33-AC1. A THIRD PROJECTION, and the reason it is not one of the two
# boards above is the arity rule those boards exist to protect: the cover is
# bounded by NOTHING -- it is one matter, once. Adding it to either board
# would give that board a second bound and the ordering rule a second subject.


