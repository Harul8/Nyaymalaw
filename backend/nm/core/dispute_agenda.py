"""One derived whole-file agenda for the conversation and the matter board.

Review readiness is not permission to close a file or act for a client. No
population can pass by disappearing, and a pause never answers a question.
"""

from __future__ import annotations

from nm.core import dependency
from nm.domain.summary import DERIVED_SECTIONS


def _value(row, name, default=""):
    return row.get(name, default) if isinstance(row, dict) else getattr(row, name, default)


def project(matter, *, after_thread_id=None) -> dict:
    """Recompute, never persist a second status or infer completeness from size."""
    ledger = dependency.Ledger.from_stored(matter.dependencies)
    rows = []
    for thread in matter.threads:
        questions = [q for q in matter.asked if q.thread == thread.id and q.open]
        needs = tuple(
            dict.fromkeys(
                [str(_value(g, "what")) for g in thread.gaps if _value(g, "what")]
                + [q.text for q in questions]
            )
        )
        paused = matter.paused_need_texts
        live = tuple(
            n
            for n in needs
            if n not in paused and not any(q.text == n and q.times_asked > 1 for q in questions)
        )
        stale = any(
            n.name.endswith(" on " + thread.id) and n.currency is not dependency.Currency.CURRENT
            for n in ledger.nodes
        )
        missing = tuple(s for s in DERIVED_SECTIONS if s not in thread.assessed)
        if thread.deferred_reason:
            status, reason = "paused", thread.deferred_reason
        elif thread.posture.conflicts:
            status, reason = (
                "needs_information",
                "The recorded client positions conflict and need clarification.",
            )
        elif live:
            status, reason = "needs_information", live[0]
        elif needs:
            status, reason = (
                "waiting",
                "Awaiting the outstanding information or your direction to resume.",
            )
        elif stale or (thread.assessed and "review_current" not in thread.assessed):
            status, reason = (
                "needs_review",
                "The assessment needs review against the current instructions.",
            )
        elif not thread.posture.resolved:
            status, reason = (
                "not_assessed",
                "The client's position on this dispute is not yet established.",
            )
        elif missing or "review_current" not in thread.assessed:
            status, reason = "not_assessed", "The review of this dispute has not been completed."
        else:
            status, reason = (
                "reviewed",
                "Reviewed on the available record; this does not close the matter.",
            )
        rows.append(
            {
                "thread_id": thread.id,
                "label": thread.label,
                "status": status,
                "next_need": reason,
                "open_needs": list(needs),
                "missing_assessments": list(missing),
            }
        )

    # Unworked disputes get a turn before repeating a standing request. A
    # current deadline gap retains the existing gap vocabulary's priority.
    def priority(row):
        thread = matter.thread(row["thread_id"])
        urgent = any(
            _value(g, "kind") in ("deadline",)
            or getattr(_value(g, "kind"), "value", "") == "deadline"
            for g in thread.gaps
        )
        return (
            0 if urgent else 1,
            {"not_assessed": 0, "needs_review": 1, "needs_information": 2}.get(row["status"], 3),
        )

    available = [r for r in rows if r["status"] not in ("reviewed", "waiting", "paused")]
    available.sort(key=priority)
    # An explicit request to move on is an override, not permission to mark
    # the current dispute complete. Never choose the same blocked item again.
    if after_thread_id:
        available = [r for r in available if r["thread_id"] != after_thread_id]
    complete = bool(rows) and all(r["status"] == "reviewed" for r in rows)
    return {
        "disputes": rows,
        "review_complete": complete,
        "state": "not_assessed"
        if not rows
        else "reviewed"
        if complete
        else "open"
        if available
        else "waiting",
        "next_thread_id": available[0]["thread_id"] if available else None,
        "matter_closed": False,
    }


def context(matter) -> str:
    agenda = project(matter)
    return "\n".join(
        f"{r['thread_id']}: {r['label']} — {r['status']}; {r['next_need']}"
        for r in agenda["disputes"]
    )


def last_focus(matter):
    """The last released substantive focus, not a label guess or list order."""
    for receipt in reversed(matter.turn_receipts):
        for row in receipt.answer.get("elements", ()):
            if row.get("kind") in ("action", "finding", "question"):
                tid = row.get("thread")
                if tid and matter.thread(tid) is not None:
                    return tid
    return None
