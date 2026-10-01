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

from nm.Archives.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopOutcome,
    StepKind,
    StopReason,
    digest,
)
from nm.Archives.legal_brain.orchestrate.loop_log_port import LoopLogPort
from nm.Archives.legal_brain.orchestrate.tools import ANSWER_PROPOSAL_SHAPE
from nm.Archives.legal_brain.reason.matter_support import (
    DocumentCurrent,
    MatterDocumentSpan,
    captured_documents,
    require_current_captured_documents,
    require_current_documents,
)
from nm.Archives.legal_brain.retrieve.evidence_port import Finding
from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_record
from nm.Archives.legal_brain.understand.brain_context import ContextRefused, require_recorded_source
from nm.Archives.legal_brain.verify.verifier import (
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
from nm.shared.budget_contracts import Budget, Completion, Exhausted, Spend
from nm.shared.json_values import same_json_value
from nm.shared.model_port import (
    ModelError,
    ModelResult,
    Tier,
    Usage,
    estimate_tokens,
    require_schema,
)
from nm.shared.store_port import StorePort
from nm.work_the_file.matter_contracts import Matter


class ReviewRefused(ValueError):
    """No paid review or published claim can follow a broken captured contract."""


class ProposalBindingRefused(ReviewRefused):
    """Saved authored references fail binding after the captured source is checked.

    This is negative proposal evidence, never an unavailable verifier or a
    permission/currentness failure. It grants no checked text or client release.
    """


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


def _review_spend(raw):
    if not isinstance(raw, dict) or set(raw) != {row.name for row in fields(Spend)}:
        raise ReviewRefused("A saved review lacks its complete typed spending contract")
    if (any(type(raw[row.name]) is not int or raw[row.name] < 0
            for row in fields(Spend) if row.name != "cost_usd")
            or type(raw["cost_usd"]) not in (int, float)
            or not math.isfinite(raw["cost_usd"]) or raw["cost_usd"] < 0):
        raise ReviewRefused("A saved review's actual spending is not finite and typed")
    return Spend(**raw)


def _review_budget_wire(budget):
    # Older STARTs used Budget.as_dict's six-decimal display cost. Preserve that
    # reader, but new admissions retain the complete actual monetary ledger.
    return {**budget.as_dict(), "spend": asdict(budget.spend)}


def saved_review_start_budget(saved):
    """The actual sealed admission ledger, including measured pre-review time."""
    from nm.Archives.legal_brain.orchestrate.loop import _budget_from

    try:
        raw = saved.events[0].payload["budget"]
        if not isinstance(raw, dict):
            raise ValueError("untyped budget")
        _review_spend(raw["spend"])
        if (any(type(raw[key]) is not int or raw[key] < 0 for key in
                ("max_ms", "max_tokens", "max_retries", "max_children"))
                or type(raw["max_cost_usd"]) not in (int, float)
                or not math.isfinite(raw["max_cost_usd"]) or raw["max_cost_usd"] < 0
                or type(raw["cancelled_at"]) is not str):
            raise ValueError("invalid resource grant")
        budget = _budget_from(raw)
        if not (same_json_value(raw, budget.as_dict())
                or same_json_value(raw, _review_budget_wire(budget))):
            raise ValueError("incomplete or inconsistent budget")
        return budget
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewRefused("A saved review has no complete typed START budget") from exc


def _review_budget_join(budget, admitted):
    if (not same_json_value(asdict(replace(admitted, spend=budget.spend,
                                         cancelled_at=budget.cancelled_at)), asdict(budget))
            or budget.cancelled_at and admitted.cancelled_at not in ("", budget.cancelled_at)):
        raise ReviewRefused("A saved review altered its whole-task resource grant")
    values = {row.name: max(getattr(budget.spend, row.name),
                           getattr(admitted.spend, row.name)) for row in fields(Spend)}
    return replace(budget, spend=Spend(**values),
                   cancelled_at=budget.cancelled_at or admitted.cancelled_at)


def _require_review_admission_floor(baseline, admitted):
    for row in fields(Spend):
        value, floor = getattr(admitted.spend, row.name), getattr(baseline.spend, row.name)
        if value < floor and not (row.name == "cost_usd" and value == round(floor, 6)):
            raise ReviewRefused("A review START restored earlier actual whole-task spending")
    if baseline.cancelled_at and admitted.cancelled_at != baseline.cancelled_at:
        raise ReviewRefused("A review START restored a cancelled whole-task budget")


def _shared_review_ledger(outcome, matter, log, *, before=None):
    """Reconstruct ordered actual child checkpoints, never sum whole START ledgers."""
    parent = outcome.record.identity
    children = sorted((row for row in matter.loop_records if
        row.identity.turn_id.startswith((f"{parent.turn_id}:verify:",
                                         f"{parent.turn_id}:check:"))
        and (before is None or row.identity.matter_version < before)),
        key=lambda row: row.identity.matter_version)
    budget, seen = outcome.budget, set()
    end = parent.matter_version + len(outcome.record.events)
    for saved in children:
        ident = saved.identity
        is_check = ident.turn_id.startswith(f"{parent.turn_id}:check:")
        expected_parent = outcome.record.events[-1].fingerprint if is_check else parent.fingerprint
        if (ident.turn_id in seen or not saved.terminal or log.read(ident) != saved
                or ident.matter_id != parent.matter_id or ident.advocate_id != parent.advocate_id
                or ident.principles_version != parent.principles_version
                or ident.tools_version != parent.tools_version or ident.mode != parent.mode
                or ident.matter_version < end
                or saved.events[0].payload.get("parent") != expected_parent):
            raise ReviewRefused("Shared review spending lacks its exact ordered sealed children")
        seen.add(ident.turn_id)
        stop = saved.events[-1].payload
        if (stop.get("released") is not False or "spend" not in stop
                or ("data" if is_check else "verification") not in stop):
            raise ReviewRefused("Shared review spending has an unknown external outcome")
        spend = _review_spend(stop["spend"])
        if spend.children != 1:
            raise ReviewRefused("A shared review must charge its actual child exactly once")
        admitted = saved_review_start_budget(saved)
        _require_review_admission_floor(budget, admitted)
        # Display-rounded historical START costs cannot replace earlier exact
        # measured STOP costs. The join preserves those exact costs and all time.
        budget = _review_budget_join(budget, admitted).spend_on(spend)
        end = ident.matter_version + len(saved.events)
        if before is not None and end > before:
            raise ReviewRefused("A review START overlaps an unfinished sibling journal")
    return budget


def saved_review_budget(outcome, saved, spend, matter, log):
    """Historical review endpoint; children admitted later cannot rewrite it."""
    baseline = _shared_review_ledger(outcome, matter, log,
                                     before=saved.identity.matter_version)
    admitted = saved_review_start_budget(saved)
    _require_review_admission_floor(baseline, admitted)
    return _review_budget_join(baseline, admitted).spend_on(spend)


def shared_review_budget(outcome, packages, matter, log, proposed):
    """Carry actual check/verification spend without replaying a grant or charging twice.

    The saved parent stays immutable. Selected saved verifications are charged
    by _one; subtract only their actual sealed spend, with the reconstructed
    sibling ledger as a hard floor. Elapsed time never goes backwards, even
    temporarily to admit a replay. Larger measured spend can only reduce work.
    """
    baseline = _shared_review_ledger(outcome, matter, log)
    selected = {f"{outcome.record.identity.turn_id}:verify:{row.id}" for row in packages}
    replayed, seen = Spend(), set()
    parent = outcome.record.identity
    for saved in matter.loop_records:
        ident = saved.identity.turn_id
        is_check = ident.startswith(f"{parent.turn_id}:check:")
        if not is_check and ident not in selected:
            continue
        if (ident in seen or not saved.terminal or log.read(saved.identity) != saved
                or saved.identity.matter_id != parent.matter_id
                or saved.identity.advocate_id != parent.advocate_id
                or saved.identity.principles_version != parent.principles_version
                or saved.identity.tools_version != parent.tools_version
                or saved.identity.mode != parent.mode):
            raise ReviewRefused("Shared review spending lacks its exact sealed child population")
        seen.add(ident)
        expected_parent = outcome.record.events[-1].fingerprint if is_check else parent.fingerprint
        stop = saved.events[-1].payload
        if (saved.events[0].payload.get("parent") != expected_parent
                or stop.get("released") is not False or "spend" not in stop
                or is_check and "data" not in stop
                or not is_check and "verification" not in stop):
            raise ReviewRefused("Shared review spending has an unknown parent or outcome")
        spent = Spend(**stop["spend"])
        if (spent.children != 1 or any(
                type(getattr(spent, row.name)) is not int or getattr(spent, row.name) < 0
                for row in fields(Spend) if row.name != "cost_usd")
                or type(spent.cost_usd) not in (int, float)
                or not math.isfinite(spent.cost_usd) or spent.cost_usd < 0):
            raise ReviewRefused("A shared child's actual spending is not finite and typed")
        if not is_check:
            replayed = replayed.plus(spent)
    if proposed is None:
        proposed = baseline
    if (not isinstance(proposed, Budget)
            or not same_json_value(asdict(replace(proposed, spend=outcome.budget.spend,
                       cancelled_at=outcome.budget.cancelled_at)), asdict(outcome.budget))
            or outcome.budget.cancelled_at
            and proposed.cancelled_at != outcome.budget.cancelled_at):
        raise ReviewRefused("A supplemental review cannot alter its sealed resource grant")
    values = {}
    for row in fields(Spend):
        value, floor = getattr(proposed.spend, row.name), getattr(baseline.spend, row.name)
        if row.name == "cost_usd":
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or value + 1e-12 < floor):
                raise ReviewRefused("Supplemental review cannot restore actual paid spending")
        elif type(value) is not int or value < floor:
            raise ReviewRefused("Supplemental review cannot restore actual child spending")
        values[row.name] = (value if row.name == "elapsed_ms" else
            max(getattr(outcome.budget.spend, row.name), value - getattr(replayed, row.name)))
    return replace(proposed, spend=Spend(**values))


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


