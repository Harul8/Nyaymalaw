"""An advocate renames their own conversation (plan AN.55, piece 55c2; D255, D355).

The name stands in place of NM's title wherever the title is shown - the history, the conversation's heading, Recently deleted -
and an empty name gives NM's title back. Only the advocate's own conversation, only while NM is not working on it; a name that
cannot be kept is refused with why and nothing is written; a write that met the conversation moving is made again once on it as
it then stands. Offline: the served application with scripted models and invented words.
"""
from __future__ import annotations

import pytest

from nm.app import api
from nm.shared.store_port import StaleWrite
from tests.served_application import OTHER, successful

pytestmark = pytest.mark.class_a


def renamed(served, chat_id, name, client=None):
    return (client or served.client).put(f"/api/chats/{chat_id}/name", json={"name": name})


def listed(served, chat_id, client=None):
    chats = (client or served.client).get("/api/work").json()["chats"]
    return next((chat for chat in chats if chat["chat_id"] == chat_id), None)


def test_the_name_is_shown_wherever_the_title_is_and_an_empty_name_gives_nm_s_title_back(served):
    chat_id = successful(served)["chat_id"]
    before = served.client.get(f"/api/chats/{chat_id}/title").json()["title"]
    reply = renamed(served, chat_id, "  Mehta  lease renewal ")
    assert reply.status_code == 200, reply.text
    assert reply.json() == {"state": "saved", "chat_id": chat_id, "title": "Mehta lease renewal", "named": True}
    line = listed(served, chat_id)
    assert line["title"] == "Mehta lease renewal" and line["named"] is True
    assert served.client.get(f"/api/chats/{chat_id}").json()["title"] == "Mehta lease renewal"
    assert served.client.get(f"/api/chats/{chat_id}/title").json()["title"] == "Mehta lease renewal"
    back = renamed(served, chat_id, "").json()
    assert back["named"] is False and back["title"] == before
    assert listed(served, chat_id)["title"] == before and "named" not in listed(served, chat_id)
    # A conversation the advocate deletes is named in Recently deleted by the name they gave it.
    renamed(served, chat_id, "Mehta lease renewal")
    assert served.client.delete(f"/api/chats/{chat_id}").status_code == 200
    assert served.client.get("/api/deleted-chats").json()["deleted"][0]["title"] == "Mehta lease renewal"


def test_a_name_that_cannot_be_kept_is_refused_with_why_and_nothing_is_written(served):
    chat_id = successful(served)["chat_id"]
    version = served.client.get(f"/api/chats/{chat_id}").json()["matter_version"]
    for name, why in [("x" * 121, "121 characters"), ("see https://example.test", "link")]:
        reply = renamed(served, chat_id, name)
        assert reply.status_code == 422 and why in reply.json()["detail"]["why"], reply.text
    assert served.client.get(f"/api/chats/{chat_id}").json()["matter_version"] == version


def test_only_the_advocate_s_own_conversation_is_renamed(served):
    chat_id = successful(served)["chat_id"]
    other = served.login(OTHER)
    assert renamed(served, chat_id, "Not theirs", client=other).status_code == 404
    assert renamed(served, "no-such-conversation", "Anything").status_code == 404
    assert listed(served, chat_id).get("named") is None
    # Without the page's own request token the server refuses before reading anything.
    served.client.headers.pop("x-nm-csrf")
    assert renamed(served, chat_id, "No token").status_code == 403


def test_while_nm_works_on_the_conversation_it_is_not_renamed(served, monkeypatch):
    chat_id = successful(served)["chat_id"]
    working = {"now": True}
    monkeypatch.setattr(api, "_held", lambda matter: {"turn_id": "turn-at-work"})
    monkeypatch.setattr(served.app, "turn_running", lambda advocate_id, turn_id: working["now"] and turn_id == "turn-at-work")
    reply = renamed(served, chat_id, "Mehta lease renewal")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "conversation_at_work"
    assert "Rename it once NM has finished or stopped" in reply.json()["detail"]["why"]
    assert listed(served, chat_id).get("named") is None
    working["now"] = False
    assert renamed(served, chat_id, "Mehta lease renewal").json()["named"] is True, "once NM has finished it is renamed"


def test_a_write_that_met_the_conversation_moving_is_made_again_once_then_refused(served, monkeypatch):
    chat_id = successful(served)["chat_id"]
    real, calls = api.save_name, []

    def moved(store, matter, name, times):
        calls.append(name)
        if len(calls) <= times:
            raise StaleWrite("moved meanwhile")
        return real(store, matter, name)

    monkeypatch.setattr(api, "save_name", lambda store, matter, name: moved(store, matter, name, 1))
    assert renamed(served, chat_id, "Second try").json()["title"] == "Second try" and len(calls) == 2
    calls.clear()
    monkeypatch.setattr(api, "save_name", lambda store, matter, name: moved(store, matter, name, 2))
    reply = renamed(served, chat_id, "Never saved")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "changed_meanwhile"
    assert listed(served, chat_id)["title"] == "Second try"
