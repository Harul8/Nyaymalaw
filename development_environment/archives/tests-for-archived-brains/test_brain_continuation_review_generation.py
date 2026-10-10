"""Accepted generation binds disposition; rejection and canonical review stay open.

Offline authored verdicts exercise the existing review boundary, mechanical
matching and scoped recovery. They do not establish that a real Judge detects
incorrect effects or that a useful reply is persisted and browser-observed.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import continuation as writer
from nm.brain import continuation_verification as reviewer
from nm.brain.conversation import Conversation, Message
from nm.brain.execution_contracts import effect_catalogue
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    on_the_wire,
    require_schema,
)
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import conversation_plan, unit, verdict
from tests.test_brain_continuation_record_outcome import evidence, material

MATCHES = {
    "none": "not_requested", "performed": "fulfilled", "already_current": "fulfilled",
    "review_no_change": "no_change_justified", "unresolved": "unfinished",
}
DISPOSITIONS = ("fulfilled", "no_change_justified", "unfinished", "not_requested")
WRONG = {
    "none": "fulfilled", "performed": "not_requested", "already_current": "unfinished",
    "review_no_change": "fulfilled", "unresolved": "fulfilled",
}


def proposed(status="none", *, index=0):
    """Schema-only owner; no execution is inferred from this authored declaration."""
    row = unit(index)
    row["record_outcome"] = {
        "status": status, "block_id": "" if status == "none" else f"account-{index}",
        "effect_ids": [], "current_record_ids": [],
        "reason": "" if status == "none" else "The authored schema fixture disposition.",
    }
    return row


def _input():
    return {"legal_sources": {}, "progress": {"state": "ok", "rows": []}}


def legacy_row(row, outcome, *, accept=True):
    payload = {"input": _input(), "units": [row]}
    data = reviewed_verdicts(payload, verdict(row["request_index"], accept=accept))
    result = data["verdicts"][0]
    result["record_check"] = {
        "outcome": outcome, "reason": "The independent authored disposition for this result."}
    return result


def wire_row(row, outcome, *, accept=True):
    result = legacy_row(row, outcome, accept=accept)
    result.pop("verdict")
    if accept:
        result.pop("retained_block_ids")
        result.pop("retained_reason")
    return result


def _schema(*rows):
    return reviewer._schema(tuple(row["request_index"] for row in rows),
                            {row["request_index"]: row for row in rows}, _input()["progress"])


@pytest.mark.parametrize("status", MATCHES)
def test_accepted_generation_admits_the_matching_disposition(status):
    row = proposed(status)
    data = {"accepted_units": [wire_row(row, MATCHES[status])], "rejected_units": []}
    original = deepcopy(data)
    require_schema(data, _schema(row))
    assert data == original


@pytest.mark.parametrize("status", MATCHES)
def test_accepted_generation_excludes_conflicting_disposition_for_this_request(status):
    row = proposed(status)
    data = {"accepted_units": [wire_row(row, WRONG[status])], "rejected_units": []}
    with pytest.raises(SchemaViolation):
        require_schema(data, _schema(row))


@pytest.mark.parametrize("status", MATCHES)
def test_rejected_generation_keeps_every_actual_disposition_including_conflicts(status):
    row = proposed(status)
    schema = _schema(row)
    for actual in DISPOSITIONS:
        data = {"accepted_units": [], "rejected_units": [wire_row(row, actual, accept=False)]}
        original = deepcopy(data)
        require_schema(data, schema)
        assert data == original


@pytest.mark.parametrize("status", MATCHES)
def test_canonical_and_legacy_transport_keep_all_dispositions_without_generation_repair(status):
    row = proposed(status)
    for actual in DISPOSITIONS:
        old = legacy_row(row, actual)
        accepted = wire_row(row, actual)
        rejected = wire_row(row, actual, accept=False)
        before = deepcopy((old, accepted, rejected))
        require_schema(old, reviewer._VERDICT)
        assert reviewer._transport_row("legacy", old) == old
        assert reviewer._transport_row("accepted_units", accepted) == old
        normalized = reviewer._transport_row("rejected_units", rejected)
        assert normalized == {**rejected, "verdict": "reject"}
        assert (old, accepted, rejected) == before


def test_each_native_accepted_branch_binds_its_own_request_and_record_disposition():
    rows = [proposed(status, index=index) for index, status in enumerate(MATCHES)]
    schema = _schema(*rows)
    items = schema["properties"]["accepted_units"]["items"]
    branches = items["anyOf"]
    assert len(branches) == len(rows)
    expected = {row["request_index"]: MATCHES[row["record_outcome"]["status"]] for row in rows}
    observed = {}
    for branch in branches:
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"])
        properties = branch["properties"]
        index, = properties["request_index"]["enum"]
        actual, = properties["record_check"]["properties"]["outcome"]["enum"]
        observed[index] = actual
        assert not {"verdict", "retained_block_ids", "retained_reason"} & properties.keys()
    assert observed == expected
    good = [wire_row(row, expected[row["request_index"]]) for row in rows]
    require_schema({"accepted_units": good, "rejected_units": []}, schema)
    wrong = deepcopy(good)
    wrong[0]["record_check"]["outcome"] = good[1]["record_check"]["outcome"]
    with pytest.raises(SchemaViolation):
        require_schema({"accepted_units": wrong, "rejected_units": []}, schema)


def test_nested_generation_schema_is_provider_compatible_without_changing_sources_or_canonical():
    rows = [proposed(status, index=index) for index, status in enumerate(MATCHES)]
    before = deepcopy(rows), deepcopy(reviewer._VERDICT), deepcopy(reviewer._RECORD_CHECK)
    schema = _schema(*rows)
    wire = on_the_wire(schema)
    require_schema({"accepted_units": [wire_row(row, MATCHES[row["record_outcome"]["status"]])
                                       for row in rows], "rejected_units": []}, wire)
    assert (rows, reviewer._VERDICT, reviewer._RECORD_CHECK) == before
    assert reviewer._RECORD_CHECK["properties"]["outcome"]["enum"] == list(DISPOSITIONS)


class ReviewModel:
    """Only the independent review call runs; replies use its actual wire schema."""
    provider = "offline"

    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []
        self.claims = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def claim_recovery(self, phase):
        self.claims.append(phase)
        return True

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        assert prompt.operation == "verify_continuation"
        payload = json.loads(prompt.user)
        self.calls.append((deepcopy(payload), deepcopy(schema)))
        reply = next(self.replies)
        data = reply(payload) if callable(reply) else deepcopy(reply)
        require_schema(data, schema)
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def test_read_only_current_record_recap_is_accepted_once_without_effect_or_fresh_extraction():
    old = "The handover was on 4 May."
    conversation = Conversation((Message("original", "advocate", old),),
                                current_matter_id="matter")
    plan = conversation_plan(items=(replace(
        conversation_plan().items[0], request="Recap the current record", next_step="answer"),))
    state = material(evidence())
    state["rows"][0]["source_turn_id"] = "original"
    state["coverage"] = {"state": "ok"}
    payload, spans, records, sources = writer._input(
        conversation, "Please recap what is already recorded.", plan,
        None, state, None, None, (), "current")
    raw = {
        "request_index": 0,
        "blocks": [{"id": "recap", "kind": "account", "uncertainty": "reported",
                    "evidence_expression": {"operator": "source_account", "source_ids": [],
                                            "record_ids": ["saved-observation"], "focus": "none"}}],
        "questions": [], "next_work": [], "progress_updates": [],
        "sufficiency": {"status": "complete", "block_id": "recap"},
        "work_selector": "$new_task", "record_outcome": {
            "status": "none", "block_id": "", "effect_ids": [],
            "current_record_ids": [], "reason": ""},
    }
    admitted, issues = writer._read_units(
        {"units": [raw]}, (0,), spans, records, sources, intents={0: "request"})
    assert issues == {} and admitted[0]["blocks"][0]["record_ids"] == ["saved-observation"]
    model = ReviewModel({"accepted_units": [wire_row(admitted[0], "not_requested")],
                         "rejected_units": []})
    result = reviewer.verify_continuation(model, input_payload=payload,
                                          units=(admitted[0],))
    assert result.decisions[0][0] and result.unavailable == ()
    assert len(model.calls) == 1 and model.claims == []
    assert result.reviewed[0]["record_check"]["outcome"] == "not_requested"
    assert payload["record_effect_catalogue"] == {}


def test_rejected_actual_effect_conflict_preserves_valid_no_effect_peer_without_retry():
    bad, peer = proposed("performed"), proposed("none", index=1)
    model = ReviewModel({"accepted_units": [wire_row(peer, "not_requested")],
                         "rejected_units": [wire_row(bad, "unfinished", accept=False)]})
    result = reviewer.verify_continuation(model, input_payload=_input(), units=(bad, peer))
    assert result.decisions[0][0] is False and result.decisions[1][0] is True
    assert result.unavailable == () and result.retained == {}
    assert result.reviewed[0]["record_check"]["outcome"] == "unfinished"
    assert "Record result differs" in result.decisions[0][1]
    assert len(model.calls) == 1 and model.claims == []


def test_wrong_accepted_disposition_remains_a_canonical_rejection_not_an_inferred_repair():
    bad, peer = proposed("none"), proposed("none", index=1)

    class CanonicalProvider(ReviewModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            # Explicit internal/historical transport, not a live generation
            # option. Per-unit admission must still reject its contradiction.
            self.calls.append((json.loads(prompt.user), deepcopy(schema)))
            return ModelResult(text=None, data={"verdicts": [
                legacy_row(bad, "fulfilled"), legacy_row(peer, "not_requested")]},
                tier=tier, provider="offline", model="offline", usage=Usage(0, 0, 0),
                latency_ms=0, completion=Completion.COMPLETE)

    model = CanonicalProvider()
    result = reviewer.verify_continuation(model, input_payload=_input(), units=(bad, peer))
    assert result.decisions[0][0] is False and result.decisions[1][0] is True
    assert result.reviewed[0]["record_check"]["outcome"] == "fulfilled"
    assert result.unavailable == () and len(model.calls) == 1 and model.claims == []


def test_matching_generated_disposition_cannot_accept_an_unrelated_admitted_effect():
    requirement = {"kind": "change", "operation": "corrects", "target_ids": ["older-entry"],
                   "success_condition": "Correct the existing entry against its original account."}
    receipt = evidence(record_requirement=requirement)
    receipt["requests"].append({"request_index": 1, "record_requirement": {
        "kind": "none", "operation": "none", "target_ids": [], "success_condition": ""}})
    effects = effect_catalogue(receipt)
    identity, = effects
    assert effects[identity]["performed"] is True
    # Real admitted result, different requested effect.
    assert effects[identity]["relation"] == "new"
    bad, peer = proposed("performed"), proposed("none", index=1)
    bad["record_outcome"]["effect_ids"] = [identity]
    payload = {**_input(), "material_coverage": {"execution": receipt},
               "record_effect_catalogue": effects, "work_items": deepcopy(receipt["requests"])}
    model = ReviewModel({"accepted_units": [wire_row(bad, "fulfilled"),
                                            wire_row(peer, "not_requested")], "rejected_units": []})
    result = reviewer.verify_continuation(model, input_payload=payload, units=(bad, peer))
    assert result.decisions[0][0] is False and result.decisions[1][0] is True
    assert result.unavailable == () and len(model.calls) == 1 and model.claims == []
    assert result.reviewed[0]["record_check"]["outcome"] == "fulfilled"
    assert "target" in result.decisions[0][1] or "operation" in result.decisions[0][1]


def test_shape_valid_foreign_block_check_repairs_only_unread_owner_and_preserves_peer():
    first, second = proposed("none"), proposed("unresolved", index=1)
    wrong = wire_row(second, "unfinished")
    # The shared catalogue offers this existing block. It belongs to the peer,
    # so exact per-unit check coverage must still refuse its use here.
    wrong["block_checks"][0]["block_id"] = first["blocks"][0]["id"]
    first_wire = wire_row(first, "not_requested")
    model = ReviewModel({"accepted_units": [first_wire, wrong], "rejected_units": []},
                        {"accepted_units": [wire_row(second, "unfinished")],
                         "rejected_units": []})
    result = reviewer.verify_continuation(model, input_payload=_input(), units=(first, second))
    assert result.decisions[0][0] and result.decisions[1][0]
    assert result.unavailable == () and len(model.calls) == 2
    assert model.claims == ["verify_continuation:correction"]
    repair = model.calls[1][0]
    assert [row["request_index"] for row in repair["units"]] == [1]
    assert [row["request_index"] for row in repair["validation_issues"]] == [1]
    assert reviewer._transport_row("accepted_units", first_wire) == result.reviewed[0]
