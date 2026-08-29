"""The evidence port. PRD §4.6 -- retrieval returns FINDINGS, never chunks.

Returning chunks pushes citation, binding status and paragraph kind downstream
to a layer that then skips them, which is precisely how counsel's argument comes
to be quoted as a holding. An obligation not represented in the type crossing
the boundary is an obligation that will be dropped -- so every one of them is a
required field here.

SLICE 2 MADE FOUR OF THEM NON-OPTIONAL
---------------------------------------
`binding`, `para_kind`, `treatment` and `locator` now have no defaults. A
default is a decision taken by whoever wrote the type on behalf of every future
call site that forgets, and the three defaults this type used to carry were
each the safe-looking wrong answer:

    para_kind = UNKNOWN     -> a submission reads as a holding
    binding   = BINDING     -> another State's High Court binds Telangana
    treatment = (absent)    -> an overruled case reads as good law

Each of those is a sentence an advocate would put in front of a judge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol, runtime_checkable


class ParaKind(str, Enum):
    """Only the first three are attributable to a court."""

    RATIO = "ratio"
    REASONING = "reasoning"
    ORDER = "order"
    ARGUMENTS = "arguments"      # counsel's submission -- 14.8% of the corpus
    FACTS = "facts"
    HEADNOTE = "headnote"
    UNKNOWN = "unknown"          # 26.7% -- cannot be vouched either way

    @property
    def attributable(self) -> bool:
        return self in (ParaKind.RATIO, ParaKind.REASONING, ParaKind.ORDER)


class Binding(str, Enum):
    """THREE states. `NOT_ASSESSED` is what an uncomputable status returns.

    Two states would force every unknown court, undated judgment and
    out-of-scope jurisdiction into one of the two findings -- and whichever one
    was chosen, the product would be stating a conclusion it had not reached.
    """

    BINDING = "binding"
    PERSUASIVE = "persuasive"
    NOT_ASSESSED = "not_assessed"

    @property
    def assessed(self) -> bool:
        return self is not Binding.NOT_ASSESSED


class TreatmentState(str, Enum):
    """Subsequent judicial treatment. THREE states, and the third is the point.

    The citator holds entries for 4,894 named cases against 33,791 judgments
    held -- so roughly one case in seven has any entry at all, and it is keyed
    by the case NAME as written in the citing judgment rather than by id.

    A miss therefore means "the citator has nothing on this", which is NOT the
    same as "this case has not been doubted". Collapsing the two would make the
    single most dangerous false negative in the product -- an overruled
    authority presented as good law -- the DEFAULT behaviour.
    """

    CLEAN = "clean"              # checked, and nothing negative found
    NEGATIVE = "negative"        # reversed, overruled, doubted, disapproved
    NOT_CHECKED = "not_checked"  # the citator could not answer

    @property
    def usable_alone(self) -> bool:
        return self is TreatmentState.CLEAN


@dataclass(frozen=True)
class Treatment:
    """Treatment, WITH ITS SCOPE.

    Scope is not a nicety. A judgment overruled on the limitation point remains
    good law on the construction point, and a citator entry that does not say
    which proposition was treated cannot tell you which of those you are
    holding. Where the scope is unknown, that is said.
    """

    state: TreatmentState
    scope: str                   # the proposition treated, or why it is unknown
    verbs: tuple[str, ...] = ()  # FOLLOWED / OVERRULED / DOUBTED / ...
    by: tuple[str, ...] = ()     # the citing judgments, so it can be read back
    source: str = "citator"

    def __post_init__(self) -> None:
        if not self.scope.strip():
            raise ValueError(
                "a Treatment must state its scope, or state that the scope is "
                "unknown. A bare 'clean' is a claim about the whole judgment.")
        if self.state is TreatmentState.NEGATIVE and not self.verbs:
            raise ValueError("negative treatment must name what was done to it")

    @staticmethod
    def not_checked(why: str) -> "Treatment":
        return Treatment(state=TreatmentState.NOT_CHECKED, scope=why, source="none")

    @staticmethod
    def statutory() -> "Treatment":
        """A provision is not `clean` -- it is not the kind of thing a citator
        speaks about at all. Saying so keeps the field honest instead of
        borrowing a case-law state for a statute."""
        return Treatment(
            state=TreatmentState.CLEAN,
            scope="a statutory provision retrieved for the governing date; "
                  "judicial treatment applies to judgments, not to the text of "
                  "the section",
            source="statute")


class Coverage(str, Enum):
    """Three states, never two."""

    ANSWERED = "answered"
    NOT_HELD = "not_held"
    HELD_NOT_FOUND = "held_not_found"   # a DEFECT that escalates


class SourceKind(str, Enum):
    PROVISION = "provision"
    AUTHORITY = "authority"


@dataclass(frozen=True)
class Finding:
    proposition: str
    source_kind: SourceKind
    ref: str
    span: str
    locator: str
    store: str
    binding: Binding
    binding_for: str
    binding_reason: str
    supports: bool
    para_kind: ParaKind
    treatment: Treatment
    valid_from: date | None = None
    valid_to: date | None = None
    governing_date: date | None = None
    origin: str = "resolved"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.span.strip():
            raise ValueError("a Finding without a verbatim span is not a Finding")
        if not self.locator.strip():
            raise ValueError("a Finding without a locator cannot be read back")
        if self.source_kind is SourceKind.AUTHORITY and not self.para_kind.attributable:
            raise ValueError(
                f"a proposition attributed to a judgment must come from a "
                f"ratio/reasoning/order paragraph, not {self.para_kind.value!r} "
                f"(PRD H7, gate G-ATTRIB)")
        if not self.binding_reason.strip():
            raise ValueError(
                "binding status must arrive with the rule that produced it. An "
                "advocate who cannot see why an authority was called binding has "
                "to take it on trust, and this is the field most likely to be "
                "wrong in a way that changes what they file.")

    # ---------------------------------------------------------------- gates ---
    @property
    def in_force(self) -> bool:
        """Was this text in force on the governing date?

        Unanswerable without a governing date, and `True` is not the safe
        answer: the 2024 codes replaced the CrPC and the IPC, so serving the
        superseded text for a 2025 offence is a wrong answer that reads as a
        right one.
        """
        if self.governing_date is None:
            return True   # no date asserted; `blocking_reason` refuses instead
        if self.valid_from and self.governing_date < self.valid_from:
            return False
        if self.valid_to and self.governing_date > self.valid_to:
            return False
        return True

    @property
    def blocking_reason(self) -> str | None:
        """The gate, stated. `None` means the Finding may carry a proposition.

        Returning a REASON rather than a boolean is deliberate: `usable=False`
        with no explanation is an absent input that reads as a quiet decision,
        and the advocate is entitled to know which of five different things
        went wrong.
        """
        if not self.supports:
            return (f"G-GROUND: the retrieved span does not support "
                    f"{self.proposition!r}")
        if self.source_kind is SourceKind.AUTHORITY:
            if not self.binding.assessed:
                return (f"G-BINDING: binding status for {self.ref} could not be "
                        f"computed -- {self.binding_reason}")
            if self.treatment.state is TreatmentState.NEGATIVE:
                return (f"G-GROUND: {self.ref} has negative treatment "
                        f"({', '.join(self.treatment.verbs)}) on "
                        f"{self.treatment.scope}")
            if self.treatment.state is TreatmentState.NOT_CHECKED:
                return (f"G-GROUND: subsequent treatment of {self.ref} was not "
                        f"checked -- {self.treatment.scope}")
        if self.governing_date is not None and not self.in_force:
            return (f"G-INFORCE: {self.ref} was not in force on "
                    f"{self.governing_date.isoformat()} (in force "
                    f"{self.valid_from or 'unrecorded'} to "
                    f"{self.valid_to or 'date'})")
        return None

    @property
    def usable(self) -> bool:
        """A GATE, not a score. A Finding that cannot carry a proposition
        blocks the answer rather than being quietly ranked lower."""
        return self.blocking_reason is None

    @property
    def quotable(self) -> bool:
        """Some Findings may be QUOTED with their status disclosed even though
        they may not carry a proposition alone -- an unassessed authority, or
        one whose treatment was never checked. What may never be quoted is a
        span that does not support what it is cited for, or text that was not
        in force."""
        return self.supports and self.in_force


@dataclass(frozen=True)
class EvidenceNeed:
    """The query is the MATTER, not a sentence.

    A need carrying only a text string would silently degrade the whole design
    back to search-first, and nothing downstream would notice -- so the
    governing date is required rather than defaulted to today.
    """

    question: str
    governing_date: date
    jurisdiction: str = "Telangana"
    forum: str | None = None
    cause_of_action: str | None = None
    provision_hint: str | None = None
    want_authority: bool = False

    def __post_init__(self) -> None:
        if self.governing_date is None:
            raise ValueError(
                "a query without a governing date is REJECTED, not defaulted to "
                "today (PRD G1/H2, gate G-DATE)")


@dataclass(frozen=True)
class EvidenceResult:
    coverage: Coverage
    findings: tuple[Finding, ...] = ()
    missing: str | None = None
    searched_stores: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.coverage is Coverage.NOT_HELD and not self.missing:
            raise ValueError(
                "a NOT_HELD result must NAME what is missing. A vague "
                "disclaimer is silence in more words (PRD M4).")

    @property
    def usable(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.usable)

    @property
    def blocked(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if not f.usable)


@runtime_checkable
class EvidencePort(Protocol):
    def fetch(self, need: EvidenceNeed) -> EvidenceResult: ...
