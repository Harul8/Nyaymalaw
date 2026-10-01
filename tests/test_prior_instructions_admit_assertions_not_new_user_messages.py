"""Exact earlier advocate words feed existing writes, never history-as-new-truth."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    Boundary,
    Effect,
    RegisteredTool,
    ToolContext,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    ToolRegistry,
    object_schema,
)
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import SchemaViolation, ToolCall, ToolDefinition
from nm.work_the_file.matter_contracts import Certainty, Thread
from nm.work_the_file.write_tools import write_tools
from tests.test_the_controlled_brain_is_actually_wired import _brain
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
ALLOW = Boundary(True, "Attributed isolated controlled scope")
EARLIER = "The sibling claims the title; our client denies releasing her share. Access was blocked."
REPLY = "There is no pending suit. Continue the separate inquiries."


def setup(tmp_path):
    store, model, brain = _brain(tmp_path)
    question = RegisteredTool(ToolDefinition("ask_advocate", "Propose a clarification.",
        object_schema({"question": {"type": "string"}})), ToolKind.CONTROL, "v1", True,
        ("test_prior_data_is_not_truth",), lambda args, context: ToolEnvelope(
            "ask_advocate", "v1", ToolKind.CONTROL, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
            {"operation": "ask_advocate", "turn_id": context.identity.turn_id}, args,
            "This is an unchecked private question.", effect=Effect.QUESTION))
    brain.registry = brain.registry.extend((*write_tools(store), question))
    brain._runner._tools = brain.registry
    limits = LoopLimits(Budget(max_ms=10000, max_tokens=100000, max_cost_usd=1),
                        max_steps=16, per_call_tokens=200)
    model.tool_call.return_value = _response(ToolCall("question", "ask_advocate",
        {"question": "Is there a pending proceeding?"}))
    first = brain.run(matter_id="mat_loop", turn_id="first_brief", message=EARLIER,
                      limits=limits)
    assert first.reason is StopReason.QUESTION
    assert not store.load("mat_loop").facts and not store.load("mat_loop").threads
    return store, model, brain, limits, first


def test_an_actual_reply_can_record_the_prior_brief_with_its_original_provenance(tmp_path):
    store, model, brain, limits, first = setup(tmp_path)
    model.tool_call.side_effect = [
        _response(ToolCall("title", "record_prior_instruction", {
            "new_dispute_label": "Claimed title", "thread_ids": [], "quoted":
            "The sibling claims the title", "instruction_turn_id": "first_brief"})),
        _response(ToolCall("access", "record_prior_instruction", {
            "new_dispute_label": "Obstructed access", "thread_ids": [], "quoted":
            "Access was blocked", "instruction_turn_id": "first_brief"})),
        _response(ToolCall("done", "submit", {"answer": "Still private and unchecked."})),
    ]
    later = brain.run(matter_id="mat_loop", turn_id="later_reply", message=REPLY, limits=limits)
    assert later.reason is StopReason.PROPOSAL
    saved = store.load("mat_loop")
    assert len(saved.threads) == 2 and len(saved.facts) == 1
    fact = saved.facts[0]
    assert fact.statement == fact.exact_words == fact.provenance.span == EARLIER
    assert fact.provenance.turn == first.record.identity.turn_id
    assert fact.certainty is Certainty.ASSERTED and fact.confirmed is None
    assert fact.statement != REPLY and REPLY not in fact.statement
    assert all(thread.chronology == (fact.id,) and not thread.assessed for thread in saved.threads)
    assert saved.version == later.record.identity.matter_version + len(later.record.events)
    assert not saved.turn_receipts
    repeated = brain.run(matter_id="mat_loop", turn_id="later_reply", message=REPLY, limits=limits)
    assert repeated == later and len(store.load("mat_loop").facts) == 1


def registry_fixture(tmp_path):
    store, _model, _brain_object, _limits, first = setup(tmp_path)
    matter = store.load("mat_loop")
    store.commit(replace(matter, threads=(Thread("thread_one", "Recorded question"),),
                         version=matter.version + 1), expected_version=matter.version)
    matter = store.load("mat_loop")
    context = ToolContext(replace(first.record.identity, turn_id="later_reply",
                                 matter_version=matter.version), original_message=REPLY)
    registry = ToolRegistry(write_tools(store), before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    return store, matter, context, registry, first


@pytest.mark.parametrize("source", [
    "missing", "first_brief:check:communication", "../first_brief", "x" * 101])
def test_unknown_child_or_nonportable_history_never_becomes_a_source(tmp_path, source):
    store, before, context, registry, _ = registry_fixture(tmp_path)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("write", "record_prior_instruction", {"quoted": EARLIER,
            "new_dispute_label": None,
            "thread_ids": ["thread_one"], "instruction_turn_id": source}), context)
    assert store.load("mat_loop") == before


@pytest.mark.parametrize("changed", [
    "future", "foreign_actor", "foreign_matter", "foreign_mode", "duplicate", "unsealed"])
def test_old_input_requires_exact_before_admission_owned_complete_parent(tmp_path, changed):
    store, before, context, registry, first = registry_fixture(tmp_path)
    parent = first.record
    if changed == "future":
        context = replace(context, identity=replace(context.identity,
            matter_version=parent.identity.matter_version + len(parent.events) - 1))
    elif changed == "duplicate":
        before = replace(before, loop_records=(parent, parent))
    elif changed == "unsealed":
        before = replace(before, loop_records=(replace(parent, events=parent.events[:-1]),))
    else:
        from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopMode, LoopRecord

        identity = replace(parent.identity, **{
            "foreign_actor": {"advocate_id": "other"},
            "foreign_matter": {"matter_id": "other"},
            "foreign_mode": {"mode": LoopMode.RECORDED},
        }[changed])
        events, previous = [], identity.fingerprint
        for event in parent.events:
            rebuilt = LoopEvent.create(
                event.sequence, event.kind, event.at, event.payload, previous)
            events.append(rebuilt)
            previous = rebuilt.fingerprint
        before = replace(before, loop_records=(LoopRecord(identity, tuple(events)),))
    # Owned store lookup is the authority; a planted record tests its closed admission.
    registry = ToolRegistry(write_tools(Mock(load=Mock(return_value=before))),
        before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("write", "record_prior_instruction", {"quoted": EARLIER,
            "new_dispute_label": None,
            "thread_ids": ["thread_one"], "instruction_turn_id": "first_brief"}), context)
    assert not before.facts


def test_correction_and_checklist_schemas_cannot_reuse_stale_original_input(tmp_path):
    _store, _matter, context, registry, _first = registry_fixture(tmp_path)
    for name in ("correct_fact", "record_requirement_answer",
                 "record_existing_requirement_answer", "add_issue"):
        definition = next(row for row in registry.definitions if row.name == name)
        assert "instruction_turn_id" not in definition.parameters["properties"]
        with pytest.raises(SchemaViolation):
            registry.invoke(
                ToolCall("forged", name, {"instruction_turn_id": "first_brief"}), context)


def test_current_writes_remain_current_and_all_seven_schemas_remain_strict(tmp_path):
    _store, _matter, context, registry, _first = registry_fixture(tmp_path)
    call = ToolCall("current", "write_fact", {"quoted": REPLY, "thread_ids": ["thread_one"]})
    assert "instruction_turn_id" not in call.arguments
    result = registry.invoke(call, context)
    assert result.mutation.after.facts[0].statement == REPLY
    assert result.mutation.after.facts[0].provenance.turn == "later_reply"
    population = registry.definitions
    assert len(population) == 7
    existing = tuple(row for row in population if row.name != "record_prior_instruction")
    assert len(existing) == 6
    assert all("instruction_turn_id" not in row.parameters["properties"] for row in existing)
    for definition in population:
        with pytest.raises(SchemaViolation):
            registry.invoke(ToolCall("missing", definition.name, {}), context)


@pytest.mark.parametrize(("label", "threads", "quoted"), [
    ("New dispute", ["thread_one"], EARLIER), (None, [], EARLIER),
    ("   ", [], EARLIER), (None, ["missing"], EARLIER),
    (None, ["thread_one", "thread_one"], EARLIER),
    (None, ["thread_one"], "The model invented this fact."),
])
def test_prior_recording_has_one_closed_mode_and_never_accepts_invented_words(
        tmp_path, label, threads, quoted):
    store, before, context, registry, _ = registry_fixture(tmp_path)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("prior", "record_prior_instruction", {
            "instruction_turn_id": "first_brief", "quoted": quoted,
            "new_dispute_label": label, "thread_ids": threads}), context)
    assert store.load("mat_loop") == before


def test_an_earlier_assertion_can_be_linked_to_an_existing_dispute_without_truth_upgrade(tmp_path):
    store, before, context, registry, _ = registry_fixture(tmp_path)
    proposed = registry.invoke(ToolCall("prior", "record_prior_instruction", {
        "instruction_turn_id": "first_brief", "quoted": "our client denies releasing her share",
        "new_dispute_label": None, "thread_ids": ["thread_one"]}), context)
    assert store.load("mat_loop") == before
    fact = proposed.mutation.after.facts[0]
    assert fact.statement == fact.exact_words == EARLIER
    assert fact.provenance.turn == "first_brief" and fact.confirmed is None
    assert fact.certainty is Certainty.ASSERTED
    assert proposed.envelope.data["instruction_turn_id"] == "first_brief"
    assert proposed.envelope.data["asserted_only"] is True


@pytest.mark.parametrize("changed", ["forged_original", "explicit_prior_scope", "narrowed_current"])
def test_prior_words_cannot_escape_recorded_original_or_either_scope(tmp_path, changed):
    from copy import deepcopy

    from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, digest

    _store, before, context, _registry, first = registry_fixture(tmp_path)
    if changed == "narrowed_current":
        context = replace(context, issue_ids=("thread_one",))
    else:
        previous, events = first.record.identity.fingerprint, []
        for event in first.record.events:
            payload = deepcopy(event.payload)
            if event.kind is StepKind.START:
                if changed == "forged_original":
                    payload["original_instruction"]["text"] = "A different advocate account."
                    payload["original_instruction"]["text_identity"] = digest(
                        payload["original_instruction"]["text"])
                else:
                    payload["scope_identity"] = digest({"requested_issue_ids": ["thread_other"]})
            rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, payload, previous)
            events.append(rebuilt)
            previous = rebuilt.fingerprint
        before = replace(before, loop_records=(LoopRecord(first.record.identity, tuple(events)),))
    registry = ToolRegistry(write_tools(Mock(load=Mock(return_value=before))),
        before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("prior", "record_prior_instruction", {
            "instruction_turn_id": "first_brief", "quoted": "Access was blocked",
            "new_dispute_label": "Access dispute", "thread_ids": []}), context)
    assert not before.facts
