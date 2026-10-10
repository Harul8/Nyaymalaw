"""Scripted paired full-review coverage gates; no actual model/API calls."""

from copy import deepcopy

import pytest

from nm.brain.execution_contracts import (
    ExecutionEvidenceInvalid,
    effect_catalogue,
    validate_record_outcome,
    validate_review_completion,
)
from nm.shared.model_port import SchemaViolation
from tests.test_brain_execution_contracts import receipt, unit


def assessment(required, *, state="complete", scope_requirement=None):
    return {
        "contract": "independent_account_coverage_v1",
        "state": state,
        "reason": "The assessment covers the original scope and final represented account.",
        "missing_source_ids": [],
        "review_scope": {
            "requests": [
                {
                    "request_index": 0,
                    "record_requirement": deepcopy(
                        required if scope_requirement is None else scope_requirement
                    ),
                }
            ]
        },
    }


def review_evidence(*, state="complete", performed=False):
    required = {
        "kind": "review",
        "operation": "none",
        "target_ids": [],
        "success_condition": "Reconcile every reported account in this matter.",
    }
    evidence = receipt(
        requested_review=True,
        activated=["result"] if performed else [],
        review="checked" if performed else "no_candidates",
    )
    if not performed:
        evidence["effects"]["details"]["operations"] = []
    evidence["requests"][0]["record_requirement"] = required
    for name in ("dispute_review", "detail_review"):
        evidence["stages"][name]["account_coverage"] = assessment(required, state=state)
    return evidence, required


@pytest.mark.parametrize("state", ["partial", "unassessed"])
def test_incomplete_omission_coverage_keeps_checked_performed_peer_but_not_full_review(state):
    evidence, _ = review_evidence(state=state, performed=True)
    identity = next(iter(effect_catalogue(evidence)))
    partial = unit("unresolved", effects=[identity])
    validate_record_outcome(partial, evidence, ["result"])
    with pytest.raises(SchemaViolation, match="partial/unassessed"):
        validate_record_outcome(
            unit("performed", effects=[identity], complete=True), evidence, ["result"]
        )


def test_complete_actual_empty_review_can_finish_without_new_rows():
    evidence, _ = review_evidence()
    validate_record_outcome(unit("review_no_change", complete=True), evidence, [])
    assert effect_catalogue(evidence) == {}


@pytest.mark.parametrize("missing_or_unassessed", ["missing", "unassessed"])
def test_stage_returned_and_no_candidates_do_not_substitute_for_independent_coverage(
    missing_or_unassessed,
):
    evidence, _ = review_evidence()
    if missing_or_unassessed == "missing":
        evidence["stages"]["detail_review"].pop("account_coverage")
    else:
        evidence["stages"]["detail_review"]["account_coverage"]["state"] = "unassessed"
    validate_record_outcome(unit("unresolved"), evidence, [])
    with pytest.raises(SchemaViolation, match="coverage"):
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])


def test_narrower_complete_scope_does_not_close_whole_requested_review():
    evidence, required = review_evidence()
    narrowed = {**required, "target_ids": ["only-one-detail"]}
    evidence["stages"]["detail_review"]["account_coverage"] = assessment(
        required, scope_requirement=narrowed
    )
    with pytest.raises(SchemaViolation, match="exact requested account scope"):
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])


def test_selected_review_task_completion_needs_coverage_while_independent_question_can_complete():
    evidence, _ = review_evidence(state="unassessed")
    independent = unit(
        "unresolved", progress=[{"target_id": "independent-question", "status": "complete"}]
    )
    validate_record_outcome(independent, evidence, [])
    completing = unit("review_no_change", progress=[{"target_id": "$work", "status": "complete"}])
    with pytest.raises(SchemaViolation, match="coverage"):
        validate_record_outcome(completing, evidence, [])


