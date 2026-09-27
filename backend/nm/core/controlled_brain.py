"""An actual controlled caller of the loop, not a client cutover switch.

Admission is a trusted bounded evaluation scope, kept apart from prompt text.
Ordinary matter processing still uses TurnEngine until its absolute bar is met.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nm.core.brain_context import (
    ContextPolicy,
    ContextSession,
    assemble_brief,
    instruction_history_enabled,
    require_recorded_source,
)
from nm.core.brain_evaluation import CheckFeedback, EvaluationService
from nm.core.brain_release import ReviewService
from nm.core.loop import LoopRunner
from nm.core.tools import After, Before, ToolRegistry
from nm.domain.loop import LoopIdentity, LoopLimits, LoopMode, LoopOutcome, digest
from nm.ports.loop_log import LoopLogPort
from nm.ports.model import ModelPort, Prompt, Tier, ToolMessage
from nm.ports.principles import PrinciplesPort
from nm.ports.store import StorePort


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
                 interaction_review=None):
        self.store, self.model, self.principles = store, model, principles
        self.log, self.registry, self.scope = log, registry, scope
        self._session_current = session_current
        self.reviewer = reviewer
        self.assessment = assessment
        self.finalizer = finalizer
        self.publication = publication
        self.checklist_review = checklist_review
        self.interaction_review = interaction_review
        self._runner = LoopRunner(model=model, tools=registry, log=log,
                                  cost_ceiling=cost_ceiling, current_matter=store.load)

    def run(self, *, matter_id: str, turn_id: str, message: str, limits: LoopLimits,
            selected_issue_ids: tuple[str, ...] = (),
            cancelled: Callable[[], bool] = lambda: False,
            feedback: CheckFeedback | None = None,
            observe_budget=None) -> LoopOutcome:
        self.require_scope(matter_id)
        matter = self.store.load(matter_id)
        if matter is None or matter.advocate_id != self.scope.advocate_id:
            raise PermissionError("the controlled file is unavailable")
        if not message.strip() or not turn_id.strip():
            raise ValueError("controlled work has an original instruction and turn identity")
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
                               source_current=source_current,
                               display_before_version=display_before_version,
                               include_admitted_instructions=include_instructions,
                               private_instruction_mode=self.scope.mode)
        session = ContextSession(principles, self.registry.definitions, brief,
                                 provider=self.model.provider,
                                 model=self.model.resolved_model(Tier.ROUTINE), policy=policy,
                                 tool_offer=self.registry.offer_state(),
                                 source_current=source_current)
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
            require_recorded_source(rows[0], matter)
            identity = previous
        if observe_budget is not None:
            from dataclasses import replace

            from nm.domain.budget import Budget

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
                                feedback_identity=feedback.identity if feedback else "",
                                scope_identity=digest({"requested_issue_ids":
                                                      sorted(set(selected_issue_ids))}))

    def evaluate(self, **arguments):
        if self.reviewer is None or self.assessment is None:
            raise ValueError("Independent review and final assessment must both be configured")
        return EvaluationService(self, self.assessment).run(**arguments)

    def review(self, outcome: LoopOutcome, *, cancelled=lambda: False,
               max_model_calls: int | None = None):
        """Independently review this scoped proposal; never imply client publication."""
        self.require_scope(outcome.record.identity.matter_id)
        if outcome.record.identity.advocate_id != self.scope.advocate_id:
            raise PermissionError("the proposal belongs to another advocate")
        if self.reviewer is None:
            raise ValueError("independent review is not configured; this is not a PASS")
        return self.reviewer.review(outcome, cancelled=cancelled, max_model_calls=max_model_calls)

    def require_scope(self, matter_id: str):
        if matter_id not in self.scope.matter_ids or not self._session_current():
            raise PermissionError("this matter or session is outside the controlled approval")
