"""A saved source is exactly its captured evidence, never new defaults."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date

import pytest
from nm.ports.evidence import Finding, Origin

from tests.test_independent_claim_verifier import finding

pytestmark = pytest.mark.class_a


def test_the_pure_finding_contract_survives_actual_json_round_trip_without_promotion():
    source = finding(
        supports=None, origin=Origin.SEARCHED, confidence=0.7, valid_to=date(2030, 1, 1)
    )
    record = source.as_record()
    restored = Finding.from_record(json.loads(json.dumps(record, allow_nan=False)))
    assert restored == source and restored.supports is None
    assert restored.origin is Origin.SEARCHED and restored.confidence == 0.7
    assert restored.as_record() == record


@pytest.mark.parametrize("name", list(finding().as_record()))
def test_every_absent_field_is_refused_instead_of_filled_from_defaults(name):
    record = finding().as_record()
    assert name in record
    del record[name]
    with pytest.raises(ValueError, match="exactly all"):
        Finding.from_record(record)


@pytest.mark.parametrize("name", list(finding().as_record()["treatment"]))
def test_every_missing_treatment_field_is_refused(name):
    record = finding().as_record()
    del record["treatment"][name]
    with pytest.raises(ValueError, match="treatment metadata"):
        Finding.from_record(record)


@pytest.mark.parametrize(
    "change",
    [
        {"supports": "true"},
        {"origin": "invented"},
        {"binding": "invented"},
        {"source_kind": "invented"},
        {"para_kind": "invented"},
        {"valid_from": "20200101"},
        {"valid_to": False},
        {"confidence": float("nan")},
        {"confidence": True},
        {"span": " "},
        {"locator": " "},
        {"store": " "},
        {"ref": " "},
        {"proposition": " "},
        {"unknown_metadata": "not allowed"},
    ],
)
def test_malformed_values_and_extra_metadata_do_not_become_typed_evidence(change):
    record = finding().as_record()
    assert set(change) <= set(record) or set(change) == {"unknown_metadata"}
    record.update(change)
    with pytest.raises(ValueError):
        Finding.from_record(record)


def test_nested_unknown_metadata_is_refused_and_original_receipt_not_mutated():
    record = finding().as_record()
    held = deepcopy(record)
    record["treatment"]["state"] = "unsupported-state"
    with pytest.raises(ValueError):
        Finding.from_record(record)
    assert record["treatment"]["state"] == "unsupported-state"
    assert held["treatment"]["state"] == "clean"
