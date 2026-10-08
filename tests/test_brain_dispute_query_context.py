"""Context remains selectable without changing source ownership or old replay."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from nm.brain.dispute_queries import prepare_queries, validate_queries
from nm.shared.model_port import SchemaViolation
from tests.test_brain_disputes_objectives import ExtractionModel, item, selection
from tests.test_brain_dispute_queries import plan
from tests.test_disputes_objectives_release import prepared
from tests.test_disputes_objectives_passage_review import (
    release, meaning, proof, verdict, outside,
)

MESSAGE = ("The provider has excluded my client from the final assessment. "
           "It is a privately managed institution. "
           "The insurer has refused reimbursement. "
           "An intermediary completed the proposal.")


def context_outputs():
    """Controlled readers for the public-boundary regression, not semantic proof."""
    extraction = {"disputes": [
        item("Assessment exclusion", [selection(), selection("current:p2", "context")]),
        item("Insurance reimbursement refused", [selection("current:p3"),
                                                  selection("current:p4", "context")]),
    ], "objectives": []}
    review = proof({
        "current:p1": [meaning(context=["current:p2"], represented=["dispute:1"])],
        "current:p2": [outside("background")],
        "current:p3": [meaning(support=["current:p3"], context=["current:p4"],
                               represented=["dispute:2"])],
        "current:p4": [outside("background")],
    }, verdict(), verdict("dispute:2"))
    queries = {"plans": [plan(), plan("dispute:2", "current:p3")]}
    queries["plans"][0]["queries"][0] = {
        "text": "procedural protections in privately managed educational institutions",
        "purpose": "Examine the applicable institutional framework without assuming public status.",
        "passage_ids": ["current:p1", "current:p2"],
    }
    queries["plans"][1]["queries"][0] = {
        "text": "attribution of an insurance intermediary's proposal answers",
        "purpose": "Examine intermediary attribution in the reimbursement dispute.",
        "passage_ids": ["current:p3", "current:p4"],
    }
    return [{"label": "information"}, extraction, review, queries]


def checked_context():
    _, extraction, review, _ = context_outputs()
    proposal = prepared(message=MESSAGE, **extraction)
    reviewed = release(proposal, review)
    assert reviewed["state"] == "ready"
    return proposal, reviewed


def test_owned_context_is_selectable_and_role_preserved_in_one_call():
    proposal, reviewed = checked_context()
    model = ExtractionModel(context_outputs()[-1])
    saved = prepare_queries(model, proposal, reviewed)
    assert saved["state"] == "ready" and saved["issues"] == []
    assert saved["contract"] == "dispute_queries_v2"
    assert validate_queries(saved, proposal, reviewed) == saved
    assert len(model.calls) == 1
    prompt, schema, _, _ = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload["original_conversation"] == proposal["sources"]
    assert payload["disputes"][0]["support_passage_ids"] == ["current:p1"]
    assert payload["disputes"][0]["context_passage_ids"] == ["current:p2"]
    assert payload["disputes"][1]["context_passage_ids"] == ["current:p4"]
    choices = schema["properties"]["plans"]["items"]["properties"]["queries"]["items"]["properties"]["passage_ids"]["items"]["enum"]
    assert set(choices) == {"current:p1", "current:p2", "current:p3", "current:p4"}
    for identity, source in payload["original_passages"].items():
        assert "purpose" not in source  # purpose belongs to the dispute association
        original = next(row["message"]["text"] for row in proposal["sources"]
                        if row["id"] == source["source_id"])
        assert original[source["start"]:source["end"]].strip()


def test_context_only_query_can_explore_a_condition_of_a_supported_dispute():
    proposal, reviewed = checked_context()
    saved = prepare_queries(ExtractionModel({"plans": [plan(passage="current:p2"),
        plan("dispute:2", "current:p4")]}), proposal, reviewed)
    assert saved["state"] == "ready"
    assert validate_queries(saved, proposal, reviewed) == saved


@pytest.mark.parametrize("foreign", ["current:p3", "current:p4", "absent:p1"])
def test_another_disputes_context_does_not_authorise_a_query(foreign):
    proposal, reviewed = checked_context()
    data = context_outputs()[-1]
    data["plans"][0]["queries"].append({
        "text": "foreign inquiry", "purpose": "Not owned by this dispute", "passage_ids": [foreign]})
    saved = prepare_queries(ExtractionModel(data), proposal, reviewed)
    assert saved["state"] == "partial" and len(saved["plans"]) == 2
    assert len(saved["plans"]["dispute:1"]["queries"]) == 1
    assert len(saved["issues"]) == 1
    assert saved["issues"][0]["query_id"] == "dispute:1:q2"
    assert validate_queries(saved, proposal, reviewed) == saved


def test_nm_interpretation_stays_visible_but_is_not_an_original_query_anchor():
    history = [{"role": "advocate", "text": "The records remain with the custodian."},
               {"role": "nm", "text": "The custodian owns the records."}]
    proposal = prepared(message="Please correct that interpretation.", history=history,
        disputes=[item("Custodian has retained the records", [selection("history_1:p1"),
            selection("history_2:p1", "context"), selection("current:p1", "context")])])
    reviewed = release(proposal, proof({"current:p1": [meaning(support=["history_1:p1"],
        context=["history_2:p1", "current:p1"], represented=["dispute:1"])]}, verdict()))
    data = {"plans": [plan(passage="history_1:p1")]}
    data["plans"][0]["queries"].append({"text": "NM interpretation", "purpose": "Not original account",
        "passage_ids": ["history_2:p1"]})
    model = ExtractionModel(data)
    saved = prepare_queries(model, proposal, reviewed)
    payload = json.loads(model.calls[0][0].user)
    assert payload["original_conversation"] == proposal["sources"]
    assert payload["disputes"][0]["context_passage_ids"] == ["current:p1"]
    assert "history_2:p1" not in payload["original_passages"]
    assert saved["state"] == "partial" and len(saved["plans"]["dispute:1"]["queries"]) == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_same_passage_keeps_its_different_role_in_each_dispute(reverse):
    items = [item("Retained records"), item("Refused claim", [
        selection("current:p2"), selection("current:p1", "context")])]
    if reverse:
        items.reverse()
    owners = {row["description"]: f"dispute:{index}" for index, row in enumerate(items, 1)}
    proposal = prepared(message="The custodian retained my records. The insurer refused my claim without those records.",
        disputes=items)
    reviewed = release(proposal, proof({
        "current:p1": [meaning(represented=[owners["Retained records"]])],
        "current:p2": [meaning(support=["current:p2"], context=["current:p1"], represented=[owners["Refused claim"]])],
    }, verdict(), verdict("dispute:2")))
    model = ExtractionModel({"plans": [plan(), plan("dispute:2", "current:p1")]})
    saved = prepare_queries(model, proposal, reviewed)
    payload = json.loads(model.calls[0][0].user)
    associations = {row["description"]: row for row in payload["disputes"]}
    assert associations["Retained records"]["support_passage_ids"] == ["current:p1"]
    assert associations["Refused claim"]["context_passage_ids"] == ["current:p1"]
    assert "purpose" not in payload["original_passages"]["current:p1"]
    assert saved["state"] == "ready"


@pytest.mark.parametrize("reverse", [False, True])
def test_one_passage_can_support_and_qualify_the_same_dispute(reverse):
    selections = [selection(), selection("current:p1", "context")]
    if reverse:
        selections.reverse()
    proposal = prepared(message="The claim was refused because the records were missing.",
        disputes=[item("Claim refused", selections)])
    reviewed = release(proposal, proof({"current:p1": [meaning(context=["current:p1"],
        represented=["dispute:1"])]}, verdict()))
    model = ExtractionModel({"plans": [plan()]})
    saved = prepare_queries(model, proposal, reviewed)
    payload = json.loads(model.calls[0][0].user)
    assert payload["disputes"][0]["support_passage_ids"] == ["current:p1"]
    assert payload["disputes"][0]["context_passage_ids"] == ["current:p1"]
    assert saved["state"] == "ready"


def test_historical_projection_does_not_readmit_its_previously_rejected_context():
    fixture = json.loads((Path(__file__).parent/"fixtures/dispute_queries_v1_context.json").read_text(encoding="utf8"))
    saved = fixture["planning"]
    assert saved["contract"] == "dispute_queries_v1" and saved["state"] == "partial"
    assert validate_queries(saved, fixture["preparation"], fixture["release"]) == saved
    ready = fixture["ready_planning"]
    assert validate_queries(ready, fixture["preparation"], fixture["release"]) == ready
    changed = deepcopy(saved)
    changed["contract"] = "dispute_queries_v2"
    with pytest.raises(SchemaViolation):
        validate_queries(changed, fixture["preparation"], fixture["release"])


def test_saved_context_cannot_be_changed_and_unknown_versions_cannot_replay():
    proposal, reviewed = checked_context()
    saved = prepare_queries(ExtractionModel(context_outputs()[-1]), proposal, reviewed)
    damaged = deepcopy(saved)
    damaged["plans"]["dispute:1"]["queries"][0]["passage_ids"] = ["current:p1", "current:p4"]
    with pytest.raises(SchemaViolation):
        validate_queries(damaged, proposal, reviewed)
    damaged = deepcopy(saved)
    damaged["contract"] = "dispute_queries_v1"
    with pytest.raises(SchemaViolation):
        validate_queries(damaged, proposal, reviewed)
    damaged = deepcopy(saved)
    damaged["contract"] = "dispute_queries_v999"
    with pytest.raises(SchemaViolation):
        validate_queries(damaged, proposal, reviewed)
