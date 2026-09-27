"""Exact captured packages reviewed privately before any client-path cutover.

This is not the eighteen-check publication service. Independently reviewed
paragraphs remain evaluation candidates until that separate contract passes.
No unconstrained answer string accompanies the checked package population.
"""
from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timezone

from nm.core.brain_context import ContextRefused, require_recorded_source
from nm.core.matter_support import (
    DocumentCurrent,
    MatterDocumentSpan,
    captured_documents,
    require_current_documents,
)
from nm.core.tool_sources import findings_from_record
from nm.core.tools import ANSWER_PROPOSAL_SHAPE
from nm.core.verifier import (
    EvidencePackage,
    EvidenceSpan,
    IndependentVerifier,
    Judgment,
    VerificationRecord,
    VerifiedRelease,
    interpret_completed_verification,
    release_verified,
    verification_prompt,
)
from nm.domain.budget import Budget, Completion, Exhausted, Spend
from nm.domain.loop import LoopEvent, LoopIdentity, LoopOutcome, StepKind, StopReason, digest
from nm.domain.matter import Matter
from nm.ports.evidence import Finding
from nm.ports.loop_log import LoopLogPort
from nm.ports.model import ModelError, ModelResult, Tier, Usage, estimate_tokens, require_schema
from nm.ports.store import StorePort


class ReviewRefused(ValueError):
    """No paid review or published claim can follow a broken captured contract."""


def review_start_budget(outcome, packages, matter, log):
    """Exact-parent supplemental verification spends, excluding these replayed subjects."""
    parent = outcome.record.identity
    selected = {f"{parent.turn_id}:verify:{package.id}" for package in packages}
    budget = outcome.budget
    for saved in matter.loop_records:
        if (not saved.identity.turn_id.startswith(f"{parent.turn_id}:verify:")
                or saved.identity.turn_id in selected):
            continue
        if (saved.identity.matter_id != parent.matter_id
                or saved.identity.advocate_id != parent.advocate_id
                or saved.identity.principles_version != parent.principles_version
                or saved.identity.tools_version != parent.tools_version
                or saved.identity.mode != parent.mode
                or saved.events[0].payload.get("parent") != parent.fingerprint
                or not saved.terminal or log.read(saved.identity) != saved):
            raise ReviewRefused("Supplemental review spend lacks its exact sealed parent")
        stop = saved.events[-1].payload
        if (stop.get("released") is not False or "verification" not in stop
                or "spend" not in stop):
            raise ReviewRefused("Supplemental verification has an unknown external outcome")
        _decode_verdict(stop["verification"])
        budget = budget.spend_on(Spend(**stop["spend"]))
    return budget


def captured_findings(outcome: LoopOutcome) -> tuple[Finding, ...]:
    try:
        return findings_from_record(outcome.record)
    except ValueError as exc:
        raise ReviewRefused(str(exc)) from exc


def _require_current_source(outcome: LoopOutcome, matter: Matter):
    try:
        return require_recorded_source(outcome.record, matter)
    except ContextRefused as exc:
        raise ReviewRefused(str(exc)) from exc


