"""The served turn releases checked replies and preserves their conversation."""
from __future__ import annotations

import json
from copy import deepcopy

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_brain_continuation import mixed_purpose_unit, unit, verdict
from tests.test_brain_turn import plan


class PublicContinuationModel:
    provider = "scripted"

    def __init__(self, routes, continuations, *, checks=None):
        self.routes = iter(routes)
        self.continuations = iter(continuations)
        self.checks = iter(checks) if checks is not None else None
        self.calls = []

    def context_budget(self, tier):
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        if prompt.operation == "interpret_conversation":
            data = next(self.routes)
        elif prompt.operation == "extract_disputes":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "extract_legal_details":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "verify_material_grounding":
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"], "verdict": "accept",
                 "reason": "The opening accurately describes the attributed account."}
                for row in payload["candidates"]]}
        elif prompt.operation == "continue_conversation":
            reply = next(self.continuations)
            data = reply(payload) if callable(reply) else deepcopy(reply)
        elif prompt.operation == "verify_continuation":
            if self.checks is None:
                data = verdict(*(row["request_index"] for row in payload["units"]))
            else:
                data = next(self.checks)
        else:
            raise AssertionError(f"Unexpected public model operation: {prompt.operation}")
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )


def opening_route(text):
    return plan(
        text, scope="proposed", step="legal_work",
        reply="I will examine your request before giving a supported assessment.",
        title="Receipt and agreement concern",
        summary="The advocate reports holding a signed receipt for a disputed transaction.")


