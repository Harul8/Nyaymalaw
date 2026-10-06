"""Actual application binds fresh coverage to live results and preserved lineage.

Historical source preservation uses an explicitly checked retirement; it never
turns an archived statement into a current assertion or invents a successor.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review
from nm.brain import turn as owner
from nm.brain.execution_contracts import ExecutionEvidenceInvalid

SOURCES = {
    "north": {"turn_id": "original", "role": "advocate",
              "quoted": "The north parcel arrived late."},
    "south": {"turn_id": "original", "role": "advocate",
              "quoted": "The south parcel remained undelivered."},
}


def assessment(*, records=(), candidates=(), peer=True, outside=False):
    selected = SOURCES if peer else {"north": SOURCES["north"]}
    dispositions = [{
        "source_id": "north", "start": 0, "end": len(SOURCES["north"]["quoted"]),
        "status": "outside_scope" if outside else "represented",
        "record_ids": [] if outside else list(records),
        "candidate_ids": [] if outside else list(candidates),
        "reason": "The independently read original portion has this scoped disposition.",
    }]
    if peer:
        dispositions.append({
            "source_id": "south", "start": 0, "end": len(SOURCES["south"]["quoted"]),
            "status": "represented", "record_ids": ["south-current"], "candidate_ids": [],
            "reason": "The separate reported account remains represented by its saved entry.",
        })
    raw = {
        "state": "complete", "reason": "Original account was independently checked.",
        "source_checks": [{
            "source_id": identity, "content_purpose": "account",
            "substantive_spans": [{"start": 0, "end": len(reference["quoted"])}],
            "reason": "This original attributed account was examined in full.",
        } for identity, reference in selected.items()],
        "dispositions": dispositions,
    }
    checked = record_review.checked_coverage(
        raw, selected, source_references=selected,
        record_ids=(*records, "south-current"), candidate_ids=candidates,
        admitted_candidate_ids=candidates)
    return {**checked, "contract": record_review.ACCOUNT_COVERAGE_CONTRACT,
            "review_scope": {"requests": [{"request_index": 0}]}, "missing_sources": []}


def history_proof(*, relation="corrects", candidate="D1", result="north-revised", kind="details"):
    old = {"id": "north-old", "source_turn_id": "original",
           "quoted": SOURCES["north"]["quoted"], "statement": SOURCES["north"]["quoted"]}
    proposal = {"kind": "event", "relation": relation, "related_dispute_ids": [],
                "related_material_ids": [old["id"]],
                "statement": "The revised account preserves its source attribution."}
    if kind == "disputes":
        proposal.update(kind="dispute", related_dispute_ids=[old["id"]], related_material_ids=[])
    return {
        "record": old, "historical_record": deepcopy(old), "proposal": proposal,
        "effect": {"id": "effect:north", "kind": kind, "performed": True, "result_id": result,
                   "relation": relation, "target_record_ids": [old["id"]],
                   "retired_target_ids": [old["id"]],
                   "source_references": [SOURCES["north"]]},
        "review": {
            "candidate_id": candidate, "verdict": "accept", "operation_supported": True,
            "proposal": deepcopy(proposal),
            "account_check": {"content_role": "reported_matter_account", "supported": True,
                              "introduces_legal_analysis": False},
            "target_checks": [{"target_id": old["id"], "account_preserved": True,
                               "identity_relation": "same_underlying_account"}],
        },
    }


def applied(coverage, *, active=("south-current",), candidates=None, history=None, opening=None):
    return owner._post_application_coverage(
        coverage, active_record_ids=active, candidate_result_ids=candidates or {},
        historical_record_results=history, durable_opening_result=opening)


def test_unchanged_current_record_coverage_needs_no_new_operation_or_row():
    coverage = assessment(records=("north-old",))
    original = deepcopy(coverage)
    result = applied(coverage, active=("north-old", "south-current"))
    assert result == original and coverage == original
    assert result is not coverage and "post_application_contract" not in result


def test_retired_current_dependency_alone_is_localized_without_discarding_valid_peer():
    coverage = assessment(records=("north-old",))
    original = deepcopy(coverage)
    result = applied(coverage)
    assert result["state"] == "partial" and result["missing_source_ids"] == ["north"]
    assert result["dispositions"][0]["status"] == "unresolved"
    assert result["dispositions"][1] == original["dispositions"][1]
    dependency, = result["representation_dependencies"]
    assert dependency["record_ids"] == ["north-old"]
    assert dependency["quoted"] == SOURCES["north"]["quoted"]
    assert result["missing_sources"] == [{"source_id": "north", **SOURCES["north"]}]
    assert coverage == original


def test_explicit_admitted_active_replacement_preserves_complete_account_reading():
    coverage = assessment(records=("north-old",), candidates=("D1",))
    result = applied(coverage, active=("north-revised", "south-current"),
                     candidates={"D1": "north-revised"})
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    assert result["dispositions"][0]["record_ids"] == []
    assert result["dispositions"][0]["candidate_ids"] == ["D1"]


@pytest.mark.parametrize("mapped", [None, "north-held", "north-withdrawal"])
def test_candidate_without_active_result_or_preserved_history_is_not_representation(mapped):
    coverage = assessment(candidates=("D1",))
    result = applied(coverage, candidates={} if mapped is None else {"D1": mapped})
    assert result["state"] == "partial" and result["missing_source_ids"] == ["north"]
    assert result["dispositions"][0]["candidate_ids"] == []
    assert result["dispositions"][1]["record_ids"] == ["south-current"]


@pytest.mark.parametrize("relation,kind", [
    ("corrects", "details"), ("withdraws", "details"), ("contradicts", "disputes"),
])
def test_checked_retirement_preserves_history_without_claiming_it_current(relation, kind):
    coverage = assessment(records=("north-old",))
    result = applied(coverage, history={"north-old": history_proof(relation=relation, kind=kind)})
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    portion = result["dispositions"][0]
    assert portion["status"] == "represented" and portion["record_ids"] == []
    lineage, = portion["historical_representations"]
    assert lineage["representation_kind"] == "historical_supersession"
    assert lineage["record_id"] == "north-old" and lineage["effect_id"] == "effect:north"
    assert lineage["original_source"] == SOURCES["north"]
    assert portion["candidate_ids"] == []


def test_withdrawal_candidate_only_can_reference_its_actual_preserved_original_lineage():
    coverage = assessment(candidates=("D1",))
    proof = history_proof(relation="withdraws", result="north-withdrawal")
    result = applied(coverage, candidates={"D1": "north-withdrawal"},
                     history={"north-old": proof})
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    portion = result["dispositions"][0]
    assert portion["record_ids"] == portion["candidate_ids"] == []
    assert portion["historical_representations"][0]["relation"] == "withdraws"


def test_outside_scope_historical_portion_stays_outside_scope_after_legitimate_withdrawal():
    coverage = assessment(outside=True)
    result = applied(coverage, history={"north-old": history_proof(relation="withdraws")})
    assert result == coverage and result["state"] == "complete"
    assert result["dispositions"][0]["status"] == "outside_scope"


@pytest.mark.parametrize("changed", [
    {"source_turn_id": "unrelated-original"},
    {"quoted": SOURCES["south"]["quoted"]},
])
def test_preserved_history_from_another_owned_source_cannot_fill_this_original_portion(changed):
    proof = history_proof()
    proof["record"].update(changed)
    proof["historical_record"] = deepcopy(proof["record"])
    proof["effect"]["source_references"] = [{
        "turn_id": proof["record"]["source_turn_id"], "role": "advocate",
        "quoted": proof["record"]["quoted"],
    }]
    result = applied(assessment(records=("north-old",)), history={"north-old": proof})
    assert result["state"] == "partial" and result["missing_source_ids"] == ["north"]
    assert "historical_representations" not in result["dispositions"][0]


@pytest.mark.parametrize("fault", [
    "changed_archive", "unperformed", "not_retired", "rejected", "not_preserved",
    "wrong_identity", "different_proposal", "missing_target_check", "unsupported_account",
    "different_operation_source",
])
def test_historical_supersession_requires_the_actual_positive_preserved_retirement(fault):
    proof = history_proof()
    if fault == "changed_archive":
        proof["historical_record"]["quoted"] = "A different archived source."
    elif fault == "unperformed":
        proof["effect"]["performed"] = False
    elif fault == "not_retired":
        proof["effect"]["retired_target_ids"] = []
    elif fault == "rejected":
        proof["review"]["verdict"] = "reject"
    elif fault == "not_preserved":
        proof["review"]["target_checks"][0]["account_preserved"] = False
    elif fault == "wrong_identity":
        proof["review"]["target_checks"][0]["identity_relation"] = "different"
    elif fault == "different_proposal":
        proof["review"]["proposal"]["statement"] = "Another candidate was accepted."
    elif fault == "missing_target_check":
        proof["review"]["target_checks"] = []
    elif fault == "unsupported_account":
        proof["review"]["account_check"]["supported"] = False
    elif fault == "different_operation_source":
        proof["effect"]["source_references"] = [SOURCES["south"]]
    with pytest.raises(ExecutionEvidenceInvalid):
        applied(assessment(records=("north-old",)), history={"north-old": proof})


def test_live_replacement_is_not_invented_from_a_retired_record_target():
    result = applied(assessment(records=("north-old",)),
                     active=("north-revised", "south-current"),
                     candidates={"D1": "north-revised"})
    assert result["state"] == "partial"
    assert result["dispositions"][0]["candidate_ids"] == []


def opening_proof():
    heading = {"ready": True, "title": "Reported parcel chronology",
               "summary": SOURCES["north"]["quoted"]}
    return {"candidate_id": "O1", "kind": "opening", "accepted": True,
            "result_id": "owned-matter", "candidate": heading, "actual": deepcopy(heading)}


def test_checked_saved_opening_is_a_durable_result_without_forcing_new_material_rows():
    coverage = assessment(candidates=("O1",), peer=False)
    result = applied(coverage, active=(), opening=opening_proof())
    assert result == coverage and result["state"] == "complete"
    assert result["dispositions"][0]["candidate_ids"] == ["O1"]


def test_opening_admission_without_the_actual_owned_heading_does_not_establish_representation():
    result = applied(assessment(candidates=("O1",), peer=False), active=())
    assert result["state"] == "partial" and result["missing_source_ids"] == ["north"]


@pytest.mark.parametrize("fault", ["unsupported", "wrong_saved_heading", "wrong_kind"])
def test_opening_proof_cannot_substitute_an_unchecked_or_different_result(fault):
    proof = opening_proof()
    if fault == "unsupported":
        proof["accepted"] = False
    elif fault == "wrong_saved_heading":
        proof["actual"]["summary"] = "An unrelated current account."
    else:
        proof["kind"] = "material"
    with pytest.raises(ExecutionEvidenceInvalid):
        applied(assessment(candidates=("O1",), peer=False), active=(), opening=proof)


def test_explicit_historical_coverage_keeps_its_existing_read_contract():
    legacy = {"state": "complete", "reason": "Historical original account was examined.",
              "missing_source_ids": []}
    assert applied(legacy, active=()) == legacy


def test_tampered_exact_portion_cannot_acquire_application_evidence():
    coverage = assessment(records=("north-old",))
    coverage["dispositions"][0]["quoted"] = "An invented original passage."
    with pytest.raises(ExecutionEvidenceInvalid, match="changed original evidence"):
        applied(coverage)


def retirement_proof():
    """An explicitly checked actual tombstone represents an operation, not an active assertion."""
    proof = history_proof(relation="withdraws", result="north-withdrawal")
    record = {"id": "north-withdrawal", "relation": "withdraws",
              "source_turn_id": SOURCES["north"]["turn_id"],
              "quoted": SOURCES["north"]["quoted"]}
    proof.update(record=record, historical_record=deepcopy(record))
    proof["review"]["account_check"]["source_checks"] = [{
        "source_id": "north", "supplies_account_content": True, "supports_proposal": True,
        "support_spans": [{"start": 0, "end": len(SOURCES["north"]["quoted"])}],
    }]
    return proof


def test_selected_actual_withdrawal_preserves_latest_account_as_operation_without_active_fact():
    result = owner._post_application_coverage(
        assessment(candidates=("D1",)), active_record_ids=("south-current",),
        candidate_result_ids={"D1": "north-withdrawal"},
        retirement_candidate_results={"D1": retirement_proof()})
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    latest = result["dispositions"][0]
    assert latest["candidate_ids"] == latest["record_ids"] == []
    assert latest["operation_representations"][0]["representation_kind"] == "performed_retirement"
    assert result["dispositions"][1]["record_ids"] == ["south-current"]


@pytest.mark.parametrize("fault", ["skipped", "wrong_target", "unpreserved_target"])
def test_false_withdrawal_operation_proof_cannot_supply_latest_account(fault):
    proof = retirement_proof()
    if fault == "skipped":
        proof["effect"]["performed"] = False
    elif fault == "wrong_target":
        proof["effect"]["target_record_ids"] = ["unowned-target"]
    else:
        proof["review"]["target_checks"][0]["account_preserved"] = False
    with pytest.raises(ExecutionEvidenceInvalid):
        owner._post_application_coverage(
            assessment(candidates=("D1",)), active_record_ids=("south-current",),
            candidate_result_ids={"D1": "north-withdrawal"},
            retirement_candidate_results={"D1": proof})


def test_actual_retirement_with_wrong_original_source_cannot_fill_unrelated_portion():
    proof = retirement_proof()
    proof["review"]["account_check"]["source_checks"][0].update(
        source_id="south", support_spans=[{
            "start": 0, "end": len(SOURCES["south"]["quoted"])}])
    result = owner._post_application_coverage(
        assessment(candidates=("D1",)), active_record_ids=("south-current",),
        candidate_result_ids={"D1": "north-withdrawal"},
        retirement_candidate_results={"D1": proof})
    assert result["state"] == "partial" and result["missing_source_ids"] == ["north"]
    assert result["dispositions"][0]["status"] == "unresolved"
    assert result["dispositions"][1]["record_ids"] == ["south-current"]


def test_identical_checked_proposal_occurrences_keep_their_distinct_result_bindings():
    from nm.brain.conversation import OpeningCandidate
    from nm.brain.material import MaterialCandidate
    from nm.brain.record_review import remember_independent_review
    from tests.test_brain_source_support_verifiers import verdict

    candidate = MaterialCandidate(
        "event", SOURCES["north"]["quoted"], SOURCES["north"]["quoted"], "new", (),
        "current", "stated", "relevant", "This reported event is material.", placement="matter")
    sources = {"north": {**SOURCES["north"], "content_role": "reported_matter_account",
                         "reason": "The original owner explicitly reports this account."}}
    rows = [{"candidate_id": identity,
             **owner._application_proposal_payload(candidate, stage="detail_review"),
             "allowed_account_source_ids": ["north"], "allowed_restoration_peer_ids": []}
            for identity in ("D1", "D2")]
    decisions = {identity: {**verdict("material", SOURCES["north"], source_id="north"),
                            "candidate_id": identity} for identity in ("D1", "D2")}
    state = {}
    remember_independent_review(state, context={"candidates": rows},
                                source_treatments=sources, decisions=decisions)
    execution = {"owner": {"turn_id": "repeat"}, "expected_version": 1, "stages": {
        "detail_review": {"account_coverage": assessment(candidates=("D1", "D2"), peer=False)},
        "dispute_review": {"account_coverage": {}},
    }}
    receipt = owner._capture_coverage_application(
        execution, states={"detail_review": state},
        proposals={"detail_review": (candidate, candidate), "dispute_review": ()},
        candidates=(candidate, candidate),
        material=[candidate.recorded("repeat", index) for index in (1, 2)],
        opening=OpeningCandidate(False, "", ""), opening_supported=False,
        sources=sources, latest_sources={"north": SOURCES["north"]["quoted"]},
        prior_sources={}, opening_result={})
    assert [(row["candidate_id"], row["result_id"]) for row in receipt["bindings"]] == [
        ("D1", "repeat:material:1"), ("D2", "repeat:material:2")]
