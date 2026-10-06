"""Strict fresh expression generation preserves the saved v1 rendering contract.

The model outputs here are fabricated. These checks establish schema, rendering
and correction mechanics, not semantic detection or useful legal advice.
"""

from copy import deepcopy

import pytest

from nm.brain import continuation
from nm.brain import evidence_rendering as rendering
from nm.brain.legal_requirements import RESEARCH_VERIFICATION
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_brain_continuation import _continue, checked_finding, checked_law
from tests.test_brain_evidence_rendering import LAW, NEGATED_ACCOUNT, expression
from tests.test_brain_evidence_rendering import evidence as evidence
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit


def assert_all_object_properties_required(schema, path="schema"):
    """Inspect declared wire objects without a provider-specific schema guard."""
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, path
        properties = schema.get("properties", {})
        assert set(schema.get("required", ())) == set(properties), path
        for name, child in properties.items():
            assert_all_object_properties_required(child, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        assert_all_object_properties_required(schema["items"], f"{path}[]")


def test_legal_expression_and_provider_wire_require_every_declared_property(evidence):
    schema = rendering.expression_schema(**evidence)
    assert "legal_source_ids" in schema["properties"]
    assert_all_object_properties_required(schema)
    assert_all_object_properties_required(continuation._schema((0,), **evidence))


@pytest.mark.parametrize("sources", [None, {}])
def test_no_legal_catalogue_keeps_the_existing_four_field_contract(evidence, sources):
    schema = rendering.expression_schema(evidence["spans"], evidence["records"], sources)
    assert set(schema["properties"]) == {"operator", "source_ids", "record_ids", "focus"}
    assert_all_object_properties_required(schema)
    require_schema(expression(), schema)
    with pytest.raises(SchemaViolation):
        require_schema({**expression(), "legal_source_ids": []}, schema)


def test_legacy_rendering_cannot_relax_the_original_provider_schema(evidence, monkeypatch):
    schema = rendering.expression_schema(**evidence)
    if "legal_source_ids" not in schema["required"]:
        schema["required"].append("legal_source_ids")
    before = deepcopy(schema), deepcopy(evidence)
    legacy = expression("checked_legal", sources=(), records=("research:1",))
    original_expression = deepcopy(legacy)
    monkeypatch.setattr(rendering, "expression_schema", lambda *args, **kwargs: schema)

    rendered = rendering.render_expression(legacy, **evidence)

    assert LAW in rendered["text"]
    assert (schema, evidence) == before
    assert legacy == original_expression
    assert_all_object_properties_required(schema)
    with pytest.raises(SchemaViolation):
        require_schema(legacy, schema)


def test_saved_v1_legal_expression_without_the_new_required_field_renders_identically(evidence):
    legacy = expression("checked_legal", records=("research:1",))
    explicit = {**deepcopy(legacy), "legal_source_ids": []}
    expected = rendering.render_expression(explicit, **evidence)
    saved = {
        "id": "saved-legal", "kind": "assessment", "uncertainty": "conditional",
        "expression_contract": rendering.EVIDENCE_EXPRESSION_CONTRACT,
        "evidence_expression": deepcopy(legacy), **deepcopy(expected),
    }
    before = deepcopy(saved), deepcopy(evidence)

    rendering.validate_rendered_block(saved, **evidence)
    actual = rendering.render_expression(saved["evidence_expression"], **evidence)

    assert rendering.EVIDENCE_EXPRESSION_CONTRACT == "evidence_expression_v1"
    assert actual == expected
    assert NEGATED_ACCOUNT in actual["text"] and LAW in actual["text"]
    assert actual["span_ids"] == ["L1"]
    assert actual["record_ids"] == ["research:1"]
    assert actual["legal_source_ids"] == ["legal:1"]
    assert actual["inline_citations"] == [
        {"text": "Checked legal passage 1", "legal_source_id": "legal:1"}]
    assert (saved, evidence) == before
    assert "legal_source_ids" not in saved["evidence_expression"]


def test_empty_direct_selector_replays_without_unused_legal_catalogue(evidence):
    expression_without_selector = expression()
    selected = {**deepcopy(expression_without_selector), "legal_source_ids": []}
    original = deepcopy(selected), deepcopy(evidence)
    expected = rendering.render_expression(expression_without_selector,
                                           **{**evidence, "sources": {}})
    # Fresh generation used a larger pool; the durable block retains only its
    # actual source dependencies. An empty direct selection names no passage.
    assert rendering.render_expression(selected, **evidence) == expected
    assert rendering.render_expression(selected, **{**evidence, "sources": {}}) == expected
    assert (selected, evidence) == original
    with pytest.raises(SchemaViolation):
        require_schema(selected, rendering.expression_schema(
            evidence["spans"], evidence["records"], {}))


@pytest.mark.parametrize("selection", [None, "", ["foreign"], ["legal:1"]])
def test_replay_does_not_ignore_populated_or_malformed_direct_selector(evidence, selection):
    selected = {**expression(), "legal_source_ids": selection}
    before = deepcopy(selected)
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **{**evidence, "sources": {}})
    assert selected == before


