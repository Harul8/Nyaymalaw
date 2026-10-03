"""Reader operation schemas reject contradictory record-change authority."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.disputes import extract_disputes
from nm.brain.material import extract_details
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage, require_schema


class CapturingModel:
    def __init__(self):
        self.calls = []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        return ModelResult(
            text=None, data={"new_items": [], "changes": []}, tier=tier,
            provider="offline", model="offline", usage=Usage(0, 0, 0),
            latency_ms=0, completion=Completion.COMPLETE)


def _reader_schema(kind):
    model = CapturingModel()
    earlier = (Message("earlier", "advocate", "The reported event is disputed."),)
    record = {"id": "earlier:material:1", "source_turn_id": "earlier",
              "quoted": earlier[0].text, "statement": "A reported event is disputed.",
              "label": "Reported event", "identification": "identified",
              "clarification": "", "kind": "event", "placement": "matter",
              "dispute_ids": []}
    arguments = {"earlier": earlier, "latest": "I correct the earlier account.",
                 "current_matter_id": "matter"}
    if kind == "dispute":
        assert extract_disputes(model, **arguments, prior_disputes=(record,)) == ()
        link_field = "related_dispute_ids"
    else:
        assert extract_details(model, **arguments, prior_material=(record,)) == ()
        link_field = "related_material_ids"
    assert len(model.calls) == 1
    schema = model.calls[0][1]
    row = {"statement": "The advocate supplies a corrected account.",
           "source_id": "L1", "prior_source_ids": ["P1S1"],
           "matter_scope": "current", "basis": "stated", "importance": "relevant",
           "why_material": "The account affects the requested assessment."}
    if kind == "dispute":
        row.update(label="Reported event", identification="identified", clarification="")
    else:
        row.pop("matter_scope")
        row.update(kind="event", assignment_ids=["matter:discussion"])
    return schema, row, link_field


@pytest.mark.parametrize("kind", ("dispute", "detail"))
@pytest.mark.parametrize("contradiction", (
    "new_with_targets", "new_with_relation", "change_as_new", "change_without_target",
    "unknown_target", "legacy_response"))
def test_shipped_reader_schema_rejects_conflicting_creation_or_change(kind, contradiction):
    schema, row, link_field = _reader_schema(kind)
    valid_new = {"new_items": [row], "changes": []}
    valid_change = {"new_items": [], "changes": [
        {**row, "relation": "corrects", link_field: ["earlier:material:1"]}]}
    require_schema(valid_new, schema)
    require_schema(valid_change, schema)
    invalid = deepcopy(valid_new if contradiction.startswith("new_") else valid_change)
    if contradiction == "new_with_targets":
        invalid["new_items"][0][link_field] = ["earlier:material:1"]
    elif contradiction == "new_with_relation":
        invalid["new_items"][0]["relation"] = "new"
    elif contradiction == "change_as_new":
        invalid["changes"][0]["relation"] = "new"
    elif contradiction == "change_without_target":
        invalid["changes"][0][link_field] = []
    elif contradiction == "unknown_target":
        invalid["changes"][0][link_field] = ["another:material:1"]
    else:
        invalid = {"disputes" if kind == "dispute" else "details": [
            {**row, "relation": "new", link_field: []}]}
    with pytest.raises(SchemaViolation):
        require_schema(invalid, schema)
