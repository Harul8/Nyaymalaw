"""Current public context plumbing; scripted meanings do not prove model accuracy.

The interpreter must receive every released original turn, current owned records
and saved work. Repair retains that same input. Invalid history and overflow
must stop before dispatch or commit; sparse IDs and long complete text are valid.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.brain.turn import chat_matter_id
from tests.test_brain_code_acknowledgements import install, record_plan
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_pressure_release import (
    BASE_TURN,
    DATE_ID,
    NEW_DATE,
    OLD_DATE,
    ORIGINAL,
    initial_plan,
    revision,
)
from tests.test_brain_turn import plan


def _route(message, *, relation="continues", preserve=False, contribution=False):
    def planned(payload):
        payload = payload.get("original_input", payload)
        value = plan(message, relation=relation)
        if contribution:
            value["items"][0]["intent"] = "contribution"
        if preserve:
            value["active_work_after"] = payload["current_work"]
        return value
    return planned


def _reply(payload):
    unit = raw_unit(payload)
    # The fabricated writer must respect offered source choices: whitespace
    # remains in the transcript but is not an assertion to select as an account.
    nonblank = {row["id"] for row in payload["latest_message_spans"] if row["text"].strip()}
    for block in unit["blocks"]:
        selected = block["evidence_expression"]["source_ids"]
        block["evidence_expression"]["source_ids"] = [i for i in selected if i in nonblank]
    if "$no_task" in payload["work_items"][0]["work_choices"]:
        unit["work_selector"] = "$no_task"
    return {"units": [unit]}


def _model(wired, monkeypatch, routes):
    model = RawExpressionModel(routes, [_reply] * len(routes))
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return model


def _saved(wired, answer):
    return wired.store.load(answer["matter_id"] or chat_matter_id("adv_demo", answer["chat_id"]))


def _transcript(saved):
    return [message for row in saved.brain_chat for message in (
        {"turn_id": row["turn_id"], "role": "advocate", "text": row["message"]},
        {"turn_id": row["turn_id"], "role": "nm",
         "text": "\n".join(element["text"] for element in row["elements"]
                            if element["text"].strip())},
    )]


def test_saved_opening_and_file_inventory_reach_public_context_without_document_text(
        client, wired, monkeypatch):
    from nm.open_matter.commission_contracts import Commission
    from nm.open_matter.engagement_contracts import Engagement
    from tests.test_document_transport_keeps_local_reading_permission_separate import read

    matter_id, instruction, _, _ = read(client, wired, key="brain-context")
    saved = wired.store.load(matter_id)
    revised = client.post(f"/api/matters/{matter_id}/opening", json={
        "request_key": "opening-context", "expected_version": saved.version,
        "title": "Recorded outside chat", "parties": {"Mira": "client"},
        "brief": {"objective": "Preserve the original account before advising."},
    })
    assert revised.status_code == 200, revised.text
    saved = wired.store.load(matter_id)
    uploads = deepcopy(saved.uploads)
    # A damaged independent inventory item must neither disclose foreign
    # metadata nor discard the owned conversation and usable file inventory.
    foreign = deepcopy(uploads[instruction["original_id"]])
    foreign["receipt"].update(upload_id="foreign", matter_id="another-matter")
    foreign["offer"]["filename"] = "FOREIGN-SECRET.txt"
    uploads["foreign"] = foreign
    commission = Commission(objective="Explain the available choices", recorded_by="adv_demo")
    wired.store.commit(replace(
        saved, uploads=uploads, engagement=Engagement(client="Mira"),
        commission=commission.next_version(objective="Review"), commission_history=(commission,),
        version=saved.version + 1), expected_version=saved.version)
    before = wired.store.load(matter_id)
    model = _model(wired, monkeypatch, [_route("Hello.")])
    response = client.post("/api/turn", json={
        "message": "Hello.", "turn_id": "inventory-context", "matter_id": matter_id})
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["llm_calls"] == 3
    payload = next(value for op, value in model.calls if op == "interpret_conversation")
    context = payload["additional_saved_context"]
    assert context["parties"] == {"Mira": "client"}
    assert context["opening"]["current"]["objective"] == (
        "Preserve the original account before advising.")
    assert context["opening"]["corrections"][0]["previous"]["parties"] == {}
    assert context["engagement"]["client"] == "Mira"
    assert context["commission"]["objective"] == "Review"
    assert len(context["commission_history"]) == 1
    document = context["documents"][0]
    assert document["filename"] == "private.txt"
    assert document["local_reading"]["state"] == "recorded"
    assert document["content_in_model_context"] is False
    assert context["documents"][1] == {"asset_id": "foreign", "state": "metadata_unavailable"}
    assert "FOREIGN-SECRET" not in str(payload)
    assert "The original records payment" not in str(payload)
    assert payload["target_catalogue"] == []
    after = wired.store.load(matter_id)
    assert after.uploads == before.uploads and after.intake_answers == before.intake_answers
    assert after.commission == before.commission


def test_sustained_public_context_keeps_correction_diversions_reopen_and_repair(
        client, wired, monkeypatch):
    correction = "The northern carton arrival was 19 April, correcting the earlier account."
    change = record_plan(correction, candidates=[revision(NEW_DATE, correction, OLD_DATE, DATE_ID)],
                         account=True)
    install(wired, monkeypatch, [initial_plan(), change], [{}, {"status": "performed"}])
    opened = send(client, ORIGINAL, BASE_TURN)
    corrected = send(client, correction, "context-correction-91", opened=opened)
    saved = _saved(wired, corrected)
    expected_records = boundary._current_records(wired.store, saved)[0].open_material
    assert NEW_DATE in [row["statement"] for row in expected_records]
    expected = _transcript(saved)
    cases = [
        ("context-aside-400", "Hello again.\nI am still here.", "aside"),
        ("context-aside-7", "A separate question: what is the capital of France?", "aside"),
        ("context-return-3000", "Please return to examining the earlier account.", "continues"),
        ("context-repair-2", "Compare my original wording with the correction before proceeding.",
         "continues"),
    ]
    routes = [_route(message, relation=relation, preserve=True, contribution=index == 0)
              for index, (_, message, relation) in enumerate(cases)]
    # One deliberately invalid routing envelope forces the existing bounded repair.
    routes.insert(3, {"items": []})
    model = _model(wired, monkeypatch, routes)
    for index, (identity, message, _) in enumerate(cases):
        before_saved = deepcopy(_saved(wired, opened))
        before_work = boundary._current_records(wired.store, before_saved)[0].progress
        start = len(model.calls)
        answer = send(client, message, identity, opened=opened)
        assert answer["blocked"] is False
        assert answer["metrics"]["llm_calls"] == (4 if index == 3 else 3)
        interpretations = [payload for op, payload in model.calls[start:]
                           if op == "interpret_conversation"]
        original = interpretations[0]
        assert original["earlier_conversation"] == expected
        assert original["saved_progress"] == before_work
        historical = {row["id"]: row for row in original["record_history"]}
        assert historical[DATE_ID]["record"]["statement"] == OLD_DATE
        assert historical[DATE_ID]["record"]["record_role"] == "nm_interpretation"
        assert historical[DATE_ID]["checked_retirement"]["turn_id"] == "context-correction-91"
        assert DATE_ID not in {row["id"] for row in original["target_catalogue"]}
        assert [row["record"]["statement"] for row in original["target_catalogue"]
                if row["type"] == "material"] == [row["statement"] for row in expected_records]
        assert len(interpretations) == (2 if index == 3 else 1)
        if index == 3:
            assert interpretations[1]["original_input"] == original
            assert interpretations[1]["original_input"]["latest_message"] == message
        saved = _saved(wired, answer)
        if index == 0:
            assert boundary._current_records(wired.store, saved)[0].progress == before_work
        assert _transcript(saved)[:len(expected)] == expected
        assert saved.brain_chat[:-1] == before_saved.brain_chat
        expected = _transcript(saved)
        assert expected[-2] == {"turn_id": identity, "role": "advocate", "text": message}
        assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
        detail = client.get(f"/api/matters/{opened['matter_id']}")
        assert detail.status_code == 200, detail.text
        assert _saved(wired, opened) == saved
        before_calls = len(model.calls)
        replay = send(client, message, identity, opened=opened)
        assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
        assert replay["elements"] == answer["elements"]
        assert len(model.calls) == before_calls and _saved(wired, opened) == saved
    assert len(expected) == 12


@pytest.mark.parametrize("damage", [
    "missing_turn", "unreadable_reply", "unreleased_reply", "not_held",
    "unknown_context_contract", "removed_context_contract",
])
def test_bad_saved_context_blocks_public_dispatch_and_save(client, wired, monkeypatch, damage):
    model = _model(wired, monkeypatch, [plan("Hello.")])
    opened = send(client, "Hello.", "context-seed-105")
    saved = _saved(wired, opened)
    row = deepcopy(saved.brain_chat[0])
    turns = saved.turns_applied
    rows = (row,)
    if damage == "missing_turn":
        turns = (*turns, "missing-original-turn")
    elif damage == "unreadable_reply":
        row["elements"] = [{"text": None}]
    elif damage == "unreleased_reply":
        row.update(committed=False, release_state="withheld")
    elif damage == "unknown_context_contract":
        row["response"]["material_coverage"]["execution"]["context_contract"] = "unknown"
    elif damage == "removed_context_contract":
        row["response"]["material_coverage"]["execution"].pop("context_contract")
    else:
        row["message_source"] = "not_held"
    wired.store.commit(replace(saved, turns_applied=turns, brain_chat=rows,
                               version=saved.version + 1), expected_version=saved.version)
    damaged = deepcopy(_saved(wired, opened))
    before_calls = len(model.calls)
    commits = []
    monkeypatch.setattr(wired.store, "commit", lambda *args, **kwargs: commits.append(args))
    response = client.post("/api/turn", json={
        "message": "Continue.", "turn_id": "context-next-1", "chat_id": opened["chat_id"]})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    assert len(model.calls) == before_calls and commits == []
    assert _saved(wired, opened) == damaged


def test_complete_long_context_is_preserved_but_overflow_never_dispatches_or_saves(
        client, wired, monkeypatch):
    message = "\n".join(f"Original observation {index}: no change is authorised."
                        for index in range(70))
    later = "Retain those original words while considering this separate message."
    model = _model(wired, monkeypatch, [plan(message), _route(later)])
    opened = send(client, message, "long-context-91")
    saved = deepcopy(_saved(wired, opened))
    before_calls = len(model.calls)
    original_budget = model.context_budget
    model.context_budget = lambda tier: 100
    response = client.post("/api/turn", json={
        "message": later, "turn_id": "long-context-4", "chat_id": opened["chat_id"]})
    assert response.status_code == 413, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    assert len(model.calls) == before_calls and _saved(wired, opened) == saved
    model.context_budget = original_budget
    answer = send(client, later, "long-context-4", opened=opened)
    assert answer["blocked"] is False
    interpreted = [payload for op, payload in model.calls if op == "interpret_conversation"][-1]
    assert interpreted["earlier_conversation"] == _transcript(saved)
    assert interpreted["earlier_conversation"][0]["text"] == message


def test_browser_transcript_preserves_native_append_order_when_clock_moves_back(
        client, wired, monkeypatch):
    install(wired, monkeypatch, [initial_plan()], [{}])
    opened = send(client, ORIGINAL, BASE_TURN)
    model = _model(wired, monkeypatch, [_route("Continue."), _route("Keep the sequence.")])
    from datetime import datetime, timezone
    from types import SimpleNamespace
    with monkeypatch.context() as clock:
        clock.setattr(boundary, "datetime", SimpleNamespace(
            now=lambda tz: datetime(2000, 1, 1, tzinfo=timezone.utc)))
        send(client, "Continue.", "a-earlier-lexical-id", opened=opened)
    readback = client.get(f"/api/matters/{opened['matter_id']}/transcript")
    assert readback.status_code == 200, readback.text
    assert readback.json()["state"] == "ok", readback.text
    assert [row["turn_id"] for row in readback.json()["turns"]] == [
        BASE_TURN, "a-earlier-lexical-id"]
    send(client, "Keep the sequence.", "next", opened=opened)
    interpreted = [payload for op, payload in model.calls if op == "interpret_conversation"][-1]
    assert [row["turn_id"] for row in interpreted["earlier_conversation"]
            if row["role"] == "advocate"] == [BASE_TURN, "a-earlier-lexical-id"]


@pytest.mark.parametrize(("first", "followup"), [
    ("\n  Hello.\t\r\n", " \tPlease retain my original wording.\n"),
    ("\u2003My note: ‘A’ and ‘B’ are different.\u00a0",
     "\nKeep the quoted wording, punctuation and spacing.  "),
])
def test_public_context_preserves_exact_submitted_words_and_replay(
        client, wired, monkeypatch, first, followup):
    model = _model(wired, monkeypatch, [plan(first), _route(followup)])
    opened = send(client, first, "exact-input-first")
    first_saved = deepcopy(_saved(wired, opened))
    first_input = next(payload for op, payload in model.calls
                       if op == "interpret_conversation")
    assert first_input["latest_message"] == first
    assert first_input["earlier_conversation"] == []
    assert first_saved.brain_chat[0]["message"] == first

    answer = send(client, followup, "exact-input-followup", opened=opened)
    interpreted = [payload for op, payload in model.calls
                   if op == "interpret_conversation"][-1]
    assert interpreted["latest_message"] == followup
    assert interpreted["earlier_conversation"] == _transcript(first_saved)
    saved = deepcopy(_saved(wired, answer))
    assert saved.brain_chat[-1]["message"] == followup
    assert answer["metrics"]["llm_calls"] == opened["metrics"]["llm_calls"] == 3
    calls = len(model.calls)
    replay = send(client, followup, "exact-input-followup", opened=opened)
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == answer["elements"]
    assert len(model.calls) == calls and _saved(wired, answer) == saved


@pytest.mark.parametrize("message", ["", " \t\r\n", "\u2003\u00a0"])
def test_blank_public_input_is_refused_before_model_use(client, wired, monkeypatch, message):
    model = _model(wired, monkeypatch, [])
    response = client.post("/api/turn", json={"message": message, "turn_id": "empty-input"})
    assert response.status_code == 422
    assert model.calls == []
