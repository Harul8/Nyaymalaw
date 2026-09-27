"""An actual controlled caller of the loop, not a client cutover switch.

Admission is a trusted bounded evaluation scope, kept apart from prompt text.
Ordinary matter processing still uses TurnEngine until its absolute bar is met.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from nm.legal_brain.common.principles_port import PrinciplesPort
from nm.legal_brain.evaluate.brain_evaluation import CheckFeedback, EvaluationService
from nm.legal_brain.orchestrate.loop import LoopRunner
from nm.legal_brain.orchestrate.loop_contracts import (
    LoopIdentity,
    LoopLimits,
    LoopMode,
    LoopOutcome,
    digest,
)
from nm.legal_brain.orchestrate.loop_log_port import LoopLogPort
from nm.legal_brain.orchestrate.tools import After, Before, ToolRegistry
from nm.legal_brain.understand.brain_context import (
    ContextPolicy,
    ContextSession,
    assemble_brief,
    instruction_history_enabled,
    require_recorded_source,
)
from nm.legal_brain.verify.brain_release import ReviewService
from nm.shared.clock_contracts import today as forum_today
from nm.shared.model_port import ModelPort, Prompt, Tier, ToolMessage
from nm.shared.store_port import StorePort


@dataclass(frozen=True)
class EvaluationScope:
    approval_reference: str
    advocate_id: str
    matter_ids: frozenset[str]
    mode: LoopMode
    """A trusted allowlist; never accepted from a model or client HTTP body."""

    def __post_init__(self):
        if not self.approval_reference.strip() or not self.advocate_id.strip():
            raise ValueError("controlled work needs its attributed approval")
        if not self.matter_ids or any(not ident.strip() for ident in self.matter_ids):
            raise ValueError("controlled work has a finite explicit matter population")
        if not isinstance(self.mode, LoopMode):
            raise ValueError("normal client matters are not an evaluation mode")


RegistryFactory = Callable[[Before, After], ToolRegistry]


class ControlledBrain:
    def __init__(self, *, store: StorePort, model: ModelPort, principles: PrinciplesPort,
                 log: LoopLogPort, registry: ToolRegistry, scope: EvaluationScope,
                 cost_ceiling: Callable[[int, int, Tier], float],
                 session_current: Callable[[], bool], reviewer: ReviewService | None = None,
                 assessment=None, finalizer=None, publication=None, checklist_review=None,
                 interaction_review=None, working_preferences=None,
                 limitation_selection_review=None, interest_selection_review=None,
                 working_review=None, working_scope=None, working_explanations=None,
                 early_review=None, input_continuations=None, fee_selection_review=None,
                 clock=None, monotonic=time.monotonic, today=forum_today):
        if not callable(monotonic) or not callable(today) or (
                clock is not None and not callable(clock)):
            raise ValueError("Controlled work requires actual callable clock owners")
        self.store, self.model, self.principles = store, model, principles
        self.log, self.registry, self.scope = log, registry, scope
        self._session_current = session_current
        self._today = today
        self.reviewer = reviewer
        self.assessment = assessment
        self.finalizer = finalizer
        self.publication = publication
        self.checklist_review = checklist_review
        self.interaction_review = interaction_review
        self.working_preferences = working_preferences
        self.limitation_selection_review = limitation_selection_review
        self.interest_selection_review = interest_selection_review
        self.working_review = working_review
        self.working_scope = working_scope
        self.working_explanations = working_explanations
        self.early_review = early_review
        self.input_continuations = input_continuations
        self.fee_selection_review = fee_selection_review
        self._runner = LoopRunner(model=model, tools=registry, log=log,
                                  cost_ceiling=cost_ceiling, current_matter=store.load,
                                  clock=clock, monotonic=monotonic)

    def run(self, *, matter_id: str, turn_id: str, message: str, limits: LoopLimits,
            selected_issue_ids: tuple[str, ...] = (),
            cancelled: Callable[[], bool] = lambda: False,
            feedback: CheckFeedback | None = None,
            continuation=None,
            observe_budget=None) -> LoopOutcome:
        self.require_scope(matter_id)
        matter = self.store.load(matter_id)
        if matter is None or matter.advocate_id != self.scope.advocate_id:
            raise PermissionError("the controlled file is unavailable")
        if not message.strip() or not turn_id.strip():
            raise ValueError("controlled work has an original instruction and turn identity")
        if continuation is not None:
            from nm.legal_brain.orchestrate.checked_input_continuation import (
                CheckedInputContinuation,
            )
            from nm.legal_brain.orchestrate.loop import _budget_from
            from nm.legal_brain.orchestrate.loop_contracts import StopReason

            if feedback is not None or type(continuation) is not CheckedInputContinuation \
                    or self.input_continuations is None or continuation.matter_id != matter_id:
                raise ValueError("A continuation needs its sole typed current review owner")
            parents = [row for row in matter.loop_records
                       if row.identity.turn_id == continuation.parent_turn_id]
            if len(parents) != 1 or not parents[0].terminal:
                raise ValueError("A continuation lacks its exact completed parent")
            saved = parents[0]
            parent = LoopOutcome(StopReason(saved.events[-1].payload["reason"]), saved,
                _budget_from(saved.events[-1].payload["budget"]),
                saved.events[-1].payload.get("proposal", {}))
            from dataclasses import replace

            limits = replace(limits, budget=self.input_continuations.validate(
                continuation, parent, original_message=message,
                selected_issue_ids=selected_issue_ids, budget=limits.budget))
        rows = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
        if len(rows) > 1:
            raise ValueError("the controlled turn has duplicate identities")
        display_before_version = rows[0].identity.matter_version if rows else matter.version
        include_instructions = (not rows or instruction_history_enabled(
            rows[0].events[0].payload["context"]["brief"]))
        # Load at each new turn boundary. An existing log carries its original
        # prefix; a changed guide is a new context, not an inherited approval.
        principles = self.principles.load()
        policy = ContextPolicy(max_tokens=self.model.context_budget(Tier.ROUTINE),
                               reserve_tokens=limits.per_call_tokens)
        source_current = (self.checklist_review.source_current
                          if self.checklist_review is not None else None)
        brief = assemble_brief(matter, selected_issue_ids, policy,
                               advocate_id=self.scope.advocate_id,
                               as_of=self._today(),
                               source_current=source_current,
                               display_before_version=display_before_version,
                               include_admitted_instructions=include_instructions,
                               private_instruction_mode=self.scope.mode)
        session = ContextSession(principles, self.registry.definitions, brief,
                                 provider=self.model.provider,
                                 model=self.model.resolved_model(Tier.ROUTINE), policy=policy,
                                 tool_offer=self.registry.offer_state(),
                                 source_current=source_current,
                                 today=self._today,
                                 working_preferences=self.working_preferences()
                                     if self.working_preferences is not None else None)
        if feedback is not None:
            if not isinstance(feedback, CheckFeedback) or feedback.matter_id != matter_id:
                raise ValueError("repair feedback belongs to this captured matter")
            parents = [row for row in matter.loop_records
                       if row.identity.turn_id == feedback.parent_turn_id]
            if (len(parents) != 1 or not parents[0].terminal
                    or parents[0].identity.advocate_id != self.scope.advocate_id
                    or parents[0].events[-1].fingerprint != feedback.parent_fingerprint):
                raise ValueError("repair feedback lacks its saved parent")
            session.append(ToolMessage("user", feedback.text))
        if continuation is not None:
            session.append(ToolMessage("user", continuation.text))
        prompt = Prompt(message, session.system, "controlled_legal_brain")
        identity = LoopIdentity(matter_id, self.scope.advocate_id, turn_id, digest({
            "user": prompt.user, "system": prompt.system, "operation": prompt.operation}),
            principles.version, self.registry.version, matter.version, self.scope.mode)
        # The journal advances the matter's transaction version, not the
        # substantive checked file. Exact retries keep their original identity.
        if rows:
            previous = rows[0].identity
            if (previous.offer_hash != identity.offer_hash
                    or previous.principles_version != identity.principles_version
                    or previous.tools_version != identity.tools_version
                    or previous.mode != identity.mode):
                raise ValueError("a retry must carry the original instruction and versions")
            require_recorded_source(rows[0], matter, as_of=self._today())
            identity = previous
        if observe_budget is not None:
            from dataclasses import replace

            from nm.shared.budget_contracts import Budget

            measured = observe_budget(limits.budget)
            if (not isinstance(measured, Budget)
                    or measured.spend.elapsed_ms < limits.budget.spend.elapsed_ms
                    or replace(measured, spend=replace(measured.spend,
                        elapsed_ms=limits.budget.spend.elapsed_ms)) != limits.budget):
                raise ValueError(
                    "A context-time observer cannot change the resource grant or spend")
            limits = replace(limits, budget=measured)
        return self._runner.run(identity, prompt, limits, session=session,
                                cancelled=lambda: cancelled() or not self._session_current(),
                                feedback_identity=(feedback.identity if feedback else
                                                   continuation.identity if continuation else ""),
                                scope_identity=digest({"requested_issue_ids":
                                                      sorted(set(selected_issue_ids))}))

    def evaluate(self, **arguments):
        if self.reviewer is None or self.assessment is None:
            raise ValueError("Independent review and final assessment must both be configured")
        return EvaluationService(self, self.assessment).run(**arguments)

    def review(self, outcome: LoopOutcome, *, cancelled=lambda: False,
               max_model_calls: int | None = None, budget=None):
        """Independently review this scoped proposal; never imply client publication."""
        self.require_scope(outcome.record.identity.matter_id)
        if outcome.record.identity.advocate_id != self.scope.advocate_id:
            raise PermissionError("the proposal belongs to another advocate")
        if self.reviewer is None:
            raise ValueError("independent review is not configured; this is not a PASS")
        return self.reviewer.review(outcome, cancelled=cancelled,
                                    max_model_calls=max_model_calls, budget=budget)

    def require_scope(self, matter_id: str):
        if matter_id not in self.scope.matter_ids or not self._session_current():
            raise PermissionError("this matter or session is outside the controlled approval")
