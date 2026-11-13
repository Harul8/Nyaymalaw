"""Entry point. The only module that both builds adapters and touches the edge.

    python -m nm.app.main                    # serve on :8000, following the code on disk
    python -m nm.app.main --check            # wire everything, print health, exit
    python -m nm.app.main --no-follow-code   # one process that keeps the code it loaded

`--check` exists because "does it start" and "does it work" are different
questions, and the second one is the one worth being able to answer without a
browser.

Following the code (owner, 16 Oct 2026: "this server running old code - you need to
address it for once and all") is how NM serves unless --no-follow-code is given, so
every way of starting it - start.ps1, a launch entry, a plain `python -m` - keeps up
with the code on disk. A supervisor serves the app as a child process
and watches the same code fingerprint the stale-code check reports. When the
code on disk changes and has settled, it waits until no request is in flight -
an answer can take ten minutes, a document read one - and then restarts the app
onto the new code. A child that stops is started again.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from nm.app import api, step_worker
from nm.app.composition import Application, storage_root
from nm.shared.egress_log_store import keep as keep_egress_log
from nm.shared.identity_contracts import source_fingerprint

#: How often the supervisor looks at the code, how long a change must hold still,
#: and how long a stopped child waits before it is started again.
CHECK_SECONDS, SETTLE_SECONDS, RESTART_PAUSE = 5.0, 10.0, 3.0
#: A child that stops this soon after starting, this many times in a row, is not
#: started again (another server holds the port, or it cannot start at all).
QUICK_EXIT_SECONDS, QUICK_EXITS = 30.0, 5
#: Set by the supervisor: the file in which the child keeps its in-flight count, and
#: the file the supervisor touches to show it is still there.
IN_FLIGHT_FILE, HEARTBEAT_FILE = "NM_IN_FLIGHT_FILE", "NM_SUPERVISOR_HEARTBEAT"
#: How often the child looks at the heartbeat, and how old it may grow.
HEARTBEAT_SECONDS, HEARTBEAT_STALE = 5.0, 60.0


class _InFlight:
    """Counts the HTTP requests and sockets being served, for the supervisor only - and, from plan AN.48 (48f1, D167), the steps
    that go on after their request has answered (hold)."""

    def __init__(self, app, path):
        self.app, self.path, self.count, self.lock = app, Path(path), 0, threading.Lock()
        self._move(0)

    def hold(self, step):
        """A step worked after its request answered: +1 as it begins, -1 as it ends."""
        self._move(step)

    def _move(self, step):
        with self.lock:
            self.count += step
            try:
                self.path.write_text(str(self.count), encoding="ascii")
            except OSError:
                pass  # the supervisor then sees the last count it could read

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        self._move(1)
        try:
            await self.app(scope, receive, send)
        finally:
            self._move(-1)


def _leave_with_supervisor(heartbeat, *, every=HEARTBEAT_SECONDS, stale=HEARTBEAT_STALE):
    """The supervisor touches its heartbeat file every few seconds; when it has stopped
    for a minute the supervisor is gone, and the child goes too rather than serve on
    unwatched. A file, not a pipe: nothing in the child blocks on its supervisor."""
    def watch():
        while True:
            time.sleep(every)
            try:
                quiet = time.time() - os.path.getmtime(heartbeat)
            except OSError:
                quiet = stale + 1
            if quiet > stale:
                print("The supervisor is gone; this server stops.", flush=True)
                os._exit(0)
                # Leaving is decided once (17 Oct 2026): a watch that kept looking would,
                # in a test that stands in for the exit, end the test process later.
                return
    threading.Thread(target=watch, name="supervisor-watch", daemon=True).start()


def _in_flight(path):
    try:
        return int(path.read_text(encoding="ascii") or "0")
    except (OSError, ValueError):
        return 0


def follow_code(serve_args, *, child=("-m", "nm.app.main")):
    """Serve the app as a child process and restart it onto the code on disk. child: what
    the interpreter runs to serve (17 Oct 2026: a development launcher that adds its own
    diagnostics names itself, so it follows the code too); it is given serve_args."""
    handle, name = tempfile.mkstemp(prefix="nm-in-flight-", suffix=".count")
    os.close(handle)
    counter = Path(name)
    heartbeat = counter.with_suffix(".alive")
    heartbeat.touch()
    environment = dict(os.environ, **{IN_FLIGHT_FILE: str(counter), HEARTBEAT_FILE: str(heartbeat)})

    def pause(seconds):
        """Sleep, touching the heartbeat on the way, so the child knows it is watched."""
        end = time.monotonic() + seconds
        while True:
            heartbeat.touch()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, HEARTBEAT_SECONDS))
    command = [sys.executable, *child, *serve_args]
    child, quick = None, 0
    try:
        while True:
            serving = source_fingerprint()
            counter.write_text("0", encoding="ascii")
            child, began = subprocess.Popen(command, env=environment), time.monotonic()
            print(f"Serving code {serving} (process {child.pid}); following the code on disk.", flush=True)
            while True:
                pause(CHECK_SECONDS)
                if child.poll() is not None:
                    quick = quick + 1 if time.monotonic() - began < QUICK_EXIT_SECONDS else 0
                    if quick >= QUICK_EXITS:
                        print(f"The server stopped {quick} times just after starting (last exit "
                              f"{child.returncode}); not starting it again.", flush=True)
                        return 1
                    print(f"The server stopped (exit {child.returncode}); starting it again.", flush=True)
                    pause(RESTART_PAUSE)
                    break
                try:
                    now = source_fingerprint()
                except Exception:  # noqa: BLE001 - not assessed this time; looked at again
                    continue
                if now == serving:
                    continue
                # A change settles first: an edit or a checkout touches many files.
                pause(SETTLE_SECONDS)
                if source_fingerprint() != now:
                    continue
                waiting = _in_flight(counter)
                if waiting:
                    print(f"The code changed ({serving} to {now}); waiting for {waiting} request(s) in "
                          "flight to finish before restarting.", flush=True)
                while _in_flight(counter) and child.poll() is None:
                    pause(1)
                print(f"Restarting onto the code on disk ({serving} to {now}).", flush=True)
                child.terminate()
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                break
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.terminate()
        return 0
    finally:
        counter.unlink(missing_ok=True)
        heartbeat.unlink(missing_ok=True)


def _take_up_what_an_earlier_run_left(application):
    """The turns an earlier run of this server was working on are released (D73), then the steps it left taken up again by the
    server itself where they can be (plan AN.48, 48f3, D167) - before any page can ask to continue them."""
    from nm.shared.turn_attempt_port import AttemptRefused
    try:
        released = application.turns_of_an_earlier_run_released()
    except AttemptRefused as exc:  # the server still starts; such an answer then waits on Continue
        print(f"The answers an earlier run was working on could not be released: {exc.code}", file=sys.stderr)
        return
    if released:
        print(f"{released} answer(s) an earlier run was working on can continue where they stopped.", file=sys.stderr)
    try:
        taken = api.continue_interrupted_steps(application)
    except Exception as exc:  # noqa: BLE001 - the server still starts; each such turn waits for its advocate, as before (D73)
        print(f"The steps an earlier run left could not be taken up: {type(exc).__name__}", file=sys.stderr)
    else:
        if taken:
            print(f"{taken} step(s) an earlier run left were taken up again.", file=sys.stderr)


def create_app(application: Application | None = None):
    """Wire the composition root into the served path and return the ASGI app."""
    api.set_application(application or Application())
    return api.app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nyaymalaw")
    ap.add_argument("--check", action="store_true",
                    help="wire everything, print health, and exit")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-follow-code", action="store_true",
                    help="serve in this one process, keeping the code it loaded (the supervisor's child)")
    args = ap.parse_args(argv)
    if not args.no_follow_code and not args.check:
        return follow_code(["--host", args.host, "--port", str(args.port), "--no-follow-code"])

    try:
        application = Application()
    except Exception as exc:
        # Configuration is refused at STARTUP rather than used: an unpinned
        # alias, an unlisted provider, a judge that grades its own homework, or
        # an unconfigured encryption key all land here.
        print(f"REFUSED TO START: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    health = application.health()
    if args.check:
        print(json.dumps(health, indent=2))
        return 0 if health["runtime"] == "ready" else 1

    # Plan AN.50 (50f, D190, D192): this server marked alive on its store and, where it works its own steps, their one owner -
    # before anything an earlier run left is taken up below. A second refuses to start.
    held, why = step_worker.take_the_store(storage_root(application.environment, application.root), "server",
                                           steps=application.steps_mode != "web")
    if held is None:
        print(f"REFUSED TO START: {why}.", file=sys.stderr)
        return 2
    create_app(application)
    import uvicorn

    served = api.app
    if os.environ.get(IN_FLIGHT_FILE):
        served = _InFlight(api.app, os.environ[IN_FLIGHT_FILE])
        # Plan AN.48 (48f1): a step that goes on after its request answered is in flight too, until it ends - from before any step
        # is taken up below (48f3).
        application.step_jobs.hold = served.hold
        if os.environ.get(HEARTBEAT_FILE):
            _leave_with_supervisor(os.environ[HEARTBEAT_FILE])

    # Plan AN.41 (D73): what the earlier run of this server was working on stopped with it; each such answer is made able to
    # continue where it stopped, by itself once its advocate's page is back. Its start is the one owner that knows this. Plan AN.48
    # (48f4): where the steps run in a worker process of their own, the worker's start owns that, and a web server restarting
    # alone stops none of them.
    if application.steps_mode == "web":
        print("The steps are worked by the step worker (NM_STEP_WORKER=separate): start it with python -m nm.app.step_worker.",
              file=sys.stderr)
    else:
        _take_up_what_an_earlier_run_left(application)

    warm_search = getattr(getattr(application, "legal_search", None), "warm", None)
    if callable(warm_search):
        threading.Thread(target=warm_search, name="search-warm", daemon=True).start()
    # The conversation history's lines (owner decision O29), made ready in the background, newest first, so
    # the first opening of the history after a start reads small lines and opens no large file.
    threading.Thread(target=api.prepare_history, name="history-warm", daemon=True).start()
    # Plan AN.48 (D169): the outgoing-data log swept now and once a day after - a day over 90 days old compressed, over a year
    # deleted - by each process that writes it.
    keep_egress_log(application.egress_log)
    print(json.dumps(health, indent=2))
    uvicorn.run(served, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
