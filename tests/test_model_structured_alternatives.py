"""Closed alternative shapes preserve valid choices without crosswiring fields."""
from copy import deepcopy

import pytest

from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema


def branch(field, properties):
    return {"type": "object", "additionalProperties": False,
            "required": ["field", *properties], "properties": {
                "field": {"type": "string", "enum": [field]}, **properties}}


CREATION = branch("create", {"statement": {"type": "string", "minLength": 1}})
REVISION = branch("revise", {"target": {"type": "string", "enum": ["owned"]}})
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["repairs"], "properties": {
              "repairs": {"type": "array", "maxItems": 1,
                          "items": {"anyOf": [CREATION, REVISION]}}}}


@pytest.mark.parametrize("row", [
    {"field": "create", "statement": "Qualified original account."},
    {"field": "revise", "target": "owned"},
])
def test_each_exact_declared_shape_is_available(row):
    before = deepcopy(row)
    require_schema({"repairs": [row]}, SCHEMA)
    assert row == before


@pytest.mark.parametrize("row", [
    {"field": "create", "target": "owned"},
    {"field": "revise", "statement": "Crosswired."},
    {"field": "revise", "target": "foreign"},
    {"field": "unknown", "target": "owned"},
    {"field": "create", "statement": ""},
    {"field": "create", "statement": "Supported.", "target": "owned"},
    None,
])
def test_alternative_does_not_silently_open_row_constraints(row):
    with pytest.raises(SchemaViolation, match="no declared alternative"):
        require_schema({"repairs": [row]}, SCHEMA)


def test_parent_constraints_remain_enforced():
    row = {"field": "revise", "target": "owned"}
    with pytest.raises(SchemaViolation, match="too many items"):
        require_schema({"repairs": [row, row]}, SCHEMA)
    with pytest.raises(SchemaViolation, match="undeclared"):
        require_schema({"repairs": [row], "success": True}, SCHEMA)


def test_overlapping_alternatives_need_one_valid_shape_not_exactly_one():
    require_schema("owned", {"anyOf": [{"type": "string"},
                                       {"type": "string", "enum": ["owned"]}]})


def test_branch_declared_empty_metadata_is_harmless_and_input_is_preserved():
    schema = {"anyOf": [{**CREATION, "x-nm-empty-metadata": {"unused": "array"}}, REVISION]}
    data = {"field": "create", "statement": "Supported.", "unused": []}
    before = deepcopy(data)
    require_schema(data, schema)
    assert data == before
    with pytest.raises(SchemaViolation):
        require_schema({**data, "unused": ["consequential"]}, schema)
    assert "x-nm-empty-metadata" not in on_the_wire(schema)["anyOf"][0]


@pytest.mark.parametrize("alternatives", [[], None, {}, [True]])
def test_malformed_declared_choice_is_a_schema_author_error(alternatives):
    with pytest.raises(ValueError):
        require_schema({}, {"anyOf": alternatives})
