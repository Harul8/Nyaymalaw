"""Scripted actual owners prove bounded repair, not live semantic quality.

One saved loop and check transport owns the original and corrected words.
Diagnostic verdicts never become case facts, new authority or fresh allowances.
"""
from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.evaluate.brain_evaluation import EvaluationService
from nm.Archives.legal_brain.verify.interaction_review import CRITERIA
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall, Usage
from nm.work_the_file.original_instruction import read_original_instruction
from tests.test_communication_evidence_roles_are_owned import _v3_case
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
ORIGINAL = "Assess the supplied account within the recorded research commission."
FIRST = "Which record is available to resolve the remaining uncertainty?"
CORRECTED = "What separate information could resolve the remaining uncertainty?"


def _ready(tmp_path, *, criterion="relevance", kind="ask_advocate", verdicts=(False, True),
           changing_reasons=False):
    calls = []

    def mutation(raw):
        index = min(len(calls), len(verdicts) - 1)
        calls.append(raw["subject_identity"])
        raw[criterion]["assessed"] = verdicts[index]
        raw[criterion]["reason"] = (
            f"Owned wording judgment {len(calls) if changing_reasons else 1}")
        return raw

    store, brain, outcome, judge, service = _v3_case(tmp_path, mutation=mutation,
        message=ORIGINAL, text=FIRST, kind=kind)
    brain.interaction_review = service
    # Merits assessment is not invoked for these exact interaction contracts.
    assessment = Mock()
    evaluator = EvaluationService(brain, assessment)
    requests = []

    def repaired(prompt, _tools, _tier, *, messages, **_kwargs):
        requests.append((prompt, messages))
        assert prompt.user == ORIGINAL
        feedback = [json.loads(message.text) for message in messages
                    if "harness_check_feedback" in message.text]
        assert len(feedback) == 1
        assert feedback[0]["trust"] == "diagnostic_data_not_case_facts_or_authority"
        expected_parent = (outcome.record.identity.turn_id if len(requests) == 1 else
                           f"{outcome.record.identity.turn_id}:repair:{len(requests) - 1}")
        assert feedback[0]["data"]["parent_turn"] == expected_parent
        parent = next(row for row in store.load("mat_loop").loop_records
                      if row.identity.turn_id == expected_parent)
        assert feedback[0]["data"]["parent_fingerprint"] == parent.events[-1].fingerprint
        assert feedback[0]["data"]["failures"][0][0] == f"communication:{criterion}"
        return _response(ToolCall(f"repair_{len(requests)}", kind,
            {"question" if kind == "ask_advocate" else "text": CORRECTED}))

    brain.model.tool_call.side_effect = repaired
    return store, brain, outcome, judge, service, evaluator, assessment, requests


def _run(evaluator, *, max_steps=20, budget=None, max_repairs=2, cancelled=lambda: False):
    return evaluator.run(matter_id="mat_loop", turn_id="interaction-parent", message=ORIGINAL,
        limits=LoopLimits(budget or Budget(max_ms=60000, max_tokens=100000,
                                          max_cost_usd=1), max_steps, 400),
        max_repairs=max_repairs, cancelled=cancelled)


