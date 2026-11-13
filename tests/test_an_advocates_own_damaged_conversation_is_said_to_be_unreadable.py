"""An advocate's own damaged conversation is said to be unreadable, at every address of it (plan AN.53, 53j2; D225).

Each address that reads a saved conversation means to answer 'This conversation could not be read reliably.' when it cannot.
They caught the disk's error and a record that does not read as one, and not the store's own error for a file that will not
open (53j1), so the advocate's own damaged conversation was a server error at every one of them. One name now says what a
reading raises, and every such address uses it. Offline: the served app with stand-in models; no browser.
"""
from __future__ import annotations

import pytest

from tests.test_core_served import OWNER, served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
DAMAGE = {
    "overwritten": lambda blob: b"not a saved matter, and longer than the file was",
    "emptied": lambda blob: b"",
    "cut short": lambda blob: blob[: len(blob) // 2],
}
READS = ("/api/chats/{chat}", "/api/chats/{chat}/title", "/api/chats/{chat}/board", "/api/chats/{chat}/documents",
         "/api/chats/{chat}/turns/{turn}/note", "/api/chats/{chat}/turns/{turn}/passages/p1")
SAID = "This conversation could not be read reliably."


@pytest.fixture
def damaged(served, request):
    """(served, the address parts of the owner's one conversation), its file then damaged as the case says."""
    successful(served)
    (matter,) = served.store.list_for(OWNER).matters
    chat = served.client.get("/api/work").json()["chats"][0]["chat_id"]
    turn = served.client.get(f"/api/chats/{chat}").json()["turns"][0]["turn_id"]
    for address in READS:
        assert served.client.get(address.format(chat=chat, turn=turn)).status_code in (200, 404), "whole, it is read"
    path = served.store._matters / f"{matter.id}.nm"
    path.write_bytes(DAMAGE[request.param](path.read_bytes()))
    return served, {"chat": chat, "turn": turn}


@pytest.mark.parametrize("damaged", sorted(DAMAGE), indirect=True)
@pytest.mark.parametrize("address", READS)
def test_each_address_that_reads_the_conversation_says_it_could_not_be_read(damaged, address):
    served, parts = damaged
    answer = served.client.get(address.format(**parts))
    assert answer.status_code == 503 and answer.json()["detail"] == SAID


@pytest.mark.parametrize("damaged", sorted(DAMAGE), indirect=True)
def test_what_waits_is_said_not_to_be_saved_and_a_discard_says_it_could_not_be_read(damaged):
    served, parts = damaged
    queued = served.client.put(f"/api/chats/{parts['chat']}/queued", json={"queued": [{"text": "A line that waits."}]})
    assert queued.status_code == 503 and queued.json()["detail"]["code"] == "queue_not_saved"
    discard = served.client.post("/api/turn/discard", json={"chat_id": parts["chat"], "turn_id": parts["turn"]})
    assert discard.status_code == 503 and discard.json()["detail"] == SAID


@pytest.mark.parametrize("damaged", sorted(DAMAGE), indirect=True)
def test_how_a_turn_stands_is_answered_without_a_server_error(damaged):
    served, parts = damaged
    answer = served.client.get(f"/api/turn-progress?turn_id={parts['turn']}&chat_id={parts['chat']}")
    assert answer.status_code < 500