def legal_state():
    source = checked_law({
        "id": "A1", "kind": "provision", "title": "Synthetic inspection provision",
        "locator": "section 1", "text": LAW,
    })
    finding = checked_finding({"label": "Conditional inspection", "sources": [source]})
    return {
        "disputes": {"state": "ok", "rows": [{"id": "D1", "label": "Reported inspection"}]},
        "requirements": {
            "state": "ok", "by_dispute": {"D1": [finding]},
            "coverage_by_dispute": {"D1": {
                "source_freshness": "current", "verification_current": True,
                "verification_contract": RESEARCH_VERIFICATION,
            }},
        },
    }


def legal_unit(payload, *, omit=False):
    proposed = raw_unit(payload, operator="checked_legal", kind="assessment", all_sources=False)
    finding_id = next(identity for identity, row in payload["record_catalogue"].items()
                      if row["type"] == "requirement")
    proposed["blocks"][0]["evidence_expression"]["record_ids"] = [finding_id]
    proposed["blocks"][0]["uncertainty"] = "conditional"
    for block in proposed["blocks"]:
        block["evidence_expression"]["legal_source_ids"] = []
    if omit:
        del proposed["blocks"][0]["evidence_expression"]["legal_source_ids"]
    return {"units": [proposed]}


@pytest.mark.parametrize("omit", [False, True])
def test_fresh_legal_unit_requires_the_field_and_corrects_only_within_the_existing_bound(omit):
    originals = {}

    def initial(payload):
        originals.update(legal_sources=deepcopy(payload["legal_sources"]),
                         record_catalogue=deepcopy(payload["record_catalogue"]))
        return legal_unit(payload, omit=omit)

    def corrected(payload):
        issues = payload["correction"]["validation_issues"]
        assert len(issues) == 1 and issues[0]["request_index"] == 0
        assert "legal_source_ids" in issues[0]["issue"]
        assert payload["legal_sources"] == originals["legal_sources"]
        assert payload["record_catalogue"] == originals["record_catalogue"]
        return legal_unit(payload)

    model = RawExpressionModel([], [initial, corrected] if omit else [initial])

    result = _continue(model, **legal_state())

    assert result.coverage[0]["state"] == "ok"
    assert len(result.units) == 1
    expected_calls = ["continue_conversation"] * (2 if omit else 1) + ["verify_continuation"]
    assert [operation for operation, _ in model.calls] == expected_calls
    assert len(model.writer_outputs) == (2 if omit else 1)
    block = result.units[0]["blocks"][0]
    assert LAW in block["text"]
    assert block["legal_source_ids"] == list(originals["legal_sources"])
    assert block["evidence_expression"]["legal_source_ids"] == []
    assert len(block["inline_citations"]) == 1
    first_expression = model.schemas[0][1]["properties"]["units"]["items"][
        "properties"]["blocks"]["items"]["properties"]["evidence_expression"]
    assert_all_object_properties_required(first_expression)
