"""Fresh scope generation and canonical ownership mechanics, without a provider.

Scope meanings are explicitly authored fixtures. These checks do not establish
semantic interpretation, factual correctness or authority to execute a change.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import conversation as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    on_the_wire,
    require_schema,
)
from tests.test_brain_record_review_wire import _strict_objects

RELATIONS = ("new", "adds", "corrects", "contradicts", "withdraws")
ORIGINAL = "The recorder says the certificate may remain with the examiner."
OTHER = "The handover date is unconfirmed."
LATEST = "Review the original attributed account and preserve its uncertainty."


def context(*, targets=True):
    return owner.Conversation(
        (owner.Message("original", "advocate", ORIGINAL + " " + OTHER),
         owner.Message("original", "nm", "The examiner holds the certificate.")),
        current_matter_id="matter-41", current_work="Review the attributed account.",
        open_material=({"id": "material-17", "statement": "The examiner holds the certificate.",
                        "quoted": ORIGINAL, "source_turn_id": "original",
                        "matter_scope": "current"},) if targets else (),
        open_disputes=({"id": "dispute-23", "label": "Custody disagreement",
                        "statement": "The reported custody remains disputed.",
                        "quoted": ORIGINAL, "source_turn_id": "original",
                        "matter_scope": "current"},) if targets else ())


def scope(*, kind="account_contribution", mode="exact", targets=(), relations=("new",),
          sources=("L1",)):
    return {"authority_kind": kind, "authority_source_ids": list(sources),
            "target_scope": mode, "target_ids": list(targets),
            "permitted_relations": list(relations)}


def reply(*scopes, purposes=None, requirement=None, latest=LATEST, matter_scope="current"):
    if purposes is None:
        purposes = sorted({entry["authority_kind"] for entry in scopes})
    return {"items": [{
        "request": latest, "relation": "continues", "matter_scope": matter_scope,
        "priority": "ordinary", "next_step": "answer", "intent": "request",
        "response_basis": "conversation_record", "research_question": "",
        "response_mode": "substantive", "material_purposes": list(purposes),
        "record_requirement": requirement or {
            "kind": "none", "target_ids": [], "operation": "none", "success_condition": ""},
        "mutation_scopes": list(scopes),
    }], "opening": {"ready": False, "party_name": "", "subject": "", "summary": ""}}


class RawInterpreter:
    """Return authored objects unchanged; optionally enforce provider shape."""

    def __init__(self, *outputs, strict=True):
        self.outputs = iter(deepcopy(outputs))
        self.strict = strict
        self.calls = []
        self.claims = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def claim_recovery(self, phase):
        self.claims.append(phase)
        return True

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        assert tier is Tier.JUDGE
        output = next(self.outputs)
        offered = on_the_wire(schema)
        self.calls.append({"payload": json.loads(prompt.user), "schema": deepcopy(schema),
                           "offered": offered, "output": deepcopy(output)})
        if self.strict:
            require_schema(output, offered)
        return ModelResult(text=None, data=output, tier=tier, provider="offline",
                           model="authored-interpreter-fixture", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def offered(*, conversation=None):
    model = RawInterpreter(reply())
    owner.interpret(model, context() if conversation is None else conversation, LATEST)
    return model.calls[0]


def scopes_schema(captured):
    return captured["offered"]["properties"]["items"]["items"]["properties"][
        "mutation_scopes"]["items"]


def test_fresh_scope_schema_offers_three_closed_native_branches_with_owned_choices():
    captured = offered()
    _strict_objects(captured["offered"])
    branches = scopes_schema(captured)["anyOf"]
    assert len(branches) == 3
    sources = set(captured["payload"]["mutation_source_catalogue"])
    targets = {row["id"] for row in captured["payload"]["target_catalogue"]}
    found = set()
    for branch in branches:
        fields = branch["properties"]
        assert set(fields) == set(owner._MUTATION_SCOPE_SCHEMA["properties"])
        assert fields["authority_source_ids"]["minItems"] == 1
        assert set(fields["authority_source_ids"]["items"]["enum"]) == sources
        assert set(fields["target_ids"]["items"]["enum"]) == targets
        mode, = fields["target_scope"]["enum"]
        if mode == "reviewed_whole":
            found.add("whole")
            assert fields["authority_kind"]["enum"] == ["interpretation_review"]
            assert fields["target_ids"]["maxItems"] == 0
            assert set(fields["permitted_relations"]["items"]["enum"]) == set(RELATIONS)
        elif fields["target_ids"].get("maxItems") == 0:
            found.add("new")
            assert set(fields["authority_kind"]["enum"]) == {
                "account_contribution", "interpretation_review"}
            assert fields["permitted_relations"]["items"]["enum"] == ["new"]
        else:
            found.add("targeted")
            assert fields["target_ids"]["minItems"] == 1
            assert set(fields["authority_kind"]["enum"]) == {
                "account_contribution", "interpretation_review"}
            assert set(fields["permitted_relations"]["items"]["enum"]) == set(RELATIONS)
    assert found == {"new", "targeted", "whole"}


def test_fresh_scope_schema_omits_targeted_branch_without_saved_targets():
    captured = offered(conversation=context(targets=False))
    branches = scopes_schema(captured)["anyOf"]

    assert len(branches) == 2
    assert all(branch["properties"]["target_ids"]["maxItems"] == 0 for branch in branches)
    require_schema(reply(scope()), captured["offered"])
    require_schema(reply(scope(kind="interpretation_review", mode="reviewed_whole",
                               relations=RELATIONS)), captured["offered"])


@pytest.mark.parametrize("grant", [
    scope(), scope(kind="interpretation_review"),
    scope(targets=("material-17",), relations=RELATIONS),
    scope(kind="interpretation_review", targets=("dispute-23",), relations=RELATIONS,
          sources=("L1", "P1S1")),
    scope(kind="interpretation_review", mode="reviewed_whole", relations=RELATIONS),
])
def test_legitimate_new_targeted_and_whole_scope_neighbours_need_no_correction(grant):
    data = reply(grant)
    before = deepcopy(data)
    model = RawInterpreter(data)

    plan = owner.interpret(model, context(), LATEST)

    assert len(model.calls) == 1 and model.claims == []
    expected = {**grant, **{field: sorted(set(grant[field])) for field in (
        "authority_source_ids", "target_ids", "permitted_relations")}}
    assert plan.items[0].mutation_scopes == (expected,)
    assert data == before


@pytest.mark.parametrize("grant", [
    scope(relations=("new", "adds")),
    scope(mode="reviewed_whole"),
    scope(kind="interpretation_review", mode="reviewed_whole", targets=("material-17",)),
])
def test_fresh_schema_rejects_empty_revision_or_non_review_whole_scope(grant):
    captured = offered()
    data = reply(grant)
    before = deepcopy(data)

    with pytest.raises(SchemaViolation):
        require_schema(data, captured["offered"])

    assert data == before


@pytest.mark.parametrize("grant", [
    scope(sources=("P2S1",)),
    scope(targets=("unowned-target",), relations=("corrects",)),
])
def test_fresh_schema_retains_original_authority_and_target_ownership_rejection(grant):
    with pytest.raises(SchemaViolation):
        require_schema(reply(grant), offered()["offered"])


def test_generation_retains_full_original_context_separate_from_nm_targets_and_words():
    saved = context()
    before = deepcopy(saved)
    captured = offered(conversation=saved)
    payload = captured["payload"]

    assert payload["latest_message"] == LATEST
    assert payload["earlier_conversation"] == [vars(message) for message in saved.messages]
    assert all(row["record"]["record_role"] == "nm_interpretation"
               for row in payload["target_catalogue"])
    assert payload["mutation_source_catalogue"]["P1S1"]["quoted"] == ORIGINAL
    assert payload["mutation_source_catalogue"]["P1S2"]["quoted"] == OTHER
    assert payload["mutation_source_catalogue"]["L1"]["quoted"] == LATEST
    assert "P2S1" not in payload["mutation_source_catalogue"]
    assert all(row["role"] == "advocate" for row in payload["mutation_source_catalogue"].values())
    assert saved == before


def test_generation_keeps_canonical_schemas_and_empty_revision_admission_unchanged():
    before = deepcopy((owner._SCHEMA, owner._MUTATION_SCOPE_SCHEMA))
    invalid = reply(scope(relations=("new", "adds")))

    offered()

    assert (owner._SCHEMA, owner._MUTATION_SCOPE_SCHEMA) == before
    assert "anyOf" not in owner._MUTATION_SCOPE_SCHEMA
    require_schema(invalid, owner._SCHEMA)
    with pytest.raises(SchemaViolation, match="exact revision scope requires owned targets"):
        owner._turn_plan(invalid, context(), latest=LATEST)


def test_targeted_review_and_separate_contribution_keep_their_distinct_native_scopes():
    review = scope(kind="interpretation_review", targets=("material-17",),
                   relations=("corrects",), sources=("L1", "P1S1"))
    contribution = scope(targets=("dispute-23",), relations=("adds",))
    data = reply(review, contribution, requirement={
        "kind": "review", "target_ids": ["material-17"], "operation": "none",
        "success_condition": "Check only the first saved formulation against its source."})
    model = RawInterpreter(data)

    plan = owner.interpret(model, context(), LATEST)

    assert len(model.calls) == 1 and model.claims == []
    assert plan.items[0].mutation_scopes == (review, contribution)


def test_permissive_invalid_generation_gets_bounded_correction_without_automatic_scope_repair():
    bad = reply(scope(relations=("new", "adds")))
    good = reply(scope())
    before = deepcopy((bad, good))
    model = RawInterpreter(bad, good, strict=False)

    plan = owner.interpret(model, context(), LATEST)

    assert len(model.calls) == 2 and model.claims == ["interpret_conversation:correction"]
    correction = model.calls[1]["payload"]
    assert correction["original_input"] == model.calls[0]["payload"]
    assert correction["rejected_output"] == bad
    assert "mutation_scopes" in correction["validation_issue"]
    assert plan.items[0].mutation_scopes == (scope(),)
    assert (bad, good) == before


def test_dropping_scope_on_correction_cannot_grant_a_requested_new_record_effect():
    requirement = {"kind": "change", "target_ids": [], "operation": "new",
                   "success_condition": "Create an attributed new record from the current account."}
    bad = reply(scope(relations=("new", "adds")), requirement=requirement)
    dropped = reply(purposes=["account_contribution"], requirement=requirement)
    model = RawInterpreter(bad, dropped, strict=False)

    with pytest.raises(
            SchemaViolation, match="requested change lacks its relevant source-linked scope"):
        owner.interpret(model, context(), LATEST)

    assert len(model.calls) == 2 and model.claims == ["interpret_conversation:correction"]
    assert model.calls[1]["payload"]["original_input"] == model.calls[0]["payload"]
    assert model.calls[1]["payload"]["rejected_output"] == bad
