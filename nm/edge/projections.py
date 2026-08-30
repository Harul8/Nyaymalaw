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


def _thread_row(thread) -> dict:
    """Six fields. One row. No analysis.

    A line that is a conclusion, a reason, or a piece of reasoning does not
    belong here -- that is the test for status versus analysis, and it applies
    without judging importance.
    """
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
        "next_deadline": None,
        # Rendered LOUDLY by the client, and never collapsed.
        "loud": unresolved or bool(posture.conflicts),
        "conflict": bool(posture.conflicts),
        "deferred_reason": thread.deferred_reason,
    }


@implements("A2")
def board_projection(matter: Matter) -> dict:
    rows = [_thread_row(t) for t in matter.threads]
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
def matter_list_projection(matters) -> dict:
    """The matter list, and what could not be read.

    `matters` is a `MatterList`, not a bare tuple, and that is the whole
    difference: a bare tuple cannot distinguish six matters from seven with one
    corrupt, so an unreadable file vanished and the board looked complete.
    A2 forbids rendering an unbuildable board as an empty one; this is the same
    rule for a board that is merely INCOMPLETE, which is the harder case
    because it looks right.
    """
    unreadable = tuple(getattr(matters, "unreadable", ()))
    rows = []
    for m in matters:
        unresolved = sum(1 for t in m.threads if not t.posture.resolved)
        rows.append({
            "matter_id": m.id,
            "matter": m.title,
            "client": m.advocate_id,
            "threads": len(m.threads),
            "next_deadline": None,
            # What is BLOCKED is a status field, not analysis: it is the handle
            # the advocate uses to decide what to open.
            "blocked": (f"{unresolved} thread(s) awaiting posture" if unresolved else None),
            "last_touched": m.version,
        })
    # Nearest deadline first, then what is blocked, then recency. NEVER
    # alphabetically and never by creation date.
    rows.sort(key=lambda r: (
        r["next_deadline"] is None,
        r["next_deadline"] or "",
        r["blocked"] is None,
        -r["last_touched"],
    ))
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
