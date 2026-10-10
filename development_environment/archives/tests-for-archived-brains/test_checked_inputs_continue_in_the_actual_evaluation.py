"""One original instruction reaches reviewed conditional calculation without a new turn."""
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.evaluate.brain_evaluation import EvaluationService
from nm.Archives.legal_brain.procedure.calculation_tools import calculation_tools
from nm.Archives.legal_brain.orchestrate.checked_input_continuation import CheckedInputContinuationService
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind
from nm.Archives.legal_brain.procedure.reviewed_limitation_selection import (
    LimitationSelectionReviewService,
    prepare_limitation_selections,
    resolve_limitation_inputs,
)
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.work_the_file.original_instruction import read_original_instruction
from tests.test_event_limitation_selections_need_sealed_review import GENERATION, _fixture
from tests.test_independent_claim_verifier import response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
MESSAGE = "Assess the conditional event selection."


def _actual(tmp_path, *, negative=False):
    case = _fixture(tmp_path, judged=response(inference=False, words="The period is ninety days")
                    if negative else None)
    store, brain, _setup, judge, thread, _candidate, current = case
    brain.registry = brain.registry.extend(calculation_tools(store, source_version=GENERATION,
        event_selections=True, source_current=current, current_source_version=lambda: GENERATION,
        resolve=lambda matter, issue, context: resolve_limitation_inputs(matter, issue, context,
            source_generation=GENERATION, source_current=current)))
    brain._runner._tools = brain.registry
    brain.model.tool_call.side_effect = [replace(_response(call), provider="scripted",
        model="scripted:author") for call in (
            ToolCall("selection", "propose_limitation_selection", case[5]),
            ToolCall("pending", "ask_advocate",
                     {"question": "Which recorded event should govern the calculation?"}))]
    first = brain.run(matter_id="mat_loop", turn_id="event-selection", message=MESSAGE,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1.0,
                                max_children=2), 12, 500))
    brain.limitation_selection_review = LimitationSelectionReviewService(brain.reviewer,
        source_generation=GENERATION, source_current=current)
    brain.input_continuations = CheckedInputContinuationService(reviewer=brain.reviewer,
        binding_owners={"limitation": lambda outcome, matter: prepare_limitation_selections(
            outcome, matter, source_generation=GENERATION, source_current=current)},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    requests = []

    def continue_request(prompt, _tools, _tier, *, messages, **_kwargs):
        requests.append((prompt, messages))
        assert prompt.user == MESSAGE
        diagnostics = [json.loads(row.text) for row in messages
                       if "harness_check_continuation" in row.text]
        assert len(diagnostics) == 1 and "failures" not in diagnostics[0]["data"]
        return replace(_response(ToolCall("calculated", "compute_limitation",
            {"thread_id": thread.id, "as_of": "2026-09-27"}) if len(requests) == 1 else
            ToolCall("question", "ask_advocate",
                     {"question": "What supports the competing event?"})),
            provider="scripted", model="scripted:author")

    brain.model.tool_call.side_effect = continue_request
    return store, brain, first, judge, thread, requests


def _evaluate(brain, *, max_repairs=2):
    return EvaluationService(brain, Mock()).run(matter_id="mat_loop", turn_id="event-selection",
        message=MESSAGE, limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000,
        max_cost_usd=1.0, max_children=2), 12, 500), max_repairs=max_repairs)


def test_actual_review_then_calculation_keeps_one_request_and_whole_budget(tmp_path):
    store, brain, first, judge, thread, requests = _actual(tmp_path)
    result = _evaluate(brain)
    assert len(result.attempts) == 2 and result.attempts[0] == first
    assert len(judge.prompts) == 1 and len(requests) == 2
    assert result.stop == "question_needs_checks" and not result.client_ready
    assert result.budget.spend.discarded_results == 1
    assert result.budget.spend.children == 1
    checked_budget = result.limitation_selection_reviews[0].review.budget
    assert result.budget.spend.cost_usd == pytest.approx(checked_budget.spend.cost_usd + 0.02)
    assert continued_input_cost(result.attempts[1]) == checked_budget.spend.cost_usd
    continued = result.attempts[1].record
    assert continued.identity.turn_id == "event-selection:repair:1"
    assert all(read_original_instruction(row.record).text == MESSAGE for row in result.attempts)
    assert continued.events[0].payload["feedback_identity"]
    calculations = [event.payload["receipt"] for event in continued.events
        if event.kind is StepKind.TOOL_RETURNED
        and event.payload["receipt"]["tool"] == "compute_limitation"]
    assert len(calculations) == 1
    assert calculations[0]["data"]["position"]["state"] == "conditional"
    assert calculations[0]["data"]["deadline_registered"] is False
    matter = store.load("mat_loop")
    assert not matter.thread(thread.id).deadlines and not matter.turn_receipts
    assert all(row.date is None and row.confirmed is None for row in matter.facts)


def continued_input_cost(outcome):
    return outcome.record.events[0].payload["budget"]["spend"]["cost_usd"]


@pytest.mark.parametrize("reason", ["negative", "bound"])
def test_negative_or_exhausted_attempt_bound_cannot_create_a_continuation(tmp_path, reason):
    _store, brain, _first, judge, _thread, requests = _actual(
        tmp_path, negative=reason == "negative")
    result = _evaluate(brain, max_repairs=0 if reason == "bound" else 2)
    assert len(result.attempts) == 1 and not requests and len(judge.prompts) == 1
    assert result.stop == ("continuation_limit" if reason == "bound" else "question_needs_checks")
