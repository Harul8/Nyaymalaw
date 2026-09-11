"""The law a computation rests on, established before the computation runs.

BK-65-AC2. P22.

    from nm.core.premise import Premises, assess, blocks

THE DEFECT THIS EXISTS FOR IS NOT AN ARITHMETIC ERROR
-------------------------------------------------------
CLAUDE.md records the previous build's death in one sentence: twelve
mechanically-checked properties all passed on a transcript where the product
analysed a twelve-year limitation on a trespass a day old. The subtraction was
right. Every guard was green. The ARTICLE was wrong, and nothing in the system
was looking at that, because nothing in the system treated *which law governs*
as a thing that could be wrong.

`compute()` already refuses to invent a period -- `Period` verifies itself
against the retrieved span, so no fabricated number reaches the arithmetic.
What it cannot refuse is a period that is real, correctly read, correctly
applied, and belongs to a different Article than the one this matter is under.

    CORRECT ARITHMETIC CANNOT ESTABLISH APPLICABLE LAW,
    ACCRUAL OR JURISDICTION.

That is the criterion, and this module is the thing that makes it true: three
premises, each separately attributed, each reviewable on its own, and none of
them derivable from the sum they feed.

WHY THREE, AND WHY THEY CANNOT BE ONE FIELD
---------------------------------------------
They fail differently and they are corrected by different people.

    APPLICABLE_LAW   the wrong Article gives a right answer to another
                     question. Corrected by retrieval or by the advocate.
    ACCRUAL_RULE     the right Article from the wrong date. Corrected by the
                     chronology, and it is the one the model most wants to
                     guess at from "the first dated fact".
    JURISDICTION     the right rule from a forum that does not bind. This one
                     is silent: nothing in an answer looks wrong.

A single `basis: str` collapses all three, and the advocate correcting it
cannot say which of the three they are correcting.

THE STATE VOCABULARY IS THE PRODUCT'S OWN
-------------------------------------------
`STATED` / `INFERRED` is the shape `nm/knowledge/manifest.py::ActBasis` already
uses for exactly this reason -- CLAUDE.md §5: keyword routing may yield
`INFERRED`, the note names what it inferred from, and the advocate can correct
it in four words. `ATTRIBUTED` is added because a premise read from a retrieved
provision is stronger than one a person asserted and weaker than nothing:
it names a source that can be re-read.

INFERRED DOES NOT RUN THE ARITHMETIC. That is the whole control. An inferred
premise is a question for the advocate, and the answer that would have been
computed from it is not computed -- because a number on the screen is acted on
whatever the note beside it says.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from nm.domain.text import refuses_blank_text


class Kind(str, Enum):
    """The three things arithmetic cannot establish about itself."""

    APPLICABLE_LAW = "applicable_law"
    ACCRUAL_RULE = "accrual_rule"
    JURISDICTION = "jurisdiction"


class Basis(str, Enum):
    """How this premise came to be believed. Ordered weakest last."""

    STATED = "stated"
    """The advocate said so. The strongest basis this product has, and the only
    one it may not second-guess."""

    ATTRIBUTED = "attributed"
    """Read from a named source that can be re-read and disagreed with."""

    INFERRED = "inferred"
    """The product worked it out. NEVER sufficient to run a computation --
    it is a question, and the note says what it was inferred from."""

    UNESTABLISHED = "unestablished"
    """Nobody has established it. §9's third state, and the common one."""

    @classmethod
    def not_established(cls) -> "Basis":
        """The escape this vocabulary declares. `tests/test_three_states.py`
        reads it rather than guessing from the member names, because
        UNESTABLISHED and a genuine finding of NOT_APPLICABLE would be
        indistinguishable to any list of substrings."""
        return cls.UNESTABLISHED


#: Bases a computation may proceed on. The omission is the control.
SUFFICIENT = (Basis.STATED, Basis.ATTRIBUTED)

#: Every computation that depends on law needs all three. A computation that
#: needed only two would be one where the third was assumed.
REQUIRED = (Kind.APPLICABLE_LAW, Kind.ACCRUAL_RULE, Kind.JURISDICTION)


