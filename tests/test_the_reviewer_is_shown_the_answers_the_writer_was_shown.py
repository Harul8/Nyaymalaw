"""The reviewer is shown what the writer was shown (plan AN.51, 51c; D197; the review's F-18; AN.48 register item 10).

The writer is given the conversation with the answers the advocate gave to NM's questions while the turn worked. The reviewer
was given a copy with those answers taken out - the copy the fingerprint binds - although the code's own note said they were
shown to it. A fact the advocate supplied in an answer was then, to the reviewer, a fact nobody gave: a correct paragraph
could be cut as unsupported, and a paragraph contradicting the answer could not be noticed. The reviewer's packet is now made
from the conversation as the writer read it; what the review binds is unchanged. Synthetic matter, scripted model.
"""
from __future__ import annotations

import json

import pytest

from nm.core_engine import turn
from nm.core_engine.conversation import chat_matter_id
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture
from tests.test_nm_asks_in_the_middle_of_a_turn import Desk, proposal, proposer

pytestmark = pytest.mark.class_a
REVIEWS = ("core_response_review", "core_response_cross_check")


def packets(model, *operations):
    return [json.loads(payload) if isinstance(payload, str) else payload for name, payload in model.calls if name in operations]


def answered(store):  # noqa: F811
    model = ScriptedModel(legal=True)
    response = run(store, model, propose=proposer(proposal()), desk=Desk({"q1": {"chosen": ["The seller"]}}))
    assert response["committed"] == "committed"
    return model, response


def test_every_review_of_a_turn_in_which_the_advocate_answered_is_sent_the_answer(store):  # noqa: F811
    model, _ = answered(store)
    reviews = packets(model, "core_response_review")
    assert reviews, "the turn reviewed what it wrote"
    for packet in reviews:
        assert packet["original_context"]["answers"] == [
            {"question": "Whom do you act for?", "answer": "The seller", "given_by": "the advocate"}]


def test_the_reviewer_reads_the_conversation_exactly_as_the_writer_read_it(store):  # noqa: F811
    model, _ = answered(store)
    written = {json.dumps(packet["original_context"], sort_keys=True) for packet in packets(model, "core_response_writer")
               if "answers" in packet["original_context"]}
    reviewed = {json.dumps(packet["original_context"], sort_keys=True) for packet in packets(model, "core_response_review")}
    assert written and reviewed <= written


def test_the_saved_turn_still_reads_back_as_bound(store):  # noqa: F811
    """What the review binds leaves the answers out, as before: the saved review is admitted again on reading the turn back."""
    _, response = answered(store)
    matter = store.load(chat_matter_id("owner", response["chat_id"]))
    (row,) = turn.saved_rows(matter, "owner")
    assert [(a["chosen"], a["how"]) for a in row["asked"]["answers"]] == [(["The seller"], "answered")]


def test_a_turn_in_which_nothing_was_asked_sends_the_reviewer_no_answers(store):  # noqa: F811
    model = ScriptedModel(legal=True)
    assert run(store, model)["committed"] == "committed"
    reviews = packets(model, "core_response_review")
    assert reviews and all("answers" not in packet["original_context"] for packet in reviews)
