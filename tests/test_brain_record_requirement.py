"""Offline qualification of a draft declared outcome contract, not model meaning."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain import conversation as brain
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests import brain_continuation_fixture


class Model:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        return ModelResult(text=None, data=next(self.responses), tier=tier,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def requirement(kind="none", *, targets=(), operation="none", condition=""):
    return {"kind": kind, "target_ids": list(targets), "operation": operation,
            "success_condition": condition}


def item(message, *, record_requirement=None, purposes=(), intent="request",
         relation="continues", scope="current"):
    # This owning builder explicitly declares no requested record effect for
    # its ordinary scripts. Targeted cases supply their declared meaning.
    declared = requirement() if record_requirement is None else record_requirement
    return {"request": message, "relation": relation, "matter_scope": scope,
            "priority": "ordinary", "next_step": "answer", "reply": "The work is pending.",
            "clarification": "", "intent": intent,
            "response_basis": "conversation_record", "research_question": "",
            "response_mode": "substantive",
            "material_purposes": list(purposes), "record_requirement": declared}


def response(*items):
    return {"items": list(items), "opening": {
        "ready": False, "party_name": "", "subject": "", "summary": ""}}


def context(*, held=False):
    account = "The freight was delivered on 11 August."
    detail = {"id": "earlier:material:2", "statement": account,
              "source_turn_id": "earlier", "quoted": account,
              "matter_scope": "uncertain" if held else "current",
              "prior_references": [], "basis": "uncertain" if held else "stated"}
    dispute = {"id": "earlier:material:1", "statement": "Whether custody is disputed.",
               "label": "Custody", "source_turn_id": "earlier", "quoted": account,
               "matter_scope": "current"}
    return brain.Conversation((brain.Message("earlier", "advocate", account),),
                              current_matter_id="matter_owned",
                              open_disputes=(dispute,), open_material=(detail,))


def test_correction_is_declared_against_owned_material_and_full_target_catalogue():
    conversation = context()
    request = "Please correct the saved delivery date to 12 August."
    declared = requirement("change", targets=("earlier:material:2",), operation="corrects",
                           condition="The saved delivery date is 12 August.")
    model = Model(response(item(request, record_requirement=declared,
                                purposes=("account_contribution",))))

    plan = brain.interpret(model, conversation, request)

    assert plan.material_review is True
    assert plan.items[0].record_requirement == declared
    assert json.loads(json.dumps(vars(plan.items[0])))["record_requirement"] == declared
    assert len(model.calls) == 1
    prompt, schema = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload["earlier_conversation"][0]["text"] == conversation.messages[0].text
    assert payload["open_disputes"][0]["id"] == "earlier:material:1"
    assert [(row["id"], row["type"]) for row in payload["target_catalogue"]] == [
        ("earlier:material:1", "dispute"), ("earlier:material:2", "material")]
    assert payload["target_catalogue"][1]["record"] == {
        **conversation.open_material[0], "record_role": "nm_interpretation"}
    choices = schema["properties"]["items"]["items"]["properties"][
        "record_requirement"]["properties"]["target_ids"]["items"]["enum"]
    assert choices == ["earlier:material:1", "earlier:material:2"]


@pytest.mark.parametrize("targets", [(), ("earlier:material:1", "earlier:material:2")])
def test_review_can_check_existing_state_without_promising_a_change(targets):
    request = "Check your saved account against my original words."
    declared = requirement("review", targets=targets,
                           condition="The review establishes whether the account is faithful.")
    model = Model(response(item(request, record_requirement=declared,
                                purposes=("interpretation_review",))))

    plan = brain.interpret(model, context(), request)

    assert plan.items[0].record_requirement["kind"] == "review"
    assert plan.items[0].record_requirement["operation"] == "none"
    assert plan.items[0].record_requirement["target_ids"] == list(targets)
    assert plan.material_review is True and len(model.calls) == 1


def test_account_contribution_does_not_invent_a_requested_record_effect():
    request = "The reported delivery date is uncertain."
    model = Model(response(item(request, purposes=("account_contribution",),
                                intent="contribution")))

    plan = brain.interpret(model, context(), request)

    assert plan.material_review is True
    assert plan.items[0].record_requirement == requirement()
    assert plan.items[0].intent == "contribution"
    assert len(model.calls) == 1


def test_authorised_restoration_can_request_a_new_record_without_new_account_facts():
    request = "Restore the separately reported date that your account omitted."
    declared = requirement("change", operation="new",
                           condition="The omitted original date has a sourced representation.")
    model = Model(response(item(request, record_requirement=declared,
                                purposes=("interpretation_review",))))

    plan = brain.interpret(model, context(), request)

    assert plan.items[0].record_requirement["operation"] == "new"
    assert plan.items[0].record_requirement["target_ids"] == []
    assert plan.items[0].material_purposes == ("interpretation_review",)
    assert len(model.calls) == 1


def test_owned_held_reference_retains_uncertainty_without_admitting_matter_ownership():
    request = "Reconcile the receipt's unresolved matter association."
    declared = requirement("change", targets=("earlier:material:2",), operation="corrects",
                           condition="The checked association preserves unresolved ownership.")
    model = Model(response(item(request, record_requirement=declared,
                                purposes=("interpretation_review",))))

    plan = brain.interpret(model, context(held=True), request)

    assert plan.items[0].record_requirement["target_ids"] == ["earlier:material:2"]
    assert json.loads(model.calls[0][0].user)["target_catalogue"][1]["record"][
        "matter_scope"] == "uncertain"


@pytest.mark.parametrize("declared,purposes,fragment", [
    (requirement(targets=("earlier:material:2",)), (), "kind none"),
    (requirement(operation="new"), (), "kind none"),
    (requirement(condition="A substantive expected effect."), (), "kind none"),
    (requirement("review", operation="corrects", condition="Review."),
     ("interpretation_review",), "review requires operation none"),
    (requirement("review"), ("interpretation_review",), "nonempty success_condition"),
    (requirement("review", condition="Review."), (), "requires interpretation_review"),
    (requirement("change", operation="corrects", targets=("earlier:material:2",),
                 condition="Updated."), (), "change requires account_contribution"),
    (requirement("change", operation="corrects", condition="Updated."),
     ("interpretation_review",), "non-new change needs"),
    (requirement("change", operation="new", targets=("earlier:material:2",),
                 condition="Created."), ("account_contribution",), "new cannot target"),
    (requirement("change", targets=("earlier:material:2",), condition="Updated."),
     ("interpretation_review",), "change requires a supported operation"),
])
def test_consequential_requirement_conflicts_get_only_one_precise_correction(
        declared, purposes, fragment):
    request = "Carry out the requested sourced record work."
    bad = response(item(request, record_requirement=declared, purposes=purposes))
    model = Model(bad, bad)

    with pytest.raises(SchemaViolation, match=fragment):
        brain.interpret(model, context(), request)

    assert len(model.calls) == 2
    feedback = json.loads(model.calls[1][0].user)
    assert fragment in feedback["validation_issue"]
    assert feedback["original_input"]["earlier_conversation"][0]["text"] == (
        context().messages[0].text)


@pytest.mark.parametrize("fault", ["missing", "foreign", "unknown"])
def test_fresh_missing_or_unowned_requirement_is_repaired_explicitly(fault):
    request = "Check the saved date against the original account."
    valid = response(item(request, record_requirement=requirement(
        "review", targets=("earlier:material:2",), condition="Review the date's fidelity."),
        purposes=("interpretation_review",)))
    bad = deepcopy(valid)
    if fault == "missing":
        bad["items"][0].pop("record_requirement")
    elif fault == "foreign":
        bad["items"][0]["record_requirement"]["target_ids"] = ["foreign:material:7"]
    else:
        bad["items"][0]["record_requirement"]["kind"] = "silently_finished"
    model = Model(bad, valid)

    plan = brain.interpret(model, context(), request)

    assert len(model.calls) == 2
    assert plan.items[0].record_requirement["kind"] == "review"
    assert "record_requirement" in json.loads(model.calls[1][0].user)["validation_issue"]


def test_harmless_duplicate_targets_and_empty_inapplicable_whitespace_need_no_retry():
    request = "Check the saved date."
    first = item(request, record_requirement=requirement(
        "review", targets=("earlier:material:2", "earlier:material:2"), condition=" Check date. "),
        purposes=("interpretation_review",))
    second = item("Repeat the existing heading.",
                  record_requirement=requirement(condition=" \n\t "))
    model = Model(response(first, second))

    plan = brain.interpret(model, context(), request)

    assert len(model.calls) == 1
    assert plan.items[0].record_requirement["target_ids"] == ["earlier:material:2"]
    assert plan.items[0].record_requirement["success_condition"] == "Check date."
    assert plan.items[1].record_requirement["success_condition"] == ""


def test_legacy_inprocess_requirement_is_untracked_not_synthesised():
    old = brain.WorkItem("Existing work", "continues", "current", "ordinary", "answer")
    assert old.record_requirement is None


def test_new_record_requirement_has_no_target_choices_on_a_first_turn():
    request = "Record this separately reported handover date."
    declared = requirement("change", operation="new",
                           condition="The handover has its sourced record.")
    model = Model(response(item(request, record_requirement=declared,
                                purposes=("account_contribution",),
                                relation="new", scope="proposed")))

    plan = brain.interpret(model, brain.Conversation(()), request)

    assert plan.items[0].record_requirement["target_ids"] == []
    selections = model.calls[0][1]["properties"]["items"]["items"]["properties"][
        "record_requirement"]["properties"]["target_ids"]
    assert selections["maxItems"] == 0
    assert json.loads(model.calls[0][0].user)["target_catalogue"] == []


def test_conflicting_saved_target_identity_stops_before_model_dispatch():
    good = context()
    changed = {**good.open_material[0], "id": good.open_disputes[0]["id"]}
    damaged = brain.Conversation(good.messages, current_matter_id=good.current_matter_id,
                                 open_disputes=good.open_disputes, open_material=(changed,))
    model = Model()

    with pytest.raises(brain.IncompleteConversation, match="identities conflict"):
        brain.interpret(model, damaged, "Check the sourced record.")
    assert model.calls == []


def test_record_contract_does_not_allow_answer_to_bypass_legal_authority_route():
    requested = item("What legal remedy follows?")
    requested.update(response_basis="legal_authority", research_question="What remedies apply?")
    invalid = response(requested)
    model = Model(invalid, invalid)

    with pytest.raises(SchemaViolation, match="requires legal_work"):
        brain.interpret(model, context(), requested["request"])
    assert len(model.calls) == 2


def fixture_adapter():
    return brain_continuation_fixture


def test_central_fixture_adds_only_explicit_owner_supplied_non_effect_requirements():
    fixture = fixture_adapter()
    neutral = item("Repeat the reported location.")
    neutral.pop("record_requirement")
    targeted = item("Review the saved date.", record_requirement=requirement(
        "review", targets=("earlier:material:2",), condition="Check the original date."),
        purposes=("interpretation_review",))
    script = response(neutral, targeted)

    migrated = fixture.interpretation(script, record_requirements={
        0: fixture.no_record_requirement()})

    assert migrated["items"][0]["record_requirement"] == requirement()
    assert migrated["items"][1]["record_requirement"] == targeted["record_requirement"]
    assert "record_requirement" not in script["items"][0]


def test_central_fixture_leaves_a_missing_targeted_requirement_invalid():
    fixture = fixture_adapter()
    targeted = item("Correct the saved date.", purposes=("interpretation_review",))
    targeted.pop("record_requirement")

    scripted = fixture.interpretation(response(targeted))

    assert "record_requirement" not in scripted["items"][0]


def test_central_fixture_refuses_conflicting_owner_declarations():
    fixture = fixture_adapter()
    targeted = item("Review the saved date.", record_requirement=requirement(
        "review", condition="Check the date."), purposes=("interpretation_review",))

    with pytest.raises(ValueError, match="different record requirements"):
        fixture.interpretation(response(targeted), record_requirements={
            0: fixture.no_record_requirement()})


@pytest.mark.parametrize("scope", ["none", "other"])
def test_change_to_current_owned_target_cannot_use_unrelated_item_scope(scope):
    request = "Correct the saved delivery date to 12 August."
    declared = requirement("change", targets=("earlier:material:2",), operation="corrects",
                           condition="The saved delivery date is 12 August.")
    wrong = response(item(request, record_requirement=declared,
                          purposes=("account_contribution",), scope=scope))
    correct = response(item(request, record_requirement=declared,
                            purposes=("account_contribution",), scope="current"))
    model = Model(wrong, correct)

    plan = brain.interpret(model, context(), request)

    assert len(model.calls) == 2
    assert plan.items[0].matter_scope == "current"
    assert plan.items[0].record_requirement == declared
    feedback = json.loads(model.calls[1][0].user)
    assert "contradicts matter_scope" in feedback["validation_issue"]
    assert feedback["original_input"]["earlier_conversation"][0]["text"] == (
        context().messages[0].text)
