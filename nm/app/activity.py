"""What this process is doing that a stop must not cut off, and how long it has had nothing to do (plan AN.52, 52c, D209; the
review's F-12).

ONE LEDGER. Every long piece of work this process does is held here while it goes on, by its own owner and by kind: a step
waiting or working (the step jobs), a request being answered (the supervisor's count, main.py), and - as their owners register
- an upload being scanned, a paper being read, a dictation and a save. It decides nothing. It answers two questions:

    may_stop()    'May I stop?' - no while anything is held. The supervisor that restarts the server onto new code waits for
                  it; the orderly stop waits for it.
    quiet_for()   How long nothing has been held and no signed-in advocate has acted, in seconds; None while work is held. The
                  idle timer of a hosted server (D176) reads this, and nothing else.

Until now what a process was doing was known only to that supervisor, and only while it ran the server: a count of requests
and steps written to a file. A paper read on a thread of its own after its request had answered was in it nowhere.

A REQUEST IS HELD, BUT IT IS NOT A SIGN OF LIFE. An outside monitor asks the health address every minute, and a server woken
by every such request would never be quiet. So quiet runs from the later of the end of the last piece of work that is not a
request and the last signed-in action, whatever requests come and go; a request is held only so that no stop cuts one off.

COUNTS ONLY: never whose, and never what.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

_log = logging.getLogger(__name__)

#: The kinds of work held, each by the owner that does it.
KINDS = ("request", "step", "scan", "reading", "dictation", "save")
#: Held so that no stop cuts it off, but not a sign of life for quiet_for (see above).
NOT_LIFE = frozenset({"request"})


class Activity:
    """The ledger of one process. Construct once, in the composition root; every owner of long work holds its kind here."""

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._held = dict.fromkeys(KINDS, 0)
        self._lock = threading.Lock()
        #: The last moment work that is a sign of life began or ended (from the ledger's start), and the last signed-in action.
        self._life, self._signed_in = clock(), None
        self._told = []

    def move(self, kind: str, step: int) -> None:
        """Hold one more piece of work of this kind (+1), or let one go (-1)."""
        if kind not in self._held:
            raise ValueError(f"no such kind of work: {kind!r}")
        if step not in (1, -1):
            raise ValueError("work is held or let go one piece at a time")
        with self._lock:
            if step < 0 and not self._held[kind]:
                # A release with nothing held is its owner's mistake; a count below nought would read to the supervisor as
                # something in flight for ever. Said, and the count stays at nought.
                _log.warning("A piece of %s work was let go with nothing held.", kind)
                return
            self._held[kind] += step
            if kind not in NOT_LIFE:
                self._life = self._clock()
            total, told = sum(self._held.values()), list(self._told)
        self._say(told, total)

    @contextmanager
    def held(self, kind: str):
        """Hold one piece of work of this kind for the length of the block, and let it go however the block ends."""
        self.move(kind, 1)
        try:
            yield
        finally:
            self.move(kind, -1)

    def counts(self) -> dict:
        """What is held now, by kind: only the kinds with something held."""
        with self._lock:
            return {kind: count for kind, count in self._held.items() if count}

    def total(self) -> int:
        with self._lock:
            return sum(self._held.values())

    def may_stop(self) -> bool:
        """'May I stop?': yes only while nothing is held."""
        return self.total() == 0

    def signed_in_action(self) -> None:
        """A signed-in advocate acted: a sign of life for quiet_for."""
        with self._lock:
            self._signed_in = self._clock()

    def quiet_for(self) -> float | None:
        """Seconds since the later of the last work that is a sign of life and the last signed-in action; None while such work is
        held."""
        with self._lock:
            if any(count for kind, count in self._held.items() if kind not in NOT_LIFE):
                return None
            last = self._life if self._signed_in is None else max(self._life, self._signed_in)
            return self._clock() - last

    def tell(self, told) -> None:
        """Call told(total) now and after every change (the supervisor's count, main.py). A failure to hear fails no work."""
        with self._lock:
            self._told.append(told)
            total = sum(self._held.values())
        self._say([told], total)

    @staticmethod
    def _say(told, total) -> None:
        for hear in told:
            try:
                hear(total)
            except Exception:  # noqa: BLE001 - the count is the hearer's courtesy; no work ever fails for it
                pass


# ------------------------------------------------------------------------------------------------ the orderly stop ---
#
# AN ORDERLY STOP (plan AN.52, 52c3, D209; the review's F-12). A process stopped on a signal ended at once, and every step at work
# on its threads - daemon threads - was cut off part-way. Now the process that is stopping closes its step jobs - no waiting step
# begins here, and each keeps its record for the next start to take up, as any step an earlier run left - then waits until
# nothing in its ledger is held, or the limit passes, and says what it waited for and what it left. Only then does it end. Work
# cut off at the limit is taken up as after any restart: a step continues where it stopped (D73), a reading is asked for again.

#: How long an orderly stop waits for the work at hand, in seconds, unless NM_STOP_WAIT_SECONDS says otherwise. A step's single
#: longest call writes for two to four minutes; most end well within this. Give whatever stops the process (systemd's
#: TimeoutStopSec, a container's stop timeout) longer than this, or it will cut the work off itself.
STOP_WAIT = 120.0
#: The most a setting may ask for.
STOP_WAIT_MOST = 3600.0


def stop_wait_from(setting, default=STOP_WAIT):
    """The wait NM_STOP_WAIT_SECONDS names: a number of seconds from 0 to an hour; anything else is the default."""
    try:
        seconds = float(str(setting).strip())
    except (TypeError, ValueError):
        return default
    return seconds if 0 <= seconds <= STOP_WAIT_MOST else default


def _said(counts) -> str:
    return ", ".join(f"{count} {kind}{'' if count == 1 else 's'}" for kind, count in counts.items())


def stop_in_order(activity, close_steps, *, limit, say, clock=time.monotonic, pause=time.sleep, every=0.1) -> dict:
    """Close the steps (close_steps() -> how many waiting steps are kept for the next start), wait until nothing is held in
    the ledger or limit seconds pass, and say both. Returns what was still held when it stopped waiting: {} for a clean stop."""
    kept = close_steps()
    held = activity.counts()
    say("STOPPING IN ORDER: no new step begins here"
        + (f" ({kept} waiting step{'' if kept == 1 else 's'} kept for the next start)" if kept else "")
        + (f"; waiting up to {limit:g} s for the work at hand: {_said(held)}." if held else "; nothing is at work."))
    if not held:
        return {}
    deadline = clock() + limit
    while not activity.may_stop() and clock() < deadline:
        pause(every)
    left = activity.counts()
    if left:
        say(f"STOPPED WITH WORK AT HAND after {limit:g} s: {_said(left)}. It is taken up at the next start as after any restart: "
            "a step continues where it stopped, and a reading is asked for again.")
    else:
        say("Stopped: the work at hand ended first.")
    return left
