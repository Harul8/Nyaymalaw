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

from nm.core import briefing as _briefing
from nm.core import retention as _retention
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
    from nm.core.deadlines import DeadlineKind
    from nm.core.dependency import Currency, names_for, presentable

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
    from nm.core.deadlines import DeadlineStatus, RegisterRead, passed, register, upcoming
    from nm.core.dependency import Ledger

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
    }


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
    rows = nearest_first([_thread_row(t, deadlines, today,
                                      currency=getattr(matter, "dependencies", None))
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
        window = _deadline_window(
            register, today, currency=getattr(m, "dependencies", None))
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
        # WHAT ON THIS FILE IS STILL CURRENT (P18). One block, read from the
        # ledger the turn writes; the same names the board uses.
        "currency": currency_projection(matter),
        # THE LEGAL PREMISES EACH THREAD'S LIMITATION RESTS ON (P22), and
        # whether the cover, the register and the answer are about the SAME
        # premise version. A mismatch is disclosed as `inconsistent`, never
        # smoothed over -- BK-35-AC2's whole point is that they share one
        # version or say precisely where they do not.
        "premises": premises_projection(matter),
        # WHAT THE RELIEF IS WORTH, per thread (P23/BK-70). Whether a remedy
        # that serves the objective is available, substantial, timely and
        # enforceable -- and its proportionality, stated alongside and never a
        # veto. `no_useful_relief` where the merits may hold but nothing on the
        # file delivers; `not_assessed` where nobody looked.
        "relief": relief_projection(matter),
        # INTAKE READINESS (P24). On the cover so it survives across turns and a
        # restart -- readiness is not turn completion, and a paused need waits on
        # its resume trigger rather than being forgotten.
        "briefing": _briefing.block(matter),
        # P33. WHAT IS BEING KEPT OR ERASED, and what is still outstanding.
        # `outstanding` travels with the state rather than being left for the
        # reader to infer from two counts that do not add up -- an advocate
        # told "not complete" and not told WHICH copy cannot chase it.
        "retention": [
            {**_retention.projection(r), "outstanding": list(r.completion_problems())}
            for r in _retention.rows(matter)],
    }


def premises_projection(matter: Matter) -> dict:
    """Per thread: the three premises with basis, source and review state, and
    a consistency verdict against the register.

    THREE STATES for the file: `established` (every thread's premises are
    stated or attributed), `conditional` (a thread's accrual was inferred),
    `not_assessed` (no thread has computed a limitation). `inconsistent`
    overrides them where a register row's premise digest does not match the
    thread's own premises -- which is the cover and the register disagreeing
    about the law, and it must be seen.
    """
    from nm.core.premise import Premises

    threads = []
    any_conditional = False
    any_computed = False
    inconsistent = []
    for t in matter.threads:
        rows = getattr(t, "premises", ()) or ()
        if not rows:
            threads.append({"thread_id": t.id, "thread": t.label,
                            "state": "not_assessed", "premises": []})
            continue
        any_computed = True
        digest = Premises.from_stored(rows).digest()
        conditional = any(p.get("basis") == "inferred" for p in rows)
        any_conditional = any_conditional or conditional
        # THE REGISTER ROWS FOR THIS THREAD, and their premise digest.
        reg_digests = {getattr(d, "premise_digest", "")
                       for d in (t.deadlines or ())
                       if getattr(d, "thread", None) == t.id
                       and getattr(d, "premise_digest", "")}
        mismatch = bool(reg_digests) and digest not in reg_digests
        if mismatch:
            inconsistent.append(t.id)
        threads.append({
            "thread_id": t.id, "thread": t.label,
            "state": "conditional" if conditional else "established",
            "digest": digest,
            "consistent_with_register": not mismatch,
            "premises": [{
                "kind": p.get("kind"), "statement": p.get("statement"),
                "basis": p.get("basis"), "source": p.get("source"),
                "review_state": p.get("review_state", "not_assessed"),
                "reviewed_by": p.get("reviewed_by", ""),
                "alternatives": p.get("alternatives", [])} for p in rows]})
    state = ("inconsistent" if inconsistent
             else "conditional" if any_conditional
             else "established" if any_computed
             else "not_assessed")
    return {"state": state, "threads": threads,
            "inconsistent_threads": inconsistent,
            "said": ("a thread's cover and deadline register rest on different "
                     "premise versions" if inconsistent
                     else "a thread's limitation rests on a premise the product "
                          "inferred; confirm it before relying on the date"
                     if any_conditional
                     else "every computed limitation rests on an attributed or "
                          "stated legal position" if any_computed
                     else "no limitation has been computed on this file")}


def relief_projection(matter: Matter) -> dict:
    """Per thread: whether the relief that serves the objective can be obtained,
    enforced and is worth the cost. BK-70 / E2.

    THREE STATES for the file, and proportionality is DISCLOSED, never a veto.
    `serveable` where a remedy delivers; `no_useful_relief` where the merits
    may hold and nothing on the file delivers (unavailable, hollow, late or
    unenforceable) -- the state this exists to make visible; `not_assessed`
    where nobody has looked, which is not the same as nothing worth pursuing.
    A disproportionate route is listed under `disproportionate` and stays in
    `useful`: the advocate is told the cost, and left to decide (E3's NEVER).
    """
    from nm.core import relief as relief_mod

    threads = []
    any_serveable = False
    any_no_useful = False
    for t in matter.threads:
        reliefs = relief_mod.reliefs_from_stored(getattr(t, "reliefs", ()) or ())
        obj = relief_mod.Objective.from_stored(getattr(t, "objective", None))
        if not reliefs and obj is None:
            threads.append({"thread_id": t.id, "thread": t.label,
                            "state": "not_assessed", "objective": None,
                            "reliefs": []})
            continue
        pos = relief_mod.assess(obj, reliefs)
        if pos.state is relief_mod.ReliefState.SERVEABLE:
            any_serveable = True
        elif pos.state in (relief_mod.ReliefState.DEFEATED,
                           relief_mod.ReliefState.CONTINGENT):
            any_no_useful = True
        threads.append({
            "thread_id": t.id, "thread": t.label,
            "state": pos.state.value,
            "objective": ({"statement": obj.statement, "basis": obj.basis.value}
                          if obj is not None else None),
            "digest": pos.digest,
            "useful": list(pos.useful),
            "defeated": [{"remedy": r, "coordinate": c, "why": w}
                         for r, c, w in pos.defeated],
            "contingent": [{"remedy": r, "coordinate": c, "why": w}
                           for r, c, w in pos.contingent],
            "disproportionate": [{"remedy": r, "why": w}
                                 for r, w in pos.disproportionate],
            "reliefs": [{
                "remedy": r.remedy, "forum": r.forum,
                "availability": r.availability.value, "value": r.value.value,
                "timing": r.timing.value,
                "enforceability": r.enforceability.value,
                "proportionality": r.proportionality.value,
                "basis": r.basis.value, "reason": r.reason,
            } for r in pos.reliefs],
        })
    state = ("no_useful_relief" if any_no_useful
             else "serveable" if any_serveable else "not_assessed")
    return {"state": state, "threads": threads,
            "said": ("a remedy that would serve the objective is not available, "
                     "hollow, late or unenforceable on at least one thread; the "
                     "recommendation reflects it" if any_no_useful
                     else "a remedy that delivers the objective is available"
                     if any_serveable
                     else "no relief has been assessed on this file")}


def currency_projection(matter: Matter) -> dict:
    """Every recorded conclusion, its currency, and its history. BK-65-AC1.

    THREE STATES AT THE TOP, and the third is a file with no ledger at all:
    `not_assessed` is a record written before P18 or a matter no turn has
    derived on, and it must not render as `current` -- which is what an
    empty list of stale nodes would say if the state were derived from it.

    THE HISTORY CARRIES `was`, `now`, the reason AND the versions that moved,
    so the advocate sees the old date and the corrected one and who changed
    it (EVAL-010) rather than a value that is different from the one they
    remember with nothing saying why.
    """
    from nm.core.dependency import Ledger

    ledger = Ledger.from_stored(getattr(matter, "dependencies", None))
    # NO NODES IS NOT ASSESSED, whatever inputs are tracked. The first draft
    # tested `not nodes and not tracked` and a matter whose turn had observed
    # its facts and concluded nothing reported `current` -- an empty list of
    # stale conclusions read as a certificate, which is the S1 shape this
    # block exists to refuse. Found by the test written for it.
    if not ledger.nodes:
        return {"state": "not_assessed",
                "said": ("no conclusion on this file has a recorded "
                         "dependency yet; currency cannot be certified"),
                "nodes": [], "history": [], "stale": [],
                # Inputs exist before the first conclusion does. Omitting
                # them here made the full dependency endpoint lose an
                # attached authority precisely while currency was still
                # unassessed. Qualify the conclusion state without shrinking
                # the underlying ledger population.
                "tracked": [t.as_dict() for t in ledger.tracked]}
    stale = ledger.stale()
    return {
        "state": "stale" if stale else "current",
        "said": (f"{len(stale)} conclusion(s) on this file are not current"
                 if stale else
                 "every recorded conclusion is current against the inputs "
                 "it was computed from"),
        "nodes": [{**n.as_dict(),
                   "source_versions": list(ledger.source_versions(n.name))}
                  for n in ledger.nodes],
        "stale": [{"name": n.name, "shown": n.label, "value": n.value,
                   "currency": n.currency.value, "because": n.stale_because,
                   "rework_exhausted": n.rework_exhausted}
                  for n in stale],
        "history": [r.as_dict() for r in ledger.history],
        "tracked": [t.as_dict() for t in ledger.tracked],
    }
