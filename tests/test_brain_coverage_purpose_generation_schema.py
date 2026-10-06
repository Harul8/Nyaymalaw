"""Fresh coverage offers the owner's established purpose/portion invariant.

Explicit fixture labels test generation shape, not semantic source purpose.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

REFERENCE = {"turn_id": "original", "role": "advocate",
             "quoted": "The witness cannot identify who removed the seal."}
REFERENCES = {"L1": REFERENCE}


@pytest.fixture(params=(False, True), ids=("declared", "strict-wire"))
def schema(request):
    value = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES)
    return on_the_wire(value) if request.param else value


def coverage(purpose, portions):
    return {
        "state": "unassessed" if purpose == "unresolved" else "complete",
        "reason": "The fixture declares original purpose and the authorised coverage scope.",
        "source_checks": [{
            "source_id": "L1", "content_purpose": purpose,
            "substantive_spans": deepcopy(portions),
            "reason": "The fixture independently declares this original source purpose.",
        }],
        "dispositions": [{
            "source_id": "L1", "start": 0, "end": len(REFERENCE["quoted"]),
            "status": "outside_scope", "record_ids": [], "candidate_ids": [],
            "reason": "The fixture declares this account outside the current stage's scope.",
        }] if purpose == "account" else [],
    }


@pytest.mark.parametrize("purpose,portions", [
    ("account", [{"start": 0, "end": len(REFERENCE["quoted"])}]),
    ("non_account", []),
    ("unresolved", []),
])
def test_every_legitimate_purpose_has_its_applicable_native_portion_shape(
        schema, purpose, portions):
    row = coverage(purpose, portions)
    before = deepcopy(row), deepcopy(REFERENCES)
    require_schema(row, schema)
    checked = owner.checked_coverage(row, tuple(REFERENCES), source_references=REFERENCES)
    assert checked["source_checks"][0]["content_purpose"] == purpose
    assert checked["source_checks"][0]["substantive_spans"] == owner.owned_source_portions(
        REFERENCE, portions, source_id="L1")
    assert checked["missing_source_ids"] == (["L1"] if purpose == "unresolved" else [])
    assert (row, REFERENCES) == before


@pytest.mark.parametrize("purpose,portions", [
    ("account", []),
    ("non_account", [{"start": 0, "end": 1}]),
    ("unresolved", [{"start": 0, "end": 1}]),
])
def test_native_generation_rejects_purpose_portion_contradictions(schema, purpose, portions):
    row = coverage(purpose, portions)
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        require_schema(row, schema)
    assert row == before


@pytest.mark.parametrize("portions", [
    [{"start": 0, "end": 1}],
    [{"start": 0, "end": 3}, {"start": 8, "end": 12}],
    [{"start": 0, "end": 12}, {"start": 8, "end": 20}],
])
def test_positive_purpose_keeps_short_separate_and_overlapping_owned_portions(schema, portions):
    row = coverage("account", portions)
    require_schema(row, schema)
    checked = owner.checked_coverage(row, tuple(REFERENCES), source_references=REFERENCES)
    assert [portion["quoted"] for portion in checked["source_checks"][0]["substantive_spans"]] == [
        REFERENCE["quoted"][portion["start"]:portion["end"]] for portion in portions]


@pytest.mark.parametrize("fault", ("foreign_source", "foreign_purpose", "copied_words",
                                  "boolean_endpoint", "beyond_owned_end"))
def test_purpose_partition_preserves_existing_source_and_span_constraints(schema, fault):
    row = coverage("account", [{"start": 0, "end": len(REFERENCE["quoted"])}])
    check = row["source_checks"][0]
    portion = check["substantive_spans"][0]
    if fault == "foreign_source":
        check["source_id"] = "foreign"
    elif fault == "foreign_purpose":
        check["content_purpose"] = "unoffered-purpose"
    elif fault == "copied_words":
        portion["quoted"] = REFERENCE["quoted"]
    elif fault == "boolean_endpoint":
        portion["start"] = False
    else:
        portion["end"] += 1
    with pytest.raises(SchemaViolation):
        require_schema(row, schema)


def test_explicit_historical_three_field_coverage_keeps_its_existing_shape():
    row = {"state": "complete", "reason": "Explicit historical coverage.", "missing_source_ids": []}
    schema = owner.coverage_schema(tuple(REFERENCES))
    require_schema(row, on_the_wire(schema))
    assert owner.checked_coverage(row, tuple(REFERENCES)) == row


def test_empty_owned_source_catalogue_remains_valid_without_inventing_checks():
    row = {"state": "complete", "reason": "No sources in this owned scope.",
           "source_checks": [], "dispositions": []}
    schema = owner.coverage_schema((), source_references={})
    require_schema(row, on_the_wire(schema))
    checked = owner.checked_coverage(row, (), source_references={})
    assert checked["source_checks"] == [] and checked["dispositions"] == []
