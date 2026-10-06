"""Mechanical wire conversion only; these checks establish no semantic verdict."""
from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_source_support_coverage import treatment

REFERENCES = {
    "L1": {"turn_id": "account", "role": "advocate",
           "quoted": "The carrier may have received three crates, but the count is unconfirmed."},
    "L2": {"turn_id": "account", "role": "advocate", "quoted": "A receipt exists."},
    "L3": {"turn_id": "review", "role": "advocate", "quoted": "Review the description."},
}


def _schema(properties):
    return {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "verdict", "operation_supported", "reason", *properties],
        "properties": {
            "candidate_id": {"type": "string", "enum": ["D1"]},
            "verdict": {"type": "string", "enum": ["accept", "reject"]},
            "operation_supported": {"type": "boolean"},
            "reason": {"type": "string", "minLength": 1},
            **properties,
        },
    }


def _canonical_properties():
    return record.review_properties(tuple(REFERENCES), (), (), source_references=REFERENCES)


def _independent_wire_schema():
    # Supply the declared caller schema directly so conversion tests do not
    # depend on the new producer option being implemented first.
    properties = deepcopy(_canonical_properties())
    account = properties["account_check"]
    account["required"].remove("source_ids")
    del account["properties"]["source_ids"]
    return _schema(properties)


def _check(identity, *, supplies, supports):
    return {
        "source_id": identity, "supplies_account_content": supplies,
        "supports_proposal": supports,
        "support_spans": [{"start": 0, "end": len(REFERENCES[identity]["quoted"])}]
        if supplies else [],
        "reason": f"The original {identity} passage has this independently selected role.",
    }


def _wire_row():
    return {
        "candidate_id": "D1", "verdict": "accept", "operation_supported": True,
        "reason": "The attributed proposition was independently examined.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False,
            "source_checks": [
                _check("L3", supplies=False, supports=False),
                _check("L1", supplies=True, supports=True),
                _check("L2", supplies=True, supports=False),
            ],
            "reason": "Account support is distinct from review authority and contextual content.",
        },
        "target_checks": [],
    }


def _convert(row, *, source_ids=frozenset(REFERENCES), schema=None):
    return record.canonical_review_from_wire(
        row, schema=_independent_wire_schema() if schema is None else schema,
        source_ids=source_ids)


def _strict_objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
            assert set(schema["required"]) == set(schema["properties"])
            assert len(schema["required"]) == len(set(schema["required"]))
        for value in schema.values():
            _strict_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            _strict_objects(value)


def test_default_canonical_properties_preserve_the_existing_complete_contract():
    properties = _canonical_properties()
    before = deepcopy(properties)
    row = _wire_row()
    row["account_check"]["source_ids"] = ["L3", "L1", "L2"]
    require_schema(row, _schema(properties))
    _strict_objects(on_the_wire(_schema(properties)))
    assert "source_ids" in properties["account_check"]["required"]
    assert "source_ids" in properties["account_check"]["properties"]
    assert properties == before


def test_wire_properties_remove_only_the_redundant_source_selection():
    canonical = _canonical_properties()
    before = deepcopy((canonical, REFERENCES))
    wire = record.review_properties(tuple(REFERENCES), (), (),
                                    source_references=REFERENCES, wire=True)
    assert _schema(wire) == _independent_wire_schema()
    assert record.review_properties(tuple(REFERENCES), (), (),
                                    source_references=REFERENCES, wire=False) == canonical
    assert (canonical, REFERENCES) == before
    provider = on_the_wire(_schema(wire))
    _strict_objects(provider)
    support = provider["properties"]["account_check"]["properties"][
        "source_checks"]["items"]["properties"]["support_spans"]["items"]
    assert support["properties"]["start"]["maximum"] == max(
        len(row["quoted"]) for row in REFERENCES.values())
    assert support["properties"]["end"]["maximum"] == max(
        len(row["quoted"]) for row in REFERENCES.values())


