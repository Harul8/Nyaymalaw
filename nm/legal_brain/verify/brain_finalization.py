"""Saved final checks on exact private proposals; no authored clean receipts.

Existing consistency and duty owners interpret actual model reads. Their
dispatches share the whole-task budget and are sealed before use. Currentness
is computed by the existing dependency owner from exact reviewed packages.
An absent prior derivation remains absent, not an empty successful comparison.
"""
from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timezone

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopOutcome,
    StepKind,
    StopReason,
    digest,
)
from nm.legal_brain.orchestrate.loop_log_port import LoopLogPort
from nm.legal_brain.reason.matter_support import DocumentCurrent, require_current_documents
from nm.legal_brain.understand import parties
from nm.legal_brain.understand.brain_context import ContextRefused
from nm.legal_brain.verify import consistency, duty
from nm.legal_brain.verify.brain_release import (
    IndependentReview,
    ReviewRefused,
    captured_findings,
    captured_source_preflight,
    prepare_claims,
)
from nm.legal_brain.verify.output_checks import (
    BoundarySubjects,
    OutputSubjects,
    competence_screen,
    measured_coverage,
    observe_reads,
)
from nm.open_matter import screens
from nm.shared.budget_contracts import Budget, Spend
from nm.shared.model_port import (
    ModelError,
    ModelPort,
    Prompt,
    Tier,
    Usage,
    estimate_tokens,
    require_schema,
)
from nm.shared.store_port import StaleWrite, StorePort
from nm.work_the_file import cascade, deadlines, dependency
from nm.work_the_file.file_mutation_contracts import neutral


@dataclass(frozen=True)
class CheckRead:
    data: dict | None
    reason: str
    spend: Spend
    model_steps: int


@dataclass(frozen=True)
class FinalizationResult:
    subjects: OutputSubjects
    boundaries: BoundarySubjects
    budget: Budget
    model_steps: int