@refuses_blank_text("source", "inferred_from")
@dataclass(frozen=True)
class Premise:
    """One legal proposition a computation rests on, and where it came from."""

    kind: Kind
    statement: str
    basis: Basis
    source: str = ""
    """WHAT CAN BE RE-READ. A provision locator, a chronology fact id, or the
    advocate's own words. Required for ATTRIBUTED -- a source nobody can open
    is an assertion with a citation-shaped decoration."""
    inferred_from: str = ""
    """For INFERRED only: what the product reasoned from, so the advocate can
    correct it in four words rather than re-stating the whole matter."""
    alternatives: tuple[str, ...] = ()
    """What ELSE matched. CLAUDE.md §5: the note names what it inferred from
    AND what else matched, because a silent guess sends an exact section
    lookup into the wrong statute."""

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "statement": self.statement,
                "basis": self.basis.value, "source": self.source,
                "inferred_from": self.inferred_from,
                "alternatives": list(self.alternatives)}


@dataclass(frozen=True)
class Premises:
    """The set a computation is about to run on."""

    items: tuple[Premise, ...] = ()

    def of(self, kind: Kind) -> Premise | None:
        for row in self.items:
            if row.kind is kind:
                return row
        return None

    def digest(self) -> str:
        """The identity of this premise set. BK-65-AC2's last clause.

        A result is stamped with this. When a premise moves the digest moves,
        so a stored conclusion can be told it is about a legal position that no
        longer holds -- WITHOUT re-running the arithmetic to find out. That is
        the difference between invalidating a result and recomputing one, and
        only the first is possible when the new premise blocks computation.
        """
        material = "|".join(
            f"{p.kind.value}={p.basis.value}:{p.statement.strip()}:{p.source.strip()}"
            for p in sorted(self.items, key=lambda r: r.kind.value))
        return hashlib.sha256(material.encode("utf8")).hexdigest()[:16]


def assess(premises: Premises) -> list[str]:
    """Why the arithmetic must not run yet, or nothing.

    EACH REASON IS ADDRESSED TO SOMEBODY. "The premises are incomplete" tells
    an advocate nothing; "which Article governs has not been established, and
    the product inferred Article 65 from the word possession" tells them what
    to type.
    """
    bad: list[str] = []
    for kind in REQUIRED:
        premise = premises.of(kind)
        if premise is None:
            bad.append(f"{_english(kind)} has not been established at all, and "
                       f"a computation that proceeds without it is answering a "
                       f"question nobody asked")
            continue
        if not premise.statement.strip():
            bad.append(f"{_english(kind)} is recorded with no statement")
            continue
        if premise.basis is Basis.UNESTABLISHED:
            bad.append(f"{_english(kind)} is explicitly unestablished")
        elif premise.basis is Basis.INFERRED:
            note = (f"the product inferred {premise.statement!r}"
                    + (f" from {premise.inferred_from}" if premise.inferred_from
                       else ""))
            if premise.alternatives:
                note += f"; {', '.join(premise.alternatives)} also matched"
            bad.append(f"{_english(kind)} was not established -- {note}. "
                       f"Confirm or correct it before this is computed")
        elif premise.basis is Basis.ATTRIBUTED and not premise.source.strip():
            bad.append(f"{_english(kind)} claims a source and names none, so "
                       f"nothing can be re-read to check it")
    return bad


def blocks(premises: Premises) -> bool:
    """ONLY when every required premise is stated or attributed."""
    return bool(assess(premises))


def invalidated(stamped: str, now: Premises) -> str | None:
    """Has the legal position under a stored result moved? BK-65-AC2.

    Returns the sentence to show, or None. A result whose premise digest no
    longer matches is not merely stale -- it may not be recomputed either, if
    the new premises block. Saying "this is being recalculated" where the truth
    is "the law this rested on is now unestablished" is the more comfortable of
    the two sentences and the wrong one.
    """
    if stamped == now.digest():
        return None
    if blocks(now):
        return ("the legal position this rested on has changed and is not yet "
                "established, so this cannot be recomputed until it is")
    return ("the legal position this rested on has changed, so this no longer "
            "carries its earlier approval and has been recomputed")


def _english(kind: Kind) -> str:
    return {
        Kind.APPLICABLE_LAW: "which provision governs",
        Kind.ACCRUAL_RULE: "what starts the limitation period",
        Kind.JURISDICTION: "which forum's law applies",
    }[kind]
