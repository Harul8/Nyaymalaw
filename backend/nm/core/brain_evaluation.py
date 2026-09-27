"""Bounded private repair over real saved proposals, never a client cutover.

Feedback is harness data, not a new advocate instruction. Repairs retain the
original words, share all resource limits and re-read the sources they rely on.
Missing professional/quality subjects do not cause futile model retries.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nm.core.brain_assessment import AssessmentService, BrainAssessment
from nm.core.brain_release import ReviewRefused
from nm.core.output_checks import CheckReceipt
from nm.domain.budget import Budget, Exhausted, Spend
from nm.domain.gates import Response, Scope
from nm.domain.loop import LoopLimits, LoopOutcome, StepKind, StopReason, digest

if TYPE_CHECKING:
    from nm.core.brain_publication import PrivatePublication
    from nm.core.controlled_brain import ControlledBrain


@dataclass(frozen=True)
class CheckFeedback:
    matter_id: str
    parent_turn_id: str
    parent_fingerprint: str
    failures: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if (not self.matter_id.strip() or not self.parent_turn_id.strip()
                or len(self.parent_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.parent_fingerprint)
                or not self.failures or any(not key.strip() or not why.strip()
                                           for key, why in self.failures)):
            raise ValueError("Repair feedback needs an exact saved parent and actual failures")

    @property
    def text(self):
        return json.dumps({"material_kind": "harness_check_feedback",
            "trust": "diagnostic_data_not_case_facts_or_authority",
            "data": {"parent_turn": self.parent_turn_id,
                "parent_fingerprint": self.parent_fingerprint,
                "failures": self.failures,
                "instruction": "Reconsider the failed proposal within the original request. "
                    "Read sources again where needed. Do not invent missing evidence, waive "
                    "a failed check, or record this diagnostic as an advocate assertion."}},
            sort_keys=True, ensure_ascii=False, allow_nan=False)

    @property
    def identity(self):
        return digest({"matter": self.matter_id, "feedback": self.text})


@dataclass(frozen=True)
class EvaluationResult:
    attempts: tuple[LoopOutcome, ...]
    assessments: tuple[BrainAssessment, ...]
    budget: Budget
    stop: str
    limitations: tuple[str, ...] = ()
    publications: tuple[PrivatePublication, ...] = ()
    checklist_reviews: tuple = ()
    interaction_reviews: tuple = ()

    @property
    def client_ready(self):
        return False


# These checks own the proposed answer's words, quoted sources or derived
# instruction. All other current checks own external/current file state: a
# model cannot repair corpus coverage, authorisation, a race, a lost prior
# derivation or a correction merely by omitting it from its next answer.
# This is an ownership classification, not a second gate response matrix.
ANSWER_REPAIR_OWNERS = frozenset({
    "G-GROUND", "G-QUOTE", "G-ATTRIB", "G-DATE", "G-INFORCE", "G-BINDING",
    "G-CONSISTENT",
})


def answer_repairable(receipt: CheckReceipt) -> bool:
    """Only an actual failed, scoped answer check invites model repair.

    DISCLOSE alone does not decide ownership. The present disclosure checks in
    this population all observe owner/file state; an eventual answer-disclosure
    check needs its own explicit repair owner before it can spend a retry.
    """
    return (receipt.assessed is False and receipt.gate_id in ANSWER_REPAIR_OWNERS
            and receipt.response in {Response.BLOCK, Response.WITHHOLD}
            and receipt.scope in {Scope.TURN, Scope.STEP, Scope.NEED})


def reservation(receipt: CheckReceipt) -> str:
    return (f"{receipt.gate_id} ({receipt.response.value}/{receipt.scope.value}): "
            + receipt.reason)


def completed_child_within_grant(budget: Budget) -> bool:
    """An admitted last child may finish; its equality forbids another child.

    Other exhausted/overflow/cancelled states retain their existing stop rules.
    This permission never admits a new model dispatch.
    """
    return (budget.exhausted() is Exhausted.CHILDREN
            and budget.spend.children == budget.max_children)


def dispatch_steps(record) -> int:
    """Count actual parent/child dispatches from the same sealed work record.

    A child count without its complete attempted-dispatch population cannot
    buy a new repair allowance. Failed attempts and the finish tool still count.
    """
    steps = 0
    for event in record.events:
        steps += event.kind in (StepKind.MODEL_STARTED, StepKind.TOOL_STARTED)
        payload = event.payload
        if "child_steps" not in payload and "child_transcript" not in payload:
            continue
        transcript = payload.get("child_transcript")
        count = payload.get("child_steps")
        if (event.kind is not StepKind.TOOL_RETURNED or type(count) is not int or count < 0
                or not isinstance(transcript, (list, tuple))
                or any(not isinstance(row, dict) or not isinstance(row.get("kind"), str)
                       for row in transcript)
                or payload.get("child_released") is not False):
            raise ReviewRefused("The saved child lacks its exact attempted dispatch population")
        actual = sum(row["kind"] in {"model_started", "tool_started"} for row in transcript)
        if actual != count:
            raise ReviewRefused("The saved child dispatch count differs from its actual transcript")
        steps += actual
    return steps


class EvaluationService:
    def __init__(self, brain: ControlledBrain, assessment: AssessmentService,
                 *, monotonic=time.monotonic):
        self.brain, self.assessment = brain, assessment
        self.monotonic = monotonic

    def run(self, *, matter_id: str, turn_id: str, message: str, limits: LoopLimits,
            selected_issue_ids: tuple[str, ...] = (), max_repairs: int = 2,
            cancelled=lambda: False) -> EvaluationResult:
        if type(max_repairs) is not int or not 0 <= max_repairs <= 10:
            raise ValueError("The private evaluation needs a bounded repair count")
        attempts, assessments, seen, reservations, publications = [], [], set(), [], []
        checklist_reviews = []
        interaction_reviews = []
        budget, steps, feedback = limits.budget, 0, None
        started, initial_ms = self.monotonic(), budget.spend.elapsed_ms

        def finish(*arguments):
            return EvaluationResult(*arguments, publications=tuple(publications),
                                    checklist_reviews=tuple(checklist_reviews),
                                    interaction_reviews=tuple(interaction_reviews))

        def measured(current):
            # Include context assembly and final checks, not only provider calls.
            elapsed = initial_ms + max(0, int((self.monotonic() - started) * 1000))
            return replace(current, spend=replace(current.spend,
                elapsed_ms=max(current.spend.elapsed_ms, elapsed)))

        def deadline_hit():
            return initial_ms + max(0, int((self.monotonic() - started) * 1000)) >= budget.max_ms

        for iteration in range(max_repairs + 1):
            budget = measured(budget)
            if budget.spent_out or steps >= limits.max_steps or cancelled():
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "cancelled" if cancelled() else "budget",
                                        tuple(reservations))
            ident = turn_id if iteration == 0 else f"{turn_id}:repair:{iteration}"
            attempt = self.brain.run(matter_id=matter_id, turn_id=ident, message=message,
                limits=replace(limits, budget=budget, max_steps=limits.max_steps - steps),
                selected_issue_ids=selected_issue_ids, cancelled=cancelled, feedback=feedback,
                observe_budget=measured)
            attempts.append(attempt)
            budget = measured(attempt.budget)
            try:
                steps += dispatch_steps(attempt.record)
            except ReviewRefused as exc:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "review_refused", tuple(reservations) + (str(exc),))
            if (self.brain.checklist_review is not None
                    and attempt.reason in (StopReason.PROPOSAL, StopReason.QUESTION,
                                           StopReason.CONVERSATION)):
                try:
                    classified = self.brain.checklist_review.review(attempt,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    checklist_reviews.append(classified)
                    if classified.review is not None:
                        budget = measured(classified.review.budget)
                        steps += classified.review.model_steps
                    reservations.extend("Checklist relevance remains unassessed: "
                        + row.requirement_key for row in classified.unresolved)
                except ReviewRefused as exc:
                    budget = measured(getattr(exc, "budget", budget))
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "review_refused", tuple(reservations) + (str(exc),))
            if attempt.reason is not StopReason.PROPOSAL:
                if (attempt.reason in (StopReason.QUESTION, StopReason.CONVERSATION)
                        and self.brain.interaction_review is not None):
                    try:
                        interaction = self.brain.interaction_review.review(attempt,
                            budget=budget, cancelled=lambda: cancelled() or deadline_hit(),
                            max_model_calls=max(0, limits.max_steps - steps))
                        interaction_reviews.append(interaction)
                        budget = measured(interaction.budget)
                        steps += interaction.model_steps
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "interaction_checks_complete_private_candidate" if interaction.checked
                                else "interaction_checks_missing",
                            tuple(reservations))
                    except ReviewRefused as exc:
                        budget = measured(getattr(exc, "budget", budget))
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "review_refused", tuple(reservations) + (str(exc),))
                return finish(tuple(attempts), tuple(assessments), budget,
                                        attempt.reason.value, tuple(reservations))
            if budget.spent_out:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "budget", tuple(reservations))
            try:
                review = self.brain.review(attempt,
                                          cancelled=lambda: cancelled() or deadline_hit(),
                                          max_model_calls=limits.max_steps - steps)
                budget = measured(review.budget)
                steps += review.model_steps
                if self.brain.finalizer is not None:
                    final = self.brain.finalizer.prepare(attempt, review,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    budget = measured(final.budget)
                    steps += final.model_steps
                if cancelled():
                    return finish(tuple(attempts), tuple(assessments),
                        budget.cancel(datetime.now(timezone.utc).isoformat()), "cancelled",
                        tuple(reservations))
                if budget.spent_out and not completed_child_within_grant(budget):
                    return finish(tuple(attempts), tuple(assessments), budget,
                                            "budget", tuple(reservations))
                current = self.brain.store.load(matter_id)
                result = self.assessment.assess(attempt, review, expected_version=current.version)
                if self.brain.publication is not None:
                    publications.append(self.brain.publication.record(
                        attempt, review, result, original_message=message))
                budget = measured(budget)
            except ReviewRefused as exc:
                # A broken captured contract is not a paid-repair invitation.
                # Its parent/child journals and external ledger retain all work.
                budget = measured(getattr(exc, "budget", budget))
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "review_refused", tuple(reservations) + (str(exc),))
            assessments.append(result)
            if budget.spent_out and not completed_child_within_grant(budget):
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "budget", tuple(reservations))
            owner_states = tuple(row for row in result.failed if not answer_repairable(row))
            reservations.extend(reservation(row) for row in owner_states
                                if reservation(row) not in reservations)
            if any(row.response in {Response.BLOCK, Response.WITHHOLD} for row in owner_states):
                # Human/authority/file-state failures stop merits repair. A
                # rewritten answer cannot make their original receipts pass.
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "owner_state_blocked", tuple(reservations))
            failures = []
            for record in review.records:
                for name in ("textual_support", "applicability", "inference",
                             "opposition_resolved"):
                    judgment = getattr(record, name)
                    if judgment.assessed is False:
                        failures.append((f"{record.package_id}:{name}", judgment.reason))
            failures.extend((row.gate_id, row.reason) for row in result.failed
                            if answer_repairable(row))
            if not failures:
                gaps = tuple(dict.fromkeys((*reservations,
                    *(row.reason for row in result.unassessed), *result.missing_receipts)))
                stop = ("required_reservations" if reservations else
                    "checks_complete_private_candidate" if result.checks_complete else
                    "required_checks_missing" if gaps else "independent_review_incomplete")
                return finish(tuple(attempts), tuple(assessments), budget, stop, gaps)
            signature = digest({"proposal": attempt.proposal, "failures": failures})
            if signature in seen:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "no_progress", tuple(reservations))
            seen.add(signature)
            if iteration == max_repairs:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "repair_limit", tuple(reservations))
            # Discarded work is still paid work, and no repair gets a fresh budget.
            budget = budget.spend_on(Spend(discarded_results=1))
            feedback = CheckFeedback(matter_id, attempt.record.identity.turn_id,
                                     attempt.record.events[-1].fingerprint, tuple(failures))
        raise AssertionError("A bounded evaluation did not terminate")
