"""The served route preserves authentication, history and truthful status.

Written while the engine was paused; since the owner resumed the build (10 Oct 2026)
the engine is served, so the two paused-only checks now guard what remains true of
them: a turn that cannot be taken does no model work, saves nothing and says why,
and a conversation from the earlier engine is kept but not continued. Offline HTTP
tests, not model or browser acceptance.
"""
from dataclasses import replace

import pytest

from nm.core_engine.conversation import chat_matter_id
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def _no_work(*args, **kwargs):
    raise AssertionError("A paused conversation must not call a model or save input")


def test_a_turn_that_cannot_be_taken_is_truthful_and_performs_no_work(client, wired, monkeypatch):
    monkeypatch.setattr(wired, "_model_for", _no_work)
    monkeypatch.setattr(wired.store, "commit", _no_work)
    before = wired.store.list_for("adv_demo")
    response = client.post("/api/turn", json={
        "message": "Synthetic brief for a conversation that does not exist.",
        "turn_id": "pause-check-turn", "chat_id": "pause-check-chat"})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "history_unavailable"
    assert detail["committed"] == "not_committed"
    assert detail["retryable"] is False
    assert detail["turn_id"] == "pause-check-turn"
    assert detail["chat_id"] == "pause-check-chat"
    assert "could not be found" in detail["why"]
    assert wired.store.list_for("adv_demo") == before


def test_paused_route_still_requires_an_authenticated_session(client):
    client.cookies.clear()
    response = client.post("/api/turn", json={"message": "Synthetic brief"})
    assert response.status_code == 401


def test_paused_route_still_checks_browser_request_origin(client):
    response = client.post("/api/turn", json={"message": "Synthetic brief"},
                           headers={"origin": "https://untrusted.example"})
    assert response.status_code == 403


def test_an_earlier_matter_is_retained_untouched_and_neither_listed_nor_opened(client, wired):
    # Plan AN.48 (D307): the history lists conversations only and no address opens a matter saved before conversations; its file
    # is kept as it was. It once checked that such a matter was listed to its owner alone and answered 409 to them.
    own = wired.store.commit(Matter.create("adv_demo", "Owned historical matter"),
                             expected_version=0)
    foreign = wired.store.commit(Matter.create("another_advocate", "Foreign private matter"),
                                 expected_version=0)
    before = wired.store.load(own.id)
    response = client.get("/api/work")
    assert response.status_code == 200
    listed = response.json()
    assert "matters" not in listed and listed["chats"] == [] and listed["total"] == 0
    for matter in (own, foreign):
        assert client.get(f"/api/matters/{matter.id}").status_code == 404
    assert wired.store.load(own.id) == before


def test_an_earlier_engine_s_conversation_is_kept_but_not_continued(client, wired):
    earlier = replace(Matter.create("adv_demo", "Earlier engine conversation"),
                      id=chat_matter_id("adv_demo", "retained-historical-chat"))
    wired.store.commit(earlier, expected_version=0)
    response = client.get("/api/chats/retained-historical-chat")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "historical_conversation"
    assert "preserved but cannot be continued" in response.json()["detail"]["why"]
    assert client.get("/api/chats/never-existed").status_code == 404
