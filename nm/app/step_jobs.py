"""Steps as jobs (plan AN.48, pieces 48f1 and 48f2; owner decision D167, 10 Nov 2026).

A step - a message sent, Continue, a go-ahead, answers given at a stop, a message while a matter waits - is worked on the server's
own step threads, never inside the request that asked for it for its minutes: a web proxy in front of a hosted server cuts a request
held open that long, and long steps would take the threads that serve every page. The request waits for its step a short while and
answers exactly as it always has where the step is done by then; otherwise it answers that the step is working, and the step goes
on. What the step answers - its answer, or its refusal as its request would have said it - is kept for its own advocate a while after
it is done (KEEP_SECONDS), in this process's memory only, for the page to read. Nothing here changes what a step does: each job is
exactly the call its request would have made, in the request's own context.

48f2: advocates share the server fairly. At most AT_ONCE steps work at once, and PER_ADVOCATE for one advocate; the others wait,
first come first served, each told its place as it changes (placed: its progress), and a step stopped while it waits is taken out:
nothing of it ran and nothing was charged. What the advocate adds to a step that has not begun goes as their next message (Steer,
D79, reaches only a step at work).
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
#: At most this many steps work at once on the server (NM_STEPS_AT_ONCE), and this many for one advocate (NM_STEPS_PER_ADVOCATE):
#: the law search shares one graphics card, the AI service limits the calls a minute, and NM's own processing of a big matter is
#: heavy. Claude's figures (plan AN.48, 48f2), for the owner to correct.
AT_ONCE, PER_ADVOCATE = 3, 2


def wait_from(setting, default=WAIT_SECONDS):
    """The wait a setting names, in seconds: a number from 0 to 60; anything else is the default."""
    try:
        seconds = float(setting)
    except (TypeError, ValueError):
        return default
    return seconds if 0 <= seconds <= 60 else default


def count_from(setting, default):
    """How many steps a setting allows: a whole number from 1 to 64; anything else is the default."""
    try:
        number = int(str(setting).strip())
    except (TypeError, ValueError):
        return default
    return number if 1 <= number <= 64 else default


class StepCancelled(Exception):
    """A step its advocate stopped before it began (48f2): nothing of it ran and nothing was charged."""


class StepJobs:
    """The steps this server is working on, waiting to work on, or has finished within KEEP_SECONDS, by advocate and turn."""

    Cancelled = StepCancelled

    def __init__(self, *, wait_seconds=WAIT_SECONDS, at_once=AT_ONCE, per_advocate=PER_ADVOCATE, keep_seconds=KEEP_SECONDS,
                 clock=time.monotonic):
        self.wait_seconds, self.at_once, self.per_advocate = wait_seconds, at_once, per_advocate
        self._keep, self._clock = keep_seconds, clock
        self._jobs: dict[tuple[str, str], dict] = {}
        self._waiting: list[dict] = []
        self._working: dict[str, int] = {}
        self._lock = threading.Lock()
        #: Told +1 as a step is taken and -1 as it ends (main.py: the supervisor's count of what is in flight), so that a server
        #: following the code on disk is not restarted onto new code while a step works or waits, as it never was while a request
        #: did.
        self.hold = None
        #: Told (advocate_id, turn_id, ahead) whenever a waiting step's place is said: how many wait before it (composition: its
        #: progress).
        self.placed = None

    def _held(self, step):
        if self.hold is not None:
            try:
                self.hold(step)
            except Exception:  # noqa: BLE001 - the count is the supervisor's courtesy; a step never fails for it
                pass

    def start(self, advocate_id: str, turn_id: str, work, *, cancelled=None) -> Future:
        """work, run on a step thread of its own in the caller's context once a place is free; its Future carries what it returned
        or raised. A later step of the same turn (Continue, a go-ahead) takes the earlier one's place once that is done; while it
        waits or works, what the turn answers stays that step's - a second request for it (another tab) is answered by its own
        Future only. cancelled: what its Future raises when its advocate stops it before it begins (StepCancelled if none)."""
        future: Future = Future()
        job = {"future": future, "done": None, "advocate": advocate_id, "turn": turn_id, "work": work,
               "context": contextvars.copy_context(), "stop": False,
               "cancelled": cancelled or (lambda: StepCancelled("You stopped this before NM began on it."))}
        with self._lock:
            self._prune()
            current = self._jobs.get((advocate_id, turn_id))
            if current is None or current["future"].done():
                self._jobs[(advocate_id, turn_id)] = job
            self._waiting.append(job)
        self._held(1)
        self._dispatch()
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
        """The step of this advocate's turn the server holds - waiting, working, or done within KEEP_SECONDS - or None."""
        with self._lock:
            self._prune()
            job = self._jobs.get((advocate_id, turn_id))
        return None if job is None else job["future"]

    def waiting(self, advocate_id: str, turn_id: str) -> bool:
        """Whether that step waits for a free place, not yet begun."""
        with self._lock:
            job = self._jobs.get((advocate_id, turn_id))
            return job is not None and any(waiting is job for waiting in self._waiting)

    def cancel(self, advocate_id: str, turn_id: str) -> bool:
        """Stop, while the step waits (48f2): it is taken out, its Future raising StepCancelled; False where it is not waiting."""
        with self._lock:
            job = self._jobs.get((advocate_id, turn_id))
            if job is None or not any(waiting is job for waiting in self._waiting):
                return False
            self._waiting.remove(job)
            job["done"] = self._clock()
        job["future"].set_exception(job["cancelled"]())
        self._held(-1)
        self._dispatch()
        return True

    def ask_stop(self, advocate_id: str, turn_id: str) -> bool:
        """Stop, for a step that has just begun and is not yet working where Stop reaches it (composition: its run not yet
        registered): kept with it, for that run to take as it registers (stop_asked). False where the server holds no such step."""
        with self._lock:
            job = self._jobs.get((advocate_id, turn_id))
            if job is None or job["future"].done():
                return False
            job["stop"] = True
            return True

    def stop_asked(self, advocate_id: str, turn_id: str) -> bool:
        """Whether its advocate asked that step to stop before its run could hear it."""
        with self._lock:
            job = self._jobs.get((advocate_id, turn_id))
            return bool(job and job.get("stop"))

    def _dispatch(self):
        """Begin every waiting step a place is free for, first come first served, an advocate at their own limit passed over; then
        tell each step still waiting its place."""
        begun = []
        with self._lock:
            working = sum(self._working.values())
            for job in list(self._waiting):
                if working >= self.at_once:
                    break
                if self._working.get(job["advocate"], 0) >= self.per_advocate:
                    continue
                self._waiting.remove(job)
                self._working[job["advocate"]] = self._working.get(job["advocate"], 0) + 1
                working += 1
                begun.append(job)
            places = [(job["advocate"], job["turn"], ahead) for ahead, job in enumerate(self._waiting)]
        for job in begun:
            self._begin(job)
        if self.placed is not None:
            for advocate_id, turn_id, ahead in places:
                try:
                    self.placed(advocate_id, turn_id, ahead)
                except Exception:  # noqa: BLE001 - a place not said is said at the next change; the step is not lost for it
                    pass

    def _begin(self, job):
        future = job["future"]

        def run():
            try:
                if not future.set_running_or_notify_cancel():
                    return
                try:
                    result = job["context"].run(job["work"])
                except BaseException as exc:  # noqa: BLE001 - carried whole to whoever waits for the step or reads its outcome
                    future.set_exception(exc)
                else:
                    future.set_result(result)
            finally:
                self._ended(job)

        try:
            threading.Thread(target=run, name="nm-step", daemon=True).start()
        except BaseException as exc:  # noqa: BLE001 - a step that cannot begin says why to whoever waits for it
            if future.set_running_or_notify_cancel():
                future.set_exception(exc)
            self._ended(job)

    def _ended(self, job):
        with self._lock:
            self._working[job["advocate"]] -= 1
            if not self._working[job["advocate"]]:
                del self._working[job["advocate"]]
            current = self._jobs.get((job["advocate"], job["turn"]))
            if current is job:
                job["done"] = self._clock()
        self._held(-1)
        self._dispatch()

    def _prune(self):
        now = self._clock()
        for key in [key for key, job in self._jobs.items() if job["done"] is not None and now - job["done"] > self._keep]:
            del self._jobs[key]