class SavedCheckReader:
    """One durable transport for private owned reads, including failed spend."""
    def __init__(self, *, store: StorePort, log: LoopLogPort, model: ModelPort,
                 session_current: Callable[[], bool], cost_ceiling,
                 current_tools_version: Callable[[], str],
                 current_principles_version: Callable[[], str], max_tokens: int = 1024,
                 document_current: DocumentCurrent | None = None,
                 subject_packages: Callable | None = None):
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("A saved check needs a positive output ceiling")
        if subject_packages is not None and not callable(subject_packages):
            raise ValueError("A saved check needs a trusted callable subject owner")
        self.store, self.log, self.model = store, log, model
        self.session_current, self.cost_ceiling = session_current, cost_ceiling
        self.current_tools_version = current_tools_version
        self.current_principles_version = current_principles_version
        self.max_tokens = max_tokens
        self.document_current = document_current
        # Installation-owned only. Legal finalization still uses prepare_claims;
        # an interaction owner must rebuild its own exact typed subject, not
        # manufacture a legal source merely to obtain a generic saved transport.
        self.subject_packages = prepare_claims if subject_packages is None else subject_packages

    def current(self, outcome):
        identity = outcome.record.identity
        if (not self.session_current()
                or self.current_tools_version() != identity.tools_version
                or self.current_principles_version() != identity.principles_version):
            raise ReviewRefused("The session, source or principles changed before the final check")
        matter = self.store.load(identity.matter_id)
        if (matter is None or matter.advocate_id != identity.advocate_id
                or self.log.read(identity) != outcome.record):
            raise ReviewRefused("The check lacks its actual saved parent and current owned file")
        stop = outcome.record.events[-1].payload if outcome.record.terminal else {}
        if (stop.get("reason") != outcome.reason.value
                or stop.get("proposal") != outcome.proposal
                or stop.get("budget") != outcome.budget.as_dict()):
            raise ReviewRefused("The check differs from its exact saved terminal and whole budget")
        try:
            captured_source_preflight(outcome, matter, document_current=self.document_current)
            packages = self.subject_packages(outcome, matter)
            from nm.legal_brain.verify.verifier import EvidencePackage

            if (not isinstance(packages, tuple)
                    or any(not isinstance(package, EvidencePackage) for package in packages)):
                raise ReviewRefused("The subject owner did not rebuild its typed document packages")
            require_current_documents(matter, packages, self.document_current)
        except ContextRefused as exc:
            raise ReviewRefused(str(exc)) from exc
        except ValueError as exc:
            if isinstance(exc, ReviewRefused):
                raise
            raise ReviewRefused(str(exc)) from exc
        return matter

    def _identity(self, outcome, name, prompt, schema, tier, matter):
        parent = outcome.record.identity
        return LoopIdentity(parent.matter_id, parent.advocate_id,
            f"{parent.turn_id}:check:{name}", digest({
                "parent": outcome.record.events[-1].fingerprint,
                "prompt": asdict(prompt), "schema": schema, "tier": tier.value,
                "provider": self.model.provider, "model": self.model.resolved_model(tier),
                "max_tokens": self.max_tokens}), parent.principles_version,
            parent.tools_version, matter.version, parent.mode)

    def recorded(self, outcome, name, prompt, schema, tier) -> CheckRead | None:
        matter = self.current(outcome)
        identity = self._identity(outcome, name, prompt, schema, tier, matter)
        rows = [row for row in matter.loop_records if row.identity.turn_id == identity.turn_id]
        if not rows:
            return None
        if (len(rows) != 1 or not rows[0].terminal
                or replace(identity, matter_version=rows[0].identity.matter_version)
                != rows[0].identity or self.log.read(rows[0].identity) != rows[0]):
            raise ReviewRefused("The saved check belongs to changed inputs or an unknown outcome")
        row = rows[0]
        start, stop = row.events[0].payload, row.events[-1].payload
        if (start.get("parent") != outcome.record.events[-1].fingerprint
                or start.get("prompt") != neutral(asdict(prompt))
                or start.get("schema") != schema or stop.get("released") is not False):
            raise ReviewRefused("The saved check did not examine these exact subjects")
        dispatched = [event for event in row.events if event.kind is StepKind.MODEL_STARTED]
        returned = [event.payload for event in row.events if event.kind is StepKind.MODEL_RETURNED]
        if len(dispatched) > 1 or len(returned) > 1:
            raise ReviewRefused("The check has an ambiguous dispatch population")
        data = stop["data"]
        if data is not None:
            if len(dispatched) != 1 or len(returned) != 1:
                raise ReviewRefused("A completed check has no actual completed model receipt")
            received = returned[0]["result"]
            if (received["completion"] != "complete" or received["data"] != data
                    or received["provider"] != self.model.provider
                    or received["model"] != self.model.resolved_model(tier)
                    or received["tier"] != tier.value):
                raise ReviewRefused("The interpreted check differs from its actual model response")
            require_schema(data, schema)
        spend = Spend(**stop["spend"])
        if returned:
            raw = returned[0]["result"]
            usage = Usage(**raw["usage"])
            if (spend.tokens != usage.tokens_in + usage.tokens_out
                    or spend.cost_usd != usage.cost_usd or spend.retries != raw["retries"]):
                raise ReviewRefused("The saved check spend differs from its provider receipt")
        elif dispatched:
            errors = [event.payload for event in row.events if event.kind is StepKind.FAILURE]
            measured = errors[-1].get("usage") if errors else None
            if measured is not None:
                usage = Usage(**measured)
                tokens, cost = usage.tokens_in + usage.tokens_out, usage.cost_usd
            else:
                reserved = Spend(**dispatched[0].payload["reserved"])
                tokens, cost = reserved.tokens, reserved.cost_usd
            if spend.tokens != tokens or spend.cost_usd != cost:
                raise ReviewRefused("The failed check lost its measured or reserved spend")
        elif spend.tokens or spend.cost_usd:
            raise ReviewRefused("An undispatched check cannot claim provider spending")
        if spend.children != 1:
            raise ReviewRefused("The actual final-check child must be counted once")
        return CheckRead(data, stop["reason"], spend, len(dispatched))

    def read(self, outcome, name: str, prompt: Prompt, schema: dict, tier: Tier,
             budget: Budget, *, cancelled=lambda: False) -> CheckRead:
        # A supplemental read may carry accumulated actual spend, never a new
        # resource grant. Validate before either replay or creating a journal.
        parent_budget = outcome.budget
        ceilings = ("max_ms", "max_tokens", "max_cost_usd", "max_retries", "max_children")
        if (not isinstance(budget, Budget)
                or any(getattr(budget, key) != getattr(parent_budget, key) for key in ceilings)
                or bool(parent_budget.cancelled_at)
                and budget.cancelled_at != parent_budget.cancelled_at
                or any(getattr(budget.spend, field.name) < getattr(parent_budget.spend, field.name)
                       for field in fields(Spend))):
            raise ReviewRefused("A saved check cannot enlarge or restore its whole-task budget")
        previous = self.recorded(outcome, name, prompt, schema, tier)
        if previous is not None:
            return previous
        matter = self.current(outcome)
        identity = self._identity(outcome, name, prompt, schema, tier, matter)
        journal, reserved, received, dispatched = None, None, None, False
        reason, data = "The owned check did not complete", None
        started = time.monotonic()

        def append(kind, payload):
            nonlocal journal
            event = LoopEvent.create(len(journal.events) + 1 if journal else 1, kind,
                datetime.now(timezone.utc).isoformat(), neutral(payload),
                journal.events[-1].fingerprint if journal else identity.fingerprint)
            try:
                journal = self.log.append(identity, event)
            except StaleWrite as exc:
                # A concurrent file change cannot be overwritten just to save
                # a receipt. Preserve actual paid usage (or the unknown-outcome
                # reservation) in the refusal returned to the budget owner.
                measured_usage = (received.usage if received is not None else
                    Usage(**payload["usage"]) if payload.get("usage") is not None else None)
                measured_spend = (Spend(tokens=measured_usage.tokens_in + measured_usage.tokens_out,
                    cost_usd=measured_usage.cost_usd,
                    retries=received.retries if received is not None else payload.get("retries", 0))
                    if measured_usage is not None else reserved if dispatched else Spend())
                measured_spend = replace(measured_spend, children=1,
                    elapsed_ms=max(0, int((time.monotonic() - started) * 1000)))
                refused = ReviewRefused("The file changed while saving the independent check")
                refused.budget = budget.spend_on(measured_spend)
                raise refused from exc

        append(StepKind.START, {"parent": outcome.record.events[-1].fingerprint,
            "prompt": asdict(prompt), "schema": schema, "budget": budget.as_dict()})
        try:
            incoming = estimate_tokens(prompt.user + (prompt.system or ""))
            cost = self.cost_ceiling(incoming, self.max_tokens, tier)
            if (cancelled() or budget.spent_out or not math.isfinite(cost) or cost < 0
                    or incoming + self.max_tokens > budget.max_tokens - budget.spend.tokens
                    or cost > budget.max_cost_usd - budget.spend.cost_usd
                    or incoming + self.max_tokens > self.model.context_budget(tier)):
                reason = "The whole-task resource or cancellation boundary prevents this check"
            else:
                self.current(outcome)
                reserved = Spend(tokens=incoming + self.max_tokens, cost_usd=cost)
                append(StepKind.MODEL_STARTED, {"prompt": asdict(prompt), "tier": tier.value,
                    "provider": self.model.provider, "model": self.model.resolved_model(tier),
                    "max_tokens": self.max_tokens, "reserved": asdict(reserved)})
                dispatched = True
                received = self.model.structured(prompt, schema, tier, max_tokens=self.max_tokens)
                append(StepKind.MODEL_RETURNED, {"result": asdict(received)})
                if (not received.usable or received.tier is not tier or received.was_downgraded
                        or received.provider != self.model.provider
                        or received.model != self.model.resolved_model(tier)):
                    reason = "The actual owned check was incomplete, downgraded or changed identity"
                else:
                    require_schema(received.data, schema)
                    data, reason = (received.data,
                                    "The existing check owner received its completed read")
        except ModelError as exc:
            reason = f"The owned check is unavailable: {type(exc).__name__}"
            usage = received.usage if received is not None else exc.usage
            append(StepKind.FAILURE, {"reason": reason,
                "usage": asdict(usage) if usage is not None else None,
                "retries": received.retries if received is not None else exc.retries})
        usage = received.usage if received is not None else (
            Usage(**journal.events[-1].payload["usage"])
            if journal.events[-1].kind is StepKind.FAILURE
            and journal.events[-1].payload.get("usage") is not None else None)
        retries = received.retries if received is not None else (
            journal.events[-1].payload.get("retries", 0)
            if journal.events[-1].kind is StepKind.FAILURE else 0)
        spend = (Spend(tokens=usage.tokens_in + usage.tokens_out, cost_usd=usage.cost_usd,
                       retries=retries) if usage is not None else reserved or Spend())
        spend = replace(spend, children=1,
                        elapsed_ms=max(0, int((time.monotonic() - started) * 1000)))
        after = budget.spend_on(spend)
        over = (after.spend.tokens > after.max_tokens
                or after.spend.cost_usd > after.max_cost_usd
                or after.spend.elapsed_ms > after.max_ms
                or after.max_children and after.spend.children > after.max_children
                or reserved is not None and (spend.tokens > reserved.tokens
                                            or spend.cost_usd > reserved.cost_usd))
        if over or cancelled():
            data, reason = None, "The owned check exceeded or lost its admitted resource boundary"
        try:
            self.current(outcome)
            append(StepKind.STOP, {"reason": reason, "data": data,
                "spend": asdict(spend), "released": False,
                "stop": StopReason.PROPOSAL.value if data is not None
                    else StopReason.REFUSED.value})
        except (ReviewRefused, StaleWrite) as exc:
            # The paid response/reservation survives even when a changed owner
            # forbids sealing or returning usable wording. Do not reset cost.
            exc.budget = after
            raise
        return CheckRead(data, reason, spend, int(dispatched))


