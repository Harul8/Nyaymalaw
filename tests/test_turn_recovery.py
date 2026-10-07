"""One shared correction allowance through the authenticated current-brain edge."""
import json

import pytest

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    Usage,
)
from tests.test_current_brain_app import (
    OPERATIONS,
    Harness,
    WiredModel,
    assert_ok,
    greeting_outputs,
)


def invented_review():
    return {"greeting": True, "unit_reviews": [
        {"unit_id": "current", "verdict": "supported", "source_ids": ["current"],
         "reason": "none"}], "omissions": []}


def invalid_provider_review():
    rejected = ModelResult(text=None, data=invented_review(), tier=Tier.ROUTINE,
        provider="scripted", model="scripted-1", usage=Usage(11, 7, 0),
        latency_ms=1, completion=Completion.COMPLETE)
    return SchemaViolation("$.unit_reviews: more than 0 items", rejected_result=rejected)


@pytest.mark.parametrize("rejection", ["reader", "provider"])
def test_invalid_review_repairs_once_with_original_input_and_feedback(tmp_path, rejection):
    label, prepared, valid = greeting_outputs()
    invalid = invented_review() if rejection == "reader" else invalid_provider_review()
    harness = Harness(tmp_path, WiredModel(label, prepared, invalid, valid))
    try:
        message = "  Good evening.\n"
        response = assert_ok(harness.post(message))
        assert response["metrics"]["llm_calls"] == 4
        calls = harness.model.calls
        assert [call[0].operation for call in calls] == [*OPERATIONS, OPERATIONS[-1]]
        rejected_prompt, retried_prompt = calls[2][0], calls[3][0]
        before = json.loads(rejected_prompt.user)
        after = json.loads(retried_prompt.user)
        feedback = after.pop("correction_feedback")
        assert after == before
        assert before["original_conversation"] == [
            {"id": "current", "message": {"role": "advocate", "text": message}}]
        assert before["permitted_unit_ids"] == []
        assert feedback["rejected_output"] == invented_review()
        assert feedback["mismatch"]
        if rejection == "provider":
            assert feedback["mismatch"] == "$.unit_reviews: more than 0 items"
        else:
            assert "Review" in feedback["mismatch"] and "unit" in feedback["mismatch"]
        assert "untrusted" in feedback["instruction"]
        assert retried_prompt.system == rejected_prompt.system
        assert calls[2][1]["properties"]["unit_reviews"]["maxItems"] == 0
        held = harness.held(response["chat_id"])
        assert len(held.brain_chat) == 1
        assert held.brain_chat[0]["release"]["proof"] == valid
        saved_reviews = held.brain_chat[0]["release"]["proof"]["unit_reviews"]
        assert "current" not in [row["unit_id"] for row in saved_reviews]
        assert "correction_feedback" not in response
        again = assert_ok(harness.post(message))
        assert again["replayed"] is True and len(harness.model.calls) == 4
    finally:
        harness.client.close()


def test_repair_keeps_the_complete_earlier_conversation_for_followup(tmp_path):
    first = greeting_outputs()
    follow = greeting_outputs()
    harness = Harness(tmp_path, WiredModel(*first, *follow[:2], invented_review(), follow[-1]))
    try:
        opened = assert_ok(harness.post("Good afternoon."))
        response = assert_ok(harness.post("Thank you.", "turn_followup",
            chat_id=opened["chat_id"], expected_version=1))
        assert response["metrics"]["llm_calls"] == 4
        original = json.loads(harness.model.calls[-2][0].user)
        retried = json.loads(harness.model.calls[-1][0].user)
        assert retried["original_conversation"] == original["original_conversation"]
        assert [(row["message"]["role"], row["message"]["text"])
                for row in original["original_conversation"]] == [
            ("advocate", "Good afternoon."), ("nm", "Hello. How can I help?"),
            ("advocate", "Thank you.")]
        assert len(harness.held(opened["chat_id"]).brain_chat) == 2
    finally:
        harness.client.close()


def test_a_second_stage_cannot_reset_the_shared_correction_allowance(tmp_path):
    valid_label, _, _ = greeting_outputs()
    bad_preparation = {"material": [], "actions": []}  # Required reply_draft is absent.
    model = WiredModel({"label": "undeclared_label"}, valid_label, bad_preparation)
    harness = Harness(tmp_path, model)
    try:
        failed = harness.post()
        assert failed.status_code == 503
        assert failed.json()["detail"]["committed"] == "not_committed"
        assert [call[0].operation for call in model.calls] == [
            "label_message", "label_message", "prepare_response"]
        first_input = json.loads(model.calls[0][0].user)
        correction_input = json.loads(model.calls[1][0].user)
        feedback = correction_input.pop("correction_feedback")
        assert correction_input == first_input
        assert feedback["rejected_output"] == {"label": "undeclared_label"}
        assert "correction_feedback" not in json.loads(model.calls[2][0].user)
        assert not harness.store.list_for("adv_wiring").matters
    finally:
        harness.client.close()


def test_two_rejected_reviews_stop_at_one_conditional_call_and_do_not_save(tmp_path):
    label, prepared, _ = greeting_outputs()
    harness = Harness(tmp_path, WiredModel(label, prepared, invented_review(), invented_review()))
    try:
        failed = harness.post()
        assert failed.status_code == 503
        assert failed.json()["detail"]["committed"] == "not_committed"
        assert len(harness.model.calls) == 4
        assert not harness.store.list_for("adv_wiring").matters
    finally:
        harness.client.close()


def test_provider_outage_is_not_a_schema_repair_or_successful_save(tmp_path):
    label, _, _ = greeting_outputs()
    harness = Harness(tmp_path, WiredModel(label, ProviderUnavailable("Synthetic provider outage")))
    try:
        failed = harness.post()
        assert failed.status_code == 503
        assert failed.json()["detail"]["committed"] == "not_committed"
        assert "elements" not in failed.json()
        assert "Synthetic provider outage" not in failed.text
        assert [call[0].operation for call in harness.model.calls] == OPERATIONS[:2]
        assert not harness.store.list_for("adv_wiring").matters
    finally:
        harness.client.close()
