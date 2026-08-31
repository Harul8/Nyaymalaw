"""The deadline register. D3, tenet 29.

WHY STATUS IS DERIVED AND NEVER STORED
---------------------------------------
D3 says it in terms: *never store deadline status. It is recomputed, because a
stored value cannot detect its own category transition.* A deadline stored as
`future` on Tuesday is still `future` on the Friday it passes, and nothing
wakes up to say otherwise. The advocate reads a board that was right when it
was written.

So `status` is a method taking `today`, exactly as `Posture.side` is derived
from `role` — the two would drift, and the drift is silent.

A PASSED DEADLINE IS REPORTED AS PASSED
----------------------------------------
Not dropped, not filed under what is upcoming. D3 forbids both, and they are
different mistakes: dropping it tells the advocate there was never a deadline,
and filing it under "these will not wait" buries the one thing they can no
longer do among the things they still can.

A passed deadline is frequently the most important row on the file, because it
is where the relief-from-delay application lives.

THE NEAREST DEADLINE ORDERS THE FILE
-------------------------------------
Where several threads are live, the one carrying the nearest deadline is
addressed first, regardless of which is legally the most interesting. That is
an ordering rule and not a ranking of importance -- the interesting thread will
still be there next week, and the one expiring on Friday will not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from nm.domain.matter import ThreadId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements

#: How near is NEAR. Authored once, here, so the board and the answer cannot
#: disagree about which deadlines are urgent -- two definitions of urgency is
#: the same defect as two definitions of anything else.
NEAR_WITHIN = timedelta(days=30)


class DeadlineStatus(str, Enum):
    """THREE LIVE STATES plus the escape.

    `NOT_COMPUTED` is not decoration: a deadline whose date could not be
    established still belongs on the register, saying so. Leaving it off would
    tell the advocate there is no deadline, which is the opposite of what is
    known.
    """

    FUTURE = "future"
    NEAR = "near"
    PASSED = "passed"
    NOT_COMPUTED = "not_computed"


class DeadlineKind(str, Enum):
    LIMITATION = "limitation"
    STATUTORY_NOTICE = "statutory_notice"
    APPEAL = "appeal"
    REVISION = "revision"
    OBJECTION = "objection"
    LISTED_HEARING = "listed_hearing"
    UNDERTAKING = "undertaking"
    OTHER = "other"


@refuses_blank_text()
@dataclass(frozen=True)
class Deadline:
    """One dated obligation. STATUS IS NOT A FIELD.

    EVERY TEXT FIELD HERE IS REQUIRED, and the first draft of this type had
    three of them defaulting to `""` and exempted from the blank check. That
    would have let the board render a dated row with no action, no owner and no
    consequence -- a date on a page the advocate can neither act on nor tell
    applies to them. Appendix E lists all of them, and a default was me
    deciding otherwise on behalf of every call site that forgets.

    `on` may be None: a deadline known to exist whose date could not be
    computed is still a deadline, and `NOT_COMPUTED` says so rather than the
    row being absent.
    """

    thread: ThreadId
    kind: DeadlineKind
    source: str
    """What imposes it -- the Article, the section, the listing."""
    action: str
    """What to do about it. A deadline with no action is a date on a page."""
    owner: str
    """Who does it. Unowned work is not scheduled work."""
    consequence: str
    """What happens if it passes. A passed deadline with no consequence tells
    the advocate nothing they can act on."""
    on: date | None = None

    def status(self, today: date) -> DeadlineStatus:
        """Recomputed every time. NEVER stored.

        A stored status cannot detect its own transition: `future` written on
        Tuesday is still `future` on the Friday it passes, and the board is
        right only until it is wrong.
        """
        if self.on is None:
            return DeadlineStatus.NOT_COMPUTED
        if self.on < today:
            return DeadlineStatus.PASSED
        if self.on - today <= NEAR_WITHIN:
            return DeadlineStatus.NEAR
        return DeadlineStatus.FUTURE

    def days(self, today: date) -> int | None:
        return None if self.on is None else (self.on - today).days


@implements("D3")
def register(deadlines: tuple[Deadline, ...], today: date) -> tuple[Deadline, ...]:
    """Every deadline on the file, NEAREST FIRST — and the passed ones kept.

    Ordering: passed first (they are the most urgent thing on the file, because
    what can be done about them shrinks daily), then by date. An uncomputed
    deadline sorts last and is still present -- it is a known obligation with
    an unknown date, which is a question to ask rather than a row to drop.
    """
    def key(d: Deadline) -> tuple[int, date]:
        status = d.status(today)
        if status is DeadlineStatus.PASSED:
            return (0, d.on or date.max)
        if status is DeadlineStatus.NOT_COMPUTED:
            return (2, date.max)
        return (1, d.on or date.max)

    return tuple(sorted(deadlines, key=key))


def passed(deadlines: tuple[Deadline, ...], today: date) -> tuple[Deadline, ...]:
    """The ones that have gone. Never merged into the upcoming list.

    D3 forbids listing an action due eight months ago under "these will not
    wait" -- it buries the thing that can no longer be done among the things
    that still can, and the advocate scans the second list for work.
    """
    return tuple(d for d in deadlines
                 if d.status(today) is DeadlineStatus.PASSED)


def upcoming(deadlines: tuple[Deadline, ...], today: date) -> tuple[Deadline, ...]:
    """What has not gone yet, nearest first. Passed rows are NOT here."""
    live = tuple(d for d in deadlines
                 if d.status(today) in (DeadlineStatus.FUTURE, DeadlineStatus.NEAR))
    return tuple(sorted(live, key=lambda d: d.on or date.max))


def nearest_thread(deadlines: tuple[Deadline, ...], today: date) -> ThreadId | None:
    """The thread addressed first when several are live.

    A PASSED deadline outranks a future one: what can be done about it shrinks
    every day, and the interesting thread will still be interesting next week.
    """
    ordered = register(deadlines, today)
    for d in ordered:
        if d.status(today) is not DeadlineStatus.NOT_COMPUTED:
            return d.thread
    return ordered[0].thread if ordered else None
