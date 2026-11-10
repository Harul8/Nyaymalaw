"""Steps in a worker process of their own (plan AN.48, piece 48f4; owner decision D167, 10 Nov 2026).

    python -m nm.app.step_worker        # the step worker, beside a web server started with NM_STEP_WORKER=separate

With NM_STEP_WORKER=separate the web server works no step itself: it hands each to the step worker through the shared step store
(nm/shared/step_share_store.py) and waits for it as 48f1 waits; the worker takes the steps, works them on its own step threads within
the limits (48f2), keeps their records and takes them up after a restart (48f3), and says what each answered. What the web server
asks of a step at work - Stop, Steer, answers to NM's questions, what is typed meanwhile - reaches the worker the same way, and the
worker says how it was taken; the progress the page reads and NM's open questions are kept there by the worker. Restarting the web
server stops no step; a big matter's own processing cannot slow other advocates' pages; and the web server needs no graphics card.
Unset (or 'inside'), everything is one process, as before.

The pieces on each side: the web server's SharedProgress, SharedDesk and RemoteSteps read and ask through the store; the worker's
MirroredProgress and MirroredDesk keep the store told while they work as before; StepWorker is the worker's loop.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from nm.app.turn_progress import KEEP_SECONDS, TurnProgress
from nm.core_engine.questions import Refused

_log = logging.getLogger("nm.steps")

#: How often the worker looks for steps and for what is asked of those at work, in seconds; how often it beats; how long a beat
#: lasts before the web server takes the worker as gone; how long the web server waits for the worker's word on what it asked.
LOOK_EVERY, BEAT_EVERY, BEAT_LASTS, VERDICT_WAIT = 0.2, 2.0, 30.0, 10.0
MODES = ("inside", "web", "worker")


def mode_from(setting):
    """'web' where the settings say the steps run in a worker of their own (NM_STEP_WORKER=separate); otherwise 'inside'."""
    return "web" if (setting or "").strip().lower() == "separate" else "inside"


def alive(share):
    """Whether a step worker has beaten within BEAT_LASTS seconds."""
    try:
        return any(quiet <= BEAT_LASTS for _, quiet, _, _ in share.workers())
    except Exception:  # noqa: BLE001 - a store that cannot be read says no worker is known to be there
        return False


# --- the web server's side ----------------------------------------------------------------------------------------------------
class SharedProgress:
    """What each turn is doing, as the worker keeps it in the shared store (the web server's TurnProgress): read as TurnProgress
    reads its own rows. A worker not heard from within BEAT_LASTS is gone: what it was doing is not known (D73 then speaks)."""

    def __init__(self, share):
        self._share = share

    def read(self, advocate_id, turn_id):
        if not alive(self._share):
            return {"state": "unknown"}
        try:
            raw = self._share.progress(advocate_id, turn_id)
        except Exception:  # noqa: BLE001 - progress is auxiliary: unknown, never a failure claim
            return {"state": "unknown"}
        return TurnProgress.view(raw, time.time(), KEEP_SECONDS) if raw else {"state": "unknown"}

    def waiting(self, advocate_id, turn_id):
        """A step taken by the web server and not yet at work (48f2's place, or not yet taken by the worker)."""
        try:
            raw = self._share.progress(advocate_id, turn_id)
        except Exception:  # noqa: BLE001
            return False
        return bool(raw and raw.get("ended") is None and raw.get("steps") and raw["steps"][-1]["stage"] == "queued")

    def taken(self, advocate_id, turn_id):
        """The web server has taken a step for the worker: until the worker says more, it waits for a place - unless the worker
        already says the turn is at work."""
        now = time.time()
        try:
            raw = self._share.progress(advocate_id, turn_id)
            if raw and raw.get("ended") is None:
                return
            self._share.put_progress(advocate_id, turn_id, {"started": now, "ended": None, "state": "working",
                                                            "steps": [{"stage": "queued", "at": now}], "detail": {}})
        except Exception:  # noqa: BLE001 - the worker says it as soon as it takes the step
            pass

    # The web server works no step: nothing else of it is told here.
    def report(self, *args, **kwargs):
        return None

    shown = saved = tentative = end = report


class _Window:
    def __init__(self, view):
        self._view = view

    def view(self):
        return self._view


class SharedDesk:
    """NM's open questions, as the worker shows them in the shared store (the web server's QuestionDesk); answers go to the worker,
    which takes them as its window does and says how."""

    def __init__(self, share, *, wait=VERDICT_WAIT):
        self._share, self._wait = share, wait

    def window(self, advocate_id, turn_id):
        if not alive(self._share):
            return None
        view = self._share.window(advocate_id, turn_id)
        return None if view is None else _Window(view)

    def answer(self, advocate_id, turn_id, given):
        verdict = ask_worker(self._share, advocate_id, turn_id, "answers", given, wait=self._wait)
        if verdict is None or verdict.get("state") == "closed":
            return "closed"
        if "refused" in verdict:
            raise Refused(verdict["refused"])
        return verdict.get("state", "taken")

    def close(self, advocate_id, turn_id):
        return None


def ask_worker(share, advocate_id, turn_id, kind, asked, *, wait=VERDICT_WAIT):
    """What is asked of a step at work, sent to the worker; its word on it, or None where it did not answer within wait."""
    number = share.control(advocate_id, turn_id, kind, asked)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        verdict = share.verdict_of(number)
        if verdict is not None:
            return verdict
        time.sleep(LOOK_EVERY / 2)
    return None


class _Asked:
    """A step the web server handed to the worker (RemoteSteps.start): what it answered, once it has."""

    def __init__(self, share, number):
        self._share, self.number = share, number

    def answered(self):
        return self._share.answered(self.number)


class RemoteSteps:
    """The web server's StepJobs: a step handed to the worker and waited for as 48f1 waits."""

    def __init__(self, share, *, wait_seconds):
        self._share, self.wait_seconds = share, wait_seconds
        self.hold = self.placed = self.settled = self.records = None

    def ask(self, advocate_id, turn_id, asked):
        return _Asked(self._share, self._share.ask(advocate_id, turn_id, asked))

    def wait_for(self, asked, seconds=None):
        """What it answered within seconds (the wait), or None while it still waits or works."""
        end = time.monotonic() + (self.wait_seconds if seconds is None else seconds)
        while True:
            answered = asked.answered()
            if answered is not None or time.monotonic() >= end:
                return answered
            time.sleep(LOOK_EVERY / 2)

    def latest(self, advocate_id, turn_id):
        found = self._share.latest(advocate_id, turn_id)
        return None if found is None else _Asked(self._share, found[0])

    def waiting(self, advocate_id, turn_id):
        """Whether that step waits, not yet at work (48f2's Steer refusal)."""
        return SharedProgress(self._share).waiting(advocate_id, turn_id)

    def running_here(self, advocate_id, turn_id):
        return False


# --- the worker's side ----------------------------------------------------------------------------------------------------------
class MirroredProgress(TurnProgress):
    """The worker's TurnProgress, on the wall clock both processes share, telling the shared store each change it makes."""

    def __init__(self, share, **kwargs):
        super().__init__(clock=time.time, **kwargs)
        self._share = share

    def _told(self, advocate_id, turn_id):
        raw = self.raw(advocate_id, turn_id)
        if raw is None:
            return
        try:
            self._share.put_progress(advocate_id, turn_id, raw)
        except Exception as exc:  # noqa: BLE001 - progress is auxiliary to the step
            _log.warning("A step's progress could not be shared (%s).", type(exc).__name__)

    def report(self, advocate_id, turn_id, stage, detail=None):
        super().report(advocate_id, turn_id, stage, detail)
        self._told(advocate_id, turn_id)

    def shown(self, advocate_id, turn_id, count, chat_id):
        super().shown(advocate_id, turn_id, count, chat_id)
        self._told(advocate_id, turn_id)

    def saved(self, advocate_id, turn_id, count, chat_id):
        super().saved(advocate_id, turn_id, count, chat_id)
        self._told(advocate_id, turn_id)

    def tentative(self, advocate_id, turn_id, seconds):
        super().tentative(advocate_id, turn_id, seconds)
        self._told(advocate_id, turn_id)

    def end(self, advocate_id, turn_id, state):
        super().end(advocate_id, turn_id, state)
        self._told(advocate_id, turn_id)


class StepWorker:
    """The step worker's loop: the steps the web server took, begun within the limits; what is asked of those at work, taken and
    answered; NM's open questions shown; a beat every BEAT_EVERY seconds."""

    def __init__(self, app, *, name=None):
        self.app, self.share = app, app.step_share
        self.name = name or f"worker-{os.getpid()}"
        self._stop = threading.Event()

    def start(self):
        """At the worker's start: its earlier run's claims released (D73), its windows closed, the progress it left said stopped,
        and the steps it left taken up (48f3)."""
        from nm.app.main import _take_up_what_an_earlier_run_left
        self.share.close_windows()
        for advocate_id, turn_id, raw in self.share.all_progress():
            if raw.get("ended") is not None:
                continue
            waiting = bool(raw.get("steps") and raw["steps"][-1]["stage"] == "queued")
            handed = self.share.latest(advocate_id, turn_id) if waiting else None
            if not waiting or handed is None or handed[1]:  # at work in the run that stopped, or waiting for nothing handed
                self.share.put_progress(advocate_id, turn_id, {**raw, "ended": time.time(), "state": "stopped"})
        _take_up_what_an_earlier_run_left(self.app)

    def tick(self):
        """One look: the steps taken, what is asked, the windows shown."""
        from nm.app import api
        for number, advocate_id, turn_id, asked in self.share.take():
            api.work_handed_step(self.app, number, advocate_id, turn_id, asked)
        for number, advocate_id, turn_id, kind, asked in self.share.controls():
            self.share.verdict(number, self._taken(advocate_id, turn_id, kind, asked))
        self.app.questions.show_open()

    def _taken(self, advocate_id, turn_id, kind, asked):
        try:
            if kind == "stop":
                return {"stopping": bool(self.app.stop_turn(advocate_id, turn_id))}
            if kind == "steer":
                return {"taken": bool(self.app.steered(advocate_id, turn_id, asked))}
            if kind == "answers":
                return {"state": self.app.questions.answer(advocate_id, turn_id, asked)}
            if kind == "queued":
                self.app.save_queued(advocate_id=advocate_id, chat_id=asked["chat_id"], queued=asked["queued"])
                return {"saved": True}
        except Refused as exc:
            return {"refused": str(exc)}
        except LookupError:
            return {"missing": True}
        except Exception as exc:  # noqa: BLE001 - said to the web server as not done; the worker goes on
            _log.warning("What was asked of a step could not be taken (%s).", type(exc).__name__)
            return {"failed": type(exc).__name__}
        return {"unknown": kind}

    def run(self):
        """Look every LOOK_EVERY seconds until stopped; beat every BEAT_EVERY seconds; let go of what was answered long ago."""
        beat = forgot = 0.0
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - one look that failed; the next looks again
                _log.warning("The step worker could not look this time (%s).", type(exc).__name__)
            now = time.monotonic()
            if now - beat >= BEAT_EVERY:
                beat = now
                try:
                    self.share.beat(self.name, waiting=self.app.step_jobs.count_waiting(),
                                    working=self.app.step_jobs.count_working())
                except Exception as exc:  # noqa: BLE001
                    _log.warning("The step worker could not beat (%s).", type(exc).__name__)
            if now - forgot >= 60:
                forgot = now
                try:
                    self.share.forget(time.time() - KEEP_SECONDS)
                except Exception:  # noqa: BLE001
                    pass
            self._stop.wait(LOOK_EVERY)

    def stop(self):
        self._stop.set()


def main(argv=None):
    """The step worker: the application in its worker's part, its start, then its loop until stopped."""
    from nm.app import api
    from nm.app.composition import Application
    try:
        app = Application(steps="worker")
    except Exception as exc:
        print(f"REFUSED TO START: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    api.set_application(app)
    worker = StepWorker(app)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: worker.stop())
    worker.start()
    warm = getattr(getattr(app, "legal_search", None), "warm", None)
    if callable(warm):
        threading.Thread(target=warm, name="search-warm", daemon=True).start()
    print(f"The step worker {worker.name} is working the steps.", flush=True)
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
