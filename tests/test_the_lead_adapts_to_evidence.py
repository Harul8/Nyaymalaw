"""P46 / BK-91-AC1 and BK-91-AC2 -- the adaptive lead.

WHAT THIS PROVES
------------------
AC1: the lead chooses and revises evidence-driven next actions within the
mandate, with no fixed cognitive sequence and no self-expanded authority, and
reaches a useful completion or an explicit escalation. Its negative control:
decisive contrary evidence after planning, or a premise removed while the plan
is 'complete', reopens the affected work and a frozen plan cannot claim done.

AC2: material claims keep their provenance and epistemic status through adaptive
reasoning; hypotheses are labelled; a SUPPORTED claim is rechecked against the
source on change before it is relied on. Its negative control: invent a date or
authority, promote an allegation to established, or accept a result on a
superseded source -- each is rejected or left explicitly unresolved.

EVAL-031's transformations are driven here: renaming parties consistently and
paraphrasing do NOT change the assessment, while changing the represented side
does. `model_eval` (required by AC1/AC2) is NOT run; nothing here judges a real
model's investigation.
"""
from __future__ import annotations

import pytest
from nm.core import lead
from nm.core.delegation import Ledger
from nm.domain.delegation import (
    Finding,
    Mandate,
    MandateDelta,
    Result,
    ResultStatus,
    Role,
    Task,
)
from nm.domain.lead import Action, EpistemicStatus, Plan

pytestmark = pytest.mark.class_a

SNAP = {"invoice-a": 1, "email-b": 1}


def _allegation(cid, statement, source, subject, by):
    return lead.classify(cid, statement, source, 1, asserted_by_party=True,
                      subject=subject, asserted_by=by)


# ============================ AC2: provenance & status ====================

def test_a_source_is_never_supported_merely_by_existing():
    """AC2. classify yields ALLEGATION or EXTRACTED; a quote and a locator do
    not make a claim SUPPORTED. Only an assessment against a CURRENT version
    does -- and the constructor refuses a SUPPORTED claim with no version, so
    the status cannot be forged onto a sourceless claim."""
    alleged = _allegation("c1", "payment is outstanding", "invoice-a", "paid", "A")
    extracted = lead.classify("c2", "clause 3 says X", "agreement-c", 1,
                           asserted_by_party=False, subject="clause3")
    assert alleged.status is EpistemicStatus.ALLEGATION
    assert extracted.status is EpistemicStatus.EXTRACTED
    assert lead.assess_support(extracted, supported=True, snapshot={"agreement-c": 1}
                            ).status is EpistemicStatus.SUPPORTED


def test_support_is_not_granted_on_a_superseded_version():
    """AC2 negative control. A claim assessed as supported, but resting on a
    version the snapshot has moved past, is NOT promoted -- support against an
    old version is not support of what the file now holds. No invention fills
    the gap; it stays an allegation."""
    c = _allegation("c1", "paid", "invoice-a", "paid", "A")
    assert lead.assess_support(c, supported=True, snapshot={"invoice-a": 2}
                            ).status is EpistemicStatus.ALLEGATION


def test_a_change_invalidates_the_claims_that_rest_on_it_only():
    """AC2 + AC1 negative control. A supported conclusion on invoice-a is
    reverted when invoice-a moves; a conclusion on another source is untouched;
    a recheck need is raised and the plan is un-completed."""
    on_a = lead.assess_support(_allegation("a", "paid", "invoice-a", "paid", "A"),
                            supported=True, snapshot=SNAP)
    on_b = lead.assess_support(_allegation("b", "defective", "email-b", "quality", "B"),
                            supported=True, snapshot=SNAP)
    plan = Plan(1, claims=(on_a, on_b), completed=True)
    after = lead.observe_source_change(plan, "invoice-a", 2)
    by_id = {c.id: c for c in after.claims}
    assert by_id["a"].status is EpistemicStatus.EXTRACTED
    assert by_id["b"].status is EpistemicStatus.SUPPORTED, "unaffected work moved"
    assert not after.completed
    assert any("invoice-a" in n for n in after.open_needs)


def test_recheck_reverts_a_stale_supported_claim_before_reliance():
    c = lead.assess_support(_allegation("a", "paid", "invoice-a", "paid", "A"),
                         supported=True, snapshot=SNAP)
    assert lead.recheck(c, {"invoice-a": 2}).status is EpistemicStatus.EXTRACTED
    assert lead.recheck(c, {"invoice-a": 1}).status is EpistemicStatus.SUPPORTED


