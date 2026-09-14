"""A CORRECTION REOPENS WHAT IT REACHED, AND NOTHING ELSE. BK-55-AC5. P28.

WHAT THIS DEFENDS
-------------------
Two failures, and they are opposites:

* THE DECISION THAT OUTLIVES ITS ADVICE. An acceptance recorded against
  version 3, still labelled current after version 4 was derived. The advocate
  reads APPROVED beside advice the approval was never given for.
* THE FILE THAT REOPENS ITSELF. One corrected date, and every conclusion on
  the matter is marked stale. That is not caution -- it is the behaviour that
  teaches an advocate to click past staleness warnings, after which the one
  that mattered goes past too.

NO SECOND FRESHNESS SYSTEM. Every assertion here runs through P18's
`nm.core.dependency` -- its `closure`, its `Currency`, its `invalidate`. If
P28 had built its own traversal there would be two answers to *is this still
true*, and the advocate would act on whichever the screen happened to show.
"""
from __future__ import annotations

import pytest
from nm.core import reassessment as ra
from nm.core.dependency import Currency, InputKind, Ledger, Node, Rest
from nm.domain.advice_decision import AdviceDecision, Disposition, supersede

pytestmark = pytest.mark.class_a


def _decision(decision_id="d1", disposition=Disposition.ACCEPT) -> AdviceDecision:
    return AdviceDecision(
        decision_id=decision_id, disposition=disposition, decided_by="adv_1",
        decided_at="2026-09-13", advice_version="v1",
        scope="the recovery thread", owner="adv_1",
        review_trigger="if the defence pleads limitation")


def _file() -> tuple[Ledger, AdviceDecision]:
    """Two threads. Only the first rests on the delivery fact."""
    led = ra.record_advice(
        Ledger(), thread_id="t1", position="sue for the price",
        rests_on=ra.rests_for_facts(("f_delivery",)), at="2026-09-13")
    led = ra.record_advice(
        led, thread_id="t2", position="defend the trespass claim",
        rests_on=ra.rests_for_facts(("f_possession",)), at="2026-09-13")
    decision = _decision()
    led = ra.record_decision(led, decision, thread_id="t1")
    return led, decision


# ================================ 1. the reach is transitive and bounded =====

def test_a_corrected_fact_reaches_the_advice_and_the_decision_taken_on_it():
    """THE TRANSITIVE EDGE. The fact moves the advice; the advice moving moves
    the decision. P28 walks nothing itself -- `InputKind.DERIVED` on the advice
    node is what carries it, and P18's closure does the rest."""
    led, decision = _file()
    led, reached = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                             reason="the advocate corrected the delivery date",
                             at="2026-09-14")
    assert ra.advice_node_name("t1") in reached
    assert ra.decision_node_name(decision.decision_id) in reached


def test_an_independent_conclusion_stays_available_and_is_not_reopened():
    """*visibly reopens ONLY the work needed.* The second thread never rested
    on the corrected fact, so it is untouched -- not re-stamped, not
    re-timestamped, not marked stale."""
    led, _ = _file()
    before = next(n for n in led.nodes if n.name == ra.advice_node_name("t2"))
    led, reached = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                             reason="the advocate corrected the delivery date",
                             at="2026-09-14")
    assert ra.advice_node_name("t2") not in reached
    after = next(n for n in led.nodes if n.name == ra.advice_node_name("t2"))
    assert after == before, (
        "the untouched thread was rewritten; every independent conclusion now "
        "reports that something happened to it")


def test_the_report_says_what_reopened_and_what_did_not():
    """An advocate shown only the stale list cannot tell whether the rest was
    checked and held or never looked at."""
    led, _ = _file()
    led, reached = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                             reason="the advocate corrected the delivery date",
                             at="2026-09-14")
    report = ra.reopened_report(led, reached)
    assert len(report["reopened"]) == 2
    assert [r["name"] for r in report["still_current"]] == [
        ra.advice_node_name("t2")]
    assert all(r["why"] for r in report["reopened"]), (
        "a conclusion was reopened without saying why")


# ============================= 2. a stale decision loses its current label ===

def test_a_decision_whose_advice_moved_is_no_longer_a_current_approval():
    """BK-55-AC5's last rule, and the dangerous half of staleness: the record
    does not merely go out of date, it keeps saying ACCEPTED."""
    led, decision = _file()
    assert ra.stale_decisions(led, (decision,)) == ()

    led, _ = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                       reason="the advocate corrected the delivery date",
                       at="2026-09-14")
    stale = ra.stale_decisions(led, (decision,))
    assert len(stale) == 1
    assert stale[0][0].decision_id == decision.decision_id
    assert stale[0][1], "a decision went stale without a reason"


