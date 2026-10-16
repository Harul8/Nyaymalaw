"""The matter board from a conversation's saved understanding (owner decision, 15 Oct 2026).

Scripted turns prove the projection and its access, not the model's understanding.
"""
import pytest

from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.matter_board import board
from nm.core_engine.turn import saved_rows
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - pytest fixture
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def rows(store, chat_id):
    return saved_rows(store.load(chat_matter_id("owner", chat_id)), "owner")


def test_a_researched_turn_fills_the_board_with_its_understanding_and_what_research_did(store):
    first = run(store, ScriptedModel(legal=True))
    shown = board(rows(store, first["chat_id"]))
    assert shown["state"] == "ready" and shown["turn_id"] == "t1"
    dispute, = shown["disputes"]
    assert dispute["name"] == "Dispute 1" and dispute["between"] == ["client", "other party"]
    assert [q["status"] for q in dispute["questions"]] == ["researched"]
    assert dispute["questions"][0]["why"] == "It decides the advice."
    fact, = shown["facts"]
    assert fact["certainty"] == "reported" and fact["words"]  # the advocate's own words travel with it
    # Where the dispute was picked up from, and why it matters (research v9, 16 Oct 2026).
    assert dispute["fact_ids"] == [fact["id"]] == ["F1"]
    assert dispute["why_it_matters"] == "Dispute 1 decides what the client can recover."


def test_an_earlier_understanding_shows_no_why_it_matters(store):
    # Older conversations open as they are (owner, 16 Oct 2026); nothing is added to them.
    first = run(store, ScriptedModel(legal=True))
    saved = rows(store, first["chat_id"])
    record = saved[-1]["activities"]["research"]
    record["contract"] = "core_research_v8"
    for dispute in record["plan"]["proposal"]["understanding"]["disputes"]:
        del dispute["why_it_matters"]
    dispute, = board(saved)["disputes"]
    assert "why_it_matters" not in dispute and dispute["name"] == "Dispute 1"


def test_a_later_courtesy_does_not_empty_the_board(store):
    first = run(store, ScriptedModel(legal=True))
    run(store, ScriptedModel(legal=False), chat_id=first["chat_id"], turn_id="t2", message="Thanks.")
    shown = board(rows(store, first["chat_id"]))
    assert shown["state"] == "ready" and shown["turn_id"] == "t1"


def test_a_conversation_without_research_has_an_empty_board(store):
    first = run(store, ScriptedModel(legal=False))
    assert board(rows(store, first["chat_id"])) == {"state": "empty"}


def test_only_the_signed_in_owner_reads_a_conversations_board(served):
    reply = successful(served)
    url = f"/api/chats/{reply['chat_id']}/board"
    mine = served.client.get(url)
    assert mine.status_code == 200 and mine.json()["state"] == "ready"
    assert mine.headers["cache-control"] == "no-store"
    other = served.login(OTHER)
    assert other.get(url).status_code in (403, 404)
    from fastapi.testclient import TestClient
    from nm.app.main import create_app
    with TestClient(create_app(served.app)) as anonymous:
        assert anonymous.get(url).status_code == 401
