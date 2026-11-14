"""An advocate deletes a conversation, puts it back, or erases it, through the server's own routes (plan AN.53, D241's third
piece, its routes - 53h3a).

The store can mark a conversation deleted, put it back for thirty days and erase it, its own key first (53h1, 53h2); nothing
asked for any of it. Now a signed-in advocate can, through four routes: DELETE a conversation of their own - not while NM is
working on it, since its answer could then not be saved; list what they deleted, with when each will be erased and the name
the history showed; PUT one BACK; and ERASE one they deleted, at once, which cannot be undone. A deleted conversation is gone
from the history and from every address of it at once - the server lets go of what it kept of it - and a message sent to it,
from a page left open, is refused before NM does any work. Only the advocate's own: another advocate's conversation is not
there for them at any of these addresses.

Offline: the served application with stand-in models; no browser.
"""
from __future__ import annotations

import pytest

from nm.app import api
from nm.core_engine.conversation import chat_matter_id
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - served is a fixture
from tests.test_steps_run_as_jobs import Held

pytestmark = pytest.mark.class_a


@pytest.fixture
def chat(served):
    """The owner's saved conversation, listed once in the history (so its line is kept): its chat id."""
    reply = successful(served)
    history = served.client.get("/api/work").json()
    assert [row["chat_id"] for row in history["chats"]] == [reply["chat_id"]]
    return reply["chat_id"]


def _delete(client, chat_id):
    return client.request("DELETE", f"/api/chats/{chat_id}")


def test_a_deleted_conversation_is_gone_from_the_history_and_every_address_of_it_at_once(served, chat):
    assert served.client.get(f"/api/chats/{chat}").status_code == 200, "read once, and kept by the server"
    deleted = _delete(served.client, chat)
    assert deleted.status_code == 200, deleted.text
    said = deleted.json()
    assert said["state"] == "deleted" and said["chat_id"] == chat and said["deleted_at"] and said["erased_after"]
    assert served.client.get("/api/work").json()["chats"] == []
    for address in (f"/api/chats/{chat}", f"/api/chats/{chat}/title", f"/api/chats/{chat}/board"):
        assert served.client.get(address).status_code == 404, address
    assert chat_matter_id(OWNER, chat) not in api._READ and chat_matter_id(OWNER, chat) not in api._LISTED


def test_what_was_deleted_is_listed_with_its_name_and_when_it_will_be_erased_and_is_put_back_as_it_was(served, chat):
    before = served.client.get(f"/api/chats/{chat}").json()
    _delete(served.client, chat)
    listed = served.client.get("/api/deleted-chats").json()["deleted"]
    assert len(listed) == 1
    entry = listed[0]
    assert entry["preview"] == "Inspect this reported account." and entry["erased_after"] and entry["ref"]
    put_back = served.client.post(f"/api/deleted-chats/{entry['ref']}/put-back")
    assert put_back.status_code == 200 and put_back.json() == {"state": "put_back", "chat_id": chat}
    assert served.client.get("/api/deleted-chats").json()["deleted"] == []
    assert served.client.get(f"/api/chats/{chat}").json() == before, "put back as it was deleted"
    assert [row["chat_id"] for row in served.client.get("/api/work").json()["chats"]] == [chat]


def test_a_deleted_conversation_is_erased_at_once_when_its_advocate_asks_and_cannot_be_put_back(served, chat):
    ref = _delete(served.client, chat).json()["ref"]
    erased = served.client.post(f"/api/deleted-chats/{ref}/erase")
    assert erased.status_code == 200 and erased.json() == {"state": "erased", "chat_id": chat, "left": 0}, (
        "named from its kept line, so the page can close it where it is open")
    assert served.client.get("/api/deleted-chats").json()["deleted"] == []
    assert served.client.post(f"/api/deleted-chats/{ref}/put-back").status_code == 404, "an erasure cannot be undone"
    assert served.store.load(chat_matter_id(OWNER, chat)) is None
    assert not (served.store._root / "keys" / f"{chat_matter_id(OWNER, chat)}.key").exists()


def test_only_a_deleted_conversation_is_erased_by_the_erase_address(served, chat):
    ref = chat_matter_id(OWNER, chat)
    assert served.client.post(f"/api/deleted-chats/{ref}/erase").status_code == 404, "it must be deleted first"
    assert served.client.get(f"/api/chats/{chat}").status_code == 200


def test_another_advocate_can_neither_delete_nor_see_nor_put_back_nor_erase_it(served, chat):
    other = served.login(OTHER)
    assert _delete(other, chat).status_code == 404, "their own conversation of that id: there is none"
    ref = _delete(served.client, chat).json()["ref"]
    assert other.get("/api/deleted-chats").json()["deleted"] == []
    assert other.post(f"/api/deleted-chats/{ref}/put-back").status_code == 404
    assert other.post(f"/api/deleted-chats/{ref}/erase").status_code == 404
    assert served.client.get("/api/deleted-chats").json()["deleted"][0]["ref"] == ref, "still the owner's to put back"


def test_a_conversation_nm_is_working_on_is_not_deleted(served):
    scripted_answers(served, Scripted())
    held = Held(served)
    served.app.step_jobs.wait_seconds = 0.2
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert reply.status_code == 202
    assert held.entered.wait(10)
    chat = reply.json()["chat_id"]
    refused = _delete(served.client, chat)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "conversation_at_work"
    held.go.set()
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    for _ in range(100):
        if not served.app.turn_running(OWNER, "turn-1"):
            break
        import time
        time.sleep(0.02)
    assert _delete(served.client, chat).status_code == 200, "once NM has finished, it can be"


def test_a_message_sent_to_a_deleted_conversation_is_refused_before_nm_does_any_work(served, chat):
    _delete(served.client, chat)
    calls = len(served.model.calls)
    reply = served.client.post("/api/turn", json={"message": "And the second notice?", "turn_id": "turn-2", "chat_id": chat})
    assert reply.status_code == 410, reply.text
    assert reply.json()["detail"]["code"] == "conversation_deleted"
    assert len(served.model.calls) == calls, "no model call was made for it"


def test_a_route_that_names_nothing_is_not_found(served):
    assert _delete(served.client, "new_no_such_chat").status_code == 404
    assert served.client.post("/api/deleted-chats/chat_" + "0" * 64 + "/put-back").status_code == 404
    assert served.client.post("/api/deleted-chats/../keys/put-back").status_code == 404
