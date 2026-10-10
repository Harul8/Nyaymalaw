"""Search hypotheses preserve owned scope; injected models prove mechanics only."""
from copy import deepcopy
import json

import pytest

from nm.brain.dispute_queries import prepare_queries, research_input, validate_queries
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, SchemaViolation
from tests.test_brain_disputes_objectives import ExtractionModel, item, selection
from tests.test_disputes_objectives_release import prepared
from tests.test_disputes_objectives_passage_review import release, meaning, proof, verdict


def checked(two=False, history=None):
    proposal = prepared(disputes=[item()] + ([item("Partner refuses access", [selection("current:p2")])] if two else []),
        message="The supplier refuses delivery." + (" The partner refuses access." if two else ""), history=history)
    readings = {"current:p1": [meaning(represented=["dispute:1"])]}
    reviews = [verdict()]
    if two:
        readings["current:p2"] = [meaning(support=["current:p2"], represented=["dispute:2"])]
        reviews.append(verdict("dispute:2"))
    return proposal, release(proposal, proof(readings, *reviews))


def plan(identity="dispute:1", passage="current:p1"):
    return {"dispute_id": identity, "queries": [{"text": " refusal of agreed delivery ",
        "purpose": " contractual performance ", "passage_ids": [passage]}], "uncertainty": None}


def test_one_focused_call_contains_complete_originals_and_returns_source_bound_hypotheses():
    proposal, reviewed = checked(history=[{"role": "advocate", "text": "Earlier complete account."}])
    original = deepcopy((proposal, reviewed))
    model = ExtractionModel({"plans": [plan()]})
    saved = prepare_queries(model, proposal, reviewed)
    assert saved["state"] == "ready" and len(model.calls) == 1
    assert saved["plans"]["dispute:1"]["queries"][0]["text"] == "refusal of agreed delivery"
    assert validate_queries(saved, proposal, reviewed) == saved
    prompt = model.calls[0][0]
    assert prompt.operation == "decompose_disputes"
    assert all(key in prompt.system for key in ("Message:", "Purpose:", "Look for:", "Outcome:"))
    assert json.loads(prompt.user)["original_conversation"] == proposal["sources"]
    assert (proposal, reviewed) == original


@pytest.mark.parametrize("damage", ["missing", "duplicate", "foreign_source", "foreign_owner", "blank", "extra"])
def test_invalid_plan_holds_only_its_scope_and_keeps_independent_peer(damage):
    proposal, reviewed = checked(two=True)
    bad = plan("dispute:2", "current:p2")
    rows = [plan(), bad]
    if damage == "missing": rows.pop()
    elif damage == "duplicate": rows.append(deepcopy(bad))
    elif damage == "foreign_source": bad["queries"][0]["passage_ids"] = ["current:p1"]
    elif damage == "foreign_owner": bad["dispute_id"] = "dispute:99"
    elif damage == "blank": bad["queries"][0]["text"] = "  "
    elif damage == "extra": bad["law_applies"] = True
    saved = prepare_queries(ExtractionModel({"plans": rows}), proposal, reviewed)
    assert saved["state"] == "partial" and list(saved["plans"]) == ["dispute:1"]
    assert validate_queries(saved, proposal, reviewed) == saved


def test_rejected_query_route_preserves_other_routes_for_that_same_dispute():
    proposal, reviewed = checked()
    row = plan()
    row["queries"] += [{"text": "Foreign", "purpose": "Invalid support", "passage_ids": ["foreign:p1"]}]
    saved = prepare_queries(ExtractionModel({"plans": [row]}), proposal, reviewed)
    assert saved["state"] == "partial"
    assert len(saved["plans"]["dispute:1"]["queries"]) == 1
    assert saved["issues"][0]["query_id"] == "dispute:1:q2"
    assert validate_queries(saved, proposal, reviewed) == saved


def test_over_budget_route_is_explicit_without_discarding_the_other_four():
    proposal, reviewed = checked()
    row = plan()
    row["queries"] *= 5
    saved = prepare_queries(ExtractionModel({"plans": [row]}), proposal, reviewed)
    assert len(saved["plans"]["dispute:1"]["queries"]) == 4
    assert saved["issues"][0]["query_id"] == "dispute:1:q5"


def test_empty_checked_extraction_needs_no_decomposition_call():
    proposal = prepared(message="Hello.")
    reviewed = release(proposal, proof(greeting=True))
    model = ExtractionModel()
    saved = prepare_queries(model, proposal, reviewed)
    assert saved["state"] == "ready" and saved["plans"] == {} and model.calls == []


@pytest.mark.parametrize("damage", ["source", "description", "query_owner", "gap", "version", "state"])
def test_saved_projection_or_source_drift_cannot_replay(damage):
    proposal, reviewed = checked()
    saved = prepare_queries(ExtractionModel({"plans": [plan()]}), proposal, reviewed)
    if damage == "source": proposal["sources"][-1]["message"]["text"] += " Changed."
    elif damage == "description": proposal["proposal"]["disputes"][0]["description"] = "Different account"
    elif damage == "query_owner": saved["plans"]["dispute:1"]["dispute_id"] = "dispute:2"
    elif damage == "gap": saved["issues"] = [{"dispute_id": "dispute:1", "reason": "False missing"}]
    elif damage == "version": saved["contract"] = "future"
    else: saved["state"] = "complete"
    with pytest.raises(SchemaViolation): validate_queries(saved, proposal, reviewed)


def test_full_context_overflow_and_incomplete_provider_output_are_not_empty_plans():
    proposal, reviewed = checked()
    model = ExtractionModel({"plans": [plan()]}, budget=1)
    with pytest.raises(ContextOverflow): prepare_queries(model, proposal, reviewed)
    assert model.calls == []
    with pytest.raises(ModelError):
        prepare_queries(ExtractionModel({"plans": [plan()]}, completion=Completion.LENGTH_LIMITED), proposal, reviewed)


def test_no_supported_dispute_is_researched_from_an_unchecked_writer_proposal():
    proposal = prepared(disputes=[item()], message="Summarise our discussion.")
    reviewed = release(proposal, proof(None, verdict(value="unsupported")))
    assert research_input(proposal, reviewed)["disputes"] == {}
