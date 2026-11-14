"""An orderly stop takes no new steps, waits for the work at hand up to a limit, then lets the process end (plan AN.52, 52c3;
D209; the review's F-12).

The step worker stopped on a signal by ending its loop and leaving: every step at work on its threads - daemon threads - was cut
off part-way, and the one-process server did the same once its web server had stopped. Now a stop closes the step jobs - no
waiting step begins here, and each keeps its record, so the next start takes it up as it takes up any step an earlier run left
- then waits until nothing in the process's ledger (52c1, 52c2) is held or its limit passes, says what it waited for and what
it left, and only then lets the process end.

Offline: real step jobs and ledger; stand-in applications, web server and worker loop; no model call.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from nm.app import main, step_worker
from nm.app.activity import STOP_WAIT, Activity, stop_in_order, stop_wait_from
from nm.app.step_jobs import StepJobs

pytestmark = pytest.mark.class_a


class Records:
    """What a step's record says, as the step jobs keep it (48f3)."""

    def __init__(self):
        self.said = []

    def taken(self, advocate_id, turn_id, **fields):
        self.said.append(("taken", turn_id))

    def begun(self, advocate_id, turn_id):
        self.said.append(("begun", turn_id))

    def ended(self, advocate_id, turn_id):
        self.said.append(("ended", turn_id))


def _jobs(ledger, records=None):
    jobs = StepJobs(wait_seconds=0.05, at_once=1, per_advocate=1)
    jobs.hold = lambda step: ledger.move("step", step)
    jobs.records = records
    return jobs


