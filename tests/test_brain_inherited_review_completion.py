"""Owned inherited no-change review results; scripted evidence only."""

from copy import deepcopy

import pytest

from nm.brain.execution_contracts import validate_record_outcome
from nm.shared.model_port import SchemaViolation
from tests.test_brain_execution_contracts import unit
from tests.test_brain_review_completion import review_evidence


def inherited_no_change_evidence(*, state="complete", task_id="prior-review"):
    evidence, original = review_evidence(state=state)
    evidence["requests"][0]["record_requirement"] = {
        "kind": "none",
        "operation": "none",
        "target_ids": [],
        "success_condition": "",
    }
    scoped = {"request_index": 0, "task_id": task_id, "record_requirement": deepcopy(original)}
    evidence["review_scope"] = {"requests": [deepcopy(scoped)]}
    for name in ("dispute_review", "detail_review"):
        evidence["stages"][name]["account_coverage"]["review_scope"]["requests"].append(
            deepcopy(scoped)
        )
    return evidence


def test_current_none_can_complete_actually_owned_inherited_no_change_review():
    evidence = inherited_no_change_evidence()
    resolved = unit(
        "review_no_change", progress=[{"target_id": "prior-review", "status": "complete"}]
    )
    validate_record_outcome(resolved, evidence, [])
    missing_owner = deepcopy(evidence)
    missing_owner.pop("review_scope")
    with pytest.raises(SchemaViolation, match="actual requested reading and review"):
        validate_record_outcome(resolved, missing_owner, [])


def test_inherited_no_change_review_cannot_complete_with_unassessed_or_narrower_scope():
    resolved = unit(
        "review_no_change", progress=[{"target_id": "prior-review", "status": "complete"}]
    )
    with pytest.raises(SchemaViolation, match="partial/unassessed"):
        validate_record_outcome(resolved, inherited_no_change_evidence(state="unassessed"), [])
    evidence = inherited_no_change_evidence()
    evidence["stages"]["detail_review"]["account_coverage"]["review_scope"]["requests"][-1][
        "record_requirement"
    ]["success_condition"] = "A narrower check."
    with pytest.raises(SchemaViolation, match="exact requested account scope"):
        validate_record_outcome(resolved, evidence, [])


def test_unrelated_question_completion_does_not_convert_current_none_into_review():
    evidence = inherited_no_change_evidence()
    resolved = unit("none", progress=[{"target_id": "independent-question", "status": "complete"}])
    validate_record_outcome(resolved, evidence, [])
    pretend_review = deepcopy(resolved)
    pretend_review["record_outcome"]["status"] = "review_no_change"
    with pytest.raises(SchemaViolation, match="actual requested reading and review"):
        validate_record_outcome(pretend_review, evidence, [])
