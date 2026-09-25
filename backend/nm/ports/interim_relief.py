"""INTERIM RELIEF IS DECIDED ON ITS OWN TEST: the shapes. LB-123.

THE DEFECT THIS REFUSES. An application for an interim injunction or a stay is
not decided on whether the suit will ultimately succeed. It has its own test,
and the test differs by the relief sought -- a mandatory injunction is not
granted on the same showing as a prohibitory one. A product that answered "your
claim looks strong" to "can I get an injunction on Monday" would be answering a
different question with a confident voice.

SO THE INTERIM POSITION IS KEPT APART FROM THE MERITS, structurally. `Test`
names the limbs; `nm.core.relief` continues to answer whether the FINAL relief
is available, valuable, timely and enforceable. Neither is derived from the
other, and `LB-123` forbids inferring either direction.

THE TABLE IS NOT HERE. `backend/nm/knowledge/interim_relief.py` holds the curated
tests and `backend/nm/adapters/knowledge/interim_relief.py` serves them -- the split
the elements, pre-institution and governing-law planes already use.

WHAT THIS SLICE DOES NOT DO. It does not assess whether the FACTS satisfy a
limb. That is a question about the advocate's own material which nothing here
reads, so every limb comes back `NOT_ASSESSED` -- named, with what would answer
it, rather than silent. An interim assessment nobody made must never read as
one that was made and came out weak.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from nm.domain.text import refuses_blank_text


class InterimRelief(str, Enum):
    """The interim relief SOUGHT. A closed vocabulary, stated never inferred.

    Closed for the reason `CauseOfAction` is closed: the alternative is
    matching a pleading's words approximately, and an approximate match here
    decides which threshold an application is measured against.

    `NOT_STATED` is a value and not an absence. Nothing in this product reads
    prose to decide which interim relief is wanted, so until the advocate says,
    the answer is that nobody said -- never a default to the commonest one.
    """

    PROHIBITORY_INJUNCTION = "prohibitory_injunction"
    MANDATORY_INJUNCTION = "mandatory_injunction"
    STAY = "stay"
    ATTACHMENT_BEFORE_JUDGMENT = "attachment_before_judgment"
    RECEIVER = "receiver"
    NOT_STATED = "not_stated"

    @classmethod
    def not_established(cls) -> "InterimRelief":
        return cls.NOT_STATED


class LimbState(str, Enum):
    """Whether a limb is made out. THREE states, and the third is this slice.

    `NOT_ASSESSED` is what every limb returns today, because nothing reads the
    advocate's material for it. It is distinct from `WEAK`, which is a finding:
    somebody looked and the limb is not made out. Collapsing them would report
    an unexamined application as a poor one.
    """

    SUPPORTED = "supported"
    WEAK = "weak"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "LimbState":
        return cls.NOT_ASSESSED


@refuses_blank_text()
@dataclass(frozen=True)
class Limb:
    """One thing an interim application must show."""

    name: str
    """In the advocate's words, as a thing to be SHOWN."""
    what_would_answer_it: str
    """What material on the file would settle this limb. Written so the
    advocate can supply it in one line -- the same discipline
    `Condition.satisfied_when` keeps for a pre-institution condition."""


@refuses_blank_text("bar", "threshold_note")
@dataclass(frozen=True)
class Test:
    """The test for one interim relief, and where it came from."""

    relief: InterimRelief
    source: str
    """The provision or rule the relief is sought under, for retrieval."""
    curated_from: str
    limbs: tuple[Limb, ...] = ()
    threshold_note: str = ""
    """What is HIGHER or different about this relief's threshold, where
    anything is. Empty means the ordinary threshold, not an unexamined one --
    every curated row states its threshold explicitly in `curated_from`."""
    bar: str = ""
    """A statutory bar that may defeat the relief whatever the limbs show.
    Named BEFORE the limbs when it is engaged: an advocate who reads three
    supported limbs and then meets the bar has read them for nothing."""


@refuses_blank_text("because")
@dataclass(frozen=True)
class Assessment:
    """The interim position: the test, and where each limb stands."""

    relief: InterimRelief
    test: Test | None = None
    states: tuple[tuple[str, LimbState], ...] = field(default_factory=tuple)
    because: str = ""

    @property
    def established(self) -> bool:
        return self.test is not None


class InterimReliefPort(Protocol):
    """The knowledge plane, asked what an interim relief must show."""

    def test_for(self, relief: InterimRelief) -> Test | None: ...

    def assess(self, relief: InterimRelief) -> Assessment: ...


__all__ = ["InterimRelief", "LimbState", "Limb", "Test", "Assessment",
           "InterimReliefPort"]
