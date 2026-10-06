"""NM-authored strict schema defects fail before transport or spending.

These tests exercise the real OpenAI adapter with an SDK-shaped offline client.
They check the mandatory object shape, not semantic response accuracy or a
guessed complete provider keyword catalogue. Historical data validation keeps
its separate contract.
"""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import (
    ConfigurationError,
    Prompt,
    SchemaViolation,
    Tier,
    on_the_wire,
    require_schema,
)

pytestmark = pytest.mark.class_a
MODEL = "gpt-4.1-mini-2025-04-14"
PROMPT = Prompt(user="Examine the complete supplied account.", operation="schema_preflight_test")


def _schema():
    return {
        "type": "object", "additionalProperties": False,
        "required": ["items", "note"],
        "properties": {
            "note": {"type": ["string", "null"]},
            "items": {
                "type": "array", "minItems": 1, "maxItems": 2,
                "items": {"anyOf": [
                    {
                        "type": "object", "additionalProperties": False,
                        "required": ["kind", "value", "reference"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["read"]},
                            "value": {"type": "string", "minLength": 1},
                            "reference": {"type": "string", "pattern": r"^f[1-9][0-9]*$"},
                        },
                        "x-nm-empty-metadata": {"unused": "array"},
                    },
                    {
                        "type": "object", "additionalProperties": False,
                        "required": ["kind", "value"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["skip"]},
                            "value": {"type": ["string", "null"]},
                        },
                    },
                ]},
            },
        },
        "x-nm-read": "schema_preflight_test",
        "x-nm-fixed-inventory": {"items": []},
    }


def _payload():
    return {"items": [{"kind": "read", "value": "Attributed original words.",
                       "reference": "f1"}], "note": None}


def _adapter(tmp_path, payload):
    budget = SessionCallBudget(tmp_path / "offline-budget.db", "1", models=(MODEL,))
    calls, authorizations = [], []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model=MODEL, id="offline-preflight-response",
            choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=12),
        )

    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL,
                                                 "offline-only", None)})
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIModelAdapter(config, client=client, call_budget=budget).for_matter_text(
        lambda: authorizations.append("authorized"))
    return model, calls, authorizations, budget


@pytest.mark.parametrize("fault", [
    "root_open", "root_additional", "root_optional", "root_extra_required",
    "root_duplicate_required", "nested_open", "nested_optional",
    "nested_extra_required", "nullable_object_optional",
])
def test_invalid_object_schema_never_dispatches_or_reserves(tmp_path, fault):
    schema = _schema()
    target = schema
    if fault.startswith("nested_"):
        target = schema["properties"]["items"]["items"]["anyOf"][0]
    if fault.endswith("open"):
        target.pop("additionalProperties")
    elif fault == "root_additional":
        target["additionalProperties"] = True
    elif fault.endswith("optional") and fault != "nullable_object_optional":
        target["required"].remove("value" if target is not schema else "note")
    elif fault.endswith("extra_required"):
        target["required"].append("foreign")
    elif fault == "root_duplicate_required":
        target["required"].append("note")
    elif fault == "nullable_object_optional":
        schema["properties"]["note"] = {
            "type": ["object", "null"], "additionalProperties": False,
            "required": [], "properties": {"reason": {"type": "string"}},
        }
    else:
        raise AssertionError(f"Undeclared test fault: {fault}")
    original = deepcopy(schema)
    model, calls, authorizations, budget = _adapter(tmp_path, _payload())
    error = None
    try:
        model.structured(PROMPT, schema, Tier.ROUTINE, max_tokens=256)
    except Exception as caught:  # noqa: BLE001 -- inspect the exact preflight outcome
        error = caught

    assert (len(calls), len(authorizations), budget.status()["attempts"]) == (0, 0, 0)
    assert budget.status()["charged_usd"] == 0
    assert isinstance(error, ConfigurationError), type(error).__name__
    assert not isinstance(error, SchemaViolation)
    assert error.usage is None and error.retries == 0
    assert schema == original


@pytest.mark.parametrize("root", [
    {"anyOf": [_schema()]},
    {**_schema(), "anyOf": [_schema()]},
    {"type": "array", "items": _schema()},
    {"type": "string"},
    {**_schema(), "type": ["object", "null"]},
])
def test_nonobject_or_alternative_root_fails_before_transport(tmp_path, root):
    original = deepcopy(root)
    model, calls, authorizations, budget = _adapter(tmp_path, _payload())
    with pytest.raises(ConfigurationError) as caught:
        model.structured(PROMPT, root, Tier.ROUTINE, max_tokens=256)
    assert "root must be an object without anyOf" in str(caught.value)
    assert (len(calls), len(authorizations), budget.status()["attempts"]) == (0, 0, 0)
    assert budget.status()["charged_usd"] == 0
    assert caught.value.usage is None and caught.value.retries == 0
    assert root == original


