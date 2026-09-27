"""Actual outgoing offers, saved inspections and replay, not metadata savings."""
from __future__ import annotations

import copy
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest
from nm.adapters.model.replay import ReplayModel, records_from_loop
from nm.adapters.store.file_store import FileMatterStore
from nm.adapters.store.loop_log import MatterLoopLog
from nm.core.brain_context import ContextPolicy, ContextRefused, ContextSession, assemble_brief
from nm.core.controlled_brain import ControlledBrain, EvaluationScope
from nm.core.tool_discovery import discovery_tools
from nm.core.tool_offers import OfferRefused
from nm.core.tools import (
    Assessment,
    Availability,
    Boundary,
    OfferRole,
    RegisteredTool,
    ToolContext,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    foundation_tools,
    object_schema,
)
from nm.domain.loop import LoopMode, StepKind, StopReason
from nm.domain.matter import Matter
from nm.ports.model import Prompt, ProviderUnavailable, Tier, ToolCall, ToolDefinition, ToolMessage

from tests.test_brain_context_is_a_checked_file_projection import snapshot
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def setup(tmp_path, *, optional_size=100, before=None, after=None):
    store = FileMatterStore(tmp_path, key="private-offer-test-key")
    matter = store.commit(Matter("offer_file", "advocate", "Private file", version=1),
                          expected_version=0)
    principles = Mock()
    principles.load.return_value = snapshot()
    def allow(*_):
        return Boundary(True, "Explicit controlled test admission.")
    registry = foundation_tools(store, Mock(), manifest=Mock(), source_version="checked-source",
                               before=before or allow, after=after or allow)
    invoked = Mock()

    def optional(args, ctx):
        invoked(args, ctx)
        return ToolEnvelope("optional_read", "v1", ToolKind.CONTROL, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.SUPPORTED,
            {"operation": "optional_read", "turn_id": ctx.identity.turn_id}, {"read": True})

    definition = ToolDefinition("optional_read", "Read another checked owner.",
        object_schema({"requested": {"type": "string", "description": "D" * optional_size}}))
    registry = registry.extend((RegisteredTool(definition, ToolKind.CONTROL, "v1", True,
        ("test_uninspected_tool_is_never_dispatched",), optional),))
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    log = MatterLoopLog(store, advocate_id="advocate")
    brain = ControlledBrain(store=store, model=model, principles=principles, log=log,
        registry=registry, scope=EvaluationScope("approved-controlled", "advocate",
            frozenset({matter.id}), LoopMode.SYNTHETIC), cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True)
    return brain, matter, invoked


def run(brain, matter, *, turn="offer-turn", limits=None):
    return brain.run(matter_id=matter.id, turn_id=turn,
        message="Read the appropriate registered owner, then ask what is missing.",
        limits=limits or _limits())


def inspect(call_id="inspection"):
    return _response(ToolCall(call_id, "inspect_tool", {"name": "optional_read"}))


def question():
    return _response(ToolCall("question", "ask_advocate", {"question": "What is still missing?"}))


def test_only_checked_inspection_adds_the_exact_schema_to_the_next_wire_request(tmp_path):
    brain, matter, invoked = setup(tmp_path, optional_size=4000)
    brain.model.tool_call.side_effect = [inspect(),
        _response(ToolCall("optional", "optional_read", {"requested": "current"})), question()]
    output = run(brain, matter)
    assert output.reason is StopReason.QUESTION
    offered = [args.args[1] for args in brain.model.tool_call.call_args_list]
    assert "optional_read" not in {row.name for row in offered[0]}
    exact = next(row for row in brain.registry.definitions if row.name == "optional_read")
    assert exact in offered[1] and exact in offered[2]
    assert len(offered[0]) < len(brain.registry.definitions)
    starts = [event for event in output.record.events if event.kind is StepKind.MODEL_STARTED]
    for event, definitions in zip(starts, offered, strict=True):
        assert event.payload["tools"] == [asdict(row) for row in definitions]
    source = next(event for event in output.record.events
                  if event.kind is StepKind.TOOL_RETURNED)
    assert source.payload["receipt"]["tool"] == "inspect_tool"
    assert source.sequence < starts[1].sequence
    assert invoked.call_count == 1 and not output.record.events[-1].payload["released"]
    # Metadata rank/identity and the loading contract are not execution authority.
    assert not source.payload["receipt"]["data"]["grants_permission"]
    restored = ContextSession.from_record(starts[-1].payload["context"],
        brain.store.load(matter.id), advocate_id="advocate")
    assert exact in restored.offered_definitions
    original_calls = brain.model.tool_call.call_count
    assert run(brain, matter) == output
    assert brain.model.tool_call.call_count == original_calls


