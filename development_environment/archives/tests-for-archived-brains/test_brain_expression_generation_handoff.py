"""Generation narrowing stays separate from canonical admission and v1 replay.

The exported continuation activity runs offline with complete rejected provider
objects and scripted independent judgments. These tests establish schema,
ownership, scoped recovery and call accounting, not real-model semantic quality,
atomic persistence or browser acceptance.
"""
import json
from copy import deepcopy

import pytest

from nm.brain import continuation
from nm.brain import evidence_rendering as rendering
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage, on_the_wire, require_schema
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import conversation_plan
from tests.test_brain_continuation_record_outcome import (
    evidence,
    material,
    no_record_requirement,
    run,
)
from tests.test_brain_expression_replay import check as check_saved
from tests.test_brain_expression_replay import fixture as saved_fixture


def _context():
    receipt = evidence()
    receipt["requests"].append({"request_index": 1,
                                "record_requirement": no_record_requirement()})
    plan = conversation_plan(items=conversation_plan().items * 2)
    payload, spans, records, sources = continuation._input(
        continuation.Conversation(()), "The handover was on 4 May.", plan,
        None, material(receipt), None, None, (), "current")
    return receipt, plan, payload, spans, records, sources


def _block(identity, operator, *, sources=(), records=(), focus="none"):
    return {"id": identity, "kind": "completion" if operator == "record_result" else "account",
            "uncertainty": "reported", "evidence_expression": {
                "operator": operator, "source_ids": list(sources),
                "record_ids": list(records), "focus": focus}}


def _units(payload, *, fault=None):
    effect = next(iter(payload["record_effect_catalogue"]))
    status = _block("status-0", "record_result")
    if fault == "source_ids":
        status["evidence_expression"]["source_ids"] = ["L1"]
    elif fault == "record_ids":
        status["evidence_expression"]["record_ids"] = list(payload["record_catalogue"])
    elif fault == "focus":
        status["evidence_expression"]["focus"] = "attribution"
    rows = []
    for index, block in ((0, status), (1, _block("account-1", "source_account", sources=("L1",)))):
        rows.append({
            "request_index": index, "blocks": [block], "questions": [], "next_work": [],
            "sufficiency": {"status": "partial", "block_id": block["id"]},
            "work_selector": "$new_task", "progress_updates": [],
            "record_outcome": {
                "status": "performed" if index == 0 else "none",
                "block_id": block["id"] if index == 0 else "",
                "effect_ids": [effect] if index == 0 else [], "current_record_ids": [],
                "reason": "The admitted operation represents this request." if index == 0 else "",
            },
        })
    return rows


class WireModel:
    """A complete provider object rejected for schema has a real quarantine receipt."""
    provider = "offline"

    def __init__(self, *, fault=None):
        self.fault = fault
        self.calls = []
        self.schemas = []
        self.rejected_objects = []

    def context_budget(self, tier):
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, deepcopy(payload)))
        self.schemas.append(deepcopy(schema))
        if prompt.operation == "continue_conversation":
            rows = _units(payload, fault=self.fault if "correction" not in payload else None)
            indexes = {row["request_index"] for row in payload["work_items"]}
            data = {"units": [row for row in rows if row["request_index"] in indexes]}
        else:
            assert prompt.operation == "verify_continuation"
            data = reviewed_verdicts(payload, {"verdicts": [{
                "request_index": row["request_index"], "verdict": "accept",
                "reason": "The independently scripted unit preserves this scoped evidence.",
                "record_check": {
                    "outcome": "fulfilled" if row["request_index"] == 0 else "not_requested",
                    "reason": "The actual owned operation supports the selected status.",
                },
            } for row in payload["units"]]})
            # Supply the live verdict-specific wire, retaining the authored
            # checks. The collection owns acceptance; no repeated label or
            # inapplicable retained-subset metadata is emitted.
            data = {"accepted_units": [{key: value for key, value in row.items()
                                        if key not in {"verdict", "retained_block_ids",
                                                       "retained_reason"}}
                                       for row in data["verdicts"]], "rejected_units": []}
        result = ModelResult(text=None, data=data, tier=tier, provider="offline",
                             model="offline", usage=Usage(0, 0, 0), latency_ms=0,
                             completion=Completion.COMPLETE)
        try:
            require_schema(data, schema)
        except SchemaViolation as exc:
            self.rejected_objects.append(deepcopy(data))
            raise SchemaViolation(str(exc), rejected_result=result) from exc
        return result


