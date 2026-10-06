"""Completion labels and proposal links cannot reopen the fresh text escape.

All writer replies use the raw fresh schema. The reviewer deliberately accepts
every supplied block. Original source and effect meaning is scripted offline;
these regressions certify release mechanics, not real-model interpretation.
"""
import json
from copy import deepcopy

import pytest

from nm.brain import turn as boundary
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.brain_reader_fixture import reader_operations
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import (
    RawExpressionModel,
    expression,
    raw_unit,
    reopened,
    visible,
)
from tests.test_brain_material import _with_source_ids, material
from tests.test_brain_turn import plan

ORIGINAL = "The cartons arrived on 17 April."
CORRECTION = "Correct the carton arrival date to 19 April, preserving the earlier attribution."
LIE = "I corrected the arrival to 19 April, saved the revision and completed your requested work."


class DatedSeedModel(RawExpressionModel):
    """Own one source-supported initial record; keep its writer entirely raw."""

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation != "extract_legal_details":
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.schemas.append((prompt.operation, deepcopy(schema)))
        self.tiers.append(tier)
        source = payload.get("original_input", payload)
        candidate = _with_source_ids(
            material("event", ORIGINAL, ORIGINAL, placement="matter"), source)
        data = reader_operations([candidate], source, link_field="related_material_ids")
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline", model="offline",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE,
        )


