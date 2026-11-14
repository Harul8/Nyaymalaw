"""The server's start says what is not ready and goes on (plan AN.52, 52a7; D242, the owner's correction of D237; D207).

52a6 built D237: the start measured readiness before it took a request and refused where NM was not ready, with one switch to
start anyway. The owner, asked which the start should do, answered "print and go on" (D242). So the start now serves at once,
measures readiness on a thread of its own and prints a line for each capability that is not ready, with why. What 52a6 built
is kept as the operator's choice: NM_START_UNREADY=refuse measures first and refuses, holding nothing and starting no web
server. 'Not checked' never refuses. A value of the setting that is neither 'refuse' nor 'serve' refuses the start and says
so: a mistyped 'refuse' must not quietly serve.

CHANGED FROM 52a6, and said: the tests that held that a start with a capability not ready refuses now hold that it serves
and says so; the refusal is tested under the setting that asks for it.

Offline: the start run with a stand-in application and a stand-in web server; no model call.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nm.app import main
from nm.app.activity import Activity
from nm.app.composition import NOT_CHECKED, NOT_READY, READY
from nm.app.step_jobs import StepJobs

pytestmark = pytest.mark.class_a

READY_ALL = {"the store": {"state": READY, "why": ""}, "the held law: provision": {"state": READY, "why": ""}}
LIBRARY_MISSING = {"the store": {"state": READY, "why": ""},
                   "the held law: provision": {"state": NOT_READY, "why": "The provision index could not be loaded"},
                   "the malware scanner": {"state": NOT_READY, "why": "no malware checker is set up on this installation"},
                   "account mail": {"state": NOT_CHECKED, "why": "no check of account mail is built yet"}}


class _Log:
    def sweep(self, now=None):
        return 0


@pytest.fixture
def start(monkeypatch, tmp_path):
    """Run the one-process server's start with readiness as given: (exit code, what the stand-in web server was started
    with, what the start took)."""
    import uvicorn

    def run(measured, *, setting=None, measuring=None, warm=None):
        took, served = [], []
        search = None if warm is None else SimpleNamespace(warm=warm)

        def readiness(measure=True):
            if measuring is not None:
                measuring()
            return measured
        monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(
            health=lambda: {"runtime": "ready"}, readiness=readiness, legal_search=search, steps_mode="inside",
            egress_log=_Log(), environment={"NM_MATTER_STORE": str(tmp_path)}, root=tmp_path,
            turns_of_an_earlier_run_released=lambda: took.append("earlier turns") or 0,
            activity=Activity(), step_jobs=StepJobs(),  # plan AN.52 (52c3): the stop in order once serving ends reads them
            store=SimpleNamespace(sweep_deleted=lambda now, look=None: ()), documents=None,
            directory=SimpleNamespace(sweep_expired=lambda now: {"registrations": 0, "resets": 0}),
            turn_record_sweep=SimpleNamespace(sweep=lambda before: 0)))  # plan AN.53 (D241): the serving process sweeps
        monkeypatch.setattr(main.api, "set_application", lambda application: None)
        monkeypatch.setattr(main.api, "continue_interrupted_steps", lambda application: 0)
        monkeypatch.setattr(main.api, "prepare_history", lambda: None)
        real_take = main.step_worker.take_the_store
        monkeypatch.setattr(main.step_worker, "take_the_store",
                            lambda *args, **kwargs: (took.append("the store"), real_take(*args, **kwargs))[1])
        monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: served.append(kwargs))
        if setting is None:
            monkeypatch.delenv("NM_START_UNREADY", raising=False)
        else:
            monkeypatch.setenv("NM_START_UNREADY", setting)
        return main.main(["--no-follow-code", "--port", "8099"]), served, took
    return run


# ------------------------------------------------------------- the rule: say it and go on (D242) ---

@pytest.mark.parametrize("setting", [None, "serve", " SERVE "])
def test_a_start_where_a_capability_is_not_ready_serves_and_says_each_with_why(start, capsys, setting):
    measured_on = []
    done = threading.Event()

    def measuring():
        measured_on.append(threading.current_thread())
        done.set()
    code, served, took = start(LIBRARY_MISSING, setting=setting, measuring=measuring)
    assert code == 0 and len(served) == 1 and "the store" in took, "it serves although the library is not ready"
    assert done.wait(10), "readiness was never measured"
    assert measured_on[0] is not threading.main_thread() and measured_on[0].daemon, "on a thread of its own: the start does not wait"
    measured_on[0].join(10)
    said = capsys.readouterr().err
    assert "NOT READY: the held law: provision: The provision index could not be loaded" in said
    assert "NOT READY: the malware scanner: no malware checker is set up on this installation" in said
    assert "NOT READY: the store" not in said and "NOT READY: account mail" not in said, "what is ready or only not checked is not named"
    assert "REFUSED TO START" not in said
    assert "NM_START_UNREADY=refuse" in said, "the operator is told how to have the start refuse instead"


def test_a_start_with_everything_ready_serves_and_says_nothing_is_wrong(start, capsys):
    done = threading.Event()
    code, served, took = start(READY_ALL, measuring=done.set)
    assert code == 0 and len(served) == 1 and "the store" in took
    assert done.wait(10)
    for thread in threading.enumerate():
        if thread.name == "readiness":
            thread.join(10)
    said = capsys.readouterr().err
    assert "NOT READY" not in said and "REFUSED TO START" not in said and "NM_START_UNREADY" not in said


# ------------------------------------------------------------- the operator's choice: refuse (what 52a6 built) ---

@pytest.mark.parametrize("setting", ["refuse", " REFUSE "])
def test_where_the_operator_asks_a_start_that_is_not_ready_refuses_names_each_and_takes_nothing(start, capsys, setting):
    code, served, took = start(LIBRARY_MISSING, setting=setting)
    assert code == 2 and served == [] and took == [], "no web server, no claim on the store, nothing of an earlier run taken up"
    said = capsys.readouterr().err
    assert "REFUSED TO START: the held law: provision is not ready: The provision index could not be loaded" in said
    assert "REFUSED TO START: the malware scanner is not ready: no malware checker is set up on this installation" in said
    assert "the store is not ready" not in said and "account mail is not ready" not in said


def test_asked_to_refuse_a_start_with_everything_ready_serves_having_measured_first(start, capsys):
    order = []
    code, served, _took = start(READY_ALL, setting="refuse", measuring=lambda: order.append("measured"))
    assert code == 0 and order == ["measured"] and len(served) == 1
    assert "REFUSED TO START" not in capsys.readouterr().err


def test_asked_to_refuse_what_is_only_not_checked_does_not_refuse_the_start(start):
    measured = {"the store": {"state": READY, "why": ""}, "account mail": {"state": NOT_CHECKED, "why": "no check is built"}}
    code, served, _took = start(measured, setting="refuse")
    assert code == 0 and len(served) == 1


@pytest.mark.parametrize("setting", ["yes", "refused", "1"])
def test_a_value_that_is_neither_refuses_the_start_and_says_which_two_there_are(start, capsys, setting):
    """A mistyped 'refuse' must not quietly serve; a start that was never measured must not be taken for one that was."""
    code, served, took = start(READY_ALL, setting=setting)
    assert code == 2 and served == [] and took == []
    said = capsys.readouterr().err
    assert "NM_START_UNREADY" in said and "refuse" in said and "serve" in said


def test_a_search_that_readiness_could_not_check_is_still_warmed_and_one_it_measured_is_not_warmed_twice(start):
    warmed = threading.Event()
    unchecked = {"the store": {"state": READY, "why": ""},
                 "the held law: provision": {"state": NOT_CHECKED, "why": "this search offers no check of its own"},
                 "the held law: judgment": {"state": NOT_CHECKED, "why": "this search offers no check of its own"}}
    for setting in (None, "refuse"):
        warmed.clear()
        code, _served, _took = start(unchecked, warm=warmed.set, setting=setting)
        assert code == 0 and warmed.wait(10), "a search with no check of its own is warmed in the background, as before"
    again = []
    both = {"the store": {"state": READY, "why": ""}, "the held law: provision": {"state": READY, "why": ""},
            "the held law: judgment": {"state": READY, "why": ""}}
    for setting in (None, "refuse"):
        measured = threading.Event()
        code, _served, _took = start(both, warm=lambda: again.append(1), setting=setting, measuring=measured.set)
        assert code == 0 and measured.wait(10)
        for thread in threading.enumerate():
            if thread.name in ("readiness", "search-warm"):
                thread.join(10)
    assert again == [], "measuring already opened it: it is not loaded a second time"
