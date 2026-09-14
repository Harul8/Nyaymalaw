"""REOPEN ONLY WHAT CHANGED. BK-55-AC5. P28.

    from nm.core import reassessment as ra

IT ADDS NO FRESHNESS SYSTEM, AND THAT IS THE POINT
-----------------------------------------------------
P18 already built one. `nm.core.dependency` holds the ledger: `Node` with what
it `rests_on`, `Currency`, `closure` for the transitive reach of a change, and
`invalidate` to mark what a move reached. A second traversal here would be the
§4 defect on the most expensive possible subject -- two answers to *is this
still true*, disagreeing, with the advocate acting on whichever one the screen
happened to show.

So this module does exactly two things:

1. It puts ADVICE and DECISIONS into that ledger as nodes, so the machinery
   that already knows a corrected fact reaches a limitation also knows it
   reaches the recommendation drawn from it, and the decision taken on that
   recommendation.
2. It answers the one question the ledger cannot: a decision whose advice has
   moved must not keep reading as current approval.

WHY A DECISION RESTS ON AN ADVICE VERSION
-------------------------------------------
`AdviceDecision.advice_version` exists for this. A decision taken against
version 3 and displayed after version 4 was derived is a decision about
something the advocate can no longer see -- and the dangerous half is not that
it is stale, it is that it still says ACCEPTED. `stale_decisions` reports it
with the reason; nothing deletes it, because the history is the record.

WHAT IS DELIBERATELY NOT REOPENED
-----------------------------------
Everything the closure does not reach. `closure` walks from the moved inputs
outward, so a conclusion that never rested on the corrected fact stays
available and is not re-derived -- BK-55-AC5's *visibly reopens ONLY the work
needed*. Reopening the file because one date changed is the behaviour that
teaches an advocate to ignore staleness warnings.
"""
from __future__ import annotations

from nm.core.dependency import (
    Currency,
    InputKind,
    Ledger,
    Node,
    Rest,
    invalidate,
)
from nm.domain.advice_decision import AdviceDecision
from nm.domain.spoken import dispute
from nm.domain.text import blank

#: How an advice node is named in the ledger. ONE SPELLING, here, because a
#: key composed at two call sites is two keys the first time one is changed.
ADVICE_PREFIX = "advice"
DECISION_PREFIX = "decision"


def advice_node_name(thread_id: str) -> str:
    return f"{ADVICE_PREFIX}:{thread_id}"


def decision_node_name(decision_id: str) -> str:
    return f"{DECISION_PREFIX}:{decision_id}"


def record_advice(ledger: Ledger, *, thread_id: str, position: str,
                  rests_on: tuple[Rest, ...], at: str = "",
                  reason: str = "", label: str = "") -> Ledger:
    """Put this thread's recommendation into the ledger as a derived node.

    `rests_on` is what the advice actually used -- the facts, premises and
    authorities the turn read. A node with nothing recorded is forced to
    NOT_ESTABLISHED by `Node.__post_init__` rather than reading as current,
    which is the right answer: advice whose inputs nobody recorded cannot be
    certified fresh, and it must not be certified fresh by omission.
    """
    from nm.core.dependency import record

    return record(ledger, Node(
        name=advice_node_name(thread_id),
        value=position or "no position",
        shown=f"the recommendation on {dispute(label)}",
        rests_on=rests_on, computed_at=at,
        reason=reason or "the recommendation derived on this turn"))


def record_decision(ledger: Ledger, decision: AdviceDecision, *,
                    thread_id: str, at: str = "",
                    label: str = "") -> Ledger:
    """Put a decision into the ledger, resting on the advice it decided.

    THE EDGE IS `InputKind.DERIVED` ON THE ADVICE NODE, which is what makes
    the reach transitive: a corrected fact moves the advice, and the advice
    moving moves the decision, without this module walking anything itself.
    """
    from nm.core.dependency import record

    return record(ledger, Node(
        name=decision_node_name(decision.decision_id),
        value=decision.disposition.value,
        shown=(f"the decision to {decision.disposition.value} the advice on "
               f"{dispute(label)}"),
        rests_on=(Rest(kind=InputKind.DERIVED,
                       id=advice_node_name(thread_id),
                       version=1),),
        computed_at=at or decision.decided_at,
        reason=decision.because or "recorded without a stated reason"))


