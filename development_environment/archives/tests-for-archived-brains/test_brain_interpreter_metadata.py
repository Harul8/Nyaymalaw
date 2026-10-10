"""Inapplicable no-effect wording is harmless; effects and targets are not.

Writer proposals use raw fresh evidence expressions. These tests exercise
interpreter bookkeeping, not semantic interpretation by a real provider.
"""
from copy import deepcopy

import pytest

from nm.brain import turn as boundary
from nm.brain.conversation import _record_requirement
from nm.shared.model_port import SchemaViolation
from tests.test_brain_completion_link_matrix import seed
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit, reopened
from tests.test_brain_turn import plan


def no_effect(condition=""):
    return {"kind": "none", "target_ids": [], "operation": "none",
            "success_condition": condition}


def read_requirement(proposed):
    return _record_requirement(
        proposed, index=0, purposes=[], known_ids={"owned-record"},
        current_ids={"owned-record"}, matter_scope="current")


@pytest.mark.parametrize("condition", [
    "", " \n ", "The ordinary conversational reply addresses the question.",
    "Preserve the uncertainty while discussing the account.",
])
def test_none_requirement_normalizes_only_unused_success_condition(condition):
    proposed = no_effect(condition)
    untouched = deepcopy(proposed)
    assert read_requirement(proposed) == no_effect()
    assert proposed == untouched


@pytest.mark.parametrize("change", [
    {"target_ids": ["owned-record"]},
    {"operation": "new"},
    {"operation": "corrects"},
    {"target_ids": ["owned-record"], "operation": "corrects"},
    {"target_ids": ["foreign-record"]},
    {"operation": "invented-operation"},
    {"success_condition": {"unexpected": "structured content"}},
])
def test_none_requirement_never_normalizes_effects_targets_or_bad_types(change):
    proposed = {**no_effect("An unused explanation."), **deepcopy(change)}
    untouched = deepcopy(proposed)
    with pytest.raises(SchemaViolation):
        read_requirement(proposed)
    assert proposed == untouched


@pytest.mark.parametrize("condition", [
    "The ordinary conversational reply addresses the question.",
    "The supplied account remains attributed and uncertain.",
])
def test_repeated_unused_interpreter_condition_delivers_and_saves_without_correction(
        client, wired, monkeypatch, condition):
    message = "Hello. I would like to examine the attributed account."
    route = plan(message, record_requirement=no_effect(condition))
    # Repeating the original output characterizes the earlier two-attempt 503.
    # Correct code normalizes the first response and never requests the second.
    model = RawExpressionModel([route, deepcopy(route)], [
        lambda payload: {"units": [raw_unit(payload)]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    turn_id = "interpreter-unused-condition"
    response = client.post("/api/turn", json={"message": message, "turn_id": turn_id})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["blocked"] is False
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "verify_continuation",
    ]
    assert answer["metrics"]["llm_calls"] == 3
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 0
    execution = answer["material_coverage"]["execution"]
    assert execution["requests"][0]["record_requirement"] == no_effect()
    assert execution["record_changes"] == []
    saved = reopened(wired, answer)
    assert len(saved.brain_chat) == 1
    assert saved.brain_chat[0]["message"] == message
    assert saved.brain_chat[0]["response"]["elements"] == answer["elements"]
    assert route["items"][0]["record_requirement"]["success_condition"] == condition
    calls_before = len(model.calls)
    repeated = send(client, message, turn_id)
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    assert len(model.calls) == calls_before
    assert len(reopened(wired, answer).brain_chat) == 1


@pytest.mark.parametrize("fault", ["owned_target", "new_operation", "correction_operation"])
def test_real_none_contract_contradiction_requires_bounded_correction_and_preserves_records(
        client, wired, monkeypatch, fault):
    turn_id = "interpreter-consequential-metadata-" + fault
    opened, before, target = seed(client, wired, monkeypatch, turn_id)
    message = "Please explain the uncertainty in the earlier account."
    bad = plan(message, scope="current", relation="continues")
    if fault == "owned_target":
        bad["items"][0]["record_requirement"]["target_ids"] = [target]
    else:
        bad["items"][0]["record_requirement"]["operation"] = (
            "new" if fault == "new_operation" else "corrects")
    bad["items"][0]["record_requirement"]["success_condition"] = "Unused description."
    corrected = plan(message, scope="current", relation="continues")
    model = RawExpressionModel([bad, corrected], [
        lambda payload: {"units": [raw_unit(payload)]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, turn_id, opened=opened)
    assert answer["blocked"] is False
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "interpret_conversation",
        "continue_conversation", "verify_continuation",
    ]
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 1
    assert model.calls[1][1]["original_input"]["latest_message"] == message
    assert "record_requirement" in model.calls[1][1]["validation_issue"]
    execution = answer["material_coverage"]["execution"]
    assert execution["requests"][0]["record_requirement"] == no_effect()
    assert execution["record_changes"] == []
    saved = reopened(wired, answer)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    assert conversation.open_material == before
    assert saved.brain_chat[-1]["message"] == message
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    before_calls = len(model.calls)
    repeated = send(client, message, turn_id, opened=opened)
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    assert len(model.calls) == before_calls
