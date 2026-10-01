"""Real finalization never replaces absent owned checks with authored PASS."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.Archives.legal_brain.verify.brain_assessment import AssessmentService
from nm.Archives.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.Archives.legal_brain.retrieve.evidence_port import Binding, Treatment
from nm.Archives.legal_brain.orchestrate.loop_contracts import StepKind
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import ProviderUnavailable, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file import dependency
from nm.work_the_file.matter_contracts import Certainty, FactBasis, Thread
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import finding

pytestmark = pytest.mark.class_a


def _setup(tmp_path, *, responses=None):
    thread = replace(Thread.create("Recorded dispute"), chronology=("fact_1",))
    store, brain, outcome, _, _ = _case(tmp_path, threads=(thread,))
    review = brain.review(outcome)
    model = ScriptedModelAdapter(ModelConfig({tier: TierConfig(
        tier, "scripted", "check-reader", None, None) for tier in (Tier.HARD, Tier.ROUTINE)}),
        structured_responses=responses or {
            "consistency": {"claim_id": "", "quoted": "", "why": "No contradiction found"},
            "duty": {"ground": "clear", "quoted": "", "why": "No prohibited instruction",
                     "lawful_section": ""}})
    reader = SavedCheckReader(store=store, log=brain.log, model=model,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version)
    service = FinalizationService(reader=reader, today=lambda: date(2026, 9, 27),
                                  jurisdiction="Recorded jurisdiction")
    return store, brain, outcome, review, model, service


def test_owned_duty_consistency_and_currency_use_real_saved_dispatches(tmp_path):
    store, brain, outcome, review, _, finalizer = _setup(tmp_path)
    result = finalizer.prepare(outcome, review)
    assert result.model_steps == 2
    assert result.budget.spend.tokens > review.budget.spend.tokens
    assert result.budget.spend.children == review.budget.spend.children + 2
    assert result.subjects.consistency_verdict.ran
    assert not result.subjects.consistency_verdict.refused
    assert not result.boundaries.duty.must_refuse
    assert dependency.presentable(result.subjects.ledger, "claim:p1")[0]
    assert result.subjects.previous_derived is None
    current = store.load("mat_loop")
    assert len([row for row in current.loop_records if ":check:" in row.identity.turn_id]) == 2
    assessment = AssessmentService(store=store, log=brain.log, session_current=lambda: True,
        supplement=finalizer.subjects, boundaries=finalizer.boundaries,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version).assess(
            outcome, review, expected_version=current.version)
    receipts = {row.gate_id: row for row in (*assessment.outputs, *assessment.boundaries)}
    for ident in ("G-CONSISTENT", "G-CURRENCY", "G-DUTY", "G-STALE"):
        assert receipts[ident].assessed is True, receipts[ident]
    for ident in ("G-CONSERVE", "G-CASCADE"):
        assert receipts[ident].assessed is True
        assert receipts[ident].reason.startswith("Not applicable: ")
    for ident in ("G-SCOPE", "G-COVERAGE"):
        assert receipts[ident].assessed is None, receipts[ident]
    assert not assessment.checks_complete and not assessment.client_ready


def test_exact_check_retry_reuses_actual_spend_without_network(tmp_path):
    _, _, outcome, review, model, finalizer = _setup(tmp_path)
    first = finalizer.prepare(outcome, review)
    model.structured = lambda *_args, **_kwargs: pytest.fail("Exact retry dispatched again")
    second = finalizer.prepare(outcome, review)
    assert second == first


def test_instruction_boundary_cannot_be_cleared_by_candidate_wording(tmp_path):
    _, _, outcome, review, _, finalizer = _setup(tmp_path, responses={
        "consistency": {"claim_id": "invented", "quoted": "notice", "why": "Invented fact"},
        "duty": {"ground": "false_document", "quoted": "Assess the notice requirement.",
                 "why": "Check actually refused", "lawful_section": ""}})
    result = finalizer.prepare(outcome, review)
    assert result.subjects.consistency_verdict.refused
    assert result.boundaries.duty.must_refuse


def test_absent_dispatch_allowance_leaves_owned_reads_unassessed(tmp_path):
    _, _, outcome, review, _, finalizer = _setup(tmp_path)
    result = finalizer.prepare(outcome, review, max_model_calls=0)
    assert result.model_steps == 0 and result.budget == review.budget
    assert not result.subjects.consistency_verdict.ran
    assert result.boundaries.duty.ground.value == "not_assessed"


def test_unknown_failed_provider_spend_retains_the_reservation(tmp_path):
    store, _, outcome, review, model, finalizer = _setup(tmp_path)
    model.structured = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ProviderUnavailable("No receipt returned"))
    result = finalizer.prepare(outcome, review)
    assert result.model_steps == 2
    assert result.budget.spend.cost_usd == pytest.approx(review.budget.spend.cost_usd + 0.06)
    assert not result.subjects.consistency_verdict.ran
    saved = [row for row in store.load("mat_loop").loop_records
             if ":check:" in row.identity.turn_id]
    assert all(row.events[-1].payload["released"] is False for row in saved)
    assert all(any(event.kind is StepKind.FAILURE for event in row.events) for row in saved)


@pytest.mark.parametrize("what", ["session", "source", "principles"])
def test_current_identity_change_refuses_saved_final_check(tmp_path, what):
    _, _, outcome, review, _, finalizer = _setup(tmp_path)
    finalizer.prepare(outcome, review)
    reader = finalizer.reader
    if what == "session":
        reader.session_current = lambda: False
    elif what == "source":
        reader.current_tools_version = lambda: "different"
    else:
        reader.current_principles_version = lambda: "different"
    with pytest.raises(ReviewRefused, match="changed"):
        finalizer.prepare(outcome, review)


@pytest.mark.parametrize("changes", [
    {"confirmed": None}, {"confirmed": False}, {"certainty": Certainty.DOCUMENTED},
    {"conflicts_with": ("another",)}, {"basis": FactBasis.BELIEF},
])
def test_status_only_changes_invalidate_dependent_claims_through_one_owner(tmp_path, changes):
    store, _, outcome, review, _, finalizer = _setup(tmp_path)
    current = store.load("mat_loop")
    ledger = finalizer.prepare(outcome, review).subjects.ledger
    changed = replace(current, facts=(replace(current.facts[0], **changes),))
    fresh, affected, _ = dependency.sync_inputs(ledger, changed, reason="Recorded status changed")
    assert "claim:p1" in affected
    assert not dependency.presentable(fresh, "claim:p1")[0]


@pytest.mark.parametrize("changes", [
    {"binding": Binding.NOT_ASSESSED}, {"supports": False},
    {"treatment": Treatment.not_checked("Current source treatment unavailable")},
    {"valid_to": date(2025, 1, 1)}, {"governing_date": date(2025, 1, 1)},
])
def test_source_status_movement_invalidates_the_same_reliance_even_when_words_stay(
        tmp_path, changes):
    store, _, outcome, review, _, finalizer = _setup(tmp_path)
    ledger = finalizer.prepare(outcome, review).subjects.ledger
    changed = finding(**changes)
    assert changed.span == finding().span
    fresh, affected, _ = dependency.sync_inputs(ledger, store.load("mat_loop"), (changed,),
                                               reason="Source metadata changed")
    assert "claim:p1" in affected
    assert not dependency.presentable(fresh, "claim:p1")[0]


def test_budget_is_not_reset_by_owned_checks(tmp_path):
    _, _, outcome, review, _, finalizer = _setup(tmp_path)
    finalizer.reader.cost_ceiling = lambda *_: review.budget.max_cost_usd + 0.01
    result = finalizer.prepare(outcome, review)
    assert result.model_steps == 0
    assert result.budget.spend.cost_usd == review.budget.spend.cost_usd
    assert result.budget.max_cost_usd == review.budget.max_cost_usd


def test_an_authored_budget_cannot_buy_a_saved_check(tmp_path):
    _, _, outcome, review, _, finalizer = _setup(tmp_path)
    inflated = replace(review, budget=replace(review.budget, max_cost_usd=100))
    with pytest.raises(ReviewRefused, match="budgets differ"):
        finalizer.prepare(outcome, inflated)


def test_cancelled_check_does_not_clear_instruction(tmp_path):
    _, _, outcome, review, _, finalizer = _setup(tmp_path)
    result = finalizer.prepare(outcome, review, cancelled=lambda: True)
    assert result.budget.spend == review.budget.spend
    assert result.boundaries.duty.ground.value == "not_assessed"


def test_changed_current_fact_refuses_previous_read_instead_of_reusing_a_clean_answer(tmp_path):
    store, _, outcome, review, _, finalizer = _setup(tmp_path)
    finalizer.prepare(outcome, review)
    current = store.load("mat_loop")
    store.commit(replace(current, facts=(replace(current.facts[0], statement="Changed account"),),
                         version=current.version + 1), expected_version=current.version)
    with pytest.raises(ValueError, match="changed"):
        finalizer.prepare(outcome, review)


def test_an_unreadable_transcript_leaves_prior_derived_checks_unassessed(tmp_path):
    store, _, outcome, review, _, finalizer = _setup(tmp_path)
    store.transcripts_for = lambda *_: (_ for _ in ()).throw(OSError("Unavailable history"))
    result = finalizer.prepare(outcome, review)
    assert not result.subjects.derivation_history.observed
    from nm.Archives.legal_brain.verify.output_checks import run_output_checks

    checks = {row.gate_id: row for row in run_output_checks(result.subjects)}
    assert checks["G-CONSERVE"].assessed is None
    assert checks["G-CASCADE"].assessed is None
