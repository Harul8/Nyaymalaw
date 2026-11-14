"""One ledger says whether this process may stop, and how long it has had nothing to do (plan AN.52, 52c1; D209; the review's
F-12).

What a process was doing was known only to the supervisor that restarts the server onto new code, and only while it ran the
server: a count of requests and of steps, written to a file. Nothing else could ask 'may I stop?', and nothing measured 'quiet'
for the hosted server's idle timer (D176). The application now owns one ledger of the work going on in it, by kind and as
counts only. The step jobs register with it in every mode; the supervisor's count is the same ledger's total, so the file it
reads says what it always said. Offline: no model call, no browser.
"""
from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path

import pytest

from nm.app import main
from nm.app.activity import KINDS, Activity
from nm.app.step_jobs import StepJobs

pytestmark = pytest.mark.class_a

REPOSITORY = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_nothing_held_may_stop_and_anything_held_may_not():
    ledger = Activity()
    assert ledger.may_stop() and ledger.total() == 0 and ledger.counts() == {}
    for kind in KINDS:
        with ledger.held(kind):
            assert not ledger.may_stop(), f"'may I stop?' must answer no while {kind} is held"
            assert ledger.counts() == {kind: 1} and ledger.total() == 1
        assert ledger.may_stop()


def test_what_is_held_is_counted_by_kind_and_released_however_the_work_ends():
    ledger = Activity()
    with pytest.raises(RuntimeError):
        with ledger.held("reading"):
            with ledger.held("reading"):
                assert ledger.counts() == {"reading": 2}
            raise RuntimeError("the work failed")
    assert ledger.may_stop(), "a held piece of work is let go however it ends"


def test_an_unknown_kind_or_step_is_a_programming_error():
    ledger = Activity()
    with pytest.raises(ValueError):
        ledger.move("lunch", 1)
    with pytest.raises(ValueError):
        ledger.move("step", 2)


def test_a_release_with_nothing_held_never_takes_the_count_below_nought(caplog):
    """A negative count would read to the supervisor as something in flight for ever."""
    ledger = Activity()
    ledger.move("step", -1)
    assert ledger.total() == 0 and ledger.may_stop()
    assert any("nothing held" in record.getMessage() for record in caplog.records), "said, never silent"


def test_quiet_is_none_while_work_is_held_and_runs_from_when_the_last_work_ended():
    clock = Clock()
    ledger = Activity(clock=clock)
    clock.now += 50
    assert ledger.quiet_for() == 50, "from the ledger's start while nothing has happened"
    with ledger.held("step"):
        clock.now += 300
        assert ledger.quiet_for() is None
    clock.now += 20
    assert ledger.quiet_for() == 20


def test_a_request_is_held_but_is_not_a_sign_of_life():
    """An outside monitor asks /api/health every minute: a request alone must not keep a hosted server awake."""
    clock = Clock()
    ledger = Activity(clock=clock)
    clock.now += 100
    with ledger.held("request"):
        clock.now += 5
        assert not ledger.may_stop(), "a stop waits for a request in flight"
        assert ledger.quiet_for() == 105, "but quiet runs on"


def test_a_signed_in_action_is_a_sign_of_life():
    clock = Clock()
    ledger = Activity(clock=clock)
    clock.now += 100
    ledger.signed_in_action()
    clock.now += 7
    assert ledger.quiet_for() == 7


def test_whoever_is_told_hears_the_total_after_every_change_and_a_failure_to_hear_fails_no_work():
    ledger, heard = Activity(), []
    ledger.tell(heard.append)
    with ledger.held("step"):
        with ledger.held("request"):
            pass
    assert heard == [0, 1, 2, 1, 0]

    def deaf(total):
        raise OSError("the count could not be written")
    ledger.tell(deaf)
    with ledger.held("save"):
        pass
    assert ledger.may_stop()


def test_the_ledger_is_safe_from_many_threads():
    ledger = Activity()

    def work():
        for _ in range(200):
            with ledger.held("reading"):
                pass
    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert ledger.total() == 0


# ----------------------------------------------------------------------- the supervisor's count is the same ledger's ---

def test_the_supervisors_count_is_the_applications_ledger_total(tmp_path):
    async def app(scope, receive, send):
        seen.append(path.read_text())
    seen, path = [], tmp_path / "count"
    ledger = Activity()
    counter = main._InFlight(app, path, activity=ledger)
    assert path.read_text() == "0"
    with ledger.held("reading"):
        assert path.read_text() == "1", "a paper read on a thread of its own is in flight for the supervisor"
        asyncio.run(counter({"type": "http"}, None, None))
    assert seen == ["2"] and path.read_text() == "0"
    counter.hold(1)
    assert ledger.counts() == {"step": 1} and path.read_text() == "1"
    counter.hold(-1)


def test_the_application_owns_one_ledger_and_its_steps_register_with_it_in_every_mode(tmp_path):
    from nm.app.composition import Application
    from tests.test_core_turn import ScriptedModel
    code = tmp_path / "code"
    for name in ("docs/blueprint/evaluations.json", "docs/blueprint/processors.yaml", "pipeline/instrument_copies.json"):
        (code / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPOSITORY / name, code / name)
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=code, model=model, legal_search=None, environment={
        "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
        "NM_MATTER_KEY": "a-ledger-control-secret-" + "k" * 24, "NM_MATTER_STORE": str(tmp_path / "data"),
        "NM_EGRESS_LOG_DIR": str(tmp_path / "logs")})
    assert isinstance(app.activity, Activity) and app.activity.may_stop()
    let_go = threading.Event()
    step = app.step_jobs.start("advocate@example.test", "turn-1", lambda: let_go.wait(5))
    assert not app.activity.may_stop() and app.activity.counts() == {"step": 1}, "a step is held without any supervisor"
    let_go.set()
    step.result(5)
    for _ in range(100):
        if app.activity.may_stop():
            break
        threading.Event().wait(0.02)
    assert app.activity.may_stop()


def test_a_step_waiting_and_a_step_working_are_each_held():
    ledger = Activity()
    jobs = StepJobs(wait_seconds=0.05, at_once=1, per_advocate=1)
    jobs.hold = lambda step: ledger.move("step", step)
    first_go, second_go = threading.Event(), threading.Event()
    first = jobs.start("a", "t1", lambda: first_go.wait(5))
    second = jobs.start("b", "t2", lambda: second_go.wait(5))
    assert ledger.counts() == {"step": 2}, "one working, one waiting: each is held"
    first_go.set()
    second_go.set()
    first.result(5)
    second.result(5)
    for _ in range(100):
        if ledger.may_stop():
            break
        threading.Event().wait(0.02)
    assert ledger.may_stop()