def test_a_hypothesis_is_labelled_and_never_a_conclusion():
    """AC2. Product reasoning is INFERENCE, not evidence, and does not enter the
    set a piece of advice may rest on."""
    h = lead.infer("h1", "the acknowledgment probably restarts limitation",
                subject="restart")
    assert h.status is EpistemicStatus.INFERENCE
    assert h not in Plan(1, claims=(h,)).conclusions()


# ============================ AC1: choose and revise ======================

def test_the_next_action_is_driven_by_state_not_a_fixed_sequence():
    """AC1. Different states call for different first actions -- there is no
    mandatory opening step. An open need retrieves; an unassessed extract
    assesses; a fully supported file stops."""
    assert lead.propose(Plan(1, open_needs=("find the delivery receipt",))
                     ).action is Action.RETRIEVE
    extract = lead.classify("e", "clause", "s", 1, asserted_by_party=False,
                         subject="x")
    assert lead.propose(Plan(1, claims=(extract,))).action is Action.ASSESS
    done = lead.assess_support(extract, supported=True, snapshot={"s": 1})
    assert lead.propose(Plan(1, claims=(done,))).action is Action.STOP


def test_changing_the_side_changes_the_assessment_not_the_facts():
    """EVAL-031's third transformation. The same disputed subject, read for one
    side then the other, challenges the claim ADVERSE to that side -- a reasoned
    difference. Renaming parties and paraphrasing change nothing."""
    d1 = _allegation("d1", "the price was paid", "email-b", "paid", "B Co")
    d2 = _allegation("d2", "the price was not paid", "invoice-a", "paid", "A Traders")
    disputed = lead.mark_disputes((d1, d2))
    for c in disputed:
        assert c.status is EpistemicStatus.DISPUTED

    plaintiff = lead.propose(Plan(1, claims=disputed), side="plaintiff",
                          opposing_party="B Co")
    defendant = lead.propose(Plan(1, claims=disputed), side="plaintiff",
                          opposing_party="A Traders")
    assert plaintiff.evidence_refs != defendant.evidence_refs

    # Renamed consistently + paraphrased -> SAME classification (material-invariant).
    r1 = _allegation("d1", "payment was rendered", "email-b", "paid", "Party-X")
    r2 = _allegation("d2", "payment was withheld", "invoice-a", "paid", "Party-Y")
    assert {c.status for c in lead.mark_disputes((r1, r2))} == {EpistemicStatus.DISPUTED}


def test_a_frozen_plan_cannot_report_completion_after_a_premise_moves():
    """AC1 negative control. `readiness` derives completion; a controlling need
    with no supported conclusion is open, and an unavailable controlling need is
    blocked -- neither can read as a clean done."""
    supported = lead.assess_support(
        _allegation("a", "paid", "invoice-a", "paid", "A"),
        supported=True, snapshot=SNAP)
    assert lead.readiness(Plan(1, claims=(supported,)),
                       controlling_needs=("paid",)).state == "useful"
    moved = lead.observe_source_change(Plan(1, claims=(supported,), completed=True),
                                    "invoice-a", 2)
    assert lead.readiness(moved, controlling_needs=("paid",)).state == "open"
    assert lead.readiness(Plan(1), controlling_needs=("receipt",),
                       unavailable=("receipt",)).state == "blocked"


def test_escalation_is_explicit_when_authority_is_insufficient():
    supported = lead.assess_support(
        _allegation("a", "paid", "invoice-a", "paid", "A"),
        supported=True, snapshot=SNAP)
    out = lead.readiness(Plan(1, claims=(supported,)), controlling_needs=("paid",),
                      authority_permits=False)
    assert out.state == "escalate"


def test_delegation_is_used_only_when_it_adds_value():
    """AC1. Ordinary work uses no specialist: when the lead can reach the need
    directly, it does not delegate."""
    assert not lead.wants_specialist("x", parallelisable=True, budget_units=2,
                                  direct_reach=True)
    assert lead.wants_specialist("x", parallelisable=True, budget_units=2,
                              direct_reach=False)


# ============================ INTEGRATION: lead + P47 =====================

PARENT = Mandate("mat-a", 7, tools=frozenset({"read", "retrieve"}),
                 processors=frozenset({"model-in"}), max_depth=1, max_concurrent=2)
SERVER = Mandate("mat-a", 7, tools=frozenset({"read", "retrieve", "draft"}),
                 processors=frozenset({"model-in", "index-in"}), max_depth=1,
                 max_concurrent=2)


