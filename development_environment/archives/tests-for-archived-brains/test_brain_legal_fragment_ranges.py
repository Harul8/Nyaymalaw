"""Owned source ranges preserve boundary-spanning evidence without overlap duplication."""

import json
import re
from copy import deepcopy

import pytest

from nm.brain.legal_requirements import finding_verification_valid, source_verification_valid
from nm.shared.model_port import Tier
from tests.test_brain_legal_requirements import (
    CONVERSATION,
    REQUEST_SUBJECT,
    Model,
    call_budget,
    finding,
    supported_verdict,
    verify_findings,
)

PREDICATE = (
    "If the agreement expressly requires notice by the identified recipient before the agreed "
    "deadline, and no permitted exception or withdrawal applies, the recipient must receive "
    "written notice in that period."
)
assert len(PREDICATE) > 140
PREFIX = "This section records the ordinary interpretation of notice terminology. ".ljust(550)
PASSAGE = (
    PREFIX
    + PREDICATE
    + " The actual agreement, relevant act, recipient and period remain essential to application."
)
assert 700 < len(PASSAGE) < 1260


def _case(*, selection="f1:f2", short=False):
    text = PREDICATE if short else PASSAGE
    source = {
        "id": "s1",
        "kind": "provision",
        "title": "Notice Conditions Act",
        "locator": "section 1",
        "text": text,
    }
    condition = (
        "If those agreement, recipient, deadline and exception predicates hold, check receipt: "
        + PREDICATE
    )
    proposal = {**finding("condition", need=condition), "sources": [source]}
    decision = supported_verdict("r1", "s1")
    decision["source_checks"][0].update(
        assertion_owner="legislative_text",
        assertion_role="legislative_text",
        assertion_statement=PREDICATE,
        owner_label="Notice Conditions Act",
        source_treatment="adopted",
        support_fragment_id=selection,
        owner_fragment_id=selection,
        treatment_fragment_id=selection,
        scope_fragment_id=selection,
        scope_status="conditional",
        context_statements=[],
    )
    decision["application_premises"] = [
        {
            "source_id": "s1",
            "predicate_fragment_id": selection,
            "status": "unresolved",
            "account_source_ids": [],
            "preserved_condition": condition,
            "reason": (
                "The complete recipient, deadline and exception predicates remain unresolved."
            ),
        }
    ]
    return proposal, decision


def _review(model, proposal):
    return verify_findings(
        model,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        proposed={"q1": [proposal]},
        conversation=CONVERSATION,
    )


def test_boundary_spanning_predicate_has_one_exact_owned_range_without_duplicate_overlap():
    proposal, decision = _case()
    untouched = deepcopy(proposal)
    model = Model([{"decisions": [decision]}])
    result = _review(model, proposal)
    assert len(model.calls) == 1 and model.calls[0][2] is Tier.JUDGE
    row = result.rows["q1"][0]
    source = row["sources"][0]
    verified = source["verification"]
    payload = json.loads(model.calls[0][0].user)
    spans = payload["subjects"][0]["candidates"][0]["sources"][0]["fragments"]
    assert [(p["id"], p["start"], p["end"]) for p in spans] == [
        ("f1", 0, 700),
        ("f2", 560, len(PASSAGE)),
    ]
    assert all(PREDICATE not in span["text"] for span in spans)
    assert all(span["text"] == PASSAGE[span["start"] : span["end"]] for span in spans)
    for field in ("support_excerpt", "owner_excerpt", "treatment_excerpt", "scope_excerpt"):
        assert verified[field] == PASSAGE and PREDICATE in verified[field]
        assert len(verified[field]) < sum(len(span["text"]) for span in spans)
    premise = row["use_verification"]["application_premises"][0]
    assert premise["predicate_excerpt"] == PASSAGE
    assert premise["preserved_condition"] == proposal["need"]
    assert source["text"] == PASSAGE and proposal == untouched
    assert source_verification_valid(source) and finding_verification_valid(row)
    assert result.coverage["q1"]["unread_items"] == 0
    assert call_budget(model.calls[0]) <= model.budget and 0 < model.calls[0][3] <= 12288
    fields = model.calls[0][1]["properties"]["decisions"]["items"]["properties"]
    for key in (
        "support_fragment_id",
        "scope_fragment_id",
        "owner_fragment_id",
        "treatment_fragment_id",
    ):
        spec = fields["source_checks"]["items"]["properties"][key]
        assert "enum" not in spec and re.fullmatch(spec["pattern"], "f1:f2")
    spec = fields["application_premises"]["items"]["properties"]["predicate_fragment_id"]
    assert re.fullmatch(spec["pattern"], "f1:f2")


@pytest.mark.parametrize("selection", ["f1", "f1:f1"])
def test_single_fragment_and_same_endpoint_range_keep_existing_exact_source_use(selection):
    proposal, decision = _case(selection=selection, short=True)
    model = Model([{"decisions": [decision]}])
    result = _review(model, proposal)
    assert len(model.calls) == 1
    assert result.rows["q1"][0]["sources"][0]["verification"]["scope_excerpt"] == PREDICATE
    assert finding_verification_valid(result.rows["q1"][0])


@pytest.mark.parametrize("selection", ["f1:f3", "f2:f1", "f1:foreign", "f1::f2", "f01:f2"])
@pytest.mark.parametrize(
    "field",
    [
        "support_fragment_id",
        "scope_fragment_id",
        "owner_fragment_id",
        "treatment_fragment_id",
        "predicate_fragment_id",
    ],
)
def test_nonmatching_foreign_or_reverse_owned_range_stays_unread_after_one_correction(
    selection, field
):
    proposal, decision = _case()
    if field == "predicate_fragment_id":
        decision["application_premises"][0][field] = selection
    else:
        decision["source_checks"][0][field] = selection
    model = Model([{"decisions": [decision]}, {"decisions": [deepcopy(decision)]}])
    result = _review(model, proposal)
    assert len(model.calls) == 2
    assert result.rows["q1"] == [] and result.coverage["q1"]["unread_items"] == 1


def test_foreign_sources_available_endpoint_cannot_be_borrowed_by_short_owned_source():
    proposal, decision = _case(selection="f1:f2", short=True)
    other_source = {
        "id": "s2",
        "kind": "judgment",
        "title": "Different source",
        "locator": "paragraph 2",
        "text": "Unrelated background. " * 80,
    }
    peer = {**finding("adverse", source_ids=["s2"]), "sources": [other_source]}
    rejected = supported_verdict("r2", "s2")
    rejected.update(
        verdict="unsupported",
        label_verdict="unsupported",
        reason="The supplied background supports no operative notice proposition.",
    )
    rejected["source_checks"] = []
    rejected["application_premises"] = []
    model = Model([{"decisions": [decision, rejected]}, {"decisions": [deepcopy(decision)]}])
    result = verify_findings(
        model,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        proposed={"q1": [proposal, peer]},
        conversation=CONVERSATION,
    )
    assert len(model.calls) == 2 and result.rows["q1"] == []
    assert (
        result.coverage["q1"]["unread_items"] == 1 and result.coverage["q1"]["withheld_items"] == 1
    )
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["subjects"][0]["candidates"]] == ["r1"]


def test_range_cannot_skip_complete_original_evidence_to_fit_actual_context_budget():
    proposal, decision = _case()
    model = Model([{"decisions": [decision]}], budget=1)
    result = _review(model, proposal)
    assert model.calls == [] and result.rows["q1"] == []
    assert result.coverage["q1"]["unread_items"] == 1
