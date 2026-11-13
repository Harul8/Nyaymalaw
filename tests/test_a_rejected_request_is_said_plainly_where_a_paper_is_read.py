"""Where a paper or a recording is read, a rejected request is said as the installation's fault (plan AN.52, 52i2; D215; F-31).

52i1 gave the provider's rejection of NM's own request its own name (RequestRejected) and made it a stop inside a turn. Reading
a scanned page or a recording is not a turn: it took the rejection for any provider failure, and the page or recording kept the
reason 'the AI could not read this page just now; it can be read again' - which promises a reading that will be rejected the
same way. It is now said as what it is, in words written once beside the usage-limit words (nm/shared/model_port.py), and the
page or recording still waits, to be read once the installation is put right. The provider's own words stay in the server's
log, at ERROR, because an operator must act on them.

Offline: the document desk on a temporary store, with stand-in models; no browser; no model call.
"""
from __future__ import annotations

import logging

import pytest

from nm.core_engine import documents
from nm.shared.model_port import (REQUEST_REJECTED_MESSAGE, REQUEST_REJECTED_WORDS, USAGE_LIMIT_WORDS, ProviderUnavailable,
                                  RequestRejected)
from tests.test_core_documents import ADVOCATE, desk, pdf  # noqa: F401 - desk is a fixture
from tests.test_core_page_reading import PageModel
from tests.test_core_voice import Hearing, wav

pytestmark = pytest.mark.class_a
SAID_BY_THE_PROVIDER = "Error code: 404 - {'error': {'message': 'The model `page-model-9` does not exist'}}"


def test_the_words_are_written_once_beside_the_usage_limit_words_and_name_no_provider():
    for words in (REQUEST_REJECTED_MESSAGE, REQUEST_REJECTED_WORDS):
        assert "rejected NM's own request" in words and "installation" in words
        assert "just now" not in words and "openai" not in words.lower() and "model" not in words.lower()
    assert REQUEST_REJECTED_WORDS[0].islower() and REQUEST_REJECTED_WORDS != USAGE_LIMIT_WORDS
    assert REQUEST_REJECTED_MESSAGE.endswith(".") and not REQUEST_REJECTED_WORDS.endswith(".")


def test_a_page_whose_reading_is_rejected_says_so_and_waits_and_the_pages_read_are_kept(desk, caplog):
    first = desk.receive(ADVOCATE, "bundle.pdf", pdf(["", "", ""]))
    model = PageModel({1: {"text": "Notice dated 3 October 2026", "readable": "all", "note": ""},
                       2: RequestRejected(SAID_BY_THE_PROVIDER), 3: RequestRejected(SAID_BY_THE_PROVIDER)})
    with caplog.at_level(logging.WARNING):
        renewed, calls = desk.read_waiting(ADVOCATE, documents.reference(first), model)
    one, two, three = renewed["pages"]
    assert one["state"] == "read", "a page already read is kept"
    for page in (two, three):
        assert (page["state"], page["code"], page["reason"]) == ("unread", "scanned", REQUEST_REJECTED_WORDS)
    assert documents.needs_transcription(renewed) == [2, 3], "they wait to be read once it is put right"
    assert len(calls) == 1
    assert documents.summary(renewed)["unread"] == [{"number": 2, "reason": REQUEST_REJECTED_WORDS},
                                                     {"number": 3, "reason": REQUEST_REJECTED_WORDS}]
    said = [record for record in caplog.records if "waits to be read again" in record.getMessage()]
    assert [record.levelname for record in said] == ["ERROR", "ERROR"], "an operator must act on it"
    assert all(SAID_BY_THE_PROVIDER in record.getMessage() for record in said), "the provider's words are the operator's"
    assert SAID_BY_THE_PROVIDER not in str(renewed), "and are not kept with the paper"


def test_a_page_the_service_could_not_reach_still_says_just_now(desk, caplog):
    """The neighbour: an outage is still an outage, with the words it had."""
    first = desk.receive(ADVOCATE, "memo.pdf", pdf(["", ""]))
    model = PageModel({1: ProviderUnavailable("down"), 2: {"text": "Page two", "readable": "all", "note": ""}})
    renewed, _calls = desk.read_waiting(ADVOCATE, documents.reference(first), model)
    assert renewed["pages"][0]["reason"] == "the AI could not read this page just now; it can be read again"
    assert [record.levelname for record in caplog.records if "waits to be read again" in record.getMessage()] == ["WARNING"]


def test_a_recording_whose_transcription_is_rejected_says_so_and_waits(desk, caplog):
    hearing = Hearing(fails=RequestRejected(SAID_BY_THE_PROVIDER))
    with caplog.at_level(logging.WARNING):
        renewed, calls = desk.read_waiting(ADVOCATE, documents.reference(desk.receive(ADVOCATE, "note.wav", wav())), hearing)
    page, = renewed["pages"]
    assert (page["state"], page["code"], page["reason"]) == ("unread", "audio", REQUEST_REJECTED_WORDS)
    assert documents.needs_transcription(renewed) == [1] and calls == []
    said = [record for record in caplog.records if "waits to be transcribed again" in record.getMessage()]
    assert [record.levelname for record in said] == ["ERROR"] and SAID_BY_THE_PROVIDER in said[0].getMessage()


def test_a_recording_the_service_could_not_reach_still_says_just_now(desk):
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(desk.receive(ADVOCATE, "note.wav", wav())),
                                   Hearing(fails=ProviderUnavailable("down")))
    assert renewed["pages"][0]["reason"] == "the recording could not be transcribed just now; it can be tried again"
