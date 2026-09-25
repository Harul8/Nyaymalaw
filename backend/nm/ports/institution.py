"""WHAT MUST BE DONE BEFORE A PROCEEDING CAN BE INSTITUTED: the shapes. LB-121.

THE TABLE IS NOT HERE. `backend/nm/knowledge/institution.py` holds the curated
conditions and `backend/nm/adapters/knowledge/institution.py` serves them through
this port, the split the elements and evidence planes already use: the port
declares the shape, the knowledge plane holds the curation, and `nm.core`
imports neither.

THE DEFECT THIS REFUSES
------------------------
A suit that skips a step the statute required first fails before its merits are
ever reached. The product's threshold map already names `statutory_notice` --
and every turn answered it BLOCKED with the same sentence, because nothing
assessed it. An advocate reading that row learned nothing about their own file.

THE TABLE IDENTIFIES; IT DOES NOT DECIDE SATISFACTION
------------------------------------------------------
Two separate questions, and conflating them is how a condition gets reported
as met because it was mentioned:

  ENGAGED    does this cause, forum or party bring a condition into play?
             Decided HERE, by exact key on the closed `CauseOfAction`
             vocabulary and on recorded party facts. Never by reading prose,
             never by fuzzy match -- CLAUDE.md section 5.

  SATISFIED  does the file show it done, on the dates the statute requires?
             NOT decided here and NOT decided by this slice. It is a question
             about the advocate's own words and documents, and until something
             reads them the honest answer is NOT ASSESSED -- named, with its
             source, so the advocate can answer it in one line.

An engaged condition nobody has assessed is therefore visible as a question
about THAT condition, rather than as the generic silence the map carried
before. That is the third state made useful rather than merely present.

`curated_from` IS REQUIRED BY THE TYPE, exactly as `nm.knowledge.resolution.Edge`
requires it: a routing decision that cannot say where it came from is one
somebody remembered, and this file is where remembering would be invisible.

WHAT IS DELIBERATELY NOT HERE
------------------------------
No period arithmetic. `Condition.period_said` is the Act's own words about its
timing, for the advocate to read and for a later slice to compute from -- it is
not parsed here, because a number computed from a rule nobody retrieved is the
defect the limitation work already paid for.

Nothing in this module asserts current law. Each row points at the provision
that must be RETRIEVED AND READ BACK before it is relied on; the text is never
recited from memory (G-GROUND, G-QUOTE).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from nm.domain.matter import CauseOfAction
from nm.domain.text import refuses_blank_text


class Against(str, Enum):
    """WHO IS ON THE OTHER SIDE, where that decides a condition.

    A closed vocabulary for the same reason `CauseOfAction` is closed: the
    alternative is matching a party description approximately, and an
    approximate match here decides whether two months' notice was required.

    `UNKNOWN` is a value and not an absence. A condition that turns on the
    opponent's character is UNDECIDED while nobody has established it -- never
    read as not arising, which is the silence this whole module exists to end.
    """

    PRIVATE = "private"
    GOVERNMENT = "government"
    UNKNOWN = "unknown"

    @classmethod
    def not_established(cls) -> "Against":
        return cls.UNKNOWN


@refuses_blank_text("period_said")
@dataclass(frozen=True)
class Condition:
    """One thing a statute requires before a proceeding is instituted."""

    key: str
    """The stable identity. Not shown to anyone; `said` is what is read."""
    said: str
    """What the advocate reads. One sentence, their vocabulary, no section
    number on its own -- `act` and `provision` carry the citation."""
    act: str
    provision: str
    """The corpus's own key for the provision: `80`, `138`, `12A`. Not prose.

    A row that wrote "section 80 CPC" would look up nothing and report a gap
    in an Act held in full -- the trap `nm.knowledge.resolution.Edge` records
    against `Article 14` versus `Article_14`."""
    curated_from: str
    satisfied_when: str
    """What the FILE must show for this condition to read satisfied. Written so
    an advocate can answer it in one line."""
    period_said: str = ""
    """The Act's own words about its timing, for reading -- never parsed here.

    Empty is a real state: a condition with no timing requirement, not a
    timing requirement nobody curated."""


@refuses_blank_text("why")
@dataclass(frozen=True)
class Engagement:
    """One engaged condition and WHY it is engaged, for this thread."""

    condition: Condition
    why: str
    """What brought it into play, in the advocate's terms -- the cause, or who
    the proceeding is against. Shown, so a wrong engagement is correctable at
    a glance rather than after the advocate has acted on it."""


class PreInstitutionPort(Protocol):
    """The knowledge plane, asked what must happen before a proceeding starts.

    TWO METHODS, AND THE SECOND IS NOT OPTIONAL, for the reason `ElementsPort`
    gives: `engaged` returning nothing says only that no condition was reached,
    and `undecided` says whether that is a finding or a key nobody established.
    An absent input must never read as a verdict.
    """

    def engaged(self, cause: CauseOfAction,
                against: Against) -> tuple[Engagement, ...]: ...

    def undecided(self, cause: CauseOfAction,
                  against: Against) -> tuple[Condition, ...]: ...


__all__ = ["Against", "Condition", "Engagement", "PreInstitutionPort"]