def test_the_stale_decision_is_kept_and_not_deleted():
    """The history is the record. Deleting it destroys the answer to *what did
    we decide, and when* -- which is what a decision record is for."""
    led, decision = _file()
    led, _ = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                       reason="the advocate corrected the delivery date",
                       at="2026-09-14")
    stale = ra.stale_decisions(led, (decision,))
    assert stale[0][0] == decision, "the decision was altered rather than flagged"


def test_a_decision_nobody_recorded_in_the_ledger_is_reported_not_assumed_fresh():
    """CLAUDE.md §9. A decision the ledger has never seen is not current -- it
    is unwatched, and nothing would notice if its advice moved."""
    orphan = _decision("d_orphan")
    stale = ra.stale_decisions(Ledger(), (orphan,))
    assert len(stale) == 1
    assert "not recorded in the dependency ledger" in stale[0][1]


def test_a_superseded_decision_is_not_reported_again():
    """It is already not current. Reporting it would bury the ones that just
    became stale."""
    led, decision = _file()
    led, _ = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                       reason="the advocate corrected the delivery date",
                       at="2026-09-14")
    withdrawn = supersede(decision, by="d2")
    assert ra.stale_decisions(led, (withdrawn,)) == ()


def test_an_undecided_record_is_not_reported_stale():
    """There is nothing to go stale. Silence does not rot."""
    led, _ = _file()
    led, _ = ra.reopen(led, ra.rests_for_facts(("f_delivery",)),
                       reason="corrected", at="2026-09-14")
    undecided = AdviceDecision(decision_id="d0")
    assert ra.stale_decisions(led, (undecided,)) == ()


# ================================ 3. no second freshness system ==============

def test_p28_reuses_p18s_ledger_and_defines_no_traversal_of_its_own():
    """THE STRUCTURAL ASSERTION, and it is the packet's governing constraint.

    Two answers to *is this still true* is the §4 defect on the most expensive
    possible subject. `reopen` is a pass-through to `invalidate`; if a closure
    walk ever appears in this module, the two will disagree the first time one
    is changed.
    """
    import inspect

    # THE RULE IS ABOUT COMPUTING THE REACH, not about touching the ledger.
    # A first version of this asserted that the module never iterates
    # `ledger.nodes`, and it failed on `stale_decisions` building a name -> node
    # index -- which is a LOOKUP. Forbidding lookups would have pushed the
    # index into another module for no reason, and the rule would then be
    # protecting the wrong thing.
    assert "closure" not in {n for n in dir(ra) if not n.startswith("__")}, (
        "nm.core.reassessment imports `closure`; the transitive reach has one "
        "owner and a second caller is a second answer waiting to disagree")

    body = inspect.getsource(ra.reopen).split('"""')[-1]
    assert "invalidate(" in body, "reopen no longer delegates to P18"
    assert "closure(" not in body, (
        "reopen recomputes a reach that `invalidate` already returns")

    # AND THE LEDGER IS P18'S, not a local re-declaration of one.
    assert ra.Ledger.__module__ == "nm.core.dependency"
    assert ra.Currency.__module__ == "nm.core.dependency"


def test_advice_with_no_recorded_inputs_cannot_be_certified_current():
    """P18's own rule, inherited rather than restated: a node that names
    nothing it rests on is NOT_ESTABLISHED, not CURRENT. Advice whose inputs
    nobody recorded must not be certified fresh by omission."""
    led = ra.record_advice(Ledger(), thread_id="t9", position="sue",
                           rests_on=(), at="2026-09-13")
    node = next(n for n in led.nodes if n.name == ra.advice_node_name("t9"))
    assert node.currency is not Currency.CURRENT
    assert node.stale_because


def test_the_reach_terminates_on_a_ring():
    """A derived value resting on itself is a defect in whatever recorded it,
    and a closure that hung on one would take the product down rather than
    reporting the ring. Inherited from P18 and asserted here because P28 is
    what introduces derived-on-derived edges in bulk."""
    from nm.core.dependency import record
    led = Ledger()
    led = record(led, Node(name="a", value="1", shown="a",
                           rests_on=(Rest(kind=InputKind.DERIVED, id="b",
                                          version=1),)))
    led = record(led, Node(name="b", value="1", shown="b",
                           rests_on=(Rest(kind=InputKind.DERIVED, id="a",
                                          version=1),)))
    led, reached = ra.reopen(led, (Rest(kind=InputKind.DERIVED, id="a",
                                        version=1),),
                             reason="a ring", at="2026-09-14")
    assert set(reached) == {"a", "b"}