def test_metadata_discovery_does_not_load_a_schema_or_approve_its_action(tmp_path):
    brain, matter, invoked = setup(tmp_path)
    brain.model.tool_call.side_effect = [
        _response(ToolCall("discover", "discover_tools", {"query": "optional"})),
        _response(ToolCall("illegal", "optional_read", {"requested": "current"}))]
    result = run(brain, matter)
    assert result.reason is StopReason.REFUSED and invoked.call_count == 0
    assert result.budget.spend.cost_usd == 0.02
    assert "optional_read" not in {
        row.name for row in brain.model.tool_call.call_args_list[1].args[1]}
    assert any(event.kind is StepKind.FAILURE
               and event.payload["kind"] == "unoffered_or_invalid_tool"
               for event in result.record.events)


def test_uninspected_tool_is_never_dispatched_even_with_same_round_inspection(tmp_path):
    brain, matter, invoked = setup(tmp_path)
    brain.model.tool_call.return_value = _response(
        ToolCall("inspection", "inspect_tool", {"name": "optional_read"}),
        ToolCall("illegal", "optional_read", {"requested": "current"}))
    result = run(brain, matter)
    assert result.reason is StopReason.REFUSED and invoked.call_count == 0
    assert result.budget.spend.cost_usd == 0.01
    assert not any(event.kind is StepKind.TOOL_STARTED for event in result.record.events)


def test_loading_never_bypasses_the_registered_permission_owner(tmp_path):
    def boundary(name, *_):
        return Boundary(name != "optional_read", "This action is not authorized.")

    brain, matter, invoked = setup(tmp_path, before=boundary)
    brain.model.tool_call.side_effect = [inspect(),
        _response(ToolCall("not-authorized", "optional_read", {"requested": "current"}))]
    result = run(brain, matter)
    assert result.reason is StopReason.REFUSED and invoked.call_count == 0
    assert result.budget.spend.cost_usd == 0.02


@pytest.mark.parametrize("changed", ["schema", "name", "version", "authority", "unknown"])
def test_forged_or_changed_inspection_cannot_load_any_schema(tmp_path, changed):
    brain, matter, _ = setup(tmp_path)
    state = brain.registry.offer_state()
    call = ToolCall("inspection", "inspect_tool", {"name": "optional_read"})
    from nm.domain.loop import LoopIdentity, digest

    identity = LoopIdentity(matter.id, "advocate", "turn", digest("prompt"),
        brain.principles.load().version, brain.registry.version, matter.version, LoopMode.SYNTHETIC)
    receipt = brain.registry.invoke(call, ToolContext(identity))
    data, origin = copy.deepcopy(receipt.data), copy.deepcopy(receipt.receipt)
    if changed == "schema":
        data["definition"]["parameters"]["properties"]["requested"]["type"] = "integer"
    elif changed == "name":
        data["definition"]["name"] = "read_provision"
    elif changed == "version":
        origin["registry_version"] = "moved-version"
    elif changed == "authority":
        data["grants_permission"] = True
    else:
        data["definition"]["parameters"]["unsupported_constraint"] = True
    with pytest.raises(OfferRefused):
        state.loaded_by(call, replace(receipt, data=data, receipt=origin))
    assert state.to_record()["loads"] == []


