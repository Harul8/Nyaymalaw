"""Actual author, sealed review and check feedback, not a simulated PASS loop."""
from __future__ import annotations

from dataclasses import replace

import pytest
from nm.core import cascade, screens
from nm.core.brain_assessment import AssessmentService
from nm.core.brain_evaluation import (
    ANSWER_REPAIR_OWNERS,
    CheckFeedback,
    EvaluationService,
    answer_repairable,
    completed_child_within_grant,
    dispatch_steps,
)
from nm.core.output_checks import (
    BoundarySubjects,
    OutputSubjects,
    run_boundary_checks,
    run_output_checks,
)
from nm.domain.budget import Budget, Spend
from nm.domain.coverage import CoveragePosition, CoverageState
from nm.domain.loop import LoopLimits, StepKind
from nm.ports.model import ToolCall, Usage

from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def test_finishing_the_last_admitted_child_does_not_discard_its_checked_result(tmp_path):
    store, brain, _, judge, _ = _case(tmp_path, children=1)
    brain.assessment = AssessmentService(store=store, log=brain.log,
        session_current=lambda: True, current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    result = brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.", limits=LoopLimits(Budget(
            max_ms=60000, max_tokens=100000, max_cost_usd=1, max_children=1), 10, 500))
    assert result.stop == "required_checks_missing"
    assert len(result.assessments) == 1 and len(judge.prompts) == 1
    assert result.budget.spend.children == result.budget.max_children == 1
    assert result.assessments[0].review.result.released
    assert not result.client_ready


def test_phase_aware_last_child_permission_never_admits_overflow_or_another_exhaustion():
    assert completed_child_within_grant(Budget(max_children=1, spend=Spend(children=1)))
    assert not completed_child_within_grant(Budget(max_children=1, spend=Spend(children=2)))
    assert not completed_child_within_grant(Budget(max_children=1, max_tokens=10,
        spend=Spend(children=1, tokens=10)))
    assert not completed_child_within_grant(Budget(max_children=1,
        spend=Spend(children=1), cancelled_at="2026-09-27T00:00:00Z"))


def test_child_dispatches_are_in_the_same_repair_allowance_as_actual_parent_work(tmp_path):
    from types import SimpleNamespace

    _, _, outcome, _, _ = _case(tmp_path)
    parent = dispatch_steps(outcome.record)
    event = SimpleNamespace(kind=StepKind.TOOL_RETURNED, payload={
        "child_steps": 3, "child_released": False, "child_transcript": [
            {"kind": "model_started"}, {"kind": "model_failed"},
            {"kind": "model_started"}, {"kind": "tool_started"},
            {"kind": "tool_returned"}]})
    combined = SimpleNamespace(events=(*outcome.record.events, event))
    assert dispatch_steps(combined) == parent + 3
    for mutation in ({"child_steps": 2}, {"child_transcript": []}, {"child_released": True}):
        corrupt = SimpleNamespace(kind=event.kind, payload={**event.payload, **mutation})
        with pytest.raises(ValueError, match="child"):
            dispatch_steps(SimpleNamespace(events=(*outcome.record.events, corrupt)))


def _ready(tmp_path, *, failed=False):
    store, brain, outcome, judge, claim = _case(tmp_path,
                                              judged=response(inference=not failed))
    brain.assessment = AssessmentService(store=store, log=brain.log,
        session_current=lambda: True, current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    original = judge.structured

    def measured(*args, **kwargs):
        return replace(original(*args, **kwargs), usage=Usage(10, 10, 0.01))

    judge.structured = measured
    return store, brain, outcome, judge, claim


def _run(brain, **kwargs):
    return brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500),
        **kwargs)


