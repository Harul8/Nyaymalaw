"""WHICH DAY IS IT, and whose day. BK-14.

`nm/edge/api.py` took `today=req.today or date.today()`, and `web/app.js`
never sends `today` -- measured 7 September 2026, grep returns nothing. So
every served turn dated itself by whatever clock the server happened to keep,
and nothing in `nm/` mentioned a timezone at all.

WHY THAT IS A LIMITATION DEFECT AND NOT A COSMETIC ONE
--------------------------------------------------------
`today` reaches `limitation.days_remaining` (`expires_on - today`),
`Deadline.status`, `deadlines.passed`, `deadlines.upcoming`, and
`ours.expired(turn.today)` -- the branch deciding whether the salvage pass
runs at all. A limitation date is the most consequential number this product
produces.

A server keeping UTC is on the PREVIOUS DAY from 18:30 UTC onward, which is
00:00 to 05:30 in India. A turn taken in that window computes every period one
day short, and a claim that expired today reads as expiring tomorrow. Silently:
there was no third state for "which day is it", because the question had never
been asked.

AND EVERY TEST WAS BLIND TO IT BY CONSTRUCTION -- each suite passes
`today=date(2026, 9, 4)` explicitly, so the default path no test exercises is
the only path production uses.

A FIXED OFFSET, NOT `ZoneInfo`
--------------------------------
India is a single timezone at UTC+5:30 with no daylight saving, unchanged
since 1945. A fixed offset is therefore EXACTLY right, and it avoids depending
on the system tz database -- which is absent on Windows without `tzdata`, so
`ZoneInfo("Asia/Kolkata")` would raise on some machines and work on others.
A clock that is correct on the developer's laptop and raises in production is
worse than no clock.

The day this product serves a jurisdiction that observes DST, this becomes a
lookup and the offset becomes wrong -- so `FORUM` names the jurisdiction it is
the offset FOR, rather than pretending to be universal.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

#: The forum this product serves. CLAUDE.md: the corpus is scoped to Telangana
#: and the Union of India, and an answer about another state's law is
#: confidently wrong with nothing downstream to catch it.
FORUM = "Telangana"

#: UTC+5:30. Not a guess and not an approximation: India Standard Time has one
#: offset, no DST, and has not moved since 1945.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def today(now: datetime | None = None) -> date:
    """The date AT THE FORUM, which is the only date a limitation runs against.

    `now` is injectable so a test can drive the boundary rather than assert
    around it. The default reads the wall clock ONCE, in UTC, and converts --
    rather than calling `date.today()`, which silently means "the date where
    this process happens to be running".
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        # A NAIVE DATETIME CANNOT BE CONVERTED, ONLY ASSUMED. Assuming UTC is
        # the conventional guess and it is still a guess, so it is made here,
        # once, where it can be read -- rather than at four call sites that
        # each decide differently.
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(IST).date()


def describe() -> str:
    """What the product will tell an advocate about its own clock.

    A date the advocate cannot check is one they cannot correct. This is the
    sentence that makes `today` visible rather than assumed -- §9's third state
    applied to a question that previously had one silent answer.
    """
    return (f"Dates are computed at {IST!s} ({FORUM}), not on the server's "
            f"clock. Today is {today().isoformat()}.")
