"""Private final checks assembled from the current file and sealed work receipts.

This service performs no model call and publishes nothing. Independent semantic
review is not a receipt for consistency, screening, currency or an atomic write.
Those subjects must come from their actual owners; absence remains visible.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import date

from nm.core.brain_context import assemble_brief
from nm.core.brain_release import (
    IndependentReview,
    ReviewRefused,
    captured_findings,
    prepare_claims,
    review_start_budget,
    saved_verification,
)
from nm.core.matter_support import DocumentCurrent, captured_documents, require_current_documents
from nm.core.output_checks import (
    BoundarySubjects,
    CheckReceipt,
    OutputSubjects,
    run_boundary_checks,
    run_output_checks,
)
from nm.core.tools import Assessment, Availability, Effect, ToolEnvelope, ToolKind, ToolOutcome
from nm.core.verifier import VerifiedRelease, release_verified
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.loop import LoopOutcome, StepKind, digest
from nm.domain.matter import Matter
from nm.domain.text import refuses_blank_text
from nm.ports.evidence import Coverage, EvidenceNeed, EvidenceResult, Finding
from nm.ports.loop_log import LoopLogPort
from nm.ports.model import ToolCall
from nm.ports.store import StorePort


class AssessmentRefused(ReviewRefused):
    """A changed or unattributable receipt cannot produce a final assessment."""


@refuses_blank_text()
@dataclass(frozen=True)
class BrainAssessment:
    matter_version: int
    snapshot_id: str
    proposal_fingerprint: str
    review: IndependentReview
    candidate: Answer | None
    outputs: tuple[CheckReceipt, ...]
    boundaries: tuple[CheckReceipt, ...]
    missing_receipts: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.matter_version) is not int or self.matter_version < 1:
            raise ValueError("An assessment needs the actually loaded positive matter version")
        if (len(self.outputs) != 18 or len(self.boundaries) != 6
                or len({row.gate_id for row in (*self.outputs, *self.boundaries)}) != 24):
            raise ValueError(
                "An assessment needs the complete distinct eighteen/six check population")

    @property
    def withheld(self):
        """Exact independent package failures; no failed paragraph is retained."""
        return self.review.result.withheld

    @property
    def partial(self):
        return bool(self.review.result.released and self.withheld)

    @property
    def unassessed(self):
        return tuple(row for row in (*self.outputs, *self.boundaries) if row.assessed is None)

    @property
    def failed(self):
        return tuple(row for row in (*self.outputs, *self.boundaries) if row.assessed is False)

    @property
    def checks_complete(self):
        # A private candidate is not a client release, even when every captured
        # check passed. Release accountability and quality acceptance are separate.
        return (self.candidate is not None and not self.missing_receipts
                and all(row.assessed is True for row in (*self.outputs, *self.boundaries)))

    @property
    def client_ready(self):
        return False


def _envelope(raw) -> ToolEnvelope:
    if not isinstance(raw, dict) or set(raw) != {field.name for field in fields(ToolEnvelope)}:
        raise AssessmentRefused("The captured tool envelope is incomplete or has unknown fields")
    values = dict(raw)
    for key, kind in (("kind", ToolKind), ("outcome", ToolOutcome),
                      ("availability", Availability), ("assessment", Assessment),
                      ("effect", Effect)):
        values[key] = kind(values[key])
    return ToolEnvelope(**values)


def _primary_read(raw) -> EvidenceResult:
    """Decode the original evidence-port contract without inferring metadata."""
    if not isinstance(raw, dict) or set(raw) != {field.name for field in fields(EvidenceResult)}:
        raise AssessmentRefused("The captured primary read lacks its complete evidence contract")
    if not isinstance(raw["findings"], list) or not isinstance(raw["searched_stores"], list):
        raise AssessmentRefused("The primary read population was not recorded exactly")
    if any(not isinstance(item, str) or not item.strip() for item in raw["searched_stores"]):
        raise AssessmentRefused("A searched store needs its exact identity")
    for key in ("missing", "assumption", "search_note"):
        if raw[key] is not None and not isinstance(raw[key], str):
            raise AssessmentRefused("Primary-read explanations must retain their recorded text")
    result = EvidenceResult(**{**raw, "coverage": Coverage(raw["coverage"]),
                               "findings": tuple(Finding.from_record(row)
                                                 for row in raw["findings"]),
                               "searched_stores": tuple(raw["searched_stores"])})
    if result.coverage is Coverage.NOT_ASSESSED and result.findings:
        raise AssessmentRefused("An unassessed primary read cannot establish a finding")
    return result


def captured_retrievals(outcome: LoopOutcome):
    """Correlate real primary reads with the exact arguments actually dispatched.

    A raw paragraph/document window is not promoted into a primary legal read.
    A missing date is not defaulted to today or copied from another source.
    """
    calls = {}
    results, needs = [], []
    dates_complete = True
    for event in outcome.record.events:
        if event.kind is StepKind.TOOL_STARTED:
            raw = event.payload["call"]
            if not isinstance(raw, dict) or set(raw) != {field.name for field in fields(ToolCall)}:
                raise AssessmentRefused("A captured tool dispatch needs its exact typed call")
            call = ToolCall(**raw)
            if call.call_id in calls:
                raise AssessmentRefused("A captured tool call was dispatched twice")
            calls[call.call_id] = call
        elif event.kind is StepKind.TOOL_RETURNED:
            call = calls.pop(event.payload["call_id"], None)
            envelope = _envelope(event.payload["receipt"])
            if call is None or call.name != envelope.tool:
                raise AssessmentRefused("A returned read does not match its actual dispatch")
            if envelope.kind is not ToolKind.SOURCE:
                continue
            raw_reads = envelope.receipt.get("primary_reads", [])
            if not isinstance(raw_reads, list):
                raise AssessmentRefused("Primary reads must retain their actual population")
            for raw in raw_reads:
                result = _primary_read(raw)
                captured = tuple(Finding.from_record(row)
                                 for row in envelope.data.get("findings", []))
                if any(finding not in captured
                       or finding.locator not in envelope.receipt["locators"]
                       for finding in result.findings):
                    raise AssessmentRefused("A primary finding differs from its source capture")
                results.append(result)
                governing = call.arguments.get("as_of")
                if not isinstance(governing, str):
                    dates_complete = False
                    continue
                try:
                    parsed = date.fromisoformat(governing)
                except ValueError as exc:
                    raise AssessmentRefused(
                        "A dispatched governing date is not a calendar date") from exc
                if parsed.isoformat() != governing:
                    raise AssessmentRefused("A dispatched governing date is not canonical")
                # The args are the captured query, not an invented legal need.
                needs.append(EvidenceNeed(
                    question=json.dumps(call.arguments, ensure_ascii=False, sort_keys=True),
                    governing_date=parsed,
                    jurisdiction=call.arguments.get("jurisdiction", "not_established")))
    if calls:
        raise AssessmentRefused("The terminal work record has unfinished tool dispatches")
    return (tuple(results) or None,
            tuple(needs) if dates_complete and needs else None)


def _saved_review(outcome, review, matter, log):
    try:
        packages = prepare_claims(outcome, matter)
    except ReviewRefused as exc:
        raise AssessmentRefused(str(exc)) from exc
    if packages != review.packages:
        raise AssessmentRefused("The reviewed packages differ from this current captured proposal")
    actual = saved_package_reviews(outcome, packages, matter, log)
    if actual != review:
        raise AssessmentRefused("Caller-authored verdicts or budgets differ from the saved review")
    return actual


def saved_package_reviews(outcome, packages, matter, log):
    """Reconstruct exact sealed independent receipts, for any trusted bound subject."""
    parent = outcome.record.identity
    authors = [event.payload for event in outcome.record.events
               if event.kind is StepKind.MODEL_RETURNED]
    if not authors:
        raise AssessmentRefused("The proposing model identity was not captured")
    author = authors[-1]
    records, budget, model_steps = [], review_start_budget(outcome, packages, matter, log), 0
    for package in packages:
        matching = [row for row in matter.loop_records
                    if row.identity.turn_id == f"{parent.turn_id}:verify:{package.id}"]
        if not matching:
            continue  # Missing review remains withheld by release_verified.
        if len(matching) != 1:
            raise AssessmentRefused("Independent review has duplicate saved claim identities")
        saved = matching[0]
        identity = saved.identity
        if (not saved.terminal or log.read(identity) != saved
                or identity.matter_id != parent.matter_id
                or identity.advocate_id != parent.advocate_id
                or identity.mode != parent.mode
                or identity.principles_version != parent.principles_version
                or identity.tools_version != parent.tools_version):
            raise AssessmentRefused(
                "The independent verdict lacks a matching sealed current receipt")
        stop = saved.events[-1].payload
        # Reuse the review owner's codec, never a second verifier decision.
        record, actual_spend = saved_verification(package, saved, log, author)
        dispatched = [event.payload for event in saved.events
                      if event.kind is StepKind.MODEL_STARTED]
        returned = [event.payload for event in saved.events
                    if event.kind is StepKind.MODEL_RETURNED]
        if len(dispatched) > 1 or len(returned) > 1:
            raise AssessmentRefused("An independent review has ambiguous dispatch receipts")
        model_steps += len(dispatched)
        judge = ({"provider": dispatched[0]["provider"], "model": dispatched[0]["model"]}
                 if dispatched else {"provider": record.provider, "model": record.model})
        if record.releasable:
            if (not dispatched or not returned
                    or judge != {"provider": record.provider, "model": record.model}
                    or judge == {"provider": author["provider"], "model": author["model"]}
                    or dispatched[0]["tier"] != record.tier.value):
                raise AssessmentRefused("A positive independent verdict lacks its actual dispatch")
            received = returned[0]["result"]
            value = received["value"]
            if (received["kind"] != "ModelResult" or value["provider"] != record.provider
                    or value["model"] != record.model or value["tier"] != record.tier.value
                    or value["completion"] != "complete"):
                raise AssessmentRefused("The completed judge identity differs from its verdict")
        expected = digest({"package": package.identity, "author": {
            "provider": author["provider"], "model": author["model"]},
            "judge": judge})
        if (identity.offer_hash != expected or stop.get("released") is not False
                or saved.events[0].payload.get("parent") != parent.fingerprint
                or saved.events[0].payload.get("package") != package.identity):
            raise AssessmentRefused("The saved verdict belongs to a different claim or reviewer")
        records.append(record)
        budget = budget.spend_on(actual_spend)
    actual = tuple(records)
    release = release_verified(packages, actual)
    return IndependentReview(packages, actual, release, budget, model_steps)


def _answer(release: VerifiedRelease) -> Answer | None:
    if not release.released:
        return None
    return Answer(Route.MATTER, Mode.ASSESSMENT, "Privately checked assessment candidate.",
                  tuple(Element(ElementKind.FINDING, package.claim,
                                refs=tuple(dict.fromkeys((
                                    *(span.finding.locator for span in package.spans),
                                    *(span.locator for span in package.documents)))))
                        for package in release.released))


class AssessmentService:
    """Assemble P51 check subjects; missing actual checks never become PASS.

    Supplementary and boundary callbacks are trusted application owners, not
    model payloads. They receive the freshly loaded file and exact saved work.
    They cannot overwrite the source, final-word or independent-review subjects.
    expected_version is the caller's admitted commit version, not the loop's
    initial version (journal appends legitimately advance that transaction).
    """
    def __init__(self, *, store: StorePort, log: LoopLogPort,
                 session_current: Callable[[], bool],
                 supplement: Callable[
                     [Matter, LoopOutcome, IndependentReview], OutputSubjects] | None = None,
                 boundaries: Callable[[Matter, LoopOutcome], BoundarySubjects] | None = None,
                 current_tools_version: Callable[[], str] | None = None,
                 current_principles_version: Callable[[], str] | None = None,
                 document_current: DocumentCurrent | None = None):
        self.store, self.log, self.session_current = store, log, session_current
        self.supplement, self.boundaries = supplement, boundaries
        self.current_tools_version, self.current_principles_version = (
            current_tools_version, current_principles_version)
        self.document_current = document_current

    def assess(self, outcome: LoopOutcome, review: IndependentReview,
               *, expected_version: int | None = None) -> BrainAssessment:
        if not self.session_current():
            raise AssessmentRefused("The session no longer permits final assessment")
        matter = self.store.load(outcome.record.identity.matter_id)
        if matter is None or self.log.read(outcome.record.identity) != outcome.record:
            raise AssessmentRefused("The saved work is unavailable or differs from the proposal")
        if outcome.record.events[-1].payload.get("budget") != outcome.budget.as_dict():
            raise AssessmentRefused("The parent budget differs from its sealed receipt")
        checked = _saved_review(outcome, review, matter, self.log)
        try:
            require_current_documents(matter, checked.packages, self.document_current)
            documents = captured_documents(outcome.record)
        except ValueError as exc:
            raise AssessmentRefused(str(exc)) from exc
        retrieved = captured_findings(outcome)
        results, needs = captured_retrievals(outcome)
        missing = []
        for label, current, expected in (
            ("current tool/source generation", self.current_tools_version,
             outcome.record.identity.tools_version),
            ("current principles generation", self.current_principles_version,
             outcome.record.identity.principles_version),
        ):
            if current is None:
                missing.append(label)
            elif current() != expected:
                raise AssessmentRefused("The " + label + " changed after the proposal")
        subjects = (self.supplement(matter, outcome, checked)
                    if self.supplement else OutputSubjects())
        if not isinstance(subjects, OutputSubjects):
            raise AssessmentRefused("Supplementary checks need actual typed owner subjects")
        owned = {"answer", "relied_on", "retrieved", "evidence_needs", "expected_version",
                 "observed_version", "retrieval_results", "independent_packages",
                 "independent_records", "retrieved_documents"}
        empty = OutputSubjects()
        if any(getattr(subjects, key) != getattr(empty, key) for key in owned):
            raise AssessmentRefused(
                "Supplementary checks cannot replace captured source/review subjects")
        candidate = _answer(checked.result)
        relied = tuple(dict.fromkeys(span.finding for package in checked.result.released
                                    for span in (*package.spans, *package.contrary)))
        subjects = replace(subjects, answer=candidate, relied_on=relied, retrieved=retrieved,
                           evidence_needs=needs, retrieval_results=results,
                           expected_version=expected_version, observed_version=matter.version,
                           independent_packages=checked.result.released,
                           independent_records=checked.records, retrieved_documents=documents)
        boundary = self.boundaries(matter, outcome) if self.boundaries else BoundarySubjects()
        outputs, boundaries = run_output_checks(subjects), run_boundary_checks(boundary)
        if (not self.session_current() or self.store.load(matter.id) != matter
                or self.log.read(outcome.record.identity) != outcome.record):
            raise AssessmentRefused("The file or session changed while final checks ran")
        if (self.current_tools_version is not None
                and self.current_tools_version() != outcome.record.identity.tools_version
                or self.current_principles_version is not None
                and self.current_principles_version()
                != outcome.record.identity.principles_version):
            raise AssessmentRefused("A source or principles generation changed during final checks")
        try:
            require_current_documents(matter, checked.packages, self.document_current)
        except ValueError as exc:
            raise AssessmentRefused(str(exc)) from exc
        saved = outcome.record.events[0].payload["context"]["brief"]
        snapshot = assemble_brief(matter, tuple(saved["selected_issue_ids"]),
                                  advocate_id=outcome.record.identity.advocate_id)
        return BrainAssessment(matter.version, snapshot.snapshot_id,
                               outcome.record.events[-1].fingerprint, checked,
                               candidate, outputs, boundaries, tuple(missing))
