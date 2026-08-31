"""The evidence inventory. C7, and the full contract is Appendix E.

EXISTENCE, ADMISSIBILITY AND WEIGHT ARE THREE QUESTIONS
---------------------------------------------------------
The original contract held two of the three, so *admissible* and *persuasive*
had one field between them — and an advocate plans differently for each. A
WhatsApp exchange EXISTS; whether it goes in depends on the electronic-records
certificate; whether it moves a judge is a third question again.

Collapsing any two of them produces an item that reads as settled when one of
the three was never asked. So each is its own enum, each carries
`not_assessed`, and the type refuses the combinations that would let one stand
in for another.

A PHOTOCOPY IS NOT THE DOCUMENT
---------------------------------
`form` distinguishes original, certified copy, photocopy, electronic and oral,
because one `form` string that does not tell them apart makes the s.65
secondary-evidence position INVISIBLE — and that position is the whole answer
on a file where the original sits with the opponent's brother.

A PRESERVATION INSTRUCTION WITH NO OWNER AND NO DATE IS A WISH
----------------------------------------------------------------
C7 requires both. The type requires both, so the wish cannot be recorded as an
instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.matter import FactId
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class Holder(str, Enum):
    """Who has it decides how it is obtained and how long that takes."""

    CLIENT = "client"
    OPPONENT = "opponent"
    THIRD_PARTY = "third_party"
    COURT = "court"
    UNKNOWN = "unknown"


class Form(str, Enum):
    """A PHOTOCOPY IS NOT THE DOCUMENT."""

    ORIGINAL = "original"
    CERTIFIED_COPY = "certified_copy"
    PHOTOCOPY = "photocopy"
    ELECTRONIC = "electronic"
    ORAL = "oral"
    NOT_ASSESSED = "not_assessed"


class Existence(str, Enum):
    """THE FIRST QUESTION. Is there such a thing, and where is it."""

    HELD = "held"
    OBTAINABLE = "obtainable"
    ABSENT = "absent"
    NOT_ASSESSED = "not_assessed"


class Admissibility(str, Enum):
    """THE SECOND. Having a thing is not being able to prove it."""

    ADMISSIBLE_AS_HELD = "admissible_as_held"
    NEEDS = "needs"
    INADMISSIBLE = "inadmissible"
    NOT_ASSESSED = "not_assessed"


class Weight(str, Enum):
    """THE THIRD, AND IT WAS MISSING ENTIRELY from the original contract."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NOT_ASSESSED = "not_assessed"


class Authenticity(str, Enum):
    ESTABLISHED = "established"
    DISPUTED = "disputed"
    NOT_ASSESSED = "not_assessed"


class Completeness(str, Enum):
    """A partial document read as whole is how a clause that kills the case
    stays unread."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text()
@dataclass(frozen=True)
class Custody:
    """One link in the chain. A break is an attack the opponent will make and
    we should make first."""

    holder: str
    from_when: str
    to_when: str


@refuses_blank_text()
@dataclass(frozen=True)
class Preservation:
    """AN OWNER AND A DATE. C7 requires both; an instruction with neither is a
    wish, and this type is what stops a wish being recorded as an instruction.
    """

    owner: str
    due: date
    issued_at: date | None = None

    @property
    def issued(self) -> bool:
        return self.issued_at is not None


@refuses_blank_text("weight_reason", "metadata")
@dataclass(frozen=True)
class EvidenceItem:
    """One item, with the three questions kept apart. Appendix E."""

    what: str
    fact: tuple[FactId, ...] = ()
    holder: Holder = Holder.UNKNOWN
    form: Form = Form.NOT_ASSESSED
    existence: Existence = Existence.NOT_ASSESSED
    admissibility: Admissibility = Admissibility.NOT_ASSESSED
    admissibility_needs: tuple[str, ...] = ()
    weight: Weight = Weight.NOT_ASSESSED
    weight_reason: str = ""
    authenticity: Authenticity = Authenticity.NOT_ASSESSED
    completeness: Completeness = Completeness.NOT_ASSESSED
    metadata: str = ""
    custody: tuple[Custody, ...] = ()
    preservation: Preservation | None = None
    lawful_source: bool | None = None
    """`None` IS THE THIRD STATE and it is why this is not a bare bool.

    C7 forbids obtaining material unlawfully or suggesting a route that would.
    Without the field nothing records that the question was asked -- and with a
    bare `bool` defaulting to `True`, every item would assert an answer nobody
    gave, which is the more dangerous of the two."""

    def __post_init__(self) -> None:
        if self.admissibility is Admissibility.NEEDS \
                and not self.admissibility_needs:
            raise ValueError(
                f"{self.what!r} is admissible only if something is done and "
                f"does not say what. `needs` with nothing named is a dead end "
                f"dressed as a next step.")
        if self.weight is not Weight.NOT_ASSESSED and blank(self.weight_reason):
            raise ValueError(
                f"{self.what!r} carries a weight with no reason. Weight "
                f"without a reason cannot be argued or challenged, which is "
                f"the only thing an advocate would do with it.")
        # THE THREE QUESTIONS MAY NOT STAND IN FOR ONE ANOTHER.
        if self.existence is Existence.ABSENT and self.admissibility in (
                Admissibility.ADMISSIBLE_AS_HELD, Admissibility.NEEDS):
            raise ValueError(
                f"{self.what!r} does not exist and carries an admissibility "
                f"position anyway. Admissibility of what? This is the collapse "
                f"C7 separates the three questions to prevent.")

    @property
    def at_risk(self) -> bool:
        """Held by someone with an interest in it not surviving.

        Not a judgement about them -- a fact about custody. D5.1's frame
        applies here too: the product reasons about where a document is, never
        about what its holder intends.
        """
        return self.holder in (Holder.OPPONENT, Holder.THIRD_PARTY)


@implements("C7")
def unpreserved(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """C7. Items at risk with no preservation instruction. THE COUNTEREXAMPLE.

    *A file where the original agreement is with the opponent's brother and no
    preservation or production step exists.* The item is inventoried, its
    holder is recorded, and nothing was ever asked of anyone -- so the file
    reads as worked and the document is gone by the time it is needed.

    Returns the items rather than a count, for the same reason everything else
    in this build does: which one it is decides what the advocate does next.
    """
    return tuple(i.what for i in items
                 if i.at_risk and i.preservation is None)


@implements("C7")
def undelivered(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """Preservation instructions that were WRITTEN AND NEVER ISSUED.

    A third state, and it is the one that reads best on a file review: the
    instruction exists, it has an owner and a date, and it is sitting in a
    draft. `unpreserved` reports nothing about it, because there IS an
    instruction — so without this the two failures are indistinguishable to
    everyone except the document, which is gone either way.
    """
    return tuple(i.what for i in items
                 if i.preservation is not None and not i.preservation.issued)


@implements("C7")
def unasked(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """Items where one of the three questions was never put.

    NOT_ASSESSED on any of existence, admissibility or weight is a real and
    ordinary state; what it may not be is invisible. An inventory that lists
    ten items and silently answered two questions of the thirty reads as an
    inventory that was done.
    """
    out: list[str] = []
    for i in items:
        missing = [name for name, value in (
            ("existence", i.existence), ("admissibility", i.admissibility),
            ("weight", i.weight)) if value.value == "not_assessed"]
        if missing:
            out.append(f"{i.what}: {', '.join(missing)} not assessed")
    return tuple(out)
