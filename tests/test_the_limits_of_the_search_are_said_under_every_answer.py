"""The limits of the search are said under every answer, in code's words (plan AN.51, piece 51e; D199, D253; AN.56's D262; the
review's F-26).

An answer rests on what the search found in the law NM holds: a fixed number of passages offered for choosing, a search that
can be incomplete or fail for a question, Acts the matter names that NM may not hold, and no check that a provision was later
amended or a judgment overruled. None of it was said. Code now reads it from the research a turn saved and says it - with each
turn of a conversation opened from the history, and at an address of its own for an answer just given. Nothing saved changes,
so an answer saved before this piece carries it too. Invented research records; a scripted turn through the served routes.
"""
from __future__ import annotations

import pytest

from nm.core_engine import search_said
from tests.test_core_served import served, successful  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def candidate(kind):
    return {"kind": kind, "id": f"{kind}:x"}


def record(searches=None, failures=None):
    return {"research": {"searches": searches or {}, "failures": failures or {}}}


READY = {"state": "ready", "candidates": [candidate("provision")] * 3 + [candidate("judgment")] * 2, "issues": []}


def test_a_turn_that_searched_nothing_has_nothing_said():
    assert search_said.said(record()) is None
    assert search_said.said({"research": None}) is None
    assert search_said.said(None) is None and search_said.said({}) is None


def test_what_was_searched_and_offered_is_counted_and_currency_is_always_said():
    said = search_said.said(record({"w1": READY, "w2": {**READY, "candidates": [candidate("provision")]}}))
    assert said["summary"] == search_said.SCOPE
    assert said["lines"] == ["2 questions were searched. The search offered 4 passages of Acts and 2 passages of judgments to "
                             "choose from.", search_said.CURRENCY]


def test_one_question_and_one_passage_are_said_in_the_singular():
    said = search_said.said(record({"w1": {**READY, "candidates": [candidate("provision"), candidate("judgment")]}}))
    assert said["lines"][0] == ("1 question was searched. The search offered 1 passage of Acts and 1 passage of judgments to "
                                "choose from.")


def test_an_incomplete_search_is_said_as_incomplete():
    said = search_said.said(record({"w1": READY, "w2": {**READY, "state": "partial"}}))
    assert ("For 1 question the search was incomplete: part of what it found could not be read. What could be read was used, "
            "and may not be all there is.") in said["lines"]


def test_a_question_whose_search_failed_is_said_with_codes_reason_once():
    why = "The held Acts could not be searched for this question: the ranking of what was found could not be used (X). Nothing was taken from a partial search."
    said = search_said.said(record({"w1": READY}, {"w2": {"stage": "search", "reason": why},
                                                    "w3": {"stage": "search", "reason": why},
                                                    "w4": {"stage": "pick", "reason": "another stage's own failure"}}))
    assert f"For 2 questions the held law could not be searched, and nothing was taken for them. {why}" in said["lines"]
    assert not any("another stage" in line for line in said["lines"])


def test_a_turn_whose_every_search_failed_still_says_so():
    said = search_said.said(record({}, {"w1": {"stage": "search", "reason": "Held-law search is not configured"}}))
    assert said["lines"] == ["For 1 question the held law could not be searched, and nothing was taken for it. Held-law search "
                             "is not configured.", search_said.CURRENCY]


def test_which_of_the_acts_and_sections_the_matter_named_nm_holds_is_said():
    searches = {
        "w1": {**READY, "instruments": [{"name": "Imagined  Relief Act, 1907", "candidates": ["imagined relief act 1907"]},
                                        {"name": "An Act Nobody Holds, 1999", "candidates": []}],
               "named": [{"act": "Imagined Relief Act, 1907", "section": "6", "state": "read", "found": ["p"], "reason": ""},
                         {"act": "Imagined Relief Act, 1890", "section": "6", "state": "not_held", "found": [],
                          "reason": "We hold an Act of this name of another year, not of the year written"}]},
        "w2": {**READY, "instruments": [{"name": "An Act Nobody Holds, 1999", "candidates": []},
                                        {"name": "A Short Name", "candidates": []}],
               "named": [{"act": "A Short Name", "section": "63", "state": "unavailable", "found": [],
                          "reason": "The list of checked short names of Acts could not be read"}]},
    }
    lines = search_said.said(record(searches))["lines"]
    assert ("Of the 3 Acts this matter named, NM holds 1. Not found in the law NM holds: An Act Nobody Holds, 1999 and A Short "
            "Name.") in lines
    assert ("Named and not read, because NM does not hold it: 6 of Imagined Relief Act, 1890 (We hold an Act of this name of "
            "another year, not of the year written).") in lines
    assert ("Named and could not be read or checked: 63 of A Short Name (The list of checked short names of Acts could not be "
            "read).") in lines
    assert not any("6 of Imagined Relief Act, 1907" in line for line in lines), "a section that was read needs no line"


def test_a_record_of_an_earlier_shape_is_read_for_what_it_has():
    said = search_said.said(record({"w1": {"state": "ready", "candidates": [candidate("provision")]}, "w2": "not a search"}))
    assert said["lines"][0].startswith("2 questions were searched. The search offered 1 passage of Acts and 0 passages")


def test_the_served_conversation_carries_it_with_each_turn_and_an_answer_just_given_can_ask_for_it(served):  # noqa: F811
    client, chat_id, turn_id = served.client, successful(served)["chat_id"], "turn-1"
    opened = client.get(f"/api/chats/{chat_id}")
    assert opened.status_code == 200
    (turn,) = opened.json()["turns"]
    assert turn["search_said"]["summary"] == search_said.SCOPE and turn["search_said"]["lines"][-1] == search_said.CURRENCY
    asked = client.get(f"/api/chats/{chat_id}/turns/{turn_id}/search-said")
    assert asked.status_code == 200 and asked.json() == {"search_said": turn["search_said"]}
    assert asked.headers["cache-control"] == "no-store"
    assert client.get(f"/api/chats/{chat_id}/turns/no-such-turn/search-said").status_code == 404