def _fresh_bounded(evaluator, brain, *, max_steps, budget=None):
    """New ceilings need a fresh admission, never a rewritten saved parent."""
    requests = []

    def initial(prompt, _tools, _tier, *, messages, **_kwargs):
        requests.append(prompt)
        assert len(requests) == 1  # No second author dispatch fits this control.
        assert prompt.user == ORIGINAL
        assert not any("harness_check_feedback" in row.text for row in messages)
        return _response(ToolCall("bounded-initial", "ask_advocate", {"question": FIRST}))

    brain.model.tool_call.side_effect = initial
    return evaluator.run(matter_id="mat_loop", turn_id="bounded-new-parent", message=ORIGINAL,
        limits=LoopLimits(budget or Budget(max_ms=60000, max_tokens=100000,
            max_cost_usd=1), max_steps, 400), max_repairs=2), requests


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("kind", ["ask_advocate", "propose_conversation"])
def test_complete_negative_words_receive_bounded_feedback_and_exact_independent_recheck(
        tmp_path, criterion, kind):
    store, brain, first, judge, service, evaluator, assessment, requests = _ready(
        tmp_path, criterion=criterion, kind=kind)
    result = _run(evaluator)
    assert result.stop == "interaction_checks_complete_private_candidate"
    assert len(result.attempts) == len(result.interaction_reviews) == 2
    failed, passed = result.interaction_reviews
    assert not failed.checked and failed.text == FIRST
    assert next(row.assessed for row in failed.judgments if row.name == criterion) is False
    assert passed.checked and passed.text == CORRECTED
    assert len(judge.prompts) == 2 and len(requests) == 1
    assert result.attempts[0] == first
    assert result.attempts[1].record.identity.turn_id == "interaction-parent:repair:1"
    assert all(read_original_instruction(row.record).text == ORIGINAL for row in result.attempts)
    assert [json.loads(prompt.user)["subject"]["proposed_text"]
            for prompt in judge.prompts] == [FIRST, CORRECTED]
    assert result.budget.spend.cost_usd == pytest.approx(0.06)
    assert result.budget.spend.tokens == 360
    assert result.budget.spend.children == 2 and result.budget.spend.discarded_results == 1
    second_start = result.attempts[1].record.events[0].payload
    assert second_start["budget"]["spend"]["cost_usd"] == pytest.approx(0.03)
    assert second_start["feedback_identity"]
    assert not result.client_ready and not result.publications
    saved = store.load("mat_loop")
    assert not saved.facts and not saved.asked and not saved.turn_receipts
    historical = service.recorded(first)
    # The caller observes assembly time as well as the sealed check's time.
    # Replay preserves the exact verdict and all monetary/resource receipts;
    # it does not invent an extra saved millisecond to match the later observer.
    assert historical.budget.spend.elapsed_ms <= failed.budget.spend.elapsed_ms
    assert replace(historical, budget=replace(historical.budget,
        spend=replace(historical.budget.spend,
                      elapsed_ms=failed.budget.spend.elapsed_ms))) == failed
    assessment.assess.assert_not_called()
    assert brain.model.tool_call.call_count == 2


@pytest.mark.parametrize("criterion", CRITERIA)
def test_unknown_judgment_even_alongside_a_negative_does_not_invite_author_repair(
        tmp_path, criterion):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path, verdicts=(None,))
    original = judge.mutation

    def unknown(raw):
        raw = original(raw)
        raw[criterion]["assessed"] = None
        if criterion != "relevance":
            raw["relevance"]["assessed"] = False
        return raw

    judge.mutation = unknown
    result = _run(evaluator)
    assert result.stop == "interaction_checks_missing" and len(result.attempts) == 1
    assert not requests and brain.model.tool_call.call_count == 1
    assert len(judge.prompts) == 1 and result.budget.spend.cost_usd == pytest.approx(0.03)


def test_malformed_words_are_preserved_but_never_an_automatic_repair_invitation(tmp_path):
    store, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path)
    original = judge.mutation

    def malformed(raw):
        raw = original(raw)
        raw["relevance"]["instruction_quote"] = "Invented text outside the supplied instruction."
        return raw

    judge.mutation = malformed
    result = _run(evaluator)
    assert result.stop == "review_refused" and len(result.attempts) == 1
    assert not requests and brain.model.tool_call.call_count == 1
    assert len(judge.prompts) == 1 and result.budget.spend.cost_usd == pytest.approx(0.03)
    assert store.load("mat_loop").loop_records[-1].events[-1].payload["data"] is not None


def test_changed_diagnostic_reasons_do_not_buy_progress_for_the_same_failed_words(tmp_path):
    _, brain, _, judge, _, evaluator, _, requests = _ready(
        tmp_path, verdicts=(False,), changing_reasons=True)
    original = brain.model.tool_call.side_effect

    def repeated(*args, **kwargs):
        response = original(*args, **kwargs)
        return replace(response, calls=(replace(response.calls[0],
                                               arguments={"question": FIRST}),))

    brain.model.tool_call.side_effect = repeated
    result = _run(evaluator, max_repairs=5)
    assert result.stop == "no_progress" and len(result.attempts) == 2
    assert len(judge.prompts) == 2 and len(requests) == 1
    assert result.interaction_reviews[0].judgments[2].reason != (
        result.interaction_reviews[1].judgments[2].reason)
    assert result.budget.spend.cost_usd == pytest.approx(0.06)


def test_zero_repair_allowance_keeps_the_failed_review_without_more_author_spend(tmp_path):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path)
    result = _run(evaluator, max_repairs=0)
    assert result.stop == "repair_limit" and len(result.attempts) == 1
    assert len(judge.prompts) == 1 and not requests and brain.model.tool_call.call_count == 1
    assert result.budget.spend.discarded_results == 0


