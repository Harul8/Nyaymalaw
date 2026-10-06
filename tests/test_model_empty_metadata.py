"""Declared empty transport tolerance never repairs meaningful fields."""

from copy import deepcopy

import pytest

from nm.shared.model_port import SchemaViolation, canonical_schema_data, on_the_wire, require_schema


def schema():
    row = {"type": "object", "additionalProperties": False,
           "required": ["decision", "reason"], "properties": {
               "decision": {"type": "string", "enum": ["admit"]},
               "reason": {"type": "string", "minLength": 1}},
           "x-nm-empty-metadata": {"unused_ids": "array", "unused_reason": "string"}}
    return {"type": "object", "additionalProperties": False,
            "required": ["rows"], "properties": {
                "rows": {"type": "array", "items": row}}}


@pytest.mark.parametrize("reason", ["", " \n\t "])
def test_declared_empty_fields_are_admissible_without_mutating_evidence(reason):
    data = {"rows": [{"decision": "admit", "reason": "Original evidence is sufficient.",
                      "unused_ids": [], "unused_reason": reason}]}
    original = deepcopy(data)
    require_schema(data, schema())
    canonical = canonical_schema_data(data, schema())
    assert canonical == {"rows": [{"decision": "admit",
                                   "reason": "Original evidence is sufficient."}]}
    assert data == original
    assert "x-nm-empty-metadata" not in str(on_the_wire(schema()))
    assert "unused_ids" not in str(on_the_wire(schema()))


@pytest.mark.parametrize("field,value", [
    ("unused_ids", ["owned-unit"]), ("unused_reason", "Keep this other result."),
    ("unused_ids", None), ("unknown", []), ("reason", ""),
])
def test_content_wrong_types_unknown_fields_and_required_reasons_remain_invalid(field, value):
    row = {"decision": "admit", "reason": "Original evidence is sufficient.", field: value}
    with pytest.raises(SchemaViolation):
        require_schema({"rows": [row]}, schema())


def test_metadata_cannot_shadow_an_applicable_field():
    offered = schema()
    offered["properties"]["rows"]["items"]["x-nm-empty-metadata"]["reason"] = "string"
    with pytest.raises(ValueError, match="unused"):
        require_schema({"rows": [{"decision": "admit", "reason": ""}]}, offered)


def test_unmarked_schemas_keep_strict_closed_object_validation():
    offered = {"type": "object", "additionalProperties": False,
               "required": ["statement"], "properties": {"statement": {"type": "string"}}}
    with pytest.raises(SchemaViolation):
        require_schema({"statement": "An attributed assertion.", "unused_ids": []}, offered)
