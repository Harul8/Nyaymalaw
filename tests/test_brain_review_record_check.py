"""Paired offline meaning dispositions and mechanical request-effect linkage.

Judgments are scripted; these tests do not certify model quality or persistence.
"""

import pytest

from nm.brain.continuation_verification import (
    _decision,
    _schema,
    _transport_row,
)
from nm.shared.model_port import SchemaViolation


def proposed(status="none", *, complete_target=None):
    unit = {
        "request_index": 0,
        "blocks": [
            {
                "id": "owner",
                "kind": "account",
                "text": "A scoped attributed result.",
                "span_ids": ["L1"],
                "record_ids": [],
                "legal_source_ids": [],
            }
        ],
        "questions": [],
        "next_work": [],
        "work": {"existing_id": "selected-task", "create": False},
        "progress_updates": [],
        "sufficiency": {"status": "partial", "block_id": "owner"},
        "record_outcome": {
            "status": status,
            "block_id": "owner",
            "effect_ids": [],
            "current_record_ids": [],
            "reason": "The declared result.",
        },
    }
    if status == "performed":
        unit["record_outcome"]["effect_ids"] = ["effect"]
    elif status == "already_current":
        unit["record_outcome"]["current_record_ids"] = ["active-record"]
    if complete_target:
        unit["progress_updates"] = [
            {
                "target_id": complete_target,
                "status": "complete",
                "block_id": "owner",
                "reason": "The attributed scoped result is supplied.",
                "span_ids": ["L1"],
            }
        ]
    return unit


def review(unit, outcome, reason="The selected evidence supports the precise declared scope."):
    return {
        "request_index": 0,
        "block_checks": [
            {
                "block_id": "owner",
                "requires_legal_support": False,
                "verdict": "accept",
                "reason": "The account preserves its attribution.",
            }
        ],
        "proposal_checks": [],
        "work_check": {
            "existing_id": "selected-task",
            "scope_preserved": True,
            "verdict": "accept",
            "reason": "The task retains its full selected purpose.",
        },
        "progress_checks": [
            {
                "target_id": row["target_id"],
                "status": row["status"],
                "scope_preserved": True,
                "result_supported": True,
                "verdict": "accept",
                "reason": "The explicit scripted result supports this transition.",
            }
            for row in unit["progress_updates"]
        ],
        "question_resolutions": [
            {"question_id": row["target_id"], "status": "complete", "block_id": "owner"}
            for row in unit["progress_updates"]
            if row["target_id"] == "prior-question"
        ],
        "record_check": {"outcome": outcome, "reason": reason},
        "reason": "The unit is a useful scoped response.",
    }


def requirement(kind="change", *, target="requested-target", operation="corrects"):
    return {
        "kind": kind,
        "target_ids": [target] if target else [],
        "operation": operation,
        "success_condition": "The reported handover date is 4 May.",
    }


def payload(required=None, *, actual_target="requested-target", relation="corrects", progress=()):
    return {
        "work_items": [{"request_index": 0, "record_requirement": required}],
        "record_effect_catalogue": {
            "effect": {
                "performed": True,
                "relation": relation,
                "target_record_ids": [actual_target],
                "result_id": "active-record",
            }
        },
        "legal_sources": {},
        "progress": {"state": "ok", "rows": list(progress)},
    }


def decision(unit, outcome, data, *, reason=None):
    row = review(unit, outcome, **({"reason": reason} if reason is not None else {}))
    return _decision(
        _transport_row("accepted_units", row), unit, {}, data["progress"], input_payload=data
    )


def test_fulfilled_relevant_checked_correction_passes_and_unrelated_target_fails():
    unit = proposed("performed")
    assert decision(unit, "fulfilled", payload(requirement()))[0][0] is True
    assert (
        decision(unit, "fulfilled", payload(requirement(), actual_target="other-target"))[0][0]
        is False
    )


def test_related_but_wrong_operation_cannot_fulfill_requested_correction():
    unit = proposed("performed")
    data = payload(requirement(), relation="adds")
    result, retained = decision(unit, "fulfilled", data)
    assert result[0] is False and "operation" in result[1]
    assert retained == ()


def test_actual_requested_review_can_produce_a_useful_no_change_result():
    unit = proposed("review_no_change")
    assert decision(unit, "no_change_justified", payload(requirement("review")))[0][0] is True
    assert decision(unit, "no_change_justified", payload(requirement("change")))[0][0] is False


def test_truthful_unfinished_result_is_an_accepted_partial_response():
    unit = proposed("unresolved")
    assert decision(unit, "unfinished", payload(requirement()))[0][0] is True
    assert decision(unit, "fulfilled", payload(requirement()))[0][0] is False


