"""THE CLOCKS THAT RUN INSIDE A PROCEEDING: the shapes. LB-124.

THE DEFECT THIS REFUSES. Limitation decides whether a claim can be brought at
all, and it is the only clock this product computed. A proceeding has others,
and losing one loses the defence rather than the claim: the written statement,
leave to defend a summary suit, the life of a caveat. An advocate who reads a
limitation position and nothing else has been told about the clock that is
least likely to be the one about to run out.

TWO THINGS ARE SAID ABOUT EVERY PERIOD AND THEY ARE NOT THE SAME. Whether it
BINDS -- mandatory or directory -- and whether it can be EXTENDED. They travel
together and are separate fields, because the pair is what the advocate acts
on: a directory period read as mandatory panics them, and a mandatory one read
as extendable loses the defence outright.

THE TRACK IS PART OF THE KEY, NOT A REFINEMENT OF THE ANSWER. The same rule
reads differently on a commercial suit and on an ordinary one, and the
difference is the whole of the row. So a period that belongs to one track is
UNDECIDED until the track is established -- never answered on the ordinary
reading because nobody said it was commercial. That is the `ActBasis.INFERRED`
discipline CLAUDE.md section 5 records, applied to a clock.

THE TABLE IS NOT HERE. `backend/nm/knowledge/procedural_period.py` holds the
curated periods and `backend/nm/adapters/knowledge/procedural_period.py` serves
them -- the split the elements, pre-institution, governing-law and interim
planes already use.

WHAT THIS SLICE DOES NOT DO. It does not COMPUTE a due date. Every period runs
from a trigger -- service, an order, a listing -- and whether that trigger
happened, and when, is a fact about the advocate's own file that nothing here
reads. So each engaged period reaches the register with no date, naming the
trigger that would compute it. A date guessed from a period nobody triggered is
the defect the deadline register already refuses (`NOT_COMPUTED`), and this
does not reintroduce it one door down.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from nm.domain.matter import Role
from nm.domain.text import refuses_blank_text


class Track(str, Enum):
    """WHICH READING OF THE RULE APPLIES. Stated, never inferred.

    A closed vocabulary for the reason `CauseOfAction` is closed: the
    alternative is deciding from the words of a brief whether a suit is
    commercial, and that decision changes a directory period into a mandatory
    one with no route back.
    """

    COMMERCIAL = "commercial"
    ORDINARY = "ordinary"
    NOT_ESTABLISHED = "not_established"

    @classmethod
    def not_established(cls) -> "Track":
        return cls.NOT_ESTABLISHED


class Bindingness(str, Enum):
    """Whether the period BINDS, or is a direction the court may relax.

    `NOT_RECORDED` is a gap in what is curated, not a finding that the period
    is directory. The two send an advocate in opposite directions.
    """

    MANDATORY = "mandatory"
    DIRECTORY = "directory"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Bindingness":
        return cls.NOT_RECORDED


class Extension(str, Enum):
    """Whether the period can be extended once it has run.

    Kept apart from `Bindingness` because the two are genuinely separate
    questions and collapsing them is how "mandatory" comes to be read as "and
    therefore nothing can be done" -- or, worse, the reverse.
    """

    AVAILABLE = "available"
    BARRED = "barred"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Extension":
        return cls.NOT_RECORDED


@refuses_blank_text()
@dataclass(frozen=True)
class Period:
    """One clock that runs inside a proceeding, and where it came from."""

    key: str
    said: str
    """What the period is, in the words an advocate uses for it."""
    act: str
    provision: str
    """The store's own key for the provision, never prose -- a row that wrote
    "Order VIII rule 1 CPC" would look up nothing and report a gap in a Code
    held in full (B-163)."""
    curated_from: str
    runs_from: str
    """THE TRIGGER, named as an event and never as a date. What starts this
    clock is a fact about the advocate's file; naming it is what lets them
    supply it in one line."""
    period_said: str
    """What the provision fixes, pointed at rather than computed. No row states
    a number of days: a period recited from memory is the defect this whole
    table exists to refuse."""
    bindingness: Bindingness = Bindingness.NOT_RECORDED
    extension: Extension = Extension.NOT_RECORDED
    extension_said: str = ""
    """The route by which it may be extended, or why none is open."""
    track: Track = Track.NOT_ESTABLISHED
    """`NOT_ESTABLISHED` here means the period reads the SAME on both tracks,
    so it is engaged whatever the track. It does NOT mean the track is
    unknown -- that is a question about the matter, and `undecided` answers
    it."""


@refuses_blank_text()
@dataclass(frozen=True)
class Running:
    """One period this matter engages, and what brought it into play."""

    period: Period
    why: str


class ProceduralPeriodPort(Protocol):
    """The knowledge plane, asked which clocks run in this proceeding."""

    def engaged(self, role: Role, track: Track) -> tuple[Running, ...]: ...

    def undecided(self, role: Role, track: Track) -> tuple[Period, ...]: ...


__all__ = ["Track", "Bindingness", "Extension", "Period", "Running",
           "ProceduralPeriodPort"]
