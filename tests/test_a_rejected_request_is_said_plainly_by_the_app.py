"""What the app answers when the AI service rejects NM's own request outside a turn (plan AN.52, 52i3; D215; F-31).

Each answer that had the usage limit's own words took a rejection of NM's own request for an outage: 'The dictation could not
be transcribed just now. Try again.', 'Live words are not available just now.', 'The pages could not be read just now. Try
again.', and, for a message sent while a matter waits, 'NM could not read this message just now ... send it again'. Each now
says, in the words written once (nm/shared/model_port.py), that the AI service rejected NM's own request - the installation's
fault, not the advocate's - with its own code, and the outage keeps the words it had. The provider's words are the operator's.

Offline: the served application with stand-in models; no browser; no model call.
"""
from __future__ import annotations

import logging

import pytest

from nm.app import api
from nm.core_engine import steps
from nm.shared.model_port import REQUEST_REJECTED_MESSAGE, ModelError, ProviderUnavailable, RequestRejected
from tests.test_a_message_while_a_matter_waits import Reader, held, reading, say, waiting_matter
from tests.test_core_served import served  # noqa: F401 - served is a fixture
from tests.test_core_voice import Hearing, wav

pytestmark = pytest.mark.class_a
SAID_BY_THE_PROVIDER = "Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-...abcd'}}"


def _said_to_the_page(answer):
    return answer.text


# ------------------------------------------------------------- dictation, as a recording and live ---

def test_dictation_that_is_rejected_says_so_with_its_own_code(served, monkeypatch, caplog):
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: Hearing(
        fails=RequestRejected(SAID_BY_THE_PROVIDER)))
    with caplog.at_level(logging.WARNING):
        refused = served.client.post("/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})
    assert refused.status_code == 503
    assert refused.json()["detail"] == {"why": REQUEST_REJECTED_MESSAGE, "code": "request_rejected"}
    assert "sk-" not in refused.text and "API key" not in refused.text
    assert any(record.levelname == "ERROR" and "rejected" in record.getMessage() for record in caplog.records)


def test_dictation_the_service_could_not_reach_still_says_try_again(served, monkeypatch):
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: Hearing(
        fails=ProviderUnavailable("down")))
    refused = served.client.post("/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})
    assert refused.status_code == 503 and refused.json()["detail"]["code"] == "dictation_unavailable"


class _Live:
    def __init__(self, error):
        self.error = error

    async def live_transcription(self, *, prompt, minutes):
        raise self.error


@pytest.mark.parametrize("error, why", [(RequestRejected(SAID_BY_THE_PROVIDER), REQUEST_REJECTED_MESSAGE),
                                        (ProviderUnavailable("down"), "Live words are not available just now.")])
def test_live_words_that_are_rejected_say_so_and_an_outage_says_what_it_did(served, monkeypatch, error, why):
    served.client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    monkeypatch.setattr(served.app, "live_dictation_reader", lambda advocate_id, *, session_current: _Live(error))
    with served.client.websocket_connect("/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        assert socket.receive_json() == {"live": False, "why": why}


# ------------------------------------------------------------- the reading of scanned pages ---

def test_a_reading_that_ends_on_a_rejection_says_so_with_its_own_code():
    said = api._reading_error(RequestRejected(SAID_BY_THE_PROVIDER))
    assert said == {"status": 503, "why": REQUEST_REJECTED_MESSAGE, "code": "request_rejected"}
    assert api._reading_error(ProviderUnavailable("down"))["code"] == "document_reading_unavailable", "an outage as before"
    assert api._reading_error(ModelError("other"))["code"] == "document_reading_unavailable"


# ------------------------------------------------------------- a message sent while a matter waits ---

def test_a_message_whose_reading_is_rejected_is_kept_and_said_as_the_installations_fault(served, caplog):
    waiting_matter(served)
    reading(served, Reader(RequestRejected(SAID_BY_THE_PROVIDER)))
    with caplog.at_level(logging.WARNING):
        reply = say(served, "Go ahead.")
    assert reply.status_code == 409
    heard = reply.json()["detail"]["heard"]
    assert heard["taken"] == "unread" and heard["said"].startswith(REQUEST_REJECTED_MESSAGE)
    assert "just now" not in heard["said"] and "sk-" not in reply.text
    assert held(served)["go"]["heard"][-1]["text"] == "Go ahead.", "the message is kept"
    assert steps.waiting_of(held(served)) == "understood", "and nothing ran"
    assert any(record.levelname == "ERROR" for record in caplog.records if "rejected" in record.getMessage())


def test_a_message_whose_reader_could_not_be_reached_still_says_just_now(served):
    waiting_matter(served)
    reading(served, Reader(ProviderUnavailable("Synthetic outage")))
    heard = say(served, "Go ahead.").json()["detail"]["heard"]
    assert heard["taken"] == "unread" and "just now" in heard["said"]
