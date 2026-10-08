"""Owned source/range/replay checks; injected judgments do not prove semantics."""
from copy import deepcopy
import json

import pytest

from nm.brain.release import (
    PASSAGE_REVIEW_RENDERER, LEGACY_PASSAGE_REVIEW_RENDERER, extraction_review_gaps, prepare_release, render_saved_release,
)
from nm.shared.model_port import SchemaViolation
from tests.test_disputes_objectives_release import prepared, historical_focused_v1_release
from tests.test_brain_disputes_objectives import item, selection
from tests.test_new_brain_release import ReviewModel


def outside(purpose="nm_work"):
    return {"kind": "outside_scope", "purpose": purpose, "reason": "No dispute or party objective is contributed."}


def meaning(kind="dispute", *, support=None, context=None, represented=None, contribution="reported"):
    return {"kind": kind, "contribution": contribution, "description": "Attributed current contribution",
        "support_passage_ids": support or ["current:p1"], "context_passage_ids": context or [],
        "uncertainty": None, "represented_by": represented or []}


def proof(readings=None, *reviews, greeting=False):
    return {"readings": readings or {"current:p1": [outside()]},
            "unit_reviews": list(reviews), "greeting": greeting}


def verdict(identity="dispute:1", value="supported", reason="scope"):
    row = {"unit_id": identity, "verdict": value}
    if value != "supported":
        row["reason"] = reason
    return row


def release(proposal, review):
    return prepare_release(ReviewModel(review), proposal, "information", passage_review=True)


def test_complete_originals_only_once_and_label_cannot_influence_independent_reading():
    proposal = prepared(disputes=[item()])
    reviewed = proof({"current:p1": [meaning(represented=["dispute:1"])]}, verdict())
    requests = []
    for label in ("greeting", "information", "action", "mixed"):
        model = ReviewModel(deepcopy(reviewed))
        saved = prepare_release(model, proposal, label, passage_review=True)
        request, schema, _, _ = model.calls[0]
        payload = json.loads(request.user)
        assert payload["current_message"]["message"]["passages"][0]["text"] == proposal["sources"][-1]["message"]["text"]
        assert "proposed_label" not in payload
        assert "passages" not in payload["proposals"]["disputes"][0]
        assert all(section in request.system for section in ("Message:", "Purpose:", "Look for:", "Outcome:"))
        assert saved["renderer_version"] == PASSAGE_REVIEW_RENDERER
        assert extraction_review_gaps(saved) == [] and saved["state"] == "ready"
        assert [row["text"] for row in saved["elements"]] == ["Message received."]
        assert render_saved_release(saved) == saved and len(model.calls) == 1
        requests.append((request, schema))
    assert all(request == requests[0] for request in requests)


def test_independently_checked_absence_can_reject_revived_history_without_losing_input():
    history = [{"role": "advocate", "text": "I want the records returned."}]
    proposal = prepared(objectives=[item("User wants records returned", [
        selection("history_1:p1"), selection("current:p1", "context")])],
        message="Summarise our discussion.", history=history)
    saved = release(proposal, proof(None, verdict("objective:1", "unsupported")))
    assert saved["state"] == "ready" and extraction_review_gaps(saved) == []
    assert saved["proof"]["unit_reviews"][0]["verdict"] == "unsupported"
    assert saved["units"]["objective:1"]["proposal"] == proposal["proposal"]["objectives"][0]
    assert render_saved_release(saved) == saved


def test_missing_conflict_is_not_filled_by_objective_with_the_same_source():
    proposal = prepared(objectives=[item("User seeks restoration", [selection()])])
    saved = release(proposal, proof({"current:p1": [meaning(), meaning("objective", represented=["objective:1"])]},
                                   verdict("objective:1")))
    gaps = extraction_review_gaps(saved)
    assert len(gaps) == 1 and gaps[0]["kind"] == "disputes"
    assert gaps[0]["passages"][0]["quote"] == proposal["sources"][-1]["message"]["text"]
    assert saved["state"] == "partial"
    damaged = deepcopy(saved)
    damaged["proof"]["readings"]["current:p1"][0]["represented_by"] = ["objective:1"]
    with pytest.raises(SchemaViolation):
        render_saved_release(damaged)


def test_wrong_current_occurrence_is_rejected_even_with_supported_verdict():
    proposal = prepared(objectives=[item("Current new objective", [selection("current:p2")])],
                        message="The previous objective is withdrawn. I now want a different outcome.")
    reviewed = proof({"current:p1": [meaning("objective", represented=["objective:1"], contribution="withdrawn")],
        "current:p2": [meaning("objective", support=["current:p2"], represented=["objective:1"])]}, verdict("objective:1"))
    rejected = release(proposal, reviewed)
    rejected_gap = extraction_review_gaps(rejected)[0]
    assert rejected["state"] == "partial"
    assert rejected_gap["rejected_associations"][0]["unit_id"] == "objective:1"
    assert rejected["proof"]["readings"]["current:p1"][0]["represented_by"] == ["objective:1"]
    reviewed["readings"]["current:p1"][0]["represented_by"] = []
    saved = release(proposal, reviewed)
    assert extraction_review_gaps(saved)[0]["contribution"] == "withdrawn"
    assert saved["state"] == "partial" and render_saved_release(saved) == saved


