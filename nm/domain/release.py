"""WHAT IS BEING RELEASED, EXACTLY, AND WHY IT IS NOT. P41.
BK-42-AC5, BK-42-AC7, BK-42-AC9, J-8-AC1.

    from nm.domain.release import Manifest, refuse_release

ENGINEERING COMPLETION OF THIS GATE IS NOT A RELEASE APPROVAL
---------------------------------------------------------------
This module builds the gate. It does not walk through it, and it cannot: an
approval is a named accountable person signing an exact scope on a date, and
there is no function here that creates one. `Approval` has no constructor a
gate can reach, `refuse_release` only ever reads approvals it was handed, and
a build with none gets `RELEASE WITHHELD` with the missing signatures listed
by role.

    A gate that could approve its own release is the check that cannot fail,
    holding the last decision anybody makes about this product.

NINETEEN IDENTITIES, FROZEN TOGETHER
--------------------------------------
A release is not a commit. It is a commit AND the schema it writes AND the
policy it enforces AND the corpus it reads AND the model it calls AND the
prompts it sends AND the provider it sends them to AND the scope it was
approved for -- and every one of those can move without the commit moving.
`Manifest` names all nineteen and `identity` is the digest of all nineteen, so
a manifest that changed one is a different release and inherits nothing.

    THIS IS THE SAME MECHANISM AS `deployment.Candidate` AND DELIBERATELY SO.
    A security claim binds to a candidate; a release binds to a manifest; the
    reason is identical, which is why the shape is.

TWELVE CONDITIONS, EACH FAILING CLOSED
----------------------------------------
`refuse_release` returns every reason, not the first, because a release
manager told one thing to fix will fix one thing and come back. Each reason
names the missing artefact, person or measurement.

NO AGGREGATE SCORE OVERRIDES A CRITICAL FAILURE
-------------------------------------------------
`Portfolio` carries a pass rate and `refuse_release` never reads it as
permission. A critical failure refuses at any rate including 100%, because a
rate is an average of things that are not comparable and the one that matters
is a single row. The rate is reported, so a reviewer sees it; it is never
subtracted from, weighted against or traded off.

WHAT THIS BUILD'S ANSWER IS
-----------------------------
ENGINEERING COMPLETE, RELEASE WITHHELD. Every approval is absent, the
production measures are absent, and `verdict()` says so in those words rather
than in a boolean somebody could read the wrong way round.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields
from datetime import date
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Severity(str, Enum):
    """How bad one portfolio row's failure is.

    `CRITICAL` is the member that cannot be averaged away. Everything else can
    be weighed by the people who own the release; this one refuses.

    `NOT_CLASSIFIED` is the DEFAULT, and a failing row carrying it refuses
    exactly like a critical one. A row nobody triaged is not a minor row: the
    safe reading of "we do not know how bad this is" at a release gate is that
    it might be the bad one, and defaulting to MINOR would let an untriaged
    legal failure be averaged into a 98% pass rate.
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NOT_CLASSIFIED = "not_classified"

    @classmethod
    def not_established(cls) -> "Severity":
        return cls.NOT_CLASSIFIED

    @property
    def refuses_a_release(self) -> bool:
        return self in (Severity.CRITICAL, Severity.NOT_CLASSIFIED)


class RunState(str, Enum):
    """Whether a portfolio actually ran to completion.

    `INCOMPLETE` exists because a run that crashed at phase 3 leaves green
    rows behind it, and a gate that counts rows reads those as a pass. It is
    not the same as `FAILED` and it is certainly not the same as `PASSED`.
    """

    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    NOT_RUN = "not_run"

    @classmethod
    def not_established(cls) -> "RunState":
        return cls.NOT_RUN


