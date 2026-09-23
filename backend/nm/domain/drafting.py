"""THE DRAFTING PACKAGE, AND WHY IT IS NOT READY TO FILE. BK-56, BK-92-AC3. P29.

    from nm.domain.drafting import DrafterBrief, Provenance, readiness

WHAT THIS IS FOR
------------------
An advocate asks for a pleading. What comes back has to be checkable: every
material claim carrying where it came from, every quotation verified against
the source it was taken from, every gap left visibly open.

And one thing above all:

    DRAFTING READINESS IS NOT FILING READINESS.

That gap is where a draft which READS finished gets filed without the
authority, the receipt or the deadline anybody checked. CHOICE-09 settles it
for this release -- *"first release prepares, verifies and exports approved
drafts; the advocate files/sends and records receipts"*, and its `approval`
field reads `None`. So `Readiness` has no member meaning *ready to file*, and
`refuse_filing_claim` exists to answer the question in a sentence rather than
leave a caller to assume.

THE RECORD IS APPENDIX E'S, FIELD FOR FIELD
---------------------------------------------
`DrafterBrief` is declared in `assurance/specification/schemas.yaml` with thirteen required
fields, and BK-56-AC2 is that record written as prose. It was not implemented.
Implementing it under different names would leave the obligation unmet while
looking met -- the naming-drift entry `test_reached_from_production.UNTYPED`
already records against `TurnRoute`.

SEVEN PROVENANCE KINDS, AND COLLAPSING ANY TWO IS THE DEFECT
--------------------------------------------------------------
Supplied text, extracted text, established fact, disputed proposition,
inference, legal premise, unresolved gap. A draft that renders an INFERENCE the
way it renders an ESTABLISHED FACT is the document an advocate signs and then
cannot support when it is put to them. The kinds are not a severity scale and
they do not collapse into "sourced / unsourced": what an opponent attacks is
the specific claim that something was established when it was inferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.spoken import named
from nm.domain.text import blank, refuses_blank_text, snippet


class Provenance(str, Enum):
    """WHERE A CLAIM IN THE DRAFT CAME FROM. Seven kinds, none interchangeable."""

    SUPPLIED_TEXT = "supplied_text"
    """The advocate wrote it. Instruction; never re-derived, never softened."""

    EXTRACTED_TEXT = "extracted_text"
    """Read out of a document. It carries a locator or it is not extracted."""

    ESTABLISHED_FACT = "established_fact"
    """On the file, attributed, and not disputed on the record."""

    DISPUTED_PROPOSITION = "disputed_proposition"
    """Asserted by somebody and contradicted by somebody. Pleaded as a case,
    never as a fact -- the distinction an opponent attacks first."""

    INFERENCE = "inference"
    """The product worked it out. Correctable in four words, and it says so."""

    LEGAL_PREMISE = "legal_premise"
    """A position of law the draft rests on. P22 owns whether it is stated or
    inferred; this only records that the claim IS one."""

    UNRESOLVED_GAP = "unresolved_gap"
    """Nothing establishes it and the draft says so where it would have gone.
    THE THIRD STATE, and the one a template most wants to fill."""

    @classmethod
    def not_established(cls) -> "Provenance":
        return cls.UNRESOLVED_GAP

    @property
    def needs_a_locator(self) -> bool:
        """Extracted text and authorities are checkable against a source; an
        inference and a gap are not, and demanding one would invite a
        fabricated citation to satisfy the field."""
        return self in (Provenance.EXTRACTED_TEXT, Provenance.LEGAL_PREMISE)

    @property
    def may_be_pleaded_as_fact(self) -> bool:
        return self in (Provenance.SUPPLIED_TEXT, Provenance.EXTRACTED_TEXT,
                        Provenance.ESTABLISHED_FACT)


class Readiness(str, Enum):
    """How far the PACKAGE has got. There is deliberately no `READY_TO_FILE`.

    Filing readiness is not a state this product can reach: it needs an
    authority, a forum, a fee and a receipt that live outside it, and
    CHOICE-09 disables the connectors that would obtain them. A member meaning
    *ready to file* would be read as one whatever its docstring said.
    """

    NOT_ASSESSED = "not_assessed"
    INCOMPLETE = "incomplete"
    """Something material is missing, and `problems()` names it."""

    READY_TO_REVIEW = "ready_to_review"
    """The package is internally consistent and every claim is sourced. It is
    ready for a person to READ, which is the furthest this goes."""

    @classmethod
    def not_established(cls) -> "Readiness":
        return cls.NOT_ASSESSED


@refuses_blank_text("locator", "source_version", "quoted", "why_unresolved")
@dataclass(frozen=True)
class Claim:
    """One material assertion in the draft, with where it came from.

    `locator` and `source_version` are EXEMPT from the blank rule because an
    inference and a gap legitimately have neither -- requiring them would push
    a caller into inventing a citation to construct the object, which is the
    fabrication this packet exists to refuse. `problems()` asks for them where
    the provenance says they must exist.
    """

    text: str
    provenance: Provenance
    source_id: str = ""
    locator: str = ""
    source_version: str = ""
    quoted: str = ""
    """The verbatim span this rests on, where it rests on one. Checked against
    the source by `nm.core.drafting`, using P21's `quote_fidelity` -- the
    product already owns *are these the source's words* and must not own it
    twice."""

    verified: bool = False
    """Set only by the verification pass. A claim nobody checked is not
    verified, and the default says so rather than assuming."""

    why_unresolved: str = ""

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.provenance.needs_a_locator and blank(self.locator):
            out.append(f"{named(snippet(self.text, 60))} is {self.provenance.value} and "
                       f"names no locator; extracted text that cannot be found "
                       f"again is an assertion with a citation-shaped label")
        if self.provenance.needs_a_locator and blank(self.source_version):
            out.append(f"{named(snippet(self.text, 60))} names a locator and no source "
                       f"version; a passage that moved is a different passage")
        if not blank(self.quoted) and not self.verified:
            out.append(f"{named(snippet(self.text, 60))} carries a quotation nobody checked "
                       f"against its source")
        if self.provenance is Provenance.UNRESOLVED_GAP and blank(self.why_unresolved):
            out.append(f"{named(snippet(self.text, 60))} is an unresolved gap and does not "
                       f"say what is missing, so nobody can close it")
        return tuple(out)


#: THE THIRTEEN FIELDS APPENDIX E DECLARES for `DrafterBrief`. Named here so
#: the type, the served projection and the test that counts them read one list.
#: `assurance/specification/schemas.yaml` is the authority; the test asserts this against it
#: rather than trusting the copy.
DECLARED_FIELDS: tuple[str, ...] = (
    "cause_title", "theory_sentence", "material_facts", "provisions",
    "limitation", "reliefs", "authorities", "proof_positions",
    "facts_not_to_plead", "arguments_parked", "open_gaps",
    "blanks_permitted", "lossless",
)


@refuses_blank_text("theory_sentence")
@dataclass(frozen=True)
class DrafterBrief:
    """Appendix E's record, implemented. BK-56-AC2.

    `theory_sentence` is exempt because a package assembled before the theory
    is settled must be REPRESENTABLE -- `problems()` reports it, and refusing
    construction would mean the advocate cannot see the package that would
    tell them what is missing.

    `blanks_permitted` and `lossless` are the two flags the contract carries
    and they are not decoration. A marked blank is a deliberate hole the
    drafter must preserve; losslessness is the promise that nothing on the file
    was dropped on the way in, and a package that cannot say it is lossless
    says so.
    """

    package_id: str
    matter_id: str
    document: str
    """WHAT IS BEING DRAFTED -- a plaint, a written statement, a reply."""
    audience: str
    purpose: str
    posture: str

    cause_title: dict = field(default_factory=dict)
    theory_sentence: str = ""
    material_facts: tuple[Claim, ...] = ()
    provisions: tuple[Claim, ...] = ()
    limitation: dict = field(default_factory=dict)
    reliefs: tuple[str, ...] = ()
    authorities: tuple[Claim, ...] = ()
    proof_positions: tuple[str, ...] = ()
    facts_not_to_plead: tuple[dict, ...] = ()
    arguments_parked: tuple[dict, ...] = ()
    open_gaps: tuple[dict, ...] = ()
    blanks_permitted: bool = True
    lossless: bool = False

    adverse: tuple[str, ...] = ()
    """MATERIAL AGAINST US, carried INTO the package. A drafting package that
    quietly omits the adverse material is the one that gets an advocate
    ambushed, and the omission is invisible precisely because the draft reads
    clean."""

    reservations: tuple[str, ...] = ()
    missing_instructions: tuple[str, ...] = ()
    stale_dependencies: tuple[str, ...] = ()
    advice_version: str = ""
    version: int = 1

    @property
    def claims(self) -> tuple[Claim, ...]:
        return (*self.material_facts, *self.provisions, *self.authorities)

    def problems(self) -> tuple[str, ...]:
        """Everything that keeps this package from being ready to review.

        Returned as a population rather than a boolean so the advocate is told
        WHICH thing is missing. A package reported merely "incomplete" sends
        them looking.
        """
        out: list[str] = []
        for name in ("document", "audience", "purpose", "posture"):
            if blank(getattr(self, name, "")):
                out.append(f"the package does not say what the {name} is")
        if blank(self.theory_sentence):
            out.append("no theory sentence: the draft has nothing to be about")
        if not self.cause_title:
            out.append("no cause title, so the document names no court or party")
        if not self.reliefs:
            out.append("no relief is sought, ranked or otherwise")
        out.extend(p for c in self.claims for p in c.problems())
        for gap in self.open_gaps:
            if blank(str(gap.get("gap", ""))):
                out.append("an open gap with no description is not a gap")
        if self.stale_dependencies:
            out.append(
                "the package rests on material that has since moved: "
                + "; ".join(self.stale_dependencies))
        if not self.lossless:
            out.append(
                "the package cannot say it carried everything on the file "
                "across; something was dropped or nobody checked")
        return tuple(out)

    def readiness(self) -> Readiness:
        """DERIVED, never handed in -- the rule P26 keeps for advice maturity
        and P33 keeps for retention state, for the same reason."""
        if not self.claims and not self.theory_sentence:
            return Readiness.NOT_ASSESSED
        return Readiness.INCOMPLETE if self.problems() else Readiness.READY_TO_REVIEW


def refuse_filing_claim(brief: DrafterBrief) -> str:
    """WHY THIS PACKAGE IS NOT READY TO FILE. Always a reason, never "".

    It answers the same way whatever the package says, and that is the rule
    rather than a check that cannot fail: CHOICE-09 disables the connectors and
    its `approval` field reads `None`, so no package this product produces has
    been filed, and none can be. It exists as a function so a caller asking
    *can this go?* gets a sentence to show the advocate instead of finding no
    answer and supplying one.
    """
    # THE FILING SENTENCE IS ON EVERY PATH, not only the finished one.
    #
    # A first version said it only when the package was ready to review, and
    # the incomplete branch said merely that nobody had read it -- which reads
    # as "not yet" rather than "not ever by this product". CHOICE-09 does not
    # depend on how complete the package is: the connectors are disabled and
    # its `approval` field is None whatever state the draft has reached.
    always = ("This package is NOT ready to file. Filing needs an authority, "
              "a forum, a fee and a receipt that this product does not hold, "
              "and the external-action connectors are disabled (CHOICE-09). "
              "Nothing here has been filed or sent, and nothing here can file "
              "or send it.")
    state = brief.readiness()
    if state is not Readiness.READY_TO_REVIEW:
        return (f"{always} It is also {state.value}: "
                f"{len(brief.problems())} thing(s) are outstanding and nobody "
                f"has read it.")
    return f"{always} It is ready for you to READ, which is as far as this goes."
