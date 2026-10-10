"""Requested delivery is source-bound interpretation, not completion evidence.

These independently authored offline declarations exercise the fresh producer
and its bounded correction. They do not evaluate interpretation quality, legal
applicability, useful public delivery or execution of the declared outcomes.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain import conversation as brain
from nm.brain.legal_requirements import RESEARCH_KINDS
from nm.brain.material import addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage

ACCOUNT = "The advocate reports that the signed inventory remains with the custodian"
PROMISE = "I will compare the original inventory account with the governing legal conditions"
TARGET = "original:material:1"
RESULT_TYPES = (
    "conversation", "dispute", "material", "checked_legal", "fixed_response", "record_result")
OUTCOME_FIELDS = {
    "request_source_ids", "scope_source_ids", "target_ids", "required_result_types",
    "legal_kinds", "success_condition"}


class Model:
    """Return authored wire objects without filling any declaration or reference."""

    def __init__(self, *replies):
        self.replies = iter(replies)
        self.last_reply = deepcopy(replies[-1])
        self.calls = []
        self.recovery_claims = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def claim_recovery(self, phase):
        self.recovery_claims.append(phase)
        return True

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, deepcopy(schema)))
        # A still-invalid correction repeats the authored object; it does not
        # obscure the owning rejection with a fixture StopIteration error.
        data = next(self.replies, self.last_reply)
        return ModelResult(
            text=None, data=deepcopy(data), tier=tier,
            provider="offline", model="offline", usage=Usage(0, 0, 0),
            latency_ms=0, completion=Completion.COMPLETE)


def context(*, promise=True):
    messages = [brain.Message("original", "advocate", ACCOUNT)]
    if promise:
        messages.append(brain.Message("original", "nm", PROMISE))
    return brain.Conversation(
        tuple(messages), current_matter_id="owned-matter", open_material=({
            "id": TARGET, "statement": ACCOUNT, "quoted": ACCOUNT,
            "source_turn_id": "original", "matter_scope": "current",
        },))


def record_requirement(kind="none", *, targets=(), operation="none", condition=""):
    return {"kind": kind, "target_ids": list(targets), "operation": operation,
            "success_condition": condition}


def outcome(*, requests=("L1",), sources=("L1",), targets=(),
            results=("conversation",), legal=(), condition="Explain the requested account."):
    return {
        "request_source_ids": list(requests), "scope_source_ids": list(sources),
        "target_ids": list(targets), "required_result_types": list(results),
        "legal_kinds": list(legal), "success_condition": condition,
    }


def item(words, *, outcomes=None, intent="request", purposes=(), requirement=None,
         scopes=(), legal=False, matter_scope="current", relation="continues",
         response_mode="substantive"):
    return {
        "request": words, "relation": relation, "matter_scope": matter_scope,
        "priority": "ordinary", "next_step": "legal_work" if legal else "answer",
        "intent": intent, "response_basis": "legal_authority" if legal
        else "conversation_record", "research_question": words if legal else "",
        "material_purposes": list(purposes), "mutation_scopes": list(scopes),
        "record_requirement": record_requirement() if requirement is None else requirement,
        "response_mode": response_mode,
        "delivery_requirement": {"outcomes": [outcome()] if outcomes is None
                                 else deepcopy(outcomes)},
    }


def response(*items):
    return {"items": list(items), "opening": {
        "ready": False, "party_name": "", "subject": "", "summary": ""}}


def assert_owned_delivery(work, proposed):
    declared = work.delivery_requirement
    assert declared["contract"] == "requested_delivery_v1"
    assert set(declared) == {"contract", "outcomes"}
    assert len(declared["outcomes"]) == len(proposed)
    identities = []
    for actual, expected in zip(declared["outcomes"], proposed, strict=True):
        assert set(actual) == OUTCOME_FIELDS | {"id"}
        assert isinstance(actual["id"], str) and actual["id"].strip()
        identities.append(actual["id"])
        assert {key: actual[key] for key in OUTCOME_FIELDS} == expected
    assert len(identities) == len(set(identities))
    return identities


@pytest.mark.parametrize("name,words,selection,legal", [
    ("greeting", "Hello", outcome(results=("fixed_response",),
                                    condition="Acknowledge the greeting."), False),
    ("recap", "Recap what I reported", outcome(sources=("L1", "P1S1"),
                                             condition="Recap the attributed account."), False),
    ("current_material", "Explain the current inventory record", outcome(
        sources=("L1", "P1S1"), targets=(TARGET,), results=("material",),
        condition="Explain the current sourced inventory record."), False),
    ("general_law", "What conditions limit the rule in general", outcome(
        results=("checked_legal",), legal=("principle", "condition"),
        condition="Explain the rule and its applicability conditions."), True),
])
def test_supported_delivery_neighbors_need_one_interpretation(name, words, selection, legal):
    conversation = brain.Conversation(()) if name in ("greeting", "general_law") else context()
    data = response(item(
        words, outcomes=[selection], legal=legal,
        matter_scope="none" if not conversation.current_matter_id else "current",
        relation="new" if not conversation.messages else "continues"))
    original = deepcopy(data)
    model = Model(data)

    plan = brain.interpret(model, conversation, words)

    assert_owned_delivery(plan.items[0], [selection])
    assert len(model.calls) == 1 and model.recovery_claims == []
    assert data == original
    assert plan.material_review is False
    if name == "general_law":
        assert conversation.open_disputes == ()
        assert plan.items[0].research_question == words


@pytest.mark.parametrize("kind", RESEARCH_KINDS)
def test_checked_legal_accepts_each_existing_research_kind_without_requiring_a_dispute(kind):
    words = "Explain the governing rule and its relevant limits"
    selection = outcome(results=("checked_legal",), legal=(kind,),
                        condition="Give the requested checked legal result with its limits.")
    model = Model(response(item(words, outcomes=[selection], legal=True,
                                matter_scope="none", relation="new")))

    plan = brain.interpret(model, brain.Conversation(()), words)

    assert_owned_delivery(plan.items[0], [selection])
    assert len(model.calls) == 1


@pytest.mark.parametrize("kind", ["review", "change"])
def test_already_correct_record_and_no_change_review_keep_explicit_requested_delivery(kind):
    words = "Check the inventory wording against my original account"
    declared = record_requirement(
        kind, targets=(TARGET,), operation="none" if kind == "review" else "corrects",
        condition="The inventory wording faithfully preserves the original account.")
    scopes = [] if kind == "review" else [{
        "authority_kind": "interpretation_review", "authority_source_ids": ["L1"],
        "target_scope": "exact", "target_ids": [TARGET], "permitted_relations": ["corrects"],
    }]
    selection = outcome(sources=("L1", "P1S1"), targets=(TARGET,),
                        results=("record_result",), condition=declared["success_condition"])
    model = Model(response(item(words, outcomes=[selection], purposes=("interpretation_review",),
                                requirement=declared, scopes=scopes,
                                response_mode="record_acknowledgement")))

    plan = brain.interpret(model, context(), words)

    assert_owned_delivery(plan.items[0], [selection])
    assert plan.items[0].record_requirement == declared
    assert len(model.calls) == 1


def test_mixed_request_preserves_two_outcomes_without_collapsing_record_and_legal_work():
    words = "Review the inventory wording. Explain the legal conditions separately."
    _, latest, _ = addressed_sources(context().messages, words)
    assert set(latest) == {"L1", "L2"}
    selections = [
        outcome(sources=("L1", "P1S1"), targets=(TARGET,), results=("record_result",),
                condition="Review the inventory wording against the original account."),
        outcome(requests=("L2",), sources=("L2", "P1S1"), results=("checked_legal",),
                legal=("principle", "condition"),
                condition="Explain the applicable legal rule and its limiting conditions."),
    ]
    declared = record_requirement("review", targets=(TARGET,),
                                  condition=selections[0]["success_condition"])
    model = Model(response(item(words, outcomes=selections, legal=True,
                                purposes=("interpretation_review",), requirement=declared)))

    plan = brain.interpret(model, context(), words)

    assert len(plan.items) == 1
    identities = assert_owned_delivery(plan.items[0], selections)
    assert len(identities) == 2 and len(model.calls) == 1


def test_prior_nm_promise_is_context_only_while_latest_advocate_owns_the_request():
    words = "Please finish the comparison you promised"
    selection = outcome(requests=("L1", "P1S1"), sources=("L1", "P1S1", "P2S1"),
                        results=("checked_legal",), legal=("principle", "condition"),
                        condition="Finish the requested comparison with checked legal limits.")
    model = Model(response(item(words, outcomes=[selection], legal=True)))

    plan = brain.interpret(model, context(), words)

    assert_owned_delivery(plan.items[0], [selection])
    payload = json.loads(model.calls[0][0].user)
    assert "P2S1" not in payload["mutation_source_catalogue"]
    assert plan.items[0].mutation_scopes == ()


def test_fresh_unrequested_contribution_may_explicitly_declare_no_delivery_outcomes():
    words = "The inventory remains with the custodian"
    model = Model(response(item(words, outcomes=[], intent="contribution",
                                purposes=("account_contribution",))))

    plan = brain.interpret(model, context(), words)

    assert_owned_delivery(plan.items[0], [])
    assert len(model.calls) == 1


def test_only_older_in_process_work_items_may_leave_delivery_untracked():
    work = brain.WorkItem(request="Older in-process request", relation="new", matter_scope="none",
                          priority="ordinary", next_step="answer")
    assert work.delivery_requirement is None


@pytest.mark.parametrize("fault", [
    "missing", "null", "empty_requested", "unknown_request_source", "nm_request_source",
    "latest_request_missing", "unknown_scope_source", "foreign_target", "empty_scope",
    "empty_result_types", "unknown_result_type", "unknown_legal_kind",
    "legal_kinds_without_checked_legal", "blank_condition", "forged_contract", "forged_id",
])
def test_faulty_delivery_gets_one_owned_correction_without_changing_valid_input(fault):
    words = "Explain the current inventory account"
    selection = outcome(sources=("L1", "P1S1"), targets=(TARGET,), results=("material",))
    valid = response(item(words, outcomes=[selection]))
    bad = deepcopy(valid)
    declaration = bad["items"][0]["delivery_requirement"]
    selected = declaration["outcomes"][0]
    if fault == "missing":
        del bad["items"][0]["delivery_requirement"]
    elif fault == "null":
        bad["items"][0]["delivery_requirement"] = None
    elif fault == "empty_requested":
        declaration["outcomes"] = []
    elif fault == "unknown_request_source":
        selected["request_source_ids"] = ["foreign:L1"]
    elif fault == "nm_request_source":
        selected["request_source_ids"] = ["L1", "P2S1"]
    elif fault == "latest_request_missing":
        selected["request_source_ids"] = ["P1S1"]
    elif fault == "unknown_scope_source":
        selected["scope_source_ids"] = ["foreign:P1S1"]
    elif fault == "foreign_target":
        selected["target_ids"] = ["another-matter:material:1"]
    elif fault == "empty_scope":
        selected["scope_source_ids"] = []
    elif fault == "empty_result_types":
        selected["required_result_types"] = []
    elif fault == "unknown_result_type":
        selected["required_result_types"] = ["provider_completed"]
    elif fault == "unknown_legal_kind":
        selected["required_result_types"] = ["checked_legal"]
        selected["legal_kinds"] = ["party_won"]
    elif fault == "legal_kinds_without_checked_legal":
        selected["legal_kinds"] = ["principle"]
    elif fault == "blank_condition":
        selected["success_condition"] = " \t "
    elif fault == "forged_contract":
        declaration["contract"] = "requested_delivery_v1"
    else:
        selected["id"] = "another-owner:outcome:1"
    before = deepcopy(bad)
    model = Model(bad, valid)

    plan = brain.interpret(model, context(), words)

    assert_owned_delivery(plan.items[0], [selection])
    assert len(model.calls) == 2
    assert model.recovery_claims == ["interpret_conversation:correction"]
    feedback = json.loads(model.calls[1][0].user)
    assert "delivery_requirement" in feedback["validation_issue"]
    assert feedback["rejected_output"] == before
    assert model.calls[0][1] == model.calls[1][1]
    assert bad == before


def test_requested_record_change_requires_delivery_even_when_item_is_a_contribution():
    words = "The original inventory has now been returned"
    declared = record_requirement("change", operation="new",
                                  condition="The new attributed inventory account is represented.")
    grant = {"authority_kind": "account_contribution", "authority_source_ids": ["L1"],
             "target_scope": "exact", "target_ids": [], "permitted_relations": ["new"]}
    selection = outcome(results=("record_result",), condition=declared["success_condition"])
    valid = response(item(words, intent="contribution", purposes=("account_contribution",),
                          requirement=declared, scopes=(grant,), outcomes=[selection]))
    bad = deepcopy(valid)
    bad["items"][0]["delivery_requirement"]["outcomes"] = []
    model = Model(bad, valid)

    plan = brain.interpret(model, context(), words)

    assert_owned_delivery(plan.items[0], valid["items"][0]["delivery_requirement"]["outcomes"])
    assert len(model.calls) == 2
    assert "delivery_requirement" in json.loads(model.calls[1][0].user)["validation_issue"]


def test_fresh_plan_admission_cannot_bypass_missing_delivery_validation():
    words = "Explain the inventory account"
    data = response(item(words))
    del data["items"][0]["delivery_requirement"]
    with pytest.raises(SchemaViolation, match="delivery_requirement"):
        brain._turn_plan(data, context(), latest=words)


def test_wire_offers_owned_selector_choices_and_excludes_server_identity_fields():
    words = "Explain what the earlier comparison was meant to cover"
    selection = outcome(sources=("L1", "P1S1", "P2S1"), targets=(TARGET,))
    model = Model(response(item(words, outcomes=[selection])))

    brain.interpret(model, context(), words)

    item_schema = model.calls[0][1]["properties"]["items"]["items"]
    assert "delivery_requirement" in item_schema["required"]
    declared = item_schema["properties"]["delivery_requirement"]
    assert set(declared["properties"]) == {"outcomes"}
    assert declared["additionalProperties"] is False
    selected = declared["properties"]["outcomes"]["items"]
    assert set(selected["properties"]) == set(selected["required"]) == OUTCOME_FIELDS
    assert selected["additionalProperties"] is False
    properties = selected["properties"]
    assert set(properties["request_source_ids"]["items"]["enum"]) == {"L1", "P1S1"}
    assert set(properties["scope_source_ids"]["items"]["enum"]) == {"L1", "P1S1", "P2S1"}
    assert properties["target_ids"]["items"]["enum"] == [TARGET]
    assert set(properties["required_result_types"]["items"]["enum"]) == set(RESULT_TYPES)
    assert set(properties["legal_kinds"]["items"]["enum"]) == set(RESEARCH_KINDS)


def test_prompt_preserves_full_original_history_without_new_delivery_word_copies():
    words = "Finish the promised comparison"
    selection = outcome(sources=("L1", "P1S1", "P2S1"), results=("checked_legal",),
                        legal=("principle", "condition"))
    valid = response(item(words, outcomes=[selection], legal=True))
    bad = deepcopy(valid)
    bad["items"][0]["delivery_requirement"]["outcomes"][0]["scope_source_ids"] = ["unknown"]
    model = Model(bad, valid)

    brain.interpret(model, context(), words)

    first = json.loads(model.calls[0][0].user)
    assert first["earlier_conversation"] == [vars(message) for message in context().messages]
    assert first["latest_message"] == words
    choices = [value for key, value in first.items()
               if key.startswith("delivery_") and isinstance(value, dict) and "P2S1" in value]
    assert len(choices) == 1
    catalogue, = choices
    assert set(catalogue) == {"L1", "P1S1", "P2S1"}
    for identity, metadata in catalogue.items():
        assert isinstance(metadata, dict)
        assert not {"text", "quoted", "source_spans"}.intersection(metadata)
        assert set(metadata) <= {"id", "turn_id", "role", "origin"}
        assert metadata["role"] == ("nm" if identity == "P2S1" else "advocate")
    assert catalogue["P1S1"]["turn_id"] == catalogue["P2S1"]["turn_id"] == "original"
    assert json.loads(model.calls[1][0].user)["original_input"] == first


def test_incomplete_original_history_refuses_before_any_delivery_interpretation():
    model = Model(response(item("Finish the earlier comparison")))
    conversation = brain.Conversation(context().messages, current_matter_id="owned-matter",
                                      complete=False)
    with pytest.raises(brain.IncompleteConversation):
        brain.interpret(model, conversation, "Finish the earlier comparison")
    assert model.calls == []


def test_server_outcome_ids_are_distinct_across_items_and_stable_for_identical_input():
    words = "Recap my account. Explain the legal conditions."
    first = outcome(sources=("L1", "P1S1"), condition="Recap the original attributed account.")
    second = outcome(requests=("L2",), sources=("L2", "P1S1"),
                     results=("checked_legal",), legal=("condition",),
                     condition="Explain the checked legal conditions.")
    data = response(item("Recap my account", outcomes=[first]),
                    item("Explain the legal conditions", outcomes=[second], legal=True))
    models = [Model(data), Model(data)]

    plans = [brain.interpret(model, context(), words) for model in models]

    identities = [
        [assert_owned_delivery(work, declaration["delivery_requirement"]["outcomes"])[0]
         for work, declaration in zip(plan.items, data["items"], strict=True)]
        for plan in plans]
    assert len(set(identities[0])) == 2
    assert identities[0] == identities[1]
    assert all(len(model.calls) == 1 for model in models)
