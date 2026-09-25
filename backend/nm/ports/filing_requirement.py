"""WHETHER A FILING WILL BE ACCEPTED: forum, valuation and court fee. LB-125.

THE DEFECT THIS REFUSES, AND IT IS NOT THE ONE THE ROW WAS DRAFTED AGAINST.
`jurisdiction`, `forum`, `valuation` and `court_fees` have been declared
thresholds since D1, and on every turn each answered BLOCKED with the map's
generic sentence -- *not assessed on this thread* -- because nothing assessed
them. An advocate reading that learned nothing they could act on and, worse,
could not tell it apart from a threshold that had been looked at.

WHY THIS SHIPS AS AN HONEST "NOT ASSESSED" AND NOT AS A FEE CALCULATOR.
Computing a court fee needs the schedule in force, and the schedule has to be
held AND VERSIONED, because a fee computed from last year's schedule is wrong
in a way that reads exactly like right. Measured on 25 September 2026 against
`pipeline/manifest.yaml`, the intended-coverage assertion: no court-fees and
suits valuation Act and no civil courts Act is among the 22 entries. So the fee
is not computed, and that is the whole of the answer this row can honestly give
today.

    A MEASURED GAP, NAMED, IS A DELIVERABLE. An estimate is not.

AND THE GAP IS MEASURED, NOT ASSERTED. `backend/nm/knowledge/filing_requirement.py`
reads the manifest at turn time and says what is missing by TITLE. Writing
"the Telangana schedule is not held" into the code would be a claim about the
filesystem that nothing compares to the filesystem, which is exactly B-141 --
a backlog row saying the authority index had never run while it sat on disk.
The day the Act is ingested, this answers differently with no edit.

THE FOUR STATES, AND WHY `NOT_MEASURED` IS ONE OF THEM. An installation with
no manifest cannot say whether the schedule is held. That is not "not held",
and it is emphatically not "held": it is the third state CLAUDE.md section 9
requires, and it is visible in the output rather than only in the type. It
exits the way a release criterion nobody computed exits -- as a failure to
know, not as a pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from nm.domain.text import refuses_blank_text


class Requirement(str, Enum):
    """What must be settled before a filing can be recommended.

    The three that decide whether the filing is ACCEPTED, kept apart because
    they fail separately: the right court with the wrong fee is refused at the
    counter, and the right fee in the wrong court is refused by the judge.
    """

    FORUM = "forum"
    VALUATION = "valuation"
    COURT_FEES = "court_fees"


class SourceState(str, Enum):
    """Whether the authority that would answer the requirement can be read.

    `HELD_UNVERSIONED` IS NOT A WEAKER `HELD`. A schedule whose version is
    unknown computes a figure that may be a revision out of date, and there is
    nothing in the figure to say so. It is treated as not computable, and the
    separate state exists so the advocate is told which of the two is wrong --
    the Act is missing, or its version is.
    """

    HELD_AND_VERSIONED = "held_and_versioned"
    HELD_UNVERSIONED = "held_unversioned"
    NOT_INTENDED = "not_intended"
    """The manifest -- the CURATED assertion of intended coverage -- carries no
    entry for it. That makes the absence VISIBLE, which a generated inventory
    never could: absence leaves no trace to enumerate."""
    NOT_MEASURED = "not_measured"
    """Nothing could be asked. Never collapsed into `NOT_INTENDED`."""


@refuses_blank_text()
@dataclass(frozen=True)
class Authority:
    """One instrument that would answer one requirement."""

    requirement: Requirement
    act_name: str
    """THE TITLE, EXACTLY. Matched against the manifest by exact title and
    never by overlap -- CLAUDE.md section 5 measured three wrong Acts in one
    hour from shared words, and a wrong Act here decides the fee."""
    what_it_would_answer: str
    curated_from: str


@refuses_blank_text("why")
@dataclass(frozen=True)
class Readiness:
    """Whether a requirement can be answered at all, and what is in the way."""

    requirement: Requirement
    state: SourceState = SourceState.NOT_MEASURED
    why: str = ""
    missing: tuple[str, ...] = field(default_factory=tuple)
    """The titles that would have to be held. Named so the advocate reads a
    gap they can close -- or hand to the person who maintains the corpus --
    rather than a refusal they cannot act on."""

    @property
    def computable(self) -> bool:
        """ONLY the fully versioned state computes anything. Three of the four
        are reasons not to, and none of them is allowed to read like a
        figure."""
        return self.state is SourceState.HELD_AND_VERSIONED


class FilingRequirementPort(Protocol):
    """The knowledge plane, asked whether a filing requirement can be read."""

    def readiness(self, requirement: Requirement) -> Readiness: ...


__all__ = ["Requirement", "SourceState", "Authority", "Readiness",
           "FilingRequirementPort"]
