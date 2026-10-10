"""Generation choices reflect operator mechanics without changing saved v1.

These offline schema/rendering witnesses use independently authored selectors.
They do not test relevance, legal applicability, provider behavior or useful
completion. Canonical ownership, rendering and replay remain separate checks.
"""
from copy import deepcopy

import pytest

from nm.brain import evidence_rendering as rendering
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_continuation import checked_law
from tests.test_brain_evidence_rendering import LAW, NEGATED_ACCOUNT, expression
from tests.test_brain_evidence_rendering import evidence as evidence


@pytest.fixture
def catalogues(evidence):
    values = deepcopy(evidence)
    dispute = deepcopy(values["records"]["material:1"])
    dispute.update(id="dispute:1", type="dispute")
    dispute["record"]["id"] = "dispute:1"
    values["records"]["dispute:1"] = dispute
    requirement = deepcopy(values["records"]["research:1"])
    requirement.update(id="requirement:1", type="requirement")
    values["records"]["requirement:1"] = requirement
    values["sources"]["legal:1"] = checked_law(values["sources"]["legal:1"])
    return values


def _generation(values):
    return rendering.expression_schema(**values, generation=True)


def _selected(operator, *, sources=(), records=(), legal=(), focus="none"):
    return {**expression(operator, sources=sources, records=records, focus=focus),
            "legal_source_ids": list(legal)}


def _supported(operator):
    if operator == "checked_legal":
        return _selected(operator, sources=("L1",), records=("research:1",))
    if operator == "comparison":
        return _selected(operator, sources=("L1", "L2"))
    if operator in ("acknowledgment", "record_result"):
        return _selected(operator)
    return _selected(operator, sources=("L1",))


def _assert_strict_objects(schema):
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
        assert set(schema.get("required", ())) == set(schema.get("properties", {}))
        for child in schema.get("properties", {}).values():
            _assert_strict_objects(child)
    if isinstance(schema.get("items"), dict):
        _assert_strict_objects(schema["items"])
    for branch in schema.get("anyOf", []):
        _assert_strict_objects(branch)


def test_default_and_explicit_canonical_schema_keep_the_existing_v1_crossproduct(catalogues):
    original = deepcopy(catalogues)
    canonical = rendering.expression_schema(**catalogues)
    assert rendering.EVIDENCE_EXPRESSION_CONTRACT == "evidence_expression_v1"
    assert "anyOf" not in canonical
    assert canonical["properties"]["operator"]["enum"] == list(rendering.OPERATORS)
    assert canonical["properties"]["source_ids"]["items"]["enum"] == list(catalogues["spans"])
    assert canonical["properties"]["record_ids"]["items"]["enum"] == list(catalogues["records"])
    assert canonical["properties"]["focus"]["enum"] == list(rendering.FOCUSES)
    _assert_strict_objects(canonical)
    assert catalogues == original


def test_explicit_generation_false_is_exactly_the_existing_canonical_schema(catalogues):
    assert rendering.expression_schema(**catalogues, generation=False) == (
        rendering.expression_schema(**catalogues))


def test_generation_has_one_strict_branch_per_operator_and_compiles_as_nested_wire(catalogues):
    original = deepcopy(catalogues)
    schema = _generation(catalogues)
    branches = schema["anyOf"]
    assert [branch["properties"]["operator"]["enum"] for branch in branches] == [
        [operator] for operator in rendering.OPERATORS]
    _assert_strict_objects(schema)
    wire = on_the_wire({"type": "object", "additionalProperties": False,
                        "required": ["expression"], "properties": {"expression": schema}})
    assert wire["properties"]["expression"] == schema
    assert catalogues == original
    assert all(not {"text", "span_ids", "inline_citations", "expression_contract",
                    "references", "rendering_seal"}.intersection(branch["properties"])
               for branch in branches)


@pytest.mark.parametrize("operator", rendering.OPERATORS)
def test_generation_admits_supported_neighbour_for_every_operator(catalogues, operator):
    selected = _supported(operator)
    before = deepcopy(selected), deepcopy(catalogues)
    require_schema(selected, _generation(catalogues))
    require_schema(selected, rendering.expression_schema(**catalogues))
    rendered = rendering.render_expression(selected, **catalogues)
    assert rendered["text"].strip()
    if operator == "checked_legal":
        assert LAW in rendered["text"] and rendered["legal_source_ids"] == ["legal:1"]
    assert (selected, catalogues) == before


@pytest.mark.parametrize("operator", ["acknowledgment", "record_result"])
@pytest.mark.parametrize("field,value", [
    ("source_ids", ["L1"]), ("record_ids", ["material:1"]),
    ("legal_source_ids", ["legal:1"]), ("focus", "attribution"),
])
def test_fixed_generation_excludes_owned_but_inapplicable_evidence_and_focus(
        catalogues, operator, field, value):
    selected = _selected(operator)
    selected[field] = value
    # Canonical shape stays broad; its renderer still owns the consequential
    # composition check and rejects this rather than silently clearing IDs.
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("operator", ["source_account", "checked_legal", "comparison",
                                      "limitation"])
def test_generation_does_not_offer_focus_for_an_operator_that_cannot_use_it(catalogues, operator):
    selected = {**_supported(operator), "focus": "actor"}
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("operator", ["source_account", "comparison", "question",
                                      "next_work", "limitation"])
