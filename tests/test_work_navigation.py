"""My work navigation reads saved headings without evaluating legal sources."""
from dataclasses import replace

from nm.app import api
from nm.brain.turn import BrainService, BrainTurn, chat_matter_id
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_turn import Model, plan


def test_work_navigation_is_authenticated(client):
    client.cookies.clear()
    assert client.get("/api/work").status_code == 401


def test_work_navigation_does_not_release_labels_after_session_revocation(
        client, wired, monkeypatch):
    owned = Matter.create("adv_demo", "Cedar client: Access obstruction")
    wired.store.commit(owned, expected_version=0)
    read = wired.store.list_for

    def revoked_during_read(advocate_id):
        held = read(advocate_id)
        assert wired.directory.close_all_sessions(advocate_id, "Synthetic revocation") == 1
        return held

    monkeypatch.setattr(wired.store, "list_for", revoked_during_read)

    response = client.get("/api/work")

    assert response.status_code == 401, response.text
    assert owned.title not in response.text
    assert owned.id not in response.text


def test_work_navigation_reads_once_and_returns_latest_saved_headings(
        client, wired, monkeypatch):
    older = Matter.create("adv_demo", "Cedar client: Agreement termination")
    newer = Matter.create("adv_demo", "Elm client: Access obstruction")
    wired.store.commit(older, expected_version=0)
    wired.store.commit(newer, expected_version=0)
    held = replace(wired.store.list_for("adv_demo"), saved_at=(
        (older.id, "2026-10-01T12:00:00+00:00"),
        (newer.id, "2026-10-02T12:00:00+00:00"),
    ))
    reads = []

    def list_for(advocate_id):
        reads.append(advocate_id)
        return held

    def unnecessary(*args, **kwargs):
        raise AssertionError("Saved heading navigation must not evaluate legal sources")

    monkeypatch.setattr(wired.store, "list_for", list_for)
    monkeypatch.setattr(api, "_registers", unnecessary)
    monkeypatch.setattr(api, "_checked_checklists", unnecessary)
    monkeypatch.setattr(wired, "source_generation_guard", unnecessary)
    monkeypatch.setattr(wired, "_model_for", unnecessary)

    response = client.get("/api/work")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert reads == ["adv_demo"]
    assert response.json() == {
        "state": "ok",
        "matters": [
            {"matter_id": newer.id, "matter": newer.title,
             "last_updated": "2026-10-02T12:00:00+00:00"},
            {"matter_id": older.id, "matter": older.title,
             "last_updated": "2026-10-01T12:00:00+00:00"},
        ],
        "row_count": 2, "chats": [], "chat_count": 0,
        "unavailable": False, "unreadable": [],
    }


def test_work_navigation_preserves_pending_chat_contract_and_account_scope(
        client, wired, monkeypatch):
    monkeypatch.setattr(wired, "_model_for",
                        lambda *args, **kwargs: Model([plan("Hello")]))
    started = client.post("/api/turn", json={
        "message": "Hello", "turn_id": "navigation-chat"})
    assert started.status_code == 200, started.text
    chat_id = started.json()["chat_id"]
    owned = Matter.create("adv_demo", "Cedar client: Access obstruction")
    foreign = Matter.create("another-advocate", "Private client: Private subject")
    wired.store.commit(owned, expected_version=0)
    wired.store.commit(foreign, expected_version=0)
    BrainService(wired.store, Model([plan("Private words")])).run(
        BrainTurn("another-advocate", "Private words", "foreign-navigation-chat"))
    pending = client.get("/api/chats").json()

    response = client.get("/api/work")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["chats"] == pending["chats"]
    assert result["chat_count"] == 1
    assert result["chats"][0]["chat_id"] == chat_id
    assert result["chats"][0]["preview"] == "Hello"
    assert result["row_count"] == 1
    assert result["matters"][0]["matter_id"] == owned.id
    assert "Private" not in response.text
    assert "foreign-navigation-chat" not in response.text
    assert foreign.id not in response.text


def test_work_navigation_retains_readable_rows_when_a_chat_or_file_is_incomplete(
        client, wired, monkeypatch):
    monkeypatch.setattr(wired, "_model_for",
                        lambda *args, **kwargs: Model([plan("Hello")]))
    started = client.post("/api/turn", json={
        "message": "Hello", "turn_id": "navigation-chat"})
    assert started.status_code == 200, started.text
    chat_id = started.json()["chat_id"]
    matter = wired.store.load(chat_matter_id("adv_demo", chat_id))
    incomplete = {"turn_id": "unreleased-navigation-turn", "matter_id": matter.id,
                  "advocate_id": matter.advocate_id, "message": "Unread released reply"}
    wired.store.commit(replace(
        matter, brain_chat=(*matter.brain_chat, incomplete), version=matter.version + 1),
        expected_version=matter.version)
    owned = Matter.create("adv_demo", "Cedar client: Access obstruction")
    wired.store.commit(owned, expected_version=0)
    pending = client.get("/api/chats").json()
    held = replace(wired.store.list_for("adv_demo"), unreadable=("unreadable-file",))
    monkeypatch.setattr(wired.store, "list_for", lambda advocate_id: held)

    response = client.get("/api/work")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "incomplete"
    assert result["unavailable"] is True
    assert result["unreadable"] == ["unreadable-file"]
    assert result["row_count"] == 1
    assert result["matters"][0]["matter_id"] == owned.id
    assert result["chat_count"] == 1
    assert result["chats"] == pending["chats"]
    assert result["chats"][0]["state"] == "incomplete"
    assert result["chats"][0]["preview"] == "Hello"


def test_detailed_matter_list_keeps_its_checked_projection(client, wired, monkeypatch):
    owned = Matter.create("adv_demo", "Cedar client: Access obstruction")
    wired.store.commit(owned, expected_version=0)
    projected = []

    def registers(held, *, request):
        projected.extend(matter.id for matter in held)
        return {}

    monkeypatch.setattr(api, "_registers", registers)

    response = client.get("/api/matters")

    assert response.status_code == 200, response.text
    result = response.json()
    assert projected == [owned.id]
    assert result["bounded_by"] == "matter_count"
    assert result["matters"][0]["matter"] == owned.title
    assert "next_deadline" in result["matters"][0]
    assert "client" in result["matters"][0]
