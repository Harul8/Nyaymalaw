"""Persisting handovers, closure and re-entry. BK-33-AC2, BK-39, BK-59. P32.

`nm.domain.handover` and `nm.domain.closure` hold the state and the rules; this
holds the persistence shape, the served projections and re-entry.

RE-ENTRY READS THE FILE, NOT A CACHE
--------------------------------------
BK-33-AC2 asks that re-entry restore the selected matter *from the
authoritative file without cross-matter state leakage*. `re_entry` therefore
takes one matter and reads only it: there is no second argument it could mix in
and no store lookup that could return a sibling. The leak this refuses is the
one that produces the worst possible outcome in this product -- another
client's material rendered under this client's name.

EVENTS GO THROUGH P18's LEDGER
--------------------------------
BK-59-AC1 asks that a material event invalidate or recompute affected
obligations *without rewriting past issued records*. Both halves are already
built: `nm.core.dependency.invalidate` marks exactly the closure a change
reaches and keeps the prior state as a `Revision`. `record_event` hands it the
moved inputs and returns what it reached. Nothing here walks the graph.
"""
from __future__ import annotations

from dataclasses import replace

from nm.core.dependency import InputKind, Ledger, Rest, invalidate
from nm.domain.closure import (
    ClosureRecord,
    Lifecycle,
    Obligation,
    reopen_checks,
)
from nm.domain.handover import (
    Assessed,
    CaseSummary,
    Handover,
    HandoverState,
    Section,
)
from nm.domain.text import clean


def _enum(kind, value, fallback):
    try:
        return kind(value)
    except (ValueError, KeyError):
        return fallback


# ------------------------------------------------------------- handovers ---

def handover_as_dict(h: Handover) -> dict:
    return {"schema": 1, "handover_id": h.handover_id, "matter_id": h.matter_id,
            "from_actor": h.from_actor, "to_actor": h.to_actor,
            "offered_at": h.offered_at, "summary_version": h.summary_version,
            "state": h.state.value, "accepted_at": h.accepted_at,
            "declined_because": h.declined_because,
            "withdrawn_at": h.withdrawn_at, "outstanding": list(h.outstanding)}


def handover_from_dict(value: dict) -> Handover:
    """An unreadable state falls to OFFERED.

    NOT to ACCEPTED: a corrupt row must not report that somebody took
    responsibility for work they have never seen.
    """
    return Handover(
        handover_id=clean(str(value.get("handover_id") or "?")),
        matter_id=clean(str(value.get("matter_id") or "?")),
        from_actor=str(value.get("from_actor") or "?"),
        to_actor=str(value.get("to_actor") or "?"),
        offered_at=str(value.get("offered_at") or "?"),
        summary_version=int(value.get("summary_version") or 1),
        state=_enum(HandoverState, value.get("state"), HandoverState.OFFERED),
        accepted_at=str(value.get("accepted_at") or ""),
        declined_because=str(value.get("declined_because") or ""),
        withdrawn_at=str(value.get("withdrawn_at") or ""),
        outstanding=tuple(str(x) for x in (value.get("outstanding") or ())))


def handover_rows(matter) -> tuple[Handover, ...]:
    return tuple(handover_from_dict(r)
                 for r in (getattr(matter, "handovers", ()) or ())
                 if isinstance(r, dict))


def put_handover(existing: tuple[Handover, ...], h: Handover) -> tuple[Handover, ...]:
    return tuple(x for x in existing if x.handover_id != h.handover_id) + (h,)


def handover_projection(h: Handover) -> dict:
    """The served handover. WHO OWNS THE WORK RIGHT NOW travels with it.

    A consumer that had to work out ownership from the state would work it out
    differently in two places, and one of them would be wrong on the day a
    handover was declined.
    """
    return {
        "handover_id": h.handover_id, "from_actor": h.from_actor,
        "to_actor": h.to_actor, "state": h.state.value,
        "offered_at": h.offered_at, "accepted_at": h.accepted_at,
        "declined_because": h.declined_because,
        "outstanding": list(h.outstanding),
        "responsibility_moved": h.state.responsibility_moved,
        "owner_of_outstanding": h.owner_of_outstanding(),
        "unowned": list(h.unowned_after()),
    }


# --------------------------------------------------------------- closure ---

def closure_as_dict(c: ClosureRecord) -> dict:
    return {
        "schema": 1, "matter": c.matter, "closed_by": c.closed_by,
        "closed_at": c.closed_at, "money": dict(c.money),
        "originals": [dict(o) for o in c.originals],
        "work_product": dict(c.work_product),
        "continuing_obligations": [
            {"what": o.what, "until": o.until, "owner": o.owner,
             "resolved": o.resolved, "transferred_to": o.transferred_to}
            for o in c.continuing_obligations],
        "retention": c.retention,
        "closure_summary_sent_at": c.closure_summary_sent_at,
        "lessons": dict(c.lessons), "lifecycle": c.lifecycle.value}


