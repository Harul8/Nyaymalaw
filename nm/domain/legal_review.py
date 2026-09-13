"""THE LEGAL HALF OF A REVIEW, WHICH IS NOT A HIGHER SCORE. BK-67, BK-91. P35.

    from nm.domain.legal_review import LegalReviewRecord, Premise, refuse_approval

WHAT THIS ADDS TO `nm/domain/review.py` AND WHY IT IS NOT A SECOND COPY
-------------------------------------------------------------------------
`review.py` owns admissibility: was the population real, was the rubric fixed
before anybody saw a result, was a critical failure averaged away, was the
thing called an advocate's judgement one. Every word of that applies here and
is REUSED -- a `LegalReviewRecord` carries a `Study` rather than restating its
seven refusals.

What is specific to a LEGAL review, and lives here:

    THE PREMISE IS REVIEWED SEPARATELY FROM THE ARITHMETIC. BK-67-AC3's
    negative control is *correct date arithmetic with an unsupported accrual
    rule*, and the reason it is a control is that the calculation passing is
    the most convincing possible evidence for the wrong thing. So a premise
    carries its own verdict and the arithmetic's verdict is CONDITIONAL on it:
    `Arithmetic.assessed_on` names the premise it assumed, and an arithmetic
    verdict whose premise failed is not a pass at a lower confidence -- it is
    not a verdict.

    THE PRIMARY SOURCE IS NAMED AND CURRENT. A premise resting on "the Act"
    rests on whichever version the reviewer had. `Premise.source_version` is
    required, and BK-67-AC3's other control -- *treat a historical court
    cohort label as proof of binding status* -- is why `binding_basis` is a
    sentence rather than a court name.

    APPROVAL IS SCOPED AND DOES NOT TRAVEL. BK-67-AC4: new facts, changed law,
    a different corpus, a different model, a changed prompt. `Approval.covers`
    names what was reviewed and `still_current` refuses everything else --
    including, explicitly, a later model version, because a model that scores
    better on average can fail differently on the cases that matter.

WHAT THIS MODULE CANNOT DO, AND SAYS SO
-----------------------------------------
It cannot review anything. Every verdict here is recorded from a person; there
is no function that produces one, and `refuse_approval` counts qualified
reviewers rather than trusting a flag. A model may build this and may not be
the reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.review import Severity, Study, refuse_conclusion
from nm.domain.text import blank, refuses_blank_text


class Verdict(str, Enum):
    """One reviewer's answer about one thing.

    `NOT_ASSESSED` is the default and is not a pass. A premise nobody looked
    at and a premise found sound are the same shape in a report and opposite
    facts in a hearing.
    """

    SOUND = "sound"
    UNSUPPORTED = "unsupported"
    WRONG = "wrong"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Verdict":
        return cls.NOT_ASSESSED

    @property
    def supports_reliance(self) -> bool:
        return self is Verdict.SOUND


class PremiseKind(str, Enum):
    """The five governing premises BK-67-AC3 enumerates, kept apart.

    They fail independently and are found by different work: the applicable
    law by reading the statute, accrual by reading the facts against it,
    jurisdiction by the forum's own rules, binding status by treatment, and
    the role restriction by the professional rules.
    """

    APPLICABLE_LAW = "applicable_law"
    ACCRUAL = "accrual"
    JURISDICTION = "jurisdiction"
    BINDING_AUTHORITY = "binding_authority"
    ROLE_RESTRICTION = "role_restriction"


@refuses_blank_text()
@dataclass(frozen=True)
class Premise:
    """One governing premise, its primary source, and a person's verdict."""

    kind: PremiseKind
    statement: str
    source_id: str = ""
    locator: str = ""
    source_version: str = ""
    """WHICH VERSION OF THE SOURCE. A premise resting on "the Act" rests on
    whichever version the reviewer happened to have, and an amendment between
    then and now is invisible."""

    binding_basis: str = ""
    """WHY THIS BINDS, in a sentence. BK-67-AC3's control is *treat a
    historical court cohort label as proof of binding status* -- so a court
    name is not an answer here, and the field is prose because the reasoning
    is the thing being reviewed."""

    verdict: Verdict = Verdict.NOT_ASSESSED
    reviewed_by: str = ""
    reservation: str = ""

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if blank(self.source_id) or blank(self.locator):
            out.append(f"the {self.kind.value} premise names no primary "
                       f"source and locator")
        if blank(self.source_version):
            out.append(f"the {self.kind.value} premise does not say which "
                       f"version of its source was read; an amendment since "
                       f"is invisible")
        if self.kind is PremiseKind.BINDING_AUTHORITY and blank(
                self.binding_basis):
            out.append("nothing says WHY this authority binds. A court's name "
                       "is not a basis, and a historical cohort label is not "
                       "proof of binding status")
        if self.verdict is Verdict.NOT_ASSESSED:
            out.append(f"nobody assessed the {self.kind.value} premise")
        elif blank(self.reviewed_by):
            out.append(f"the {self.kind.value} premise carries a verdict and "
                       f"no reviewer")
        return tuple(out)