def recorded_claims(matter, today: date) -> tuple[consistency.Claim, ...]:
    """Existing typed register/posture facts, never model-selected computation."""
    register = deadlines.read_matter(matter)
    out = []
    for thread in matter.threads:
        rows = (tuple(row for row in register.rows if row.thread == thread.id)
                if thread.id in register.assessed and not register.unreadable else None)
        side = thread.posture.side.value if thread.posture.resolved else ""
        out.extend(replace(row, id=f"{thread.id}:{row.id}")
                   for row in consistency.claims_for(None, rows, side, today))
    return tuple(out)


def _original(outcome):
    prompts = [event.payload["prompt"] for event in outcome.record.events
               if event.kind is StepKind.MODEL_STARTED]
    if not prompts or not isinstance(prompts[0].get("user"), str) or not prompts[0]["user"].strip():
        raise ReviewRefused("The final check lacks the original authenticated instruction")
    return prompts[0]["user"]


def _derivations(review):
    return tuple(cascade.Derived(f"claim:{package.id}", package.claim,
        from_facts=tuple(fact.id for fact in package.premises), shown=package.claim)
        for package in review.result.released)


def _file_note(matter):
    return json.dumps({key: value for key, value in neutral(asdict(matter)).items()
                       if key not in {"version", "loop_records"}},
                       ensure_ascii=False, sort_keys=True, allow_nan=False)


