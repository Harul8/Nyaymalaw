"""Pending conversations remain recoverable through an authenticated list."""
from dataclasses import replace

from nm.brain.turn import BrainService, BrainTurn, chat_matter_id
from tests.test_brain_turn import Model, plan


def test_pending_chat_list_tracks_opening_and_scopes_to_the_account(
        client, wired, monkeypatch):
    account_model = Model([
        plan("Hello"),
        plan("My client disputes a terminated contract.", scope="proposed",
             step="legal_work", reply="I will check the contract and the record.",
             title="Contract dispute", summary="The client disputes termination."),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: account_model)

    assert client.get("/api/chats").json() == {
        "state": "ok", "chats": [], "chat_count": 0, "unavailable": False}
    first = client.post("/api/turn", json={"message": "Hello", "turn_id": "chat-first"})
    assert first.status_code == 200, first.text
    chat_id = first.json()["chat_id"]
    BrainService(wired.store, Model([plan("Private")])).run(
        BrainTurn("another-advocate", "Private", "other-chat"))

    listing = client.get("/api/chats")
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert listing.json()["state"] == "ok"
    assert listing.json()["chat_count"] == 1
    pending = listing.json()["chats"][0]
    assert pending["chat_id"] == chat_id
    assert pending["preview"] == "Hello"
    assert pending["turn_count"] == 1
    assert pending["state"] == "ok"
    assert pending["last_at"]
    assert client.get("/api/chats/other-chat").status_code == 404

    second = client.post("/api/turn", json={
        "message": "My client disputes a terminated contract.",
        "turn_id": "chat-second", "chat_id": chat_id})
    assert second.status_code == 200, second.text
    assert second.json()["matter_id"]
    assert client.get("/api/chats").json()["chats"] == []


def test_pending_chat_list_marks_an_incomplete_saved_conversation(
        client, wired, monkeypatch):
    monkeypatch.setattr(wired, "_model_for",
                        lambda *args, **kwargs: Model([plan("Hello")]))
    first = client.post("/api/turn", json={"message": "Hello", "turn_id": "chat-first"})
    assert first.status_code == 200, first.text
    chat_id = first.json()["chat_id"]
    matter = wired.store.load(chat_matter_id("adv_demo", chat_id))
    assert matter is not None
    incomplete_row = {"turn_id": "chat-second", "matter_id": matter.id,
                      "advocate_id": matter.advocate_id, "message": "Unverified words"}
    wired.store.commit(replace(matter, brain_chat=(*matter.brain_chat, incomplete_row),
                               version=matter.version + 1), expected_version=matter.version)

    listing = client.get("/api/chats")
    assert listing.status_code == 200
    assert listing.json()["state"] == "incomplete"
    assert listing.json()["unavailable"] is True
    assert listing.json()["chats"][0]["chat_id"] == chat_id
    assert listing.json()["chats"][0]["state"] == "incomplete"
    assert listing.json()["chats"][0]["preview"] == "Hello"