def test_writer_none_cannot_hide_typed_change_or_independently_detected_original_effect_request():
    unit = proposed("none")
    assert decision(unit, "not_requested", payload(requirement()))[0][0] is False
    # Original-request reading can identify a misclassified effect even when
    # the provisional interpreter says none; disposition mismatch rejects it.
    assert decision(unit, "unfinished", payload(requirement("none")))[0][0] is False
    assert decision(unit, "not_requested", payload(requirement("none")))[0][0] is True


def test_current_state_noop_is_supported_without_a_new_operation_claim():
    unit = proposed("already_current")
    assert decision(unit, "fulfilled", payload(requirement()))[0][0] is True
    assert unit["record_outcome"]["effect_ids"] == []


def test_current_none_request_cannot_complete_inherited_edit_task_without_its_effect():
    prior = {
        "id": "prior-edit",
        "kind": "task",
        "status": "pending",
        "text": "Correct the reported handover date.",
        "record_requirement": requirement(),
    }
    unit = proposed("none", complete_target="prior-edit")
    data = payload(requirement("none"), progress=[prior])
    assert decision(unit, "not_requested", data)[0][0] is False
    fulfilled = proposed("performed", complete_target="prior-edit")
    assert decision(fulfilled, "fulfilled", data)[0][0] is True
    wrong_effect = payload(requirement("none"), actual_target="other-target", progress=[prior])
    assert decision(fulfilled, "fulfilled", wrong_effect)[0][0] is False


def test_unresolved_edit_still_allows_independent_answered_prior_question_completion():
    question = {
        "id": "prior-question",
        "kind": "question",
        "status": "pending",
        "text": "What date do you report?",
    }
    unit = proposed("unresolved", complete_target="prior-question")
    assert decision(unit, "unfinished", payload(requirement(), progress=[question]))[0][0] is True
    edit = {
        "id": "prior-edit",
        "kind": "task",
        "status": "pending",
        "text": "Correct the record.",
        "record_requirement": requirement(),
    }
    unit = proposed("unresolved", complete_target="prior-edit")
    assert decision(unit, "unfinished", payload(requirement(), progress=[edit]))[0][0] is False


def test_substantive_long_record_reason_is_not_arbitrarily_capped_but_empty_is_invalid():
    unit = proposed("none")
    assert decision(unit, "not_requested", payload(None), reason="x" * 600)[0][0] is True
    with pytest.raises(SchemaViolation, match="reason"):
        decision(unit, "not_requested", payload(None), reason="")
    with pytest.raises(SchemaViolation, match="reason"):
        decision(unit, "not_requested", payload(None), reason="  ")
    schema = _schema((0,), {0: unit}, {"rows": []})
    metadata = schema["properties"]["accepted_units"]["items"]["properties"]["record_check"]
    assert metadata["required"] == ["outcome", "reason"]
    assert "maxLength" not in metadata["properties"]["reason"]


def test_all_required_targets_need_actual_matching_operations_without_unrelated_substitution():
    requested = requirement()
    requested["target_ids"] = ["requested-target", "second-target"]
    unit = proposed("performed")
    data = payload(requested)
    assert decision(unit, "fulfilled", data)[0][0] is False
    unit["record_outcome"]["effect_ids"] = ["effect", "second-effect"]
    data["record_effect_catalogue"]["second-effect"] = {
        "performed": True,
        "relation": "corrects",
        "target_record_ids": ["second-target"],
    }
    assert decision(unit, "fulfilled", data)[0][0] is True
    data["record_effect_catalogue"]["second-effect"]["target_record_ids"] = ["unrelated-target"]
    assert decision(unit, "fulfilled", data)[0][0] is False


def test_one_admitted_operation_may_cover_the_whole_requested_target_set():
    requested = requirement()
    requested["target_ids"] = ["requested-target", "second-target"]
    data = payload(requested)
    data["record_effect_catalogue"]["effect"]["target_record_ids"] = [
        "requested-target",
        "second-target",
    ]
    assert decision(proposed("performed"), "fulfilled", data)[0][0] is True
    data["record_effect_catalogue"]["effect"]["target_record_ids"].append(
        "duplicate-sourced-target"
    )
    assert (
        decision(
            proposed("performed"),
            "fulfilled",
            data,
            reason=(
                "The required targets and independently authorized "
                "duplicate correction are covered."
            ),
        )[0][0]
        is True
    )
    data["record_effect_catalogue"]["effect"]["target_record_ids"] = ["duplicate-sourced-target"]
    assert decision(proposed("performed"), "fulfilled", data)[0][0] is False