def reopen(ledger: Ledger, moved: tuple[Rest, ...], *, reason: str,
           at: str = "") -> tuple[Ledger, tuple[str, ...]]:
    """Mark what the change reached, and return the names, using P18's closure.

    IT IS A PASS-THROUGH, and the first version was not: it called `closure`
    itself and then `invalidate`, which computes the same closure internally.
    Two computations of one reach is the second copy §4 asks about -- and it
    was wrong as well as duplicated, because `invalidate` already returns the
    affected names alongside the new ledger. What this adds is nothing, which
    is the intended amount.
    """
    return invalidate(ledger, moved, reason=reason, at=at)


def stale_decisions(ledger: Ledger,
                    decisions: tuple[AdviceDecision, ...],
                    ) -> tuple[tuple[AdviceDecision, str], ...]:
    """Every decision whose advice has moved, with why. BK-55-AC5's last rule.

    A stale decision KEEPS ITS RECORD and loses its current-approval label.
    Deleting it would destroy the answer to *what did we decide, and when*,
    which is the question a decision record exists for; leaving it labelled
    current would let an acceptance of advice nobody can still see read as an
    acceptance of the advice on screen.

    Superseded decisions are skipped: they are already not current, and
    reporting them again would bury the ones that just became stale.
    """
    out: list[tuple[AdviceDecision, str]] = []
    by_name = {node.name: node for node in ledger.nodes}
    for decision in decisions:
        if not decision.is_current or not decision.disposition.is_decided:
            continue
        node = by_name.get(decision_node_name(decision.decision_id))
        if node is None:
            out.append((decision, (
                "this decision is not recorded in the dependency ledger, so "
                "nothing would notice if the advice it rests on moved")))
            continue
        if node.currency is not Currency.CURRENT:
            out.append((decision, node.stale_because or (
                "the advice this decision rests on has moved")))
    return tuple(out)


def reopened_report(ledger: Ledger, reached: tuple[str, ...]) -> dict:
    """WHAT NEEDS RECONSIDERATION AND WHY, and what deliberately does not.

    Both halves are served. An advocate shown only the stale list cannot tell
    whether the rest was checked and held, or never looked at -- and that is
    the difference between a product they trust and one whose warnings they
    learn to click past.
    """
    by_name = {node.name: node for node in ledger.nodes}
    reopened = []
    for name in reached:
        node = by_name.get(name)
        reopened.append({
            "name": name,
            "shown": node.label if node else name,
            "why": (node.stale_because if node and node.stale_because
                    else "an input it rests on moved"),
            "usable": bool(node.currency.usable) if node else False,
        })
    untouched = [
        {"name": node.name, "shown": node.label}
        for node in ledger.nodes
        if node.name not in set(reached) and node.currency is Currency.CURRENT]
    return {
        "reopened": reopened,
        "still_current": untouched,
        "note": (f"{len(reopened)} conclusion(s) rest on what moved and are "
                 f"reopened; {len(untouched)} did not and are unchanged"),
    }


def rests_for_facts(fact_ids: tuple[str, ...],
                    versions: dict[str, int] | None = None) -> tuple[Rest, ...]:
    """Build the `Rest` tuple for a set of corrected facts.

    A helper rather than a mechanism: the shape of a `Rest` belongs to P18 and
    this only saves every caller writing the same comprehension. Blank ids are
    dropped rather than recorded, because a dependency on nothing is the state
    `Node.__post_init__` already refuses to certify.
    """
    seen = versions or {}
    return tuple(Rest(kind=InputKind.FACT, id=fid, version=seen.get(fid, 1))
                 for fid in fact_ids if not blank(fid))
