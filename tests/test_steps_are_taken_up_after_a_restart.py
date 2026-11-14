"""Continued by itself after a restart (plan AN.48, piece 48f3; owner decision D167): a content-free record of each step the server
takes - never its words - says at the next start what can be taken up again. A step that had begun, whose turn its conversation holds
as stopped by the restart, is continued by the server itself, as Continue does (D70, D73), without waiting for the advocate's page; a
go-ahead that had not begun is given again as given; a message not yet begun was never kept and is said as before; and nothing is
taken up once the advocate's sign-in no longer holds - checked by its fingerprint, never its token. Offline: scripted models; the
words are invented."""
import threading
from datetime import datetime, timedelta, timezone

import pytest

from nm.app import api
from nm.app.step_jobs import StepJobs
from nm.arrive.advocate_contracts import token_fingerprint
from nm.core_engine import steps as stepwise
from nm.shared.step_record_store import FileStepRecords
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, held

from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - pytest fixture
from tests.test_steps_run_as_jobs import Held, outcome


class ServerStopped(BaseException):
    """Stands in for the server stopping while a step works: no handler of the turn hears it, as none hears a process ending."""


def fingerprint_of(served):
    return token_fingerprint(served.client.cookies.get("nm_session"))


def test_the_records_hold_no_words_go_with_their_steps_and_never_fail_one(tmp_path):
    records = FileStepRecords(tmp_path / "step-records.sqlite")
    records.taken("a@example.test", "t1", route="go", chat_id="c1", choice="research", disputes=["D1", "D2"], session="f" * 64)
    records.taken("a@example.test", "t2", route="send")
    records.begun("a@example.test", "t1")
    left = records.left()
    # When each was taken (plan AN.53, D241: kept 90 days from then; 14 Nov 2026), a time with its zone and no words.
    assert all(datetime.fromisoformat(each.pop("taken_at")).utcoffset() is not None for each in left)
    assert left == [
        {"advocate_id": "a@example.test", "turn_id": "t1", "chat_id": "c1", "route": "go", "choice": "research",
         "disputes": ["D1", "D2"], "session": "f" * 64, "begun": True},
        {"advocate_id": "a@example.test", "turn_id": "t2", "chat_id": None, "route": "send", "choice": None, "disputes": None,
         "session": None, "begun": False}]
    records.ended("a@example.test", "t2")
    assert [left["turn_id"] for left in records.left()] == ["t1"]
    for wrong in ({"route": "write"}, {"route": "go", "choice": "anything"}, {"route": "go", "disputes": ["D1 and words"]},
                  {"route": "send", "session": "a token, not a fingerprint"}):
        with pytest.raises(ValueError):
            records.taken("a@example.test", "t3", **wrong)
    # A store that cannot be written loses that record and nothing else.
    (tmp_path / "step-records.sqlite").unlink()
    records.taken("a@example.test", "t4", route="send")
    records.ended("a@example.test", "t4")
    assert records.left() == []


def test_the_step_threads_keep_a_record_for_each_step_they_answer_for_and_let_it_go_when_it_ends(tmp_path):
    records = FileStepRecords(tmp_path / "step-records.sqlite")
    jobs = StepJobs(wait_seconds=0.05, at_once=1, per_advocate=1)
    jobs.records = records
    let_go = threading.Event()
    first = jobs.start("a", "t1", lambda: let_go.wait(5), record={"route": "send", "chat_id": "c1"})
    waiting = jobs.start("b", "t2", lambda: "never", record={"route": "go", "choice": "next"})
    jobs.start("a", "t1", lambda: "a second request's", record={"route": "continue"})  # leaves t1's record as it is
    assert [(left["turn_id"], left["route"], left["begun"]) for left in records.left()] == [("t1", "send", True),
                                                                                         ("t2", "go", False)]
    assert jobs.cancel("b", "t2") and [left["turn_id"] for left in records.left()] == ["t1"]
    let_go.set()
    first.result(5)
    for _ in range(100):
        if not records.left():
            break
        threading.Event().wait(0.02)
    assert records.left() == []
    assert waiting.exception(1) is not None


def test_a_sign_in_is_found_by_its_fingerprint_only_while_it_holds_and_only_for_its_advocate(served):
    fingerprint, now = fingerprint_of(served), datetime.now(timezone.utc)
    assert served.directory.working_session(OWNER, fingerprint, now).advocate_id == OWNER
    assert served.directory.working_session(OTHER, fingerprint, now) is None, "another advocate's sign-in is none of theirs"
    assert served.directory.working_session(OWNER, "0" * 64, now) is None
    assert served.directory.working_session(OWNER, "../" + fingerprint[3:], now) is None
    assert served.directory.keep_working_session(OWNER, fingerprint, now) is not None
    assert served.directory.working_session(OWNER, fingerprint, now + timedelta(days=2)) is None, "an expired one does not hold"


def test_a_step_a_restart_interrupted_is_continued_by_the_server_itself(served):
    scripted_answers(served, Scripted())
    stopping = Held(served, fail=ServerStopped())
    served.app.step_jobs.wait_seconds = 0.2
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert stopping.entered.wait(10)
    stopping.go.set()
    assert isinstance(served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30), ServerStopped)
    for _ in range(250):  # the step's own ending lets its record go, which a stopped server never does
        if not served.app.step_records.left():
            break
        threading.Event().wait(0.02)
    # What the stopped server left: the step's record as it was while it worked, the turn kept with its conversation.
    served.app.step_records.taken(OWNER, "turn-1", route="send", session=fingerprint_of(served))
    served.app.step_records.begun(OWNER, "turn-1")
    stopping.fail = None
    # The next start: the claims of the earlier run released (D73), then its steps taken up.
    served.app.turns_of_an_earlier_run_released()
    assert api.continue_interrupted_steps() == 1
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    later = outcome(served)
    assert later.status_code == 409 and later.json()["detail"]["code"] == "waiting", "the step finished as Continue finishes it"
    assert stepwise.waiting_of(held(served)) == "understood"
    assert served.app.step_records.left() == []


def test_a_go_ahead_not_yet_begun_is_given_again_as_given(served):
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    served.app.step_records.taken(OWNER, "turn-1", route="go", chat_id=CHAT, choice="research", disputes=["D1"],
                                  session=fingerprint_of(served))
    assert api.continue_interrupted_steps() == 1
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    assert outcome(served).json()["detail"]["code"] == "waiting"
    assert set(held(served)["steps"]["parts"]) == {"D1"}, "only the dispute it named was researched"


def test_nothing_is_taken_up_without_its_words_or_once_the_sign_in_no_longer_holds(served):
    """CHANGED BY PLAN AN.52 (52c4, D209), 14 Nov 2026. This test held that a go-ahead whose sign-in no longer holds is let go at
    the start, with nothing taken up. D209: a recorded step is let go only after its sign-in is checked, and is kept where the
    sign-in has lapsed - so the go-ahead is still there after the start (tests/test_a_step_whose_sign_in_lapsed_is_kept.py).
    Nothing is taken up, as before, and a message that never began is still let go."""
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    calls = len(served.model.calls)
    served.app.step_records.taken(OWNER, "turn-2", route="send", session=fingerprint_of(served))  # a message never begun
    served.app.step_records.taken(OWNER, "turn-1", route="go", chat_id=CHAT, choice="research", session="0" * 64)
    assert api.continue_interrupted_steps() == 0
    assert [left["turn_id"] for left in served.app.step_records.left()] == ["turn-1"] and len(served.model.calls) == calls
    assert stepwise.waiting_of(held(served)) == "understood", "the matter waits for its advocate, as it did"
