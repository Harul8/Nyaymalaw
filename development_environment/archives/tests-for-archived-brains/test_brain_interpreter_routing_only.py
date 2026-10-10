"""Interpretation routes requested work; checked continuation owns public words.

Inputs, routes and model outputs are independently authored offline fixtures.
Removing discarded draft fields must preserve consequential decision checks.
"""
import json
from collections import deque
from copy import deepcopy

import pytest

from nm.brain.conversation import Conversation, _turn_plan, interpret
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests.brain_continuation_fixture import scripted_message_labels, transport_message_parts
from tests.test_brain_continuation_service import FIXTURE_SOURCE_PURPOSES, send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit, reopened


def route(step="answer"):
    return {
        "message_parts": [{"category": "work_request", "selections": [
            {"source_id": "$message", "whole_source": True}]}],
        "items": [{
            "request": "Explain the uncertainty in the attributed collection account.",
            "relation": "new", "matter_scope": "none", "priority": "ordinary",
            "next_step": step, "intent": "request", "response_mode": "substantive",
            "response_basis": "legal_authority" if step == "legal_work" else "conversation_record",
            "research_question": "Which legal rule applies?" if step == "legal_work" else "",
            "material_purposes": [], "mutation_scopes": [],
            "record_requirement": {
                "kind": "none", "target_ids": [], "operation": "none", "success_condition": "",
            },
        }],
        "opening": {"ready": False, "party_name": "", "subject": "", "summary": ""},
    }


class RoutingModel:
    def __init__(self, outputs):
        self.outputs = deque(outputs)
        self.calls = []

    def context_budget(self, tier):
        return 100000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        assert tier == (Tier.ROUTINE if prompt.operation == "label_message" else Tier.JUDGE)
        self.calls.append((prompt, deepcopy(schema)))
        payload = json.loads(prompt.user)
        original = payload.get("original_input", payload)
        data = (scripted_message_labels(self.outputs[0], original)
                if prompt.operation == "label_message" else
                transport_message_parts(self.outputs.popleft(), original))
        return ModelResult(
            text=None, data=data, tier=tier,
            provider="offline", model="offline", usage=Usage(0, 0, 0),
            latency_ms=0, completion=Completion.COMPLETE,
        )


@pytest.mark.parametrize("step", ["answer", "legal_work", "clarify"])
def test_routes_without_disposable_drafts_need_one_interpretation(step):
    data = route(step)
    original = deepcopy(data)
    model = RoutingModel([data])
    plan = interpret(model, Conversation(()), "Collection remains uncertain.")
    item, = plan.items
    assert item.next_step == step and item.request == data["items"][0]["request"]
    assert item.reply == item.clarification == ""
    assert item.record_requirement == data["items"][0]["record_requirement"]
    assert item.mutation_scopes == () and not plan.material_review
    assert len(model.calls) == 2 and data == original
    assert [call[0].operation for call in model.calls] == [
        "label_message", "interpret_conversation"]
    assert not {"message_parts", "message_labels"}.intersection(model.calls[1][1]["properties"])
    for decisions in model.calls[1][1]["properties"]["items"]["items"]["anyOf"]:
        assert not {"reply", "clarification"}.intersection(decisions["properties"])
        assert not {"reply", "clarification"}.intersection(decisions["required"])


@pytest.mark.parametrize("field", ["reply", "clarification"])
def test_fresh_provider_extra_draft_is_rejected_then_corrected_under_same_contract(field):
    bad, corrected = route(), route()
    bad["items"][0][field] = "I changed the saved date and completed the work."
    model = RoutingModel([bad, corrected])
    result = interpret(model, Conversation(()), "Explain the uncertainty.")
    assert result.items[0].reply == result.items[0].clarification == ""
    assert len(model.calls) == 3
    feedback = json.loads(model.calls[2][0].user)
    assert "result.items[0]" in feedback["validation_issue"]
    assert "undeclared properties" in feedback["validation_issue"]
    assert feedback["rejected_output"] == transport_message_parts(bad, feedback["original_input"])
    assert model.calls[1][1] == model.calls[2][1]


