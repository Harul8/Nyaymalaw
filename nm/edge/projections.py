"""The two boards. PRD §6.2A.

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

from nm.domain.clock import today as forum_today
from nm.domain.matter import Matter, Role
from nm.domain.traceability import implements


def nearest_first(rows: list[dict]) -> list[dict]:
    """D3's ordering, and BOTH BOARDS ASK THE SAME FUNCTION FOR IT.

    *Nearest deadline first, then what is blocked, then recency. Never
    alphabetically and never by creation date.* The thread board did not sort
    at all and the matter list sorted on a field hard-coded `None`, so the rule
    was stated in the PRD, stated in the docstring, and applied by neither.

    Two copies of an ordering rule drift within a slice, and the advocate then
    sees the urgent file at the top of one board and the bottom of the other.

    A row with no date sorts LAST rather than first: `not_assessed` is a gap
    and a gap is not an emergency, but it must not displace a window that is
    actually running out.

    The two boards name "blocked" differently -- the matter list carries a
    `blocked` reason, the thread row carries `loud` -- so this reads both. One
    function that understands both shapes is the point; a second sort that
    understood only one is what produced the drift.
    """
    def blocked(r: dict) -> bool:
        return r.get("blocked") is not None or bool(r.get("loud"))

    return sorted(rows, key=lambda r: (
        r.get("next_deadline") is None,
        r.get("next_deadline") or "",
        not blocked(r),
        _recency(r),
    ))


def _recency(row: dict) -> int:
    """Most recently worked first. NEGATIVE ORDINAL, not a negated integer.

    This read `-(r.get("last_touched") or 0)` when `last_touched` was the
    VERSION NUMBER -- so the list sorted by how many times a file had been
    written, and a matter written nine times outranked one written twice
    yesterday. BK-33 made it a date, and the old expression then raised
    `bad operand type for unary -: 'str'` on the first list that loaded.

    NEVER WORKED SORTS LAST among otherwise equal rows, which is the honest
    order: a file nobody has opened is not the one they were working on.
    """
    from datetime import date as _date

    raw = str(row.get("last_touched") or "")
    try:
        return -_date.fromisoformat(raw).toordinal()
    except ValueError:
        return 0


def _deadline_window(deadlines, today, *, thread_id=None) -> dict:
    """One read-accounting rule shared by the matter list, board and cover."""
    from nm.core.deadlines import DeadlineStatus, RegisterRead, passed, register, upcoming

    if isinstance(deadlines, RegisterRead):
        held = tuple(d for d in deadlines.rows if thread_id is None or d.thread == thread_id)
        unreadable = [{"thread": p.thread, "index": p.index, "reason": p.reason}
                      for p in deadlines.unreadable
                      if thread_id is None or p.thread in (None, thread_id)]
        unassessed = [t for t in deadlines.unassessed if thread_id is None or t == thread_id]
        assessed = [t for t in deadlines.assessed if thread_id is None or t == thread_id]
        complete = bool(assessed) and not unreadable and not unassessed
    else:
        # A direct tuple is an explicitly supplied, assessed register. The
        # served caller uses RegisterRead and cannot acquire that assumption.
        held = tuple(d for d in (deadlines or ()) if thread_id is None or d.thread == thread_id)
        unreadable, unassessed, assessed = [], [], []
        complete = deadlines is not None
    assessment = ("assessed" if complete else "incomplete" if held or unreadable or assessed
                  else "not_assessed")
    ordered = register(held, today)
    live, gone = upcoming(ordered, today), passed(ordered, today)
    unknown = tuple(d for d in ordered if d.status(today) is DeadlineStatus.NOT_COMPUTED)

    def row(d):
        return {"thread": d.thread, "on": d.on.isoformat() if d.on else None,
                "action": d.action, "owner": d.owner, "source": d.source,
                "consequence": d.consequence, "status": d.status(today).value}

    status = (live[0].status(today).value if live else "passed" if gone else
              "not_computed" if unknown else "not_assessed" if not complete else
              "none_on_this_thread" if thread_id is not None else "none_on_this_matter")
    return {
        "next_deadline": live[0].on.isoformat() if live else None,
        "next_deadline_status": status,
        "deadline_assessment": assessment,
        "deadline_unreadable": unreadable,
        "deadline_unassessed": unassessed,
        "passed_deadlines": ([{**row(d), "days_ago": -d.days(today)} for d in gone]
                             if held or complete else None),
        "uncomputed_deadlines": [row(d) for d in unknown],
        "deadline_entries": [row(d) for d in ordered],
    }


def _thread_row(thread, deadlines, today=None) -> dict:
    """Six fields. One row. No analysis.

    A line that is a conclusion, a reason, or a piece of reasoning does not
    belong here -- that is the test for status versus analysis, and it applies
    without judging importance.

    `deadlines` IS REQUIRED AND HAS THREE STATES. It defaulted to `()`, and the
    served board never passed one -- so every row rendered `next_deadline:
    null` and an advocate reading it saw a file with no deadlines on it. That
    is defect shape S1: the absent input produced the shape of a clean result,
    and `()` could not be told from "nobody computed a register".
    """

    today = today or forum_today()   # BK-14: the forum's date
    window = _deadline_window(deadlines, today, thread_id=thread.id)
    window.pop("deadline_entries")  # The board stays a summary, not a second register.
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
        **window,
        # Rendered LOUDLY by the client, and never collapsed.
        "loud": unresolved or bool(posture.conflicts),
        "conflict": bool(posture.conflicts),
        "deferred_reason": thread.deferred_reason,
    }


@implements("A2")
def board_projection(matter: Matter, deadlines, today=None) -> dict:
    """`deadlines` HAS NO DEFAULT, deliberately.

    It had one -- `()` -- and the served board never passed a register, so
    every row said the file had no deadlines. A default here is a decision
    taken on behalf of every call site that forgets one, and the decision it
    took was to report a gap as a clean sheet. `None` is the honest value for
    a view that did not compute the register, and it now has to be written.
    """
    # D3 — THE NEAREST WINDOW LEADS, regardless of which thread is legally the
    # most interesting. The interesting one will still be there next week.
    rows = nearest_first([_thread_row(t, deadlines, today)
                          for t in matter.threads])
    return {
        "state": "ok",
        "matter_id": matter.id,
        "title": matter.title,
        "version": matter.version,
        "threads": rows,
        # The regression to watch: this must be a function of thread count
        # alone, never of turns, facts, issues or authorities.
        "row_count": len(rows),
        "bounded_by": "thread_count",
    }


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
        from nm.domain.engagement import from_stored

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


@implements("A2")
def matter_list_projection(matters, registers=None) -> dict:
    """The matter list, and what could not be read.

    `matters` is a `MatterList`, not a bare tuple, and that is the whole
    difference: a bare tuple cannot distinguish six matters from seven with one
    corrupt, so an unreadable file vanished and the board looked complete.
    A2 forbids rendering an unbuildable board as an empty one; this is the same
    rule for a board that is merely INCOMPLETE, which is the harder case
    because it looks right.
    """

    unreadable = tuple(getattr(matters, "unreadable", ()))
    today = forum_today()            # BK-14: the forum's date
    rows = []
    for m in matters:
        unresolved = sum(1 for t in m.threads if not t.posture.resolved)
        # THE ORDERING RULE COULD NOT FIRE. `next_deadline` was hard-coded
        # `None` on every row and the sort below reads it first, so "nearest
        # deadline first" -- the rule this list exists to obey -- had no input
        # and every board fell through to recency. Same shape as the thread
        # row above and same answer: three states, and a register that has to
        # be supplied rather than defaulted into silence.
        register = None if registers is None else registers.get(m.id)
        window = _deadline_window(register, today)
        window.pop("deadline_entries")
        rows.append({
            "matter_id": m.id,
            "matter": m.title,
            # WHO THE FILE IS FOR, and it was the ADVOCATE'S OWN ID. BK-33.
            #
            # Every row in an advocate's list said `client: adv_demo`, which
            # is the one thing every row has in common -- so the column that
            # exists to tell ten matters apart told them apart by nothing.
            # The names come from intake (BK-34); a matter opened before it
            # says so rather than naming the advocate.
            "client": _party(m, "client") or "not recorded",
            "opponent": _party(m, "adverse") or "not recorded",
            "threads": len(m.threads),
            **window,
            # What is BLOCKED is a status field, not analysis: it is the handle
            # the advocate uses to decide what to open.
            "blocked": (f"{unresolved} thread(s) awaiting posture" if unresolved else None),
            # WHEN, NOT HOW MANY TIMES. `last_touched` was `m.version`, an
            # integer counting writes -- so a matter written nine times
            # looked more recent than one written twice yesterday.
            "last_touched": m.last_activity or "never worked",
        })
    rows = nearest_first(rows)
    return {
        # NOT "ok" when something could not be read. An advocate scanning a
        # board for what needs them must be able to see that a file is missing
        # from it, and `row_count` alone would say six either way.
        "state": "ok" if not unreadable else "incomplete",
        "matters": rows,
        "row_count": len(rows),
        "bounded_by": "matter_count",
        "unreadable": list(unreadable),
        "unreadable_reason": (
            f"{len(unreadable)} matter(s) on this file could not be read and "
            f"are NOT in the list above: {', '.join(unreadable)}. They are not "
            f"gone — they could not be decoded, and anything they hold is not "
            f"shown." if unreadable else None),
    }


def unbuildable(reason: str) -> dict:
    """A board that could not be built is an EXPLICIT FAILURE.

    Never an empty one. A board that fails to load and renders empty tells the
    advocate they have no matters -- defect shape S1 in its most visible
    possible form.
    """
    return {"state": "unbuildable", "reason": reason, "matters": [], "row_count": 0}


# ============================== the matter cover ============================
#
# BK-33-AC1. A THIRD PROJECTION, and the reason it is not one of the two
# boards above is the arity rule those boards exist to protect: the cover is
# bounded by NOTHING -- it is one matter, once. Adding it to either board
# would give that board a second bound and the ordering rule a second subject.


def _stage_of(matter: Matter) -> str:
    """Where this file is, from what is persisted. NEVER GUESSED.

    `opening` is what a file with no threads genuinely is, not a default
    somebody chose because the field had to say something.
    """
    if not matter.threads:
        return "opening"
    if any(t.deferred_reason or not t.posture.resolved or t.posture.conflicts
           for t in matter.threads):
        return "blocked"
    # A saved dispute is evidence of work in progress, not of a released
    # professional opinion or a particular advice-maturity level.
    return "work_in_progress"


def _cover_posture(matter: Matter) -> dict:
    """An aggregate cannot turn the first thread's role into every thread's role."""
    rows = [{"thread_id": thread.id, "thread": thread.label,
             "role": thread.posture.role.value, "basis": thread.posture.basis.value,
             "resolved": thread.posture.resolved,
             "conflicts": [{"on_record": c.on_record.value,
                            "now_suggested": c.now_suggested.value, "applied": c.applied}
                           for c in thread.posture.conflicts]}
            for thread in matter.threads]
    roles = {thread.posture.role for thread in matter.threads
             if thread.posture.role is not Role.UNKNOWN}
    if any(row["conflicts"] for row in rows):
        state = "conflicted"
    elif not roles:
        state = "not_established"
    elif any(not row["resolved"] for row in rows):
        state = "partial"
    elif len(roles) > 1:
        state = "mixed"
    else:
        state = "recorded"
    posture = next(iter(roles)).value if state == "recorded" else (
        "mixed" if state == "mixed" else "unknown")
    return {"posture": posture, "posture_state": state, "postures": rows}


def cover_projection(matter: Matter, deadlines=None, today=None) -> dict:
    """THE COVER. Client, title, posture, stage, last activity, deadline state.

    EVERY FIELD IS EITHER PERSISTED OR SAYS IT IS NOT ASSESSED. BK-33-AC1's
    whole subject is that an unassessed value must not be rendered as a fact,
    and the two ways that happens are a blank that reads as "none" and an
    implementation id that reads as a name. So:

      * the client is what the ADVOCATE said, or `not recorded`
      * the posture is `Role.UNKNOWN`'s own word, never a guess from the title
      * the deadline carries its ASSESSMENT STATE, so `no deadline` and
        `nobody has worked out the deadline` are different sentences
      * `matter_id` is present and is never offered as the title

    `deadlines=None` is honoured rather than defaulted, for the reason
    `board_projection` gives directly above: a default here would report an
    uncomputed register as a clean sheet on every call site that forgot one.
    """
    from nm.domain.commission import Commission
    commission = Commission.from_stored(matter.commission)
    client = _party(matter, "client")

    deadline_state = "not_assessed"
    deadline_said = "no instruction deadline has been assessed on this matter"
    if commission is not None:
        deadline_state = ("assessed" if commission.deadline.assessed
                          else "not_assessed")
        deadline_said = commission.deadline.said()

    return {
        "state": "ok",
        "matter_id": matter.id,
        "title": matter.title,
        "version": matter.version,
        # NOT "" AND NOT THE MATTER ID. An empty client field reads as a file
        # with no client; the id reads as a name nobody chose.
        "client": client or None,
        "client_state": "recorded" if client else "not_recorded",
        **_cover_posture(matter),
        "stage": _stage_of(matter),
        "last_activity": matter.last_activity or None,
        "last_activity_state": "recorded" if matter.last_activity else "not_recorded",
        # Legacy aliases retain their commission meaning. A case-register
        # date must not overwrite a separate deadline in the instructions.
        "deadline_scope": "commission",
        "deadline_assessment": deadline_state,
        "deadline_said": deadline_said,
        "case_deadlines": _deadline_window(deadlines, today or forum_today()),
        "commission": commission.as_dict() if commission else None,
        "commission_state": ("recorded" if commission else "not_recorded"),
        "thread_count": len(matter.threads),
    }
