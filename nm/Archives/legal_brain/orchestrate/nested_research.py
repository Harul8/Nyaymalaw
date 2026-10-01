"""Bounded research and opposition with fresh sources and one journal writer.

The caller decides whether a task is useful. This owner grants no new file,
actor, authority or allowance. Children may read; their exact extracts and
tentative observations are private inputs to independent parent review, never
new case facts, a professional clearance or an advocate-visible answer.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, replace

from nm.Archives.legal_brain.orchestrate.loop import _spend
from nm.Archives.legal_brain.orchestrate.loop_contracts import StepKind, digest
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    DelegatedToolResult,
    DelegationPolicy,
    Effect,
    PreparedToolResult,
    ToolContext,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    ToolRegistry,
    _wire_value,
)
from nm.Archives.legal_brain.reason.opposition_work import (
    PASSES,
    OppositionRequest,
    check_observations,
    controls,
    reusable_work,
    scoped_premises,
    work_record,
)
from nm.Archives.legal_brain.reason.tool_finish_opposition import DEFINITION as OPPOSITION_FINISH
from nm.Archives.legal_brain.retrieve.research_context import ResearchFinding, ResearchSession, ResearchTask
from nm.Archives.legal_brain.retrieve.tool_finish_research import DEFINITION as FINISH
from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_envelope
from nm.Archives.legal_brain.understand.brain_context import (
    ContextPolicy,
    ContextRefused,
    assemble_brief,
    saved_source_references,
)
from nm.Archives.legal_brain.verify.verifier import EvidenceSpan
from nm.shared.budget_contracts import Exhausted, Spend
from nm.shared.model_port import (
    ModelError,
    Prompt,
    Tier,
    ToolMessage,
    estimate_tokens,
    tool_request_text,
)


def _source_reads(envelope):
    """Only a returned source contract can supply law; arbitrary keys cannot."""
    try:
        return findings_from_envelope(envelope)
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolRefused("A child source has no actual captured read locator.") from exc


def _parent_reads(matter, identity):
    record = next((row for row in matter.loop_records if row.identity == identity), None)
    if record is None or not record.events or record.events[-1].kind is not StepKind.TOOL_STARTED:
        raise ToolRefused("Research begins only after its parent journals the reservation.")
    from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_record

    return findings_from_record(record)


def _window(finding):
    return EvidenceSpan("law_" + digest(finding.as_record()), finding, 0, len(finding.span))


class ResearchDispatcher:
    def __init__(
        self,
        *,
        store,
        model,
        principles,
        registry: ToolRegistry,
        cost_ceiling,
        per_call_tokens=1000,
        monotonic=time.monotonic,
    ):
        if type(per_call_tokens) is not int or per_call_tokens <= 0:
            raise ValueError("research output calls are bounded")
        self.store, self.model, self.principles = store, model, principles
        self.registry, self.cost_ceiling = registry, cost_ceiling
        self.per_call_tokens, self.monotonic = per_call_tokens, monotonic

    def tools(self, policy: DelegationPolicy):
        """Useful specialised roles; no scenario tables or implied authority."""
        from nm.Archives.legal_brain.reason.tool_oppose import build_tool as oppose_tool
        from nm.Archives.legal_brain.reason.tool_oppose_early import build_tool as oppose_early_tool
        from nm.Archives.legal_brain.reason.tool_oppose_full import build_tool as oppose_full_tool
        from nm.Archives.legal_brain.reason.tool_oppose_matter import build_tool as oppose_matter_tool
        from nm.Archives.legal_brain.retrieve.tool_research import build_tool as research_tool

        return (
            research_tool(dispatcher=self, policy=policy),
            oppose_tool(dispatcher=self, policy=policy),
            oppose_early_tool(dispatcher=self, policy=policy),
            oppose_full_tool(dispatcher=self, policy=policy),
            oppose_matter_tool(dispatcher=self, policy=policy),
        )

    def run(self, kind, arguments, context: ToolContext):
        started = self.monotonic()
        grant = context.delegation
        if grant is None or kind not in ("research", "oppose", *PASSES):
            raise ToolRefused("A child requires an exact trusted parent reservation.")
        matter = self.store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("The research file or authenticated owner changed.")
        selected = tuple(arguments["issue_ids"])
        if (
            not selected
            or len(selected) != len(set(selected))
            or not set(selected) <= set(context.issue_ids)
            or not arguments["question"].strip()
        ):
            raise ToolRefused(
                "Research has an explicit admitted dispute scope and actual question."
            )
        captured = _parent_reads(matter, context.identity)
        principles = self.principles.load()
        if principles.version != context.identity.principles_version:
            raise ToolRefused("The admitted professional principles changed before research.")
        opposition = (
            OppositionRequest(kind, arguments["question"], selected) if kind in PASSES else None
        )
        control = controls(context, self.model.provider, self.model.resolved_model(Tier.ROUTINE))
        if opposition:
            opposition.admit(matter, context.issue_ids)
            reusable = reusable_work(matter, opposition, captured, control)
            if reusable:
                saved, reference = reusable
                task_result = {
                    "state": "reused_private_work",
                    "research": saved["research"],
                    "opposition_work": saved,
                    "reused_from": reference,
                    "admitted_as_facts": False,
                    "advice_released": False,
                }
                return DelegatedToolResult(
                    ToolEnvelope(
                        kind,
                        "nested-research-v1",
                        ToolKind.SOURCE,
                        ToolOutcome.RESULTS,
                        Availability.AVAILABLE,
                        Assessment.NOT_ASSESSED,
                        {
                            "index": "current source-checked saved opposition work",
                            "locators": [row["locator"] for row in saved["sources"]],
                            "source_version": digest(saved["sources"]),
                            "task_result": task_result,
                        },
                        task_result,
                        "Reused exact private work; independent assessment is still missing.",
                    ),
                    grant.budget.spend_on(Spend(children=1)),
                    0,
                    (),
                )
        reads = tuple(
            row
            for row in self.registry.reading_tools()
            if row.kind in (ToolKind.SOURCE, ToolKind.COMPUTATION)
        )
        if not reads:
            raise ToolRefused("No source/file reader has an admitted read-only child contract.")
        # Preserve the very same boundary closures as the lead. Name aliases,
        # write effects, external actions and recursive children are not inherited.
        child_registry = ToolRegistry(
            reads, before=self.registry._before, after=self.registry._after
        )
        finish = OPPOSITION_FINISH if opposition else FINISH
        definitions = (*child_registry.definitions, finish)
        task = ResearchTask(
            digest(
                {
                    "parent": context.identity.fingerprint,
                    "kind": kind,
                    "question": arguments["question"],
                    "issues": selected,
                }
            ),
            matter.id,
            matter.advocate_id,
            arguments["question"],
            selected,
        )
        brief = assemble_brief(matter, selected, advocate_id=matter.advocate_id)
        session = ResearchSession(
            brief,
            task,
            principles,
            tuple(_window(row) for row in captured),
            definitions,
            captured=captured,
            provider=self.model.provider,
            model=self.model.resolved_model(Tier.ROUTINE),
            policy=ContextPolicy(
                max_tokens=self.model.context_budget(Tier.ROUTINE),
                reserve_tokens=self.per_call_tokens,
            ),
        )
        session.context.append(
            ToolMessage(
                "user",
                json.dumps(
                    {
                        "trusted_task_role": kind,
                        "guidance": (
                            "Read relevant primary sources and their limits. Return exact cited "
                            "extracts "
                            "and explicitly tentative interpretations for independent review."
                            if kind == "research"
                            else "Critically test each supported premise, relief and procedural "
                            "position against "
                            "the strongest source-grounded contrary case and plausible judicial "
                            "questions. "
                            "Actual, anticipated and conditional positions remain distinct. Never"
                            " claim "
                            "that an opponent or judge has acted or will act without recorded "
                            "evidence. "
                            "A persuasive unsupported objection cannot change the file or its "
                            "conclusions."
                        ),
                        "no_permissions_or_case_facts_created": True,
                        "opposition_pass": PASSES.get(kind, "not_applicable"),
                        "full_readiness": "not_assessed",
                        "pass_constraints": (
                            "Early: identify material anticipated defences, not a fixed question "
                            "checklist. "
                            "Full: address the strongest contrary case, supported reply or "
                            "absence of one "
                            "with a proportionate course, and judicial vulnerabilities. "
                            "Cross-matter: "
                            "examine interactions across the actual selected disputes. Cite "
                            "actual supplied "
                            "premise identities and exact retrieved finding identities for each "
                            "candidate. "
                            "No findings is a gap, not absence of opposition; no automatic pass "
                            "completion."
                            if opposition
                            else "Use the admitted task's actual scope."
                        ),
                    },
                    sort_keys=True,
                ),
            )
        )
        prompt = Prompt(task.question, session.context.system, "controlled_" + kind)
        return self._work(
            kind,
            context,
            child_registry,
            definitions,
            captured,
            session,
            prompt,
            started,
            opposition=opposition,
            finish=finish,
            control=control,
        )

    def _work(
        self,
        kind,
        context,
        registry,
        definitions,
        captured,
        session,
        prompt,
        started,
        *,
        opposition=None,
        finish=FINISH,
        control=None,
    ):
        grant = context.delegation
        budget = grant.budget.spend_on(Spend(children=1))
        initial_spend = grant.budget.spend
        steps, trace = 0, []
        provider, model = session.context.provider, session.context.model
        role_message = session.context.messages[-1]
        returned, seen, findings = {}, set(), list(captured)
        reason = "not_assessed"

        def measured():
            nonlocal budget
            budget = replace(
                budget,
                spend=replace(
                    budget.spend,
                    elapsed_ms=initial_spend.elapsed_ms
                    + max(0, int((self.monotonic() - started) * 1000)),
                ),
            )

        def allowed():
            measured()
            delta = budget.spend
            return (
                not context.cancelled()
                and not budget.cancelled_at
                and budget.exhausted() in (Exhausted.NONE, Exhausted.CHILDREN)
                and steps < grant.policy.max_steps
                and delta.elapsed_ms - initial_spend.elapsed_ms < grant.policy.max_ms
                and delta.tokens - initial_spend.tokens < grant.policy.max_tokens
                and delta.cost_usd - initial_spend.cost_usd < grant.policy.max_cost_usd
            )

        try:
            while allowed():
                if (self.model.provider, self.model.resolved_model(Tier.ROUTINE)) != (
                    provider,
                    model,
                ):
                    reason = "provider_identity_changed"
                    break
                messages = session.context.messages
                incoming = estimate_tokens(tool_request_text(prompt, definitions, messages))
                if incoming + self.per_call_tokens > session.context.policy.max_tokens:
                    matter = self.store.load(context.identity.matter_id)
                    if (
                        matter is None
                        or matter.advocate_id != context.identity.advocate_id
                        or matter.version != context.current_version
                    ):
                        raise ContextRefused("stale_context", "The research file moved.")
                    receipts = tuple(
                        row["receipt"]
                        for row in trace
                        if row["kind"] == "tool_returned"
                        and row["receipt"]["kind"] == ToolKind.SOURCE.value
                    )
                    stubs = saved_source_references(receipts)
                    session.compact(
                        assemble_brief(
                            matter, session.task.issue_ids, advocate_id=matter.advocate_id
                        ),
                        reason="actual research request context capacity reached",
                    )
                    session.context.append(role_message)
                    if stubs:
                        session.context.append(stubs)
                    messages = session.context.messages
                    session.context.policy.require_fit(
                        tool_request_text(prompt, definitions, messages)
                    )
                    incoming = estimate_tokens(tool_request_text(prompt, definitions, messages))
                    trace.append(
                        {"kind": "context_compacted", "context": session.context.to_record()}
                    )
                session.context.assert_request(prompt.system, messages, model=model)
                remaining = grant.policy.max_tokens - (budget.spend.tokens - initial_spend.tokens)
                outgoing = min(self.per_call_tokens, remaining - incoming)
                if outgoing <= 0:
                    reason = "budget"
                    break
                reservation = self.cost_ceiling(incoming, outgoing, Tier.ROUTINE)
                if (
                    not math.isfinite(reservation)
                    or reservation < 0
                    or budget.spend.cost_usd - initial_spend.cost_usd + reservation
                    > grant.policy.max_cost_usd
                ):
                    reason = "budget"
                    break
                trace.append(
                    {
                        "kind": "model_started",
                        "prompt": asdict(prompt),
                        "messages": [asdict(row) for row in messages],
                        "provider": provider,
                        "model": model,
                        "reserved_tokens": incoming + outgoing,
                        "reserved_cost_usd": reservation,
                    }
                )
                steps += 1
                try:
                    reply = self.model.tool_call(
                        prompt, definitions, Tier.ROUTINE, messages=messages, max_tokens=outgoing
                    )
                except ModelError as exc:
                    usage = getattr(exc, "usage", None)
                    try:
                        used = (
                            _spend(usage, getattr(exc, "retries", 0))
                            if usage
                            else Spend(tokens=incoming + outgoing, cost_usd=reservation)
                        )
                    except (ValueError, AttributeError):
                        used = Spend(tokens=incoming + outgoing, cost_usd=reservation)
                        usage = None
                    budget = budget.spend_on(used)
                    trace.append(
                        {
                            "kind": "model_failed",
                            "error": type(exc).__name__,
                            "usage_measured": usage is not None,
                        }
                    )
                    reason = "provider_unavailable"
                    break
                try:
                    used = _spend(reply.usage, reply.retries)
                except (ValueError, AttributeError) as exc:
                    budget = budget.spend_on(
                        Spend(tokens=incoming + outgoing, cost_usd=reservation)
                    )
                    raise ToolRefused(
                        "Child usage could not be measured; reservation retained."
                    ) from exc
                budget = budget.spend_on(used)
                trace.append({"kind": "model_returned", "result": asdict(reply)})
                if (
                    (reply.provider, reply.model, reply.tier) != (provider, model, Tier.ROUTINE)
                    or (self.model.provider, self.model.resolved_model(Tier.ROUTINE))
                    != (provider, model)
                    or not reply.completion.usable_for_legal_work
                ):
                    reason = "provider_result_refused"
                    break
                if not allowed() or reply.usage.cost_usd > reservation:
                    reason = "budget_or_cancelled"
                    break
                if not reply.calls or any(row.call_id in seen for row in reply.calls):
                    reason = "no_progress"
                    break
                session.context.append(
                    ToolMessage("assistant", reply.text or "", reply.calls), defer_fit=True
                )
                for call in reply.calls:
                    if not allowed():
                        reason = "budget_or_cancelled"
                        break
                    seen.add(call.call_id)
                    steps += 1
                    trace.append({"kind": "tool_started", "call": asdict(call)})
                    if call.name == finish.name:
                        if call is not reply.calls[-1]:
                            raise ToolRefused("Research cannot finish before pending reads.")
                        from nm.Archives.legal_brain.reason.tool_finish_opposition import (
                            finish as finish_opposition,
                        )
                        from nm.Archives.legal_brain.retrieve.tool_finish_research import (
                            finish as finish_research,
                        )

                        complete = finish_opposition if opposition else finish_research
                        returned = complete(
                            handoff=self._handoff,
                            session=session,
                            arguments=call.arguments,
                            captured=tuple(findings),
                            opposition=opposition,
                            definition=finish,
                        )
                        trace.append(
                            {
                                "kind": "tool_returned",
                                "receipt": json.loads(
                                    ToolEnvelope(
                                        finish.name,
                                        "nested-research-v1",
                                        ToolKind.CONTROL,
                                        ToolOutcome.RESULTS,
                                        Availability.AVAILABLE,
                                        Assessment.NOT_ASSESSED,
                                        {
                                            "operation": finish.name,
                                            "turn_id": context.identity.turn_id,
                                        },
                                        returned,
                                        "An exact source-bound proposal, not independent "
                                        "assessment.",
                                    ).wire()
                                ),
                            }
                        )
                        reason = "exact_extracts_need_independent_review"
                        break
                    receipt = registry.invoke(
                        call, replace(context, delegation=None, issue_ids=session.task.issue_ids)
                    )
                    if (
                        not isinstance(receipt, ToolEnvelope)
                        or isinstance(receipt, PreparedToolResult)
                        or receipt.effect is not Effect.CONTINUE
                        or receipt.kind not in (ToolKind.SOURCE, ToolKind.COMPUTATION)
                    ):
                        raise ToolRefused("A research child may only return an actual read.")
                    trace.append({"kind": "tool_returned", "receipt": json.loads(receipt.wire())})
                    for finding in _source_reads(receipt):
                        if finding not in findings:
                            findings.append(finding)
                    session.context.append(
                        ToolMessage("tool", receipt.wire(), call_id=call.call_id), defer_fit=True
                    )
                if returned or reason != "not_assessed":
                    break
        except (ToolRefused, ContextRefused, ValueError) as exc:
            reason = "child_boundary_refused"
            trace.append({"kind": "refused", "error": type(exc).__name__, "reason": str(exc)})
        measured()
        if reason == "not_assessed":
            reason = "budget_or_cancelled"
        current = self.store.load(context.identity.matter_id)
        if (
            current is None
            or current.version != context.current_version
            or current.advocate_id != context.identity.advocate_id
        ):
            returned, reason = {}, "file_changed"
        if not returned:
            budget = budget.spend_on(Spend(failed_children=1))
        # Private traces contain model prose; the parent journals them sealed.
        # Only exact reads and explicitly unchecked observations enter context.
        task_result = {
            "task_identity": session.identity,
            "state": reason,
            "research": returned,
            "admitted_as_facts": False,
            "advice_released": False,
        }
        if opposition and returned:
            task_result["opposition_work"] = work_record(
                current, opposition, returned, tuple(findings), control
            )
        data = (
            {**task_result, "findings": [row.as_record() for row in findings]} if findings else {}
        )
        locators = list(dict.fromkeys(row.locator for row in findings))
        return DelegatedToolResult(
            ToolEnvelope(
                kind,
                "nested-research-v1",
                ToolKind.SOURCE,
                ToolOutcome.RESULTS if data else ToolOutcome.NO_RESULTS,
                Availability.AVAILABLE if returned else Availability.PARTIAL,
                Assessment.NOT_ASSESSED,
                {
                    "index": "admitted child source readers",
                    "locators": locators,
                    "source_version": digest([row.as_record() for row in findings]),
                    "task_result": task_result,
                },
                data,
                "Exact reads and tentative observations require independent semantic review. "
                + reason,
            ),
            budget,
            steps,
            tuple(json.loads(json.dumps(trace, default=_wire_value, allow_nan=False))),
        )

    @staticmethod
    def _handoff(session, arguments, captured, *, opposition=None):
        windows, proposed = [], []
        for row in arguments["findings"]:
            found = [
                item
                for item in captured
                if item.locator == row["locator"]
                and row["quote"].strip()
                and row["quote"] in item.span
            ]
            if len(found) != 1:
                raise ToolRefused("Research must identify one actual exact source extract.")
            source = _window(found[0])
            if source not in windows:
                windows.append(source)
            proposed.append(ResearchFinding(row["id"], source.id, row["quote"]))
        checked = session.validate_findings(
            tuple(proposed), additional_sources=tuple(windows), captured=captured
        )
        known_facts = {
            row.source_id
            for row in session.context.brief.sources
            if row.kind != "exact_captured_legal_window"
        }
        finding_ids = {row.id for row in checked.findings}
        observations = arguments["observations"]
        if opposition:
            check_observations(
                opposition,
                observations,
                finding_ids=finding_ids,
                premise_ids=known_facts,
                premise_by_issue=scoped_premises(
                    json.loads(session.context.brief.source_record_json)
                ),
            )
        for row in observations:
            if not opposition and (
                row["issue_id"] not in session.task.issue_ids
                or not row["text"].strip()
                or not row["finding_ids"]
                or not set(row["finding_ids"]) <= finding_ids
                or not set(row["premise_ids"]) <= known_facts
            ):
                raise ToolRefused("A tentative observation needs its actual scoped facts and law.")
        return {
            "state": checked.state,
            "task_identity": checked.task_identity,
            "findings": [asdict(row) for row in checked.findings],
            "source_windows": json.loads(checked.cited_windows_json),
            "source_set_identity": digest(json.loads(checked.cited_windows_json)),
            "independent_uncertainties": json.loads(checked.uncertainties_json),
            "observations": [
                {**row, "semantic_assessment": "not_assessed"} for row in observations
            ],
        }
