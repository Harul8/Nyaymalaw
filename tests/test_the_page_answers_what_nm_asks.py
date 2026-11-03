"""What a turn asks reaches its advocate's page and their answer reaches the turn (plan AN.37, D37-D40, D44), through the
served application: the progress says a window is open (never what it asks), the advocate reads its questions and answers them,
and the saved answer carries what was asked. Scripted model; the window itself is checked in the browser."""
from __future__ import annotations

import threading
import time

import pytest

from tests.test_core_served import OTHER, served  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a

QUESTION = {"header": "Your client", "question": "Whom do you act for?",
            "why": "It decides which party is adverse to your client.",
            "choices": [{"label": "The buyer", "description": ""}, {"label": "The seller", "description": ""}],
            "multiple": False, "default": ["The buyer"], "depends": []}


def asks(served, *items):
    served.app.propose_questions = lambda calls, context, interpreted, plan, asked_before: [dict(i) for i in items]


def sending(served, turn_id="turn-1"):
    result = {}

    def post():
        result["response"] = served.client.post("/api/turn", json={"message": "Inspect this reported account.",
                                                                   "turn_id": turn_id})
    thread = threading.Thread(target=post)
    thread.start()
    return thread, result


def until(check, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        seen = check()
        if seen:
            return seen
        time.sleep(0.05)
    raise AssertionError("not seen in time")


def test_the_advocate_reads_the_question_answers_it_and_the_saved_answer_carries_it(served):
    asks(served, QUESTION)
    page = served.login()
    thread, result = sending(served)
    progress = until(lambda: (lambda seen: seen if seen.get("asking") else None)(
        page.get("/api/turn-progress?turn_id=turn-1").json()))
    assert progress["stage"] == "waiting_for_answer" and "Whom" not in str(progress)  # the progress never says what it asks
    window = page.get("/api/turn-question?turn_id=turn-1").json()
    assert [q["question"] for q in window["questions"]] == ["Whom do you act for?"] and not window["defaults_applied"]
    refused = page.post("/api/turn-question", json={"turn_id": "turn-1", "answers": {"q1": {"chosen": ["Someone"]}}})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "answer_refused"
    taken = page.post("/api/turn-question", json={"turn_id": "turn-1", "answers": {"q1": {"chosen": ["The seller"]}}})
    assert taken.status_code == 200 and taken.json() == {"state": "taken"}
    thread.join(60)
    reply = result["response"]
    assert reply.status_code == 200, reply.text
    asked = reply.json()["questions_asked"]
    assert [(a["chosen"], a["how"]) for a in asked["answers"]] == [(["The seller"], "answered")]
    # Reopened, the turn carries it as saved; the window has closed with the turn, and an answer now goes as the next message.
    turn = served.client.get(f"/api/chats/{reply.json()['chat_id']}").json()["turns"][0]
    assert turn["questions_asked"] == asked
    assert page.get("/api/turn-question?turn_id=turn-1").status_code == 404
    late = page.post("/api/turn-question", json={"turn_id": "turn-1", "answers": {"q1": {"chosen": ["The buyer"]}}})
    assert late.status_code == 409 and late.json()["detail"]["code"] == "window_closed"
    assert "asking" not in page.get("/api/turn-progress?turn_id=turn-1").json()


def test_another_advocate_can_neither_read_nor_answer_the_window(served, monkeypatch):
    from nm.core_engine import questions
    monkeypatch.setattr(questions, "WAIT", 1.0)
    asks(served, QUESTION)
    thread, result = sending(served)
    until(lambda: served.app.questions.window("core-owner@example.test", "turn-1"))
    other = served.login(OTHER)
    assert other.get("/api/turn-question?turn_id=turn-1").status_code == 404
    assert other.post("/api/turn-question", json={"turn_id": "turn-1", "answers": {"q1": {"chosen": ["The seller"]}}}
                      ).status_code == 409
    assert "asking" not in other.get("/api/turn-progress?turn_id=turn-1").json()
    thread.join(60)
    # Unanswered, the default stood and the turn was answered with it.
    asked = result["response"].json()["questions_asked"]
    assert [(a["chosen"], a["how"]) for a in asked["answers"]] == [(["The buyer"], "assumed")]


def test_a_turn_with_nothing_to_ask_opens_no_window(served):
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert reply.status_code == 200 and reply.json()["questions_asked"] is None
    assert "asking" not in served.client.get("/api/turn-progress?turn_id=turn-1").json()
