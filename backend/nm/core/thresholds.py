"""The threshold map. D1.

WHY SILENCE IS THE DEFECT
--------------------------
D1's first NEVER is *never leave a threshold silent — silence is not a
not-applicable finding*, and that is the whole shape of this module. An
advocate reading a map with eight rows on it believes the ninth was checked and
found irrelevant. It was not checked.

So the map is BUILT FROM THE COMPLETE LIST and every threshold gets a row.
`for_thread` starts from `Threshold` — the enum — rather than from whatever the
caller happened to assess, so a threshold nobody looked at appears as BLOCKED
with a reason, in the advocate's eye line, instead of not appearing.

That is the same arrangement as the limitation coverage record, and for the
same reason: absence is invisible and a row is not.

RUN BEFORE THE MERITS
---------------------
A threshold disposes of a claim without reaching the merits, so an hour spent
on the theory of a suit that cannot be maintained is an hour spent twice. D1
says it plainly: run this before investing in merits.

NOT A THINNER PIPELINE
-----------------------
A threshold issue gets a cited provision and a computed date, exactly as a
merits issue does. `Answered` requires its `finding`, so a threshold answered
from memory cannot be constructed -- the same rule `Factor` applies to an
extending provision, and for the same reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.core.limitation import Limitation, LimitationState
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


class Threshold(str, Enum):
    """THE COMPLETE LIST. The map is built from this, never from what was done.

    D1 names them, and naming them here is what makes "never leave a threshold
    silent" checkable: a row is generated per member, so a threshold nobody
    assessed is visibly BLOCKED rather than quietly absent.
    """

    JURISDICTION = "jurisdiction"
    FORUM = "forum"
    STANDING = "standing"
    MAINTAINABILITY = "maintainability"
    LIMITATION = "limitation"
    STATUTORY_NOTICE = "statutory_notice"
    VALUATION = "valuation"
    COURT_FEES = "court_fees"
    ARBITRATION_CLAUSE = "arbitration_clause"


class ThresholdState(str, Enum):
    """THREE STATES, and `BLOCKED` is the one that carries the work.

    `NOT_APPLICABLE` is a FINDING -- somebody looked and it does not arise.
    `BLOCKED` is a question. Collapsing them is exactly the silence D1 forbids,
    because the first needs nothing and the second needs an answer.
    """

    ANSWERED = "answered"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"

    @classmethod
    def not_established(cls) -> "ThresholdState":
        """BLOCKED is the escape here, and NOT_APPLICABLE is not.

        Declared rather than inferred because no vocabulary of substrings could
        tell these apart: `not_applicable` READS like an escape and is a
        finding -- somebody looked and it does not arise -- while `blocked`
        reads like a decision and is the gap. Getting that backwards would make
        every unassessed threshold render as one nobody needs to answer.
        """
        return cls.BLOCKED


@refuses_blank_text("finding")
@dataclass(frozen=True)
class ThresholdAnswer:
    """One row of the map. Every row has a reason, whatever its state."""

    threshold: Threshold
    state: ThresholdState
    reason: str
    finding: str = ""
    """The retrieved provision. REQUIRED when ANSWERED -- see `__post_init__`.

    D1 forbids a threshold issue receiving a thinner pipeline than a merits
    issue, and an answer with no citation is thinner by definition.
    """
    expires_on: date | None = None

    def __post_init__(self) -> None:
        if self.state is ThresholdState.ANSWERED and not self.finding.strip():
            raise ValueError(
                f"threshold {self.threshold.value!r} is ANSWERED with no "
                f"provision behind it. D1 forbids a threshold issue receiving "
                f"a thinner pipeline than a merits issue, and an answer from "
                f"memory is thinner by definition.")


@implements("D1")
def for_thread(assessed: dict[Threshold, ThresholdAnswer]) -> tuple[ThresholdAnswer, ...]:
    """The map: ONE ROW PER THRESHOLD, whatever the caller assessed.

    Built from `Threshold` rather than from `assessed`, so a threshold nobody
    looked at appears as BLOCKED with a reason instead of not appearing. An
    advocate reading eight rows believes the ninth was checked.
    """
    return tuple(
        assessed.get(t) or ThresholdAnswer(
            threshold=t, state=ThresholdState.BLOCKED,
            reason="not assessed on this thread — this is a gap in the map, "
                   "not a finding that it does not arise")
        for t in Threshold)


def silent(map_: tuple[ThresholdAnswer, ...]) -> tuple[Threshold, ...]:
    """Thresholds absent from the map entirely. Should always be empty."""
    return tuple(t for t in Threshold if t not in {a.threshold for a in map_})


def absurd(map_: tuple[ThresholdAnswer, ...], chronology: tuple[date, ...],
           ) -> tuple[str, ...]:
    """D1.1. Answers that are arithmetically absurd on the file's own dates.

    The measured counterexample is *a twelve-year clock applied to a one-day-old
    trespass* -- and the absurdity is not the twelve years, which is what
    Article 65 gives. It is that the expiry was computed from an accrual the
    chronology does not contain.

    So the check is against the FILE'S OWN DATES: an expiry earlier than
    everything that has happened, or a period running from before the earliest
    event, is arithmetic about a different matter.
    """
    if not chronology:
        return ()
    earliest, latest = min(chronology), max(chronology)
    out: list[str] = []
    for a in map_:
        if a.state is not ThresholdState.ANSWERED or a.expires_on is None:
            continue
        if a.expires_on < earliest:
            out.append(
                f"{a.threshold.value}: expires {a.expires_on.isoformat()}, "
                f"before the earliest event on the file "
                f"({earliest.isoformat()}). That is arithmetic about a "
                f"different matter.")
        elif a.expires_on < latest:
            out.append(
                f"{a.threshold.value}: expires {a.expires_on.isoformat()}, "
                f"before events the file already records "
                f"({latest.isoformat()}). Either the accrual is wrong or the "
                f"chronology is.")
    return tuple(out)


def from_limitation(lim: Limitation) -> ThresholdAnswer:
    """The limitation row, from the computation rather than beside it.

    Two owners for "is this claim in time" would be the second-copy defect on
    the most consequential question the map asks.
    """
    if lim.state is not LimitationState.COMPUTED or lim.article is None:
        return ThresholdAnswer(
            threshold=Threshold.LIMITATION, state=ThresholdState.BLOCKED,
            reason=lim.not_computed_because or "limitation was not computed")
    return ThresholdAnswer(
        threshold=Threshold.LIMITATION, state=ThresholdState.ANSWERED,
        reason=f"accrual: {lim.accrual_reason}",
        finding=lim.article, expires_on=lim.expires_on)