def test_loading_history_survives_checked_compaction_not_an_authored_state_flag(tmp_path):
    brain, matter, _ = setup(tmp_path)
    offer = brain.registry.offer_state()
    session = ContextSession(brain.principles.load(), brain.registry.definitions,
        assemble_brief(matter, advocate_id="advocate"), provider="scripted", model="recorded-v1",
        policy=ContextPolicy(max_tokens=100000), tool_offer=offer)
    from nm.domain.loop import LoopIdentity, digest

    identity = LoopIdentity(matter.id, "advocate", "turn", digest("prompt"),
        brain.principles.load().version, brain.registry.version, matter.version, LoopMode.SYNTHETIC)
    call = ToolCall("inspection", "inspect_tool", {"name": "optional_read"})
    receipt = brain.registry.invoke(call, ToolContext(identity))
    session.append(ToolMessage("assistant", calls=(call,)),
                   ToolMessage("tool", receipt.wire(), call_id=call.call_id))
    session.load_checked_schema(call, receipt)
    session.compact(matter, reason="Actual checked-file context generation.")
    restored = ContextSession.from_record(session.to_record(), matter, advocate_id="advocate")
    assert "optional_read" in {row.name for row in restored.offered_definitions}
    mutated = copy.deepcopy(session.to_record())
    mutated["transcript"] = mutated["messages"]
    with pytest.raises(ContextRefused):
        ContextSession.from_record(mutated, matter, advocate_id="advocate")
    with pytest.raises(ContextRefused, match="loaded schemas"):
        restored.assert_request(restored.system, restored.messages, model=restored.model,
                                tools=tuple(sorted(brain.registry.definitions,
                                                   key=lambda row: row.name)))


def test_replay_uses_each_exact_loaded_offer_and_changed_offer_cannot_consume_record(tmp_path):
    brain, matter, _ = setup(tmp_path)
    brain.model.tool_call.side_effect = [inspect(), question()]
    result = run(brain, matter)
    rows, versions = records_from_loop(result.record, brain.registry.definitions)
    replay = ReplayModel(rows, versions=versions)
    starts = [event.payload for event in result.record.events
              if event.kind is StepKind.MODEL_STARTED]
    for payload in starts:
        definitions = tuple(ToolDefinition(**row) for row in payload["tools"])
        messages = tuple(ToolMessage(row["role"], row["text"],
            tuple(ToolCall(**call) for call in row["calls"]), row["call_id"])
            for row in payload["messages"])
        if payload is starts[0]:
            from nm.ports.model import SchemaViolation

            with pytest.raises(SchemaViolation):
                replay.tool_call(Prompt(**payload["prompt"]), brain.registry.definitions,
                    Tier.ROUTINE, messages=messages, max_tokens=payload["max_tokens"])
        replay.tool_call(Prompt(**payload["prompt"]), definitions, Tier.ROUTINE,
                         messages=messages, max_tokens=payload["max_tokens"])
    assert replay.position == len(rows)


def test_actual_request_size_reduces_without_changing_the_budget_or_cutting_data(tmp_path):
    brain, matter, _ = setup(tmp_path, optional_size=80000)
    brain.model.tool_call.return_value = question()
    output = run(brain, matter)
    assert output.reason is StopReason.QUESTION
    from nm.ports.model import estimate_tokens, tool_request_text

    payload = next(event.payload for event in output.record.events
                   if event.kind is StepKind.MODEL_STARTED)
    definitions = tuple(ToolDefinition(**row) for row in payload["tools"])
    messages = brain.model.tool_call.call_args.kwargs["messages"]
    prompt = Prompt(**payload["prompt"])
    actual = estimate_tokens(tool_request_text(prompt, definitions, messages))
    eager = estimate_tokens(tool_request_text(prompt, brain.registry.definitions, messages))
    assert actual + payload["max_tokens"] == payload["reserved_tokens"]
    assert actual < _limits().budget.max_tokens < eager
    assert len(payload["context"]["tool_specs"]) == len(brain.registry.definitions)
    assert len(payload["tools"]) < len(payload["context"]["tool_specs"])


def test_a_loaded_schema_exceeding_capacity_stops_without_silent_truncation(tmp_path):
    brain, matter, _ = setup(tmp_path, optional_size=80000)
    brain.model.tool_call.side_effect = [inspect(), question()]
    output = run(brain, matter)
    assert output.reason is StopReason.BUDGET
    assert brain.model.tool_call.call_count == 1 and output.budget.spend.cost_usd == 0.01
    assert any(event.kind is StepKind.TOOL_RETURNED for event in output.record.events)


