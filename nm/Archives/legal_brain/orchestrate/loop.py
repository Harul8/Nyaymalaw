"""Budgeted model-decides/tool-acts loop, isolated from the live TurnEngine.

It returns a proposal to the harness, NEVER an approved Answer. Durable starts
precede every potentially paid or mutating operation. An interrupted operation
is not repeated on restart: its external outcome may be unknown.
"""
from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone

from nm.Archives.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopLimits,
    LoopOutcome,
    LoopRecord,
    StepKind,
    StopReason,
    digest,
)
from nm.Archives.legal_brain.orchestrate.loop_log_port import LoopLogPort
from nm.Archives.legal_brain.orchestrate.tool_offers import OfferRefused
from nm.Archives.legal_brain.orchestrate.tools import (
    TERMINAL_REASONS,
    DelegatedToolResult,
    DelegationGrant,
    DelegationPolicy,
    PreparedToolResult,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.Archives.legal_brain.understand.brain_context import ContextRefused, ContextSession, assemble_brief
from nm.shared.budget_contracts import Budget, Spend
from nm.shared.model_port import (
    ModelError,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    ToolMessage,
    estimate_tokens,
    require_tool_calls,
    tool_request_text,
)
from nm.work_the_file.original_instruction import capture_original_instruction


class LoopRunner:
    def __init__(self, *, model: ModelPort, tools: ToolRegistry, log: LoopLogPort,
                 cost_ceiling: Callable[[int, int, Tier], float],
                 monotonic: Callable[[], float] = time.monotonic,
                 clock: Callable[[], datetime] | None = None, current_matter=None):
        self._model = model
        self._tools = tools
        self._log = log
        self._cost_ceiling = cost_ceiling
        self._monotonic = monotonic
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._current_matter = current_matter

    def run(self, identity: LoopIdentity, prompt: Prompt, limits: LoopLimits,
            *, cancelled: Callable[[], bool] = lambda: False,
            tier: Tier = Tier.ROUTINE, context_record: dict | None = None,
            session: ContextSession | None = None,
            feedback_identity: str = "", scope_identity: str = "") -> LoopOutcome:
        for value in (feedback_identity, scope_identity):
            if value and (len(value) != 64 or
                    any(c not in "0123456789abcdef" for c in value)):
                raise ValueError("repair feedback and scope have exact captured identities")
        if identity.tools_version != self._tools.version:
            raise ValueError("the registered tools changed after turn admission")
        initial_offer = self._tools.offer_state()
        if session is not None:
            session.tool_offer.require_initial(initial_offer)
        if identity.offer_hash != digest({"user": prompt.user, "system": prompt.system,
                                         "operation": prompt.operation}):
            raise ValueError("the prompt differs from the original admitted instruction")
        original_instruction = capture_original_instruction(prompt)
        if session is not None and (session.principles.version != identity.principles_version
                                    or session.system != prompt.system):
            raise ValueError("the context differs from the admitted principles and prefix")
        model_identity = {"provider": self._model.provider,
                          "model": self._model.resolved_model(tier), "tier": tier.value}
        if session is not None and (session.provider != model_identity["provider"]
                                    or session.model != model_identity["model"]):
            raise ValueError("the provider/model differs from the admitted context")
        saved = self._log.read(identity)
        if saved is not None and saved.events:
            start = saved.events[0].payload
            if (start["max_steps"] != limits.max_steps
                    or start["per_call_tokens"] != limits.per_call_tokens
                    or start.get("max_stagnant_steps", 2) != limits.max_stagnant_steps
                    or any(start["budget"][key] != limits.budget.as_dict()[key]
                           for key in ("max_ms", "max_tokens", "max_cost_usd", "max_children",
                                       "max_retries"))):
                raise ValueError("the resource limits differ from the saved whole-task admission")
            if saved.events[0].payload.get("feedback_identity", "") != feedback_identity:
                raise ValueError("the repair feedback differs from its saved admission")
            if saved.events[0].payload.get("scope_identity", "") != scope_identity:
                raise ValueError("the dispute scope differs from its saved admission")
            if saved.events[0].payload.get("model_identity") != model_identity:
                raise ValueError("the provider/model differs from its saved admission")
            if ("original_instruction" in start
                    and start["original_instruction"] != original_instruction):
                raise ValueError("the original instruction differs from its saved admission")
            # Replaying a completed result is free. A crashed invocation is
            # intentionally not resumed by blindly calling its tools again.
            if saved.terminal:
                payload = saved.events[-1].payload
                return LoopOutcome(StopReason(payload["reason"]), saved,
                                   _budget_from(payload["budget"]), payload["proposal"])
            budget = _last_budget(saved, limits.budget)
            return self._stop(identity, saved, budget, StopReason.INTERRUPTED)
        record = saved or LoopRecord(identity)
        record = self._append(identity, record, StepKind.START,
                              {"budget": limits.budget.as_dict(),
                               "max_steps": limits.max_steps,
                               "per_call_tokens": limits.per_call_tokens,
                               "max_stagnant_steps": limits.max_stagnant_steps,
                               "feedback_identity": feedback_identity,
                               "scope_identity": scope_identity,
                               "model_identity": model_identity,
                               "original_instruction": original_instruction,
                               "tools": [asdict(row) for row in self._tools.definitions],
                               "tool_offer": initial_offer.to_record(),
                               "context": session.to_record() if session else context_record or {}})
        return self._work(identity, prompt, limits, record, cancelled, tier, session)

    def _append(self, identity, record, kind, payload, *, mutation=None):
        previous = record.events[-1].fingerprint if record.events else identity.fingerprint
        event = LoopEvent.create(len(record.events) + 1, kind,
                                 self._clock().isoformat(), payload, previous)
        return (self._log.append(identity, event) if mutation is None else
                self._log.append_mutation(identity, event, mutation))

    def _stop(self, identity, record, budget, reason, proposal=None):
        candidate = proposal or {}
        record = self._append(identity, record, StepKind.STOP,
                              {"reason": reason.value, "budget": budget.as_dict(),
                               "proposal": candidate, "released": False})
        return LoopOutcome(reason, record, budget, candidate)

    def _work(self, identity, prompt, limits, record, cancelled, tier, session):
        budget = limits.budget
        tool_offer = self._tools.offer_state()
        started = self._monotonic()
        messages: tuple[ToolMessage, ...] = session.messages if session else ()
        seen_calls: set[str] = set()
        read_results: set[str] = set()
        stagnant = 0
        steps = 0
        base_ms = budget.spend.elapsed_ms
        admitted = record.events[0].payload["model_identity"]
        known_issue_ids = session.brief.selected_issue_ids if session else ()
        whole_file_scope = record.events[0].payload.get("scope_identity") == digest(
            {"requested_issue_ids": []})

        def measured(current: Budget) -> Budget:
            return replace(current, spend=replace(
                current.spend, elapsed_ms=base_ms +
                max(0, int((self._monotonic() - started) * 1000))))

        while True:
            budget = measured(budget)
            if (self._model.provider != admitted["provider"]
                    or self._model.resolved_model(tier) != admitted["model"]
                    or tier.value != admitted["tier"]):
                return self._stop(identity, record, budget, StopReason.PROVIDER)
            if self._tools.version != identity.tools_version:
                return self._stop(identity, record, budget, StopReason.REFUSED)
            if cancelled():
                return self._stop(identity, record, budget.cancel(self._clock().isoformat()),
                                  StopReason.CANCELLED)
            if budget.spent_out or steps >= limits.max_steps:
                return self._stop(identity, record, budget, StopReason.BUDGET)
            if session:
                try:
                    offered = session.offered_definitions
                    incoming = _request_tokens(prompt, offered, messages)
                    if incoming + limits.per_call_tokens > session.policy.max_tokens:
                        if self._current_matter is None:
                            raise ContextRefused(
                                "no_context_owner", "Safe compaction is unavailable.")
                        matter = self._current_matter(identity.matter_id)
                        if (matter is None or matter.advocate_id != identity.advocate_id
                                or matter.version != identity.matter_version + len(record.events)):
                            raise ContextRefused("stale_context", "The checked file moved.")
                        reads = tuple(event.payload["receipt"] for event in record.events
                                      if event.kind is StepKind.TOOL_RETURNED
                                      and event.payload["receipt"]["kind"] == "source")
                        session.compact_for_request(matter, prompt, offered,
                                                    source_reads=reads)
                        messages = session.messages
                    session.assert_request(prompt.system, messages,
                                           model=self._model.resolved_model(tier), tools=offered)
                except ContextRefused:
                    return self._stop(identity, record, budget, StopReason.CONTEXT)
            else:
                offered = tool_offer.definitions
            incoming = _request_tokens(prompt, offered, messages)
            remaining = budget.max_tokens - budget.spend.tokens - incoming
            outgoing = min(limits.per_call_tokens, remaining)
            if outgoing <= 0:
                return self._stop(identity, record, budget, StopReason.BUDGET)
            reserved_cost = self._cost_ceiling(incoming, outgoing, tier)
            if not math.isfinite(reserved_cost) or reserved_cost < 0:
                raise ValueError("the model price must bound this complete request")
            if budget.spend.cost_usd + reserved_cost > budget.max_cost_usd:
                return self._stop(identity, record, budget, StopReason.BUDGET)
            admitted_provider, admitted_model = admitted["provider"], admitted["model"]
            if (self._model.provider != admitted_provider
                    or self._model.resolved_model(tier) != admitted_model):
                return self._stop(identity, record, budget, StopReason.PROVIDER)
            record = self._append(identity, record, StepKind.MODEL_STARTED,
                                  {"budget": budget.as_dict(), "tier": tier.value,
                                   "provider": admitted_provider,
                                   "model": admitted_model,
                                   "prompt": asdict(prompt),
                                   "reserved_tokens": incoming + outgoing,
                                   "reserved_cost_usd": reserved_cost,
                                   "max_tokens": outgoing, "messages": _messages(messages),
                                   "tools": [asdict(row) for row in offered],
                                   "context": session.to_record() if session else {}})
            steps += 1
            try:
                result = self._model.tool_call(prompt, offered, tier,
                                               messages=messages, max_tokens=outgoing)
            except ModelError as exc:
                usage = getattr(exc, "usage", None)
                # Unknown outcomes retain the full reservation, including
                # after a restart. Unknown cost is never silently zero.
                spend = _spend(usage, getattr(exc, "retries", 0)) if usage else Spend(
                    tokens=incoming + outgoing, cost_usd=reserved_cost)
                budget = measured(budget.spend_on(spend))
                record = self._append(identity, record, StepKind.FAILURE,
                                      {"kind": type(exc).__name__, "budget": budget.as_dict(),
                                       "usage_measured": usage is not None,
                                       "error": {"kind": type(exc).__name__, "message": str(exc),
                                                 "usage": asdict(usage) if usage else None,
                                                 "latency_ms": getattr(exc, "latency_ms", 0),
                                                 "retries": getattr(exc, "retries", 0)}})
                return self._stop(identity, record, budget, StopReason.PROVIDER)
            budget = measured(budget.spend_on(_spend(result.usage, result.retries)))
            response = {"text": result.text, "calls": [asdict(c) for c in result.calls],
                        "model": result.model, "provider": result.provider,
                        "completion": result.completion.value,
                        "result": {"kind": "ToolCallResult", "value": asdict(result)},
                        "budget": budget.as_dict()}
            record = self._append(identity, record, StepKind.MODEL_RETURNED, response)
            if ((result.provider, result.model, result.tier) !=
                    (admitted_provider, admitted_model, tier)
                    or self._model.provider != admitted_provider
                    or self._model.resolved_model(tier) != admitted_model
                    or not result.completion.usable_for_legal_work):
                # Retain the measured response and its cost, but an unadmitted
                # identity may not execute a tool or supply a checked proposal.
                return self._stop(identity, record, budget, StopReason.PROVIDER)
            if budget.spent_out or result.usage.cost_usd > reserved_cost:
                return self._stop(identity, record, budget, StopReason.BUDGET)
            if cancelled():
                return self._stop(identity, record, budget.cancel(self._clock().isoformat()),
                                  StopReason.CANCELLED)
            if not result.calls:
                # Free-form model text is not a terminal, checked contract.
                return self._stop(identity, record, budget, StopReason.NO_PROGRESS)
            try:
                require_tool_calls(result.calls, offered, messages)
            except (SchemaViolation, ValueError):
                record = self._append(identity, record, StepKind.FAILURE,
                    {"kind": "unoffered_or_invalid_tool", "budget": budget.as_dict()})
                return self._stop(identity, record, budget, StopReason.REFUSED)
            if any(call.call_id in seen_calls for call in result.calls):
                return self._stop(identity, record, budget, StopReason.NO_PROGRESS)
            message = ToolMessage("assistant", result.text or "", result.calls)
            if session:
                try:
                    session.append(message, defer_fit=True)
                except ContextRefused:
                    return self._stop(identity, record, budget, StopReason.CONTEXT)
            messages += (message,)
            for call in result.calls:
                budget = measured(budget)
                if self._tools.version != identity.tools_version:
                    return self._stop(identity, record, budget, StopReason.REFUSED)
                if cancelled():
                    return self._stop(identity, record, budget.cancel(self._clock().isoformat()),
                                      StopReason.CANCELLED)
                if budget.spent_out or steps >= limits.max_steps:
                    return self._stop(identity, record, budget, StopReason.BUDGET)
                seen_calls.add(call.call_id)
                try:
                    policy = self._tools.delegation_for(call.name)
                except ToolRefused:
                    policy = None  # The normal admitted invocation records the refusal.
                grant = (_delegation_grant(budget, policy, limits.max_steps - steps - 1)
                         if policy is not None else None)
                if policy is not None and grant is None:
                    return self._stop(identity, record, budget, StopReason.BUDGET)
                record = self._append(identity, record, StepKind.TOOL_STARTED,
                                      {"call": asdict(call), "budget": budget.as_dict(),
                                       "delegation": grant.as_dict() if grant else None})
                steps += 1
                try:
                    result_receipt = self._tools.invoke(call, ToolContext(
                        identity, identity.matter_version + len(record.events), prompt.user,
                        grant, cancelled, known_issue_ids))
                except ToolRefused as exc:
                    # Late authority refusal cannot refund work already paid for.
                    if grant is not None:
                        budget = (_checked_child_budget(grant, exc.delegated)
                                  if exc.delegated else _unknown_child_budget(grant))
                    budget = measured(budget)
                    record = self._append(identity, record, StepKind.FAILURE,
                                          {"kind": "tool_boundary_refused",
                                           "call_id": call.call_id,
                                           "delegation_usage_measured": exc.delegated is not None,
                                           "budget": budget.as_dict()})
                    return self._stop(identity, record, budget, StopReason.REFUSED)
                if isinstance(result_receipt, DelegatedToolResult):
                    budget = _checked_child_budget(grant, result_receipt)
                    steps += result_receipt.steps_used
                budget = measured(budget)
                if self._tools.version != identity.tools_version:
                    return self._stop(identity, record, budget, StopReason.REFUSED)
                mutation = (result_receipt.mutation
                            if isinstance(result_receipt, PreparedToolResult) else None)
                receipt = (result_receipt.envelope if isinstance(result_receipt,
                           (PreparedToolResult, DelegatedToolResult)) else result_receipt)
                payload = {"call_id": call.call_id, "receipt": json.loads(receipt.wire()),
                           "budget": budget.as_dict()}
                if isinstance(result_receipt, DelegatedToolResult):
                    payload.update(child_steps=result_receipt.steps_used,
                                   child_transcript=result_receipt.transcript,
                                   child_released=False)
                if mutation is not None:
                    if cancelled() or budget.spent_out:
                        # Preparing a projection is not applying it. Refusal
                        # records remain durable without changing the file.
                        record = self._append(identity, record, StepKind.FAILURE,
                                              {"kind": "write_not_committed",
                                               "call_id": call.call_id,
                                               "budget": budget.as_dict()})
                        reason = StopReason.CANCELLED if cancelled() else StopReason.BUDGET
                        return self._stop(identity, record, budget, reason)
                try:
                    if mutation is not None:
                        selected = session.brief.selected_issue_ids if session else ()
                        checked = assemble_brief(mutation.after, selected,
                                                 advocate_id=identity.advocate_id)
                        payload.update(mutation_identity=mutation.identity,
                                       checked_snapshot=checked.snapshot_id)
                    record = self._append(identity, record, StepKind.TOOL_RETURNED,
                                          payload, mutation=mutation)
                except ToolRefused:
                    # The actual source/permission owner may revoke between the
                    # registry post-check and the transactional precommit. It
                    # still owns refusal here: do not leave a crashed turn or
                    # count an unapplied projection as an admitted scope.
                    record = self._append(identity, record, StepKind.FAILURE,
                                          {"kind": "write_boundary_refused",
                                           "call_id": call.call_id,
                                           "budget": budget.as_dict()})
                    return self._stop(identity, record, budget, StopReason.REFUSED)
                if mutation is not None and whole_file_scope:
                    # Only a committed dispute extends a whole-file context.
                    # Explicit narrow scopes never inherit unrelated disputes.
                    known_issue_ids = tuple(thread.id for thread in mutation.after.threads)
                if session:
                    try:
                        session.load_checked_schema(call, receipt)
                    except ContextRefused:
                        return self._stop(identity, record, budget, StopReason.REFUSED)
                else:
                    try:
                        tool_offer = tool_offer.loaded_by(call, receipt)
                    except OfferRefused:
                        return self._stop(identity, record, budget, StopReason.REFUSED)
                if (isinstance(result_receipt, DelegatedToolResult)
                        and _child_overrun(grant, result_receipt)):
                    return self._stop(identity, record, budget, StopReason.BUDGET)
                if budget.spent_out:
                    return self._stop(identity, record, budget, StopReason.BUDGET)
                if cancelled():
                    return self._stop(identity, record, budget.cancel(self._clock().isoformat()),
                                      StopReason.CANCELLED)
                message = ToolMessage("tool", receipt.wire(), call_id=call.call_id)
                if session:
                    try:
                        session.append(message, defer_fit=True)
                    except ContextRefused:
                        return self._stop(identity, record, budget, StopReason.CONTEXT)
                messages += (message,)
                if receipt.effect in TERMINAL_REASONS:
                    if call is not result.calls[-1]:
                        # An alleged terminal before unfinished tool calls
                        # is not a completed tool round.
                        return self._stop(identity, record, budget, StopReason.NO_PROGRESS)
                    reason = TERMINAL_REASONS[receipt.effect]
                    return self._stop(identity, record, budget, reason, receipt.data)
                # Progress is new content/state, NOT volatile audit versions,
                # call IDs, timestamps, or repeated requests in new wording.
                key = digest({"tool": call.name, "data": json.loads(receipt.wire())["data"],
                              "outcome": receipt.outcome.value,
                              "availability": receipt.availability.value,
                              "assessment": receipt.assessment.value,
                              "reason": receipt.reason})
                stagnant = stagnant + 1 if key in read_results else 0
                read_results.add(key)
                if stagnant >= limits.max_stagnant_steps:
                    return self._stop(identity, record, budget, StopReason.NO_PROGRESS)


def _messages(messages):
    return [asdict(message) for message in messages]


def _request_tokens(prompt, tools, messages) -> int:
    definitions = tools.definitions if isinstance(tools, ToolRegistry) else tools
    return estimate_tokens(tool_request_text(prompt, definitions, messages))


def _spend(usage, retries) -> Spend:
    if any(type(v) is not int or v < 0 for v in (
            usage.tokens_in, usage.tokens_out, retries)) or not math.isfinite(
                usage.cost_usd) or usage.cost_usd < 0:
        raise ValueError("model usage is not a valid whole-task spending receipt")
    return Spend(tokens=usage.tokens_in + usage.tokens_out,
                 cost_usd=usage.cost_usd, retries=retries)


def _budget_from(value):
    return Budget(**{key: value[key] for key in (
        "max_ms", "max_tokens", "max_cost_usd", "max_retries", "max_children", "cancelled_at")},
                  spend=Spend(**value["spend"]))


def _last_budget(record, fallback):
    for event in reversed(record.events):
        payload = event.payload
        if "budget" in payload:
            budget = _budget_from(payload["budget"])
            if event.kind is StepKind.MODEL_STARTED:
                # No completion receipt: this reservation is still spent.
                budget = budget.spend_on(Spend(tokens=payload["reserved_tokens"],
                                               cost_usd=payload["reserved_cost_usd"]))
            elif event.kind is StepKind.TOOL_STARTED and payload.get("delegation"):
                reservation = payload["delegation"]["policy"]
                budget = budget.spend_on(Spend(
                    tokens=reservation["max_tokens"], cost_usd=reservation["max_cost_usd"],
                    elapsed_ms=reservation["max_ms"], children=1, failed_children=1))
            return budget
    return fallback


def _delegation_grant(budget: Budget, policy: DelegationPolicy, steps: int):
    # A zero Budget ceiling means unbounded, not forbidden. A child therefore
    # requires an explicit admission rather than treating zero as permission.
    if budget.max_children <= 0 or budget.spend.children >= budget.max_children or steps <= 0:
        return None
    tokens = min(policy.max_tokens, budget.max_tokens - budget.spend.tokens)
    cost = min(policy.max_cost_usd, budget.max_cost_usd - budget.spend.cost_usd)
    millis = min(policy.max_ms, budget.max_ms - budget.spend.elapsed_ms)
    if tokens <= 0 or cost <= 0 or millis <= 0:
        return None
    return DelegationGrant(budget, DelegationPolicy(
        min(policy.max_steps, steps), tokens, cost, millis))


def _unknown_child_budget(grant):
    policy = grant.policy
    return grant.budget.spend_on(Spend(
        tokens=policy.max_tokens, cost_usd=policy.max_cost_usd,
        elapsed_ms=policy.max_ms, children=1, failed_children=1))


def _checked_child_budget(grant, result):
    if not isinstance(grant, DelegationGrant) or not isinstance(result, DelegatedToolResult):
        raise ValueError("delegated spend needs its trusted parent reservation")
    previous, current = grant.budget, result.budget
    if (replace(current, spend=previous.spend) != previous
            or result.steps_used > grant.policy.max_steps):
        raise ValueError("a child changed the whole-task grant or exceeded its admitted steps")
    deltas = {key: getattr(current.spend, key) - getattr(previous.spend, key)
              for key in previous.spend.__dataclass_fields__}
    if (any(not math.isfinite(value) or value < 0 for value in deltas.values())
            or deltas["children"] != 1 or deltas["failed_children"] > 1
            or any(type(getattr(current.spend, key)) is not int for key in deltas
                   if key != "cost_usd")):
        raise ValueError("a child refunded spend, forged counters or exceeded its reservation")
    return current


def _child_overrun(grant, result):
    # Actual provider overage or late completion is retained, never replaced by
    # the smaller reservation. It stops further parent work after journalling.
    return any(getattr(result.budget.spend, key) - getattr(grant.budget.spend, key) > maximum
               for key, maximum in (("tokens", grant.policy.max_tokens),
                                    ("cost_usd", grant.policy.max_cost_usd),
                                    ("elapsed_ms", grant.policy.max_ms)))
