"""Source-purpose generation exposes the existing role/portion admission rule.

Declared labels exercise shape and ownership only. These tests do not establish
that a real model classifies original conversation purpose correctly.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

ACCOUNT_ROLES = ("reported_matter_account", "reported_party_position", "mixed")
OTHER_ROLES = ("examination_material", "work_instruction", "nm_interpretation", "uncertain")
REFERENCE = {
    "turn_id": "original", "role": "advocate",
    "quoted": "The witness cannot confirm whether the seal was intact.",
}


@pytest.fixture(params=(False, True), ids=("declared", "strict-wire"))
def schema(request):
    value = owner._source_proposal_schema({"L1": REFERENCE})
    return on_the_wire(value) if request.param else value


def declared(role, portions):
    return {"source_treatments": {"L1": {
        "content_role": role, "reason": "The fixture independently declares original purpose.",
        "substantive_spans": deepcopy(portions),
    }}}


@pytest.mark.parametrize("role", ACCOUNT_ROLES)
def test_account_roles_offer_nonempty_exact_portions_without_changing_words_or_role(schema, role):
    portions = [{"start": 0, "end": len(REFERENCE["quoted"])}]
    row = declared(role, portions)
    before = deepcopy(row), deepcopy(REFERENCE)

    require_schema(row, schema)
    canonical = owner._source_proposal(REFERENCE, row["source_treatments"]["L1"], source_id="L1")

    assert canonical["content_role"] == role
    assert canonical["quoted"] == REFERENCE["quoted"]
    assert canonical["substantive_spans"][0]["quoted"] == REFERENCE["quoted"]
    assert (row, REFERENCE) == before


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_every_nonaccount_and_unresolved_role_remains_available_with_empty_portions(schema, role):
    row = declared(role, [])
    before = deepcopy(row)

    require_schema(row, schema)
    canonical = owner._source_proposal(REFERENCE, row["source_treatments"]["L1"], source_id="L1")

    assert canonical["content_role"] == role and canonical["substantive_spans"] == []
    assert row == before


@pytest.mark.parametrize("role,portions", [
    *((role, []) for role in ACCOUNT_ROLES),
    *((role, [{"start": 0, "end": 1}]) for role in OTHER_ROLES),
])
def test_generation_rejects_role_portion_contradictions_before_canonical_admission(
        schema, role, portions):
    row = declared(role, portions)
    before = deepcopy(row)

    with pytest.raises(SchemaViolation):
        require_schema(row, schema)

    assert row == before


@pytest.mark.parametrize("role", ACCOUNT_ROLES)
def test_short_separate_and_overlapping_portions_remain_allowed(schema, role):
    for portions in (
            [{"start": 0, "end": 1}],
            [{"start": 0, "end": 3}, {"start": 8, "end": 12}],
            [{"start": 0, "end": 12}, {"start": 8, "end": 20}]):
        row = declared(role, portions)
        before = deepcopy(row)
        require_schema(row, schema)
        canonical = owner._source_proposal(
            REFERENCE, row["source_treatments"]["L1"], source_id="L1")
        assert [(item["start"], item["end"], item["quoted"])
                for item in canonical["substantive_spans"]] == [
                    (item["start"], item["end"], REFERENCE["quoted"][item["start"]:item["end"]])
                    for item in portions]
        assert row == before


@pytest.mark.parametrize("mutation", ("boolean_start", "negative_start", "beyond_owned_end",
                                     "copied_words", "foreign_role", "foreign_source"))
def test_partition_preserves_existing_endpoint_and_field_ownership(schema, mutation):
    row = declared("reported_matter_account", [{"start": 0, "end": len(REFERENCE["quoted"])}])
    treatment = row["source_treatments"]["L1"]
    portion = treatment["substantive_spans"][0]
    if mutation == "boolean_start":
        portion["start"] = False
    elif mutation == "negative_start":
        portion["start"] = -1
    elif mutation == "beyond_owned_end":
        portion["end"] += 1
    elif mutation == "copied_words":
        portion["quoted"] = REFERENCE["quoted"]
    elif mutation == "foreign_role":
        treatment["content_role"] = "unsupported-role"
    else:
        row["source_treatments"]["foreign"] = row["source_treatments"].pop("L1")
    before = deepcopy(row)

    with pytest.raises(SchemaViolation):
        require_schema(row, schema)

    assert row == before


def test_each_source_branch_uses_its_own_original_endpoint_bound():
    references = {"short": {**REFERENCE, "quoted": "Unknown."}, "long": REFERENCE}
    schema = on_the_wire(owner._source_proposal_schema(references))
    row = {"source_treatments": {
        identity: {"content_role": "reported_matter_account", "reason": "Explicit fixture role.",
                   "substantive_spans": [{"start": 0, "end": len(reference["quoted"])}]}
        for identity, reference in references.items()}}
    require_schema(row, schema)
    row["source_treatments"]["short"]["substantive_spans"][0]["end"] = len(REFERENCE["quoted"])

    with pytest.raises(SchemaViolation):
        require_schema(row, schema)