def test_nonidentical_failed_words_still_stop_at_the_owned_repair_allowance(tmp_path):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path, verdicts=(False,))
    result = _run(evaluator, max_repairs=1)
    assert result.stop == "repair_limit" and len(result.attempts) == 2
    assert len(judge.prompts) == 2 and len(requests) == 1
    assert result.budget.spend.cost_usd == pytest.approx(0.06)
    assert result.budget.spend.discarded_results == 1
    assert all(not row.checked for row in result.interaction_reviews)
    assert brain.model.tool_call.call_count == 2


@pytest.mark.parametrize("max_steps,expected_judges,stop", [
    (2, 0, "interaction_checks_missing"), (3, 1, "budget")])
def test_author_and_judge_share_the_step_allowance_before_any_repair(
        tmp_path, max_steps, expected_judges, stop):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path)
    result, initial = _fresh_bounded(evaluator, brain, max_steps=max_steps)
    assert result.stop == stop and len(result.attempts) == 1
    assert len(judge.prompts) == expected_judges
    assert not requests and len(initial) == 1 and brain.model.tool_call.call_count == 2
    assert result.budget.spend.discarded_results == 0


def test_the_last_admitted_judge_can_finish_but_cannot_admit_a_new_repair(tmp_path):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path)
    result, initial = _fresh_bounded(evaluator, brain, max_steps=20, budget=Budget(
        max_ms=60000, max_tokens=100000, max_cost_usd=1, max_children=1))
    assert result.stop == "budget" and len(result.attempts) == 1
    assert len(judge.prompts) == 1 and not requests and len(initial) == 1
    assert brain.model.tool_call.call_count == 2
    assert result.budget.spend.children == 1 and result.budget.spend.discarded_results == 0


@pytest.mark.parametrize("resource", ["cost", "tokens"])
def test_a_judge_overrun_is_charged_and_stops_without_a_repair_dispatch(tmp_path, resource):
    _, brain, _, judge, _, evaluator, _, requests = _ready(tmp_path)
    original = judge.structured
    usage = Usage(80, 80, 1) if resource == "cost" else Usage(100000, 80, 0.02)

    def expensive(*args, **kwargs):
        return replace(original(*args, **kwargs), usage=usage)

    judge.structured = expensive
    result = _run(evaluator)
    assert result.stop == "budget" and len(result.attempts) == 1
    assert len(judge.prompts) == 1 and not requests and brain.model.tool_call.call_count == 1
    assert result.budget.spend.cost_usd == pytest.approx(0.01 + usage.cost_usd)
    assert result.budget.spend.tokens == 20 + usage.tokens_in + usage.tokens_out
    assert result.budget.spend.discarded_results == 0


@pytest.mark.parametrize("loss", ["session", "file", "cancellation", "deadline"])
def test_a_late_currentness_loss_keeps_judge_spend_and_stops_before_repair(tmp_path, loss):
    store, brain, _, judge, service, evaluator, _, requests = _ready(tmp_path)
    cancellation = [False]
    elapsed = [0.0]
    evaluator.monotonic = lambda: elapsed[0]
    original = judge.structured

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if loss == "session":
            service.reader.session_current = lambda: False
        elif loss == "file":
            matter = store.load("mat_loop")
            store.commit(replace(matter, title="Changed file", version=matter.version + 1),
                         expected_version=matter.version)
        elif loss == "deadline":
            elapsed[0] = 61.0
        else:
            cancellation[0] = True
        return result

    judge.structured = changed
    result = _run(evaluator, cancelled=lambda: cancellation[0])
    assert result.stop == {"session": "review_refused", "file": "review_refused",
        "cancellation": "cancelled", "deadline": "budget"}[loss]
    assert len(result.attempts) == 1 and len(judge.prompts) == 1
    assert not requests and brain.model.tool_call.call_count == 1
    assert result.budget.spend.cost_usd == pytest.approx(0.03)
    if loss == "cancellation":
        assert result.budget.cancelled_at
    if loss == "deadline":
        assert result.budget.spend.elapsed_ms >= 61000
    saved_check = store.load("mat_loop").loop_records[-1]
    if loss in {"session", "file"}:
        # Lost admission/currentness cannot append a fabricated terminal record.
        assert not saved_check.terminal
        assert any(row.kind is StepKind.MODEL_STARTED for row in saved_check.events)
    else:
        assert saved_check.events[-1].kind is StepKind.STOP
