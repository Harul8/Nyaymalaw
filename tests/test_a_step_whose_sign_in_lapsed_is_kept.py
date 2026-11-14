"""A step whose advocate's sign-in has lapsed is kept at the next start, not let go (plan AN.52, 52c4; D209; the review's F-12).

At a start, each step an earlier run left was let go of first and its advocate's sign-in checked after: a go-ahead given before
the restart, by an advocate whose sign-in had lapsed meanwhile, was lost - and so was every step, when the sign-ins could not be
read at all at that start. Now a step is let go of only after its sign-in is checked, and a step that could be taken up (a
go-ahead, or one that had begun) is kept where the sign-in has lapsed or could not be checked; the next start checks it again.
A message that never began kept no words and could never be taken up: it is let go, as before.

Offline: the served application with stand-in models; the words are invented.
"""
from __future__ import annotations

import logging

import pytest

from nm.app import api
from nm.arrive.directory_port import AuthenticationUnavailable
from nm.core_engine import steps as stepwise
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, held
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - served is a fixture
from tests.test_steps_are_taken_up_after_a_restart import fingerprint_of
from tests.test_steps_run_as_jobs import outcome

pytestmark = pytest.mark.class_a

LAPSED = "0" * 64


def _waiting(served):
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"


def _left(served):
    return sorted((left["turn_id"], left["route"], left["begun"]) for left in served.app.step_records.left())


def test_a_go_ahead_whose_sign_in_lapsed_is_still_there_after_the_start_and_nothing_runs(served, caplog):
    _waiting(served)
    calls = len(served.model.calls)
    served.app.step_records.taken(OWNER, "turn-1", route="go", chat_id=CHAT, choice="research", disputes=["D1"], session=LAPSED)
    with caplog.at_level(logging.WARNING, logger="nm.steps"):
        assert api.continue_interrupted_steps() == 0
    assert _left(served) == [("turn-1", "go", False)], "kept for when its advocate is back"
    assert len(served.model.calls) == calls and stepwise.waiting_of(held(served)) == "understood"
    assert any("1 step" in record.getMessage() and "kept" in record.getMessage() for record in caplog.records)


def test_a_begun_step_whose_sign_in_lapsed_is_kept_too(served):
    _waiting(served)
    served.app.step_records.taken(OWNER, "turn-1", route="send", chat_id=CHAT, session=LAPSED)
    served.app.step_records.begun(OWNER, "turn-1")
    assert api.continue_interrupted_steps() == 0
    assert _left(served) == [("turn-1", "send", True)]


def test_a_message_that_never_began_is_let_go_whatever_its_sign_in(served):
    _waiting(served)
    served.app.step_records.taken(OWNER, "turn-2", route="send", session=fingerprint_of(served))
    served.app.step_records.taken(OWNER, "turn-3", route="send", session=LAPSED)
    assert api.continue_interrupted_steps() == 0
    assert _left(served) == [], "it kept no words and could never be taken up"


def test_a_step_whose_sign_in_could_not_be_checked_is_kept_and_taken_up_at_a_start_that_can_check_it(served, monkeypatch):
    """The sign-ins could not be read at one start: every step was let go. Now each waits, and the next start takes it up."""
    _waiting(served)
    served.app.step_records.taken(OWNER, "turn-1", route="go", chat_id=CHAT, choice="research", disputes=["D1"],
                                  session=fingerprint_of(served))
    reading = served.app.directory.working_session

    def unreadable(*args, **kwargs):
        raise AuthenticationUnavailable("the sign-in files could not be read")
    monkeypatch.setattr(served.app.directory, "working_session", unreadable)
    assert api.continue_interrupted_steps() == 0
    assert _left(served) == [("turn-1", "go", False)]
    monkeypatch.setattr(served.app.directory, "working_session", reading)
    assert api.continue_interrupted_steps() == 1, "the next start can check it, and takes it up"
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    assert outcome(served).json()["detail"]["code"] == "waiting"
    assert set(held(served)["steps"]["parts"]) == {"D1"}, "given again as given"


def test_a_step_whose_sign_in_holds_is_let_go_only_after_it_is_checked_and_taken_up_as_before(served, monkeypatch):
    _waiting(served)
    served.app.step_records.taken(OWNER, "turn-1", route="go", chat_id=CHAT, choice="research", disputes=["D1"],
                                  session=fingerprint_of(served))
    order = []
    checking = api._still_signed_in
    letting_go = served.app.step_records.ended
    monkeypatch.setattr(api, "_still_signed_in", lambda *args, **kwargs: (order.append("checked"), checking(*args, **kwargs))[1])
    monkeypatch.setattr(served.app.step_records, "ended", lambda *args: (order.append("let go"), letting_go(*args))[1])
    assert api.continue_interrupted_steps() == 1
    assert order[:2] == ["checked", "let go"]
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