def prepare_claims(outcome: LoopOutcome, matter: Matter) -> tuple[EvidencePackage, ...]:
    """Bind each final paragraph to exact journal sources and current file premises."""
    if (outcome.reason is not StopReason.PROPOSAL or not outcome.record.terminal
            or outcome.record.events[-1].payload.get("proposal") != outcome.proposal):
        raise ReviewRefused("The saved work did not end in this exact answer proposal")
    _require_current_source(outcome, matter)
    require_schema(outcome.proposal, ANSWER_PROPOSAL_SHAPE)
    rows = outcome.proposal["claims"]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ReviewRefused("A proposal needs nonempty, uniquely identified claims")
    findings = captured_findings(outcome)
    try:
        documents = captured_documents(outcome.record)
    except ValueError as exc:
        raise ReviewRefused(str(exc)) from exc
    facts = {fact.id: fact for fact in matter.facts}
    packages = []
    for row in rows:
        def spans(windows, prefix):
            result, document_result = [], []
            for index, window in enumerate(windows):
                quote = window["quote"]
                if not quote.strip():
                    raise ReviewRefused("A source window cannot be empty")
                candidates = [finding for finding in findings
                              if finding.locator == window["locator"] and quote in finding.span]
                document_candidates = [document for document in documents
                                       if document.locator == window["locator"]
                                       and quote in document.text]
                if len(candidates) + len(document_candidates) != 1:
                    raise ReviewRefused("A window must identify one exact captured source")
                if document_candidates:
                    document = document_candidates[0]
                    start = document.text.find(quote)
                    document_result.append(MatterDocumentSpan(
                        f"{prefix}_document_{index}", document, start, start + len(quote)))
                    continue
                finding = candidates[0]
                start = finding.span.find(quote)
                result.append(EvidenceSpan(f"{prefix}_{index}", finding, start, start + len(quote)))
            return tuple(result), tuple(document_result)

        if (len(set(row["premise_ids"])) != len(row["premise_ids"])
                or any(ident not in facts for ident in row["premise_ids"])):
            raise ReviewRefused("A premise must identify one recorded fact in this file")
        support, support_documents = spans(row["sources"], "support")
        contrary, contrary_documents = spans(row["contrary"], "contrary")
        packages.append(EvidencePackage(
            row["id"], row["text"], support,
            tuple(facts[ident] for ident in row["premise_ids"]),
            contrary, tuple(row["depends_on"]), documents=support_documents,
            document_contrary=contrary_documents))
    return tuple(packages)


@dataclass(frozen=True)
class IndependentReview:
    packages: tuple[EvidencePackage, ...]
    records: tuple[VerificationRecord, ...]
    result: VerifiedRelease
    budget: Budget
    model_steps: int = 0

    def __post_init__(self):
        if type(self.model_steps) is not int or self.model_steps < 0:
            raise ValueError("Review steps count actual captured model dispatches")

    @property
    def candidate_text(self):
        return "\n\n".join(package.claim for package in self.result.released)

    @property
    def client_ready(self):
        # Independent semantic review alone cannot waive the other output checks.
        return False


def _json(value):
    def encode(item):
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError(f"Unsupported review value {type(item).__name__}")
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      default=encode)


def _decode_verdict(raw):
    if set(raw) != {field.name for field in fields(VerificationRecord)}:
        raise ReviewRefused("The saved independent review has an unknown contract")
    values = dict(raw)
    values["tier"] = Tier(values["tier"])
    if values["usage"] is not None:
        values["usage"] = Usage(**values["usage"])
    for key in ("textual_support", "applicability", "inference", "opposition_resolved"):
        values[key] = Judgment(**{**values[key],
                                 "supporting_words": tuple(values[key]["supporting_words"])})
    return VerificationRecord(**values)