def test_missing_owner_checks_do_not_cause_futile_paid_repairs_or_a_client_release(tmp_path):
    store, brain, _, judge, _ = _ready(tmp_path)
    checked = _run(brain)
    assert checked.stop == "required_checks_missing" and len(checked.attempts) == 1
    assert len(judge.prompts) == 1 and checked.limitations
    assert not checked.client_ready and not store.load("mat_loop").turn_receipts
    repeated = _run(brain)
    assert repeated.attempts == checked.attempts and repeated.assessments == checked.assessments
    assert repeated.stop == checked.stop and repeated.limitations == checked.limitations
    # Rechecking is not another provider call. Its own assembly/checking time
    # is observed rather than silently copied from the previous invocation.
    assert repeated.budget.spend.cost_usd == checked.budget.spend.cost_usd
    assert repeated.budget.spend.tokens == checked.budget.spend.tokens
    assert repeated.budget.spend.children == checked.budget.spend.children
    assert repeated.budget.spend.elapsed_ms >= repeated.attempts[0].budget.spend.elapsed_ms
    assert len(judge.prompts) == 1


def test_many_claims_share_the_remaining_step_allowance_with_the_independent_judge(tmp_path):
    _, _, _, _, original = _case(tmp_path / "seed")
    claims = [{**original, "id": f"claim-{i}"} for i in range(5)]
    store, brain, outcome, judge, _ = _case(tmp_path / "bounded", claims=claims, max_steps=5)
    brain.assessment = AssessmentService(store=store, log=brain.log,
        session_current=lambda: True, current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    # The previously admitted parent has four steps. The shared allowance
    # has exactly one remaining judge dispatch, not one per claimed paragraph.
    evaluation = brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 5, 500))
    review = evaluation.assessments[0].review
    assert review.model_steps == 1 and len(judge.prompts) == 1
    assert len(review.result.withheld) == 4 and len(review.result.released) == 1
    assert not store.load("mat_loop").turn_receipts
    repeated = brain.review(outcome, max_model_calls=1)
    assert repeated == review and len(judge.prompts) == 1


