"""Offer executable interpreter modes without suppressing valid neighbouring work.

These authored proposals test schema and bounded correction mechanics, not the
model's understanding of the request or whether a requested effect occurred.
"""
from copy import deepcopy

import pytest

from nm.brain import conversation as owner
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_brain_interpret_mutation_generation import (
    LATEST,
    RawInterpreter,
    context,
    reply,
    scope,
)
from tests.test_brain_record_review_wire import _strict_objects


def _review(*, mode="record_acknowledgement", change=False):
    requirement = {
        "kind": "change" if change else "review", "target_ids": ["material-17"],
        "operation": "corrects" if change else "none",
        "success_condition": "The saved entry matches the original account, including "
                             "where that entry already satisfies the requested result.",
    }
    data = reply(scope(kind="interpretation_review", targets=("material-17",),
                       relations=("corrects",)), requirement=requirement)
    data["items"][0]["response_mode"] = mode
    return data


def _captured():
    model = RawInterpreter(reply())
    owner.interpret(model, context(), LATEST)
    return model.calls[0]


def test_offered_modes_are_closed_and_keep_shared_owned_choices():
    captured = _captured()
    _strict_objects(captured["offered"])
    branches = captured["offered"]["properties"]["items"]["items"]["anyOf"]
    modes = {branch["properties"]["response_mode"]["enum"][0]: branch
             for branch in branches}
    assert set(modes) == {"substantive", "record_acknowledgement"}
    assert len(branches) == 2
    targets = {row["id"] for row in captured["payload"]["target_catalogue"]}
    sources = set(captured["payload"]["mutation_source_catalogue"])
    for branch in branches:
        fields = branch["properties"]
        assert set(fields["record_requirement"]["properties"]["target_ids"]["items"][
            "enum"]) == targets
        for mutation in fields["mutation_scopes"]["items"]["anyOf"]:
            assert set(mutation["properties"]["authority_source_ids"]["items"]["enum"]) == sources
            assert set(mutation["properties"]["target_ids"]["items"]["enum"]) == targets
    fields = modes["record_acknowledgement"]["properties"]
    assert fields["intent"]["enum"] == ["request"]
    assert fields["next_step"]["enum"] == ["answer"]
    assert fields["response_basis"]["enum"] == ["conversation_record"]
    assert fields["record_requirement"]["properties"]["kind"]["enum"] == ["review", "change"]


@pytest.mark.parametrize("case", ["no_record_answer", "already_current_request", "review_request",
                                  "implicit_contribution"])
def test_legitimate_mode_neighbours_are_admitted_without_a_correction(case):
    if case == "no_record_answer":
        data = reply()
    elif case == "already_current_request":
        data = _review(change=True)
    elif case == "review_request":
        data = _review()
    else:
        data = reply(scope(targets=("material-17",), relations=("corrects",)))
        data["items"][0]["intent"] = "contribution"
    original = deepcopy(data)
    model = RawInterpreter(data)
    planned = owner.interpret(model, context(), LATEST)
    assert len(model.calls) == 1 and model.claims == []
    require_schema(data, model.calls[0]["offered"])
    assert planned.items[0].response_mode == data["items"][0]["response_mode"]
    assert planned.items[0].record_requirement == data["items"][0]["record_requirement"]
    assert data == original
    if case == "implicit_contribution":
        assert planned.material_review is True
        assert planned.items[0].mutation_scopes[0]["permitted_relations"] == ["corrects"]
        assert planned.items[0].record_requirement["kind"] == "none"


@pytest.mark.parametrize("fault", ["no_record_requirement", "contribution", "legal_basis",
                                   "legal_work", "clarification"])
def test_inapplicable_acknowledgement_is_not_offered_even_before_runtime_admission(fault):
    data = _review()
    item = data["items"][0]
    if fault == "no_record_requirement":
        item["record_requirement"] = reply()["items"][0]["record_requirement"]
    elif fault == "contribution":
        item["intent"] = "contribution"
    elif fault == "legal_basis":
        item["response_basis"] = "legal_authority"
    elif fault == "legal_work":
        item["next_step"] = "legal_work"
    else:
        item["next_step"] = "clarify"
    captured = _captured()
    before = deepcopy(data)
    with pytest.raises(SchemaViolation):
        require_schema(data, captured["offered"])
    with pytest.raises(SchemaViolation):
        owner._turn_plan(data, context(), latest=LATEST)
    assert data == before


@pytest.mark.parametrize("mode", ["substantive", "record_acknowledgement"])
@pytest.mark.parametrize("foreign", ["target", "authority_source"])
def test_each_mode_retains_exact_owned_target_and_original_authority_ids(mode, foreign):
    data = _review(mode=mode, change=True)
    fields = data["items"][0]
    if foreign == "target":
        fields["record_requirement"]["target_ids"] = ["foreign-record"]
        fields["mutation_scopes"][0]["target_ids"] = ["foreign-record"]
    else:
        # The earlier NM message is available as context, never original authority.
        fields["mutation_scopes"][0]["authority_source_ids"] = ["P2S1"]
    with pytest.raises(SchemaViolation):
        require_schema(data, _captured()["offered"])


def test_bad_mode_repair_retains_full_original_input_and_one_conditional_call():
    invalid = reply()
    invalid["items"][0]["response_mode"] = "record_acknowledgement"
    model = RawInterpreter(invalid, reply())
    planned = owner.interpret(model, context(), LATEST)
    assert planned.items[0].response_mode == "substantive"
    assert len(model.calls) == 2
    assert model.claims == ["interpret_conversation:correction"]
    assert model.calls[1]["payload"]["original_input"] == model.calls[0]["payload"]
    assert model.calls[1]["offered"] == model.calls[0]["offered"]
