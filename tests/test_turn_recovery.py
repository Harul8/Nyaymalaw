"""One shared correction allowance through the authenticated current-brain edge."""
import json
from copy import deepcopy

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
    mixed_outputs,
    MIXED_MESSAGE,
)


def invented_review():
    return {"greeting": True, "unit_reviews": [
        {"unit_id": "current", "verdict": "supported",
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
    bad_preparation = {"disputes": []}  # Required independent objectives collection is absent.
    model = WiredModel({"label": "undeclared_label"}, valid_label, bad_preparation)
    harness = Harness(tmp_path, model)
    try:
        failed = harness.post()
        assert failed.status_code == 503
        assert failed.json()["detail"]["committed"] == "not_committed"
        assert [call[0].operation for call in model.calls] == [
            "label_message", "label_message", "extract_disputes_objectives"]
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


def test_all_held_extraction_uses_one_owned_correction_before_review_and_save(tmp_path):
    label, prepared, review = mixed_outputs(MIXED_MESSAGE)
    invalid = deepcopy(prepared)
    for items in invalid.values():
        items[0]["selections"][0]["passage_id"] = "other_matter:p1"
    model = WiredModel(label, invalid, prepared, review)
    harness = Harness(tmp_path, model)
    try:
        response = assert_ok(harness.post(MIXED_MESSAGE))
        assert [call[0].operation for call in model.calls] == [
            "label_message", "extract_disputes_objectives", "extract_disputes_objectives",
            "review_prepared_response"]
        before = json.loads(model.calls[1][0].user)
        after = json.loads(model.calls[2][0].user)
        feedback = after.pop("correction_feedback")
        assert after == before
        assert feedback["rejected_output"] == invalid
        assert "dispute:1" in feedback["mismatch"]
        assert "Unknown selected passage other_matter:p1" in feedback["mismatch"]
        assert response["metrics"]["llm_calls"] == 4
        saved = harness.held(response["chat_id"]).brain_chat[0]
        assert saved["preparation"]["issues"] == []
        assert saved["preparation"]["proposal"]["disputes"]
        assert saved["preparation"]["proposal"]["objectives"]
        assert "other_matter:p1" not in json.dumps(saved)
        assert [element["text"] for element in response["elements"]] == ["Message received."]
    finally:
        harness.client.close()


def test_all_held_extraction_cannot_reset_a_correction_spent_by_labeling(tmp_path):
    label, prepared, _ = mixed_outputs(MIXED_MESSAGE)
    for items in prepared.values():
        items[0]["selections"][0]["passage_id"] = "other_matter:p1"
    model = WiredModel({"label": "undeclared_label"}, label, prepared)
    harness = Harness(tmp_path, model)
    try:
        response = harness.post(MIXED_MESSAGE)
        assert response.status_code == 503
        assert response.json()["detail"]["committed"] == "not_committed"
        assert [call[0].operation for call in model.calls] == [
            "label_message", "label_message", "extract_disputes_objectives"]
        assert not harness.store.list_for("adv_wiring").matters
    finally:
        harness.client.close()


def test_held_peer_preserves_supported_extraction_without_repeating_accepted_input(tmp_path):
    label, prepared, review = mixed_outputs(MIXED_MESSAGE)
    prepared["objectives"][0]["selections"][0]["passage_id"] = "other_matter:p1"
    review["unit_reviews"] = review["unit_reviews"][:1]
    harness = Harness(tmp_path, WiredModel(label, prepared, review))
    try:
        response = assert_ok(harness.post(MIXED_MESSAGE))
        saved = harness.held(response["chat_id"]).brain_chat[0]
        assert saved["release"]["state"] == "partial"
        assert saved["preparation"]["proposal"]["disputes"]
        assert saved["preparation"]["proposal"]["objectives"] == []
        assert saved["preparation"]["issues"][0]["unit"] == "objective:1"
        assert response["service_status"] is None
        assert response["metrics"]["llm_calls"] == 3
        assert [element["text"] for element in response["elements"]] == ["Message received."]
        again = assert_ok(harness.post(MIXED_MESSAGE))
        assert again["replayed"] is True and len(harness.model.calls) == 3
    finally:
        harness.client.close()