def test_unknown_provider_result_retains_reservation_and_exact_retry_does_not_dispatch(tmp_path):
    brain, matter, _ = setup(tmp_path)
    brain.model.tool_call.side_effect = ProviderUnavailable("Unknown provider outcome.")
    output = run(brain, matter)
    assert output.reason is StopReason.PROVIDER and output.budget.spend.cost_usd == 0.03
    assert run(brain, matter) == output and brain.model.tool_call.call_count == 1


def test_schema_loading_waits_for_a_durable_receipt_and_interruption_is_not_redispatched(tmp_path):
    from nm.ports.store import StaleWrite

    brain, matter, invoked = setup(tmp_path)
    brain.model.tool_call.side_effect = [inspect(), question()]
    original = brain._runner._log
    guarded = Mock(wraps=original)

    def append(identity, event):
        if event.kind is StepKind.TOOL_RETURNED:
            raise StaleWrite("The loader receipt was not durably accepted.")
        return original.append(identity, event)

    guarded.append.side_effect = append
    brain._runner._log = guarded
    with pytest.raises(StaleWrite):
        run(brain, matter)
    saved = brain.store.load(matter.id).loop_records[0]
    assert saved.events[-1].kind is StepKind.TOOL_STARTED and not saved.terminal
    brain._runner._log = original
    output = run(brain, matter)
    assert output.reason is StopReason.INTERRUPTED
    assert brain.model.tool_call.call_count == 1 and invoked.call_count == 0
    assert output.budget.spend.cost_usd == 0.01


def test_a_loader_receipt_refused_after_the_handler_does_not_load_the_schema(tmp_path):
    def after(receipt, _context):
        return Boundary(receipt.tool != "inspect_tool", "This result has not passed its boundary.")

    brain, matter, invoked = setup(tmp_path, after=after)
    brain.model.tool_call.side_effect = [inspect(), question()]
    output = run(brain, matter)
    assert output.reason is StopReason.REFUSED and brain.model.tool_call.call_count == 1
    assert not any(event.kind is StepKind.TOOL_RETURNED for event in output.record.events)
    assert output.budget.spend.cost_usd == 0.01 and invoked.call_count == 0


@pytest.mark.parametrize("mutation", ["added", "removed", "changed", "missing"])
def test_replay_refuses_a_per_dispatch_offer_that_does_not_follow_sealed_loading(
        tmp_path, mutation):
    from nm.domain.loop import LoopEvent, LoopRecord
    from nm.ports.model import SchemaViolation

    brain, matter, _ = setup(tmp_path)
    brain.model.tool_call.side_effect = [inspect(), question()]
    output = run(brain, matter)
    previous, events, changed = output.record.identity.fingerprint, [], False
    for event in output.record.events:
        payload = copy.deepcopy(event.payload)
        if event.kind is StepKind.MODEL_STARTED and not changed:
            changed = True
            if mutation == "added":
                payload["tools"].append(asdict(next(row for row in brain.registry.definitions
                    if row.name == "optional_read")))
            elif mutation == "removed":
                payload["tools"].pop()
            elif mutation == "changed":
                payload["tools"][0]["description"] = "Another tool definition."
            else:
                del payload["tools"]
        copied = LoopEvent.create(event.sequence, event.kind, event.at, payload, previous)
        events.append(copied)
        previous = copied.fingerprint
    assert changed
    with pytest.raises(SchemaViolation):
        records_from_loop(LoopRecord(output.record.identity, tuple(events)),
                          brain.registry.definitions)


def test_loader_metadata_is_typed_and_cannot_turn_a_write_into_an_initial_loader():
    from nm.domain.authority import Act

    definition = ToolDefinition("write", "Record a checked change.", object_schema({}))
    with pytest.raises(ValueError):
        RegisteredTool(definition, ToolKind.MATTER, "v1", False, ("refusal",), Mock(),
                       required_act=Act.RECORD, offer_role=OfferRole.SCHEMA_LOADER)
    with pytest.raises(ValueError):
        RegisteredTool(definition, ToolKind.MATTER, "v1", False, ("refusal",), Mock(),
                       offer_role="schema_loader")
