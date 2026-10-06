"""Durable scoped dispute changes revalidate authority before retiring records."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_state as projection
from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    bind_record_mutation,
    build_mutation_authorities,
)
from nm.work_the_file.matter_contracts import Matter

FIRST = "The first reported conduct is disputed."
SECOND = "The independently reported custody is contested."
LATEST = "Repair only the first sourced formulation."
MATTER_ID = "mutation-projection-matter"


def proposal(identity, words, *, source_turn="seed", target=None, relation=None, scope="current"):
    return {
        "id": identity, "source_turn_id": source_turn, "state": "proposed", "kind": "dispute",
        "statement": FIRST if target else words, "quoted": words,
        "relation": ("corrects" if target else "new") if relation is None else relation,
        "prior_references": ([{"turn_id": "seed", "role": "advocate", "quoted": FIRST},
                              {"turn_id": "seed", "role": "advocate", "quoted": SECOND}]
                             if target else []),
        "matter_scope": scope, "basis": "stated", "importance": "central",
        "why_material": "This contested account requires a practical conclusion.",
        "label": "First account" if target else words,
        "identification": "identified", "clarification": "",
        "related_dispute_ids": [target] if target else [],
        "grounding": "advocate_semantic_v1",
    }


def saved_turn(identity, message, proposals, *, execution=None):
    response = {"turn_id": identity, "elements": [{"text": "Supported reply."}],
                "material": proposals, "route": "matter"}
    if execution is not None:
        response["material_coverage"] = {"execution": execution}
    return {"turn_id": identity, "matter_id": MATTER_ID, "advocate_id": "owned-advocate",
            "offer_digest": "offered-" + identity, "message": message, "response": response,
            "elements": response["elements"], "committed": True, "release_state": "released"}


def base_matter():
    original = saved_turn("seed", FIRST + " " + SECOND, [
        proposal("dispute-a", FIRST), proposal("dispute-b", SECOND)])
    return Matter(id=MATTER_ID, advocate_id="owned-advocate", title="Attributed dispute",
                  brain_ready=True, version=1, brain_chat=(original,))


def fixture(*, new=False, legacy=False):
    baseline = base_matter()
    canonical = projection.proposed_disputes(baseline)
    assert canonical["state"] == "ok"
    owner = {"matter_id": MATTER_ID, "advocate_id": "owned-advocate", "turn_id": "later",
             "offer_digest": "offered-later"}
    _, current, prior = addressed_sources((Message("seed", "advocate", FIRST + " " + SECOND),),
                                          LATEST)
    sources = {
        **{identity: vars(reference) for identity, reference in prior.items()},
        **{identity: {"turn_id": "later", "role": "advocate", "quoted": words}
           for identity, words in current.items()},
    }
    ledger = build_mutation_authorities(
        owner=owner, expected_version=1, target_catalogue={
            row["id"]: row for row in canonical["rows"]}, source_catalogue=sources,
        proposals=[] if new else [{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": ["dispute-a"], "permitted_relations": ["corrects"],
        }], request_indices=(0,))
    row = proposal("later-dispute", LATEST, source_turn="later",
                   target=None if new else "dispute-a")
    if not new and not legacy:
        row["mutation_authority"] = bind_record_mutation(
            row, ledger, supporting_source_ids=["P1S1"])
    execution = {"owner": owner, "expected_version": 1,
                 "mutation_authority_contract": AUTHORITY_CONTRACT,
                 "mutation_authorities": ledger}
    later = saved_turn("later", LATEST, [row], execution=None if legacy else execution)
    matter = replace(baseline, version=2, brain_chat=(*baseline.brain_chat, later))
    return matter


def original_ids(result):
    return {row["id"] for row in result["rows"]}


def test_valid_bound_correction_retires_only_its_granted_target():
    matter = fixture()
    result = projection.proposed_disputes(matter)
    assert result["state"] == "ok"
    assert original_ids(result) == {"later-dispute", "dispute-b"}
    assert result["rows"][-1]["mutation_authority"]["target_ids"] == ["dispute-a"]


@pytest.mark.parametrize("fault", [
    "missing-binding", "wrong-target", "wrong-relation", "wrong-owner",
    "wrong-execution-owner", "wrong-version", "missing-ledger", "ledger-drift",
    "current-quote-drift", "actual-prior-target-drift",
])
def test_invalid_fresh_binding_keeps_both_previous_disputes_and_marks_incomplete(fault):
    matter = fixture()
    turns = deepcopy(matter.brain_chat)
    later = turns[-1]
    row = later["response"]["material"][0]
    execution = later["response"]["material_coverage"]["execution"]
    if fault == "missing-binding":
        row.pop("mutation_authority")
    elif fault == "wrong-target":
        row["related_dispute_ids"] = ["dispute-b"]
    elif fault == "wrong-relation":
        row["relation"] = "withdraws"
    elif fault == "wrong-owner":
        later["offer_digest"] = "another-offered-message"
    elif fault == "wrong-execution-owner":
        execution["owner"] = {**execution["owner"], "matter_id": "another-matter"}
    elif fault == "wrong-version":
        execution["expected_version"] = 2
    elif fault == "missing-ledger":
        execution.pop("mutation_authorities")
    elif fault == "ledger-drift":
        execution["mutation_authorities"]["authorities"][0]["target_ids"] += ["dispute-b"]
    elif fault == "current-quote-drift":
        row["quoted"] = "Different currently unreported words."
    else:
        turns[0]["response"]["material"][0]["statement"] = "A changed prior interpretation."
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}
    assert "later-dispute" not in original_ids(result)
    assert "a dispute proposal lacks valid saved mutation authority" in result["problems"]


def test_fresh_new_account_validates_owner_without_needing_revision_permission():
    matter = fixture(new=True)
    result = projection.proposed_disputes(matter)
    assert result["state"] == "ok"
    assert original_ids(result) == {"dispute-a", "dispute-b", "later-dispute"}


@pytest.mark.parametrize("scope", ["current", "other"])
def test_even_fresh_new_or_scope_excluded_rows_cannot_bypass_owner_integrity(scope):
    matter = fixture(new=True)
    turns = deepcopy(matter.brain_chat)
    execution = turns[-1]["response"]["material_coverage"]["execution"]
    execution["owner"] = {**execution["owner"], "advocate_id": "another-advocate"}
    turns[-1]["response"]["material"][0]["matter_scope"] = scope
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}


def test_genuine_old_unstamped_correction_remains_compatible_and_untracked():
    matter = fixture(legacy=True)
    result = projection.proposed_disputes(matter)
    assert result["state"] == "ok"
    assert original_ids(result) == {"dispute-b", "later-dispute"}
    assert all("mutation_authority" not in row for row in result["history"])


def test_orphaned_binding_cannot_downgrade_a_stamped_correction_to_legacy():
    matter = fixture()
    turns = deepcopy(matter.brain_chat)
    turns[-1]["response"].pop("material_coverage")
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}


def test_incomplete_durable_turn_does_not_admit_a_valid_peer_from_that_turn():
    matter = fixture()
    turns = deepcopy(matter.brain_chat)
    turns[-1]["response"]["material"][0].pop("mutation_authority")
    turns[-1]["response"]["material"].insert(
        0, proposal("valid-new-peer", LATEST, source_turn="later"))
    result = projection.proposed_disputes(replace(matter, brain_chat=turns))
    assert result["state"] == "incomplete"
    assert original_ids(result) == {"dispute-a", "dispute-b"}