def _duty_request(matter, outcome):
    quotable = Quotable(turn=_original(outcome),
        file="\n".join(f.statement for f in matter.facts
                       if f.provenance.kind == "advocate_statement" and not f.superseded_by),
        context=_file_note(matter))
    return quotable, ("duty", duty.build_prompt(quotable), duty.DUTY_SCHEMA, Tier.ROUTINE)


def _currentness(matter, review, outcome):
    at = outcome.record.events[-1].at
    findings = captured_findings(outcome)
    ledger, _, _ = dependency.sync_inputs(dependency.Ledger.from_stored(matter.dependencies),
        matter, findings, reason="Checked private proposal against the current recorded inputs",
        at=at, by=outcome.record.identity.advocate_id)
    nodes = []
    for package in review.result.released:
        documents = (*package.documents, *package.document_contrary)
        document_edges = []
        for span in documents:
            span.validate()
            source = span.source
            ident = f"{source['original_id']}:{source['number']}:{source['start']}:{source['end']}"
            ledger, _ = dependency.observe(ledger, dependency.InputKind.DOCUMENT, ident,
                span.captured_identity,
                reason="Exact currently admitted document derivative window")
            document_edges.append(dependency.Rest(dependency.InputKind.DOCUMENT, ident))
        row = next(item for item in _derivations(review) if item.name == f"claim:{package.id}")
        node = dependency.from_derived(row, authorities=tuple(dict.fromkeys(
            dependency.authority_id(span.finding) for span in (*package.spans, *package.contrary))),
            documents=tuple(edge.id for edge in document_edges),
            reason="Independently verified exact private evidence package", at=at)
        nodes.append(replace(node, rests_on=(*node.rests_on, *(dependency.Rest(
            dependency.InputKind.DERIVED, f"claim:{ident}") for ident in package.dependencies))))
    names = tuple(node.name for node in nodes)
    # Dependency order is closed by the verifier; settle records exact edges.
    return dependency.settle(ledger, tuple(nodes), expected=names, at=at), names or None


