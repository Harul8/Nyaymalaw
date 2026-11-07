"""The turn record's line holds no word of the turn (plan AN.46, piece 46h; owner decision D120, 7 Nov 2026: "Yes add it").

A line says that a turn happened and how it went: when, how long, how it ended, the model and effort chosen, how many calls, what they
cost, how many documents. It cannot say what the turn was about."""
from __future__ import annotations

import pytest

from nm.arrive import turn_event_port
from nm.arrive.turn_event_port import EVENT_FIELDS, OUTCOMES, TurnEventPort

pytestmark = pytest.mark.class_a

FORBIDDEN = {"message", "text", "words", "answer", "matter", "matter_id", "chat", "chat_id", "turn_id", "conversation", "document",
             "documents_text", "file", "name", "title", "email", "address", "account", "advocate", "advocate_id", "note", "content"}


def test_a_line_is_given_only_times_names_and_numbers_and_no_identity_of_the_conversation():
    assert EVENT_FIELDS == ("started_at", "ended_at", "outcome", "model", "effort", "calls", "micro_usd", "documents")
    assert set(EVENT_FIELDS).isdisjoint(FORBIDDEN)


def test_a_turn_ends_one_of_four_ways_and_reopening_a_saved_answer_is_none_of_them():
    assert OUTCOMES == ("answered", "stopped", "refused", "failed")


def test_the_port_can_only_add_a_line():
    assert {name for name in vars(TurnEventPort) if not name.startswith("_")} == {"record"}
    assert issubclass(turn_event_port.TurnEventRefused, Exception)
