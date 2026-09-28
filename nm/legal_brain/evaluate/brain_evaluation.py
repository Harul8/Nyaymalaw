"""Bounded private repair over real saved proposals, never a client cutover.

Feedback is harness data, not a new advocate instruction. Repairs retain the
original words, share all resource limits and re-read the sources they rely on.
Missing professional/quality subjects do not cause futile model retries.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nm.legal_brain.orchestrate.loop_contracts import (
    LoopLimits,
    LoopOutcome,
    StepKind,
    StopReason,
    digest,
)
from nm.legal_brain.verify.brain_assessment import (
    AssessmentService,
    BrainAssessment,
    saved_package_reviews,
)
from nm.legal_brain.verify.brain_release import (
    ProposalBindingRefused,
    ReviewRefused,
    shared_review_budget,
)
from nm.legal_brain.verify.output_checks import CheckReceipt
from nm.shared.budget_contracts import Budget, Exhausted, Spend
from nm.shared.gates_contracts import Response, Scope

if TYPE_CHECKING:
    from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain
    from nm.legal_brain.verify.brain_publication import PrivatePublication


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
    limitation_selection_reviews: tuple = ()
    interest_selection_reviews: tuple = ()
    fee_selection_reviews: tuple = ()
    working_reviews: tuple = ()
    working_scope_reviews: tuple = ()
    working_completeness: tuple = ()
    working_explanations: tuple = ()

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
        limitation_selection_reviews = []
        interest_selection_reviews = []
        fee_selection_reviews = []
        working_reviews, working_scope_reviews, working_completeness = [], [], []
        working_explanations = []
        budget, steps, feedback, continuation = limits.budget, 0, None, None
        continued_inputs = set()
        started, initial_ms = self.monotonic(), budget.spend.elapsed_ms

        def finish(*arguments):
            return EvaluationResult(*arguments, publications=tuple(publications),
                                    checklist_reviews=tuple(checklist_reviews),
                                    interaction_reviews=tuple(interaction_reviews),
                                    limitation_selection_reviews=tuple(limitation_selection_reviews),
                                    interest_selection_reviews=tuple(interest_selection_reviews),
                                    fee_selection_reviews=tuple(fee_selection_reviews),
                                    working_reviews=tuple(working_reviews),
                                    working_scope_reviews=tuple(working_scope_reviews),
                                    working_completeness=tuple(working_completeness),
                                    working_explanations=tuple(working_explanations))

        def measured(current):
            # Include context assembly and final checks, not only provider calls.
            elapsed = initial_ms + max(0, int((self.monotonic() - started) * 1000))
            return replace(current, spend=replace(current.spend,
                elapsed_ms=max(current.spend.elapsed_ms, elapsed)))

        def deadline_hit():
            # Saved children can carry more elapsed time than the parent STOP
            # on an idempotent retry. Compare that sealed floor with this
            # invocation's clock; never add the two overlapping intervals.
            elapsed = initial_ms + max(0, int((self.monotonic() - started) * 1000))
            return max(budget.spend.elapsed_ms, elapsed) >= budget.max_ms

        def check_work(attempt):
            """Scope is last: it spends the real allowance after all wording/final checks.

            This cannot promote a private explanation to a released answer. A
            useful question can leave work outstanding without claiming completion.
            """
            nonlocal budget, steps
            owner = getattr(self.brain, "working_review", None)
            scope = getattr(self.brain, "working_scope", None)
            if owner is None or scope is None:
                return None
            proof = scope.review(attempt, budget=budget,
                cancelled=lambda: cancelled() or deadline_hit(),
                max_model_calls=max(0, limits.max_steps - steps))
            working_scope_reviews.append(proof)
            budget = measured(proof.budget)
            steps += proof.model_steps
            complete = owner.completeness(attempt, scope_service=scope)
            working_completeness.append(complete)
            explanations = getattr(self.brain, "working_explanations", None)
            if explanations is not None:
                checked = explanations.review(attempt, budget=budget,
                    cancelled=lambda: cancelled() or deadline_hit(),
                    max_model_calls=max(0, limits.max_steps - steps))
                working_explanations.append(checked)
                budget = measured(checked.budget)
                steps += checked.model_steps
            return complete

        for iteration in range(max_repairs + 1):
            budget = measured(budget)
            if budget.spent_out or steps >= limits.max_steps or cancelled():
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "cancelled" if cancelled() else "budget",
                                        tuple(reservations))
            ident = turn_id if iteration == 0 else f"{turn_id}:repair:{iteration}"
            entering_budget = budget
            attempt = self.brain.run(matter_id=matter_id, turn_id=ident, message=message,
                limits=replace(limits, budget=budget, max_steps=limits.max_steps - steps),
                selected_issue_ids=selected_issue_ids, cancelled=cancelled, feedback=feedback,
                continuation=continuation,
                observe_budget=measured)
            attempts.append(attempt)
            budget = measured(attempt.budget)
            try:
                steps += dispatch_steps(attempt.record)
                # An exact retry returns the immutable parent. Its STOP budget
                # cannot contain independent children already sealed after it.
                # Reconstruct their actual shared ledger before any owner can
                # admit another review; never ask the reviewer to accept a
                # caller-restored parent-only spending proposal.
                recorded = shared_review_budget(attempt, (),
                    self.brain.store.load(matter_id), self.brain.log, None)
                spend = Spend(**{field.name: max(
                    getattr(recorded.spend, field.name),
                    getattr(entering_budget.spend, field.name),
                    getattr(budget.spend, field.name)) for field in fields(Spend)})
                budget = measured(replace(recorded, spend=spend))
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
            continuation_groups = []
            continuation_keys = []

            def pending_inputs(kind, selected, *, groups=continuation_groups,
                               keys=continuation_keys):
                if selected.review is None:
                    return
                ids = []
                for binding in selected.bindings:
                    key = (kind, digest(binding.candidate))
                    if binding.package in selected.review.result.released \
                            and key not in continued_inputs:
                        ids.append(binding.package.id)
                        keys.append(key)
                if ids:
                    groups.append((kind, tuple(ids)))

            selection_owner = getattr(self.brain, "limitation_selection_review", None)
            if selection_owner is not None and attempt.reason in (
                    StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION):
                try:
                    selected = selection_owner.review(attempt, budget=budget,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    limitation_selection_reviews.append(selected)
                    if selected.review is not None:
                        budget = measured(selected.review.budget)
                        steps += selected.review.model_steps
                    reservations.extend("Calculation selection remains unassessed: " + str(row)
                                        for row in selected.unresolved)
                    pending_inputs("limitation", selected)
                except ReviewRefused as exc:
                    budget = measured(getattr(exc, "budget", budget))
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "review_refused", tuple(reservations) + (str(exc),))
            interest_owner = getattr(self.brain, "interest_selection_review", None)
            if interest_owner is not None and attempt.reason in (
                    StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION):
                try:
                    selected = interest_owner.review(attempt, budget=budget,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    interest_selection_reviews.append(selected)
                    if selected.review is not None:
                        budget = measured(selected.review.budget)
                        steps += selected.review.model_steps
                    reservations.extend("Interest selection remains unassessed: " + str(row)
                                        for row in selected.unresolved)
                    pending_inputs("interest", selected)
                except ReviewRefused as exc:
                    budget = measured(getattr(exc, "budget", budget))
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "review_refused", tuple(reservations) + (str(exc),))
            fee_owner = getattr(self.brain, "fee_selection_review", None)
            if fee_owner is not None and attempt.reason in (
                    StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION):
                try:
                    selected = fee_owner.review(attempt, budget=budget,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    fee_selection_reviews.append(selected)
                    if selected.review is not None:
                        budget = measured(selected.review.budget)
                        steps += selected.review.model_steps
                    reservations.extend("Fee selection remains unassessed: " + str(row)
                                        for row in selected.unresolved)
                    pending_inputs("fee", selected)
                except ReviewRefused as exc:
                    budget = measured(getattr(exc, "budget", budget))
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "review_refused", tuple(reservations) + (str(exc),))
            continuation_owner = getattr(self.brain, "input_continuations", None)
            if continuation_groups and continuation_owner is not None:
                if cancelled() or budget.spent_out or steps >= limits.max_steps:
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "cancelled" if cancelled() else "budget", tuple(reservations))
                if iteration == max_repairs:
                    return finish(tuple(attempts), tuple(assessments), budget,
                                  "continuation_limit", tuple(reservations))
                try:
                    continuation = continuation_owner.prepare(attempt,
                        groups=tuple(continuation_groups), original_message=message,
                        selected_issue_ids=selected_issue_ids, budget=budget)
                except ReviewRefused as exc:
                    return finish(tuple(attempts), tuple(assessments), budget,
                        "review_refused", tuple(reservations) + (str(exc),))
                continued_inputs.update(continuation_keys)
                budget = budget.spend_on(Spend(discarded_results=1))
                feedback = None
                continue
            continuation = None
            failures = []
            working_owner = getattr(self.brain, "working_review", None)
            if working_owner is not None and attempt.reason in (
                    StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION):
                try:
                    work = working_owner.review(attempt, budget=budget,
                        cancelled=lambda: cancelled() or deadline_hit(),
                        max_model_calls=max(0, limits.max_steps - steps))
                    working_reviews.append(work)
                    if work.review is not None:
                        budget = measured(work.review.budget)
                        steps += work.review.model_steps
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
                        if interaction.checked:
                            check_work(attempt)
                    except ReviewRefused as exc:
                        budget = measured(getattr(exc, "budget", budget))
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "review_refused", tuple(reservations) + (str(exc),))
                    if cancelled():
                        return finish(tuple(attempts), tuple(assessments),
                            budget.cancel(datetime.now(timezone.utc).isoformat()), "cancelled",
                            tuple(reservations))
                    if budget.spent_out and not completed_child_within_grant(budget):
                        return finish(tuple(attempts), tuple(assessments), budget,
                                      "budget", tuple(reservations))
                    if interaction.checked:
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "interaction_checks_complete_private_candidate", tuple(reservations))
                    # A missing/unknown semantic assessment is not an instruction
                    # to retry. Only complete explicit failures of these proposed
                    # words can enter the same repair mechanism as a legal answer.
                    if (not interaction.clauses_complete
                            or any(row.assessed is None for row in interaction.judgments)):
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "interaction_checks_missing", tuple(reservations))
                    failures.extend((f"communication:{row.name}", row.reason)
                        for row in interaction.judgments if row.assessed is False)
                    if not failures:
                        return finish(tuple(attempts), tuple(assessments), budget,
                            "interaction_checks_missing", tuple(reservations))
                else:
                    return finish(tuple(attempts), tuple(assessments), budget,
                                            attempt.reason.value, tuple(reservations))
            else:
                if budget.spent_out:
                    return finish(tuple(attempts), tuple(assessments), budget,
                                            "budget", tuple(reservations))
                try:
                    if self.brain.finalizer is not None:
                        # Run the installation-owned current source/generation
                        # owner before any candidate failure may invite repair.
                        self.brain.finalizer.reader.current(attempt)
                    review = self.brain.review(attempt, budget=budget,
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
                    complete_work = check_work(attempt)
                    if cancelled():
                        return finish(tuple(attempts), tuple(assessments),
                            budget.cancel(datetime.now(timezone.utc).isoformat()), "cancelled",
                            tuple(reservations))
                    if budget.spent_out and not completed_child_within_grant(budget):
                        return finish(tuple(attempts), tuple(assessments), budget,
                                                "budget", tuple(reservations))
                    current = self.brain.store.load(matter_id)
                    # A replay carries fresh elapsed time and all prior child
                    # spending in its running budget. The final assessment is
                    # about the historical sealed verdict, whose exact budget
                    # is reconstructed separately; only that budget field may
                    # differ from the trusted reviewer's returned verdict.
                    sealed_review = saved_package_reviews(
                        attempt, review.packages, current, self.brain.log)
                    if replace(review, budget=sealed_review.budget) != sealed_review:
                        raise ReviewRefused(
                            "The current review differs from its sealed independent verdict")
                    review = sealed_review
                    result = self.assessment.assess(
                        attempt, review, expected_version=current.version)
                    if self.brain.publication is not None:
                        publications.append(self.brain.publication.record(
                            attempt, review, result, original_message=message))
                    budget = measured(budget)
                except ProposalBindingRefused as exc:
                    # Only a typed authored-reference failure enters repair.
                    # The source owner has already checked the actual captured
                    # file; no fabricated citation reaches an independent judge.
                    budget = measured(getattr(exc, "budget", budget))
                    failures.append(("proposal_binding", str(exc)))
                except ReviewRefused as exc:
                    # A broken captured contract is not a paid-repair invitation.
                    # Its parent/child journals and external ledger retain all work.
                    budget = measured(getattr(exc, "budget", budget))
                    return finish(tuple(attempts), tuple(assessments), budget,
                                            "review_refused", tuple(reservations) + (str(exc),))
                else:
                    assessments.append(result)
                    if budget.spent_out and not completed_child_within_grant(budget):
                        return finish(tuple(attempts), tuple(assessments), budget,
                                                "budget", tuple(reservations))
                    owner_states = tuple(row for row in result.failed if not answer_repairable(row))
                    reservations.extend(reservation(row) for row in owner_states
                                        if reservation(row) not in reservations)
                    if any(row.response in {Response.BLOCK, Response.WITHHOLD}
                           for row in owner_states):
                        # Human/authority/file-state failures stop merits repair.
                        return finish(tuple(attempts), tuple(assessments), budget,
                                                "owner_state_blocked", tuple(reservations))
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
                        stop = ("working_checks_incomplete_private_candidate"
                            if complete_work is not None and not complete_work.complete else
                            "required_reservations" if reservations else
                            "checks_complete_private_candidate" if result.checks_complete else
                            "required_checks_missing" if gaps else "independent_review_incomplete")
                        return finish(tuple(attempts), tuple(assessments), budget, stop, gaps)
            if cancelled():
                return finish(tuple(attempts), tuple(assessments),
                    budget.cancel(datetime.now(timezone.utc).isoformat()), "cancelled",
                    tuple(reservations))
            # Changed diagnostic wording is not new work. A repeated failed
            # proposal cannot buy progress in either communication or merits.
            signature = digest(attempt.proposal)
            if signature in seen:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "no_progress", tuple(reservations))
            if budget.spent_out or steps >= limits.max_steps:
                return finish(tuple(attempts), tuple(assessments), budget,
                              "budget", tuple(reservations))
            seen.add(signature)
            if iteration == max_repairs:
                return finish(tuple(attempts), tuple(assessments), budget,
                                        "repair_limit", tuple(reservations))
            # Discarded work is still paid work, and no repair gets a fresh budget.
            budget = budget.spend_on(Spend(discarded_results=1))
            feedback = CheckFeedback(matter_id, attempt.record.identity.turn_id,
                                     attempt.record.events[-1].fingerprint, tuple(failures))
        raise AssertionError("A bounded evaluation did not terminate")