def test_nonlegal_generation_does_not_offer_direct_legal_selectors(catalogues, operator):
    selected = {**_supported(operator), "legal_source_ids": ["legal:1"]}
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("operator", ["source_account", "comparison", "question",
                                      "next_work", "limitation"])
def test_nonlegal_record_choices_exclude_finding_rows(catalogues, operator):
    selected = {**_supported(operator), "record_ids": ["research:1"]}
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("record_id", ["material:1", "dispute:1"])
def test_legal_generation_cannot_use_matter_formulations_as_checked_findings(catalogues, record_id):
    selected = _selected("checked_legal", records=(record_id,))
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("record_id", ["material:1", "dispute:1"])
def test_account_generation_retains_current_owned_record_without_requiring_new_work(
        catalogues, record_id):
    selected = _selected("source_account", records=(record_id,))
    require_schema(selected, _generation(catalogues))
    assert rendering.render_expression(selected, **catalogues)["record_ids"] == [record_id]


@pytest.mark.parametrize("record_id", ["research:1", "requirement:1"])
def test_legal_generation_retains_both_existing_owned_finding_types(catalogues, record_id):
    selected = _selected("checked_legal", records=(record_id,))
    require_schema(selected, _generation(catalogues))
    result = rendering.render_expression(selected, **catalogues)
    assert result["record_ids"] == [record_id]
    assert result["legal_source_ids"] == ["legal:1"]


def test_account_generation_excludes_nm_words_without_widening_canonical_account_authority(
        catalogues):
    selected = _selected("source_account", sources=("P1S1",))
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation, match="NM's words"):
        rendering.render_expression(selected, **catalogues)
    with pytest.raises(SchemaViolation):
        require_schema(selected, _generation(catalogues))


@pytest.mark.parametrize("operator", ["comparison", "question", "next_work", "limitation"])
def test_nm_words_remain_available_as_attributed_context_for_other_operators(catalogues, operator):
    selected = _selected(operator, sources=("L1", "P1S1"),
                         focus="attribution" if operator in ("question", "next_work") else "none")
    require_schema(selected, _generation(catalogues))
    rendered = rendering.render_expression(selected, **catalogues)
    assert "NM's earlier message includes" in rendered["text"]
    assert rendered["span_ids"] == ["L1", "P1S1"]


def test_generation_keeps_direct_checked_passage_and_original_account_together(catalogues):
    selected = _selected("checked_legal", sources=("L1",), legal=("legal:1",))
    require_schema(selected, _generation(catalogues))
    rendered = rendering.render_expression(selected, **catalogues)
    assert NEGATED_ACCOUNT in rendered["text"] and LAW in rendered["text"]
    assert rendered["span_ids"] == ["L1"] and rendered["legal_source_ids"] == ["legal:1"]


@pytest.mark.parametrize("operator", ["acknowledgment", "record_result", "limitation"])
def test_empty_catalogues_keep_legitimate_fixed_and_unresolved_generation(operator):
    empty = {"spans": {}, "records": {}, "sources": {}}
    selected = expression(operator, sources=())
    schema = _generation(empty)
    require_schema(selected, schema)
    assert rendering.render_expression(selected, **empty)["text"].strip()
    with pytest.raises(SchemaViolation):
        require_schema({**selected, "legal_source_ids": []}, schema)


def test_generation_does_not_forbid_harmless_repeated_owned_selections(catalogues):
    selected = _selected("source_account", sources=("L1", "L1"),
                         records=("material:1", "material:1"))
    require_schema(selected, _generation(catalogues))
    rendered = rendering.render_expression(selected, **catalogues)
    assert rendered["span_ids"] == ["L1"] and rendered["record_ids"] == ["material:1"]


def test_saved_v1_omitted_legal_selector_keeps_exact_canonical_rendering(catalogues):
    legacy = expression("checked_legal", records=("research:1",))
    before = deepcopy(legacy), deepcopy(catalogues)
    rendered = rendering.render_expression(legacy, **catalogues)
    saved = {"id": "old-legal", "kind": "assessment", "uncertainty": "conditional",
             "evidence_expression": legacy,
             "expression_contract": "evidence_expression_v1", **rendered}
    rendering.validate_rendered_block(saved, **catalogues)
    assert rendered["legal_source_ids"] == ["legal:1"] and LAW in rendered["text"]
    assert "legal_source_ids" not in saved["evidence_expression"]
    assert (legacy, catalogues) == before


def test_saved_empty_direct_selector_keeps_smaller_replay_dependency_pool(catalogues):
    selected = _selected("source_account", sources=("L1",))
    before = deepcopy(selected), deepcopy(catalogues)
    expected = rendering.render_expression(selected, **catalogues)
    replay = {**catalogues, "sources": {}}
    assert rendering.render_expression(selected, **replay) == expected
    assert (selected, catalogues) == before


def test_canonical_distinct_comparison_check_is_not_replaced_by_generation(catalogues):
    selected = _selected("comparison", sources=("L1", "L1"))
    require_schema(selected, rendering.expression_schema(**catalogues))
    with pytest.raises(SchemaViolation, match="at least two distinct"):
        rendering.render_expression(selected, **catalogues)
