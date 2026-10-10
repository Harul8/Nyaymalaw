"""The paused public route preserves authentication, history and truthful status.

These are offline HTTP tests of the clean-slate shell, not model or browser
acceptance of the future core engine.
"""
import pytest

from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def _no_work(*args, **kwargs):
    raise AssertionError("A paused conversation must not call a model or save input")


def test_paused_turn_is_truthful_and_performs_no_work(client, wired, monkeypatch):
    monkeypatch.setattr(wired, "_model_for", _no_work)
    monkeypatch.setattr(wired.store, "commit", _no_work)
    before = wired.store.list_for("adv_demo")
    response = client.post("/api/turn", json={
        "message": "Synthetic brief that must not be recorded while paused.",
        "turn_id": "pause-check-turn", "chat_id": "pause-check-chat"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "engine_paused"
    assert detail["committed"] == "not_committed"
    assert detail["retryable"] is False
    assert detail["turn_id"] == "pause-check-turn"
    assert detail["chat_id"] == "pause-check-chat"
    assert "Nothing you send now is saved" in detail["why"]
    assert wired.store.list_for("adv_demo") == before


def test_paused_route_still_requires_an_authenticated_session(client):
    client.cookies.clear()
    response = client.post("/api/turn", json={"message": "Synthetic brief"})
    assert response.status_code == 401


def test_paused_route_still_checks_browser_request_origin(client):
    response = client.post("/api/turn", json={"message": "Synthetic brief"},
                           headers={"origin": "https://untrusted.example"})
    assert response.status_code == 403


def test_history_is_retained_and_only_its_owner_can_see_it(client, wired):
    own = wired.store.commit(Matter.create("adv_demo", "Owned historical matter"),
                             expected_version=0)
    foreign = wired.store.commit(Matter.create("another_advocate", "Foreign private matter"),
                                 expected_version=0)
    before = wired.store.load(own.id)
    response = client.get("/api/work")
    assert response.status_code == 200
    rows = response.json()["matters"]
    assert [row["matter_id"] for row in rows] == [own.id]
    assert rows[0]["state"] == "historical"
    assert client.get(f"/api/matters/{own.id}").status_code == 409
    assert client.get(f"/api/matters/{foreign.id}").status_code == 404
    assert wired.store.load(own.id) == before


def test_paused_history_is_not_presented_as_an_openable_new_chat(client):
    response = client.get("/api/chats/retained-historical-chat")
    assert response.status_code == 409
    assert "earlier brain" in response.json()["detail"]