def test_independent_contributions_within_one_occurrence_can_be_represented_together():
    # Add the second selected passage to the fixture: the complete compound
    # meaning legitimately depends on both current navigation partitions.
    proposal = prepared(objectives=[item("Prior aim withdrawn; new aim expressed", [selection(), selection("current:p2")])],
                        message="I no longer want continued access; I want to collect my things.")
    reviewed = proof({"current:p1": [meaning("objective", represented=["objective:1"], contribution="withdrawn")],
        "current:p2": [meaning("objective", support=["current:p2"], represented=["objective:1"])]}, verdict("objective:1"))
    saved = release(proposal, reviewed)
    assert extraction_review_gaps(saved) == [] and saved["state"] == "ready"


def test_repeated_meaning_can_bind_shared_original_support_without_a_duplicate_record():
    proposal = prepared(disputes=[item("Reported refusal", [selection()])],
                        message="The supplier refuses delivery. It still refuses.")
    reviewed = proof({"current:p1": [meaning(represented=["dispute:1"])],
        "current:p2": [meaning(support=["current:p1"], context=["current:p2"], represented=["dispute:1"])]}, verdict())
    saved = release(proposal, reviewed)
    assert len(saved["units"]) == 1 and saved["state"] == "ready"
    assert extraction_review_gaps(saved) == [] and render_saved_release(saved) == saved


def test_positive_verdict_cannot_coexist_with_only_outside_scope_readings():
    proposal = prepared(disputes=[item()])
    with pytest.raises(SchemaViolation, match="no in-scope current reading"):
        release(proposal, proof(None, verdict()))


def test_context_only_overlap_does_not_represent_a_different_contribution():
    proposal = prepared(objectives=[item("New goal", [selection("current:p2"), selection("current:p1", "context")])],
                        message="The old goal is withdrawn. I now seek a different result.")
    reviewed = proof({"current:p1": [meaning("objective", represented=["objective:1"], contribution="withdrawn")],
        "current:p2": [meaning("objective", support=["current:p2"], represented=["objective:1"])]}, verdict("objective:1"))
    saved = release(proposal, reviewed)
    assert extraction_review_gaps(saved)[0]["rejected_associations"]
    assert saved["state"] == "partial" and render_saved_release(saved) == saved
    saved["renderer_version"] = LEGACY_PASSAGE_REVIEW_RENDERER
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)


def test_previous_strict_passage_review_replays_valid_proof_without_upgrade():
    saved = release(prepared(), proof())
    saved["renderer_version"] = LEGACY_PASSAGE_REVIEW_RENDERER
    assert render_saved_release(saved) == saved


def test_repaired_objective_uses_original_support_and_derives_current_context_from_owned_parent():
    history = [{"role": "advocate", "text": "I want access for repairs, not ownership."},
               {"role": "nm", "text": "You want ownership."}]
    proposal = prepared(objectives=[item("User seeks access for repairs, not ownership", [
        selection("history_1:p1"), selection("current:p1", "context")])],
        message="Correct your understanding.", history=history)
    reviewed = proof({"current:p1": [meaning("objective", support=["history_1:p1"],
        context=["history_2:p1"], represented=["objective:1"], contribution="interpretation_repair")]}, verdict("objective:1"))
    assert release(proposal, reviewed)["state"] == "ready"
    reviewed["readings"]["current:p1"][0]["support_passage_ids"] = ["history_2:p1"]
    with pytest.raises(SchemaViolation):
        release(proposal, reviewed)


@pytest.mark.parametrize("alter", [
    lambda p: p["readings"].clear(),
    lambda p: p["readings"].update({"foreign:p1": [outside()]}),
    lambda p: p["readings"]["current:p1"].clear(),
    lambda p: p["readings"]["current:p1"][0].update(reply="Work completed"),
    lambda p: p["readings"]["current:p1"][0].update(represented_by=["dispute:99"]),
    lambda p: p["readings"]["current:p1"][0].update(support_passage_ids=["foreign:p1"]),
    lambda p: p["unit_reviews"].clear(),
    lambda p: p["unit_reviews"].append(deepcopy(p["unit_reviews"][0])),
    lambda p: p["unit_reviews"][0].update(reason="none"),
])
def test_invalid_owned_review_is_typed_failure_without_internal_retry(alter):
    proposal = prepared(disputes=[item()])
    reviewed = proof({"current:p1": [meaning(represented=["dispute:1"])]}, verdict())
    alter(reviewed)
    model = ReviewModel(reviewed)
    with pytest.raises(SchemaViolation):
        prepare_release(model, proposal, "information", passage_review=True)
    assert len(model.calls) == 1


def test_unrepresented_rejected_and_unresolved_meanings_remain_incomplete():
    proposal = prepared(disputes=[item()])
    for value in ("unsupported", "unresolved"):
        saved = release(proposal, proof({"current:p1": [meaning(represented=["dispute:1"])]}, verdict(value=value)))
        assert extraction_review_gaps(saved) and saved["state"] == "withheld"
        assert saved["elements"] == [] and render_saved_release(saved) == saved


@pytest.mark.parametrize("version", ["disputes_objectives_release_v1", "disputes_objectives_release_v2", "unknown"])
def test_new_review_cannot_be_rebound_to_a_legacy_or_unknown_proof_contract(version):
    saved = release(prepared(), proof())
    saved["renderer_version"] = version
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)
    historical = historical_focused_v1_release()
    historical["renderer_version"] = PASSAGE_REVIEW_RENDERER
    with pytest.raises(SchemaViolation):
        render_saved_release(historical)
