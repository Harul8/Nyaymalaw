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

    from nm.core.deadlines import passed as _passed
    from nm.core.deadlines import upcoming as _upcoming
    from nm.core.dependency import Ledger

    today = today or forum_today()   # BK-14: the forum's date
    ledger = Ledger.from_stored(currency)
    if deadlines is None:
        # NOT ASSESSED, said as a value. Not the same as a file with no
        # deadlines, and the two must not render alike.
        window = {"next_deadline": None,
                  "next_deadline_status": "not_assessed",
                  "passed_deadlines": None,
                  "stale_deadline": None,
                  "next_deadline_currency": None}
    else:
        ours = tuple(d for d in deadlines if d.thread == thread.id)
        judged = {id(d): _currency_of(ledger, thread.id, d) for d in ours}
        live_rows = tuple(d for d in ours if judged[id(d)][0] != "stale")
        not_live = tuple(d for d in ours if judged[id(d)][0] == "stale")
        mine = _upcoming(live_rows, today)
        gone = _passed(live_rows, today)
        window = {
            # A2.5. THE NEAREST LIVE DEADLINE, and the passed ones separately.
            # This was hard-coded `None`, so the clause forbidding a passed
            # deadline from being dropped was a rule about a field that never
            # held anything.
            "next_deadline": (mine[0].on.isoformat() if mine else None),
            "next_deadline_status": (
                mine[0].status(today).value if mine
                # NOTHING LIVE, BUT NOT NOTHING. The state names why the
                # nearest is missing rather than reading as a clean sheet.
                else judged[id(not_live[0])][0] if not_live
                else "none_on_this_thread"),
            # PASSED ROWS ARE THEIR OWN LIST. Merging them into what is
            # upcoming buries the thing that can no longer be done among the
            # things that still can, and the advocate scans the second for work.
            "passed_deadlines": [
                {"on": d.on.isoformat(), "action": d.action,
                 "consequence": d.consequence, "days_ago": -d.days(today)}
                for d in gone],
            # THE WINDOW THAT STOPPED COUNTING, as a DATE and nothing more.
            # The advocate recognises the number they were working to; WHY it
            # stopped is reasoning, and reasoning is what A2 keeps off the
            # board -- it is on the cover and the case file, with the ledger's
            # own words. A2's test enumerates the board's keys, and this one
            # was admitted as a status field on that argument.
            "stale_deadline": (not_live[0].on.isoformat()
                               if not_live and not_live[0].on else None),
            # THE LABEL ON THE ROW THAT LEADS, so `not_established` is seen
            # even while it is allowed to lead. Three words; no reasoning.
            "next_deadline_currency": (judged[id(mine[0])][0] if mine
                                       else None),
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

    from nm.core.deadlines import upcoming as _upcoming
    from nm.core.dependency import Ledger

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
        register = None if registers is None else registers.get(m.id, ())
        # ONLY CURRENT ROWS COMPETE FOR THE NEAREST DEADLINE (P18). The same
        # judgement the thread board makes, asked of the same ledger; a stale
        # window at the top of the matter list is the corrected date at the
        # top of the advocate's day.
        ledger = Ledger.from_stored(getattr(m, "dependencies", None))
        stale_rows = 0
        if register is not None:
            judged = [(d, _currency_of(ledger, d.thread, d)[0])
                      for d in register]
            stale_rows = sum(1 for _, state in judged if state == "stale")
            register = tuple(d for d, state in judged if state != "stale")
        live = () if register is None else _upcoming(tuple(register), today)
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
            "next_deadline": live[0].on.isoformat() if live else None,
            "next_deadline_status": (
                "not_assessed" if register is None
                else live[0].status(today).value if live
                else "stale" if stale_rows
                else "none_on_this_matter"),
            # NAMED, so a list whose nearest deadline vanished says why.
            "stale_deadlines": stale_rows,
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
    if any(getattr(t, "blocked_reason", None) for t in matter.threads):
        return "blocked"
    return "advising"


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
    from nm.domain.engagement import from_stored as engagement_from_stored

    engaged = engagement_from_stored(matter.engagement)
    commission = Commission.from_stored(matter.commission)

    client = (engaged.client if engaged and engaged.client else "")
    posture = Role.UNKNOWN
    for thread in matter.threads:
        role = getattr(thread, "our_role", None)
        if isinstance(role, Role) and role is not Role.UNKNOWN:
            posture = role
            break

    deadline_state = "not_assessed"
    deadline_said = "no deadline has been assessed on this matter"
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
        "posture": posture.value,
        "posture_state": ("recorded" if posture is not Role.UNKNOWN
                          else "not_established"),
        "stage": _stage_of(matter),
        "last_activity": getattr(matter, "touched_at", "") or None,
        "last_activity_state": ("recorded" if getattr(matter, "touched_at", "")
                                else "not_recorded"),
        "deadline_assessment": deadline_state,
        "deadline_said": deadline_said,
        "commission": commission.as_dict() if commission else None,
        "commission_state": ("recorded" if commission else "not_recorded"),
        "thread_count": len(matter.threads),
        # WHAT ON THIS FILE IS STILL CURRENT (P18). One block, read from the
        # ledger the turn writes; the same names the board uses.
        "currency": currency_projection(matter),
    }


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
                "nodes": [], "history": [], "stale": []}
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
