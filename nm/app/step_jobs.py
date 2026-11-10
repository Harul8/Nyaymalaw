"""Steps as jobs (plan AN.48, piece 48f1; owner decision D167, 10 Nov 2026).

A step - a message sent, Continue, a go-ahead, answers given at a stop, a message while a matter waits - is worked on the server's
own step threads, never inside the request that asked for it for its minutes: a web proxy in front of a hosted server cuts a request
held open that long, and long steps would take the threads that serve every page. The request waits for its step a short while and
answers exactly as it always has where the step is done by then; otherwise it answers that the step is working, and the step goes
on. What the step answers - its answer, or its refusal as its request would have said it - is kept for its own advocate a while after
it is done (KEEP_SECONDS), in this process's memory only, for the page to read. Nothing here changes what a step does: each job is
exactly the call its request would have made, in the request's own context.
"""
from __future__ import annotations

import contextvars
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as StepStillWorking

#: How long a request waits for its step before answering that it is working, in seconds (NM_STEP_WAIT_SECONDS): well inside the
#: minute after which common web proxies close a request.
WAIT_SECONDS = 20.0
#: How long what a step answered is kept after it is done, for its advocate's page, in seconds.
KEEP_SECONDS = 900


def wait_from(setting, default=WAIT_SECONDS):
    """The wait a setting names, in seconds: a number from 0 to 60; anything else is the default."""
    try:
        seconds = float(setting)
    except (TypeError, ValueError):
        return default
    return seconds if 0 <= seconds <= 60 else default


class StepJobs:
    """The steps this server is working on, or has finished within KEEP_SECONDS, by advocate and turn."""

    def __init__(self, *, wait_seconds=WAIT_SECONDS, keep_seconds=KEEP_SECONDS, clock=time.monotonic):
        self.wait_seconds = wait_seconds
        self._keep, self._clock = keep_seconds, clock
        self._jobs: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()
        #: Told +1 as a step begins and -1 as it ends (main.py: the supervisor's count of what is in flight), so that a server
        #: following the code on disk is not restarted onto new code while a step works, as it never was while a request did.
        self.hold = None

    def _held(self, step):
        if self.hold is not None:
            try:
                self.hold(step)
            except Exception:  # noqa: BLE001 - the count is the supervisor's courtesy; a step never fails for it
                pass

    def start(self, advocate_id: str, turn_id: str, work) -> Future:
        """work, run on a step thread of its own in the caller's context; its Future carries what it returned or raised. A later
        step of the same turn (Continue, a go-ahead) takes the earlier one's place once that is done; while it works, what the turn
        answers stays that step's - a second request for it (another tab) is answered by its own Future only."""
        future: Future = Future()
        context = contextvars.copy_context()

        def run():
            if not future.set_running_or_notify_cancel():
                return
            try:
                result = context.run(work)
            except BaseException as exc:  # noqa: BLE001 - carried whole to whoever waits for the step or reads what it answered
                future.set_exception(exc)
            else:
                future.set_result(result)
            finally:
                with self._lock:
                    job = self._jobs.get((advocate_id, turn_id))
                    if job is not None and job["future"] is future:
                        job["done"] = self._clock()
                self._held(-1)

        with self._lock:
            self._prune()
            current = self._jobs.get((advocate_id, turn_id))
            if current is None or current["future"].done():
                self._jobs[(advocate_id, turn_id)] = {"future": future, "done": None}
        self._held(1)
        try:
            threading.Thread(target=run, name="nm-step", daemon=True).start()
        except BaseException:
            self._held(-1)
            raise
        return future

    def answered(self, future: Future):
        """(True, what the step returned) where it is done within the wait - raising what it raised - else (False, None). A step
        that itself ended in a timeout is done, and says so: the wait's own timeout is told apart by the step not being done."""
        try:
            return True, future.result(timeout=self.wait_seconds)
        except StepStillWorking:
            if not future.done():
                return False, None
            return True, future.result()

    def of(self, advocate_id: str, turn_id: str) -> Future | None:
        """The step of this advocate's turn the server holds - working, or done within KEEP_SECONDS - or None."""
        with self._lock:
            self._prune()
            job = self._jobs.get((advocate_id, turn_id))
        return None if job is None else job["future"]

    def _prune(self):
        now = self._clock()
        for key in [key for key, job in self._jobs.items() if job["done"] is not None and now - job["done"] > self._keep]:
            del self._jobs[key]
