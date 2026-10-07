"""Original-source scope interpretation contracts, without a real model call."""
from __future__ import annotations

import json
from collections import deque
from copy import deepcopy

import pytest

from nm.brain import conversation as brain
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests.brain_continuation_fixture import (
    prepare_interpretation,
    scripted_message_labels,
    transport_message_parts,
)


class Model:
    def __init__(self, *responses):
        self.responses = deque(responses)
        self.calls = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        payload = json.loads(prompt.user)
        original = payload.get("original_input", payload)
        data = (scripted_message_labels(self.responses[0], original)
                if prompt.operation == "label_message" else transport_message_parts(
                    prepare_interpretation(self.responses.popleft()), original))
        return ModelResult(text=None, data=data, tier=tier,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


ACCOUNT_A = "The first original account records the received value."
ACCOUNT_B = "The second original account describes who holds the record."


def context():
    return brain.Conversation(
        (brain.Message("earlier", "advocate", ACCOUNT_A + " " + ACCOUNT_B),
         brain.Message("earlier", "nm", "An NM interpretation with a derived value.")),
        current_matter_id="owned-matter", open_material=(
            {"id": "material-a", "statement": ACCOUNT_A, "quoted": ACCOUNT_A,
             "source_turn_id": "earlier", "matter_scope": "current"},
            {"id": "material-b", "statement": ACCOUNT_B, "quoted": ACCOUNT_B,
             "source_turn_id": "earlier", "matter_scope": "current"}))


def requirement(kind="none", *, targets=(), operation="none", condition=""):
    return {"kind": kind, "target_ids": list(targets), "operation": operation,
            "success_condition": condition}


def scope(*, kind="account_contribution", sources=("L1",), targets=("material-a",),
          mode="exact", relations=("corrects",)):
    return {"authority_kind": kind, "authority_source_ids": list(sources),
            "target_scope": mode, "target_ids": list(targets),
            "permitted_relations": list(relations)}


def item(words, *, scopes=(), purposes=(), declared=None, intent="contribution",
         matter_scope="current", relation="continues"):
    return {"request": words, "relation": relation, "matter_scope": matter_scope,
            "priority": "ordinary", "next_step": "answer",
            "reply": "The supplied account is noted.",
            "clarification": "", "intent": intent, "response_basis": "conversation_record",
            "research_question": "", "response_mode": "substantive",
            "material_purposes": list(purposes),
            "record_requirement": requirement() if declared is None else declared,
            "mutation_scopes": list(scopes)}


def response(*items):
    return {"message_parts": [{"category": "work_request", "selections": [
                {"source_id": "$message", "whole_source": True}]}],
            "items": list(items), "opening": {
        "ready": False, "party_name": "", "subject": "", "summary": ""}}


def interpret(words, *items, conversation=None):
    model = Model(response(*items))
    plan = brain.interpret(model, context() if conversation is None else conversation, words)
    assert len(model.calls) == 2
    return plan, model


def test_implicit_contribution_authorizes_correction_without_inventing_update_request():
    words = "The first reported value should instead be the revised one."
    grant = scope()
    plan, model = interpret(words, item(words, scopes=(grant,), purposes=("account_contribution",)))
    assert plan.items[0].intent == "contribution"
    assert plan.items[0].record_requirement == requirement()
    assert plan.items[0].mutation_scopes == (grant,)
    payload = json.loads(model.calls[1][0].user)
    assert payload["latest_message"] == words
    assert payload["earlier_conversation"][0]["text"] == ACCOUNT_A + " " + ACCOUNT_B
    assert payload["earlier_conversation"][1]["role"] == "nm"
    assert payload["mutation_source_catalogue"]["L1"]["quoted"] == words
    assert payload["mutation_source_catalogue"]["P1S1"]["quoted"] == ACCOUNT_A
    assert "P2S1" not in payload["mutation_source_catalogue"]


def test_repair_authority_can_reference_prior_original_support_without_a_new_fact():
    words = "Repair your account interpretation against what I originally reported."
    grant = scope(kind="interpretation_review", sources=("L1", "P1S1"))
    declared = requirement("change", targets=("material-a",), operation="corrects",
                           condition="The interpretation preserves the original attributed value.")
    plan, _ = interpret(words, item(
        words, scopes=(grant,), purposes=("interpretation_review",), declared=declared,
        intent="request"))
    assert plan.items[0].mutation_scopes[0]["authority_source_ids"] == ["L1", "P1S1"]


def test_selected_review_and_separate_contribution_preserve_both_target_scopes():
    review = "Review only your formulation of the first reported value."
    contribution = "The second account's reported custody has changed."
    words = review + " " + contribution
    first = scope(kind="interpretation_review")
    second = scope(sources=("L2",), targets=("material-b",))
    declared = requirement("review", targets=("material-a",), condition="Check the first account.")
    plan, _ = interpret(
        words,
        item(review, scopes=(first,), purposes=("interpretation_review",),
             declared=declared, intent="request"),
        item(contribution, scopes=(second,), purposes=("account_contribution",)))
    assert [entry.mutation_scopes[0]["target_ids"] for entry in plan.items] == [
        ["material-a"], ["material-b"]]


def test_mixed_item_can_keep_independent_contribution_outside_its_targeted_review():
    words = "Review the first account; the second account's custody has changed."
    grants = (scope(kind="interpretation_review"), scope(targets=("material-b",)))
    declared = requirement("review", targets=("material-a",), condition="Review the first account.")
    plan, _ = interpret(words, item(
        words, scopes=grants, purposes=("interpretation_review", "account_contribution"),
        declared=declared, intent="request"))
    assert len(plan.items[0].mutation_scopes) == 2


def test_explicit_whole_review_does_not_force_a_change():
    words = "Reconcile every saved formulation against my original account."
    grant = scope(kind="interpretation_review", mode="reviewed_whole", targets=(),
                  relations=("new", "adds", "corrects", "contradicts", "withdraws"))
    plan, _ = interpret(words, item(
        words, scopes=(grant,), purposes=("interpretation_review",), intent="request",
        declared=requirement("review", condition="Check the full account's representation.")))
    assert plan.items[0].mutation_scopes[0]["target_scope"] == "reviewed_whole"
    assert plan.items[0].record_requirement["kind"] == "review"


def test_no_change_review_and_existing_record_use_need_no_mutation_grants():
    review = "Check whether the first account is faithful; it may already be correct."
    plan, _ = interpret(review, item(
        review, purposes=("interpretation_review",), intent="request",
        declared=requirement("review", targets=("material-a",), condition="Check fidelity.")))
    assert plan.items[0].mutation_scopes == ()
    use = "Explain the current heading."
    ordinary, _ = interpret(use, item(use, intent="request"))
    assert ordinary.items[0].mutation_scopes == ()
    assert ordinary.material_review is False


def test_first_account_creation_has_only_original_sources_and_no_existing_targets():
    words = "The recipient retained the original record."
    grant = scope(targets=(), relations=("new",))
    plan, model = interpret(words, item(
        words, scopes=(grant,), purposes=("account_contribution",),
        matter_scope="proposed", relation="new"), conversation=brain.Conversation(()))
    assert plan.items[0].mutation_scopes == (grant,)
    for branch in model.calls[1][1]["properties"]["items"]["items"]["anyOf"]:
        scopes = branch["properties"]["mutation_scopes"]["items"]["anyOf"]
        for option in scopes:
            choices = option["properties"]
            assert choices["authority_source_ids"]["items"]["enum"] == ["L1"]
            assert choices["target_ids"]["maxItems"] == 0


def test_identical_scopes_and_repeated_references_are_harmless_without_retries():
    words = "Reconcile the same original account."
    grant = scope(sources=("P1S1", "L1", "L1"), targets=("material-a", "material-a"),
                  relations=("corrects", "corrects"))
    plan, _ = interpret(words, item(words, scopes=(grant, deepcopy(grant)),
                                   purposes=("account_contribution",)))
    assert plan.items[0].mutation_scopes == (scope(sources=("L1", "P1S1")),)


def test_fresh_missing_scope_list_gets_one_explicit_correction():
    words = "Explain the saved heading."
    good = response(item(words, intent="request"))
    bad = deepcopy(good)
    del bad["items"][0]["mutation_scopes"]
    model = Model(bad, good)
    plan = brain.interpret(model, context(), words)
    assert len(model.calls) == 3
    assert plan.items[0].mutation_scopes == ()
    assert "mutation_scopes" in json.loads(model.calls[2][0].user)["validation_issue"]


@pytest.mark.parametrize("fault,fragment", [
    ("foreign-source", "authority_source_ids"),
    ("nm-source", "authority_source_ids"),
    ("foreign-target", "target_ids"),
    ("unknown-relation", "permitted_relations"),
    ("missing-purpose", "material purpose"),
    ("whole-contribution", "reviewed_whole requires"),
    ("whole-explicit-target", "reviewed_whole requires"),
    ("empty-exact-revision", "owned targets"),
    ("earlier-only-authority", "current original"),
    ("other-matter", "another matter"),
    ("unknown-scope", "target_scope"),
    ("unknown-field", "undeclared properties"),
])
def test_consequential_scope_defects_get_one_precise_bounded_correction(fault, fragment):
    words = "Correct the first attributed account."
    grant = scope()
    candidate = item(words, scopes=(grant,), purposes=("account_contribution",))
    if fault == "foreign-source":
        grant["authority_source_ids"] = ["foreign"]
    elif fault == "nm-source":
        grant["authority_source_ids"] = ["P2S1"]
    elif fault == "foreign-target":
        grant["target_ids"] = ["foreign"]
    elif fault == "unknown-relation":
        grant["permitted_relations"] = ["invented"]
    elif fault == "missing-purpose":
        candidate["material_purposes"] = []
    elif fault == "whole-contribution":
        grant.update(target_scope="reviewed_whole", target_ids=[])
    elif fault == "whole-explicit-target":
        grant.update(authority_kind="interpretation_review", target_scope="reviewed_whole")
        candidate["material_purposes"] = ["interpretation_review"]
    elif fault == "empty-exact-revision":
        grant["target_ids"] = []
    elif fault == "earlier-only-authority":
        grant["authority_source_ids"] = ["P1S1"]
    elif fault == "other-matter":
        candidate["matter_scope"] = "other"
    elif fault == "unknown-scope":
        grant["target_scope"] = "arbitrary"
    else:
        grant["invented_permission"] = True
    bad = response(candidate)
    model = Model(bad, bad)
    generation_fragment = {
        "whole-contribution": "authority_kind",
        "whole-explicit-target": "target_ids' has too many items",
        "empty-exact-revision": "target_ids' has too few items",
    }.get(fault, fragment)
    if generation_fragment != fragment:
        # Fresh transport rejects these impossible choices before the semantic
        # constructor. Retain the original authority invariant assertion too.
        with pytest.raises(SchemaViolation, match=fragment):
            brain._turn_plan(prepare_interpretation(bad), context(), latest=words)
    with pytest.raises(SchemaViolation, match=generation_fragment):
        brain.interpret(model, context(), words)
    assert len(model.calls) == 3
    assert generation_fragment in json.loads(model.calls[2][0].user)["validation_issue"]


@pytest.mark.parametrize("mode,targets", [("exact", ("material-b",)), ("reviewed_whole", ())])
def test_selected_review_cannot_expand_to_another_record_or_whole_scope(mode, targets):
    words = "Review only the first original account's formulation."
    grant = scope(kind="interpretation_review", mode=mode, targets=targets)
    declared = requirement("review", targets=("material-a",), condition="Check the first account.")
    bad = response(item(words, scopes=(grant,), purposes=("interpretation_review",),
                        declared=declared, intent="request"))
    model = Model(bad, bad)
    with pytest.raises(SchemaViolation, match="targeted review"):
        brain.interpret(model, context(), words)


@pytest.mark.parametrize("grants", [(), (scope(targets=("material-b",)),),
                                   (scope(relations=("withdraws",)),)])
def test_requested_change_needs_a_scope_covering_its_own_target_and_relation(grants):
    words = "Correct the first original account."
    declared = requirement("change", targets=("material-a",), operation="corrects",
                           condition="The first account has the faithful value.")
    bad = response(item(words, scopes=grants, purposes=("account_contribution",),
                        declared=declared, intent="request"))
    with pytest.raises(SchemaViolation, match="relevant source-linked scope"):
        brain.interpret(Model(bad, bad), context(), words)


def test_old_inprocess_items_remain_explicitly_untracked():
    legacy = brain.WorkItem("Earlier work", "continues", "current", "ordinary", "answer")
    assert legacy.mutation_scopes is None


def test_original_transcript_and_purpose_remain_visible_in_correction_feedback():
    words = "Please repair your interpretation against the original account."
    bad = response(item(words, scopes=(scope(sources=("foreign",)),),
                        purposes=("account_contribution",)))
    good = response(item(words, scopes=(scope(),), purposes=("account_contribution",)))
    model = Model(bad, good)
    plan = brain.interpret(model, context(), words)
    original = json.loads(model.calls[2][0].user)["original_input"]
    assert original["latest_message"] == words
    assert original["earlier_conversation"][0]["text"] == ACCOUNT_A + " " + ACCOUNT_B
    assert original["earlier_conversation"][1]["text"] == context().messages[1].text
    assert plan.items[0].mutation_scopes[0]["target_ids"] == ["material-a"]
