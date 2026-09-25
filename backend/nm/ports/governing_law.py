"""WHICH LAW GOVERNS, WHEN ONE HAS REPLACED ANOTHER: the shapes. LB-120.

THE DEFECT THIS REFUSES
------------------------
A statute that has been repealed and replaced does not stop governing the
matters that arose under it. Reading the replacing code because it is the
current one produces a confident answer under a law that does not apply, and
nothing downstream catches it: every citation is correctly formatted, the
provision is genuinely held, and the section number often even matches.

SUBSTANTIVE AND PROCEDURAL LAW ARE ASKED SEPARATELY, AND THAT IS THE POINT.
One matter routinely needs the OLD substantive code and the NEW procedural one
at the same time, because they turn on different facts: what governs conduct is
fixed at the conduct, while what governs a proceeding turns on whether that
proceeding was already under way. A single "which code applies" answer is
therefore wrong however carefully it is reasoned, and this module refuses to
express one.

THE TABLE IS NOT HERE. `backend/nm/knowledge/governing_law.py` holds the curated
successions and `backend/nm/adapters/knowledge/governing_law.py` serves them through
this port -- the split the elements, evidence and pre-institution planes
already use: the port declares the shape, the knowledge plane holds the
curation, and `nm.core` imports neither.

NOTHING HERE ASSERTS CURRENT LAW. A `Succession` points at the commencement and
the saving provision that must be RETRIEVED AND READ BACK. The saving provision
decides the hard cases, and it is named rather than paraphrased.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol

from nm.domain.text import refuses_blank_text


class Limb(str, Enum):
    """WHICH QUESTION IS BEING ASKED OF THE LAW.

    Separated because the fact that decides each is different, and a single
    answer would have to pick one and be wrong about the other.
    """

    SUBSTANTIVE = "substantive"
    """What conduct was an offence, and what it carries. Fixed at the conduct."""

    PROCEDURAL = "procedural"
    """How a proceeding is conducted. Turns on whether it was already under way
    at commencement, which is what the saving provision addresses."""

    EVIDENTIARY = "evidentiary"
    """What may be proved and how. Read separately again, because a succession
    can commence for evidence on a different footing from procedure."""


class Pending(str, Enum):
    """WAS A PROCEEDING ALREADY UNDER WAY AT COMMENCEMENT?

    Three states, and `UNKNOWN` is the one that carries the work: the answer
    decides which procedural code governs, so guessing it is choosing the law
    by assumption. It is a value rather than an absence for the reason
    `CauseOfAction.NOT_ESTABLISHED` is.
    """

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    @classmethod
    def not_established(cls) -> "Pending":
        return cls.UNKNOWN


@refuses_blank_text()
@dataclass(frozen=True)
class Succession:
    """One statute replacing another, and what decides which of them governs."""

    limb: Limb
    replaced: str
    """The Act that governed before. Its full title, as the corpus holds it."""
    replacing: str
    commenced_on: date
    saving: str
    """THE PROVISION THAT DECIDES THE HARD CASES, named and not paraphrased.

    Every interesting question here -- a proceeding begun under the old code,
    an appeal from a trial under it -- is answered by this provision and not by
    the commencement date alone. Naming it is what lets the advocate check the
    answer against the text rather than against this product's reading of it."""
    curated_from: str


@refuses_blank_text("because", "read_the_saving")
@dataclass(frozen=True)
class Governing:
    """WHICH ACT GOVERNS ONE LIMB, and what settled it.

    `act` EMPTY IS A REAL STATE and it is the honest one: where the date or the
    pending status is unestablished, no Act is named and `because` says which
    fact is missing. An advocate can supply it in one line; a guessed Act
    cannot be corrected because nothing shows it was a guess.
    """

    limb: Limb
    act: str = ""
    because: str = ""
    read_the_saving: str = ""
    """The saving provision to read where one decides this answer. Empty where
    the succession is not engaged at all."""

    @property
    def established(self) -> bool:
        return bool(self.act)


class GoverningLawPort(Protocol):
    """The knowledge plane, asked which Act governs a limb on these facts."""

    def governing(self, limb: Limb, on: date | None,
                  pending: Pending) -> Governing: ...

    def successions(self) -> tuple[Succession, ...]: ...


__all__ = ["Limb", "Pending", "Succession", "Governing", "GoverningLawPort"]
