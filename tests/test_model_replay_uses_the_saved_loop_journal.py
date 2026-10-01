"""Replay consumes real sealed journals, including rejected paid attempts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, StepKind, digest
from nm.shared.model_port import ProviderUnavailable, SchemaViolation, ToolCall, Usage
from nm.shared.model_replay import ReplayModel
from nm.shared.store_file_store import FileMatterStore
from tests.test_the_loop_records_work_before_using_it import (
    PROMPT,
    _limits,
    _registry,
    _response,
    _setup,
)

pytestmark = pytest.mark.class_a


def _run(tmp_path, error=None):
    registry = _registry()
    _, identity, _, model, runner = _setup(tmp_path, registry)
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.tool_call.side_effect = error or [
        _response(ToolCall("first", "read", {})),
        _response(ToolCall("last", "submit", {"answer": "An unreleased candidate."})),
    ]
    output = runner.run(identity, PROMPT, _limits())
    return registry, model, output


def _reseal(record, change):
    events, previous = [], record.identity.fingerprint
    for held in record.events:
        payload = held.payload
        change(held.kind, payload)
        event = LoopEvent.create(held.sequence, held.kind, held.at, payload, previous)
        events.append(event)
        previous = event.fingerprint
    return LoopRecord(record.identity, tuple(events))


def test_two_real_saved_calls_replay_after_a_store_restart_without_network(tmp_path):
    registry, model, output = _run(tmp_path)
    restarted = FileMatterStore(tmp_path, key="isolated-loop-key")
    record = restarted.load(output.record.identity.matter_id).loop_records[0]
    replay = ReplayModel.from_loop(record, registry.definitions)
    # Use the actual saved neutral receipt, not a second independently
    # authored expected list.
    results = [
        event.payload["result"]["value"]
        for event in record.events
        if event.kind is StepKind.MODEL_RETURNED
    ]
    for request, expected in zip(model.tool_call.call_args_list, results, strict=True):
        restored = replay.tool_call(*request.args, **request.kwargs)
        assert restored.model == expected["model"]
        assert restored.usage.cost_usd == expected["usage"]["cost_usd"]
        assert [call.call_id for call in restored.calls] == [
            row["call_id"] for row in expected["calls"]
        ]
    assert replay.position == 2 and model.tool_call.call_count == 2


def test_a_changed_prompt_does_not_consume_the_saved_call(tmp_path):
    registry, model, output = _run(tmp_path)
    replay = ReplayModel.from_loop(output.record, registry.definitions)
    request = model.tool_call.call_args_list[0]
    with pytest.raises(SchemaViolation, match="request/version"):
        replay.tool_call(
            replace(PROMPT, user="A materially different instruction."),
            *request.args[1:],
            **request.kwargs,
        )
    assert replay.position == 0
    assert replay.tool_call(*request.args, **request.kwargs).calls[0].call_id == "first"


def test_changed_tool_descriptions_and_source_generation_are_refused(tmp_path):
    registry, _, output = _run(tmp_path)
    tools = list(registry.definitions)
    tools[0] = replace(tools[0], description="A different capability contract.")
    with pytest.raises(SchemaViolation, match="tool definitions"):
        ReplayModel.from_loop(output.record, tuple(tools))
    versions = {
        "principles": output.record.identity.principles_version,
        "tools": digest("a moved source generation"),
        "matter": str(output.record.identity.matter_version),
    }
    with pytest.raises(SchemaViolation, match="tools/sources"):
        ReplayModel.from_loop(output.record, registry.definitions, versions=versions)


def test_actual_failed_dispatch_replays_its_exact_error_and_usage(tmp_path):
    usage = Usage(25, 10, 0.017, provider_extra={"response_id": "recorded-response"})
    error = ProviderUnavailable("A paid dispatch failed.", usage=usage, latency_ms=123, retries=2)
    registry, model, output = _run(tmp_path, error)
    replay = ReplayModel.from_loop(output.record, registry.definitions)
    request = model.tool_call.call_args
    with pytest.raises(ProviderUnavailable, match="paid dispatch") as observed:
        replay.tool_call(*request.args, **request.kwargs)
    assert observed.value.usage == usage
    assert observed.value.retries == 2 and observed.value.latency_ms == 123
    assert replay.position == 1 and model.tool_call.call_count == 1


@pytest.mark.parametrize("mutation", ["unknown_error", "missing_usage", "unknown_model"])
def test_a_resealed_failure_cannot_invent_missing_or_unknown_receipts(tmp_path, mutation):
    registry, _, output = _run(tmp_path, ProviderUnavailable("Unreachable provider."))

    def change(kind, payload):
        if kind is StepKind.FAILURE:
            assert "error" in payload and "usage" in payload["error"]
            if mutation == "unknown_error":
                payload["error"]["kind"] = "ImaginaryProviderFault"
            elif mutation == "missing_usage":
                del payload["error"]["usage"]
        if kind is StepKind.MODEL_STARTED and mutation == "unknown_model":
            assert "model" in payload
            payload["model"] = ""

    changed = _reseal(output.record, change)
    with pytest.raises(SchemaViolation):
        ReplayModel.from_loop(changed, registry.definitions)


def test_a_sealed_stop_without_a_model_receipt_is_not_replayable(tmp_path):
    registry, _, output = _run(tmp_path)
    kept = [
        event
        for event in output.record.events
        if event.kind in {StepKind.START, StepKind.MODEL_STARTED, StepKind.STOP}
    ]
    kept = [kept[0], kept[1], kept[-1]]
    previous, events = output.record.identity.fingerprint, []
    for index, event in enumerate(kept, 1):
        copied = LoopEvent.create(index, event.kind, event.at, event.payload, previous)
        events.append(copied)
        previous = copied.fingerprint
    record = LoopRecord(output.record.identity, tuple(events))
    with pytest.raises(SchemaViolation, match="without a result"):
        ReplayModel.from_loop(record, registry.definitions)


def test_an_empty_model_call_population_is_not_a_replay_pass(tmp_path):
    registry, _, output = _run(tmp_path)
    kept = [output.record.events[0], output.record.events[-1]]
    previous, events = output.record.identity.fingerprint, []
    for index, event in enumerate(kept, 1):
        copied = LoopEvent.create(index, event.kind, event.at, event.payload, previous)
        events.append(copied)
        previous = copied.fingerprint
    with pytest.raises(SchemaViolation, match="population"):
        ReplayModel.from_loop(
            LoopRecord(output.record.identity, tuple(events)), registry.definitions
        )
