"""Offline original-goal completion checks; no live provider or API calls."""

from copy import deepcopy
from dataclasses import replace

from tests.test_brain_continuation import ContinuationModel, _operation_names, conversation_plan
from tests.test_brain_continuation_record_outcome import declared_unit, evidence, run, verdict

ORIGINAL = {
    "kind": "review",
    "operation": "none",
    "target_ids": [],
    "success_condition": "Review all original accounts and opposing formulations.",
}
NONE = {"kind": "none", "operation": "none", "target_ids": [], "success_condition": ""}


def prior_progress(kind="task"):
    return {
        "state": "ok",
        "rows": [
            {
                "id": "old-review",
                "kind": kind,
                "status": "pending",
                "text": "Review all original accounts and opposing formulations.",
                **({"record_requirement": deepcopy(ORIGINAL)} if kind == "task" else {}),
            }
        ],
        "events": [],
        "coverage": {},
        "diagnostics": [],
    }


def proposed_completion(*, target="old-review", selected=True):
    proposed = declared_unit("already_current", current=["saved-observation"])
    if selected:
        proposed["work"] = {"existing_id": "old-review", "create": False}
    proposed["progress_updates"] = [
        {
            "target_id": target,
            "status": "complete",
            "block_id": "account-0",
            "reason": "The selected original review is complete.",
            "span_ids": ["L1"],
        }
    ]
    return proposed


def ordinary_plan():
    return conversation_plan(
        items=(replace(conversation_plan().items[0], record_requirement=NONE),)
    )


def test_missing_inherited_review_coverage_corrects_locally_and_retains_current_checked_result():
    receipt = evidence(reader="not_run", review="not_run")
    receipt["requests"][0]["record_requirement"] = deepcopy(NONE)
    proposed = proposed_completion()

    def repair(payload):
        assert "correction" in payload
        assert "account coverage" in payload["correction"]["validation_issues"][0]["issue"]
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised["progress_updates"] = []
        return {"units": [revised]}

    model = ContinuationModel(
        [
            {"units": [proposed]},
            repair,
            verdict(0, outcome="fulfilled"),
        ]
    )
    result = run(model, receipt, plan=ordinary_plan(), progress=prior_progress())
    assert _operation_names(model) == [
        "continue_conversation",
        "continue_conversation",
        "verify_continuation",
    ]
    assert result.units[0]["progress_updates"] == []
    assert result.units[0]["record_outcome"]["status"] == "already_current"
    assert result.gate_events[0]["gate"] == "G-INCOMPLETE"


def test_exact_inherited_original_coverage_allows_completion_without_writer_retry():
    receipt = evidence()
    receipt["requests"][0]["record_requirement"] = deepcopy(NONE)
    owned = {"request_index": 0, "task_id": "old-review", "record_requirement": deepcopy(ORIGINAL)}
    receipt["review_scope"] = {"requests": [deepcopy(owned)]}
    for name in ("dispute_review", "detail_review"):
        receipt["stages"][name]["account_coverage"] = {
            "contract": "independent_account_coverage_v1",
            "state": "complete",
            "reason": "The full immutable original account scope was independently checked.",
            "missing_source_ids": [],
            "review_scope": {"requests": [deepcopy(owned)]},
        }
    proposed = proposed_completion()
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt, plan=ordinary_plan(), progress=prior_progress())
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["progress_updates"][0]["target_id"] == "old-review"
    assert result.gate_events == ()


def test_independent_answered_question_completes_without_original_review_coverage():
    receipt = evidence(reader="not_run", review="not_run")
    receipt["requests"][0]["record_requirement"] = deepcopy(NONE)
    proposed = proposed_completion(selected=False)
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt, plan=ordinary_plan(), progress=prior_progress(kind="question"))
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["progress_updates"][0]["target_id"] == "old-review"
    assert result.gate_events == ()


def test_other_inherited_review_completion_cannot_bypass_coverage_via_new_selected_task():
    receipt = evidence(reader="not_run", review="not_run")
    receipt["requests"][0]["record_requirement"] = deepcopy(NONE)
    proposed = proposed_completion(selected=False)

    def repair(payload):
        assert "correction" in payload
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised["progress_updates"] = []
        return {"units": [revised]}

    model = ContinuationModel([{"units": [proposed]}, repair, verdict(0, outcome="fulfilled")])
    result = run(model, receipt, plan=ordinary_plan(), progress=prior_progress())
    assert _operation_names(model) == [
        "continue_conversation",
        "continue_conversation",
        "verify_continuation",
    ]
    assert result.units[0]["progress_updates"] == []
    assert result.gate_events[0]["gate"] == "G-INCOMPLETE"


def test_fresh_created_current_review_completes_with_current_owner_coverage_once():
    receipt = evidence(review="no_candidates")
    receipt["effects"]["details"].update(activated_record_ids=[], operations=[])
    receipt["requests"][0]["record_requirement"] = deepcopy(ORIGINAL)
    owned = {"request_index": 0, "record_requirement": deepcopy(ORIGINAL)}
    receipt["review_scope"] = {"requests": [deepcopy(owned)]}
    for name in ("dispute_review", "detail_review"):
        receipt["stages"][name]["account_coverage"] = {
            "contract": "independent_account_coverage_v1",
            "state": "complete",
            "reason": "The full requested current account scope was independently checked.",
            "missing_source_ids": [],
            "review_scope": {"requests": [deepcopy(owned)]},
        }
    proposed = proposed_completion(target="$work", selected=False)
    proposed["record_outcome"].update(status="review_no_change", current_record_ids=[])
    current = conversation_plan(
        items=(replace(conversation_plan().items[0], record_requirement=ORIGINAL),)
    )
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="no_change_justified")])
    result = run(model, receipt, plan=current)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["progress_updates"][0]["target_id"] == "$work"
    assert result.gate_events == ()


def test_missing_legacy_original_goal_does_not_rederive_current_requirement_as_inherited():
    receipt = evidence(reader="not_run", review="not_run")
    receipt["requests"][0]["record_requirement"] = deepcopy(NONE)
    progress = prior_progress()
    progress["rows"][0].pop("record_requirement")
    model = ContinuationModel(
        [
            {"units": [proposed_completion()]},
            verdict(0, outcome="fulfilled"),
        ]
    )
    result = run(model, receipt, plan=ordinary_plan(), progress=progress)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["progress_updates"][0]["target_id"] == "old-review"
    assert result.gate_events == ()
