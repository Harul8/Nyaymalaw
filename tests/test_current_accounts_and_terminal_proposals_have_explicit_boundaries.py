"""Dispatched source/stop contracts, not a claim of live semantic compliance."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.Archives.legal_brain.understand.brain_context import ContextRefused, ContextSession
from nm.Archives.legal_brain.common.conversation import PRINCIPLES
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.Archives.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.Archives.legal_brain.orchestrate.tools import TERMINAL_CONTRACT, TERMINAL_REASONS, Effect, ToolRefused
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from tests.test_prior_instructions_admit_assertions_not_new_user_messages import registry_fixture
from tests.test_prior_private_user_input_survives_a_question_without_fact_writes import setup
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
TERMINALS = (
    ("ask_advocate", {"question": "Which material is presently available?"}, Effect.QUESTION),
    ("propose_conversation", {"text": "Understood."}, Effect.CONVERSATION),
    ("submit_answer", {"claims": []}, Effect.ANSWER),
)


def run(brain, turn, message, calls):
    brain.model.tool_call.side_effect = [_response(*calls)]
    return brain.run(matter_id="mat_loop", turn_id=turn, message=message,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))


def contract(system):
    payload = system.split("TRUSTED LOOP TERMINAL CONTRACT\n", 1)[1].split("\n", 1)[0]
    return json.loads(payload)


def test_single_guidance_owner_preserves_current_and_historical_attribution_without_examples():
    owner = FilePrinciples().load()
    assert PRINCIPLES == owner.text
    assert "earlier supplied accounts" in owner.text
    assert "each factual detail tied to its source turn" in owner.text
    assert "A newly\ndescribed event is not automatically a correction" in owner.text
    assert "Preserve both accounts unless their relationship is established" in owner.text
    assert "what was said now" in owner.text


def test_terminal_effect_population_is_the_immutable_runtime_and_request_owner():
    assert set(TERMINAL_REASONS) == set(Effect) - {Effect.CONTINUE}
    assert set(TERMINAL_REASONS.values()) == {
        StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION}
    with pytest.raises(TypeError):
        TERMINAL_REASONS[Effect.ANSWER] = StopReason.NO_PROGRESS


@pytest.mark.parametrize("name,args,effect", TERMINALS, ids=[row[0] for row in TERMINALS])
def test_each_actual_terminal_handler_stops_without_an_unrecorded_future_operation(
        tmp_path, name, args, effect):
    store, brain = setup(tmp_path)
    outcome = run(brain, "terminal", "Address the immediate request.",
                  (ToolCall("finish", name, deepcopy(args)),))
    actual = brain.model.tool_call.call_args.args[0]
    assert actual.system.count(TERMINAL_CONTRACT) == 1
    metadata = contract(actual.system)
    assert metadata == {"contract": TERMINAL_CONTRACT,
        "effects": {key.value: value.value for key, value in TERMINAL_REASONS.items()}}
    assert outcome.reason is TERMINAL_REASONS[effect]
    assert outcome.record.terminal and brain.model.tool_call.call_count == 1
    assert sum(event.kind is StepKind.TOOL_RETURNED for event in outcome.record.events) == 1
    assert outcome.record.events[-1].payload["released"] is False
    saved = store.load("mat_loop")
    assert not saved.turn_receipts and not saved.facts and not saved.asked
    before_calls = brain.model.tool_call.call_count
    retry = brain.run(matter_id="mat_loop", turn_id="terminal",
        message="Address the immediate request.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    assert retry == outcome and brain.model.tool_call.call_count == before_calls


@pytest.mark.parametrize("name,args,_effect", TERMINALS, ids=[row[0] for row in TERMINALS])
def test_a_terminal_cannot_claim_that_an_unfinished_tool_round_will_continue(
        tmp_path, name, args, _effect):
    _, brain = setup(tmp_path)
    outcome = run(brain, "unfinished", "Address the immediate request.", (
        ToolCall("finish", name, deepcopy(args)), ToolCall("later", "read_matter", {})))
    assert outcome.reason is StopReason.NO_PROGRESS and not outcome.proposal
    assert brain.model.tool_call.call_count == 1
    assert not any(event.kind is StepKind.TOOL_STARTED
        and event.payload["call"]["name"] == "read_matter" for event in outcome.record.events)


def test_current_request_and_previous_event_keep_exact_source_bindings_on_dispatch_and_recovery(
        tmp_path):
    store, brain = setup(tmp_path)
    earlier = "A different event affected the shared property last week; its cause is disputed."
    current = ("The same parties report a new entry-lock change this morning, "
               "not that earlier event.")
    first = run(brain, "prior_event", earlier,
                (ToolCall("one", "ask_advocate", {"question": "Which account is documented?"}),))
    second = run(brain, "current_event", current,
                 (ToolCall("two", "ask_advocate", {"question": "What confirms the new event?"}),))
    actual = brain.model.tool_call.call_args
    assert actual.args[0].user == current and current not in actual.args[0].system
    history = json.loads(actual.kwargs["messages"][0].text)["data"][
        "admitted_private_instructions"]
    assert len(history) == 1 and history[0]["turn_id"] == first.record.identity.turn_id
    assert history[0]["original_instruction"]["text"] == earlier
    assert history[0]["original_instruction"]["trust"] == (
        "user_instruction_not_established_fact_or_legal_authority")
    captured = second.record.events[0].payload["context"]
    recovered = ContextSession.from_record(captured, store.load("mat_loop"), advocate_id="adv_loop")
    assert recovered.to_record() == captured
    recovered.compact(store.load("mat_loop"), reason="Controlled source-bound compaction")
    recovered_row = json.loads(recovered.brief.text)["data"]["admitted_private_instructions"][0]
    assert recovered_row == history[0]
    assert recovered.brief.span("instruction:prior_event").verbatim == earlier
    assert not store.load("mat_loop").facts
    with pytest.raises(ContextRefused):
        recovered.assert_request(recovered.system.replace(TERMINAL_CONTRACT, "Continues later."),
                                 recovered.messages, model=recovered.model)


def test_earlier_source_words_cannot_be_recorded_as_a_new_current_event(tmp_path):
    store, before, context, registry, first = registry_fixture(tmp_path)
    earlier = first.record.events[0].payload["original_instruction"]["text"]
    assert earlier not in context.original_message
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("misattribute", "write_fact", {
            "quoted": "Access was blocked", "thread_ids": ["thread_one"]}), context)
    assert store.load("mat_loop") == before


def test_unrelated_current_words_cannot_replace_a_saved_previous_event_on_recovery(tmp_path):
    store, brain = setup(tmp_path)
    run(brain, "earlier", "An earlier distinct event was disputed.",
        (ToolCall("first", "propose_conversation", {"text": "Understood."}),))
    later = run(brain, "later", "A different event is now reported.",
        (ToolCall("next", "propose_conversation", {"text": "Understood."}),))
    forged = deepcopy(later.record.events[0].payload["context"])
    data = json.loads(forged["brief"]["text"])
    original = data["data"]["admitted_private_instructions"][0]["original_instruction"]
    original["text"] = "A different event is now reported."
    forged["brief"]["text"] = json.dumps(data)
    assert forged != later.record.events[0].payload["context"]
    with pytest.raises(ContextRefused):
        ContextSession.from_record(forged, store.load("mat_loop"), advocate_id="adv_loop")