@pytest.mark.parametrize("alternatives, location", [
    ([], "$.items[].anyOf needs declared alternatives"),
    (None, "$.items[].anyOf needs declared alternatives"),
    ({}, "$.items[].anyOf needs declared alternatives"),
    ([True], "$.items[].anyOf[0] must be an object"),
    ([_schema(), False], "$.items[].anyOf[1] must be an object"),
])
def test_malformed_nested_alternatives_report_the_owned_schema_path(
    tmp_path, alternatives, location,
):
    schema = _schema()
    schema["properties"]["items"]["items"]["anyOf"] = alternatives
    original = deepcopy(schema)
    model, calls, authorizations, budget = _adapter(tmp_path, _payload())
    with pytest.raises(ConfigurationError) as caught:
        model.structured(PROMPT, schema, Tier.ROUTINE, max_tokens=256)
    assert location in str(caught.value)
    assert (len(calls), len(authorizations), budget.status()["attempts"]) == (0, 0, 0)
    assert budget.status()["charged_usd"] == 0
    assert schema == original


def test_one_declared_nested_alternative_is_a_valid_neighbour(tmp_path):
    schema = _schema()
    alternatives = schema["properties"]["items"]["items"]["anyOf"]
    schema["properties"]["items"]["items"]["anyOf"] = alternatives[:1]
    model, calls, authorizations, budget = _adapter(tmp_path, _payload())
    result = model.structured(PROMPT, schema, Tier.ROUTINE, max_tokens=256)
    assert result.data == _payload()
    assert len(calls) == len(authorizations) == budget.status()["attempts"] == 1


@pytest.mark.parametrize("payload", [
    _payload(),
    {"items": [{"kind": "skip", "value": None}], "note": "No legal conclusion."},
])
def test_closed_alternatives_nullable_and_pattern_dispatch_normally(tmp_path, payload):
    schema = _schema()
    original = deepcopy(schema)
    model, calls, authorizations, budget = _adapter(tmp_path, payload)
    result = model.structured(PROMPT, schema, Tier.ROUTINE, max_tokens=256)

    assert result.data == payload
    assert len(calls) == len(authorizations) == budget.status()["attempts"] == 1
    assert budget.status()["charged_usd"] > 0
    wire = calls[0]["response_format"]["json_schema"]
    assert wire["strict"] is True
    assert wire["schema"]["properties"]["note"]["type"] == ["string", "null"]
    branches = wire["schema"]["properties"]["items"]["items"]["anyOf"]
    assert branches[0]["properties"]["reference"]["pattern"] == r"^f[1-9][0-9]*$"
    assert all(key not in str(wire["schema"]) for key in (
        "x-nm-read", "x-nm-fixed-inventory", "x-nm-empty-metadata"))
    assert schema == original


@pytest.mark.parametrize("note", [None, {"reason": "Original account remains qualified."}])
def test_nullable_object_with_all_fields_required_is_a_valid_neighbour(tmp_path, note):
    schema = _schema()
    schema["properties"]["note"] = {
        "type": ["object", "null"], "additionalProperties": False,
        "required": ["reason"], "properties": {"reason": {"type": "string"}},
    }
    payload = {**_payload(), "note": note}
    model, calls, authorizations, budget = _adapter(tmp_path, payload)
    result = model.structured(PROMPT, schema, Tier.ROUTINE, max_tokens=256)
    assert result.data == payload
    assert len(calls) == len(authorizations) == budget.status()["attempts"] == 1


def test_projection_handles_metadata_and_existing_quoted_enum_without_mutation():
    schema = _schema()
    schema["properties"]["note"] = {"type": "string", "enum": ['Exact "quoted" words.']}
    original = deepcopy(schema)
    wire = on_the_wire(schema)
    assert "enum" not in wire["properties"]["note"]
    assert set(wire["required"]) == set(wire["properties"])
    assert schema == original


def test_local_historical_validation_does_not_acquire_wire_required_rules():
    historical_schema = {
        "type": "object", "additionalProperties": False, "required": ["operator"],
        "properties": {"operator": {"type": "string"},
                       "legal_source_ids": {"type": "array", "items": {"type": "string"}}},
    }
    expression = {"operator": "source_account"}
    original = deepcopy(expression)
    require_schema(expression, historical_schema)
    assert expression == original


def test_valid_schema_with_bad_provider_output_remains_a_receipted_schema_violation(tmp_path):
    payload = _payload()
    payload["items"][0]["kind"] = "foreign"
    model, calls, authorizations, budget = _adapter(tmp_path, payload)
    with pytest.raises(SchemaViolation) as caught:
        model.structured(PROMPT, _schema(), Tier.ROUTINE, max_tokens=256)
    assert not isinstance(caught.value, ConfigurationError)
    assert caught.value.usage is not None
    assert len(calls) == len(authorizations) == budget.status()["attempts"] == 1
    assert budget.status()["charged_usd"] > 0

