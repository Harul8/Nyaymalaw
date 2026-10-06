"""Fresh target availability is mechanical; canonical proof retains its contract."""

from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_record_review_wire import REFERENCES, _schema, _strict_objects, _wire_row
from tests.test_brain_source_support_coverage import treatment


def _properties(target_ids=(), *, wire=True):
    return record.review_properties(
        tuple(REFERENCES), target_ids, ("D1", "D2"),
        source_references=REFERENCES, wire=wire)


def _target(identity, *, peers=()):
    return {
        "target_id": identity, "identity_relation": "same_underlying_account",
        "account_preserved": True, "required_peer_ids": list(peers),
        "reason": "The owned prior account is preserved by the proposed replacement.",
    }


def _canonical(row, schema):
    return record.canonical_review_from_wire(row, schema=schema, source_ids=set(REFERENCES))


def _admit(row, target_ids=()):
    return record.validate_record_checks(
        row, source_ids=set(REFERENCES), target_ids=set(target_ids), candidate_id="D1",
        candidates={"D1": set(target_ids), "D2": set(target_ids)},
        source_treatments={
            identity: treatment(reference, role=(
                "work_instruction" if identity == "L3" else "reported_matter_account"))
            for identity, reference in REFERENCES.items()})


def test_fresh_provider_empty_target_catalogue_offers_only_an_empty_check_array():
    schema = _schema(_properties())
    before = deepcopy(schema)

    provider = on_the_wire(schema)

    assert provider["properties"]["target_checks"]["maxItems"] == 0
    _strict_objects(provider)
    assert schema == before


@pytest.mark.parametrize("verdict", ("accept", "reject"))
def test_fresh_empty_target_catalogue_rejects_invented_empty_string_target(verdict):
    row = _wire_row()
    row.update(verdict=verdict, operation_supported=verdict == "accept")
    row["target_checks"] = [_target("")]
    schema = _schema(_properties())
    before = deepcopy((row, schema))

    with pytest.raises(SchemaViolation):
        require_schema(row, on_the_wire(schema))
    with pytest.raises(SchemaViolation) as failure:
        _canonical(row, schema)

    assert "Review output contract mismatch" in str(failure.value)
    assert "not an original proposal defect" in str(failure.value)
    assert "target_checks" in str(failure.value)
    assert (row, schema) == before


@pytest.mark.parametrize("verdict", ("accept", "reject"))
def test_fresh_empty_target_catalogue_preserves_legitimate_empty_checks(verdict):
    row = _wire_row()
    row.update(verdict=verdict, operation_supported=verdict == "accept")
    if verdict == "reject":
        row["account_check"].update(supported=False, source_checks=[])
    schema = _schema(_properties())
    before = deepcopy((row, schema))

    require_schema(row, on_the_wire(schema))
    canonical = _canonical(row, schema)

    assert canonical["target_checks"] == []
    assert canonical["verdict"] == verdict
    assert canonical["account_check"]["source_ids"] == (
        ["L3", "L1", "L2"] if verdict == "accept" else [])
    require_schema(canonical, _schema(_properties(wire=False)))
    assert _admit(canonical) is (verdict == "accept")
    assert (row, schema) == before


def test_fresh_owned_replacement_targets_and_successor_peer_are_preserved():
    target_ids = ("prior-account-7", "prior-account-12")
    row = _wire_row()
    row["target_checks"] = [_target(identity, peers=("D2",)) for identity in target_ids]
    schema = _schema(_properties(target_ids))
    before = deepcopy((row, schema))
    provider = on_the_wire(schema)

    assert "maxItems" not in provider["properties"]["target_checks"]
    assert provider["properties"]["target_checks"]["items"]["properties"][
        "target_id"]["enum"] == list(target_ids)
    require_schema(row, provider)
    canonical = _canonical(row, schema)

    assert canonical["target_checks"] == row["target_checks"]
    require_schema(canonical, _schema(_properties(target_ids, wire=False)))
    assert _admit(canonical, target_ids)
    assert (row, schema) == before


def test_fresh_negative_review_may_leave_owned_targets_unchecked():
    target_ids = ("prior-account-7",)
    row = _wire_row()
    row.update(verdict="reject", operation_supported=False)
    row["account_check"].update(supported=False, source_checks=[])
    schema = _schema(_properties(target_ids))

    require_schema(row, on_the_wire(schema))
    canonical = _canonical(row, schema)

    assert canonical["target_checks"] == []
    assert not _admit(canonical, target_ids)


@pytest.mark.parametrize("identity", ("", "another-owner-target"))
def test_fresh_owned_target_catalogue_still_rejects_foreign_target_checks(identity):
    row = _wire_row()
    row["target_checks"] = [_target(identity)]
    schema = _schema(_properties(("prior-account-7",)))

    with pytest.raises(SchemaViolation):
        require_schema(row, on_the_wire(schema))


def test_canonical_empty_target_shape_is_unchanged_but_admission_still_checks_ownership():
    properties = _properties(wire=False)
    assert properties == record.review_properties(
        tuple(REFERENCES), (), ("D1", "D2"), source_references=REFERENCES)
    assert "maxItems" not in properties["target_checks"]
    assert properties["target_checks"]["items"]["properties"]["target_id"]["enum"] == [""]
    row = _wire_row()
    row["account_check"]["source_ids"] = ["L3", "L1", "L2"]
    row["target_checks"] = [_target("")]
    before = deepcopy((properties, row))

    # Retaining historical shape does not turn an unowned target into admitted proof.
    require_schema(row, _schema(properties))
    with pytest.raises(SchemaViolation, match="unowned target IDs"):
        _admit(row)

    assert (properties, row) == before


def test_fresh_empty_target_bound_does_not_mutate_canonical_or_owned_target_schemas():
    canonical = _properties(wire=False)
    owned = _properties(("prior-account-7",))
    before = deepcopy((canonical, owned, REFERENCES))

    empty = _properties()
    empty["target_checks"]["items"]["properties"]["target_id"]["enum"].append("draft")

    assert (canonical, owned, REFERENCES) == before
    assert _properties(wire=False) == canonical
    assert _properties(("prior-account-7",)) == owned


@pytest.mark.parametrize("supplies", (False, True))
def test_support_selection_feedback_locates_review_fields_without_blaming_original(supplies):
    row = _wire_row()
    check = row["account_check"]["source_checks"][1]
    check["supplies_account_content"] = supplies
    if supplies:
        check["support_spans"] = []
    before = deepcopy(row)
    canonical = _canonical(row, _schema(_properties()))

    with pytest.raises(SchemaViolation) as failure:
        _admit(canonical)

    message = str(failure.value)
    assert "account_check.source_checks for L1" in message
    assert "supplies_account_content" in message and "support_spans" in message
    assert "not a defect of the original account or proposal" in message
    assert row == before
