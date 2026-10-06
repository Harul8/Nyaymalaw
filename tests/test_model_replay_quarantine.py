"""Completed rejected envelopes stay errors while owned rows remain inspectable."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    Usage,
)
from nm.shared.model_replay import RecordingModel, ReplayModel, _record_digest
from tests.model_quarantine_support import (
    PROMPT,
    SCHEMA,
    VERSIONS,
    adapter,
    recorded_failure,
)

pytestmark = pytest.mark.class_a


def test_replay_schema_quarantine_stays_the_same_failed_call_without_dispatch():
    recorder, original, calls = recorded_failure()
    record = recorder.records[0]
    assert "error" in record and "result" not in record
    assert set(record["error"]) == {
        "kind", "message", "usage", "latency_ms", "retries", "rejected_result",
    }
    replay = ReplayModel(json.loads(json.dumps(recorder.records)), versions=VERSIONS)
    recorder.records[0]["error"]["rejected_result"]["value"]["data"] = {}
    with pytest.raises(SchemaViolation) as caught:
        replay.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=512)
    assert caught.value.rejected_result == original.rejected_result
    assert caught.value.usage == original.usage
    assert replay.position == 1 and len(calls) == 1


@pytest.mark.parametrize("mutation", [
    "completion", "text", "nonobject", "tier", "provider", "model", "usage",
    "latency", "retries", "error_kind", "extra_result", "extra_error", "missing_usage",
    "now_valid", "missing_completion", "unknown_result", "null_result", "bad_usage",
])
def test_replay_refuses_resealed_quarantine_with_a_broken_boundary_receipt(mutation):
    recorder, _, _ = recorded_failure()
    row = copy.deepcopy(recorder.records[0])
    error = row["error"]
    result = error["rejected_result"]["value"]
    if mutation == "completion":
        result["completion"] = Completion.LENGTH_LIMITED.value
    elif mutation == "text":
        result["text"] = "An unreviewed assertion."
    elif mutation == "nonobject":
        result["data"] = []
    elif mutation == "tier":
        result["tier"] = Tier.JUDGE.value
    elif mutation in {"provider", "model"}:
        result[mutation] = "another-owner"
    elif mutation == "usage":
        result["usage"]["tokens_out"] += 1
    elif mutation in {"latency", "retries"}:
        result["latency_ms" if mutation == "latency" else mutation] += 1
    elif mutation == "error_kind":
        error["kind"] = "ProviderUnavailable"
    elif mutation == "extra_result":
        result["unknown"] = True
    elif mutation == "extra_error":
        error["unknown"] = True
    elif mutation == "missing_usage":
        del error["usage"]
    elif mutation == "now_valid":
        result["data"] = {"items": []}
    elif mutation == "missing_completion":
        del result["completion"]
    elif mutation == "unknown_result":
        error["rejected_result"]["kind"] = "ToolCallResult"
    elif mutation == "null_result":
        error["rejected_result"] = None
    else:
        error["usage"] = {"invented": 1}
    row["record_digest"] = _record_digest(row)
    replay = ReplayModel([row], versions=VERSIONS)
    with pytest.raises(SchemaViolation) as caught:
        replay.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=512)
    assert caught.value.rejected_result is None and replay.position == 0


@pytest.mark.parametrize("error_type", [SchemaViolation, ProviderUnavailable])
def test_replay_old_error_receipts_remain_compatible(error_type):
    model, _, _ = adapter("openai")
    usage = Usage(2, 1, 0.003)

    def fail(*args, **kwargs):
        raise error_type("Rejected before a quarantinable object.", usage=usage, retries=1)

    model.structured = fail
    recorder = RecordingModel(model, versions=VERSIONS)
    with pytest.raises(error_type):
        recorder.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert "rejected_result" not in recorder.records[0]["error"]
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    with pytest.raises(error_type) as caught:
        replay.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert caught.value.usage == usage and caught.value.retries == 1
    assert replay.position == 1


def test_replay_quarantine_is_not_reusable_for_another_schema_or_tier():
    recorder, _, _ = recorded_failure()
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    with pytest.raises(SchemaViolation, match="request/version"):
        replay.structured(PROMPT, SCHEMA, Tier.JUDGE, max_tokens=512)
    with pytest.raises(SchemaViolation, match="request/version"):
        replay.structured(PROMPT, {**SCHEMA, "additionalProperties": True}, Tier.ROUTINE,
                          max_tokens=512)
    assert replay.position == 0


def test_replay_quarantine_tampering_without_resealing_is_rejected():
    recorder, _, _ = recorded_failure()
    recorder.records[0]["error"]["rejected_result"]["value"]["data"]["items"] = []
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    with pytest.raises(SchemaViolation, match="integrity"):
        replay.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=512)
    assert replay.position == 0


def test_complete_replay_success_is_not_changed_by_quarantine_support():
    model, _, _ = adapter("openai", data={"items": []})
    recorder = RecordingModel(model, versions=VERSIONS)
    result = recorder.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    assert replay.structured(PROMPT, SCHEMA, Tier.ROUTINE) == result
    assert replay.position == 1


def test_quarantined_receipt_does_not_silently_downgrade_the_requested_tier():
    recorder, original, _ = recorded_failure()
    wrong_tier = replace(original.rejected_result, tier=Tier.JUDGE)
    row = recorder.records[0]
    row["error"]["rejected_result"]["value"]["tier"] = wrong_tier.tier.value
    row["record_digest"] = _record_digest(row)
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    with pytest.raises(SchemaViolation, match="failed-call receipt"):
        replay.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=512)
    assert replay.position == 0

