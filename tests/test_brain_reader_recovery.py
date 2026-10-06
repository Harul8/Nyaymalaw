"""Candidate material/dispute handoffs through their actual owner acceptance."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain.turn import Message
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage

LATEST = "The report describes a conditional handover. A separate receipt remains unverified."


@pytest.fixture
def readers():
    from nm.brain import disputes, material
    return material, disputes


class Model:
    def __init__(self, outputs, *, recovery_allowed=True):
        self.outputs, self.calls = deepcopy(outputs), []
        self.recovery_allowed, self.reservations = recovery_allowed, []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def claim_recovery(self, phase):
        self.reservations.append(phase)
        return self.recovery_allowed

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        index = len(self.calls)
        assert index < len(self.outputs)
        self.calls.append({"input": json.loads(prompt.user), "schema": deepcopy(schema),
                           "operation": prompt.operation})
        return ModelResult(None, deepcopy(self.outputs[index]), tier,
                           "offline", "fabricated-reader-handoff", Usage(5, 5, 0), 0,
                           completion=Completion.COMPLETE)


def detail(source="L1", statement="The described handover remains conditional."):
    return {"kind": "event", "statement": statement, "source_id": source,
            "basis": "stated", "importance": "relevant",
            "why_material": "The conditions affect the reported chronology.",
            "assignment_ids": ["matter:discussion"]}


def dispute(source="L1", statement="What conditions govern the described handover?"):
    return {"statement": statement, "source_id": source,
            "basis": "stated", "importance": "relevant",
            "why_material": "The described conditions affect an independent disputed obligation.",
            "matter_scope": "proposed", "label": "Conditions governing reported handover",
            "identification": "identified", "clarification": ""}


def envelope(rows):
    return {"new_items": rows, "changes": []}


@pytest.mark.parametrize("activity", ["material"])
def test_readers_preserve_owned_peer_during_keyed_repair(readers, activity):
    material, disputes = readers
    if activity == "material":
        extract, factory = material.extract_details, detail
    else:
        extract, factory = disputes.extract_disputes, dispute
    model, diagnostics = Model([
        envelope([factory(), factory("L2", " ")]),
        {"repairs": {"new_items:2": {"proposals": [
            factory("L2", "The separate receipt is unverified.")]}}},
    ]), {}
    results = extract(model, earlier=(), latest=LATEST, current_matter_id=None,
                      diagnostics=diagnostics)
    assert len(results) == 2 and results[0].quoted == "The report describes a conditional handover."
    assert results[1].quoted == "A separate receipt remains unverified."
    assert diagnostics["state"] == "returned" and len(model.calls) == 2
    assert model.calls[1]["schema"]["properties"]["repairs"]["required"] == ["new_items:2"]


@pytest.mark.parametrize("activity", ["material"])
def test_readers_keep_peer_and_unread_when_shared_budget_exhausted(readers, activity):
    material, disputes = readers
    extract, factory = (material.extract_details, detail) if activity == "material" else (
        disputes.extract_disputes, dispute)
    model, diagnostics = Model([envelope([factory(), factory("L2", " ")])],
                               recovery_allowed=False), {}
    assert len(extract(model, earlier=(), latest=LATEST, current_matter_id=None,
                       diagnostics=diagnostics)) == 1
    assert diagnostics["state"] == "partial" and diagnostics["recovery_exhausted"]
    assert len(model.calls) == 1


@pytest.mark.parametrize("activity", ["material"])
def test_readers_pass_typed_missing_source_context_without_new_prompt_variant(readers, activity):
    material, disputes = readers
    extract = material.extract_details if activity == "material" else disputes.extract_disputes
    model = Model([envelope([])])
    scope = {"review_scope": {}, "missing_source_ids": ["L2", "L2"],
             "retained_proposals": [], "reason": "The second original passage remains unassessed."}
    before = deepcopy(scope)
    assert extract(model, earlier=(), latest=LATEST, current_matter_id=None,
                   recovery_scope=scope) == ()
    supplied = model.calls[0]["input"]["recovery_scope"]
    assert supplied["missing_source_ids"] == ["L2"] and scope == before
    assert "conditional handover" in json.dumps(model.calls[0]["input"])
    assert model.reservations == []  # The turn owner reserves the semantic recovery call.


@pytest.mark.parametrize("identity", ["UNKNOWN", "P2S1"])
def test_recovery_input_cannot_promote_foreign_or_nm_source_ownership(readers, identity):
    material, _ = readers
    earlier = (Message("earlier", "advocate", "The prior account remains tentative."),
               Message("earlier", "nm", "I inferred unconditional performance."))
    scope = {"review_scope": {}, "missing_source_ids": [identity],
             "retained_proposals": [], "reason": "An account distinction remains unresolved."}
    model = Model([])
    with pytest.raises(SchemaViolation, match="owned original advocate source"):
        material.extract_details(model, earlier=earlier, latest=LATEST,
                                 current_matter_id=None, recovery_scope=scope)
    assert model.calls == []


def test_recovery_input_accepts_original_prior_advocate_for_authorized_repair(readers):
    material, _ = readers
    earlier = (Message("earlier", "advocate", "The prior account remains tentative."),
               Message("earlier", "nm", "I inferred unconditional performance."))
    scope = {"review_scope": {}, "missing_source_ids": ["P1S1"],
             "retained_proposals": [], "reason": "The prior original account must be considered."}
    model = Model([envelope([])])
    material.extract_details(model, earlier=earlier, latest=LATEST,
                             current_matter_id=None, recovery_scope=scope)
    assert model.calls[0]["input"]["recovery_scope"]["missing_source_ids"] == ["P1S1"]
    original = model.calls[0]["input"]["earlier_conversation"][0]["source_spans"][0]["text"]
    assert original == earlier[0].text


@pytest.mark.parametrize("modify", [
    lambda scope: scope.update(missing_source_ids=[]),
    lambda scope: scope.update(reason=" "),
    lambda scope: scope.update(review_scope=[]),
    lambda scope: scope.update(retained_proposals="invented"),
    lambda scope: scope.update(completed=True),
])
def test_ambiguous_recovery_context_is_rejected_before_dispatch(readers, modify):
    material, _ = readers
    scope = {"review_scope": {}, "missing_source_ids": ["L1"],
             "retained_proposals": [], "reason": "An original passage remains unassessed."}
    modify(scope)
    model = Model([])
    with pytest.raises(SchemaViolation):
        material.extract_details(model, earlier=(), latest=LATEST,
                                 current_matter_id=None, recovery_scope=scope)
    assert model.calls == []


def test_retained_proposals_are_exact_attributed_derived_context(readers):
    material, _ = readers
    earlier = (Message("earlier", "advocate", "The prior account remains tentative."),)
    retained = {"statement": "A checked provisional statement.",
                "quoted": "The report describes a conditional handover.",
                "prior_references": [{"turn_id": "earlier", "role": "advocate",
                                      "quoted": earlier[0].text}]}
    scope = {"review_scope": {}, "missing_source_ids": ["L2"],
             "retained_proposals": [retained], "reason": "The second passage needs examination."}
    model = Model([envelope([])])
    material.extract_details(model, earlier=earlier, latest=LATEST,
                             current_matter_id=None, recovery_scope=scope)
    context = model.calls[0]["input"]["recovery_scope"]["retained_proposals"][0]
    assert context["record_role"] == "nm_interpretation"
    assert "record_role" not in retained


@pytest.mark.parametrize("retained", [
    {"quoted": "Words absent from the original message."},
    {"quoted": "The report describes a conditional handover.",
     "prior_references": [{"turn_id": "foreign", "role": "advocate", "quoted": "Invented."}]},
    {"quoted": "The report describes a conditional handover.",
     "prior_references": [{"turn_id": [], "role": "advocate", "quoted": "Invalid."}]},
])
def test_unowned_retained_context_cannot_enter_recovery_prompt(readers, retained):
    material, _ = readers
    scope = {"review_scope": {}, "missing_source_ids": ["L2"],
             "retained_proposals": [retained], "reason": "The second passage needs examination."}
    model = Model([])
    with pytest.raises(SchemaViolation):
        material.extract_details(model, earlier=(), latest=LATEST,
                                 current_matter_id=None, recovery_scope=scope)
    assert model.calls == []
