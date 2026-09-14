"""A REVIEW THAT CANNOT BE ADJUSTED AFTER IT IS SCORED. BK-66, BK-67, BK-91.
P34 and P35.

    from nm.domain.review import Freeze, Study, Observation, refuse_conclusion

WHAT THIS IS FOR
------------------
`docs/blueprint/evaluations.json` already declares five manual review
protocols -- REVIEW-USABILITY for BK-66-AC3, REVIEW-LEGAL for BK-67-AC2 and
AC3, and three others -- each with a reviewer role, required inputs, tasks,
failure conditions and required output fields. It declares them in prose, and
nothing runs them.

    That is the failure this repository opens by describing: *a hundred good
    rules with no runner, so they became aspirations. A rule you cannot run is
    not a requirement.*

So this is the runner. It does not decide whether the product is good, and it
cannot: that is what a qualified advocate and a representative user are for.
What it decides is whether a review is ADMISSIBLE -- whether the population was
real, whether the rubric was fixed before anybody saw a result, whether a
critical failure was averaged away, and whether the thing being called an
advocate's judgement was one.

THE SEVEN REFUSALS, AND WHY EACH IS A SEPARATE ONE
----------------------------------------------------
Every one of them is a way to produce a favourable number from an unfavourable
run, and each is available at a different moment:

    an empty population              nothing was measured; the average of no
                                     tasks is not a high score
    tasks changed after observation  the study answered a different question
                                     from the one it reports
    thresholds moved after scoring   the bar was drawn round the result
    disagreement not recorded        two reviewers who differed were made to
                                     agree by whoever wrote it up
    a model judge read as an advocate  the cheapest substitution available,
                                     and the one that looks identical
    a demo fixture read as a user    the population is the thing that makes a
                                     study representative
    a critical failure averaged away an invented authority is not offset by
                                     nine good answers

A MODEL MAY BUILD THIS AND MAY NOT BE THE REVIEWER
----------------------------------------------------
`Observer.MODEL_JUDGE` exists so that a model-scored result can be RECORDED --
it is useful, and hiding it would push it into being recorded as something
else. What it may never do is satisfy a criterion that requires
`counsel_review` or an advocate observation, and `refuse_conclusion` says so by
counting the two populations separately rather than by trusting a label.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.text import blank, clean, refuses_blank_text


class Observer(str, Enum):
    """WHO PRODUCED A JUDGEMENT. The distinction the whole file turns on.

    `MODEL_JUDGE` is recorded rather than hidden, because a result that cannot
    be recorded honestly gets recorded dishonestly. It is simply not counted
    towards anything that requires a person.
    """

    ADVOCATE = "advocate"
    """A representative practising advocate, observed doing the task."""

    QUALIFIED_REVIEWER = "qualified_reviewer"
    """A qualified reviewer scoring served output against a rubric."""

    MODEL_JUDGE = "model_judge"
    """A model scoring a model. Useful, cheap, and not a person."""

    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Observer":
        return cls.NOT_RECORDED

    @property
    def is_a_person(self) -> bool:
        """Written once so no report decides for itself."""
        return self in (Observer.ADVOCATE, Observer.QUALIFIED_REVIEWER)


class Severity(str, Enum):
    """How badly one task went. CRITICAL IS NOT A HIGH NUMBER ON A SCALE.

    It is a different kind of finding: an invented authority, a leaked
    confidence, decisive advice with nothing under it. Averaging is defined for
    the other two and is not defined for this one -- which is why it is an enum
    member and not a score of 5.
    """

    NONE = "none"
    MINOR = "minor"
    MATERIAL = "material"
    CRITICAL = "critical"

    @classmethod
    def not_established(cls) -> "Severity":
        return cls.NONE

    @property
    def blocks(self) -> bool:
        return self is Severity.CRITICAL


class Stratum(str, Enum):
    """Which population a participant or matter came from.

    `DEMO_FIXTURE` is the one that must never be counted as representative,
    and it is named rather than excluded so that a study which used one has to
    say so instead of quietly presenting it as a user.
    """

    REPRESENTATIVE = "representative"
    HELD_OUT = "held_out"
    DEMO_FIXTURE = "demo_fixture"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Stratum":
        return cls.NOT_RECORDED

    @property
    def counts_as_representative(self) -> bool:
        return self in (Stratum.REPRESENTATIVE, Stratum.HELD_OUT)


def digest(value) -> str:
    """A stable fingerprint of what was frozen."""
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str,
        separators=(",", ":")).encode("utf8")).hexdigest()


@refuses_blank_text()
@dataclass(frozen=True)
class Freeze:
    """THE TASKS, THE POPULATION, THE RUBRIC AND THE THRESHOLDS, BEFORE ANY OF
    IT IS SCORED.

    `frozen_at` and `manifest` together are what make "the bar was drawn round
    the result" a checkable statement rather than an accusation: the manifest
    hashes the four, and a study that scores against a different manifest is
    answering a different question from the one it reports.
    """

    protocol_id: str
    tasks: tuple[str, ...] = ()
    strata: tuple[str, ...] = ()
    rubric: tuple[str, ...] = ()
    thresholds: dict = field(default_factory=dict)
    frozen_at: str = ""
    frozen_by: str = ""

    @property
    def manifest(self) -> str:
        return digest({"protocol": self.protocol_id, "tasks": self.tasks,
                       "strata": self.strata, "rubric": self.rubric,
                       "thresholds": self.thresholds})

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.tasks:
            out.append("no tasks are frozen, so there is nothing to have "
                       "measured")
        if not self.strata:
            out.append("no participant or matter strata are frozen, so "
                       "nothing says who or what this was meant to represent")
        if not self.rubric:
            out.append("no rubric is frozen, so what counts as success was "
                       "decided somewhere else")
        if not self.thresholds:
            out.append("no pass threshold is frozen, so the bar can be drawn "
                       "round whatever the result turns out to be")
        if blank(self.frozen_at) or blank(self.frozen_by):
            out.append("nobody and no time is recorded for the freeze, so "
                       "'before scoring' is a claim rather than a fact")
        return tuple(out)


@refuses_blank_text()
@dataclass(frozen=True)
class Observation:
    """One task, as it actually went.

    `by` IS NOT DECORATION. A study that records who produced each judgement
    can be counted two ways; one that does not can only be believed.
    """

    task: str
    by: Observer = Observer.NOT_RECORDED
    stratum: Stratum = Stratum.NOT_RECORDED
    succeeded: bool = False
    severity: Severity = Severity.NONE
    assisted: bool = False
    """Whether somebody had to help. A completed-with-help task is not a
    failure and is certainly not an unassisted success."""

    seconds: int = 0
    retyped: int = 0
    """How much the participant had to type again. BK-66-AC2's *without
    compulsory repetitive typing* is measured, not asserted."""

    source_navigated: bool = False
    note: str = ""

    @property
    def counts_for_a_person(self) -> bool:
        return self.by.is_a_person and self.stratum.counts_as_representative


@refuses_blank_text()
@dataclass(frozen=True)
class Disagreement:
    """Two reviewers who differed, and what was done about it.

    KEPT, NEVER RESOLVED BY DELETION. `evaluations.json` says it in terms:
    *adjudicate material disagreements without deleting original labels*.
    """

    task: str
    between: tuple[str, ...]
    about: str
    adjudicated_by: str = ""
    outcome: str = ""

    @property
    def open(self) -> bool:
        return blank(self.adjudicated_by) or blank(self.outcome)


@refuses_blank_text()
@dataclass(frozen=True)
class Study:
    """One run of one protocol, and everything admissibility depends on."""

    study_id: str
    protocol_id: str
    freeze: Freeze
    observations: tuple[Observation, ...] = ()
    disagreements: tuple[Disagreement, ...] = ()
    reviewers: tuple[dict, ...] = ()
    """Each: identity, qualification, evidence of it, conflict declaration."""

    product_identity: str = ""
    """THE EXACT THING REVIEWED. A review of a tree nobody can name is a
    review of nothing in particular, and it silently becomes a review of
    whatever ships next."""

    scored_at: str = ""
    scoring_manifest: str = ""
    """The freeze manifest AS IT STOOD WHEN SCORING BEGAN. It is recorded
    separately so that a later edit to the freeze is visible as a mismatch
    rather than absorbed."""

    superseded_by: str = ""

    def by_people(self) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.counts_for_a_person)

    def critical(self) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.severity.blocks)

    def success_rate(self) -> float | None:
        """Over the PEOPLE's observations, or None where there are none.

        NOT ZERO AND NOT ONE. A study with no human observations has no
        success rate, and returning a number would make "nobody was observed"
        arithmetically indistinguishable from "everybody failed".
        """
        people = self.by_people()
        if not people:
            return None
        return sum(1 for o in people if o.succeeded and not o.assisted) / len(people)


def refuse_conclusion(study: Study) -> tuple[str, ...]:
    """EVERY REASON THIS STUDY CANNOT SUPPORT A CONCLUSION. BK-66-AC3,
    BK-67-AC2, BK-91-AC4.

    A population rather than a boolean, because "not admissible" sends the
    reader looking and the one they find is whichever they thought of first.
    """
    out: list[str] = list(study.freeze.problems())

    if not study.observations:
        out.append("nothing was observed. The average of no tasks is not a "
                   "high score")
    people = study.by_people()
    if not people:
        out.append("no observation was produced by a person from a "
                   "representative or held-out population, so nothing here "
                   "can close a criterion that requires one")

    # THE MANIFEST, WHICH IS HOW "AFTER THE RUN" BECOMES CHECKABLE.
    if blank(study.scoring_manifest):
        out.append("nothing records which frozen manifest was scored against, "
                   "so whether the tasks or thresholds moved afterwards "
                   "cannot be established")
    elif study.scoring_manifest != study.freeze.manifest:
        out.append(
            "the tasks, population, rubric or thresholds changed after "
            "scoring began: scored against "
            f"{study.scoring_manifest[:12]}..., now "
            f"{study.freeze.manifest[:12]}...")

    for task in {o.task for o in study.observations} - set(study.freeze.tasks):
        out.append(f"{task!r} was observed and is not one of the frozen "
                   f"tasks, so the study answered a question it does not "
                   f"report")

    demo = [o.task for o in study.observations
            if o.stratum is Stratum.DEMO_FIXTURE]
    if demo and not people:
        out.append(
            "every observation came from a demonstration fixture. A fixture "
            "is not a representative user, and a study of one measures the "
            "fixture: " + "; ".join(sorted(set(demo))))

    judged = [o.task for o in study.observations
              if o.by is Observer.MODEL_JUDGE]
    if judged and not people:
        out.append(
            "every observation was produced by a model judge. A model scoring "
            "a model is useful and is not an advocate: "
            + "; ".join(sorted(set(judged))))

    unattributed = [o.task for o in study.observations
                    if o.by is Observer.NOT_RECORDED]
    if unattributed:
        out.append("these observations do not record who produced them: "
                   + "; ".join(sorted(set(unattributed))))

    for row in study.critical():
        out.append(
            f"{row.task!r} is a CRITICAL failure and blocks regardless of the "
            f"average. {row.note or 'No account of it is recorded.'}")

    for row in study.disagreements:
        if row.open:
            out.append(f"the disagreement about {row.task!r} between "
                       f"{', '.join(row.between)} is unresolved and no "
                       f"adjudication is recorded")

    if blank(study.product_identity):
        out.append("nothing records WHAT was reviewed, so this review cannot "
                   "be tied to a version of the product")

    for index, reviewer in enumerate(study.reviewers):
        for wanted in ("identity", "qualification", "evidence",
                       "conflict_declaration"):
            if blank(str(reviewer.get(wanted, ""))):
                out.append(f"reviewer {index + 1} does not record their "
                           f"{wanted.replace('_', ' ')}")
    return tuple(out)


def refuse_average(study: Study) -> str:
    """Why an average must not be reported for this study, or "".

    BK-67-AC2's negative control: *average away invented authority, material
    confidentiality failure or unsupported decisive advice*. The refusal is
    separate from `refuse_conclusion` because a study can be perfectly
    admissible and still have a critical failure in it -- and that is exactly
    the case where somebody reaches for the mean.
    """
    critical = study.critical()
    if critical:
        return (f"{len(critical)} critical failure(s) are recorded, and a "
                f"critical failure is not a low score on a scale: "
                + "; ".join(sorted(o.task for o in critical)))
    if study.success_rate() is None:
        return ("no person from a representative population was observed, so "
                "there is no rate to report")
    return ""


#: WHAT INVALIDATES AN APPROVAL. BK-67-AC4.
#:
#: Named once, so the reassessment trigger and the thing that records a change
#: cannot drift. Every one of these was, in the previous build, a thing that
#: changed while an approval stayed green.
INVALIDATED_BY: tuple[str, ...] = (
    "facts", "law", "corpus", "model", "prompt", "tools", "policy",
)


def invalidated(study: Study, *, changed: tuple[str, ...]) -> tuple[str, ...]:
    """Which recorded changes invalidate this study's conclusion.

    AN UNRECOGNISED CHANGE INVALIDATES. A change nobody classified is a change
    nobody assessed, and reading it as harmless is the assumption that lets an
    approval outlive the thing it was about.
    """
    if not changed:
        return ()
    out: list[str] = []
    for what in changed:
        key = clean(what).lower()
        if key in INVALIDATED_BY:
            out.append(f"the {key} changed since this was scored")
        else:
            out.append(f"{what!r} changed and is not a classified kind of "
                       f"change, so whether it affects this review is not "
                       f"established")
    return tuple(out)


def supersede(study: Study, *, by: str) -> Study:
    """Replace it, KEEPING IT. BK-67-AC4's *superseded reviews remain
    historical evidence*.

    A deleted review makes the work it approved look unreviewed, and a review
    that is quietly overwritten makes the approval look continuous when it was
    re-earned.
    """
    if blank(by):
        raise ValueError("a superseding review names itself")
    return replace(study, superseded_by=by)


def projection(study: Study) -> dict:
    """What a reader is shown, INCLUDING WHY IT MAY NOT BE RELIED ON."""
    blockers = refuse_conclusion(study)
    rate = study.success_rate()
    return {
        "study_id": study.study_id, "protocol_id": study.protocol_id,
        "product_identity": study.product_identity or "NOT RECORDED",
        "frozen_manifest": study.freeze.manifest,
        "scored_against": study.scoring_manifest or "NOT RECORDED",
        "observations": len(study.observations),
        "by_people": len(study.by_people()),
        "by_model_judge": sum(1 for o in study.observations
                              if o.by is Observer.MODEL_JUDGE),
        "critical": [o.task for o in study.critical()],
        "open_disagreements": [d.task for d in study.disagreements if d.open],
        # NONE, NEVER ZERO. A study with no human observations has no rate,
        # and a zero would be arithmetically indistinguishable from total
        # failure.
        "success_rate": rate,
        "average_refused": refuse_average(study),
        "admissible": not blockers,
        "blockers": list(blockers),
        "superseded_by": study.superseded_by,
        "said": ("This is a record of a review, not a review. Nothing here "
                 "was scored by this product, and an admissible study is one "
                 "that may be relied on -- not one that passed."),
    }
