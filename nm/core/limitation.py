"""Limitation as a COMPUTED DATE. D2.

WHY A DATE AND NEVER A SENTENCE
--------------------------------
*"Roughly three years from the invoices"* is not an output. An advocate cannot
file against it, cannot advise against it, and cannot tell whether it is right.
A date can be checked; a sentence can only be believed.

So `Limitation` carries `expires_on` and `days_remaining` as fields, and a
computation that cannot produce them is NOT_COMPUTED — a third state — rather
than prose that reads like an answer.

THE INVARIANT, AND IT IS THE ONE THAT WAS MEASURED FAILING
-----------------------------------------------------------
E-042: EVERY CHRONOLOGY ENTRY APPEARS IN THE COVERAGE RECORD. The measured
defect was an acknowledgment in writing on 12 June 2024 that sat in the
chronology, was repeated back to the advocate, and never reached the
arithmetic. The claim was reported time-barred. It was not.

Nothing about that failure was visible: the citation was right, the period was
right, the accrual date was right, and the answer was wrong because one fact in
the chart was never asked about. So `covered` is a record with one row per
chronology entry, each APPLIED or expressly NO_EFFECT, and
`accounts_for_every_entry` refuses a computation that skipped one.

Three states there too. NOT_ASSESSED is what an entry gets when the computation
could not reach it, and it is distinguishable from "considered and irrelevant"
because those call for different next moves.

AN EXTENDING PROVISION IS RETRIEVED, NEVER REMEMBERED
------------------------------------------------------
Acknowledgment, part payment, exclusion, disability, fraud, notice periods,
continuing breach — every one of them is a section, and every one of them is
cited to retrieved text or it does not apply. `Factor.finding` is required by
the type, so a factor asserted from memory cannot be constructed.

THE CALENDAR COUNTS, NOT THE DAYS
----------------------------------
Three years from 15 April 2019 is 15 April 2022, not 1,095 days later. The
difference is one day across a leap year, and one day is the whole of a
limitation argument. `add_years` and `add_months` work on the calendar and
clamp the month end, so 31 January plus one month is 28 February and not 3
March.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.matter import FactId, Side
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements

# ------------------------------------------------------- calendar arithmetic ---


def add_years(on: date, years: int) -> date:
    """The same day, `years` later, by the CALENDAR.

    29 February plus one year is 28 February, because there is no 29 February
    in the following year and the alternative -- 1 March -- would silently
    extend the period by a day. A day is the whole of a limitation argument.
    """
    return _clamped(on.year + years, on.month, on.day)


def add_months(on: date, months: int) -> date:
    """The same day, `months` later, clamped to the month end.

    31 January plus one month is 28 February. Rolling into 3 March would give
    the advocate three days they do not have.
    """
    total = (on.year * 12 + (on.month - 1)) + months
    return _clamped(total // 12, total % 12 + 1, on.day)


def _clamped(year: int, month: int, day: int) -> date:
    last = _DAYS[month] + (1 if month == 2 and _leap(year) else 0)
    return date(year, month, min(day, last))


_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
         7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


# ------------------------------------------------------------------ states ---


class Applied(str, Enum):
    """What the computation did with one chronology entry. THREE STATES.

    `NO_EFFECT` and `NOT_ASSESSED` are the two that get conflated, and they
    call for opposite next moves: the first is an answer, the second is a gap.
    """

    APPLIED = "applied"
    NO_EFFECT = "no_effect"
    NOT_ASSESSED = "not_assessed"


class LimitationState(str, Enum):
    """Whether a date could be produced at all. `NOT_COMPUTED` is the escape."""

    COMPUTED = "computed"
    NOT_COMPUTED = "not_computed"


class FactorKind(str, Enum):
    """What moved the clock. Every one of these is a SECTION, never a memory."""

    ACKNOWLEDGMENT = "acknowledgment"
    PART_PAYMENT = "part_payment"
    EXCLUSION = "exclusion"
    DISABILITY = "disability"
    FRAUD = "fraud"
    NOTICE_PERIOD = "notice_period"
    CONTINUING_BREACH = "continuing_breach"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text()
@dataclass(frozen=True)
class Factor:
    """One thing that extends, restarts or excludes — CITED, never remembered.

    `finding` is a required field with no default, so a factor asserted from
    memory cannot be constructed. D2 forbids it in terms: acknowledgment, part
    payment, exclusion, disability, fraud, notice periods, continuing breach
    and continuing wrongs are each a provision, and each is retrieved or it
    does not apply.
    """

    kind: FactorKind
    fact: FactId
    finding: str
    """The retrieved provision this rests on. Required BY THE TYPE."""
    restarts_from: date | None = None
    adds_days: int = 0


@refuses_blank_text()
@dataclass(frozen=True)
class Entry:
    """One chronology entry, and what the computation did with it.

    THE COVERAGE RECORD. A fact in the chart that never reaches the arithmetic
    is the measured defect this whole record exists to refuse -- and it was
    invisible, because every other part of the answer was right.
    """

    fact: FactId
    applied: Applied
    reason: str


@refuses_blank_text("accrual_reason", "not_computed_because")
@dataclass(frozen=True)
class Limitation:
    """A limitation position: a DATE, a day count, and what it rests on."""

    for_side: Side
    state: LimitationState = LimitationState.NOT_COMPUTED
    article: str | None = None
    """The retrieved Article or section. `None` while NOT_COMPUTED."""
    accrual: FactId | None = None
    accrual_reason: str = ""
    period_years: int = 0
    period_months: int = 0
    period_days: int = 0
    expires_on: date | None = None
    factors: tuple[Factor, ...] = ()
    covered: tuple[Entry, ...] = ()
    not_computed_because: str = ""

    def days_remaining(self, today: date) -> int | None:
        """The count, or None where no date was produced.

        E-043 requires every position to yield a date AND a day count. A
        negative count is the answer where the period has run -- it is not an
        error, and rounding it to zero would hide how far gone the claim is.
        """
        if self.expires_on is None:
            return None
        return (self.expires_on - today).days

    def expired(self, today: date) -> bool | None:
        """THREE STATES: expired, alive, or NOT COMPUTED.

        `None` is the third, and it is why this returns an optional rather than
        a bool: `False` for "we could not compute it" would read as "the claim
        is alive", which is the most expensive false reassurance this product
        could give.
        """
        remaining = self.days_remaining(today)
        return None if remaining is None else remaining < 0

    def accounts_for_every_entry(self, chronology: tuple[FactId, ...]) -> tuple[FactId, ...]:
        """E-042. The chronology entries this computation never reached.

        Returns the gap rather than a boolean, so the caller can name what was
        missed. The measured defect was ONE acknowledgment, in the chart,
        absent from the arithmetic -- and a boolean would have said `False`
        without saying which.
        """
        seen = {e.fact for e in self.covered
                if e.applied is not Applied.NOT_ASSESSED}
        return tuple(f for f in chronology if f not in seen)


#: Statutes write periods in words far more often than in figures, and the
#: Limitation Act's Schedule writes them in words throughout.
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirty": 30, "sixty": 60, "ninety": 90,
}
_PERIOD = re.compile(
    r"\b(\d{1,3}|" + "|".join(_WORDS) + r")\s+(year|month|day)s?\b", re.I)


@refuses_blank_text()
@dataclass(frozen=True)
class Period:
    """A period, AND THE RETRIEVED TEXT IT WAS READ OUT OF.

    The span is required by the type and verified against the numbers, so a
    period the product invented cannot be constructed -- which is the same
    mechanism `Factor.finding` uses to refuse an extending provision asserted
    from memory, and it is here for the same reason.

    Making it a type rather than three integers is what closes the hole.
    `compute(years=3)` was reachable from anywhere and read as ordinary Python;
    `compute(period=Period(3, 0, 0, "..."))` has to produce a span that really
    says three years, and there is nowhere to get one except retrieval.
    """

    years: int
    months: int
    days: int
    read_from: str

    def __post_init__(self) -> None:
        if not (self.years or self.months or self.days):
            raise ValueError(
                "a period of zero expires on the accrual date, which would "
                "report every claim as barred the day it arose. Where no "
                "period could be read, the position is NOT_COMPUTED.")
        if min(self.years, self.months, self.days) < 0:
            raise ValueError("a limitation period does not run backwards")
        # THE SPAN MUST ACTUALLY SAY IT. Without this the field is decoration:
        # any string would satisfy a required-text check, and an invented
        # period would carry a real-looking citation beside it.
        found = _read(self.read_from)
        if found != (self.years, self.months, self.days):
            raise ValueError(
                f"this period is not what the retrieved text says. The span "
                f"reads {found!r} and the period claims "
                f"{(self.years, self.months, self.days)!r}. A period the "
                f"product supplied itself is the defect that reported a "
                f"twelve-year Article barred after three.")


def _read(span: str) -> tuple[int, int, int] | None:
    """The numbers a span states, with no Period built. One regex, one owner."""
    if not span:
        return None
    m = _PERIOD.search(span)
    if m is None:
        return None
    raw = m.group(1).lower()
    n = _WORDS.get(raw) or int(raw)
    unit = m.group(2).lower()
    return ((n, 0, 0) if unit == "year"
            else (0, n, 0) if unit == "month" else (0, 0, n))


@implements("D2")
def period_in(span: str) -> "Period | None":
    """The period THE RETRIEVED TEXT STATES, or `None`.

    THE PERIOD IS NOT A CONSTANT AND MAY NEVER BE ONE. It was measured being
    one: the engine passed `years=3` into every computation it made, and on a
    turn that retrieved *Article 65 — twelve years* it produced a bar three
    years after accrual and reported the claim dead. Every citation on that
    turn was correct. The Article was correct. The accrual date was correct.
    The answer was wrong by nine years, and nothing in the output showed which
    part had been invented, because the invented part looked exactly like the
    retrieved part.

    That is the same defect as asserting an extending provision from memory,
    which `Factor.finding` already refuses by type -- so it gets the same
    answer. The period comes out of the span, or it does not come at all and
    the position is NOT_COMPUTED with the reason.

    `None` is the third state and it is not failure: an Article whose text this
    could not read is ordinary, and it must be distinguishable from a period of
    zero, which `Period` refuses outright.
    """
    found = _read(span)
    return None if found is None else Period(*found, read_from=span)


@implements("D2")
def compute(for_side: Side, article: str, accrual: FactId, accrual_on: date,
            accrual_reason: str, chronology: tuple[FactId, ...],
            period: Period,
            factors: tuple[Factor, ...] = (),
            considered: dict[FactId, str] | None = None) -> Limitation:
    """Compute the position, and account for EVERY entry in the chronology.

    `period` IS A TYPE AND NOT THREE INTEGERS. It carries the retrieved span it
    was read out of and verifies itself against it, so there is no signature
    here through which a period the product invented can reach the arithmetic.
    It was three integers with defaults of zero, and the engine passed
    `years=3` into every computation it made -- including one that had just
    retrieved Article 65 and its twelve years.

    `considered` names the entries the caller examined and found to have no
    effect, with the reason. Anything in the chronology that is neither applied
    nor considered lands as NOT_ASSESSED -- visibly, in the record -- rather
    than being silently absent, which is how the acknowledgment was lost.
    """
    considered = considered or {}
    years, months, days = period.years, period.months, period.days

    # THE CALENDAR, NOT THE DAYS. Years and months first so that clamping
    # happens once, at the month end, rather than compounding.
    on = accrual_on
    if years:
        on = add_years(on, years)
    if months:
        on = add_months(on, months)
    if days:
        from datetime import timedelta
        on = on + timedelta(days=days)

    applied_facts = {f.fact for f in factors}
    for f in factors:
        if f.restarts_from is not None:
            # A RESTART recomputes from the new date -- it does not add to the
            # old expiry. Adding would give a period longer than the statute
            # allows, which is the error that favours our own client.
            on = f.restarts_from
            if years:
                on = add_years(on, years)
            if months:
                on = add_months(on, months)
    for f in factors:
        if f.adds_days:
            from datetime import timedelta
            on = on + timedelta(days=f.adds_days)

    rows: list[Entry] = []
    for fid in chronology:
        if fid == accrual:
            # THE ACCRUAL EVENT IS APPLIED. It is the fact the clock runs FROM,
            # and leaving it unaccounted made the record report a gap where the
            # computation's own foundation sat -- which would have taught the
            # reader to ignore the record.
            rows.append(Entry(fid, Applied.APPLIED,
                              f"accrual — {accrual_reason}"))
        elif fid in applied_facts:
            kind = next(f.kind for f in factors if f.fact == fid)
            rows.append(Entry(fid, Applied.APPLIED,
                              f"{kind.value} — moves the clock"))
        elif fid in considered:
            rows.append(Entry(fid, Applied.NO_EFFECT, considered[fid]))
        else:
            # NOT ASSESSED, and SAID SO. This row is the whole point of the
            # record: the acknowledgment that was lost would appear here.
            rows.append(Entry(fid, Applied.NOT_ASSESSED,
                              "this entry was not examined against the period"))

    return Limitation(
        for_side=for_side, state=LimitationState.COMPUTED, article=article,
        accrual=accrual, accrual_reason=accrual_reason,
        period_years=years, period_months=months, period_days=days,
        expires_on=on, factors=factors, covered=tuple(rows))


def not_computed(for_side: Side, because: str,
                 chronology: tuple[FactId, ...] = ()) -> Limitation:
    """No date could be produced, and the reason is carried.

    Not an error path. An Article that could not be retrieved, an accrual event
    the advocate has not given, a period the corpus does not hold -- all
    ordinary, and all of them must be distinguishable from "the claim is
    alive", which is what a bare absence would read as.
    """
    return Limitation(
        for_side=for_side, state=LimitationState.NOT_COMPUTED,
        not_computed_because=because,
        covered=tuple(Entry(f, Applied.NOT_ASSESSED,
                            "no computation was made on this thread")
                      for f in chronology))