@pytest.mark.parametrize("field", ["message_parts", "message_labels"])
def test_planner_cannot_replace_classifier_labels_and_correction_preserves_their_owner(field):
    class LabelOverrideModel(RoutingModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "interpret_conversation" and sum(
                    call[0].operation == "interpret_conversation" for call in self.calls) == 1:
                result.data[field] = [{"category": "social", "sources": []}]
            return result

    declared = route()
    declared["message_parts"][0]["category"] = "information"
    model = LabelOverrideModel([declared, declared])
    latest = "The recipient is uncertain."

    plan = interpret(model, Conversation(()), latest)

    assert [call[0].operation for call in model.calls] == [
        "label_message", "interpret_conversation", "interpret_conversation"]
    assert [part["category"] for part in plan.message_parts] == ["information"]
    assert plan.message_parts[0]["sources"][0]["text"] == latest
    feedback = json.loads(model.calls[2][0].user)
    assert "undeclared properties" in feedback["validation_issue"]
    assert "'result'" in feedback["validation_issue"]
    assert feedback["rejected_output"][field] == [{"category": "social", "sources": []}]
    assert feedback["original_input"] == json.loads(model.calls[1][0].user)


@pytest.mark.parametrize("field", ["reply", "clarification"])
def test_internal_legacy_constructor_data_cannot_retain_discarded_response_words(field):
    data = route()
    data["items"][0][field] = "The revision was saved and the requested work is complete."
    before = deepcopy(data)
    item, = _turn_plan(data, Conversation(()), latest="Explain uncertainty.").items
    assert item.reply == item.clarification == ""
    assert item.request == before["items"][0]["request"]
    assert item.record_requirement == before["items"][0]["record_requirement"]
    assert data == before


@pytest.mark.parametrize("fault", [
    "missing_record_requirement", "contradictory_operation", "foreign_target",
    "wrong_acknowledgement",
])
def test_draft_removal_preserves_consequential_contract_rejections(fault):
    data = route()
    item = data["items"][0]
    if fault == "missing_record_requirement":
        del item["record_requirement"]
    elif fault == "contradictory_operation":
        item["record_requirement"]["operation"] = "corrects"
    elif fault == "foreign_target":
        item["record_requirement"]["target_ids"] = ["foreign-record"]
    else:
        item["response_mode"] = "record_acknowledgement"
    with pytest.raises(SchemaViolation):
        _turn_plan(data, Conversation(()), latest="Explain uncertainty.")


def test_fixture_preparation_removes_only_discarded_item_fields_and_preserves_authority():
    from tests.brain_continuation_fixture import prepare_interpretation

    data = route()
    data["items"][0].update(reply="Legacy draft", clarification="Legacy question",
                            deliberately_invalid="Keep this attack")
    original = deepcopy(data)
    prepared = prepare_interpretation(data)
    expected = deepcopy(data)
    del expected["items"][0]["reply"], expected["items"][0]["clarification"]
    assert prepared == expected and data == original
    assert prepared["items"][0]["mutation_scopes"] == []
    assert prepared["items"][0]["record_requirement"]["kind"] == "none"


@pytest.mark.parametrize("step", ["answer", "clarify"])
def test_public_routing_only_reply_is_checked_saved_and_replayed_without_model_calls(
        client, wired, monkeypatch, step):
    message = "Hello." if step == "answer" else "Clarify the reference in my request."
    # This routing-only fixture supplies social/instruction content, not a new
    # attributed matter account. The independent reader receives that decision.
    monkeypatch.setitem(FIXTURE_SOURCE_PURPOSES, message, "non_account")

    def writer(payload):
        assert all(not {"reply", "clarification"}.intersection(item)
                   for item in payload["work_items"])
        unit = raw_unit(payload, operator="acknowledgment", kind="acknowledgment",
                        all_sources=False) if step \
            == "answer" else raw_unit(payload, operator="question", kind="question",
                                     focus="certainty", questions=True)
        return {"units": [unit]}

    declared = route(step)
    declared["message_parts"][0]["category"] = "social" if step == "answer" else "work_request"
    declared["items"][0]["request"] = (
        "Acknowledge this greeting." if step == "answer" else "Clarify the reported uncertainty.")
    model = RawExpressionModel([declared], [writer])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    turn_id = "routing-only-" + step
    answer = send(client, message, turn_id)
    assert answer["blocked"] is False and answer["metrics"]["llm_calls"] == 4
    assert [op for op, _ in model.calls] == [
        "label_message", "interpret_conversation", "continue_conversation", "verify_continuation",
    ]
    assert answer["material_coverage"]["execution"]["record_changes"] == []
    saved = reopened(wired, answer)
    assert saved.brain_chat[-1]["message"] == message
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    count = len(model.calls)
    replay = send(client, message, turn_id)
    assert replay["replayed"] and replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == count and replay["elements"] == answer["elements"]
    assert reopened(wired, answer) == saved