def seed(client, wired, monkeypatch, turn_id):
    route = plan(
        ORIGINAL, scope="proposed", title="Carton arrival account", summary=ORIGINAL,
        material_purposes=("account_contribution",))
    model = DatedSeedModel([route], [lambda payload: {"units": [raw_unit(payload)]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, ORIGINAL, turn_id + "-seed")
    saved = reopened(wired, opened)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    before = deepcopy(conversation.open_material)
    assert before, "The matrix must preserve an actual saved predecessor."
    target, = [row["id"] for row in before if row["statement"] == ORIGINAL]
    return opened, before, target


def linked_unit(payload, section, *, record_status, record_owner=False, forged_text=False,
                complete=False):
    unit = raw_unit(payload, record_status=record_status)
    selected = [row["id"] for row in payload["latest_message_spans"]]
    operator = "record_result" if record_owner else (
        "question" if section == "questions" else "next_work")
    # A completion label was sufficient for the old linked-owner bypass. The
    # expression now controls displayed meaning, regardless of that label.
    block = {
        "id": "linked-owner", "kind": "completion", "uncertainty": "reported",
        "evidence_expression": expression(
            operator, sources=() if record_owner else selected,
            focus="none" if record_owner else "chronology"),
    }
    if forged_text:
        block["text"] = LIE
    unit["blocks"] = [block]
    unit[section] = [{
        "id": "linked-proposal", "block_id": "linked-owner",
        "purpose": "Examine the chronology of the referenced arrival account.",
        "target_ids": [], "existing_id": "",
    }]
    unit["record_outcome"]["block_id"] = "linked-owner" if record_status != "none" else ""
    unit["sufficiency"] = {
        "status": ("complete" if complete else
                   "needs_input" if section == "questions" else "partial"),
        "block_id": "linked-owner",
    }
    unit["progress_updates"] = [{
        "target_id": "$work", "status": "complete", "block_id": "linked-owner",
        "reason": "The requested correction has been completed.", "span_ids": selected,
    }] if complete else []
    return unit


def verify_saved_and_replayed(client, wired, model, answer, opened, before, turn_id):
    assert answer["blocked"] is False
    assert LIE not in visible(answer)
    saved = reopened(wired, answer)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    assert conversation.open_material == before
    assert answer["material_coverage"]["execution"]["record_changes"] == []
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    assert saved.brain_chat[-1]["elements"] == answer["elements"]
    assert LIE not in "\n".join(element["text"] for element in saved.brain_chat[-1]["elements"])
    assert LIE not in json.dumps(saved.brain_chat[-1], ensure_ascii=False)
    writers = [operation for operation, _ in model.calls if operation == "continue_conversation"]
    assert len(writers) == 2
    reviews = [operation for operation, _ in model.calls if operation == "verify_continuation"]
    assert len(reviews) == 1
    saved_version = saved.version
    before_calls = len(model.calls)
    repeated = send(client, CORRECTION, turn_id, opened=opened)
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    assert repeated["elements"] == answer["elements"]
    assert len(model.calls) == before_calls
    assert reopened(wired, answer).version == saved_version


@pytest.mark.parametrize("response_mode", ["substantive", "record_acknowledgement"])
@pytest.mark.parametrize("section", ["questions", "next_work"])
def test_raw_completion_lie_cannot_escape_through_a_linked_owner_in_either_response_mode(
        client, wired, monkeypatch, response_mode, section):
    turn_id = "completion-link-" + response_mode + "-" + section
    opened, before, target = seed(client, wired, monkeypatch, turn_id)
    route = plan(
        CORRECTION, scope="current", relation="continues",
        material_purposes=("account_contribution",),
        record_requirement={"kind": "change", "target_ids": [target],
                            "operation": "corrects",
                            "success_condition": "The dated entry represents the requested "
                            "19 April correction."})
    route["items"][0].update(response_mode=response_mode, mutation_scopes=[{
        "authority_kind": "account_contribution", "authority_source_ids": ["L1"],
        "target_scope": "exact", "target_ids": [target], "permitted_relations": ["corrects"],
    }])

    def first(payload):
        return {"units": [linked_unit(
            payload, section, record_status="unresolved", record_owner=True, forged_text=True)]}

    def corrected(payload):
        assert LIE in json.dumps(payload["correction"]["rejected_units"])
        return {"units": [linked_unit(payload, section, record_status="unresolved")]}

    model = RawExpressionModel([route], [first, corrected])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, CORRECTION, turn_id, opened=opened)
    verify_saved_and_replayed(client, wired, model, answer, opened, before, turn_id)
    assert "requested record work remains unfinished" in visible(answer)
    unit, = answer["continuation"]["units"]
    assert unit[section][0]["block_id"] == "linked-owner"
    owner = next(block for block in unit["blocks"] if block["id"] == "linked-owner")
    assert owner["evidence_expression"]["operator"] == (
        "question" if section == "questions" else "next_work")
    assert CORRECTION in owner["text"]
    assert unit["record_outcome"]["block_id"] != "linked-owner"
    assert answer["material_coverage"]["execution"]["requests"][0]["fulfillment"] == "unfinished"


@pytest.mark.parametrize("section", ["questions", "next_work"])
@pytest.mark.parametrize("attack", ["literal", "record_result"])
def test_interpreter_none_miss_without_readers_cannot_authorize_linked_false_completion(
        client, wired, monkeypatch, section, attack):
    turn_id = "completion-none-miss-" + section + "-" + attack
    opened, before, _target = seed(client, wired, monkeypatch, turn_id)
    # Preserve the deliberately wrong interpretation. This test must not
    # declare a record change merely because the original words requested one.
    route = plan(CORRECTION, scope="current", relation="continues")
    assert route["items"][0]["record_requirement"]["kind"] == "none"
    assert route["items"][0]["material_purposes"] == []

    def first(payload):
        requirement = payload["material_coverage"]["execution"]["requests"][0]["record_requirement"]
        assert requirement["kind"] == "none"
        return {"units": [linked_unit(
            payload, section, record_status="none", record_owner=attack == "record_result",
            forged_text=attack == "literal", complete=True)]}

    def corrected(payload):
        rejected, = payload["correction"]["rejected_units"]
        if attack == "literal":
            assert rejected["blocks"][0]["text"] == LIE
        else:
            assert rejected["blocks"][0]["evidence_expression"]["operator"] == "record_result"
        return {"units": [linked_unit(payload, section, record_status="none")]}

    model = RawExpressionModel([route], [first, corrected])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, CORRECTION, turn_id, opened=opened)
    verify_saved_and_replayed(client, wired, model, answer, opened, before, turn_id)
    assert not any(operation in (
        "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding") for operation, _ in model.calls)
    assert "No changes were made to the saved record." in visible(answer)
    unit, = answer["continuation"]["units"]
    assert unit["record_outcome"]["status"] == "none"
    assert unit["progress_updates"] == []
    assert unit["sufficiency"]["status"] != "complete"
    assert CORRECTION in next(block for block in unit["blocks"]
                              if block["id"] == "linked-owner")["text"]
