"""A new conversation's first stop names the conversation it was kept in (plan AN.48, D134: every message is worked step by
step; found mending the browser journeys, 15 Nov 2026).

The page sends every message step by step, so a new conversation's first message ends in a stop - for the go-ahead, or part-way
with what was finished kept. The stop's reply named the conversation the request named, which for a new one is none. The page
learns a new conversation's id from the step's progress while it works; where the step ended before the page first asked (a
quick step), the page could not read the stop card and showed the red "NM stopped" message with Continue in place of the
go-ahead (measured in Chromium with the offline doubles). The stop now names the conversation it was kept in. A refusal that kept
nothing names only what the request named: there is no conversation to read.

Offline: the scripted served application; no model call.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nm.app import api
from nm.core_engine.conversation import ConversationRefused, stored_chat
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}


def test_the_first_stop_of_a_new_conversation_names_it_and_its_card_is_read_by_that_name(served):
    scripted_answers(served, Scripted())
    sent = served.client.post("/api/turn", json=SENT)
    detail = sent.json()["detail"]
    assert sent.status_code == 409 and detail["code"] == "waiting" and detail["kept"] is True
    assert detail["chat_id"] == stored_chat(OWNER, None, "turn-1")
    card = served.client.get(f"/api/chats/{detail['chat_id']}").json()["pending"]["stopped"]
    assert card["code"] == "waiting" and card["waiting"]["after"] == "understood", "the page reads the go-ahead card by it"


def test_a_stop_in_an_open_conversation_names_that_conversation(served):
    scripted_answers(served, Scripted())
    chat = served.client.post("/api/turn", json=SENT).json()["detail"]["chat_id"]
    went = served.client.post("/api/turn/go", json={"chat_id": chat, "turn_id": "turn-1", "choice": "next"})
    assert went.status_code == 409 and went.json()["detail"]["chat_id"] == chat


def test_a_refusal_that_kept_nothing_names_only_what_the_request_named():
    req = SimpleNamespace(turn_id="turn-1", chat_id=None)
    withheld = ConversationRefused("Not answered.", status=503, code="answer_withheld")
    withheld.chat_id = "a-conversation-never-saved"
    assert api._conversation_error(withheld, req)["chat_id"] is None
    kept = ConversationRefused("Waiting.", status=409, code="waiting", retryable=True)
    kept.kept, kept.chat_id = True, "the-conversation-it-was-kept-in"
    assert api._conversation_error(kept, req)["chat_id"] == "the-conversation-it-was-kept-in"
    named = SimpleNamespace(turn_id="turn-1", chat_id="the-open-one")
    assert api._conversation_error(kept, named)["chat_id"] == "the-open-one", "an open conversation is the one named"
