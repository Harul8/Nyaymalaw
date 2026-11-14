"""One process works the steps of a store at a time (plan AN.50, piece 50f; D192; the review's F-17).

A second step worker started on a store already being worked ran its start-up recovery: it released the claims of the turns an
earlier run was working on - which were the first worker's, still at work - and took up their steps again, so one message could
be worked twice. The process that works the steps now holds one operating-system lock on the store for its life, taken before its
start-up recovery; a second refuses to start and takes up nothing. Each process also marks itself alive on the store, which the key
rotation refuses to work beside, and refuses to start while a rotation has the store (D190). The server that works its own steps
does the same (50f2); one whose steps the worker works leaves the steps to it and still marks itself alive. Offline: the
application, its loop and its serving are stood in for; the store is a temporary folder.
"""
from __future__ import annotations

import signal
from types import SimpleNamespace

import pytest

from nm.app import api, composition, step_worker
from nm.app.activity import Activity
from nm.app.step_jobs import StepJobs
from nm.shared import egress_log_store
from nm.shared.store_file_store import REKEYING, alive_on, claim

pytestmark = pytest.mark.class_a


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """The step worker's start, with its application and loop stood in for: how many times its start-up recovery ran, and what
    it held while it worked."""
    store = tmp_path / "store"
    store.mkdir()
    seen = {"started": 0, "held": None}
    monkeypatch.setattr(composition, "Application", lambda **_: SimpleNamespace(
        environment={"NM_MATTER_STORE": str(store)}, root=tmp_path, step_share=None, egress_log=None, legal_search=None,
        activity=Activity(), step_jobs=StepJobs()))  # plan AN.52 (52c3): the worker's stop in order reads them
    monkeypatch.setattr(api, "set_application", lambda app: None)
    monkeypatch.setattr(egress_log_store, "keep", lambda log: None)
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    monkeypatch.setattr(step_worker.StepWorker, "start", lambda self: seen.update(started=seen["started"] + 1))

    def run(self):
        seen["held"] = (claim(store / step_worker.STEPS_LOCK) is None, alive_on(store))
    monkeypatch.setattr(step_worker.StepWorker, "run", run)
    return store, seen


def test_a_second_worker_on_the_same_store_refuses_to_start_and_releases_no_claim(worker):
    store, seen = worker
    first = claim(store / step_worker.STEPS_LOCK)  # the first worker, at work
    try:
        assert step_worker.main() == 2
    finally:
        first.release()
    assert seen["started"] == 0, "it took up nothing of an earlier run, so no claim of the first's turns was released"
    assert alive_on(store) == [], "and it leaves no mark of being alive"


def test_a_worker_alone_on_its_store_holds_the_steps_and_its_mark_while_it_works(worker):
    store, seen = worker
    assert step_worker.main() == 0
    assert seen["started"] == 1
    held, marks = seen["held"]
    assert held, "the steps are held while it works"
    assert len(marks) == 1 and marks[0].startswith("worker-")
    again = claim(store / step_worker.STEPS_LOCK)
    assert again is not None, "a worker that ended lets the steps go"
    again.release()


def test_a_worker_does_not_start_while_a_key_rotation_has_the_store(worker):
    store, seen = worker
    rotation = claim(store / REKEYING)
    try:
        assert step_worker.main() == 2
    finally:
        rotation.release()
    assert seen["started"] == 0 and alive_on(store) == []


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The server's start (plan AN.50, 50f2), with its application and its serving stood in for: whether it took up what an
    earlier run left, and what it held while it served. steps: how the application works its steps."""
    import uvicorn

    from nm.app import main as served
    store = tmp_path / "store"
    store.mkdir()
    seen = {"taken_up": 0, "held": None}

    def start(steps):
        monkeypatch.setattr(served, "Application", lambda: SimpleNamespace(
            environment={"NM_MATTER_STORE": str(store)}, root=tmp_path, steps_mode=steps, egress_log=None, legal_search=None,
            health=lambda: {"runtime": "ready"},
            readiness=lambda: {},  # plan AN.52 (52a6): the start measures readiness; this stand-in has nothing not ready
            activity=Activity(), step_jobs=StepJobs(),  # 52c3: the stop in order once serving ends reads them
            store=SimpleNamespace(sweep_deleted=lambda now, look=None: ())))  # plan AN.53 (D241): the serving process sweeps
        return served.main(["--no-follow-code"])
    monkeypatch.delenv(served.IN_FLIGHT_FILE, raising=False)
    monkeypatch.setattr(served, "create_app", lambda application=None: None)
    monkeypatch.setattr(served, "keep_egress_log", lambda log: None)
    monkeypatch.setattr(api, "prepare_history", lambda: None)
    monkeypatch.setattr(served, "_take_up_what_an_earlier_run_left",
                        lambda application: seen.update(taken_up=seen["taken_up"] + 1))
    monkeypatch.setattr(uvicorn, "run", lambda *_, **__: seen.update(
        held=(claim(store / step_worker.STEPS_LOCK) is None, alive_on(store))))
    return store, seen, start


def test_a_second_server_that_works_its_own_steps_refuses_to_start_and_takes_up_nothing(server):
    store, seen, start = server
    first = claim(store / step_worker.STEPS_LOCK)  # a server, or the step worker, at work on the steps
    try:
        assert start("inside") == 2
    finally:
        first.release()
    assert seen["taken_up"] == 0 and seen["held"] is None and alive_on(store) == []


def test_a_server_that_works_its_own_steps_holds_them_and_its_mark_while_it_serves(server):
    store, seen, start = server
    assert start("inside") == 0
    held, marks = seen["held"]
    assert seen["taken_up"] == 1 and held and len(marks) == 1 and marks[0].startswith("server-")


def test_a_server_whose_steps_the_worker_works_leaves_the_steps_to_it_and_still_marks_itself_alive(server):
    store, seen, start = server
    the_worker = claim(store / step_worker.STEPS_LOCK)
    try:
        assert start("web") == 0
    finally:
        the_worker.release()
    held, marks = seen["held"]
    assert held and len(marks) == 1 and marks[0].startswith("server-"), "the worker keeps the steps; the server is alive"


def test_a_server_does_not_start_while_a_key_rotation_has_the_store(server):
    store, seen, start = server
    rotation = claim(store / REKEYING)
    try:
        assert start("inside") == 2
    finally:
        rotation.release()
    assert seen["taken_up"] == 0 and seen["held"] is None and alive_on(store) == []
