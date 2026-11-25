"""The diary of time limits across matters (plan AN.55, piece 55e1; D257, D332, D355(f)).

For each of the advocate's conversations, the time limits of its latest answer that worked any out: each last day code worked
out with its conversation, those still to come soonest first and those passed after them, the days from today counted by code,
how each stood on the day it was worked out, and those not worked out said with why - never a model's date, and with code's
note that it is not a court diary. Model words shown here pass the door for words outside an answer (51b). Read from each
conversation's sealed line; another advocate's are never in it. Offline: the served store, conversations saved with invented
time-limit records, and a fixed today.
"""
from __future__ import annotations

from datetime import date
from itertools import count

import pytest

from nm.app import api
from nm.core_engine.conversation import commit_turn, open_turn
from tests.served_application import OTHER, OWNER

pytestmark = pytest.mark.class_a
TODAY = date(2026, 11, 25)
#: Each conversation made here has turns of its own: a new conversation's identity comes from its first turn's.
MADE = count(1)


def entry(what, last_day, stood="open", done=None):
    return {"id": what, "what": what, "provision_name": "Article 54", "provision": {"act": "The Limitation Act, 1963"},
            "working": {"last_day": last_day}, "standing": {"state": stood, "days": 0}, "done": done}


def worked(*entries, not_assessed=(), today="2026-11-01"):
    return {"contract": "core_calculation_v9", "state": "worked", "today": today, "calculations": list(entries),
            "not_assessed": list(not_assessed)}


def conversation(served, advocate, *records, message="Invented facts of a matter."):
    """A conversation of the advocate's whose answers saved these time-limit records, oldest first; its chat id."""
    context, made = None, next(MADE)
    for number, record in enumerate(records, 1):
        context = open_turn(served.store, advocate_id=advocate, message=f"{message} ({number})", turn_id=f"c{made}-t{number}",
                            chat_id=context.chat_id if context else None)
        commit_turn(served.store, context, elements=[{"text": "An invented answer."}],
                    activities={"calculation": record}, session_current=lambda: True)
    return context.chat_id


@pytest.fixture
def diary(served, monkeypatch):
    monkeypatch.setattr(api, "forum_today", lambda: TODAY)

    def read(client=None):
        reply = (client or served.client).get("/api/time-limits")
        assert reply.status_code == 200, reply.text
        return reply.json()
    return read


def test_each_last_day_with_its_conversation_coming_soonest_first_then_passed_latest_first(served, diary):
    suit = conversation(served, OWNER, worked(entry("Filing the suit", "2027-01-10"), entry("Notice before suit", "2026-11-20"),
                                              entry("Reply to the notice", "2026-11-28", stood="in_time",
                                                    done={"what": "replied", "date": "2026-11-02"})))
    cheque = conversation(served, OWNER, worked(entry("Complaint on the cheque", "2026-12-01"),
                                                entry("Demand notice", "2026-10-15", stood="expired"), today="2026-10-20"))
    said = diary()
    assert said["today"] == "2026-11-25" and "It is not a court diary" in said["said"] and said["state"] == "ok"
    assert [(row["what"], row["chat_id"], row["days_from_today"]) for row in said["coming"]] == [
        ("Reply to the notice", suit, 3), ("Complaint on the cheque", cheque, 6), ("Filing the suit", suit, 46)]
    assert [(row["what"], row["days_from_today"]) for row in said["passed"]] == [
        ("Notice before suit", -5), ("Demand notice", -41)], "the latest passed first"
    reply = said["coming"][0]
    assert reply["stood"] == "in_time" and reply["taken"] is True and reply["worked_on"] == "2026-11-01"
    assert reply["provision"] == "Article 54" and reply["act"] == "The Limitation Act, 1963"
    assert said["coming"][1]["worked_on"] == "2026-10-20" and said["coming"][1]["taken"] is False


def test_the_latest_answer_that_worked_any_out_is_read_and_one_that_could_not_is_said(served, diary):
    later = {"contract": "core_calculation_v9", "state": "not_needed", "why": "", "calculations": [], "not_assessed": []}
    failed = {"contract": "core_calculation_v9", "state": "unavailable", "why": "the time limits could not be worked out",
              "calculations": [], "not_assessed": []}
    kept = conversation(served, OWNER, worked(entry("An earlier limit", "2026-12-24")),
                        worked(entry("The latest limit", "2026-12-10")), later, failed)
    never = conversation(served, OWNER, failed)
    said = diary()
    assert [(row["what"], row["chat_id"]) for row in said["coming"]] == [("The latest limit", kept)]
    assert [(row["chat_id"], row["why"]) for row in said["not_worked"]] == [(never, "the time limits could not be worked out")]


def test_those_not_worked_out_are_said_and_model_words_pass_the_door(served, diary):
    conversation(served, OWNER, worked(
        entry("See https://example.test for the date", "2026-12-05"), {"what": "A damaged record"},
        not_assessed=[{"what": "Appeal against the decree", "why": "The date of the decree is not given."},
                      {"what": "Execution", "why": "I have recalculated it at https://example.test"}]))
    said = diary()
    assert [row["what"] for row in said["coming"]] == ["A time limit"], "words carrying a link are not shown"
    assert [(row["what"], row["why"]) for row in said["not_worked"]] == [
        ("A damaged record", "This time limit's record could not be read."),
        ("Appeal against the decree", "The date of the decree is not given."),
        ("Execution", "NM could not work this time limit out.")]


def test_another_advocate_s_time_limits_are_never_in_the_diary(served, diary):
    conversation(served, OTHER, worked(entry("Another's limit", "2026-12-01")))
    mine = conversation(served, OWNER, worked(entry("My limit", "2026-12-02")))
    assert [(row["what"], row["chat_id"]) for row in diary()["coming"]] == [("My limit", mine)]
    other = served.login(OTHER)
    assert [row["what"] for row in diary(other)["coming"]] == ["Another's limit"]
    assert all(row.get("limits") is None and row.get("find") is None
               for row in served.client.get("/api/work").json()["chats"]), "what the diary reads is not sent with the list"
