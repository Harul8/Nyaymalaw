"""D3 — the deadline register, and its three NEVER clauses.

E-046's counterexample is the sharp one: *a comparison order that makes `near`
unreachable, so nothing is ever urgent.* A register whose middle state cannot
be reached reports a file with no urgency on it, forever, and reads exactly
like a file with nothing pressing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from nm.core.deadlines import (
    NEAR_WITHIN,
    Deadline,
    DeadlineKind,
    DeadlineStatus,
    nearest_thread,
    passed,
    register,
    upcoming,
)
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)


def _d(days: int | None, thread: str = "thr_1", **kw) -> Deadline:
    base = dict(thread=thread, kind=DeadlineKind.LIMITATION,
                source="Limitation Act, 1963 Article 65",
                action="file the suit", owner="the advocate",
                consequence="the claim is barred")
    base.update(kw)
    on = None if days is None else TODAY + timedelta(days=days)
    return Deadline(on=on, **base)


# ================================= E-046 — every status is reachable =========


@pytest.mark.eval_id("E-046")
def test_a_deadline_can_reach_every_status_including_near():
    """E-046's counterexample: *a comparison order that makes `near`
    unreachable, so nothing is ever urgent.*

    A middle state that cannot be reached is not a state. The register would
    report a file with no urgency on it forever, and that reads exactly like a
    file with nothing pressing on it.
    """
    reached = {_d(days).status(TODAY)
               for days in (-400, -1, 0, 1, 29, 30, 31, 400)}
    reached.add(_d(None).status(TODAY))

    assert reached == set(DeadlineStatus), (
        f"only {sorted(s.value for s in reached)} are reachable. A status no "
        f"deadline can hold is not a status.")

    # THE BOUNDARIES, named rather than assumed.
    assert _d(-1).status(TODAY) is DeadlineStatus.PASSED
    assert _d(0).status(TODAY) is DeadlineStatus.NEAR, (
        "a deadline due TODAY is near, not passed — the day is not over")
    assert _d(NEAR_WITHIN.days).status(TODAY) is DeadlineStatus.NEAR
    assert _d(NEAR_WITHIN.days + 1).status(TODAY) is DeadlineStatus.FUTURE


@refuses("D3", 2)
@pytest.mark.eval_id("E-046")
def test_status_is_recomputed_and_never_stored():
    """D3: *Never store deadline status. It is recomputed, because a stored
    value cannot detect its own category transition.*

    `future` written on Tuesday is still `future` on the Friday it passes. The
    board is right only until it is wrong, and nothing wakes up to say so.
    """
    import dataclasses

    assert "status" not in {f.name for f in dataclasses.fields(Deadline)}, (
        "status is a stored field. It cannot detect its own transition.")

    # ONE deadline, THREE answers, depending only on when you ask.
    d = _d(10)
    assert d.status(TODAY) is DeadlineStatus.NEAR
    assert d.status(TODAY - timedelta(days=60)) is DeadlineStatus.FUTURE
    assert d.status(TODAY + timedelta(days=30)) is DeadlineStatus.PASSED


# ============================ D3.0 — a passed deadline is reported ==========


@refuses("D3", 0)
@pytest.mark.eval_id("E-046")
def test_a_passed_deadline_is_reported_as_passed_and_never_dropped():
    """D3: *Never quietly drop a passed deadline.*

    Dropping it tells the advocate there was never a deadline. It is frequently
    the most important row on the file, because it is where the
    relief-from-delay application lives — and it carries its consequence, or it
    tells them nothing they can act on.
    """
    gone = _d(-240, action="apply under s.5 for condonation")
    live = _d(10)
    rows = register((live, gone), TODAY)

    assert gone in rows, "a passed deadline was dropped from the register"
    assert rows[0] is gone, (
        "the passed deadline is not first. What can be done about it shrinks "
        "every day; the live one will still be there tomorrow.")
    assert gone.consequence, "a passed deadline with no consequence says nothing"
    assert gone.days(TODAY) == -240


@refuses("D3", 1)
@pytest.mark.eval_id("E-046")
def test_a_passed_action_is_never_listed_among_what_will_not_wait():
    """D3: *Never list an action due eight months ago under "these will not
    wait".*

    It buries the thing that can no longer be done among the things that still
    can, and the advocate scans the second list for work.
    """
    gone = _d(-240)
    soon = _d(3)
    far = _d(200)

    ahead = upcoming((gone, soon, far), TODAY)
    assert gone not in ahead, (
        "an action eight months overdue was listed as upcoming")
    assert [d.days(TODAY) for d in ahead] == [3, 200], "not nearest first"

    behind = passed((gone, soon, far), TODAY)
    assert behind == (gone,)

    # AND NEITHER LIST SILENTLY LOSES A ROW. Together they account for
    # everything that has a date.
    assert len(ahead) + len(behind) == 3


def test_a_deadline_with_no_computable_date_stays_on_the_register():
    """A known obligation with an unknown date is a QUESTION, not an absence.

    Leaving it off tells the advocate there is no deadline, which is the
    opposite of what is known — the same shape as an unreadable matter
    vanishing from the list (B-053).
    """
    unknown = _d(None, action="the appeal period runs from service, date unknown")
    rows = register((unknown, _d(5)), TODAY)
    assert unknown in rows
    assert unknown.status(TODAY) is DeadlineStatus.NOT_COMPUTED
    assert rows[-1] is unknown, "an uncomputed deadline should sort last"
    # It is in NEITHER list, because it is neither — and that is why it has its
    # own status rather than being forced into one of the two.
    assert unknown not in upcoming((unknown,), TODAY)
    assert unknown not in passed((unknown,), TODAY)


# ======================= the nearest deadline orders the file ===============


@pytest.mark.eval_id("E-046")
def test_the_thread_carrying_the_nearest_deadline_is_addressed_first():
    """D3: *Where several threads are live, the thread carrying the nearest
    deadline is addressed first, regardless of which is legally the most
    interesting.*

    An ordering rule, not a ranking of importance. The interesting thread will
    still be interesting next week; the one expiring on Friday will not.
    """
    assert nearest_thread((_d(200, "thr_slow"), _d(4, "thr_urgent")),
                          TODAY) == "thr_urgent"

    # A PASSED deadline outranks a live one.
    assert nearest_thread((_d(4, "thr_urgent"), _d(-9, "thr_overdue")),
                          TODAY) == "thr_overdue"

    # And an uncomputed date does not jump the queue over a real one.
    assert nearest_thread((_d(None, "thr_unknown"), _d(90, "thr_dated")),
                          TODAY) == "thr_dated"
    assert nearest_thread((), TODAY) is None


def test_a_deadline_cannot_be_built_without_what_makes_it_actionable():
    """A row with no action, owner, source or consequence is a date on a page.

    The advocate cannot act on it and cannot tell whether it applies to them,
    so the type refuses it rather than the board rendering a blank.
    """
    for missing in ("action", "owner", "consequence", "source"):
        kw = dict(thread="thr_1", kind=DeadlineKind.APPEAL, source="s.96 CPC",
                  action="file the appeal", owner="the advocate",
                  consequence="the decree becomes final", on=TODAY)
        kw[missing] = "   "
        with pytest.raises(ValueError):
            Deadline(**kw)
