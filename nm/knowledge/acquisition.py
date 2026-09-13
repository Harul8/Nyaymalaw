"""Explainable judgment acquisition and immutable quarantine receipts.

Discovery is not publication.  This module selects candidates inside an exact
authorised scope and records staged bytes; P20 remains the only owner allowed
to publish an approved corpus snapshot.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

from nm.domain.text import refuses_blank_text
from nm.knowledge.source_registry import (
    CanonicalSource,
    PublicationState,
    ReviewState,
    RightsState,
    SourceKind,
)

POLICY_ID = "judgment-acquisition-selection"
POLICY_VERSION = 2
"""RAISED FOR THE COURT AND RIGHTS RULES. A receipt names the policy version
that produced it, so a selection made under version 1 stays explicable after
version 2 exists -- and a report cannot silently claim the newer rules ran."""


class Stage(str, Enum):
    """SIX CLAIMS, AND THEY ARE NOT THE SAME CLAIM.

    Every one of these was, at some point in this build, read as the next one
    along. Naming them is what makes "we have it" and "it applies" different
    sentences:

        DISCOVERED    a candidate exists at a source. Nothing has been fetched.
        ACQUIRED      bytes were obtained. Nobody has looked at them.
        QUARANTINED   the bytes are staged and outside the active corpus.
        VERIFIED      the digest matches and the content was readable.
        PUBLISHED     P20 activated a snapshot containing it. Still nothing
                      about whether it governs anything.
        APPLICABLE    it bears on a matter. ACQUISITION NEVER REACHES HERE and
                      no function in this module returns it.
    """

    DISCOVERED = "discovered"
    ACQUIRED = "acquired"
    QUARANTINED = "quarantined"
    VERIFIED = "verified"
    PUBLISHED = "published"
    APPLICABLE = "applicable"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Stage":
        return cls.NOT_ASSESSED

    @property
    def reached_by_acquisition(self) -> bool:
        """The furthest this module goes is QUARANTINED. Publication is P20's
        and applicability is a legal judgement about a matter."""
        return self in (Stage.DISCOVERED, Stage.ACQUIRED, Stage.QUARANTINED,
                        Stage.VERIFIED)


#: WHAT ACQUISITION ESTABLISHES, AND THE FOUR THINGS IT DOES NOT.
#:
#: Written once and carried into every receipt, because the inference this
#: refuses is the cheapest one available: the bytes are here, therefore the
#: law is current, correct, untreated and complete. Each of those four is a
#: separate piece of work owned somewhere else -- currency by
#: `SourceVersion.amended_by`, treatment by `nm/knowledge/citator.py`,
#: completeness by `docs/BASELINE.md`'s measured coverage, correctness by a
#: person.
ACQUISITION_ESTABLISHES: str = (
    "This records that bytes were obtained from a named source at a named "
    "time, and nothing else. It does not establish that the decision is "
    "current, that the text is correct, how it has been treated since, or "
    "that the population is complete."
)


def quarantine_source_state() -> dict[str, str]:
    """The only honest publication state for bytes still in acquisition."""
    return {
        "rights_state": RightsState.UNKNOWN.value,
        "review_state": ReviewState.UNREVIEWED.value,
        "publication_state": PublicationState.CANDIDATE.value,
    }


def selection_policy_identity() -> dict[str, int | str]:
    """The versioned rule set a quarantine receipt is allowed to name."""
    return {"id": POLICY_ID, "version": POLICY_VERSION}


class AcquisitionRoute(str, Enum):
    API = "api"
    WEB = "web"


class SelectionState(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"

    @classmethod
    def not_established(cls) -> "SelectionState":
        return cls.UNRESOLVED


class ReconciliationState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"
    REFUSED = "refused"


def _normal(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def acquisition_dates(
    year: int, *, from_date: date | None = None, to_date: date | None = None,
) -> tuple[date, date]:
    """One explicit interval shared by planning, requests and selection.

    An explicit year is a bounded full-year scope for compatibility. Both
    optional dates narrow it. No wall clock or remembered release cutoff
    silently changes the approved population.
    """
    if (from_date is None) != (to_date is None):
        raise ValueError("acquisition requires both from_date and to_date")
    start, end = date(year, 1, 1), date(year, 12, 31)
    if from_date is not None and to_date is not None:
        if from_date > to_date:
            raise ValueError("acquisition date interval starts after it ends")
        start, end = max(start, from_date), min(end, to_date)
        if start > end:
            raise ValueError("selected year is outside the acquisition date interval")
    return start, end


def _stable_id(prefix: str, value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


@refuses_blank_text()
@dataclass(frozen=True)
class AcquisitionScope:
    route: AcquisitionRoute
    source: str
    jurisdiction: str
    document_types: tuple[str, ...]
    from_date: date
    to_date: date
    discovery_budget: int
    selection_budget: int
    authorization_id: str
    source_rights: RightsState = RightsState.UNKNOWN
    """THE REVIEWED RIGHT TO TAKE FROM THIS SOURCE, recorded once where the
    authorisation is rather than on every candidate.

    A candidate inherits it and may only narrow it: a sealed or in-camera
    judgment is RESTRICTED whatever the source-level review said, and no
    document-level statement can widen a source nobody was permitted to take
    from. UNKNOWN here is refused at construction -- an authorisation that did
    not review the right is not an authorisation."""

    issuing_bodies: tuple[str, ...] = ()
    """WHICH COURTS THIS AUTHORISATION COVERS. Empty is refused rather than
    defaulted to "any", because a jurisdiction is not a court: an approval to
    take High Court judgments is not an approval to take everything filed
    anywhere in Telangana, and a blank field reading as "all of them" is the
    absent-input-as-success shape at the widest possible scope."""

    def __post_init__(self) -> None:
        if self.from_date > self.to_date:
            raise ValueError("acquisition scope starts after it ends")
        if not self.issuing_bodies or not all(
                str(body).strip() for body in self.issuing_bodies):
            raise ValueError(
                "an acquisition scope names the courts it covers; a "
                "jurisdiction is not a court and an empty list is not "
                "'every court'")
        if self.source_rights is RightsState.UNKNOWN:
            raise ValueError(
                "an acquisition scope records the reviewed right to take from "
                "this source. UNKNOWN is not permission, and an authorisation "
                "id is a reference to a decision rather than the decision")
        if self.discovery_budget < 1 or self.selection_budget < 1:
            raise ValueError("acquisition budgets must be positive")
        if self.selection_budget > self.discovery_budget:
            raise ValueError("selection budget cannot exceed discovery budget")
        if not self.document_types or any(not value.strip()
                                          for value in self.document_types):
            raise ValueError("acquisition scope requires document types")

    @property
    def scope_id(self) -> str:
        return _stable_id("scope", {
            "route": self.route.value,
            "source": _normal(self.source),
            "jurisdiction": _normal(self.jurisdiction),
            "document_types": sorted(_normal(x) for x in self.document_types),
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "discovery_budget": self.discovery_budget,
            "selection_budget": self.selection_budget,
            "authorization_id": self.authorization_id,
        })


@refuses_blank_text()
@dataclass(frozen=True)
class JudgmentCandidate:
    candidate_id: str
    source: str
    jurisdiction: str
    issuing_body: str
    document_type: str
    source_url: str
    source_date: date | None
    citation_count: int | None
    readable: bool = True
    rights: RightsState = RightsState.UNKNOWN
    """A RESTRICTION ON THIS DOCUMENT IN PARTICULAR, narrowing the scope's
    reviewed source right.

    UNKNOWN means "nothing is recorded about this document specifically", so
    the scope's source-level review governs. It can only NARROW: a sealed or
    in-camera judgment is RESTRICTED whatever the source review said, and a
    document cannot declare itself permitted out of a source nobody was
    allowed to take from."""

    def __post_init__(self) -> None:
        if self.citation_count is not None and self.citation_count < 0:
            raise ValueError("citation_count cannot be negative")

    @property
    def canonical_source_id(self) -> str:
        return CanonicalSource(
            kind=SourceKind.JUDGMENT,
            jurisdiction=self.jurisdiction,
            issuing_body=self.issuing_body,
            official_identifier=self.candidate_id,
            display_name=self.candidate_id,
        ).source_id


@refuses_blank_text()
@dataclass(frozen=True)
class SelectionDecision:
    candidate_id: str
    state: SelectionState
    reasons: tuple[str, ...]
    priority: int | None = None


@refuses_blank_text()
@dataclass(frozen=True)
class SelectionReport:
    policy_id: str
    policy_version: int
    scope_id: str
    observed: int
    decisions: tuple[SelectionDecision, ...]

    @property
    def selected_ids(self) -> tuple[str, ...]:
        ordered = sorted(
            (row for row in self.decisions
             if row.state is SelectionState.SELECTED),
            key=lambda row: row.priority or 0,
        )
        return tuple(row.candidate_id for row in ordered)

    def count(self, state: SelectionState) -> int:
        return sum(row.state is state for row in self.decisions)

    def as_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "scope_id": self.scope_id,
            "observed": self.observed,
            "decisions": [
                {
                    "candidate_id": row.candidate_id,
                    "state": row.state.value,
                    "reasons": list(row.reasons),
                    "priority": row.priority,
                }
                for row in self.decisions
            ],
        }


def effective_right(scope: AcquisitionScope,
                    candidate: JudgmentCandidate) -> RightsState:
    """The right that governs THIS document. ONE OWNER, and it only narrows.

    The scope carries the reviewed source-level right, recorded once where the
    authorisation is. A candidate may say RESTRICTED -- a sealed judgment, an
    in-camera proceeding -- and that wins. It may not say PERMITTED out of a
    source nobody was allowed to take from, which is why this is a function
    rather than a `candidate.rights or scope.source_rights`.
    """
    if candidate.rights is RightsState.RESTRICTED:
        return RightsState.RESTRICTED
    return scope.source_rights


def select_candidates(
    scope: AcquisitionScope,
    candidates: Iterable[JudgmentCandidate],
) -> SelectionReport:
    """Apply eligibility first, then citation priority only within one year."""
    population = tuple(candidates)
    decisions: dict[int, SelectionDecision] = {}
    eligible: list[tuple[int, JudgmentCandidate, tuple[str, ...]]] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    allowed_types = {_normal(value) for value in scope.document_types}
    allowed_bodies = {_normal(value) for value in scope.issuing_bodies}

    for position, candidate in enumerate(population):
        reasons: list[str] = []
        if position >= scope.discovery_budget:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.REJECTED,
                ("outside the authorised discovery budget",),
            )
            continue
        if candidate.candidate_id in seen_ids or candidate.source_url in seen_urls:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.REJECTED,
                ("duplicate candidate identity or source URL",),
            )
            continue
        seen_ids.add(candidate.candidate_id)
        seen_urls.add(candidate.source_url)

        if _normal(candidate.source) != _normal(scope.source):
            reasons.append("source is outside the authorised scope")
        if _normal(candidate.jurisdiction) != _normal(scope.jurisdiction):
            reasons.append("jurisdiction is outside the authorised scope")
        if _normal(candidate.document_type) not in allowed_types:
            reasons.append("document type is outside the authorised scope")
        if (candidate.issuing_body.strip()
                and _normal(candidate.issuing_body) not in allowed_bodies):
            reasons.append("issuing court is outside the authorised scope")
        if effective_right(scope, candidate) is RightsState.RESTRICTED:
            reasons.append(
                "the right to acquire this document is recorded as restricted")
        if candidate.source_date is not None and not (
                scope.from_date <= candidate.source_date <= scope.to_date):
            reasons.append("source date is outside the authorised scope")
        if reasons:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.REJECTED, tuple(reasons),
            )
            continue
        unresolved: list[str] = []
        if candidate.source_date is None:
            unresolved.append("source date is not recorded")
        if not candidate.readable:
            unresolved.append("source content was not readable")
        if not candidate.issuing_body.strip():
            # NOT THE WRONG COURT -- NO COURT. A candidate whose source did not
            # record a bench cannot be checked against the authorised ones, and
            # rejecting it would say something about it that nobody knows.
            unresolved.append("no issuing court is recorded")
        if effective_right(scope, candidate) is RightsState.UNKNOWN:
            # UNKNOWN IS NOT PERMISSION, and it is not a refusal either. It is
            # work: somebody has to review the right before a request is made,
            # and an unresolved candidate is what puts that on a list rather
            # than resolving it in whichever direction is convenient.
            #
            # It is unreachable through `AcquisitionScope`, whose constructor
            # refuses an unreviewed source -- and it stays here because the
            # constructor is one door and this is the rule.
            unresolved.append(
                "nobody has reviewed the right to acquire this document")
        if unresolved:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.UNRESOLVED,
                tuple(unresolved),
            )
            continue
        citation_note = (
            "citation metadata is unavailable and was not treated as zero"
            if candidate.citation_count is None
            else f"citation count {candidate.citation_count} affects priority "
                 "only within the same source year"
        )
        eligible.append((position, candidate, (citation_note,)))

    # Recency is the outer cohort. Citation popularity never makes a document
    # eligible and cannot lift an older case above a newer eligible cohort.
    eligible.sort(key=lambda row: (
        -row[1].source_date.year,  # type: ignore[union-attr]
        row[1].citation_count is None,
        -(row[1].citation_count or 0),
        -row[1].source_date.toordinal(),  # type: ignore[union-attr]
        row[1].candidate_id,
    ))
    for priority, (position, candidate, notes) in enumerate(eligible, 1):
        if priority <= scope.selection_budget:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.SELECTED,
                ("eligible under exact source, jurisdiction, type and date scope",
                 *notes),
                priority,
            )
        else:
            decisions[position] = SelectionDecision(
                candidate.candidate_id, SelectionState.REJECTED,
                ("eligible but outside the authorised selection budget", *notes),
            )

    ordered = tuple(decisions[index] for index in range(len(population)))
    return SelectionReport(
        POLICY_ID, POLICY_VERSION, scope.scope_id, len(population), ordered,
    )


@refuses_blank_text("error")
@dataclass(frozen=True)
class AcquiredArtifact:
    candidate_id: str
    source_id: str
    source_url: str
    payload: bytes | None
    error: str = ""


@refuses_blank_text()
@dataclass(frozen=True)
class ReconciliationReport:
    run_path: str
    state: ReconciliationState
    reasons: tuple[str, ...]
    planned: int
    observed: int
    accepted: int
    rejected: int
    unresolved: int
    staged: int
    failed: int

    def as_dict(self) -> dict:
        value = asdict(self)
        value["state"] = self.state.value
        value["reasons"] = list(self.reasons)
        return value


class AcquisitionRefused(RuntimeError):
    pass


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, path)


def stage_acquisition(
    root: str | Path,
    *,
    run_id: str,
    scope: AcquisitionScope,
    selection: SelectionReport,
    artifacts: Iterable[AcquiredArtifact],
    observed_at: datetime,
    stop_after_writes: int | None = None,
) -> Path:
    """Write a unique quarantine run; the receipt is committed last."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a short filesystem-safe identifier")
    if selection.scope_id != scope.scope_id:
        raise AcquisitionRefused("selection report does not belong to this scope")
    if selection.policy_id != POLICY_ID or selection.policy_version != POLICY_VERSION:
        raise AcquisitionRefused("selection report uses unsupported acquisition policy")
    if stop_after_writes is not None and stop_after_writes < 0:
        raise ValueError("stop_after_writes cannot be negative")

    base = Path(root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    partial = base / f"{run_id}.partial"
    final = base / run_id
    if partial.exists() or final.exists():
        raise AcquisitionRefused("run id already exists; quarantine is immutable")
    partial.mkdir()

    supplied: dict[str, list[AcquiredArtifact]] = {}
    for artifact in artifacts:
        supplied.setdefault(artifact.candidate_id, []).append(artifact)
    selected = selection.selected_ids
    selected_set = set(selected)
    source_state = quarantine_source_state()
    rows: list[dict] = []
    writes = 0
    for candidate_id in selected:
        received = supplied.get(candidate_id, [])
        if len(received) != 1:
            reason = "artifact response missing" if not received else \
                "duplicate artifact responses"
            rows.append({
                "candidate_id": candidate_id,
                "state": "failed",
                "reason": reason,
                **source_state,
            })
            continue
        artifact = received[0]
        if artifact.payload is None:
            rows.append({
                "candidate_id": candidate_id,
                "source_id": artifact.source_id,
                "source_url": artifact.source_url,
                "state": "failed",
                "reason": artifact.error or "source response carried no bytes",
                **source_state,
            })
            continue
        digest = hashlib.sha256(artifact.payload).hexdigest()
        filename = f"{hashlib.sha256(candidate_id.encode('utf8')).hexdigest()[:16]}.source"
        (partial / filename).write_bytes(artifact.payload)
        writes += 1
        rows.append({
            "candidate_id": candidate_id,
            "source_id": artifact.source_id,
            "source_url": artifact.source_url,
            "state": "staged",
            "file": filename,
            "bytes": len(artifact.payload),
            "sha256": digest,
            **source_state,
        })
        if stop_after_writes is not None and writes >= stop_after_writes:
            raise InterruptedError("fault injected after staged write")

    unexpected = sorted(set(supplied) - selected_set)
    staged = sum(row["state"] == "staged" for row in rows)
    failed = sum(row["state"] == "failed" for row in rows)
    receipt = {
        "schema": 1,
        "run_id": run_id,
        "observed_at": observed_at.isoformat(),
        "route": scope.route.value,
        "source": scope.source,
        "authorization_id": scope.authorization_id,
        "scope_id": scope.scope_id,
        "selection_policy": selection_policy_identity(),
        "counts": {
            "planned": scope.discovery_budget,
            "observed": selection.observed,
            "accepted": selection.count(SelectionState.SELECTED),
            "rejected": selection.count(SelectionState.REJECTED),
            "unresolved": selection.count(SelectionState.UNRESOLVED),
            "staged": staged,
            "failed": failed,
        },
        "selection": selection.as_dict(),
        "artifacts": rows,
        "unexpected_responses": unexpected,
        "source_state": source_state,
        "published": False,
        "stage": Stage.QUARANTINED.value,
        "establishes": ACQUISITION_ESTABLISHES,
    }
    _atomic_json(partial / "receipt.json", receipt)
    os.replace(partial, final)
    return final


def _empty_report(path: Path, state: ReconciliationState, reason: str) \
        -> ReconciliationReport:
    return ReconciliationReport(
        str(path), state, (reason,), 0, 0, 0, 0, 0, 0, 0,
    )


def reconcile_acquisition(run_path: str | Path) -> ReconciliationReport:
    """Verify every receipt count, path and byte; silence never means complete."""
    run = Path(run_path)
    try:
        resolved = run.resolve(strict=True)
    except OSError:
        return _empty_report(
            run, ReconciliationState.NOT_ASSESSED,
            "acquisition run path is unavailable",
        )
    if not resolved.is_dir():
        return _empty_report(
            resolved, ReconciliationState.NOT_ASSESSED,
            "acquisition run path is not a directory",
        )
    if resolved.name.endswith(".partial"):
        return _empty_report(
            resolved, ReconciliationState.PARTIAL,
            "acquisition run is partial and has no committed receipt",
        )
    receipt_path = resolved / "receipt.json"
    if not receipt_path.is_file():
        return _empty_report(
            resolved, ReconciliationState.NOT_ASSESSED,
            "committed acquisition receipt is missing",
        )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf8"))
        counts = receipt["counts"]
        rows = receipt["artifacts"]
        selection = receipt["selection"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return _empty_report(
            resolved, ReconciliationState.REFUSED,
            "acquisition receipt is malformed or unreadable",
        )
    if not isinstance(counts, dict) or not isinstance(rows, list) \
            or not isinstance(selection, dict):
        return _empty_report(
            resolved, ReconciliationState.REFUSED,
            "acquisition receipt population types are malformed",
        )

    reasons: list[str] = []
    refused = False
    required_counts = (
        "planned", "observed", "accepted", "rejected", "unresolved",
        "staged", "failed",
    )
    if any(type(counts.get(name)) is not int or counts[name] < 0
           for name in required_counts):
        return _empty_report(
            resolved, ReconciliationState.REFUSED,
            "receipt counts are missing, negative or not integers",
        )
    expected_source_state = quarantine_source_state()
    expected_policy = selection_policy_identity()
    if receipt.get("selection_policy") != expected_policy:
        reasons.append("acquisition receipt names an unsupported selection policy")
        refused = True
    if selection.get("policy_id") != expected_policy["id"] or (
            selection.get("policy_version") != expected_policy["version"]):
        reasons.append("selection report names an unsupported selection policy")
        refused = True
    if selection.get("scope_id") != receipt.get("scope_id"):
        reasons.append("selection report scope does not match the receipt scope")
        refused = True
    if receipt.get("published") is not False:
        reasons.append("acquisition receipt does not declare an unpublished quarantine")
        refused = True
    if receipt.get("source_state") != expected_source_state:
        reasons.append(
            "quarantine source state does not declare unknown rights, "
            "unreviewed law and candidate publication status"
        )
        refused = True
    decisions = selection.get("decisions") if isinstance(selection, dict) else None
    if not isinstance(decisions, list):
        reasons.append("selection decision population is missing")
        refused = True
        decisions = []
    states = [row.get("state") for row in decisions if isinstance(row, dict)]
    expected = {
        "observed": len(decisions),
        "accepted": states.count(SelectionState.SELECTED.value),
        "rejected": states.count(SelectionState.REJECTED.value),
        "unresolved": states.count(SelectionState.UNRESOLVED.value),
        "staged": sum(row.get("state") == "staged" for row in rows
                      if isinstance(row, dict)),
        "failed": sum(row.get("state") == "failed" for row in rows
                      if isinstance(row, dict)),
    }
    for name, value in expected.items():
        if counts[name] != value:
            reasons.append(
                f"{name} count says {counts[name]} but population contains {value}"
            )
    if counts["observed"] != (
            counts["accepted"] + counts["rejected"] + counts["unresolved"]):
        reasons.append("observed population does not reconcile to decisions")
    if selection.get("observed") != counts["observed"]:
        reasons.append("selection observed population does not match receipt counts")
        refused = True
    if counts["accepted"] != counts["staged"] + counts["failed"]:
        reasons.append("accepted population does not reconcile to artifacts")

    candidate_ids: list[str] = []
    declared_files: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            reasons.append("artifact row is not an object")
            refused = True
            continue
        for key, expected_value in expected_source_state.items():
            if row.get(key) != expected_value:
                reasons.append(f"artifact row has invalid {key}")
                refused = True
        candidate_ids.append(str(row.get("candidate_id", "")))
        if row.get("state") != "staged":
            continue
        relative = row.get("file")
        if not isinstance(relative, str) or not relative:
            reasons.append("staged artifact has no file")
            refused = True
            continue
        declared_files.append(relative)
        path = resolved / relative
        try:
            target = path.resolve(strict=True)
            target.relative_to(resolved)
        except (OSError, ValueError):
            reasons.append(f"artifact path escapes or is missing: {relative}")
            refused = True
            continue
        payload = target.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row.get("sha256") or len(payload) != row.get("bytes"):
            reasons.append(f"artifact bytes changed: {relative}")
            refused = True
    if len(candidate_ids) != len(set(candidate_ids)):
        reasons.append("artifact candidate ids are duplicated")
        refused = True
    selected_ids = [row.get("candidate_id") for row in decisions
                    if isinstance(row, dict)
                    and row.get("state") == SelectionState.SELECTED.value]
    if any(not isinstance(value, str) or not value.strip() for value in selected_ids) \
            or len(selected_ids) != len(set(selected_ids)) \
            or set(candidate_ids) != set(selected_ids):
        reasons.append("artifact identities do not exactly match selected candidate identities")
        refused = True
    if len(declared_files) != len(set(declared_files)):
        reasons.append("artifact files are duplicated")
        refused = True
    actual_files = sorted(
        path.name for path in resolved.iterdir()
        if path.is_file() and path.name != "receipt.json"
    )
    if actual_files != sorted(declared_files):
        reasons.append("quarantine contains missing or unaccounted files")
        refused = True
    if receipt.get("unexpected_responses"):
        reasons.append("receipt records responses for unselected candidates")

    state = ReconciliationState.COMPLETE
    if refused:
        state = ReconciliationState.REFUSED
    elif reasons:
        state = ReconciliationState.PARTIAL
    return ReconciliationReport(
        str(resolved), state, tuple(reasons),
        *(counts[name] for name in required_counts),
    )


# ------------------------------------------------------ submission to P20 ---

@refuses_blank_text()
@dataclass(frozen=True)
class PublicationSubmission:
    """One staged candidate, ready to be OFFERED to P20's publication.

    IT IS NOT A PUBLICATION AND CANNOT BECOME ONE HERE. Nothing in this module
    calls `publish_corpus`: acquisition that could publish is acquisition that
    will, and P20 exists because activating a corpus snapshot is a decision
    with an approval behind it. This produces the inputs and refuses to
    produce them where the preconditions are not met.
    """

    candidate_id: str
    source_id: str
    relative_path: str
    sha256: str
    acquisition_run: str
    stage: Stage = Stage.QUARANTINED
    establishes: str = ACQUISITION_ESTABLISHES


def submit_for_publication(
    run_path: str | Path, *, expected_run_id: str = "",
) -> tuple[PublicationSubmission, ...]:
    """Everything in this run that P20 may be offered. BK-24-AC1.

    THE ONLY CODE THAT BUILT THIS LIVED IN A TEST. `CorpusSourceInput` already
    carries `acquisition_run` and `candidate_id`, and the helper that filled
    them was inside `tests/test_immutable_corpus_publication.py` -- a correct
    module with no path from the product to it, which is the gap CLAUDE.md
    section 8 says every externally-found defect has lived in.

    A run that did not reconcile produces NOTHING, and that is not a partial
    answer: a receipt whose staged bytes and recorded digests disagree is a
    run nobody can say what is in, and offering its readable half to a
    publication boundary would publish exactly the members whose absence was
    the problem.
    """
    report = reconcile_acquisition(run_path)
    if report.state is not ReconciliationState.COMPLETE:
        raise AcquisitionRefused(
            f"this run reconciled as {report.state.value} and cannot be "
            f"offered for publication: " + "; ".join(report.reasons))

    run = Path(run_path).resolve()
    if expected_run_id and run.name != expected_run_id:
        raise AcquisitionRefused(
            f"this is run {run.name!r} and {expected_run_id!r} was expected")
    # A RUN ALREADY PUBLISHED IS NOT RE-OFFERED, and this function does not
    # check that: `reconcile_acquisition` above already refuses a receipt that
    # does not declare an unpublished quarantine, so a second check here would
    # be a second owner of one rule -- and the day the two disagreed, one of
    # them would be the permissive one.
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf8"))

    out: list[PublicationSubmission] = []
    for row in receipt.get("artifacts", ()):
        if row.get("state") != "staged":
            continue
        out.append(PublicationSubmission(
            candidate_id=str(row["candidate_id"]),
            source_id=str(row.get("source_id") or ""),
            relative_path=str(row["file"]),
            sha256=str(row["sha256"]),
            acquisition_run=str(run),
        ))
    if not out:
        raise AcquisitionRefused(
            "this run staged nothing, so there is nothing to offer. An empty "
            "submission is not a successful one")
    return tuple(out)