def _task():
    return Task(task_id="t-research", parent_task_id="root", role=Role.RESEARCH,
                objective="find the authority on acknowledgment",
                mandate=PARENT, source_snapshot="commission@7",
                idempotency_key="idem-1", result_contract_version="rc-1",
                requested_budget={"tokens_and_cost": 2}, depth=1)


def test_the_lead_delegates_and_folds_candidates_through_the_p47_path():
    """INTEGRATION. The lead dispatches a specialist through P47 admission and
    folds the accepted result's findings into the plan as EXTRACTED candidates
    -- never SUPPORTED, because a specialist's finding is evidence to assess."""
    ledger = Ledger({"concurrency": 2, "tokens_and_cost": 5})
    admission = lead.dispatch(PARENT, _task(), SERVER, ledger)
    assert admission.admitted

    result = Result(
        task_id="t-research", attempt_id="att-1", mandate_version=7,
        source_snapshot="commission@7", status=ResultStatus.COMPLETED,
        producer_identity="research@v1",
        findings=(Finding("s.18 restarts limitation", "the_limitation_act::s18",
                          subject="restart"),))
    plan, acceptance = lead.integrate_result(
        Plan(1), result, admission.task, current_mandate_version=7, ledger=ledger)
    assert acceptance.accepted and not acceptance.incomplete
    folded = [c for c in plan.claims if c.subject == "restart"]
    assert folded and folded[0].status is EpistemicStatus.EXTRACTED


def test_a_forged_or_stale_specialist_result_changes_nothing():
    """INTEGRATION + AC2. A result whose task id does not match, or that rests on
    a superseded mandate, is refused by the P47 path and folds nothing."""
    ledger = Ledger({"concurrency": 2, "tokens_and_cost": 5})
    admission = lead.dispatch(PARENT, _task(), SERVER, ledger)
    forged = Result(task_id="somebody-else", attempt_id="a", mandate_version=7,
                    source_snapshot="commission@7", status=ResultStatus.COMPLETED,
                    producer_identity="")
    plan, acc = lead.integrate_result(Plan(1), forged, admission.task,
                                   current_mandate_version=7, ledger=ledger)
    assert not acc.accepted and plan.claims == ()

    stale = Result(task_id="t-research", attempt_id="b", mandate_version=6,
                   source_snapshot="commission@6", status=ResultStatus.COMPLETED,
                   producer_identity="research@v1",
                   findings=(Finding("x", "loc", subject="y"),))
    plan2, acc2 = lead.integrate_result(Plan(1), stale, admission.task,
                                     current_mandate_version=7, ledger=ledger)
    assert not acc2.accepted and plan2.claims == ()


def test_an_incomplete_specialist_leaves_the_plan_incomplete():
    """AC1/AC2. A FAILED specialist is accepted only as visibly incomplete, and
    the plan cannot then read as complete."""
    ledger = Ledger({"concurrency": 2, "tokens_and_cost": 5})
    admission = lead.dispatch(PARENT, _task(), SERVER, ledger)
    failed = Result(task_id="t-research", attempt_id="f", mandate_version=7,
                    source_snapshot="commission@7", status=ResultStatus.FAILED,
                    producer_identity="research@v1", stop_reason="index down")
    plan, acc = lead.integrate_result(Plan(1, completed=True), failed, admission.task,
                                   current_mandate_version=7, ledger=ledger)
    assert acc.accepted and acc.incomplete
    assert not plan.completed and plan.open_needs


def test_a_source_proposal_to_expand_authority_is_refused_end_to_end():
    """AC2 + EVAL-031/032 prompt injection. A specialist result that proposes to
    add a processor (the 'send the canary elsewhere' instruction) is accepted
    minus the delta -- the source grants no authority through the lead either."""
    ledger = Ledger({"concurrency": 2, "tokens_and_cost": 5})
    admission = lead.dispatch(PARENT, _task(), SERVER, ledger)
    result = Result(task_id="t-research", attempt_id="p", mandate_version=7,
                    source_snapshot="commission@7", status=ResultStatus.COMPLETED,
                    producer_identity="research@v1",
                    proposed_deltas=(MandateDelta(add_processors=frozenset({"another-firm"})),))
    _plan, acc = lead.integrate_result(Plan(1), result, admission.task,
                                    current_mandate_version=7, ledger=ledger)
    assert acc.accepted and acc.refused_deltas