def saved_verification(package, saved, log, author):
    """A positive saved verdict must be derived from its actual model receipt.

    Unknown/refused results may be stricter than a completed response after a
    budget or cancellation boundary. They stay refused; no replay upgrades
    them. The one pure live interpreter also owns every positive replay.
    """
    if not saved.terminal or log.read(saved.identity) != saved:
        raise ReviewRefused("The verification lacks its exact sealed completed journal")
    stop = saved.events[-1].payload
    record, spend = _decode_verdict(stop["verification"]), Spend(**stop["spend"])
    if record.package_id != package.id or record.package_identity != package.identity:
        raise ReviewRefused("The saved verification belongs to a different package")
    if not record.releasable:
        return record, spend
    started = [event.payload for event in saved.events if event.kind is StepKind.MODEL_STARTED]
    returned = [event.payload for event in saved.events if event.kind is StepKind.MODEL_RETURNED]
    if len(started) != 1 or len(returned) != 1:
        raise ReviewRefused("A positive verdict needs one actual dispatch and response")
    dispatched, received = started[0], returned[0]["result"]
    if (dispatched.get("prompt") != asdict(verification_prompt(package))
            or saved.events[0].payload.get("package") != package.identity):
        raise ReviewRefused("The independent model did not examine this exact captured package")
    if (set(received) != {"kind", "value"} or received["kind"] != "ModelResult"
            or set(received["value"]) != {field.name for field in fields(ModelResult)}):
        raise ReviewRefused("The saved verification response has an incomplete or unknown contract")
    values = dict(received["value"])
    try:
        values["usage"] = Usage(**values["usage"])
        values["tier"] = Tier(values["tier"])
        values["completion"] = Completion(values["completion"])
        values["downgraded_from"] = (Tier(values["downgraded_from"])
                                     if values["downgraded_from"] is not None else None)
        result = ModelResult(**values)
        if (not result.usable or result.was_downgraded
                or (result.provider, result.model) == (author["provider"], author["model"])
                or result.provider != dispatched["provider"]
                or result.model != dispatched["model"]
                or result.tier.value != dispatched["tier"]):
            raise ReviewRefused(
                "The saved independent result changed or lost its admitted identity")
        actual = interpret_completed_verification(package, result)
    except (ModelError, ValueError, TypeError, KeyError) as exc:
        raise ReviewRefused("The saved verification has no valid completed interpretation") from exc
    if (record != actual or spend.tokens != result.usage.tokens_in + result.usage.tokens_out
            or spend.cost_usd != result.usage.cost_usd or spend.retries != result.retries
            or spend.children != 1):
        raise ReviewRefused("The saved verdict or spending differs from the actual model response")
    from nm.core.loop import _budget_from

    budget = _budget_from(saved.events[0].payload["budget"])
    charged = budget.spend_on(spend)
    if (charged.exhausted() not in (Exhausted.NONE, Exhausted.CHILDREN)
            or charged.max_children and charged.spend.children > charged.max_children
            or spend.tokens > dispatched["reserved_tokens"]
            or spend.cost_usd > dispatched["reserved_cost_usd"]):
        raise ReviewRefused("The saved positive review exceeded its admitted resource boundary")
    return record, spend


