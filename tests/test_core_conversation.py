"""Owned transcript and receipts, exercised against the shipped sealed CAS store."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.core_engine.conversation import (
    CONTRACT, HEADER, ConversationRefused, checked_rows, commit_turn, open_turn,
)
from nm.shared.store_file_store import FileMatterStore

pytestmark = pytest.mark.class_a


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-not-a-secret")


def start(store, **kw):
    return open_turn(store, **{"advocate_id": "owner", "message": "Original words\nनमस्ते",
                              "turn_id": "t1", **kw})


def save(store, context, **kw):
    return commit_turn(store, context, **{
        "elements": [{"text": "Acknowledged.\nExact reply."}],
        "activities": {"fixture": "admitted synthetic result"},
        "session_current": lambda: True, **kw})


def test_exact_first_followup_context_and_independent_copies(store):
    first = start(store)
    assert first.payload()["conversation"] == []
    assert first.payload()["position"] == "first"
    response = save(store, first, records={"restriction": "Do not send"},
                    work=[{"id": "w1", "status": "pending"}], service_status="Search interrupted.")
    second = start(store, chat_id=response["chat_id"], turn_id="t2", message="Continue.")
    payload = second.payload()
    assert [(r["speaker"], r["text"]) for r in payload["conversation"]] == [
        ("advocate", first.message), ("nm", "Acknowledged.\nExact reply."),
        ("service", "Search interrupted.")]
    assert payload["position"] == "follow_up"
    assert all(r["turn_id"] == "t1" for r in payload["conversation"])
    assert payload["saved_work"] == [{"id": "w1", "status": "pending"}]
    payload["current_records"]["restriction"] = "changed"
    assert second.payload()["current_records"] == {"restriction": "Do not send"}
    save(store, second)
    third = start(store, chat_id=response["chat_id"], turn_id="t3")
    assert len(third.payload()["conversation"]) == 5
    assert third.payload()["current_records"] == {"restriction": "Do not send"}


@pytest.mark.parametrize("returned_identity", [False, True])
def test_retry_has_one_effect_and_exact_saved_response_even_with_stale_version(store, returned_identity):
    original = start(store)
    response = save(store, original)
    retry = start(store, chat_id=response["chat_id"] if returned_identity else None,
                  expected_version=0)
    assert retry.replay == {**response, "replayed": True}
    assert save(store, retry) == retry.replay
    assert len(store.load(original.matter.id).brain_chat) == 1


def test_same_id_different_message_never_replays_or_changes(store):
    context = start(store)
    save(store, context)
    with pytest.raises(ConversationRefused, match="different message"):
        start(store, message="Replacement")
    assert store.load(context.matter.id).brain_chat[0]["message"] == context.message


def test_unknown_chat_or_another_owner_does_not_create_empty_history(store):
    response = save(store, start(store))
    for identity, owner in [("absent", "owner"), (response["chat_id"], "another")]:
        with pytest.raises(ConversationRefused, match="could not be found"):
            start(store, chat_id=identity, advocate_id=owner)


def test_non_chat_state_versions_are_valid_but_truncated_history_is_not(store):
    first = start(store)
    response = save(store, first)
    current = store.load(first.matter.id)
    store.commit(replace(current, version=7), expected_version=1)
    second = start(store, chat_id=response["chat_id"], turn_id="t2", expected_version=7)
    assert save(store, second)["matter_version"] == 8
    saved = store.load(first.matter.id)
    assert [r["state_version"] for r in checked_rows(saved, "owner")] == [1, 8]
    with pytest.raises(ConversationRefused):
        checked_rows(replace(saved, brain_chat=saved.brain_chat[:-1]), "owner")


@pytest.mark.parametrize("change", ["words", "reply", "header", "version", "contract"])
def test_tampered_or_unknown_history_is_refused(store, change):
    context = start(store)
    save(store, context)
    saved = store.load(context.matter.id)
    rows = deepcopy(saved.brain_chat)
    metadata = deepcopy(saved.intake_answers)
    if change == "words": rows[0]["message"] = "Another account"
    if change == "reply": rows[0]["response"]["elements"][0]["text"] = "Changed"
    if change == "header": metadata[HEADER]["tail_digest"] = "bad"
    if change == "version": rows[0]["state_version"] = 9
    if change == "contract": metadata[HEADER]["contract"] = CONTRACT + "_future"
    with pytest.raises(ConversationRefused):
        checked_rows(replace(saved, brain_chat=rows, intake_answers=metadata), "owner")


def test_lost_acknowledgement_reads_durable_receipt(store):
    context = start(store)
    class LostAck:
        load = store.load
        def commit(self, matter, *, expected_version):
            store.commit(matter, expected_version=expected_version)
            raise OSError("ack lost")
    response = save(LostAck(), context)
    assert response["committed"] == "committed"
    assert len(store.load(context.matter.id).brain_chat) == 1
    assert start(store).replay["elements"] == response["elements"]


def test_unknown_save_cannot_claim_saved_or_unsaved(store):
    context = start(store)
    class Unavailable:
        def commit(self, *args, **kwargs): raise OSError("unavailable")
        def load(self, *args): raise OSError("unavailable")
    with pytest.raises(ConversationRefused) as error:
        save(Unavailable(), context)
    assert error.value.committed == "unconfirmed"
    assert error.value.retryable


def test_concurrent_loser_cannot_overwrite_or_claim_success(store):
    response = save(store, start(store))
    left = start(store, chat_id=response["chat_id"], turn_id="t2", message="Left")
    right = start(store, chat_id=response["chat_id"], turn_id="t3", message="Right")
    save(store, left)
    with pytest.raises(ConversationRefused):
        save(store, right)
    saved = store.load(left.matter.id)
    assert [r["message"] for r in saved.brain_chat] == ["Original words\nनमस्ते", "Left"]


def test_authorisation_is_required_for_save_and_replay(store):
    context = start(store)
    with pytest.raises(ConversationRefused) as error:
        save(store, context, session_current=lambda: False)
    assert error.value.status == 401
    assert store.load(context.matter.id) is None
    save(store, context)
    with pytest.raises(ConversationRefused):
        save(store, start(store), session_current=lambda: False)


def test_revoked_session_after_save_does_not_disclose_reply(store):
    context = start(store)
    checks = iter([True, False])
    with pytest.raises(ConversationRefused) as error:
        save(store, context, session_current=lambda: next(checks))
    assert error.value.status == 401
    assert error.value.committed == "committed"
    assert start(store).replay is not None
