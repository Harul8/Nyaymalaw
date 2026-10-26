"""The server prepares the conversation history's lines in the background when it starts (plan AN.23; owner decision
O29), so the first opening of the history after a start reads small lines and opens no large file.

The launcher is run with a stand-in application and a stand-in web server: nothing is served and nothing is read.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nm.app import main

pytestmark = pytest.mark.class_a


def start(monkeypatch, prepare):
    """Run the one-process server's start-up; returns what the stand-in web server saw when it was started."""
    import uvicorn

    monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(health=lambda: {"runtime": "ready"}, legal_search=None))
    monkeypatch.setattr(main.api, "set_application", lambda application: None)
    monkeypatch.setattr(main.api, "prepare_history", prepare)
    seen = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.append(kwargs))
    assert main.main(["--no-follow-code", "--port", "8099"]) == 0
    return seen


def test_the_history_is_prepared_on_a_thread_of_its_own_and_the_server_does_not_wait_for_it(monkeypatch):
    started, release, ran_on = threading.Event(), threading.Event(), []

    def prepare():
        ran_on.append(threading.current_thread())
        started.set()
        release.wait(10)

    seen = start(monkeypatch, prepare)
    try:
        assert seen == [{"host": "127.0.0.1", "port": 8099, "log_level": "warning"}], "the server was started"
        assert started.wait(10), "the history was never prepared"
        assert ran_on[0].name == "history-warm" and ran_on[0].daemon, "a daemon thread of its own"
        assert ran_on[0] is not threading.main_thread()
        assert release.is_set() is False, "the server was started without waiting for the preparation to end"
    finally:
        release.set()


def test_a_preparation_that_fails_does_not_stop_the_server(monkeypatch):
    done = threading.Event()

    def prepare():
        done.set()
        raise RuntimeError("a fault in the preparation")

    monkeypatch.setattr(threading, "excepthook", lambda args: None)   # the thread's own report is not this test's output
    assert start(monkeypatch, prepare)
    assert done.wait(10)


def test_a_check_only_start_prepares_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(main, "Application", lambda: SimpleNamespace(health=lambda: {"runtime": "ready"}, legal_search=None))
    monkeypatch.setattr(main.api, "prepare_history", lambda: called.append(True))
    assert main.main(["--check"]) == 0
    assert called == []