class ReviewService:
    """Scoped private reviews, durably started, with no new money on exact retries."""
    def __init__(self, *, store: StorePort, log: LoopLogPort,
                 verifier: IndependentVerifier, session_current: Callable[[], bool],
                 cost_ceiling: Callable[[int, int, Tier], float],
                 document_current: DocumentCurrent | None = None):
        self.store, self.log, self.verifier = store, log, verifier
        self.session_current, self.cost_ceiling = session_current, cost_ceiling
        self.document_current = document_current

    def review(self, outcome: LoopOutcome, *, cancelled=lambda: False,
               max_model_calls: int | None = None) -> IndependentReview:
        matter = self._current(outcome)
        packages = prepare_claims(outcome, matter)
        return self.review_packages(outcome, packages, cancelled=cancelled,
                                   max_model_calls=max_model_calls)

    def review_packages(self, outcome: LoopOutcome, packages: tuple[EvidencePackage, ...], *,
                        current_owner=None, current_sources=None, cancelled=lambda: False,
                        max_model_calls: int | None = None) -> IndependentReview:
        """One durable independent transport for explicitly bound supplemental subjects.

        The trusted current owner reconstructs each supplemental package at every
        boundary. It cannot replace session, sealed parent, generation or budget
        checks. Ordinary final answers still use prepare_claims without a bypass.
        """
        if (not isinstance(packages, tuple) or not packages
                or any(not isinstance(package, EvidencePackage) for package in packages)
                or len({package.id for package in packages}) != len(packages)):
            raise ReviewRefused("Independent review needs exact uniquely identified packages")
        if current_owner is not None and not callable(current_owner):
            raise ReviewRefused("Supplemental packages require their actual trusted current owner")
        if current_sources is not None and (current_owner is None or not callable(current_sources)):
            raise ReviewRefused(
                "Supplemental captured sources need their same trusted subject owner")
        if max_model_calls is not None and (
                type(max_model_calls) is not int or max_model_calls < 0):
            raise ValueError("The remaining review dispatch allowance is a nonnegative integer")
        matter = self._current(outcome, packages=packages, current_owner=current_owner)
        captured = (current_sources(outcome, matter, packages)
                    if current_sources is not None else captured_findings(outcome))
        if (not isinstance(captured, tuple)
                or any(not isinstance(source, Finding) for source in captured)):
            raise ReviewRefused("An independent subject's captured law needs actual typed findings")
        authors = [event.payload for event in outcome.record.events
                   if event.kind is StepKind.MODEL_RETURNED]
        if not authors:
            raise ReviewRefused("The proposing model identity was not captured")
        author = authors[-1]
        budget, records, model_steps = (
            review_start_budget(outcome, packages, matter, self.log), [], 0)
        try:
            for package in packages:
                if (budget.spent_out or cancelled() or
                        max_model_calls is not None and model_steps >= max_model_calls):
                    break  # Missing reviews withhold their packages, never assume PASS.
                self._current(outcome, packages=packages, current_owner=current_owner)
                record, spend = self._one(outcome, package, captured, author, budget, cancelled,
                                          packages=packages, current_owner=current_owner)
                budget = budget.spend_on(spend)
                child = next((row for row in self.store.load(
                    outcome.record.identity.matter_id).loop_records
                    if row.identity.turn_id ==
                    f"{outcome.record.identity.turn_id}:verify:{package.id}"), None)
                if child is not None:
                    model_steps += sum(event.kind is StepKind.MODEL_STARTED
                                       for event in child.events)
                if record is not None:
                    records.append(record)
            self._current(outcome, packages=packages, current_owner=current_owner)
        except ReviewRefused as exc:
            # A later pre-dispatch refusal must not hide already completed
            # children from the evaluator's whole-task spending result.
            exc.budget = budget
            raise
        results = tuple(records)
        return IndependentReview(packages, results, release_verified(packages, results),
                                 budget, model_steps)

    def _current(self, outcome, *, packages=None, current_owner=None):
        if not self.session_current():
            raise ReviewRefused("The session no longer permits independent review")
        matter = self.store.load(outcome.record.identity.matter_id)
        if matter is None:
            raise ReviewRefused("The captured file is unavailable")
        saved = self.log.read(outcome.record.identity)
        if saved != outcome.record:
            raise ReviewRefused("The work record differs from the captured proposal")
        if (not saved.terminal or saved.events[-1].payload.get("budget")
                != outcome.budget.as_dict()):
            raise ReviewRefused("The review budget differs from the saved whole-task budget")
        _require_current_source(outcome, matter)
        actual = packages
        if current_owner is not None:
            if (outcome.reason not in (StopReason.PROPOSAL, StopReason.QUESTION,
                                      StopReason.CONVERSATION)
                    or not outcome.record.terminal):
                raise ReviewRefused("Supplemental review requires a completed answer/question turn")
            current_owner(outcome, matter, packages)
        else:
            actual = prepare_claims(outcome, matter)
            if packages is not None and packages != actual:
                raise ReviewRefused("The reviewed packages differ from the captured final proposal")
        try:
            require_current_documents(matter, packages or actual,
                                      self.document_current)
        except ValueError as exc:
            raise ReviewRefused(str(exc)) from exc
        return matter

    def _one(self, outcome, package, captured, author, budget, cancelled, *,
             packages=None, current_owner=None):
        parent = outcome.record.identity
        model = self.verifier.model
        tier = self.verifier.tier
        identity = LoopIdentity(parent.matter_id, parent.advocate_id,
                                f"{parent.turn_id}:verify:{package.id}",
                                digest({"package": package.identity, "author": {
                                    "provider": author["provider"], "model": author["model"]},
                                    "judge": {"provider": model.provider,
                                              "model": model.resolved_model(tier)}}),
                                parent.principles_version, parent.tools_version,
                                self._current(outcome, packages=packages,
                                              current_owner=current_owner).version, parent.mode)
        existing = [row for row in self.store.load(parent.matter_id).loop_records
                    if row.identity.turn_id == identity.turn_id]
        if existing:
            old = existing[0]
            if (len(existing) != 1 or old.identity.offer_hash != identity.offer_hash
                    or old.events[0].payload.get("parent") != parent.fingerprint
                    or old.identity.principles_version != identity.principles_version
                    or old.identity.tools_version != identity.tools_version):
                raise ReviewRefused("The saved review belongs to a changed claim or verifier")
            if not old.terminal:
                raise ReviewRefused("The previous verification's external outcome is unknown")
            # Reconstructed parent's spend excludes child journals. Count the
            # previous review once in this result, without another provider call.
            return saved_verification(package, old, self.log, author)

        journal = None
        reservation = None
        started = time.monotonic()

        def append(kind, payload):
            nonlocal journal
            previous = journal.events[-1].fingerprint if journal else identity.fingerprint
            event = LoopEvent.create(len(journal.events) + 1 if journal else 1, kind,
                                     datetime.now(timezone.utc).isoformat(), payload, previous)
            journal = self.log.append(identity, event)

        def before(prompt, requested_tier, maximum):
            nonlocal reservation
            self._current(outcome, packages=packages, current_owner=current_owner)
            if cancelled():
                raise ReviewRefused("The advocate cancelled before independent dispatch")
            incoming = estimate_tokens((prompt.system or "") + prompt.user)
            cost = self.cost_ceiling(incoming, maximum, requested_tier)
            if (not math.isfinite(cost) or cost < 0
                    or incoming + maximum > budget.max_tokens - budget.spend.tokens
                    or cost > budget.max_cost_usd - budget.spend.cost_usd):
                raise ReviewRefused("The remaining whole-task budget cannot fund this review")
            reservation = Spend(tokens=incoming + maximum, cost_usd=cost)
            append(StepKind.START, {"budget": budget.as_dict(), "package": package.identity,
                                    "parent": parent.fingerprint})
            append(StepKind.MODEL_STARTED, {"prompt": asdict(prompt), "tier": tier.value,
                                           "provider": model.provider,
                                           "model": model.resolved_model(tier),
                                           "max_tokens": maximum,
                                           "reserved_tokens": reservation.tokens,
                                           "reserved_cost_usd": cost})

        def after(result):
            append(StepKind.MODEL_RETURNED,
                   {"result": {"kind": "ModelResult", "value": asdict(result)}})

        def failed(error):
            append(StepKind.FAILURE, {"reason": type(error).__name__,
                                      "usage_measured": error.usage is not None,
                                      "usage": asdict(error.usage) if error.usage else None,
                                      "retries": error.retries})

        record = self.verifier.verify(package, author_provider=author["provider"],
                                      author_model=author["model"], retrieved=captured,
                                      retrieved_documents=captured_documents(outcome.record),
                                      before_dispatch=before, after_dispatch=after,
                                      on_error=failed)
        spend = (Spend(tokens=record.usage.tokens_in + record.usage.tokens_out,
                       cost_usd=record.usage.cost_usd, retries=record.retries)
                 if record.usage is not None else reservation or Spend())
        spend = replace(spend, children=1,
                        elapsed_ms=max(0, int((time.monotonic() - started) * 1000)))
        charged = budget.spend_on(spend)
        # Completing the last admitted child does not invalidate its result;
        # it prevents another child. An actual overflow remains a refusal.
        exhausted = charged.exhausted()
        over_children = bool(charged.max_children and
                             charged.spend.children > charged.max_children)
        if (cancelled() or exhausted not in (Exhausted.NONE, Exhausted.CHILDREN) or over_children
                or reservation is not None and (
                spend.cost_usd > reservation.cost_usd or spend.tokens > reservation.tokens)):
            reason = ("Independent review was cancelled before its verdict could be used"
                      if cancelled() else
                      "Independent review exceeded its admitted whole-task resource boundary")
            unknown = Judgment(reason, (), None)
            record = replace(record, reason=reason, textual_eligible=None,
                             textual_support=unknown, applicability=unknown,
                             inference=unknown, opposition_resolved=unknown)
        if journal is None:
            # A deterministic refusal cost no network tokens. It is still saved.
            append(StepKind.START, {"budget": budget.as_dict(), "package": package.identity,
                                    "parent": parent.fingerprint})
        elif journal.events[-1].kind is StepKind.MODEL_STARTED:
            append(StepKind.FAILURE, {"reason": record.reason, "usage_measured": False})
        append(StepKind.STOP, json.loads(_json({
            "reason": StopReason.PROPOSAL.value if record.releasable else StopReason.REFUSED.value,
            "verification": asdict(record), "spend": asdict(spend), "released": False})))
        return record, spend