@refuses_blank_text()
@dataclass(frozen=True)
class Arithmetic:
    """A calculation, and THE PREMISE IT ASSUMED.

    `assessed_on` is required and is the whole point: a limitation computed
    perfectly from an unsupported accrual rule is not a partially right
    answer, and reporting the calculation as passing is how the wrong date
    reaches a cause list.
    """

    what: str
    assessed_on: PremiseKind
    verdict: Verdict = Verdict.NOT_ASSESSED
    reviewed_by: str = ""

    def conditional_on(self, premises: tuple[Premise, ...]) -> str:
        """Why this calculation's verdict does not stand, or "".

        NOT A DOWNGRADE. An arithmetic verdict whose premise failed is not a
        pass at lower confidence; there is nothing for it to be a verdict
        about.
        """
        premise = next((p for p in premises if p.kind is self.assessed_on),
                       None)
        if premise is None:
            return (f"{self.what!r} was assessed on a "
                    f"{self.assessed_on.value} premise this review does not "
                    f"record")
        if not premise.verdict.supports_reliance:
            return (f"{self.what!r} is arithmetically {self.verdict.value} on "
                    f"a {self.assessed_on.value} premise that is "
                    f"{premise.verdict.value}. The calculation is not a "
                    f"verdict about the answer")
        return ""


@refuses_blank_text()
@dataclass(frozen=True)
class Approval:
    """WHAT WAS APPROVED, FOR WHAT, AND UNDER WHICH CONFIGURATION.

    `covers` and the four identities together are the scope. Approval does not
    travel: not to another matter family, not to a later corpus, and -- the
    one that gets assumed -- not to a later model. A model that scores better
    on average can fail differently on the cases that matter, which is the
    whole reason the comparison in BK-91-AC4 exists.
    """

    approval_id: str
    covers: tuple[str, ...] = ()
    corpus_identity: str = ""
    model_identity: str = ""
    prompt_identity: str = ""
    product_identity: str = ""
    approved_by: str = ""
    approved_at: str = ""
    valid_until: str = ""
    reservations: tuple[str, ...] = ()
    withdrawn_at: str = ""

    def still_current(self, *, covering: str, corpus: str, model: str,
                      prompt: str, product: str, today: str = "") -> str:
        """Why this approval does not cover the thing in front of you, or "".

        EVERY MISMATCH IS NAMED SEPARATELY, because the next step differs: a
        corpus change calls for a re-run on held-out scenarios, and a scope
        miss calls for a review that was never done.
        """
        if not blank(self.withdrawn_at):
            return f"this approval was withdrawn on {self.withdrawn_at}"
        if covering not in self.covers:
            return (f"{covering!r} is not among the matter families this "
                    f"approval covers ({', '.join(self.covers) or 'none'})")
        for name, was, now in (("corpus", self.corpus_identity, corpus),
                               ("model", self.model_identity, model),
                               ("prompt", self.prompt_identity, prompt),
                               ("product", self.product_identity, product)):
            if was != now:
                return (f"the {name} changed since this was approved "
                        f"({was or 'not recorded'} -> {now or 'not recorded'})"
                        f"; approval is not inherited across it")
        if not blank(self.valid_until) and today and today > self.valid_until:
            return (f"this approval ran out on {self.valid_until} and has not "
                    f"been renewed")
        return ""


@refuses_blank_text()
@dataclass(frozen=True)
class LegalReviewRecord:
    """One qualified review, carrying the admissibility record rather than
    restating it."""

    review_id: str
    study: Study
    premises: tuple[Premise, ...] = ()
    arithmetic: tuple[Arithmetic, ...] = ()
    approval: Approval | None = None
    critical_failures: tuple[str, ...] = field(default_factory=tuple)
    """Named critical failures the reviewers found, beyond the per-task
    severities. Kept separately because a reviewer can find one in a matter
    they otherwise scored well."""


def refuse_approval(record: LegalReviewRecord) -> tuple[str, ...]:
    """EVERY REASON THIS REVIEW CANNOT CONFER APPROVAL. BK-67-AC1 to AC4.

    It begins with `refuse_conclusion`, because a review that is not
    admissible cannot approve anything, and repeating those seven refusals
    here would be a second copy of the thing most likely to be relaxed.
    """
    out: list[str] = list(refuse_conclusion(record.study))

    if not record.premises:
        out.append("no governing legal premise was reviewed, so what the "
                   "advice rests on was never assessed")
    for premise in record.premises:
        out.extend(premise.problems())
    for row in record.arithmetic:
        why = row.conditional_on(record.premises)
        if why:
            out.append(why)
        if row.verdict is Verdict.NOT_ASSESSED:
            out.append(f"{row.what!r} carries no verdict")

    for failure in record.critical_failures:
        out.append(f"CRITICAL: {failure}. A critical legal failure blocks "
                   f"conformance regardless of the average")

    people = [r for r in record.study.reviewers
              if not blank(str(r.get("qualification", "")))
              and not blank(str(r.get("evidence", "")))]
    if not people:
        out.append("no reviewer with evidenced qualification is recorded. A "
                   "review is a person's judgement, and this product cannot "
                   "supply one")
    return tuple(out)