def captured_source_preflight(outcome: LoopOutcome, matter: Matter, *, document_current):
    """Whole saved population and actual document authority, before author errors.

    The caller still owns current session, grant and runtime generation checks.
    This is not a merit verdict or a surrogate legal package.
    """
    _require_current_source(outcome, matter)
    findings = captured_findings(outcome)
    try:
        documents = captured_documents(outcome.record)
        require_current_captured_documents(matter, documents, document_current)
    except ValueError as exc:
        raise ReviewRefused(str(exc)) from exc
    return findings, documents


def prepare_claims(outcome: LoopOutcome, matter: Matter) -> tuple[EvidencePackage, ...]:
    """Bind each final paragraph to exact journal sources and current file premises."""
    if (outcome.reason is not StopReason.PROPOSAL or not outcome.record.terminal
            or outcome.record.events[-1].payload.get("reason") != outcome.reason.value
            or outcome.record.events[-1].payload.get("proposal") != outcome.proposal):
        raise ReviewRefused("The saved work did not end in this exact answer proposal")
    _require_current_source(outcome, matter)
    require_schema(outcome.proposal, ANSWER_PROPOSAL_SHAPE)
    # Decode the whole captured population before classifying any authored
    # mistake. A broken receipt must never purchase a paid repair, including
    # when the proposal is empty or carries duplicate identifiers.
    findings = captured_findings(outcome)
    try:
        documents = captured_documents(outcome.record)
    except ValueError as exc:
        raise ReviewRefused(str(exc)) from exc
    rows = outcome.proposal["claims"]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ProposalBindingRefused("A proposal needs nonempty, uniquely identified claims")
    facts = {fact.id: fact for fact in matter.facts}
    packages = []
    for row in rows:
        def spans(windows, prefix):
            result, document_result = [], []
            for index, window in enumerate(windows):
                quote = window["quote"]
                if not quote.strip():
                    raise ProposalBindingRefused("A source window cannot be empty")
                candidates = [finding for finding in findings
                              if finding.locator == window["locator"] and quote in finding.span]
                document_candidates = [document for document in documents
                                       if document.locator == window["locator"]
                                       and quote in document.text]
                if len(candidates) + len(document_candidates) != 1:
                    raise ProposalBindingRefused("A window must identify one exact captured source")
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
            raise ProposalBindingRefused("A premise must identify one recorded fact in this file")
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
    record, spend = _decode_verdict(stop["verification"]), _review_spend(stop["spend"])
    budget = saved_review_start_budget(saved)
    if spend.children != 1:
        raise ReviewRefused("The saved verification lacks its actual one-child charge")
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
               max_model_calls: int | None = None,
               budget: Budget | None = None) -> IndependentReview:
        matter = self._current(outcome)
        packages = prepare_claims(outcome, matter)
        return self.review_packages(outcome, packages, cancelled=cancelled,
                                   max_model_calls=max_model_calls, budget=budget)

    def review_packages(self, outcome: LoopOutcome, packages: tuple[EvidencePackage, ...], *,
                        current_owner=None, current_sources=None, cancelled=lambda: False,
                        max_model_calls: int | None = None,
                        budget: Budget | None = None) -> IndependentReview:
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
            shared_review_budget(outcome, packages, matter, self.log, budget), [], 0)
        selected = {f"{outcome.record.identity.turn_id}:verify:{row.id}" for row in packages}
        unreplayed = {row.identity.turn_id: replace(
                          _review_spend(row.events[-1].payload["spend"]), elapsed_ms=0)
                      for row in matter.loop_records if row.identity.turn_id in selected}

        def retain_unreplayed():
            nonlocal budget
            for spent in unreplayed.values():
                budget = budget.spend_on(spent)
            unreplayed.clear()

        try:
            for package in packages:
                if (budget.spent_out or cancelled() or
                        max_model_calls is not None and model_steps >= max_model_calls):
                    break  # Missing reviews withhold their packages, never assume PASS.
                self._current(outcome, packages=packages, current_owner=current_owner)
                record, spend = self._one(outcome, package, captured, author, budget, cancelled,
                                          packages=packages, current_owner=current_owner)
                child = next((row for row in self.store.load(
                    outcome.record.identity.matter_id).loop_records
                    if row.identity.turn_id ==
                    f"{outcome.record.identity.turn_id}:verify:{package.id}"), None)
                if child is not None:
                    charged_spend = (replace(spend, elapsed_ms=0)
                                     if child.identity.turn_id in unreplayed else spend)
                    budget = _review_budget_join(
                        budget, saved_review_start_budget(child)).spend_on(charged_spend)
                    model_steps += sum(event.kind is StepKind.MODEL_STARTED
                                       for event in child.events)
                    unreplayed.pop(child.identity.turn_id, None)
                else:
                    raise ReviewRefused("The completed review lacks its actual START receipt")
                if record is not None:
                    records.append(record)
            self._current(outcome, packages=packages, current_owner=current_owner)
        except ReviewRefused as exc:
            # A later pre-dispatch refusal must not hide already completed
            # children from the evaluator's whole-task spending result.
            retain_unreplayed()
            exc.budget = budget
            raise
        retain_unreplayed()
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
                != outcome.budget.as_dict()
                or saved.events[-1].payload.get("reason") != outcome.reason.value
                or saved.events[-1].payload.get("proposal") != outcome.proposal):
            raise ReviewRefused("The review budget differs from the saved whole-task budget")
        captured_source_preflight(outcome, matter, document_current=self.document_current)
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
            append(StepKind.START, {"budget": _review_budget_wire(budget),
                                    "package": package.identity,
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
            append(StepKind.START, {"budget": _review_budget_wire(budget),
                                    "package": package.identity,
                                    "parent": parent.fingerprint})
        elif journal.events[-1].kind is StepKind.MODEL_STARTED:
            append(StepKind.FAILURE, {"reason": record.reason, "usage_measured": False})
        append(StepKind.STOP, json.loads(_json({
            "reason": StopReason.PROPOSAL.value if record.releasable else StopReason.REFUSED.value,
            "verification": asdict(record), "spend": asdict(spend), "released": False})))
        return record, spend
