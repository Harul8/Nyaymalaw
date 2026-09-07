"""BK-20 / BK-18 — how many wrong answers a door accepts before it stops.

WHY IT IS TWO COUNTERS AND NOT ONE
------------------------------------
They defend different things and one does not imply the other.

    per ADVOCATE   guessing the password of ONE known account
    per SOURCE     sweeping MANY addresses from one place -- which is the
                   enumeration this pairs with

Limiting only per advocate leaves enumeration untouched: a sweep tries each
address once, never trips a per-account counter, and walks the whole
directory. Limiting only per source leaves a distributed guess at one account
untouched. The product needed both the day sign-in started naming which of
three things failed, and it had neither.

WHY THE ADVOCATE IS TOLD WHEN, NOT JUST NO
--------------------------------------------
"Too many attempts" with no time on it is a wall. A locked-out advocate with a
hearing tomorrow needs to know whether the answer is four minutes or four
hours, and an attacker learns nothing from a number they can measure with a
clock anyway.

FAILING OPEN IS THE RIGHT DIRECTION AND MUST BE VISIBLE
--------------------------------------------------------
If the attempt log cannot be read or written, this cannot enforce. Refusing
every sign-in would be a self-inflicted outage on a product an advocate uses
under time pressure; allowing them silently is the S1 shape -- a control that
could not run returning the shape of a clean result.

So it fails OPEN and says so: `readiness()` reports rate limiting as NOT
RUNNING, which is the third state the operator sees before an incident rather
than during one.

NOT A LOCKOUT
---------------
Nothing is disabled and no state is set on the account. The window simply
passes. A real lockout hands an attacker a denial-of-service: send five wrong
passwords for an advocate's address and they cannot work.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: Wrong answers allowed for ONE address before that address pauses.
#:
#: Five is enough that an advocate who genuinely mistypes -- caps lock, an old
#: password, a keyboard layout -- is not stopped, and few enough that guessing
#: is hopeless. The number matters far less than the window.
PER_ADVOCATE = 5

#: Wrong answers allowed from ONE SOURCE across ALL addresses.
#:
#: Deliberately larger and deliberately still finite. A chambers behind one
#: address does share a source, and three advocates each mistyping twice must
#: not stop the fourth. Twenty makes a directory sweep useless while leaving
#: ordinary shared use alone.
PER_SOURCE = 20

#: How far back the count reaches, and therefore how long a pause lasts.
WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class Verdict:
    """Whether the door opens, and if not, when it will."""

    allowed: bool
    retry_after: timedelta | None = None
    because: str = ""

    @property
    def said(self) -> str:
        """What the advocate is told. Empty when they are let through."""
        if self.allowed:
            return ""
        seconds = int((self.retry_after or timedelta()).total_seconds())
        when = (f"{seconds // 60 + 1} minute(s)" if seconds >= 60
                else f"{max(seconds, 1)} second(s)")
        return (f"Too many failed sign-in attempts {self.because}. "
                f"Try again in about {when}. Nothing is locked and no account "
                f"has been changed -- the count simply ages out.")


def verdict(advocate_failures: tuple[datetime, ...],
            source_failures: tuple[datetime, ...],
            now: datetime) -> Verdict:
    """Whether this attempt may proceed.

    TIMES IN, VERDICT OUT. No store, no clock of its own, no I/O -- so the
    policy can be exercised at any moment in any order, which is the only way
    to test a window without waiting fifteen minutes.
    """
    for times, limit, because in (
            (advocate_failures, PER_ADVOCATE, "for this email address"),
            (source_failures, PER_SOURCE, "from this connection")):
        recent = sorted(t for t in times if now - t < WINDOW)
        if len(recent) >= limit:
            # THE OLDEST ATTEMPT IN THE WINDOW is what has to age out before
            # one slot frees. Counting from the newest would extend the pause
            # every time the attacker knocked -- and would extend it for the
            # advocate too, who is the one actually reading the message.
            frees_at = recent[0] + WINDOW
            return Verdict(allowed=False, retry_after=max(frees_at - now,
                                                          timedelta(seconds=1)),
                           because=because)
    return Verdict(allowed=True)
