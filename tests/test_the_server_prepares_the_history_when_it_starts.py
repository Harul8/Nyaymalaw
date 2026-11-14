"""The server prepares the conversation history's lines in the background when it starts (plan AN.23; owner decision
O29), so the first opening of the history after a start reads small lines and opens no large file.

The launcher is run with a stand-in application and a stand-in web server: nothing is served and nothing is read.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nm.app import main
from nm.app.activity import Activity
from nm.app.step_jobs import StepJobs

pytestmark = pytest.mark.class_a


class SweptLog:
    """The outgoing-data log's stand-in (plan AN.48, D169): says when, and on which thread, it was swept."""

    def __init__(self, hold=None):
        self.swept, self.hold = threading.Event(), hold

    def sweep(self, today=None):
        self.on = threading.current_thread()
        self.swept.set()
        if self.hold is not None:
            self.hold.wait(10)


def start(monkeypatch, store, prepare, log=None):
    """Run the one-process server's start-up on the store at `store`; returns what the stand-in web server saw when it was
    started."""
    import uvicorn

    # Plan AN.41 (D73): at its start the server also releases the answers an earlier run of it was working on, and (plan AN.48,
    # 48f3) takes up the steps it left; the one process works its steps itself (48f4, steps_mode "inside"). Plan AN.50 (50f): it
    # marks itself alive on its store and holds the steps there first, so the stand-in names a temporary store.
    released = []
    monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(
        health=lambda: {"runtime": "ready"}, legal_search=None, steps_mode="inside", egress_log=log or SweptLog(),
        readiness=lambda: {},  # plan AN.52 (52a6): the start measures readiness; this stand-in has nothing not ready
        activity=Activity(), step_jobs=StepJobs(),  # 52c3: the stop in order once serving ends reads them
        store=SimpleNamespace(sweep_deleted=lambda now: ()),  # plan AN.53 (D241): the serving process sweeps what was deleted
        environment={"NM_MATTER_STORE": str(store)}, root=store,
        turns_of_an_earlier_run_released=lambda: released.append(1) or 0))
    monkeypatch.setattr(main.api, "set_application", lambda application: None)
    monkeypatch.setattr(main.api, "continue_interrupted_steps", lambda application: 0)
    monkeypatch.setattr(main.api, "prepare_history", prepare)
    seen = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.append(kwargs))
    assert main.main(["--no-follow-code", "--port", "8099"]) == 0
    assert released == [1], "the answers of an earlier run released once, as the server starts"
    return seen


def test_the_outgoing_data_log_is_swept_at_start_on_a_thread_of_its_own_and_the_server_does_not_wait_for_it(
        monkeypatch, tmp_path):
    hold = threading.Event()
    log = SweptLog(hold)
    try:
        assert start(monkeypatch, tmp_path, lambda: None, log), "the server was started"
        assert log.swept.wait(10), "the log was not swept as the server started"
        assert log.on.name == "egress-log-sweep" and log.on.daemon and log.on is not threading.main_thread()
        assert not hold.is_set(), "the server was started without waiting for the sweep to end"
    finally:
        hold.set()


def test_the_history_is_prepared_on_a_thread_of_its_own_and_the_server_does_not_wait_for_it(monkeypatch, tmp_path):
    started, release, ran_on = threading.Event(), threading.Event(), []

    def prepare():
        ran_on.append(threading.current_thread())
        started.set()
        release.wait(10)

    seen = start(monkeypatch, tmp_path, prepare)
    try:
        # Plan AN.53 (53c3): the start hands the web server NM's own trust in a proxy's address headers.
        assert seen == [{"host": "127.0.0.1", "port": 8099, "log_level": "warning", "proxy_headers": True,
                         "forwarded_allow_ips": seen[0].get("forwarded_allow_ips")}], "the server was started"
        assert seen[0]["forwarded_allow_ips"], "with the senders it believes named"
        assert started.wait(10), "the history was never prepared"
        assert ran_on[0].name == "history-warm" and ran_on[0].daemon, "a daemon thread of its own"
        assert ran_on[0] is not threading.main_thread()
        assert release.is_set() is False, "the server was started without waiting for the preparation to end"
    finally:
        release.set()


def test_a_preparation_that_fails_does_not_stop_the_server(monkeypatch, tmp_path):
    done = threading.Event()

    def prepare():
        done.set()
        raise RuntimeError("a fault in the preparation")

    monkeypatch.setattr(threading, "excepthook", lambda args: None)   # the thread's own report is not this test's output
    assert start(monkeypatch, tmp_path, prepare)
    assert done.wait(10)


def test_a_check_only_start_prepares_nothing(monkeypatch):
    called, log = [], SweptLog()
    # Plan AN.52 (52a2): the check measures readiness; this stand-in is ready and keeps nothing under the code.
    monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(health=lambda: {"runtime": "ready"}, legal_search=None,
                                                                     steps_mode="inside", egress_log=log,
                                                                     readiness=lambda: {}, kept_in_code_folder=lambda: ()))
    monkeypatch.setattr(main.api, "prepare_history", lambda: called.append(True))
    assert main.main(["--check"]) == 0
    assert called == [] and not log.swept.is_set()