def test_conversion_keeps_support_negative_and_context_checks_in_selected_order():
    row = _wire_row()
    schema = _independent_wire_schema()
    before = deepcopy((row, schema, REFERENCES))

    canonical = _convert(row, schema=schema)

    expected = deepcopy(row)
    expected["account_check"]["source_ids"] = ["L3", "L1", "L2"]
    assert canonical == expected
    require_schema(canonical, _schema(_canonical_properties()))
    assert record.validate_record_checks(
        canonical, source_ids=set(REFERENCES), target_ids=set(),
        candidate_id="D1", candidates={"D1": set()},
        source_treatments={identity: treatment(
            reference, role="work_instruction" if identity == "L3" else "reported_matter_account")
            for identity, reference in REFERENCES.items()})
    assert (row, schema, REFERENCES) == before
    canonical["account_check"]["source_checks"][1]["support_spans"][0]["end"] = 1
    canonical["target_checks"].append({"server_copy": True})
    assert (row, schema, REFERENCES) == before


def test_empty_negative_review_converts_without_inventing_support():
    row = _wire_row()
    row.update(verdict="reject", operation_supported=False)
    row["account_check"].update(supported=False, source_checks=[])
    before = deepcopy(row)

    canonical = _convert(row)

    assert canonical["account_check"]["source_ids"] == []
    assert canonical["account_check"]["source_checks"] == []
    assert canonical["verdict"] == "reject" and canonical["operation_supported"] is False
    require_schema(canonical, _schema(_canonical_properties()))
    assert row == before


@pytest.mark.parametrize("contradictory", (False, True))
def test_repeated_check_ids_are_not_coalesced_even_when_the_schema_accepts_them(contradictory):
    row = _wire_row()
    repeated = deepcopy(row["account_check"]["source_checks"][1])
    if contradictory:
        repeated.update(supplies_account_content=False, supports_proposal=False, support_spans=[])
    row["account_check"]["source_checks"].append(repeated)
    before = deepcopy(row)
    require_schema(row, _independent_wire_schema())

    with pytest.raises(SchemaViolation):
        _convert(row)

    assert row == before


def test_conversion_checks_candidate_ownership_beyond_the_shared_schema_catalogue():
    row = _wire_row()
    before = deepcopy(row)
    require_schema(row, _independent_wire_schema())

    with pytest.raises(SchemaViolation):
        _convert(row, source_ids={"L1"})

    assert row == before


@pytest.mark.parametrize("fault", (
    "authored_empty_ids", "authored_populated_ids", "foreign_check", "missing_flag",
    "string_flag", "unknown_account_field", "unknown_check_field", "unknown_span_field",
    "unknown_verdict_field", "endpoint_overrun", "boolean_endpoint",
))
def test_invalid_wire_fields_fail_before_conversion_without_mutation(fault):
    row = _wire_row()
    account = row["account_check"]
    check = account["source_checks"][1]
    if fault == "authored_empty_ids":
        account["source_ids"] = []
    elif fault == "authored_populated_ids":
        account["source_ids"] = ["L1", "L1"]
    elif fault == "foreign_check":
        check["source_id"] = "foreign"
    elif fault == "missing_flag":
        del check["supports_proposal"]
    elif fault == "string_flag":
        check["supplies_account_content"] = "true"
    elif fault == "unknown_account_field":
        account["certainty"] = "proved"
    elif fault == "unknown_check_field":
        check["quoted"] = "Model-authored source words"
    elif fault == "unknown_span_field":
        check["support_spans"][0]["quoted"] = "Model-authored source words"
    elif fault == "unknown_verdict_field":
        row["model_decision"] = {"verdict": "accept"}
    elif fault == "endpoint_overrun":
        check["support_spans"][0]["end"] = len(REFERENCES["L1"]["quoted"]) + 1
    elif fault == "boolean_endpoint":
        check["support_spans"][0]["start"] = True
    before = deepcopy(row)
    schema = _independent_wire_schema()
    schema_before = deepcopy(schema)

    with pytest.raises(SchemaViolation):
        _convert(row, schema=schema)

    assert row == before and schema == schema_before


@pytest.mark.parametrize("sources", (["L3", "L1", "L1", "L2"], ["L1"]))
def test_existing_canonical_checks_still_reject_duplicate_or_contradictory_id_lists(sources):
    row = _wire_row()
    row["account_check"]["source_ids"] = sources
    before = deepcopy(row)

    with pytest.raises(SchemaViolation):
        record.validate_record_checks(
            row, source_ids=set(REFERENCES), target_ids=set(), candidate_id="D1",
            candidates={"D1": set()}, source_treatments={
                identity: treatment(reference) for identity, reference in REFERENCES.items()})

    assert row == before
