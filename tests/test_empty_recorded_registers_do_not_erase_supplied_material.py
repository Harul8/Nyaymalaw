"""Exact read scope and actual controlled callers, not a live reasoning score."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from nm.legal_brain.brain_context import ContextRefused, ContextSession
from nm.legal_brain.conversation import PRINCIPLES
from nm.legal_brain.loop_contracts import LoopLimits, StepKind, StopReason
from nm.legal_brain.principles_file_adapter import FilePrinciples
from nm.legal_brain.tool_discovery import discovery_tools
from nm.legal_brain.tools import ToolRefused
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.work_the_file.matter_contracts import Certainty
from nm.work_the_file.write_tools import write_tools
from tests.test_prior_instructions_admit_assertions_not_new_user_messages import registry_fixture
from tests.test_prior_private_user_input_survives_a_question_without_fact_writes import setup
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
ACCOUNT = ("The opponent alleges a transfer; our client denies it. "
           "Assess the available material without treating either account as proven.")
REPLY = "The original document has not been supplied; I can provide the correspondence."


def run(brain, turn, message, calls):
    dispatched, responses = [], iter(calls)

    def response(prompt, tools, _tier, *, messages, **_kwargs):
        dispatched.append((prompt, tools, messages))
        return _response(next(responses))

    brain.model.tool_call.side_effect = response
    outcome = brain.run(matter_id="mat_loop", turn_id=turn, message=message,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 24, 400))
    return outcome, dispatched


def read_then_ack(brain, turn, message):
    return run(brain, turn, message, (
        ToolCall("read", "read_matter", {}),
        ToolCall("reply", "propose_conversation", {"text": "Understood."})))


def test_single_guide_and_actual_capability_description_keep_the_read_scope_explicit(tmp_path):
    _, brain = setup(tmp_path)
    owner = FilePrinciples().load()
    assert PRINCIPLES == owner.text
    assert "Persisted structured registers and supplied advocate material are different inputs" in (
        owner.text)
    assert "not automatically admitted facts or established truth" in owner.text
    assert "Do not substitute an empty-register" in owner.text
    assert "absence of a needed schema" in owner.text
    definition = next(row for row in brain.registry.definitions if row.name == "read_matter")
    assert "persisted structured matter registers" in definition.description
    assert "not that no brief or material was supplied" in definition.description
    assert "neither admits them nor establishes their truth" in definition.description
    _, sent = read_then_ack(brain, "actual_scope", ACCOUNT)
    assert sent[0][0].system.count(owner.text) == 1
    assert sent[0][0].system.count(definition.description) == 1
    actual = next(row for row in sent[0][1] if row.name == "read_matter")
    assert actual == definition


def test_empty_read_result_does_not_replace_the_current_supplied_account(tmp_path):
    store, brain = setup(tmp_path)
    outcome, dispatched = read_then_ack(brain, "opening", ACCOUNT)
    result = json.loads(dispatched[1][2][-1].text)
    assert result["tool"] == "read_matter"
    assert result["data"]["facts"] == [] and result["data"]["disputes"] == []
    assert result["receipt"]["matter_id"] == "mat_loop"
    assert all(prompt.user == ACCOUNT for prompt, _, _ in dispatched)
    assert all(ACCOUNT not in prompt.system for prompt, _, _ in dispatched)
    assert outcome.record.events[0].payload["original_instruction"]["text"] == ACCOUNT
    saved = store.load("mat_loop")
    assert not saved.facts and not saved.threads and not saved.turn_receipts


def test_empty_read_preserves_earlier_assertions_and_current_limits_on_actual_later_dispatch(
        tmp_path):
    store, brain = setup(tmp_path)
    first, _ = read_then_ack(brain, "original", ACCOUNT)
    second, dispatched = read_then_ack(brain, "reply", REPLY)
    for prompt, _, messages in dispatched:
        assert prompt.user == REPLY
        data = json.loads(messages[0].text)["data"]
        assert data["facts"] == [] and data["threads"] == []
        row = data["admitted_private_instructions"][0]
        assert row["turn_id"] == first.record.identity.turn_id
        assert row["original_instruction"]["text"] == ACCOUNT
        assert row["original_instruction"]["trust"] == (
            "user_instruction_not_established_fact_or_legal_authority")
    captured = second.record.events[0].payload["context"]
    restored = ContextSession.from_record(captured, store.load("mat_loop"), advocate_id="adv_loop")
    assert restored.to_record() == captured
    assert restored.brief.span("instruction:original").verbatim == ACCOUNT
    assert not store.load("mat_loop").facts


def test_needed_unoffered_schema_can_be_discovered_loaded_and_used_without_inventing_truth(
        tmp_path):
    store, brain = setup(tmp_path)
    brain.registry = brain.registry.extend(write_tools(store))
    brain.registry = brain.registry.extend(
        discovery_tools(lambda: brain.registry, brain.principles))
    brain._runner._tools = brain.registry
    outcome, sent = run(brain, "record_supplied", ACCOUNT, (
        ToolCall("read", "read_matter", {}),
        ToolCall("find", "discover_tools", {"query": "record supplied account"}),
        ToolCall("load", "inspect_tool", {"name": "create_dispute"}),
        ToolCall("record", "create_dispute", {"label": "Disputed transfer",
                                               "quoted": "The opponent alleges a transfer"}),
        ToolCall("finish", "propose_conversation", {
            "text": "The attributed account is recorded."})))
    assert "create_dispute" not in {row.name for row in sent[0][1]}
    assert "create_dispute" not in {row.name for row in sent[2][1]}
    assert "create_dispute" in {row.name for row in sent[3][1]}
    assert all(prompt.user == ACCOUNT for prompt, _, _ in sent)
    assert outcome.reason is StopReason.CONVERSATION
    saved = store.load("mat_loop")
    assert len(saved.facts) == 1 and len(saved.threads) == 1
    fact = saved.facts[0]
    assert fact.statement == fact.exact_words == fact.provenance.span == ACCOUNT
    assert fact.certainty is Certainty.ASSERTED and fact.confirmed is None
    assert fact.provenance.turn == "record_supplied"
    assert saved.threads[0].chronology == (fact.id,) and not saved.threads[0].assessed
    assert not saved.turn_receipts
    assert sum(event.kind is StepKind.MODEL_STARTED for event in outcome.record.events) == 5


@pytest.mark.parametrize("terminal", ["propose_conversation", "ask_advocate"])
def test_empty_register_clarification_does_not_force_intake_or_research_for_every_interaction(
        tmp_path, terminal):
    store, brain = setup(tmp_path)
    args = {"text": "Understood."} if terminal == "propose_conversation" else {
        "question": "Which document are you asking me to examine?"}
    message = "Thank you." if terminal == "propose_conversation" else "Please examine the document."
    outcome, dispatched = run(brain, "proportionate", message,
                              (ToolCall("finish", terminal, args),))
    assert len(dispatched) == 1
    assert outcome.reason in {StopReason.CONVERSATION, StopReason.QUESTION}
    assert not store.load("mat_loop").facts and not store.load("mat_loop").threads
    assert not any(event.kind is StepKind.TOOL_STARTED and event.payload["call"]["name"] in {
        "read_matter", "create_dispute", "search_authority"} for event in outcome.record.events)


def test_supplied_history_cannot_be_relabelled_as_a_current_admitted_fact(tmp_path):
    store, before, context, registry, _ = registry_fixture(tmp_path)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("mislabel", "write_fact", {
            "quoted": "The sibling claims the title", "thread_ids": ["thread_one"]}), context)
    assert store.load("mat_loop") == before


def test_recovery_cannot_silently_replace_narrow_register_scope_with_total_material_absence(
        tmp_path):
    store, brain = setup(tmp_path)
    outcome, _ = read_then_ack(brain, "source_scope", ACCOUNT)
    captured = outcome.record.events[0].payload["context"]
    restored = ContextSession.from_record(captured, store.load("mat_loop"), advocate_id="adv_loop")
    changed = tuple(replace(row, description="Empty registers prove no material was supplied.")
        if row.name == "read_matter" else row for row in restored.offered_definitions)
    assert changed != restored.offered_definitions
    with pytest.raises(ContextRefused):
        restored.assert_request(restored.system, restored.messages, model=restored.model,
                                tools=changed)