def test_change_completion_does_not_require_unrelated_global_coverage():
    evidence, _ = review_evidence(state="unassessed", performed=True)
    evidence["requests"][0]["record_requirement"] = {
        "kind": "change",
        "operation": "new",
        "target_ids": [],
        "success_condition": "Record the newly reported date.",
    }
    identity = next(iter(effect_catalogue(evidence)))
    validate_record_outcome(
        unit("performed", effects=[identity], complete=True), evidence, ["result"]
    )


def test_present_corrupt_complete_assessment_is_core_integrity_error():
    evidence, _ = review_evidence()
    evidence["stages"]["detail_review"]["account_coverage"]["missing_source_ids"] = ["L1"]
    with pytest.raises(ExecutionEvidenceInvalid, match="contradicts"):
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])


def test_extra_requested_scopes_at_same_index_do_not_hide_exact_review_coverage():
    evidence, required = review_evidence()
    extra = {
        **required,
        "target_ids": ["separate-target"],
        "success_condition": "Review this separate stored detail too.",
    }
    for name in ("dispute_review", "detail_review"):
        evidence["stages"][name]["account_coverage"]["review_scope"]["requests"].append(
            {"request_index": 0, "record_requirement": extra, "task_id": "another-review"}
        )
    validate_record_outcome(unit("review_no_change", complete=True), evidence, [])


def test_inherited_review_task_different_from_selected_work_requires_its_owned_scope():
    evidence, required = review_evidence(state="unassessed")
    independent = unit(
        "performed", progress=[{"target_id": "independent-question", "status": "complete"}]
    )
    validate_review_completion(
        independent, evidence, requirement=required, task_id="another-review"
    )
    completing = unit("performed", progress=[{"target_id": "another-review", "status": "complete"}])
    with pytest.raises(SchemaViolation, match="coverage"):
        validate_review_completion(
            completing, evidence, requirement=required, task_id="another-review"
        )
    for name in ("dispute_review", "detail_review"):
        coverage = assessment(required)
        coverage["review_scope"]["requests"].append(
            {
                "request_index": 0,
                "record_requirement": deepcopy(required),
                "task_id": "another-review",
            }
        )
        evidence["stages"][name]["account_coverage"] = coverage
    validate_review_completion(completing, evidence, requirement=required, task_id="another-review")
    for name in ("dispute_review", "detail_review"):
        evidence["stages"][name]["account_coverage"]["review_scope"]["requests"][-1]["task_id"] = (
            "wrong-task"
        )
    with pytest.raises(SchemaViolation, match="exact requested account scope"):
        validate_review_completion(
            completing, evidence, requirement=required, task_id="another-review"
        )


def test_current_review_needs_current_scope_while_matching_aliases_are_allowed():
    evidence, required = review_evidence()
    for name in ("dispute_review", "detail_review"):
        current = evidence["stages"][name]["account_coverage"]["review_scope"]["requests"][0]
        evidence["stages"][name]["account_coverage"]["review_scope"]["requests"].append(
            {**deepcopy(current), "task_id": "prior-review"}
        )
    validate_record_outcome(unit("review_no_change", complete=True), evidence, [])
    for name in ("dispute_review", "detail_review"):
        evidence["stages"][name]["account_coverage"]["review_scope"]["requests"].pop(0)
    with pytest.raises(SchemaViolation, match="exact requested account scope"):
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])


@pytest.mark.parametrize("state", ["partial", "unassessed"])
def test_review_completion_diagnostic_has_typed_state_not_text_inference(state):
    from nm.brain.execution_contracts import ReviewCompletionIncomplete

    evidence, _ = review_evidence(state=state)
    with pytest.raises(ReviewCompletionIncomplete) as captured:
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])
    assert captured.value.state == state


def test_missing_review_coverage_diagnostic_is_unassessed():
    from nm.brain.execution_contracts import ReviewCompletionIncomplete

    evidence, _ = review_evidence()
    evidence["stages"]["detail_review"].pop("account_coverage")
    with pytest.raises(ReviewCompletionIncomplete) as captured:
        validate_record_outcome(unit("review_no_change", complete=True), evidence, [])
    assert captured.value.state == "unassessed"
