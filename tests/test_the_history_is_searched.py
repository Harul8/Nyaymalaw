"""The conversation history is searched (plan AN.55, piece 55a; D254, D332, D355(e)).

One box over the history finds the signed-in advocate's conversations holding every word typed - in the conversation's name or
NM's title, its particulars and the advocate's own messages - without regard to case, newest first and ten at a time like the
history, each saying where the words were found. It reads each conversation's sealed line, never the conversation; what it
reads is never sent with the list. Another advocate's conversations, and a deleted one, are not found. The words of answers and
papers are not searched. Offline: the served application with scripted models and invented words.
"""
from __future__ import annotations

import pytest

from tests.served_application import OTHER, successful

pytestmark = pytest.mark.class_a


def searched(served, words, client=None, **page):
    reply = (client or served.client).get("/api/work", params={"q": words, **page})
    assert reply.status_code == 200, reply.text
    return reply.json()


@pytest.fixture
def three(served):
    """Three conversations of the owner's, newest last: one renamed, one with particulars, one as sent."""
    lease = successful(served, message="Inspect this reported account of the Andheri shop lease.", turn_id="turn-1")["chat_id"]
    cheque = successful(served, message="Inspect this reported account of a dishonoured cheque.", turn_id="turn-2")["chat_id"]
    plain = successful(served, message="Inspect this reported account of a boundary wall.", turn_id="turn-3")["chat_id"]
    assert served.client.put(f"/api/chats/{lease}/name", json={"name": "Mehta lease renewal"}).status_code == 200
    assert served.client.put(f"/api/chats/{cheque}/particulars",
                             json={"client": "Asha Rao", "court": "Metropolitan Magistrate, Esplanade"}).status_code == 200
    return {"lease": lease, "cheque": cheque, "plain": plain}


def test_every_word_must_be_found_anywhere_without_regard_to_case_and_each_row_says_where(served, three):
    found = searched(served, "ANDHERI")
    assert [chat["chat_id"] for chat in found["chats"]] == [three["lease"]]
    assert found["chats"][0]["found_in"] == ["your messages"] and found["searched"] == "andheri"
    found = searched(served, "mehta shop")
    assert [chat["chat_id"] for chat in found["chats"]] == [three["lease"]]
    assert found["chats"][0]["found_in"] == ["title", "your messages"], "one word in the name, one in a message"
    found = searched(served, "asha esplanade")
    assert [(chat["chat_id"], chat["found_in"]) for chat in found["chats"]] == [(three["cheque"], ["particulars"])]
    assert searched(served, "asha andheri")["chats"] == [], "every word must be found in the one conversation"
    assert searched(served, "inspect")["chat_count"] == 3


def test_results_come_in_the_history_s_own_order_and_ten_at_a_time_like_it(served, three):
    # The history is newest saved first; a rename or particulars written is a save, so it moves its conversation up (found 25 Nov
    # 2026, as any save does - an answer, a title).
    history = [chat["chat_id"] for chat in served.client.get("/api/work").json()["chats"]]
    assert history == [three["cheque"], three["lease"], three["plain"]]
    first = searched(served, "reported", limit=2, offset=0)
    assert [chat["chat_id"] for chat in first["chats"]] == history[:2]
    assert first["chat_count"] == 3 and first["has_more"] is True and first["next_offset"] == 2
    rest = searched(served, "reported", limit=2, offset=2)
    assert [chat["chat_id"] for chat in rest["chats"]] == history[2:] and rest["has_more"] is False


def test_what_the_search_reads_is_never_sent_and_an_empty_box_is_the_history(served, three):
    for reply in (searched(served, "lease"), served.client.get("/api/work").json()):
        assert all("find" not in chat for chat in reply["chats"])
    whole = searched(served, "   ")
    assert whole["chat_count"] == 3 and "searched" not in whole and all("found_in" not in chat for chat in whole["chats"])
    assert served.client.get("/api/work", params={"q": "x" * 201}).status_code == 422


def test_another_advocate_s_and_a_deleted_conversation_are_not_found(served, three):
    other = served.login(OTHER)
    assert searched(served, "andheri", client=other)["chats"] == []
    assert served.client.delete(f"/api/chats/{three['lease']}").status_code == 200
    assert searched(served, "andheri")["chats"] == []
    assert searched(served, "inspect")["chat_count"] == 2
