"""Delivery mode expresses the requested result, never a prose keyword match."""

from copy import deepcopy

import pytest

from nm.brain.conversation import Conversation, WorkItem, _turn_plan
from nm.shared.model_port import SchemaViolation
from tests.brain_continuation_fixture import interpretation
from tests.test_brain_material import plan


def declared(mode="record_acknowledgement"):
    data = interpretation(plan(
        "Review my attributed account and leave it unchanged if it is faithful.",
        material_purposes=("interpretation_review",),
        record_requirement={"kind": "review", "target_ids": [], "operation": "none",
                            "success_condition": "Check the original account against its record."}))
    data.pop("material", None)
    data["items"][0].update(response_mode=mode, next_step="answer", matter_scope="none")
    return data


@pytest.mark.parametrize("mode", ["record_acknowledgement", "substantive"])
def test_record_work_does_not_force_acknowledgement_delivery(mode):
    result = _turn_plan(declared(mode), Conversation(()))
    assert result.items[0].response_mode == mode


@pytest.mark.parametrize("field,value", [
    ("intent", "contribution"), ("response_mode", "unknown"),
    ("record_requirement", {"kind": "none", "target_ids": [], "operation": "none",
                            "success_condition": ""}),
])
def test_acknowledgement_requires_an_explicit_requested_record_result(field, value):
    data = declared()
    data["items"][0][field] = value
    with pytest.raises(SchemaViolation):
        _turn_plan(data, Conversation(()))


def test_legal_or_clarification_work_cannot_be_reclassified_as_acknowledgement():
    data = declared()
    legal = deepcopy(data)
    legal["items"][0].update(next_step="legal_work", response_basis="legal_authority",
                             research_question="What law governs the requested remedy?")
    with pytest.raises(SchemaViolation, match="response_mode"):
        _turn_plan(legal, Conversation(()))
    data["items"][0].update(next_step="clarify", reply="",
                             clarification="Which of the attributed records should be examined?")
    with pytest.raises(SchemaViolation, match="response_mode"):
        _turn_plan(data, Conversation(()))


def test_missing_fresh_mode_is_not_silently_inferred_from_record_work():
    data = declared()
    del data["items"][0]["response_mode"]
    with pytest.raises(SchemaViolation, match="response_mode"):
        _turn_plan(data, Conversation(()))
    assert WorkItem("Original explanation", "new", "none", "ordinary", "answer").response_mode \
        == "substantive"