def critical(record: LegalReviewRecord) -> tuple[str, ...]:
    """Every critical failure, from both places one can be recorded."""
    return tuple(record.critical_failures) + tuple(
        o.task for o in record.study.observations if o.severity.blocks)


@refuses_blank_text()
@dataclass(frozen=True)
class Comparison:
    """Planned orchestration against an adaptive lead. BK-91-AC4.

    THE BUDGETS AND THE FAMILIES ARE MATCHED OR THERE IS NO COMPARISON. Its
    negative control is *omit difficult matter families or present a larger
    spend as proof of architectural improvement*, and both are arithmetic
    rather than judgement -- so both are checked here rather than left to a
    reviewer to notice.
    """

    families: tuple[str, ...] = ()
    planned_spend: dict = field(default_factory=dict)
    adaptive_spend: dict = field(default_factory=dict)
    planned_families: tuple[str, ...] = ()
    adaptive_families: tuple[str, ...] = ()
    runs_each: int = 0
    judged_by: str = ""
    judged_model: str = ""
    """WHO GRADED IT. Its first negative control is *grade the tested model
    with itself*, and that is a comparison of a model with its own opinion of
    itself."""

    tested_model: str = ""

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.families:
            out.append("no matter family is declared, so there is nothing the "
                       "comparison is about")
        missing_planned = set(self.families) - set(self.planned_families)
        missing_adaptive = set(self.families) - set(self.adaptive_families)
        if missing_planned or missing_adaptive:
            out.append(
                "the two arms did not run the same families; omitted: "
                + "; ".join(sorted(missing_planned | missing_adaptive)))
        if self.runs_each < 2:
            out.append("a single run each cannot separate an improvement from "
                       "a difference between two runs")
        if blank(self.judged_by):
            out.append("nobody is recorded as having judged this")
        if self.judged_model and self.judged_model == self.tested_model:
            out.append("the tested model graded itself, which is a "
                       "comparison of a model with its own opinion of itself")
        for name in ("cost_usd", "tokens", "elapsed_ms"):
            planned = self.planned_spend.get(name)
            adaptive = self.adaptive_spend.get(name)
            if planned is None or adaptive is None:
                out.append(f"{name} is not recorded for both arms, so a "
                           f"larger spend cannot be told from a better result")
        return tuple(out)

    def refuses_improvement_claim(self) -> str:
        """Why no improvement may be claimed from this, or ""."""
        problems = self.problems()
        if problems:
            return ("this comparison cannot support an improvement claim: "
                    + "; ".join(problems))
        return ""


def withdraw(approval: Approval, *, at: str, because: str) -> Approval:
    """Withdraw it, KEEPING IT. The historical review stays evidence of what
    was true when it was made."""
    if blank(at) or blank(because):
        raise ValueError("a withdrawal records when and why")
    if not blank(approval.withdrawn_at):
        return approval
    return replace(approval, withdrawn_at=at,
                   reservations=approval.reservations + (because,))


def projection(record: LegalReviewRecord, *, today: str = "") -> dict:
    """What a reader is shown. THE RESERVATIONS TRAVEL WITH IT.

    BK-67-AC1 asks for material reservations kept VISIBLE, and a reservation
    filed behind a green verdict is a reservation nobody reads.
    """
    blockers = refuse_approval(record)
    approval = record.approval
    return {
        "review_id": record.review_id,
        "study": record.study.study_id,
        "premises": [{"kind": p.kind.value, "verdict": p.verdict.value,
                      "source": f"{p.source_id} {p.locator}".strip()
                                or "NOT RECORDED",
                      "version": p.source_version or "NOT RECORDED",
                      "reservation": p.reservation}
                     for p in record.premises],
        "arithmetic": [{"what": a.what, "verdict": a.verdict.value,
                        "conditional_on": a.assessed_on.value,
                        "stands": not a.conditional_on(record.premises)}
                       for a in record.arithmetic],
        "critical": list(critical(record)),
        "approves": not blockers,
        "blockers": list(blockers),
        "reservations": list(approval.reservations) if approval else [],
        "approval": ({"approval_id": approval.approval_id,
                      "covers": list(approval.covers),
                      "withdrawn_at": approval.withdrawn_at}
                     if approval else None),
        "said": ("A review is a person's judgement recorded here, never one "
                 "this product produced. Nothing on this record was scored by "
                 "the thing being reviewed."),
    }


#: Severity is re-exported so a caller grading a legal review reaches for the
#: same three levels a usability study uses. TWO VOCABULARIES FOR ONE IDEA is
#: how a critical failure becomes a four out of five somewhere else.
__all__ = [
    "Approval", "Arithmetic", "Comparison", "LegalReviewRecord", "Premise",
    "PremiseKind", "Severity", "Verdict", "critical", "projection",
    "refuse_approval", "withdraw",
]
