"""Message labeling through the shipped turn boundary.

All meanings and reviewer decisions below are explicitly scripted. These tests
prove labeling input, exact context, persistence and accounting, not semantic
accuracy or authority to admit information into the matter record.

The unfinished automatic source-dispatch candidate is preserved unchanged at
outputs/brain-classification-20261007/candidate/source-routing-with-unfinished-intake.py.
Its source-only classification persistence and intake behavior remain deferred.
"""
from copy import deepcopy

import pytest

from nm.brain.turn import chat_matter_id
from nm.brain.history import from_turns
from nm.shared.model_port import Tier
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_turn import plan


def acknowledgment(payload):
    unit = raw_unit(payload, operator="acknowledgment", kind="acknowledgment",
                    all_sources=False)
    unit["sufficiency"]["status"] = "complete"
    return {"units": [unit]}


class MessageLabelModel(RawExpressionModel):
    def __init__(self, routes):
        super().__init__(routes, [acknowledgment for _ in routes])


def install(wired, monkeypatch, model):
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)


def operations(model):
    return [operation for operation, _ in model.calls]


def classified_route(message, category="work_request", **kwargs):
    route = plan(message, **kwargs)
    route["message_parts"] = [{"category": category, "selections": [
        {"source_id": "$message", "whole_source": True}]}]
    return route