def test_writer_schema_uses_generation_branches_and_compiles_as_provider_wire():
    _, _, payload, spans, records, sources = _context()
    before = deepcopy((spans, records, sources))
    schema = continuation._schema((0, 1), spans, records, sources,
                                  effect_ids=tuple(payload["record_effect_catalogue"]))
    selected = schema["properties"]["units"]["items"]["properties"]["blocks"]["items"][
        "properties"]["evidence_expression"]
    assert selected == rendering.expression_schema(spans, records, sources, generation=True)
    assert "anyOf" in selected
    assert on_the_wire(schema) == schema
    assert (spans, records, sources) == before


@pytest.mark.parametrize("fault", ["source_ids", "record_ids", "focus"])
def test_canonical_admission_localizes_owned_but_inapplicable_expression_and_keeps_peer(
        monkeypatch, fault):
    receipt, _, payload, spans, records, sources = _context()
    raw = {"units": _units(payload, fault=fault)}
    before = deepcopy(raw)
    calls = []
    original = continuation.expression_schema

    def traced(*args, **kwargs):
        calls.append(kwargs.get("generation", False))
        return original(*args, **kwargs)

    monkeypatch.setattr(continuation, "expression_schema", traced)
    local = {}
    valid, issues = continuation._read_units(
        raw, (0, 1), spans, records, sources, intents={0: "request", 1: "request"},
        local_failures=local, execution_receipt=receipt)
    assert list(valid) == [1]
    assert set(issues) == set(local) == {0}
    assert set(local[0][1]) == {"status-0"}
    assert calls == [False, False]
    assert valid[1]["blocks"][0]["text"] == 'Your message includes: “The handover was on 4 May.”'
    assert raw == before


@pytest.mark.parametrize("fault", ["source_ids", "record_ids", "focus"])
def test_complete_generation_rejection_repairs_only_failed_writer_request_after_peer_review(fault):
    receipt, plan, _, _, _, _ = _context()
    before = deepcopy(receipt)
    model = WireModel(fault=fault)
    result = run(model, receipt, plan=plan)
    assert [operation for operation, _ in model.calls] == [
        "continue_conversation", "verify_continuation",
        "continue_conversation", "verify_continuation"]
    assert len(model.rejected_objects) == 1
    assert [row["request_index"] for row in model.rejected_objects[0]["units"]] == [0, 1]
    first_review = model.calls[1][1]
    assert [row["request_index"] for row in first_review["units"]] == [1]
    correction = model.calls[2][1]
    assert [row["request_index"] for row in correction["work_items"]] == [0]
    assert [row["request_index"] for row in correction["correction"]["validation_issues"]] == [0]
    assert [row["request_index"] for row in correction["correction"]["rejected_units"]] == [0]
    assert correction["correction"]["rejected_units"][0] == model.rejected_objects[0]["units"][0]
    assert [row["request_index"] for row in model.calls[3][1]["units"]] == [0]
    assert [row["request_index"] for row in result.units] == [0, 1]
    assert [row["state"] for row in result.coverage] == ["ok", "ok"]
    expected_peer = deepcopy(first_review["units"][0]["blocks"])
    expected_peer[0]["references"] = [{
        "type": "conversation", "id": "L1", "role": "advocate",
        "text": "The handover was on 4 May.", "turn_id": "current"}]
    assert result.units[1]["blocks"] == expected_peer
    status = result.units[0]
    assert status["record_outcome"]["status"] == "performed"
    assert status["record_outcome"]["effect_ids"] == list(correction["record_effect_catalogue"])
    assert status["blocks"][0]["evidence_expression"] == {
        "operator": "record_result", "source_ids": [], "record_ids": [], "focus": "none"}
    assert receipt == before


def test_valid_account_and_owned_status_need_only_routine_writer_and_independent_review():
    receipt, plan, _, _, _, _ = _context()
    model = WireModel()
    result = run(model, receipt, plan=plan)
    assert [operation for operation, _ in model.calls] == [
        "continue_conversation", "verify_continuation"]
    assert model.rejected_objects == []
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [0, 1]
    assert [row["state"] for row in result.coverage] == ["ok", "ok"]
    assert result.units[0]["record_check"]["outcome"] == "fulfilled"
    assert result.units[0]["blocks"][0]["text"]
    assert result.units[1]["blocks"][0]["text"] == (
        'Your message includes: “The handover was on 4 May.”')


def test_saved_v1_reconstruction_keeps_original_contract_and_uses_canonical_schema(monkeypatch):
    block, row, words = saved_fixture()
    before = deepcopy((block, row, words))
    calls = []
    original = rendering.expression_schema

    def traced(*args, **kwargs):
        calls.append(kwargs.get("generation", False))
        return original(*args, **kwargs)

    monkeypatch.setattr(rendering, "expression_schema", traced)
    check_saved(block, row, words)
    assert calls and not any(calls)
    assert block["expression_contract"] == "evidence_expression_v1"
    assert (block, row, words) == before
