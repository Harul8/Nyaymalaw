"""Direct observable acknowledgement contract checks, without app/model calls.

The caller supplies a mechanically admitted unit and, for final rendering, its
independently checked disposition. This helper does not evaluate source meaning.
"""
from copy import deepcopy

import pytest

from nm.brain import execution_contracts
from nm.brain.execution_contracts import ExecutionEvidenceInvalid, effect_catalogue
from tests.test_brain_continuation_record_outcome import evidence

STATEMENT = "The handover was on 4 May."


def inputs(status="performed", *, checked=True, reader="returned"):
    receipt = evidence(reader=reader)
    receipt["requests"][0]["response_mode"] = "record_acknowledgement"
    effect_id = next(iter(effect_catalogue(receipt)))
    record = {"id": "saved-observation", "statement": STATEMENT}
    catalogue = {record["id"]: {"id": record["id"], "type": "material", "record": record}}
    receipt["record_changes"] = [{"effect_id": effect_id, "kind": "details", "relation": "new",
                                  "before_records": [], "after_record": record}]
    unit = {
        "request_index": 0,
        "blocks": [{"id": "owned-block", "kind": "completion", "text": "Fabricated prose.",
                    "uncertainty": "reported", "span_ids": ["L1"], "record_ids": [],
                    "legal_source_ids": [], "inline_citations": []}],
        "questions": [], "next_work": [],
        "record_outcome": {"status": status, "block_id": "owned-block",
                           "effect_ids": [effect_id] if status == "performed" else [],
                           "current_record_ids": [record["id"]]
                           if status == "already_current" else [], "reason": "Declared outcome."},
        "sufficiency": {"status": "partial" if status == "unresolved" else "complete",
                        "block_id": "owned-block"},
        "work": {"create": True, "existing_id": ""}, "progress_updates": [],
    }
    if checked:
        unit["record_check"] = {
            "outcome": {"performed": "fulfilled", "already_current": "fulfilled",
                        "review_no_change": "no_change_justified",
                        "unresolved": "unfinished"}[status],
            "reason": "The test explicitly supplies the checked disposition.",
        }
    return {"units": [unit]}, receipt, catalogue


def render(continuation, receipt, catalogue, **kwargs):
    return execution_contracts.canonical_record_acknowledgements(
        continuation, receipt, record_catalogue=catalogue, **kwargs)


def test_pre_review_rendering_needs_no_invented_independent_verdict():
    continuation, receipt, catalogue = inputs(checked=False)
    original = deepcopy(continuation)
    result = render(continuation, receipt, catalogue, require_checked=False)
    assert result["units"][0]["blocks"][0]["text"] == (
        "Saved record changes:\nNew entry: " + STATEMENT)
    assert "record_check" not in result["units"][0]
    assert continuation == original
    assert receipt["requests"][0]["acknowledgement_delivery"] == "code_only"


def test_final_rendering_requires_checked_disposition():
    continuation, receipt, catalogue = inputs(checked=False)
    with pytest.raises(ExecutionEvidenceInvalid, match="no checked record outcome"):
        render(continuation, receipt, catalogue)


def test_checked_outcome_preserves_lifecycle_and_block_owners():
    continuation, receipt, catalogue = inputs()
    original = deepcopy(continuation["units"][0])
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["record_outcome"] == original["record_outcome"]
    assert result["record_check"] == original["record_check"]
    assert result["work"] == original["work"]
    assert result["progress_updates"] == original["progress_updates"]
    assert result["sufficiency"] == original["sufficiency"]
    assert result["blocks"][0]["id"] == original["blocks"][0]["id"]


def test_a_returned_reader_is_required_for_selected_performed_effect():
    continuation, receipt, catalogue = inputs(reader="not_run")
    with pytest.raises(ExecutionEvidenceInvalid, match="unperformed change"):
        render(continuation, receipt, catalogue)


def test_selected_effect_needs_canonical_entry_delta():
    continuation, receipt, catalogue = inputs()
    receipt["record_changes"] = []
    with pytest.raises(ExecutionEvidenceInvalid, match="unperformed change"):
        render(continuation, receipt, catalogue)


def test_current_entry_selection_cannot_invent_foreign_record():
    continuation, receipt, catalogue = inputs("already_current")
    continuation["units"][0]["record_outcome"]["current_record_ids"] = ["foreign-record"]
    with pytest.raises(ExecutionEvidenceInvalid, match="unowned current entry"):
        render(continuation, receipt, catalogue)


def test_current_state_is_displayed_without_claiming_historical_operation():
    continuation, receipt, catalogue = inputs("already_current")
    result = render(continuation, receipt, catalogue)
    assert result["units"][0]["blocks"][0]["text"] == "Current record entries:\n" + STATEMENT


def test_unresolved_outcome_cannot_turn_into_completion_by_rendering():
    continuation, receipt, catalogue = inputs("unresolved")
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0]["text"] == "The requested record work remains unfinished."
    assert result["record_check"]["outcome"] == "unfinished"
    assert result["sufficiency"]["status"] == "partial"
    assert result["progress_updates"] == []


@pytest.mark.parametrize("field", ["questions", "next_work"])
def test_substantive_followup_preserves_checked_content_instead_of_silently_dropping_it(field):
    continuation, receipt, catalogue = inputs("unresolved")
    continuation["units"][0][field] = [{"id": "followup", "block_id": "owned-block"}]
    original = deepcopy(continuation)
    assert render(continuation, receipt, catalogue) == original
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


def test_substantive_receipt_cannot_carry_forged_code_delivery_marker():
    continuation, receipt, catalogue = inputs()
    receipt["requests"][0].update(response_mode="substantive", acknowledgement_delivery="code_only")
    with pytest.raises(ExecutionEvidenceInvalid, match="no declared delivery owner"):
        render(continuation, receipt, catalogue)


def test_discarded_law_prose_does_not_leave_false_inline_anchors_on_code_status():
    continuation, receipt, catalogue = inputs("unresolved")
    block = continuation["units"][0]["blocks"][0]
    block.update(kind="assessment", legal_source_ids=["law-1"], record_ids=["research-1"],
                 inline_citations=[{"text": "Fabricated prose.", "legal_source_id": "law-1"}])
    before_review = render(continuation, receipt, catalogue, require_checked=False)["units"][0]
    assert before_review["blocks"][0]["kind"] == "limitation"
    assert before_review["blocks"][0]["inline_citations"] == []
    assert before_review["blocks"][0]["legal_source_ids"] == []
    assert before_review["blocks"][0]["record_ids"] == []
    assert before_review["blocks"][0]["span_ids"] == ["L1"]
    after_review = render({"units": [before_review]}, receipt, catalogue)["units"][0]
    assert "inline_citations" not in after_review["blocks"][0]