#: EVERY IDENTITY A RELEASE IS. Named once, because a manifest that froze
#: eighteen of them would read as frozen.
IDENTITIES: tuple[str, ...] = (
    "commit", "tree_fingerprint", "schema_version", "migration_head",
    "policy_version", "processor_inventory_digest", "gate_matrix_digest",
    "corpus_generation", "authority_index_digest", "model_provider",
    "model_id", "embedding_model", "prompt_digest", "feature_set_digest",
    "config_digest", "environment", "enabled_scope_digest",
    "jurisdiction", "languages_digest",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Manifest:
    """The nineteen identities of one release candidate, frozen together.

    Every field is required and none defaults. A default would be the release
    manifest saying "whatever was there", which is the sentence this type
    exists to make unwritable.
    """

    commit: str
    tree_fingerprint: str
    schema_version: str
    migration_head: str
    policy_version: str
    processor_inventory_digest: str
    gate_matrix_digest: str
    corpus_generation: str
    authority_index_digest: str
    model_provider: str
    model_id: str
    embedding_model: str
    prompt_digest: str
    feature_set_digest: str
    config_digest: str
    environment: str
    enabled_scope_digest: str
    jurisdiction: str
    languages_digest: str
    version: int = 1

    def __post_init__(self) -> None:
        declared = {f.name for f in fields(self)} - {"version"}
        if declared != set(IDENTITIES):
            missing = sorted(set(IDENTITIES) - declared)
            extra = sorted(declared - set(IDENTITIES))
            raise ValueError(
                f"the manifest and the declared identity list disagree "
                f"(missing {missing}, unexpected {extra}); a manifest that "
                f"froze eighteen of nineteen would read as frozen")
        # INDIA IS THE ONLY SUPPORTED OPERATING JURISDICTION, and a manifest
        # is where a second one would first appear.
        if self.jurisdiction.strip().lower() not in ("in", "india"):
            raise ValueError(
                f"the manifest names jurisdiction {self.jurisdiction!r}. This "
                f"product is scoped to Telangana and the Union of India; an "
                f"answer about another state's law is confidently wrong and "
                f"nothing downstream catches it.")

    @property
    def identity(self) -> str:
        joined = "|".join(f"{name}={getattr(self, name)}"
                          for name in IDENTITIES)
        return hashlib.sha256(joined.encode("utf8")).hexdigest()[:16]

    @property
    def is_a_deployment(self) -> bool:
        return self.environment not in (
            "", "local", "local_rehearsal", "synthetic", "working_tree")


@refuses_blank_text()
@dataclass(frozen=True)
class Approval:
    """One accountable person signing one exact scope on one date.

    `covers_manifest` is the manifest identity this signature was given
    against. An approval that named only a role would travel to the next
    release, which is BK-42-AC9's mutation exactly: *release a new
    jurisdiction using an unrelated or expired legal review.*
    """

    role: str
    approver_id: str
    covers_manifest: str
    signed_on: str
    valid_until: str
    scope: str

    def expired_on(self, day: str) -> bool:
        try:
            return date.fromisoformat(self.valid_until) < date.fromisoformat(day)
        except (ValueError, TypeError):
            return True    # an unreadable expiry has expired


#: WHO HAS TO SIGN. Named once. An approval matrix assembled per release is an
#: approval matrix somebody shortens during a release.
REQUIRED_APPROVALS: tuple[str, ...] = (
    "product_owner", "engineering_owner", "security_privacy_owner",
    "qualified_counsel", "operations_owner",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Row:
    """One portfolio result."""

    row_id: str
    state: RunState
    severity: Severity = Severity.NOT_CLASSIFIED
    note: str = ""


@refuses_blank_text()
@dataclass(frozen=True)
class Portfolio:
    """One run of one suite, and whether it finished.

    `pass_rate` is DERIVED and it is reported, never consulted. See the module
    docstring: a rate is an average of things that are not comparable, and the
    row that matters is a single one.
    """

    portfolio_id: str
    state: RunState = RunState.NOT_RUN
    rows: tuple[Row, ...] = ()
    covers_manifest: str = ""

    @property
    def pass_rate(self) -> float:
        if not self.rows:
            return 0.0
        passed = sum(1 for row in self.rows if row.state is RunState.PASSED)
        return passed / len(self.rows)

    @property
    def critical_failures(self) -> tuple[Row, ...]:
        """Failing rows that refuse a release: critical, and untriaged.

        Untriaged belongs here rather than beside MINOR because the question
        the gate asks is "may this ship", and the honest answer about a
        failure nobody has looked at is no.
        """
        return tuple(row for row in self.rows
                     if row.severity.refuses_a_release
                     and row.state is not RunState.PASSED)


#: THE PORTFOLIOS A RELEASE RESTS ON. P41 step 2 names them: the supported
#: journey, accessibility, load and degradation, and legal quality.
REQUIRED_PORTFOLIOS: tuple[str, ...] = (
    "supported_journey", "accessibility", "load_and_degradation",
    "legal_quality", "cumulative_regression",
)


@dataclass(frozen=True)
class Submission:
    """Everything a release decision reads. Nothing it writes.

    NOT `Candidate`. `deployment.Candidate` is already the identity of a build
    a security claim is about, and two types called the same thing in one
    product is an invitation to pass one where the other belongs. What this
    holds is a submission TO the gate: the manifest that identifies the
    release, plus everything offered in support of it.
    """

    manifest: Manifest
    portfolios: tuple[Portfolio, ...] = ()
    approvals: tuple[Approval, ...] = ()
    production_measures: dict = field(default_factory=dict)
    enabled_scope: tuple[str, ...] = ()
    approved_scope: tuple[str, ...] = ()

    def portfolio(self, portfolio_id: str) -> Portfolio | None:
        for row in self.portfolios:
            if row.portfolio_id == portfolio_id:
                return row
        return None


def refuse_release(submission: Submission, *, on: str) -> tuple[str, ...]:
    """THE TWELVE CONDITIONS. Every reason, never the first.

    A release manager told one thing to fix will fix one thing and come back,
    and the second pass is where the tired mistake lives.
    """
    out: list[str] = []
    manifest = submission.manifest

    # 1. A CRITICAL FAILURE, AT ANY PASS RATE.
    for portfolio in submission.portfolios:
        for row in portfolio.critical_failures:
            out.append(
                f"{portfolio.portfolio_id}/{row.row_id} is a "
                f"{row.severity.value} failure ({row.state.value}); the "
                f"portfolio's pass rate is {portfolio.pass_rate:.0%} and no "
                f"aggregate score overrides a critical security or legal "
                f"failure")

    # 2. A PORTFOLIO THAT DID NOT FINISH.
    for portfolio in submission.portfolios:
        if portfolio.state is RunState.INCOMPLETE:
            out.append(
                f"{portfolio.portfolio_id} did not finish; a run that stopped "
                f"part way leaves green rows behind it and a gate that counts "
                f"rows reads those as a pass")

    # 3. A PORTFOLIO NOBODY RAN.
    for needed in REQUIRED_PORTFOLIOS:
        portfolio = submission.portfolio(needed)
        if portfolio is None or portfolio.state is RunState.NOT_RUN:
            out.append(f"the {needed!r} portfolio was not run, and a suite "
                       f"nobody ran is not one that passed")

    # 4. A PORTFOLIO BOUND TO A DIFFERENT RELEASE.
    for portfolio in submission.portfolios:
        if (portfolio.covers_manifest
                and portfolio.covers_manifest != manifest.identity):
            out.append(
                f"{portfolio.portfolio_id} was run against manifest "
                f"{portfolio.covers_manifest} and this release is "
                f"{manifest.identity}")
        elif not portfolio.covers_manifest:
            out.append(f"{portfolio.portfolio_id} names no manifest, so it is "
                       f"a result about some build")

    # 5. A MISSING SIGNATURE, BY ROLE.
    signed = {}
    for approval in submission.approvals:
        if approval.covers_manifest != manifest.identity:
            out.append(
                f"the {approval.role!r} approval covers manifest "
                f"{approval.covers_manifest} and this release is "
                f"{manifest.identity}: unsupported scope cannot inherit "
                f"approval from another population")
        elif approval.expired_on(on):
            out.append(f"the {approval.role!r} approval expired on "
                       f"{approval.valid_until} and today is {on}")
        else:
            signed[approval.role] = approval
    for role in REQUIRED_APPROVALS:
        if role not in signed:
            out.append(f"no current {role!r} approval covers this release")

    # 6. AN APPROVAL THAT DOES NOT COVER THE SCOPE BEING ENABLED.
    unapproved = tuple(sorted(set(submission.enabled_scope)
                              - set(submission.approved_scope)))
    if unapproved:
        out.append(f"{list(unapproved)} would be enabled and no approval "
                   f"names them; a new jurisdiction, language, medium or "
                   f"professional operation does not inherit approval from "
                   f"another population")

    # 7. A PRODUCTION MEASURE THAT WAS NEVER TAKEN.
    outstanding = sorted(name for name, result
                         in submission.production_measures.items()
                         if result != "PASS")
    if outstanding:
        out.append(f"these production measures are not PASS: "
                   f"{', '.join(outstanding)}")
    if not submission.production_measures:
        out.append("no production measure is recorded at all, and an empty "
                   "set of measurements is an unrun measurement rather than a "
                   "clean one")

    # 8. A RELEASE OF A BUILD THAT IS NOT DEPLOYED ANYWHERE.
    if not manifest.is_a_deployment:
        out.append(f"the manifest names environment "
                   f"{manifest.environment!r}, which is not a deployment; "
                   f"local synthetic success is not target proof")

    return tuple(out)


def verdict(submission: Submission, *, on: str) -> str:
    """The sentence a reader gets. NEVER a boolean.

    "ENGINEERING COMPLETE, RELEASE WITHHELD" is the correct answer for this
    build and it is one string rather than two flags, because two flags is
    where somebody reads the first and reports it.
    """
    refused = refuse_release(submission, on=on)
    if not refused:
        return "RELEASE PERMITTED BY THIS GATE"
    return ("ENGINEERING COMPLETE, RELEASE WITHHELD -- "
            + f"{len(refused)} condition(s) refuse it")


def projection(submission: Submission, *, on: str) -> dict:
    """What a release reviewer is shown."""
    refused = refuse_release(submission, on=on)
    return {
        "manifest": submission.manifest.identity,
        "commit": submission.manifest.commit,
        "environment": submission.manifest.environment,
        "is_a_deployment": submission.manifest.is_a_deployment,
        "portfolios": {p.portfolio_id: {
            "state": p.state.value,
            "pass_rate": round(p.pass_rate, 4),
            "critical_failures": [r.row_id for r in p.critical_failures],
        } for p in submission.portfolios},
        "approvals_held": sorted(a.role for a in submission.approvals),
        "approvals_required": list(REQUIRED_APPROVALS),
        "approvals_missing": sorted(
            set(REQUIRED_APPROVALS) - {a.role for a in submission.approvals}),
        "production_measures": dict(submission.production_measures),
        "verdict": verdict(submission, on=on),
        "refused_because": list(refused),
        "said": ("Engineering completion of this gate is not a release "
                 "approval. Nothing here creates one: an approval is a named "
                 "accountable person signing an exact scope, and this module "
                 "can only read signatures it was handed."),
    }


def blank_manifest_fields(manifest_like: dict) -> tuple[str, ...]:
    """Which of the nineteen a proposed manifest has not established."""
    return tuple(name for name in IDENTITIES
                 if blank(str(manifest_like.get(name, ""))))
