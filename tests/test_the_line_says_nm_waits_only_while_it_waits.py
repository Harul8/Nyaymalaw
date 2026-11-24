"""The line on the page says NM waits for the advocate only while it does (plan AN.80, D350; owner, 24 Nov 2026: "Yes, trace it",
then "Build and apply").

End-to-end run 4 found the line saying 'Waiting for your answer' for eight minutes after the advocate had answered, while NM researched
and wrote. The page's progress put those words in place of the turn's own whenever the turn's window of questions was open - and the
window stays open for a later or changed answer (D44) ten minutes after the last question, until the turn ends. Now the words stand
only while a question has neither an answer nor its default; the page is still told the window is open and how many it asks (D87), in
one process and with the step worker alike. Real windows, desks and progress; no model. The question is invented.
"""
from types import SimpleNamespace

import pytest

from nm.app import api
from nm.app.composition import QuestionDesk
from nm.app.step_worker import _Window
from nm.app.turn_progress import STAGES, TurnProgress
from nm.core_engine import questions

pytestmark = pytest.mark.class_a

QUESTION = {"header": "Your client", "question": "Whom do you act for?", "why": "It decides which party is adverse to your client.",
            "choices": [{"label": "The buyer", "description": ""}, {"label": "The seller", "description": ""}],
            "multiple": False, "default": ["The buyer"], "depends": []}
SECOND = {**QUESTION, "header": "The date", "question": "When was the notice sent?"}


class Shared:
    """The web server's desk with the step worker (48f4): it reads the window's view as the worker shows it."""

    def __init__(self, desk):
        self.desk = desk

    def window(self, advocate_id, turn_id):
        asking = self.desk.window(advocate_id, turn_id)
        return None if asking is None else _Window(asking.view())


@pytest.fixture(params=["one process", "step worker"])
def served(request, monkeypatch):
    progress, desk = TurnProgress(), QuestionDesk()
    monkeypatch.setattr(api, "_application", SimpleNamespace(
        turn_progress=progress, questions=desk if request.param == "one process" else Shared(desk)))
    return progress, desk


def opened(desk, progress, turn_id, *items, wait=None):
    asking = questions.Asking([], hold=lambda state: None, report=lambda stage, **detail: progress.report("a", turn_id, stage, detail),
                              **({"wait": wait} if wait is not None else {}))
    ids = asking.add([dict(item) for item in items])
    desk.bound("a").open(turn_id, asking)
    return asking, ids


def test_the_line_says_nm_waits_until_each_question_is_answered_then_what_the_turn_does(served):
    progress, desk = served
    progress.report("a", "t1", "choosing_provisions")
    asking, (first, second) = opened(desk, progress, "t1", QUESTION, SECOND)
    seen = api._progress_seen("a", "t1", None)
    assert (seen["stage"], seen["label"], seen["asking"], seen["asked"]) == (
        "waiting_for_answer", STAGES["waiting_for_answer"], True, 2)
    assert asking.receive({first: {"chosen": ["The seller"]}}) == "taken"
    progress.report("a", "t1", "writing", {"part": "s1"})
    assert api._progress_seen("a", "t1", None)["stage"] == "waiting_for_answer", "one question still waits"
    assert asking.receive({second: {"chosen": ["The buyer"]}}) == "taken"
    seen = api._progress_seen("a", "t1", None)
    assert (seen["stage"], seen["label"]) == ("writing", STAGES["writing"]), "answered: the turn's own stage"
    assert seen["asking"] is True and seen["asked"] == 2, "the window is still open for a changed answer (D44, D87)"


def test_once_the_defaults_stand_the_line_says_what_the_turn_does(served):
    progress, desk = served
    asking, _ = opened(desk, progress, "t2", QUESTION, wait=0)
    assert api._progress_seen("a", "t2", None)["stage"] == "waiting_for_answer"
    asking.wait()
    progress.report("a", "t2", "reviewing", {"part": "s1"})
    seen = api._progress_seen("a", "t2", None)
    assert (seen["stage"], seen["asking"]) == ("reviewing", True)


def test_a_question_added_while_the_turn_works_makes_the_line_wait_again(served):
    """D87: code may add a question to the window after the first are answered; NM then waits for it."""
    progress, desk = served
    asking, (first,) = opened(desk, progress, "t3", QUESTION)
    asking.receive({first: {"chosen": ["The seller"]}})
    progress.report("a", "t3", "writing", {"part": "s1"})
    assert api._progress_seen("a", "t3", None)["stage"] == "writing"
    asking.add([dict(SECOND)])
    seen = api._progress_seen("a", "t3", None)
    assert (seen["stage"], seen["asked"]) == ("waiting_for_answer", 2)


def test_without_a_window_the_line_is_the_turns_own(served):
    progress, desk = served
    progress.report("a", "t4", "searching", {"done": 0, "total": 1})
    seen = api._progress_seen("a", "t4", None)
    assert seen["stage"] == "searching" and "asking" not in seen
