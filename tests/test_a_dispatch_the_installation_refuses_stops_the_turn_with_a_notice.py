"""A dispatch the installation refuses stops the turn with a service notice, not a server error (plan AN.53, 53e3; D236).

The gate refuses a dispatch the installation does not permit - a recipient not on its reviewed list, or (D236) a call whose
line in the outgoing-data log cannot be written. Part-way through a message that refusal went out of the turn as it was: what
NM had finished was kept, but the advocate was answered with a server error, and the stop was recorded as 'something went wrong
on NM's side'. It is now a stop of its own: said in code's words, with what was finished kept and Continue working once the
installation is put right. Nothing was sent, and the refusal is never turned into an answer.

Offline: the served application with stand-in models; no browser.
"""
from __future__ import annotations

import pytest

from nm.core_engine import turn
from nm.core_engine.conversation import stored_chat
from nm.shared.egress_contracts import EgressRefused
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1"}


def _refused_at(served, operation):
    """The stand-in model, with the gate refusing the dispatch of one step: (the scripted answers, a way to lift the refusal)."""
    scripted = Scripted()
    scripted_answers(served, scripted)
    answering, lifted = served.model.structured, []

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == operation and not lifted:
            raise EgressRefused("this installation does not permit sending ['client_matter'] to 'outside-ai' for model: "
                                "the record of what is sent could not be written")
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return scripted, lambda: lifted.append(True)


def test_the_advocate_is_answered_with_a_notice_and_what_nm_finished_is_kept(served):
    _refused_at(served, "core_response_overview")
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503, reply.text
    detail = reply.json()["detail"]
    assert detail["code"] == "sending_refused" and detail["kept"] is True
    assert turn.STOPS["sending_refused"] in detail["why"]
    assert "outside-ai" not in reply.text and "client_matter" not in reply.text, "the gate's own line is the operator's"
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    pending = served.client.get(f"/api/chats/{stored_chat(OWNER, None, 'turn-1')}").json()["pending"]
    assert pending["stopped"]["code"] == "sending_refused"
    assert pending["stopped"]["why"] == turn.STOPS["sending_refused"]
    assert pending["stopped"]["needs"] == turn.STOP_NEEDS["sending_refused"]


def test_continue_finishes_the_answer_once_the_refusal_is_lifted_and_writes_nothing_twice(served):
    scripted, lift = _refused_at(served, "core_response_overview")
    assert served.client.post("/api/turn", json=SENT).status_code == 503
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    chat_id = stored_chat(OWNER, None, "turn-1")
    written = len(scripted.payloads("core_response_writer"))
    still = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert still.status_code == 503 and still.json()["detail"]["code"] == "sending_refused", "refused again while it stands"
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    lift()
    reply = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert reply.status_code == 200 and reply.json()["committed"] == "committed", reply.text
    assert len(scripted.payloads("core_response_writer")) == written, "the sections finished are not written again"


def test_a_refusal_before_anything_was_understood_is_a_notice_too(served):
    _refused_at(served, "core_research_understand")
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "sending_refused", reply.text


def test_the_words_say_nothing_was_sent_and_what_puts_it_right():
    assert "sending_refused" in turn.STOPS and "sending_refused" in turn.STOP_NEEDS
    assert "Continue" in turn.STOP_NEEDS["sending_refused"]
