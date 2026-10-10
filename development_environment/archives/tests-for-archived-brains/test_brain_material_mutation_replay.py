"""Durable material projection requires the original admitted mutation scope."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message
from nm.brain.material_state import material_record
from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    authorize_mutation,
    build_mutation_authorities,
    candidate_authority_ids,
)
from nm.work_the_file.matter_contracts import Matter
from tests.brain_reader_fixture import scripted_source_treatments
from tests.test_brain_board_proposals import saved_turn
from tests.test_brain_material import material
from tests.test_brain_material_record import _record

EMPTY_DISPUTES = {"state": "ok", "history": [], "rows": []}
INITIAL = "The event happened on Monday. The document is with the client."
LATEST = "Sorry, Tuesday."
MATTER_ID = "material-authority"


def initial_row(*, quote="The event happened on Monday.", index=1, unchecked=False,
                scope="current"):
    row = _record(material("event", quote, quote, scope=scope, placement="matter"), "first", index)
    if not unchecked:
        row["grounding"] = "advocate_semantic_v1"
    else:
        row["statement"] = "An older unchecked interpretation adds a fact."
    return row


def owned_turn(turn_id, message, rows, execution=None):
    turn = saved_turn(turn_id, message, rows, matter_id=MATTER_ID)
    turn["offer_digest"] = "offer-for-" + turn_id
    turn["response"]["route"] = "matter"
    if execution is not None:
        turn["response"]["material_coverage"] = {"execution": execution}
    return turn


def matter_with(*turns):
    return Matter(id=MATTER_ID, advocate_id="adv", title="Reported chronology",
                  brain_ready=True, brain_chat=turns, version=len(turns))


def projection(matter):
    return material_record(matter, disputes=EMPTY_DISPUTES)


def fixture(*, unchecked=False, prior_scope="current", fresh_seed=False, relation="corrects",
            latest=LATEST, authority_kind="account_contribution", support="L1"):
    old = initial_row(unchecked=unchecked, scope=prior_scope)
    other = initial_row(quote="The document is with the client.", index=2)
    first = owned_turn("first", INITIAL, [old, other])
    if fresh_seed:
        seed_owner = {"matter_id": MATTER_ID, "advocate_id": "adv", "turn_id": "first",
                      "offer_digest": first["offer_digest"]}
        seed_ledger = build_mutation_authorities(
            owner=seed_owner, expected_version=0, target_catalogue={},
            source_catalogue=scripted_source_treatments((), INITIAL, turn_id="first"),
            proposals=[], request_indices=[0])
        first["response"]["material_coverage"] = {"execution": {
            "owner": seed_owner, "expected_version": 0,
            "mutation_authority_contract": AUTHORITY_CONTRACT,
            "mutation_authorities": seed_ledger,
        }}
    initial_matter = matter_with(first)
    before = projection(initial_matter)
    assert before["state"] == "ok"
    targets = {row["id"]: row for row in (*before["rows"], *before["excluded_scope"])}
    owner = {"matter_id": MATTER_ID, "advocate_id": "adv", "turn_id": "second",
             "offer_digest": "offer-for-second"}
    ledger = build_mutation_authorities(
        owner=owner, expected_version=1, target_catalogue=targets,
        source_catalogue=scripted_source_treatments(
            (Message("first", "advocate", INITIAL),), latest, turn_id="second"),
        request_indices=[0], proposals=[{
            "request_index": 0, "authority_kind": authority_kind,
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": [old["id"]], "permitted_relations": [relation],
        }])
    revised = _record(material(
        "event", "The event happened on Tuesday.", latest, scope="current", relation=relation,
        references=({"turn_id": "first", "role": "advocate", "quoted": old["quoted"]},),
        placement="matter", related_material_ids=(old["id"],)), "second", 1)
    revised["grounding"] = "advocate_semantic_v1"
    current = {"turn_id": "second", "role": "advocate", "quoted": latest}
    authorities = candidate_authority_ids(
        ledger=ledger, owner=owner, snapshot_version=1, relation=relation,
        target_ids=[old["id"]], current_source_reference=current)
    revised["mutation_authority"] = authorize_mutation(
        ledger=ledger, owner=owner, snapshot_version=1, authority_ids=authorities,
        relation=relation, target_ids=[old["id"]], current_source_reference=current,
        supporting_source_ids=[support], attached_context_source_ids=["P1S1"])
    execution = {"owner": owner, "expected_version": 1,
                 "mutation_authority_contract": AUTHORITY_CONTRACT,
                 "mutation_authorities": ledger}
    second = owned_turn("second", latest, [revised], execution)
    return matter_with(first, second), first, second


def test_saved_correction_retires_only_its_authorized_target_and_reopens_identically():
    matter, first, second = fixture(fresh_seed=True)
    original = deepcopy(matter)
    projected = projection(matter)
    assert projected["state"] == "ok"
    assert {row["id"] for row in projected["rows"]} == {
        "first:material:2", "second:material:1"}
    assert [row["id"] for row in projected["history"]] == [
        "first:material:1", "first:material:2", "second:material:1"]
    assert projected == projection(matter)
    assert matter == original and matter.brain_chat == (first, second)


@pytest.mark.parametrize("failure", ["missing_certificate", "wrong_target", "wrong_operation",
                                   "corrupt_ledger", "wrong_owner", "changed_support",
                                   "missing_ledger", "wrong_snapshot", "changed_original_source"])
def test_damaged_saved_scope_marks_projection_incomplete_without_retiring_the_predecessor(failure):
    matter, first, second = fixture()
    second = deepcopy(second)
    revised = second["response"]["material"][0]
    execution = second["response"]["material_coverage"]["execution"]
    if failure == "missing_certificate":
        revised.pop("mutation_authority")
    elif failure == "wrong_target":
        revised["related_material_ids"] = ["first:material:2"]
        revised["prior_references"] = [{"turn_id": "first", "role": "advocate",
                                        "quoted": "The document is with the client."}]
    elif failure == "wrong_operation":
        revised["relation"] = "withdraws"
    elif failure == "corrupt_ledger":
        execution["mutation_authorities"]["authorities"][0]["target_ids"].append("first:material:2")
    elif failure == "wrong_owner":
        second["offer_digest"] = "different-exact-offer"
    elif failure == "changed_support":
        revised["mutation_authority"]["supporting_source_ids"] = ["P1S2"]
    elif failure == "missing_ledger":
        execution.pop("mutation_authorities")
    elif failure == "wrong_snapshot":
        execution["expected_version"] = 2
    else:
        first = deepcopy(first)
        # Same current target has intact exact source; the other saved original
        # passage has drifted from a source dependency bound by the scope ledger.
        first["message"] = "The event happened on Monday. The document has another custodian."
        first["response"]["material"] = first["response"]["material"][:1]
    damaged = replace(matter, brain_chat=(first, second))
    projected = projection(damaged)
    assert projected["state"] == "incomplete"
    assert "first:material:1" in {row["id"] for row in projected["rows"]}
    assert "second:material:1" not in {row["id"] for row in projected["rows"]}
    assert any("invalid authority" in reason for reason in projected["problems"])


def test_fresh_repair_of_unchecked_legacy_interpretation_uses_the_owned_exact_word_snapshot():
    latest = "Restore the account from the earlier original passage."
    matter, _, _ = fixture(unchecked=True, latest=latest,
                          authority_kind="interpretation_review", support="P1S1")
    projected = projection(matter)
    assert projected["state"] == "ok"
    assert {row["id"] for row in projected["rows"]} == {
        "first:material:2", "second:material:1"}
    assert projected["rows"][1]["grounding"] == "advocate_semantic_v1"


def test_owned_scope_can_clarify_a_held_prior_account_without_false_target_rejection():
    matter, _, _ = fixture(prior_scope="uncertain")
    projected = projection(matter)
    assert projected["state"] == "ok" and projected["excluded_scope"] == []
    assert {row["id"] for row in projected["rows"]} == {
        "first:material:2", "second:material:1"}


def test_genuine_legacy_correction_remains_readable_as_untracked_history():
    matter, first, second = fixture()
    second = deepcopy(second)
    second["response"].pop("material_coverage")
    second["response"]["material"][0].pop("mutation_authority")
    projected = projection(replace(matter, brain_chat=(first, second)))
    assert projected["state"] == "ok"
    assert {row["id"] for row in projected["rows"]} == {
        "first:material:2", "second:material:1"}


def test_fresh_new_accounts_also_check_the_real_turn_owner_even_without_revision_bindings():
    matter, first, _ = fixture(fresh_seed=True)
    first = deepcopy(first)
    first["offer_digest"] = "different-exact-offer"
    projected = projection(replace(matter, brain_chat=(first,)))
    assert projected["state"] == "incomplete" and projected["rows"] == []
    assert any("actual turn owner" in reason for reason in projected["problems"])


def test_integrity_failure_on_one_saved_row_cannot_admit_its_unchecked_same_turn_peer():
    matter, first, second = fixture()
    second = deepcopy(second)
    second["response"]["material"][0].pop("mutation_authority")
    independent = _record(material(
        "event", "A separate event is reported.", LATEST, scope="current", placement="matter"),
        "second", 2)
    independent["grounding"] = "advocate_semantic_v1"
    second["response"]["material"].append(independent)
    projected = projection(replace(matter, brain_chat=(first, second)))
    assert projected["state"] == "incomplete"
    assert {row["id"] for row in projected["rows"]} == {"first:material:1", "first:material:2"}
