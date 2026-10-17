"""A running NM moves onto the code on disk (owner, 16 Oct 2026: "this server running
old code - you need to address it for once and all"). The supervisor restarts the app
when the code has changed and settled, only once nothing is in flight, and starts a
stopped app again. Scripted processes and clock; no server is started here."""
import asyncio

import pytest

from nm.app import main

pytestmark = pytest.mark.class_a


class Child:
    started = []

    def __init__(self, command, env):
        self.command, self.env, self.returncode, self.stopped = command, env, None, False
        Child.started.append(self)
        self.pid = len(Child.started)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.stopped, self.returncode = True, 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.terminate()


def supervise(monkeypatch, codes, in_flight, crash_first=False, rounds=40, child=None):
    """Run the supervisor over scripted fingerprints and in-flight counts."""
    Child.started = []
    seen = {"looks": 0, "sleeps": 0}
    monkeypatch.setattr(main.subprocess, "Popen", Child)

    def fingerprint():
        seen["looks"] += 1
        return codes[min(seen["looks"] - 1, len(codes) - 1)]

    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])

    def sleep(seconds):
        clock[0] += seconds
        seen["sleeps"] += 1
        if crash_first and len(Child.started) == 1 and seen["sleeps"] == 1:
            Child.started[0].returncode = 1
        if seen["sleeps"] > rounds:
            raise KeyboardInterrupt

    monkeypatch.setattr(main, "source_fingerprint", fingerprint)
    monkeypatch.setattr(main.time, "sleep", sleep)
    monkeypatch.setattr(main, "_in_flight", lambda _path: in_flight.pop(0) if in_flight else 0)
    given = {} if child is None else {"child": child}
    assert main.follow_code(["--port", "8099"], **given) == 0
    return Child.started


def test_a_settled_change_restarts_the_app_onto_the_new_code(monkeypatch):
    started = supervise(monkeypatch, ["a", "a", "b", "b", "b"], in_flight=[])
    assert len(started) >= 2 and started[0].stopped
    assert started[0].command[-3:] == ["nm.app.main", "--port", "8099"]  # what the supervisor was given
    assert main.IN_FLIGHT_FILE in started[0].env


def test_a_development_launcher_is_served_and_followed_the_same_way(monkeypatch):
    # 17 Oct 2026: a launcher that adds its own diagnostics restarts onto new code too.
    started = supervise(monkeypatch, ["a", "a", "b", "b", "b"], in_flight=[], child=("dev_launcher.py",))
    assert len(started) >= 2 and started[0].stopped
    assert started[1].command[1:] == ["dev_launcher.py", "--port", "8099"]


def test_nothing_restarts_while_a_request_is_in_flight(monkeypatch):
    # The count is looked at before the restart: two looks still busy, then idle.
    started = supervise(monkeypatch, ["a", "a", "b", "b", "b"], in_flight=[2, 2, 1, 0])
    assert len(started) >= 2 and started[0].stopped


def test_a_change_still_moving_is_not_restarted_onto(monkeypatch):
    # Every look finds new code: nothing has settled, so no second app is started.
    started = supervise(monkeypatch, [str(n) for n in range(40)], in_flight=[], rounds=12)
    assert len(started) == 1


def test_a_stopped_app_is_started_again(monkeypatch):
    started = supervise(monkeypatch, ["a"], in_flight=[], crash_first=True, rounds=4)
    assert len(started) == 2 and started[0].returncode == 1


def test_the_app_counts_what_is_in_flight(tmp_path):
    seen = []

    async def app(scope, receive, send):
        seen.append(counter.path.read_text())

    counter = main._InFlight(app, tmp_path / "count")
    assert (tmp_path / "count").read_text() == "0"
    asyncio.run(counter({"type": "http"}, None, None))
    asyncio.run(counter({"type": "lifespan"}, None, None))
    assert seen == ["1", "0"] and (tmp_path / "count").read_text() == "0"


def test_serving_follows_the_code_unless_told_not_to_and_the_child_is_told_not_to(monkeypatch):
    given = []
    monkeypatch.setattr(main, "follow_code", lambda args: given.append(args) or 0)
    assert main.main(["--port", "8099"]) == 0
    assert given == [["--host", "127.0.0.1", "--port", "8099", "--no-follow-code"]]


def test_a_server_that_cannot_start_is_not_started_forever(monkeypatch):
    class Failing(Child):
        def poll(self):
            return 1

    Child.started = []
    monkeypatch.setattr(main.subprocess, "Popen", Failing)
    monkeypatch.setattr(main, "source_fingerprint", lambda: "a")
    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(main.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    assert main.follow_code(["--port", "8099"]) == 1
    assert len(Child.started) == main.QUICK_EXITS


def test_the_app_leaves_when_its_supervisor_is_gone(monkeypatch, tmp_path):
    import os
    import threading
    import time
    left = threading.Event()
    monkeypatch.setattr(main.os, "_exit", lambda code: left.set())
    beat = tmp_path / "alive"
    beat.touch()
    old = time.time() - 120
    os.utime(beat, (old, old))  # the supervisor stopped touching it two minutes ago
    main._leave_with_supervisor(str(beat), every=0.01, stale=60)
    assert left.wait(5)
    # The watch stops once it has decided (17 Oct 2026): it had kept looking and, with the
    # real exit restored after this test, ended the whole test run a moment later.
    for watch in [t for t in threading.enumerate() if t.name == "supervisor-watch"]:
        watch.join(1)
    assert not any(t.name == "supervisor-watch" for t in threading.enumerate())


def test_the_supervisor_touches_its_heartbeat_and_passes_it_on(monkeypatch):
    started = supervise(monkeypatch, ["a"], in_flight=[], rounds=3)
    assert main.HEARTBEAT_FILE in started[0].env