def send(client, message, turn_id, *, opened=None):
    body = {"message": message, "turn_id": turn_id}
    if opened is not None:
        body.update(matter_id=opened["matter_id"], chat_id=opened["chat_id"])
    response = client.post("/api/turn", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_public_first_turn_uses_checked_conversation_reply_and_replay_is_free(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    model = PublicContinuationModel([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, message, "continuation-first")
    repeated = send(client, message, "continuation-first")

    visible = "\n".join(row["text"] for row in first["elements"])
    assert "You report holding a signed receipt." in visible
    assert "What outcome would you like to achieve?" in visible
    assert "The record and applicable legal sources have not been checked." in visible
    assert "I will examine your request" not in visible
    assert first["metrics"]["llm_calls"] == 6
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "extract_disputes", "extract_legal_details",
        "verify_material_grounding", "continue_conversation", "verify_continuation"]
    composition = next(payload for operation, payload in model.calls
                       if operation == "continue_conversation")
    assert all("reply" not in item and "clarification" not in item
               for item in composition["work_items"])
    assert "I will examine your request before giving a supported assessment." not in (
        json.dumps(composition))
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    saved = wired.store.load(first["matter_id"])
    assert len(saved.brain_chat) == 1
    assert saved.brain_chat[0]["elements"] == first["elements"]
    assert saved.brain_chat[0]["response"]["continuation"] == first["continuation"]


def test_public_substantive_return_has_all_history_and_diversion_preserves_work(
        client, wired, monkeypatch):
    first_message = "I have a signed receipt for the disputed transaction. Please review it."
    correction = "Correction: the receipt is unsigned."
    greeting = "Hello again."
    returned = "Please return to the review. I cannot obtain a signed copy."
    routes = [
        opening_route(first_message),
        plan(correction, scope="current", step="legal_work", relation="changes",
             reply="I will revisit the reported status of the receipt."),
        plan(greeting, scope="none", relation="aside", reply="Hello."),
        plan(returned, scope="current", step="legal_work", relation="continues",
             reply="I will continue the requested review."),
    ]
    routes[2]["active_work_after"] = routes[1]["active_work_after"]
    routes[1]["material_review"] = True
    routes[3]["material_review"] = True
    corrected = unit(
        text="You have corrected the receipt's status to unsigned.",
        question="Is any other record of the transaction available?")
    final = unit(
        text="You have said that a signed copy is unavailable.", span_ids=("L2",),
        question="Would you like to assess the record that remains available?")
    model = PublicContinuationModel(routes, [
        {"units": [unit()]}, {"units": [corrected]}, {"units": [final]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, first_message, "public-first")
    second = send(client, correction, "public-correction", opened=first)
    aside = send(client, greeting, "public-aside", opened=second)
    last = send(client, returned, "public-return", opened=aside)

    assert second["metrics"]["llm_calls"] == 5
    assert aside["metrics"]["llm_calls"] == 1
    assert last["metrics"]["llm_calls"] == 5
    continuation_payloads = [payload for operation, payload in model.calls
                             if operation == "continue_conversation"]
    earlier = continuation_payloads[-1]["earlier_conversation"]
    assert [row["turn_id"] for row in earlier] == [
        "public-first", "public-first", "public-correction", "public-correction",
        "public-aside", "public-aside"]
    words = ["".join(span["text"] for span in row["source_spans"]) for row in earlier]
    assert words[::2] == [first_message, correction, greeting]
    assert words[1::2] == ["\n".join(row["text"] for row in response["elements"])
                          for response in (first, second, aside)]
    assert "signed copy is unavailable" in json.dumps(last["elements"])
    saved = wired.store.load(first["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [
        first_message, correction, greeting, returned]
    assert saved.brain_chat[2]["active_work_after"] == routes[1]["active_work_after"]


def test_public_mixed_purpose_block_uses_question_link_for_display(client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    proposed = mixed_purpose_unit()
    model = PublicContinuationModel([opening_route(message)], [{"units": [proposed]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    released = send(client, message, "public-mixed-block")

    assert released["metrics"]["llm_calls"] == 6
    assert released["continuation"]["units"][0]["blocks"][0]["kind"] == "limitation"
    assert released["elements"][0]["kind"] == "question"
    assert released["elements"][0]["section"] == "needed"
    assert released["elements"][0]["text"] == proposed["blocks"][0]["text"]
    checked = next(payload for operation, payload in model.calls
                   if operation == "verify_continuation")
    assert checked["units"] == [proposed]


def test_public_rejected_assessment_keeps_input_once_and_does_not_release_accusation(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    unsupported = unit(text="You deliberately concealed a damaging record.")
    reason = "The attributed record does not establish deliberate concealment."
    model = PublicContinuationModel(
        [opening_route(message)], [{"units": [unsupported]}, {"units": [unsupported]}],
        checks=[verdict(0, accept=False, reason=reason),
                verdict(0, accept=False, reason=reason)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = send(client, message, "public-rejected")

    assert "deliberately concealed" not in json.dumps(response["elements"])
    assert response["continuation"]["units"] == []
    assert response["continuation"]["coverage"][0]["state"] == "unavailable"
    assert response["metrics"]["llm_calls"] == 8
    saved = wired.store.load(response["matter_id"])
    assert len(saved.brain_chat) == 1
    assert saved.brain_chat[0]["message"] == message
    assert "deliberately concealed" not in json.dumps(saved.brain_chat[0]["elements"])


def test_public_foreign_chat_and_corrupt_history_stop_before_model_dispatch(
        client, wired, monkeypatch):
    from dataclasses import replace

    message = "I have a signed receipt for the disputed transaction. Please review it."
    model = PublicContinuationModel([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, message, "public-owned")
    before_calls = len(model.calls)
    other = client.sign_in("adv_other", fresh=True)

    foreign = other.post("/api/turn", json={
        "message": "Continue", "turn_id": "public-foreign",
        "matter_id": first["matter_id"]})

    assert foreign.status_code == 404, foreign.text
    assert len(model.calls) == before_calls
    saved = wired.store.load(first["matter_id"])
    unreadable = deepcopy(saved.brain_chat[0])
    unreadable["release_state"] = "unknown"
    wired.store.commit(replace(
        saved, brain_chat=(unreadable,), version=saved.version + 1),
        expected_version=saved.version)

    refused = client.post("/api/turn", json={
        "message": "Continue", "turn_id": "public-corrupt",
        "matter_id": first["matter_id"], "chat_id": first["chat_id"]})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert len(model.calls) == before_calls
    assert len(wired.store.load(first["matter_id"]).brain_chat) == 1


def test_public_session_revoked_during_verification_cannot_save_or_release(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."

    class RevokedDuringVerification(PublicContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "verify_continuation":
                assert wired.directory.close_all_sessions(
                    "adv_demo", "Synthetic revocation during response checking") == 1
            return checked

    model = RevokedDuringVerification([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = client.post("/api/turn", json={
        "message": message, "turn_id": "public-revoked-during-check"})

    assert response.status_code == 401, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    assert "You report holding a signed receipt." not in response.text
    assert wired.store.list_for("adv_demo").matters == ()
    assert [operation for operation, _ in model.calls].count("verify_continuation") == 1
