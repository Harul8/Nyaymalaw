"""Fresh coverage offers only mechanically meaningful representation choices."""
from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

REFERENCE = {"turn_id": "owned", "role": "advocate", "quoted": "An attributed account."}


def schema(records=(), candidates=(), wire=False):
    value = record.coverage_schema(
        ("L1",), source_references={"L1": REFERENCE},
        record_ids=records, candidate_ids=candidates)
    return on_the_wire(value) if wire else value


def row(status="represented", records=(), candidates=()):
    return {"state": "partial", "reason": "Original evidence examined.",
            "source_checks": [{"source_id": "L1", "content_purpose": "account",
                               "substantive_spans": [{"start": 0, "end": 22}],
                               "reason": "The advocate supplied this account."}],
            "dispositions": [{"source_id": "L1", "start": 0, "end": 22,
                              "status": status, "record_ids": list(records),
                              "candidate_ids": list(candidates),
                              "reason": "This portion has the selected disposition."}]}


@pytest.mark.parametrize("wire", [False, True])
@pytest.mark.parametrize("records,candidates", [((), ()), (("R1",), ()),
                                              ((), ("C1",)), (("R1",), ("C1",))])
def test_represented_without_any_owned_representation_is_not_offered(wire, records, candidates):
    with pytest.raises(SchemaViolation):
        require_schema(row(), schema(records, candidates, wire))


@pytest.mark.parametrize("wire", [False, True])
@pytest.mark.parametrize("records,candidates", [(("R1",), ()), ((), ("C1",)),
                                              (("R1",), ("C1",))])
def test_legitimate_record_candidate_and_shared_representation_remain_available(
        wire, records, candidates):
    value = row(records=records, candidates=candidates)
    before = deepcopy(value)
    require_schema(value, schema(("R1",), ("C1",), wire))
    assert value == before


@pytest.mark.parametrize("status", ["missing", "unresolved", "non_account", "outside_scope"])
@pytest.mark.parametrize("wire", [False, True])
def test_unrepresented_judgments_keep_empty_owned_arrays(status, wire):
    require_schema(row(status), schema(("R1",), ("C1",), wire))
    for value in [row(status, records=("R1",)), row(status, candidates=("C1",))]:
        with pytest.raises(SchemaViolation):
            require_schema(value, schema(("R1",), ("C1",), wire))


def test_generated_choice_does_not_bypass_actual_admission_or_support():
    value = row(candidates=("C1",))
    value["state"] = "complete"
    require_schema(value, schema(candidates=("C1",)))
    with pytest.raises(SchemaViolation, match="not actually admitted"):
        record.checked_coverage(value, ("L1",), source_references={"L1": REFERENCE},
                                candidate_ids=("C1",), admitted_candidate_ids=())
    with pytest.raises(SchemaViolation):
        require_schema(row(records=("foreign",)), schema(records=("R1",)))


def test_historical_coverage_shape_and_legitimate_empty_account_read_are_preserved():
    legacy = record.coverage_schema(("L1",))
    assert set(legacy["properties"]) == {"state", "reason", "missing_source_ids"}
    require_schema({"state": "complete", "reason": "Original review complete.",
                    "missing_source_ids": []}, legacy)
    value = row("non_account")
    value["state"] = "complete"
    value["source_checks"][0].update(content_purpose="non_account", substantive_spans=[])
    assert record.checked_coverage(value, ("L1",),
                                   source_references={"L1": REFERENCE})["state"] == "complete"