def until(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


RECORD = {"route": "go", "chat_id": "c1", "session": "fingerprint"}


def test_after_close_no_waiting_step_begins_here_and_the_step_at_work_goes_to_its_end():
    ledger, records, ran = Activity(), Records(), []
    jobs = _jobs(ledger, records)
    go = threading.Event()
    first = jobs.start("a", "t1", lambda: go.wait(5), record=RECORD)
    second = jobs.start("b", "t2", lambda: ran.append("second"), record=RECORD)
    assert ledger.counts() == {"step": 2}
    assert jobs.close() == 1, "one step was waiting"
    assert ledger.counts() == {"step": 1}, "the waiting step will not run here: it is let go of in the ledger"
    go.set()
    assert first.result(5) is True
    assert until(ledger.may_stop)
    time.sleep(0.1)
    assert ran == [] and not second.done(), "the waiting step never began"
    assert ("taken", "t2") in records.said and ("begun", "t2") not in records.said and ("ended", "t2") not in records.said, (
        "its record is kept as taken and not begun, for the next start to take up")
    assert jobs.close() == 0, "a second close changes nothing"


def test_a_step_asked_for_after_close_is_kept_for_the_next_start_and_neither_begun_nor_held():
    ledger, records, ran = Activity(), Records(), []
    jobs = _jobs(ledger, records)
    jobs.close()
    late = jobs.start("a", "t1", lambda: ran.append("late"), record=RECORD)
    time.sleep(0.1)
    assert ran == [] and not late.done() and ledger.may_stop()
    assert records.said == [("taken", "t1")]


def test_a_waiting_step_stopped_by_its_advocate_after_close_is_not_let_go_twice(caplog):
    ledger = Activity()
    jobs = _jobs(ledger)
    go = threading.Event()
    jobs.start("a", "t1", lambda: go.wait(5))
    jobs.start("b", "t2", lambda: None)
    jobs.close()
    assert jobs.cancel("b", "t2")
    assert not any("nothing held" in record.getMessage() for record in caplog.records)
    go.set()
    assert until(ledger.may_stop)


def test_the_stop_returns_as_soon_as_nothing_is_held_and_says_what_it_waited_for():
    ledger, said = Activity(), []
    jobs = _jobs(ledger)
    jobs.start("a", "t1", lambda: time.sleep(0.3))
    began = time.monotonic()
    left = stop_in_order(ledger, jobs.close, limit=10, say=said.append)
    assert left == {} and 0.25 <= time.monotonic() - began < 5
    assert "no new step begins" in said[0] and "1 step" in said[0]
    assert said[-1].startswith("Stopped")


def test_the_stop_waits_no_longer_than_its_limit_and_says_what_it_left():
    ledger, said, now = Activity(), [], [0.0]
    jobs = _jobs(ledger)
    go = threading.Event()
    jobs.start("a", "t1", lambda: go.wait(5))
    with ledger.held("reading"):
        left = stop_in_order(ledger, jobs.close, limit=30, say=said.append, clock=lambda: now[0],
                             pause=lambda seconds: now.__setitem__(0, now[0] + seconds))
    go.set()
    assert left == {"step": 1, "reading": 1}
    assert "STOPPED WITH WORK AT HAND" in said[-1] and "1 step" in said[-1] and "1 reading" in said[-1]
    assert "next start" in said[-1]


def test_nothing_at_work_stops_at_once():
    said = []
    assert stop_in_order(Activity(), lambda: 0, limit=30, say=said.append, pause=lambda s: pytest.fail("no wait")) == {}
    assert "nothing is at work" in said[0]


@pytest.mark.parametrize("setting, seconds", [(None, STOP_WAIT), ("", STOP_WAIT), ("30", 30.0), ("0", 0.0), ("2.5", 2.5),
                                              ("-1", STOP_WAIT), ("3601", STOP_WAIT), ("soon", STOP_WAIT)])
def test_the_limit_is_the_operators_setting_within_an_hour(setting, seconds):
    assert stop_wait_from(setting) == seconds


# ------------------------------------------------------------------------------------- the two processes that stop ---

def test_the_step_worker_lets_its_process_end_only_when_no_step_is_working(monkeypatch):
    """After a stop signal the worker's loop ends; the worker's process then ends only once its step at work has."""
    ledger = Activity()
    jobs = _jobs(ledger)
    app = SimpleNamespace(activity=ledger, step_jobs=jobs, environment={"NM_STOP_WAIT_SECONDS": "10"})
    ended = []
    jobs.start("a", "t1", lambda: (time.sleep(0.3), ended.append(time.monotonic())))
    worker = SimpleNamespace(run=lambda: None)  # its loop, ended by the signal
    began = time.monotonic()
    left = step_worker.work_until_stopped(worker, app, say=lambda line: None)
    assert left == {} and ended and ended[0] - began >= 0.25, "it returned only after the step had ended"


def test_the_one_process_server_stops_in_order_once_its_web_server_has_stopped(monkeypatch, tmp_path, capsys):
    import uvicorn
    ledger = Activity()
    jobs = _jobs(ledger)
    ended = []
    monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(
        health=lambda: {"runtime": "ready"}, readiness=lambda: {}, legal_search=None, steps_mode="inside",
        egress_log=SimpleNamespace(), environment={"NM_MATTER_STORE": str(tmp_path)}, root=tmp_path,
        turns_of_an_earlier_run_released=lambda: 0, activity=ledger, step_jobs=jobs,
        store=SimpleNamespace(sweep_deleted=lambda now, look=None: (), sweep_metrics=lambda before: 0),
        documents=None, directory=SimpleNamespace(sweep_expired=lambda now: {"registrations": 0, "resets": 0}),
            turn_record_sweep=SimpleNamespace(sweep=lambda before: 0)))
    monkeypatch.setattr(main.api, "set_application", lambda application: None)
    monkeypatch.setattr(main.api, "continue_interrupted_steps", lambda application: 0)
    monkeypatch.setattr(main.api, "prepare_history", lambda: None)
    monkeypatch.setattr(main, "keep_egress_log", lambda log: None)
    monkeypatch.setattr(main, "create_app", lambda application=None: None)
    monkeypatch.delenv(main.IN_FLIGHT_FILE, raising=False)
    monkeypatch.setenv("NM_STOP_WAIT_SECONDS", "10")

    def serve_then_stop(app, **kwargs):
        # A step taken while serving, still at work when the web server stops (a stop signal ends uvicorn.run).
        jobs.start("a", "t1", lambda: (time.sleep(0.3), ended.append(time.monotonic())))
    monkeypatch.setattr(uvicorn, "run", serve_then_stop)
    assert main.main(["--no-follow-code", "--port", "8099"]) == 0
    returned = time.monotonic()
    assert ended and ended[0] <= returned, "the process's start returned only after the step had ended"
    said = capsys.readouterr().err
    assert "STOPPING IN ORDER" in said and "Stopped" in said