def closure_from_dict(value: dict) -> ClosureRecord:
    """An unreadable lifecycle falls to OPEN.

    A matter whose state nobody can read is LIVE, not closed: treating it as
    closed would hide whatever is still owed inside it.
    """
    return ClosureRecord(
        matter=clean(str(value.get("matter") or "?")),
        closed_by=str(value.get("closed_by") or "?"),
        closed_at=str(value.get("closed_at") or ""),
        money=dict(value.get("money") or {}),
        originals=tuple(dict(o) for o in (value.get("originals") or ())
                        if isinstance(o, dict)),
        work_product=dict(value.get("work_product") or {}),
        continuing_obligations=tuple(
            Obligation(what=str(o.get("what") or "?"),
                       until=str(o.get("until") or ""),
                       owner=str(o.get("owner") or ""),
                       resolved=bool(o.get("resolved")),
                       transferred_to=str(o.get("transferred_to") or ""))
            for o in (value.get("continuing_obligations") or ())
            if isinstance(o, dict)),
        retention=str(value.get("retention") or ""),
        closure_summary_sent_at=str(value.get("closure_summary_sent_at") or ""),
        lessons=dict(value.get("lessons") or {}),
        lifecycle=_enum(Lifecycle, value.get("lifecycle"), Lifecycle.OPEN))


def closure_of(matter) -> ClosureRecord | None:
    row = getattr(matter, "closure", None)
    return closure_from_dict(row) if isinstance(row, dict) and row else None


def closure_projection(c: ClosureRecord) -> dict:
    return {
        "matter": c.matter, "lifecycle": c.lifecycle.value,
        "closed_by": c.closed_by, "closed_at": c.closed_at or "not closed",
        "retention": c.retention or "not decided",
        "complete": c.complete, "blockers": list(c.blockers),
        "continuing_obligations": [
            {"what": o.what, "until": o.until or "no date",
             "owner": o.owner or "nobody", "live": o.is_live,
             "transferred_to": o.transferred_to}
            for o in c.continuing_obligations],
    }


# -------------------------------------------------------------- re-entry ---

def summary_of(matter) -> CaseSummary:
    """Build the handover snapshot from ONE matter's own file.

    Each section reports EMPTY where the file was read and held nothing, and
    NOT_ASSESSED where this product has no answer at all. The difference is
    BK-39-AC2's, and getting it wrong in the generous direction tells a
    receiving advocate there are no authorities when nobody searched.
    """
    def section(items, assessed: bool) -> Section:
        rows = tuple(str(x) for x in items if str(x).strip())
        if not assessed:
            return Section(state=Assessed.NOT_ASSESSED)
        return Section(items=rows,
                       state=Assessed.ASSESSED if rows else Assessed.EMPTY)

    threads = getattr(matter, "threads", ()) or ()
    facts = getattr(matter, "facts", ()) or ()
    return CaseSummary(
        matter=matter.id,
        engagement=section([getattr(matter, "title", "")], True),
        screens=section([], bool(getattr(matter, "screens", ()))),
        threads=section([getattr(t, "label", "") for t in threads], True),
        posture=section(
            [getattr(getattr(t, "posture", None), "side", "") for t in threads],
            bool(threads)),
        chronology=section([getattr(f, "statement", "") for f in facts], True),
        issues=section([], bool(getattr(matter, "issues", ()))),
        theory=section([], bool(threads)),
        proof=section([], False),
        authorities=section([], bool(getattr(matter, "research", ()))),
        deadlines=section([], bool(getattr(matter, "deadlines", ()))),
        decisions=section(
            [str(d.get("disposition", "")) for d in
             (getattr(matter, "advice_decisions", ()) or ())
             if isinstance(d, dict)],
            True),
        reservations=section([], False),
        gaps=section([str(g.get("need", "")) for g in
                      (getattr(matter, "paused_needs", ()) or ())
                      if isinstance(g, dict)], True),
        instruction=str(getattr(matter, "title", "") or ""),
        next_responsibility="",
        version=int(getattr(matter, "version", 1)))


def re_entry(matter) -> dict:
    """What the advocate needs on coming back. BK-33-AC2.

    ONE MATTER, READ ONCE. There is no second matter in scope here and no
    lookup that could return a sibling -- the leak this refuses renders another
    client's material under this client's name, which is the worst outcome this
    product has.
    """
    summary = summary_of(matter)
    closed = closure_of(matter)
    handovers = handover_rows(matter)
    live = [h for h in handovers if h.state is HandoverState.OFFERED]
    return {
        "matter_id": matter.id,
        "version": getattr(matter, "version", 1),
        "lifecycle": (closed.lifecycle.value if closed else Lifecycle.OPEN.value),
        "instruction": summary.instruction or "not recorded",
        "unassessed_sections": list(summary.unassessed()),
        "sections": {name: s.render() for name, s in summary.sections.items()},
        "handover_pending": [handover_projection(h) for h in live],
        "closure": closure_projection(closed) if closed else None,
        "reopen_checks": list(reopen_checks(closed)) if closed else [],
    }


def record_event(ledger: Ledger, *, kind: str, event_id: str, reason: str,
                 at: str = "") -> tuple[Ledger, tuple[str, ...]]:
    """A material event moves what rests on it. BK-59-AC1.

    THE PAST IS NOT REWRITTEN, and that is P18's guarantee rather than one this
    module adds: `invalidate` keeps the prior value as a `Revision` and touches
    nothing outside the closure. This only names the moved input and hands it
    over.
    """
    moved = (Rest(kind=InputKind.FACT, id=event_id, version=1),)
    del kind  # the event's kind is recorded by the caller, not by the ledger
    return invalidate(ledger, moved, reason=reason, at=at)


def with_closure(matter, record: ClosureRecord):
    return replace(matter, closure=closure_as_dict(record),
                   version=matter.version + 1)