class FinalizationService:
    """Dispatch owned checks once, then reconstruct subjects from sealed results."""
    def __init__(self, *, reader: SavedCheckReader, today: Callable[[], date],
                 coverage=None, jurisdiction: str, authority=None):
        self.reader, self.today = reader, today
        self.coverage, self.jurisdiction, self.authority = coverage, jurisdiction, authority

    def _requests(self, matter, outcome, review):
        if prepare_claims(outcome, matter) != review.packages:
            raise ReviewRefused("Final checks cannot read changed package premises")
        candidate = review.candidate_text
        # Journal appends advance the transaction version and add work receipts,
        # not a new case. A private check's exact input must not stale itself.
        file_note = _file_note(matter)
        claims = recorded_claims(matter, self.today())
        quotable, duty_request = _duty_request(matter, outcome)
        return claims, quotable, (
            ("consistency", consistency.build_prompt(candidate, claims, file_note),
             consistency.CONSISTENCY_SCHEMA, consistency.TIER),
            duty_request)

    def prepare(self, outcome: LoopOutcome, review: IndependentReview, *,
                cancelled=lambda: False, max_model_calls: int | None = None) -> FinalizationResult:
        if max_model_calls is not None and (
                type(max_model_calls) is not int or max_model_calls < 0):
            raise ValueError("The remaining check dispatch allowance is a nonnegative integer")
        matter = self.reader.current(outcome)
        from nm.legal_brain.verify.brain_assessment import _saved_review

        _saved_review(outcome, review, matter, self.reader.log)
        claims, _, requests = self._requests(matter, outcome, review)
        budget, steps = review.budget, 0
        for name, prompt, schema, tier in requests:
            if name == "consistency" and (not claims or not review.candidate_text):
                continue
            if budget.spent_out or cancelled():
                break
            existing = self.reader.recorded(outcome, name, prompt, schema, tier)
            if existing is None and max_model_calls is not None and steps >= max_model_calls:
                break
            read = self.reader.read(outcome, name, prompt, schema, tier, budget,
                                    cancelled=cancelled)
            budget, steps = budget.spend_on(read.spend), steps + read.model_steps
        current = self.reader.current(outcome)
        return FinalizationResult(self.subjects(current, outcome, review),
                                  self.boundaries(current, outcome, review), budget, steps)

    def subjects(self, matter, outcome, review) -> OutputSubjects:
        claims, _, requests = self._requests(matter, outcome, review)
        name, prompt, schema, tier = requests[0]
        read = self.reader.recorded(outcome, name, prompt, schema, tier)
        verdict = (consistency.interpret(read.data, review.candidate_text,
                    frozenset(row.id for row in claims)) if read and read.data is not None
                   else consistency.UNVERIFIED)
        ledger, names = _currentness(matter, review, outcome)
        selected = outcome.record.events[0].payload["context"]["brief"]["selected_issue_ids"]
        try:
            transcripts = self.reader.store.transcripts_for(matter.id)
        except OSError as exc:
            history = cascade.DerivationHistory(None, False,
                f"The recorded derivation history could not be read: {type(exc).__name__}")
        else:
            history = cascade.observe_history(matter, transcripts,
                selected_issue_ids=selected, before_turn=outcome.record.identity.turn_id)
        return OutputSubjects(consistency_verdict=verdict, previous_derived=history.prior,
            derivation_history=history,
            derived=_derivations(review), ledger=ledger, dependency_names=names,
            empty_reads=observe_reads(self.reader.model, "empty_decisive"),
            refused_reads=observe_reads(self.reader.model, "refused_reads"),
            coverage=measured_coverage(self.coverage, self.jurisdiction),
            competence=competence_screen(self.coverage, self.jurisdiction))

    def boundaries(self, matter, outcome, review=None) -> BoundarySubjects:
        # Duty is bound to the instruction/current account, not the candidate.
        # It can be reconstructed without another independent-model review.
        prepare_claims(outcome, matter)
        quotable, request = _duty_request(matter, outcome)
        name, prompt, schema, tier = request
        read = self.reader.recorded(outcome, name, prompt, schema, tier)
        refusal = (duty.interpret(quotable, read.data)
                   if read and read.data is not None else duty.UNREAD)
        return BoundarySubjects(screens=screens.from_stored(matter.screens),
            parties=parties.on_file(matter).names, duty=refusal,
            authority=self.authority(matter, outcome) if self.authority else None)