def test_read_only_request_skips_source_reading_and_replay_adds_no_calls(
        client, wired, monkeypatch):
    latest = "Please explain what information has been provided so far."
    model = MessageLabelModel([classified_route(latest)])
    install(wired, monkeypatch, model)

    answer = send(client, latest, "source-read-only")
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    replay = send(client, latest, "source-read-only")

    assert operations(model) == [
        "label_message", "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert answer["metrics"]["llm_calls"] == 4
    assert replay["metrics"]["llm_calls"] == 0
    assert model.calls[0] == ("label_message", {
        "latest_message": latest, "message_position": "first", "earlier_conversation": [],
    })
    assert model.tiers[0] is Tier.ROUTINE
    label_schema = model.schemas[0][1]
    assert set(label_schema["properties"]) == {"parts"}
    assert set(label_schema["properties"]["parts"]["items"]["properties"]) == {"text", "labels"}
    assert "message_parts" not in model.schemas[1][1]["properties"]
    receipt = answer["material_coverage"]["execution"]
    assert receipt["material_selected"] is False
    assert receipt["stages"]["source_classification"]["state"] == "not_run"
    assert receipt["stages"]["detail_extraction"]["state"] == "not_run"
    assert receipt["record_changes"] == []
    expected_understanding = {
        "contract": "attributed_message_parts_v1", "position": "first",
        "parts": [{"id": "part_1", "category": "work_request", "sources": [
            {"start": 0, "end": len(latest), "text": latest}]}],
    }
    assert receipt["message_understanding"] == expected_understanding
    assert replay["material_coverage"]["execution"]["message_understanding"] == expected_understanding
    assert saved.brain_chat[0]["response"]["material_coverage"]["execution"][
        "message_understanding"] == expected_understanding
    assert saved.brain_chat[0]["message"] == latest
    assert saved.brain_chat[0]["response"]["elements"] == answer["elements"]


def test_information_label_keeps_exact_history_and_saved_followup_labels(
        client, wired, monkeypatch):
    first = "Hello."
    second = 'The draft says "the receipt proves acceptance".'
    model = MessageLabelModel(
        [classified_route(first, "social"),
         classified_route(second, "information", relation="continues")])
    install(wired, monkeypatch, model)
    opened = send(client, first, "source-history-first")
    prior = from_turns(wired.store.load(
        chat_matter_id("adv_demo", opened["chat_id"])).brain_chat, state="ok").messages

    answer = send(client, second, "source-history-second", opened=opened)

    interpreter_inputs = [payload for operation, payload in model.calls
                          if operation == "interpret_conversation"]
    assert interpreter_inputs[1]["earlier_conversation"] == [
        {"turn_id": "source-history-first", "role": "advocate", "text": first},
        {"turn_id": "source-history-first", "role": "nm", "text": prior[1].text},
    ]
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    assert [row["message"] for row in saved.brain_chat] == [first, second]
    assert [answer["metrics"]["llm_calls"], opened["metrics"]["llm_calls"]] == [4, 4]
    assert operations(model) == [
        "label_message", "interpret_conversation", "continue_conversation", "verify_continuation",
        "label_message", "interpret_conversation",
        "continue_conversation", "verify_continuation"]
    assert answer["material_coverage"]["execution"]["material_selected"] is False
    understanding = answer["material_coverage"]["execution"]["message_understanding"]
    assert understanding == {
        "contract": "attributed_message_parts_v1", "position": "follow_up",
        "parts": [{"id": "part_1", "category": "information", "sources": [
            {"start": 0, "end": len(second), "text": second}]}],
    }
    labeling_inputs = [payload for operation, payload in model.calls
                       if operation == "label_message"]
    assert labeling_inputs == [
        {"latest_message": first, "message_position": "first", "earlier_conversation": []},
        {"latest_message": second, "message_position": "follow_up",
         "earlier_conversation": interpreter_inputs[1]["earlier_conversation"]},
    ]
    assert saved.brain_chat[0]["response"]["material_coverage"]["execution"][
        "message_understanding"] == opened["material_coverage"]["execution"]["message_understanding"]
    assert saved.brain_chat[1]["response"]["material_coverage"]["execution"][
        "message_understanding"] == understanding
    call_count = len(model.calls)
    replay = send(client, second, "source-history-second", opened=opened)
    assert replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == call_count
    assert replay["material_coverage"]["execution"]["message_understanding"] == understanding


@pytest.mark.parametrize("damage", ["offset", "contract", "position"])
def test_replay_rejects_changed_saved_message_labels_without_provider_calls(
        client, wired, monkeypatch, damage):
    latest = "Please explain the recorded account."
    model = MessageLabelModel([classified_route(latest)])
    install(wired, monkeypatch, model)
    opened = send(client, latest, "source-label-replay")
    matter_id = chat_matter_id("adv_demo", opened["chat_id"])
    damaged = deepcopy(wired.store.load(matter_id))
    understanding = damaged.brain_chat[0]["response"]["material_coverage"][
        "execution"]["message_understanding"]
    if damage == "offset":
        understanding["parts"][0]["sources"][0]["start"] = 1
    elif damage == "contract":
        understanding["contract"] = "attributed_message_parts_unknown"
    else:
        understanding["position"] = "follow_up"
    original_load = wired.store.load
    monkeypatch.setattr(wired.store, "load", lambda identity: (
        damaged if identity == matter_id else original_load(identity)))
    previous_calls = len(model.calls)

    response = client.post("/api/turn", json={"message": latest, "turn_id": "source-label-replay"})

    assert response.status_code == 409, response.text
    assert len(model.calls) == previous_calls


def test_earlier_account_does_not_retrigger_reading_for_a_social_followup(
        client, wired, monkeypatch):
    from tests.test_brain_material_purpose import (
        PurposeModel, open_account, public_record, seed_plan,
    )

    account = "The freight is held at the depot."
    seeded = seed_plan(account)
    seeded["message_parts"] = [{"category": "information", "selections": [
        {"source_id": "$message", "whole_source": True}]}]
    opened = open_account(client, wired, monkeypatch, PurposeModel([seeded]), account,
                          turn_id="source-earlier-account")
    before = public_record(client, opened["matter_id"])
    assert [row["statement"] for row in before["rows"]] == [account]
    latest = "Hello again."
    route = classified_route(latest, "social", relation="aside")
    route["items"][0]["intent"] = "contribution"
    model = MessageLabelModel([route])
    install(wired, monkeypatch, model)

    answer = send(client, latest, "source-social-followup", opened=opened)

    assert operations(model) == [
        "label_message", "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert answer["metrics"]["llm_calls"] == 4
    assert answer["material_coverage"]["execution"]["material_selected"] is False
    assert public_record(client, opened["matter_id"]) == before