def test_context_assembly_cannot_spend_past_the_deadline_before_the_first_dispatch(tmp_path):
    _, brain, _, judge, _ = _ready(tmp_path)
    elapsed = [0.0]
    actual_load = brain.principles.load

    def slow_context():
        value = actual_load()
        elapsed[0] = 61.0
        return value

    brain.principles.load = slow_context
    evaluator = EvaluationService(brain, brain.assessment, monotonic=lambda: elapsed[0])
    result = evaluator.run(matter_id="mat_loop", turn_id="slow-assembly",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    assert result.stop == "budget" and result.budget.spend.elapsed_ms >= 61000
    assert result.attempts[0].record.events[0].payload["budget"]["spend"]["elapsed_ms"] == 61000
    assert not judge.prompts and not result.client_ready


def test_context_and_assessment_time_are_part_of_the_whole_operation_deadline(tmp_path):
    _, brain, _, judge, _ = _ready(tmp_path)
    elapsed = [0.0]
    actual_assessment = brain.assessment.assess

    def slow_assessment(*args, **kwargs):
        value = actual_assessment(*args, **kwargs)
        elapsed[0] = 61.0
        return value

    brain.assessment.assess = slow_assessment
    evaluator = EvaluationService(brain, brain.assessment, monotonic=lambda: elapsed[0])
    result = evaluator.run(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    assert result.stop == "budget" and result.budget.spend.elapsed_ms == 61000
    assert result.budget.spend.cost_usd == pytest.approx(0.03)
    assert len(judge.prompts) == 1 and len(result.attempts) == 1
    assert not result.client_ready


def test_failed_inference_returns_to_author_then_rechecks_exact_repaired_words(tmp_path):
    store, brain, _, judge, original = _ready(tmp_path, failed=True)
    # Subsequent calls are genuinely new source reads and new checked claims.
    count = 0

    def repair(prompt, _tools, _tier, *, messages, **_kw):
        nonlocal count
        count += 1
        assert prompt.user == "Assess the notice requirement."
        assert any("harness_check_feedback" in m.text for m in messages)
        if count == 1:
            return replace(_response(ToolCall("r-source", "read_provision", {
                "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})),
                model="scripted:author")
        return replace(_response(ToolCall("r-answer", "submit_answer", {"claims": [
            {**original, "text": "On this account, the benefit remains conditional on notice."}]})),
            model="scripted:author")

    brain.model.tool_call.side_effect = repair
    original_judge = judge.structured

    def second_judgment(*args, **kwargs):
        value = original_judge(*args, **kwargs)
        if len(judge.prompts) > 1:
            return replace(value, data=response())
        return value

    judge.structured = second_judgment
    result = _run(brain)
    assert len(result.attempts) == 2 and len(result.assessments) == 2
    assert result.assessments[0].withheld and not result.assessments[1].withheld
    assert result.budget.spend.cost_usd == pytest.approx(0.06)
    assert result.budget.spend.children == 2 and result.budget.spend.discarded_results == 1
    start = result.attempts[1].record.events[0].payload
    assert start["budget"]["spend"]["cost_usd"] == pytest.approx(0.03)
    assert start["feedback_identity"]
    assert not store.load("mat_loop").turn_receipts and not result.client_ready


def test_unchanged_failed_proposal_stops_instead_of_exhausting_the_repair_allowance(tmp_path):
    _, brain, _, judge, original = _ready(tmp_path, failed=True)
    brain.model.tool_call.side_effect = [
        replace(_response(ToolCall("r-source", "read_provision", {
            "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})),
            model="scripted:author"),
        replace(_response(ToolCall("r-answer", "submit_answer", {"claims": [original]})),
                model="scripted:author")]
    result = _run(brain, max_repairs=5)
    assert result.stop == "no_progress" and len(result.attempts) == 2
    assert len(judge.prompts) == 2 and result.budget.spend.cost_usd == pytest.approx(0.06)


def test_feedback_cannot_be_swapped_on_an_exact_finished_retry(tmp_path):
    _, brain, outcome, _, _ = _ready(tmp_path)
    first = CheckFeedback("mat_loop", "package-turn", outcome.record.events[-1].fingerprint,
                          (("p1:inference", "The proposed inference did not follow."),))
    brain.model.tool_call.side_effect = None
    brain.model.tool_call.return_value = replace(_response(text="not a terminal"),
                                               model="scripted:author")
    args = {"matter_id": "mat_loop", "turn_id": "repair-admission",
        "message": "Assess the notice requirement.",
        "limits": LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 4, 500)}
    brain.run(**args, feedback=first)
    calls = brain.model.tool_call.call_count
    with pytest.raises(ValueError, match="feedback differs"):
        brain.run(**args, feedback=replace(first, failures=(("different", "Changed verdict"),)))
    assert brain.model.tool_call.call_count == calls


def test_cancellation_during_the_judge_keeps_spend_and_withholds_the_returned_result(tmp_path):
    store, brain, _, judge, _ = _ready(tmp_path)
    cancelled = [False]
    original = judge.structured

    def cancel(*args, **kwargs):
        result = original(*args, **kwargs)
        cancelled[0] = True
        return result

    judge.structured = cancel
    result = _run(brain, cancelled=lambda: cancelled[0])
    assert result.stop == "cancelled" and result.budget.cancelled_at
    assert result.budget.spend.cost_usd == pytest.approx(0.03)
    assert not result.assessments and not result.client_ready
    receipt = store.load("mat_loop").loop_records[-1]
    assert receipt.events[-1].kind is StepKind.STOP
    assert receipt.events[-1].payload["verification"]["textual_eligible"] is None


def test_repair_ownership_is_closed_over_the_actual_eighteen_and_six_population():
    population = (*run_output_checks(OutputSubjects()), *run_boundary_checks(BoundarySubjects()))
    assert len(population) == 24 and len({row.gate_id for row in population}) == 24
    failed = tuple(replace(row, assessed=False, reason="Controlled real-owner failure")
                   for row in population)
    assert {row.gate_id for row in failed if answer_repairable(row)} == ANSWER_REPAIR_OWNERS
    assert all(not answer_repairable(replace(row, assessed=None)) for row in population)
    assert all(not answer_repairable(replace(row, assessed=True)) for row in population)


@pytest.mark.parametrize("state,gate_id,stop", [
    ("coverage", "G-COVERAGE", "required_reservations"),
    ("movement", "G-CASCADE", "required_reservations"),
    ("lost_derivation", "G-CONSERVE", "owner_state_blocked"),
    ("conflict", "G-CONFLICT", "owner_state_blocked"),
])
def test_real_owner_state_does_not_invite_paid_answer_rewrites(tmp_path, state, gate_id, stop):
    store, brain, _, judge, _ = _ready(tmp_path)
    if state == "coverage":
        brain.assessment.supplement = lambda *_: OutputSubjects(coverage=CoveragePosition(
            CoverageState.UNMET, "recorded-forum",
            "This binding period is absent from the corpus."))
    elif state in {"movement", "lost_derivation"}:
        before = cascade.Derived("recorded-position", "earlier", ("fact_1",), "Recorded position")
        after = replace(before, value="corrected")
        brain.assessment.supplement = lambda *_: OutputSubjects(
            previous_derived=(before,), derived=(after,) if state == "movement" else ())
    else:
        brain.assessment.boundaries = lambda *_: BoundarySubjects(
            screens=(screens.Screen(screens.ScreenKind.CONFLICT, screens.ScreenState.BLOCKED,
                                    detail="A conflict requires the qualified owner."),),
            parties=frozenset({"recorded-party"}))
    calls = brain.model.tool_call.call_count
    result = _run(brain, max_repairs=5)
    assert result.stop == stop and len(result.attempts) == len(result.assessments) == 1
    assert brain.model.tool_call.call_count == calls and len(judge.prompts) == 1
    assert any(gate_id in reason for reason in result.limitations)
    failed = {row.gate_id: row for row in result.assessments[0].failed}
    assert failed[gate_id].assessed is False
    assert not result.client_ready and not store.load("mat_loop").turn_receipts


def test_a_legitimate_answer_repair_preserves_prior_owner_reservations(tmp_path):
    _, brain, _, judge, original = _ready(tmp_path, failed=True)
    brain.assessment.supplement = lambda _matter, outcome, _review: OutputSubjects(
        coverage=CoveragePosition(
            CoverageState.UNMET if outcome.record.identity.turn_id == "package-turn"
            else CoverageState.MET, "recorded-forum", "The actual observed coverage position."))
    calls = 0

    def repair(prompt, _tools, _tier, *, messages, **_kw):
        nonlocal calls
        calls += 1
        feedback = tuple(message.text for message in messages
                         if "harness_check_feedback" in message.text)
        assert feedback and "p1:inference" in feedback[0] and "G-COVERAGE" not in feedback[0]
        assert prompt.user == "Assess the notice requirement."
        call = (ToolCall("r-source", "read_provision", {
            "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})
            if calls == 1 else ToolCall("r-answer", "submit_answer", {"claims": [{
                **original,
                "text": "On this account, notice remains a condition of the benefit."}]}))
        return replace(_response(call), model="scripted:author")

    brain.model.tool_call.side_effect = repair
    original_judge = judge.structured

    def second_judgment(*args, **kwargs):
        value = original_judge(*args, **kwargs)
        return replace(value, data=response()) if len(judge.prompts) > 1 else value

    judge.structured = second_judgment
    result = _run(brain)
    assert len(result.attempts) == 2 and len(judge.prompts) == 2
    assert result.stop == "required_reservations"
    assert not result.assessments[1].withheld
    assert any("G-COVERAGE" in reason for reason in result.limitations)
    assert any(row.gate_id == "G-COVERAGE" for row in result.assessments[0].failed)
    assert not any(row.gate_id == "G-COVERAGE" for row in result.assessments[1].failed)
    assert result.budget.spend.cost_usd == pytest.approx(0.06)
