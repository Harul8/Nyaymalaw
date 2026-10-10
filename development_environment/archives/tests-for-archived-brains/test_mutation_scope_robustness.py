"""Malformed durable data, truthful support and exact span identity neighbours."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_state as projection
from nm.brain import mutation_contracts as contracts
from nm.shared.model_port import SchemaViolation
from tests.test_brain_dispute_mutation_projection import fixture, original_ids
from tests.test_mutation_admission_adapters import (
    OWNER,
    SOURCES,
    TARGETS,
    candidate,
    decision,
    ledger,
    scope,
)


@pytest.mark.parametrize("relation", [[], {}, None, True, 1, "unowned-operation"])
@pytest.mark.parametrize("operation", ["select", "authorize", "saved"])
def test_malformed_relation_stays_in_schema_boundary(relation, operation):
    grant = ledger()
    reference = {key: SOURCES["L1"][key] for key in ("turn_id", "role", "quoted")}
    arguments = dict(ledger=grant, owner=OWNER, snapshot_version=1,
                     relation=relation, target_ids=["date"],
                     current_source_reference=reference)
    with pytest.raises(SchemaViolation):
        if operation == "select":
            contracts.candidate_authority_ids(**arguments)
        elif operation == "authorize":
            contracts.authorize_mutation(
                **arguments, authority_ids=[grant["authorities"][0]["id"]],
                supporting_source_ids=["L1"])
        else:
            row = candidate().recorded("second", 0)
            row["relation"] = relation
            contracts.bind_record_mutation(row, grant, supporting_source_ids=["L1"])


@pytest.mark.parametrize("relation", [[], {}, None, True])
def test_malformed_durable_relation_preserves_original_disputes(relation):
    matter = fixture()
    turns = deepcopy(matter.brain_chat)
    turns[-1]["response"]["material"][0]["relation"] = relation
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}


@pytest.mark.parametrize("field,value", [
    ("id", []), ("request_index", {}), ("authority_kind", []),
    ("authority_source_ids", {}), ("target_scope", []),
    ("target_ids", {}), ("permitted_relations", {}),
])
def test_malformed_stored_grants_fail_with_schema_violation(field, value):
    grant = ledger()
    grant["authorities"][0][field] = value
    grant["seal"] = contracts._digest({key: row for key, row in grant.items() if key != "seal"})
    with pytest.raises(SchemaViolation):
        contracts.candidate_authority_ids(
            ledger=grant, owner=OWNER, snapshot_version=1,
            relation="corrects", target_ids=["date"],
            current_source_reference={key: SOURCES["L1"][key]
                                      for key in ("turn_id", "role", "quoted")})


def checked_support(*positive, negative=()):
    result = decision(*positive, *negative)
    for check in result["account_check"]["source_checks"]:
        if check["source_id"] in negative:
            check["supports_proposal"] = False
    return result


def test_negative_checked_context_is_not_relabelled_as_factual_support():
    checked = contracts.scoped_record_decisions(
        {"D1": checked_support("L1", negative=("P1S1",))},
        {"D1": candidate()}, scope(ledger()))
    assert checked["D1"]["verdict"] == "accept"
    binding = checked["D1"]["mutation_authority"]
    assert binding["supporting_source_ids"] == ["L1"]
    assert binding["attached_context_source_ids"] == ["P1S1"]


def test_review_instruction_and_earlier_support_keep_distinct_roles():
    checked_decision = checked_support("P1S1", negative=("L2",))
    checked_decision["account_check"]["source_checks"][1]["supplies_account_content"] = False
    checked = contracts.scoped_record_decisions(
        {"D1": checked_decision}, {"D1": candidate(quote=SOURCES["L2"]["quoted"])},
        scope(ledger(source="L2", kind="interpretation_review")))
    assert checked["D1"]["verdict"] == "accept"
    assert checked["D1"]["mutation_authority"]["supporting_source_ids"] == ["P1S1"]
    current = checked["D1"]["mutation_authority"]["current_source_reference"]
    assert current["quoted"] == SOURCES["L2"]["quoted"]


def test_no_positive_support_cannot_be_filled_by_selected_negative_sources():
    checked = contracts.scoped_record_decisions(
        {"D1": checked_support(negative=("L1", "P1S1"))},
        {"D1": candidate()}, scope(ledger()))
    assert checked["D1"]["admission_issue"] == "mutation_scope"
    assert "supporting_source_ids" in checked["D1"]["reason"]


def duplicate_source_ledger():
    sources = {**SOURCES, "L3": deepcopy(SOURCES["L1"])}
    return contracts.build_mutation_authorities(
        owner=OWNER, expected_version=1, target_catalogue=TARGETS,
        source_catalogue=sources, request_indices=[0, 1], proposals=[
            {"request_index": index, "authority_kind": "account_contribution",
             "authority_source_ids": [source], "target_scope": "exact",
             "target_ids": [target], "permitted_relations": ["corrects"]}
            for index, source, target in [(0, "L1", "date"), (1, "L3", "custody")]])


def test_owned_source_id_disambiguates_repeated_exact_words_without_widening_scope():
    grant = duplicate_source_ledger()
    row = candidate().recorded("second", 0)
    row["source_id"] = "L1"
    checked = contracts.scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": row}, scope(grant))
    assert checked["D1"]["verdict"] == "accept"
    certificate = checked["D1"]["mutation_authority"]
    assert certificate["current_source_reference"]["source_id"] == "L1"
    assert certificate["request_indices"] == [0]
    assert contracts.bind_record_mutation(row, grant, binding=certificate) == certificate
    row["source_id"] = "L3"
    checked = contracts.scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": row}, scope(grant))
    assert checked["D1"]["admission_issue"] == "mutation_scope"


def test_duplicate_words_without_owned_source_identity_remain_ambiguous():
    checked = contracts.scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": candidate()}, scope(duplicate_source_ledger()))
    assert checked["D1"]["admission_issue"] == "mutation_scope"
    assert "ambiguous current source" in checked["D1"]["reason"]


@pytest.mark.parametrize("source_id", ["L2", "invented", "", [], {}])
def test_owned_source_id_requires_its_exact_current_words(source_id):
    row = candidate().recorded("second", 0)
    row["source_id"] = source_id
    checked = contracts.scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": row}, scope(ledger()))
    assert checked["D1"]["admission_issue"] == "mutation_scope"


def test_existing_three_field_certificate_is_unchanged_and_replayable():
    grant = ledger()
    row = candidate().recorded("second", 0)
    checked = contracts.scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": row}, scope(grant))
    certificate = checked["D1"]["mutation_authority"]
    assert set(certificate["current_source_reference"]) == {"turn_id", "role", "quoted"}
    assert contracts.bind_record_mutation(row, grant, binding=certificate) == certificate


@pytest.mark.parametrize("source_id", ["L2", "unowned-source", "", None, [], {}])
def test_fresh_new_row_cannot_ignore_a_present_wrong_source_identity(source_id):
    matter = fixture(new=True)
    turns = deepcopy(matter.brain_chat)
    row = turns[-1]["response"]["material"][0]
    row["source_id"] = source_id
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}


@pytest.mark.parametrize("source_id", ["L1", "absent"])
def test_fresh_new_row_exact_source_or_older_missing_identity_needs_no_mutation_grant(source_id):
    matter = fixture(new=True)
    turns = deepcopy(matter.brain_chat)
    row = turns[-1]["response"]["material"][0]
    if source_id != "absent":
        row["source_id"] = source_id
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "ok"
    assert original_ids(result) == {"dispute-a", "dispute-b", "later-dispute"}


def test_fresh_new_owned_identity_does_not_require_or_invent_a_binding():
    grant = ledger()
    row = candidate(relation="new").recorded("second", 0)
    row["source_id"] = "L1"
    assert contracts.bind_record_mutation(row, grant) is None
    row["source_id"] = "L2"
    with pytest.raises(SchemaViolation, match="owned current source"):
        contracts.bind_record_mutation(row, grant)
