"""The server's start measures readiness and refuses where NM is not ready (plan AN.52, 52a6; D237; D207; the review's F-11).

The check command failed on what was not ready (52a2); the server's own start did not ask. It started without its library,
its store or its record of what it sends, took an advocate's message and failed it part-way. The start now measures
readiness before it takes a request and refuses - naming each capability that is not ready, with why - holding nothing and
starting no web server. 'Not checked' never refuses. One switch is the operator's, for development: NM_START_UNREADY=serve
starts at once, says so, measures in the background and prints what is not ready when it is known.

Offline: the start run with a stand-in application and a stand-in web server; no model call.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nm.app import main
from nm.app.composition import NOT_CHECKED, NOT_READY, READY

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
            turns_of_an_earlier_run_released=lambda: took.append("earlier turns") or 0))
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


def test_a_start_with_everything_ready_serves(start, capsys):
    code, served, took = start(READY_ALL)
    assert code == 0 and len(served) == 1 and "the store" in took
    assert "REFUSED TO START" not in capsys.readouterr().err


def test_a_start_where_a_capability_is_not_ready_refuses_names_each_and_takes_nothing(start, capsys):
    code, served, took = start(LIBRARY_MISSING)
    assert code == 2 and served == [] and took == [], "no web server, no claim on the store, nothing of an earlier run taken up"
    said = capsys.readouterr().err
    assert "REFUSED TO START: the held law: provision is not ready: The provision index could not be loaded" in said
    assert "REFUSED TO START: the malware scanner is not ready: no malware checker is set up on this installation" in said
    assert "the store is not ready" not in said and "account mail is not ready" not in said
    assert "NM_START_UNREADY=serve" in said, "the operator is told the one way to start anyway"


def test_what_is_only_not_checked_does_not_refuse_the_start(start):
    measured = {"the store": {"state": READY, "why": ""}, "account mail": {"state": NOT_CHECKED, "why": "no check is built"}}
    code, served, _took = start(measured)
    assert code == 0 and len(served) == 1


def test_readiness_is_measured_before_the_web_server_starts(start):
    order = []
    code, served, _took = start(READY_ALL, measuring=lambda: order.append("measured"))
    assert code == 0 and order == ["measured"] and len(served) == 1


@pytest.mark.parametrize("setting", ["serve", " SERVE "])
def test_the_operators_switch_starts_at_once_says_so_and_measures_in_the_background(start, capsys, setting):
    measured_on = []
    done = threading.Event()

    def measuring():
        measured_on.append(threading.current_thread())
        done.set()
    code, served, _took = start(LIBRARY_MISSING, setting=setting, measuring=measuring)
    assert code == 0 and len(served) == 1, "it serves although the library is not ready"
    assert done.wait(10), "readiness was never measured"
    assert measured_on[0] is not threading.main_thread() and measured_on[0].daemon, "on a thread of its own"
    measured_on[0].join(10)
    said = capsys.readouterr().err
    assert "NM_START_UNREADY=serve" in said and "WITHOUT" in said, "said at every start that uses it"
    assert "NOT READY: the held law: provision: The provision index could not be loaded" in said
    assert "REFUSED TO START" not in said


def test_any_other_value_of_the_switch_is_not_the_switch(start):
    code, served, _took = start(LIBRARY_MISSING, setting="yes")
    assert code == 2 and served == []


def test_a_search_that_readiness_could_not_check_is_still_warmed_and_one_it_measured_is_not_warmed_twice(start):
    warmed = threading.Event()
    unchecked = {"the store": {"state": READY, "why": ""},
                 "the held law: provision": {"state": NOT_CHECKED, "why": "this search offers no check of its own"},
                 "the held law: judgment": {"state": NOT_CHECKED, "why": "this search offers no check of its own"}}
    code, _served, _took = start(unchecked, warm=warmed.set)
    assert code == 0 and warmed.wait(10), "a search with no check of its own is warmed in the background, as before"
    again = []
    both = {"the store": {"state": READY, "why": ""}, "the held law: provision": {"state": READY, "why": ""},
            "the held law: judgment": {"state": READY, "why": ""}}
    code, _served, _took = start(both, warm=lambda: again.append(1))
    assert code == 0 and again == [], "measuring already opened it: it is not loaded a second time"
