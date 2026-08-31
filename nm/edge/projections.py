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
        -(r.get("last_touched") or 0),
    ))


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
    from datetime import date as _date

    from nm.core.deadlines import passed as _passed
    from nm.core.deadlines import upcoming as _upcoming

    today = today or _date.today()
    if deadlines is None:
        # NOT ASSESSED, said as a value. Not the same as a file with no
        # deadlines, and the two must not render alike.
        window = {"next_deadline": None,
                  "next_deadline_status": "not_assessed",
                  "passed_deadlines": None}
    else:
        ours = tuple(d for d in deadlines if d.thread == thread.id)
        mine = _upcoming(ours, today)
        gone = _passed(ours, today)
        window = {
            # A2.5. THE NEAREST LIVE DEADLINE, and the passed ones separately.
            # This was hard-coded `None`, so the clause forbidding a passed
            # deadline from being dropped was a rule about a field that never
            # held anything.
            "next_deadline": (mine[0].on.isoformat() if mine else None),
            "next_deadline_status": (mine[0].status(today).value if mine
                                     else "none_on_this_thread"),
            # PASSED ROWS ARE THEIR OWN LIST. Merging them into what is
            # upcoming buries the thing that can no longer be done among the
            # things that still can, and the advocate scans the second for work.
            "passed_deadlines": [
                {"on": d.on.isoformat(), "action": d.action,
                 "consequence": d.consequence, "days_ago": -d.days(today)}
                for d in gone],
        }
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
    from datetime import date as _date

    from nm.core.deadlines import upcoming as _upcoming

    unreadable = tuple(getattr(matters, "unreadable", ()))
    today = _date.today()
    rows = []
    for m in matters:
        unresolved = sum(1 for t in m.threads if not t.posture.resolved)
        # THE ORDERING RULE COULD NOT FIRE. `next_deadline` was hard-coded
        # `None` on every row and the sort below reads it first, so "nearest
        # deadline first" -- the rule this list exists to obey -- had no input
        # and every board fell through to recency. Same shape as the thread
        # row above and same answer: three states, and a register that has to
        # be supplied rather than defaulted into silence.
        register = None if registers is None else registers.get(m.id, ())
        live = () if register is None else _upcoming(tuple(register), today)
        rows.append({
            "matter_id": m.id,
            "matter": m.title,
            "client": m.advocate_id,
            "threads": len(m.threads),
            "next_deadline": live[0].on.isoformat() if live else None,
            "next_deadline_status": (
                "not_assessed" if register is None
                else live[0].status(today).value if live
                else "none_on_this_matter"),
            # What is BLOCKED is a status field, not analysis: it is the handle
            # the advocate uses to decide what to open.
            "blocked": (f"{unresolved} thread(s) awaiting posture" if unresolved else None),
            "last_touched": m.version,
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
