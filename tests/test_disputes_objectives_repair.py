"""Repair owner preserves checked peers; real semantics are tested separately."""
from copy import deepcopy
import json

import pytest

from nm.brain.disputes_objectives import extraction_units, repair_disputes_objectives
from nm.brain.release import extraction_review_gaps
from nm.shared.model_port import SchemaViolation
from tests.test_brain_disputes_objectives import ExtractionModel, item, output, selection
from tests.test_disputes_objectives_release import prepared
from tests.test_disputes_objectives_passage_review import release, meaning, proof, verdict


def missing(proposal):
    reviewed = release(proposal, proof({"current:p1": [meaning(represented=["dispute:1"])],
        "current:p2": [meaning(support=["current:p2"])]}, verdict()))
    return extraction_review_gaps(reviewed)


def test_repair_preserves_supported_peer_and_assigns_fresh_owned_id_without_changing_sources():
    proposal = prepared(disputes=[item()], message="The supplier refuses delivery. The partner refuses access.")
    before = deepcopy(proposal)
    model = ExtractionModel(output(disputes=[item("Partner refuses access", [selection("current:p2")])]))
    merged = repair_disputes_objectives(model, proposal, supported_unit_ids=["dispute:1"], gaps=missing(proposal))
    assert proposal == before and merged["sources"] == proposal["sources"]
    assert merged["proposal"]["disputes"][0] == proposal["proposal"]["disputes"][0]
    assert list(extraction_units(merged)) == ["dispute:1", "dispute:2"]
    payload = json.loads(model.calls[0][0].user)
    assert payload["repair_scope"]["supported_records"][0]["id"] == "dispute:1"
    assert payload["repair_scope"]["missing_contributions"][0]["kind"] == "disputes"
    assert "quote" not in json.dumps(payload["repair_scope"])
    assert len(model.calls) == 1


def test_exact_repetition_does_not_duplicate_supported_record_or_overwrite_it():
    proposal = prepared(disputes=[item()])
    model = ExtractionModel(output(disputes=[item()]))
    merged = repair_disputes_objectives(model, proposal, supported_unit_ids=["dispute:1"], gaps=[])
    assert merged["proposal"] == proposal["proposal"] and len(model.calls) == 1


def test_held_ids_and_rejected_units_do_not_collide_with_repaired_replacements():
    proposal = prepared(disputes=[item(description=""), item(), item("Rejected interpretation")])
    model = ExtractionModel(output(disputes=[item(description=""), item("Corrected account")]))
    merged = repair_disputes_objectives(model, proposal, supported_unit_ids=["dispute:2"], gaps=[])
    assert [row["id"] for row in merged["proposal"]["disputes"]] == ["dispute:2", "dispute:5"]
    assert merged["issues"][0]["unit"] == "dispute:4"
    assert merged["proposal"]["disputes"][0] == proposal["proposal"]["disputes"][0]
    assert list(extraction_units(merged)) == ["dispute:2", "dispute:5"]


@pytest.mark.parametrize("damage", ["foreign_peer", "duplicate_peer", "bad_gap", "source_drift", "held_identity"])
def test_invalid_repair_scope_fails_before_a_model_call(damage):
    proposal = prepared(disputes=[item()], message="The supplier refuses delivery. The partner refuses access.")
    gaps = missing(proposal)
    peers = ["dispute:1"]
    if damage == "foreign_peer": peers = ["dispute:99"]
    elif damage == "duplicate_peer": peers *= 2
    elif damage == "bad_gap": gaps[0]["kind"] = "actions"
    elif damage == "source_drift": gaps[0]["passages"][0]["quote"] = "Invented source"
    else: proposal["issues"] = [{"unit":"foreign:x", "reason":"Unknown unit", "rejected_proposal":{}}]
    model = ExtractionModel(output())
    with pytest.raises(SchemaViolation):
        repair_disputes_objectives(model, proposal, supported_unit_ids=peers, gaps=gaps)
    assert model.calls == []
