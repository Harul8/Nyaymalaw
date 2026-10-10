"""Declared owned effect mechanics, separately from semantic/model quality."""

from copy import deepcopy

import pytest

from nm.brain.execution_contracts import (
    ExecutionEvidenceInvalid,
    effect_catalogue,
    validate_record_outcome,
)
from nm.shared.model_port import SchemaViolation


def receipt(
    *,
    kind="details",
    relation="new",
    activated=("result",),
    targets=(),
    retired=(),
    reader="returned",
    review="checked",
    requested_review=False,
):
    empty = {
        "activated_record_ids": [],
        "retired_record_ids": [],
        "held_record_ids": [],
        "outside_owned_record_ids": [],
        "operations": [],
    }
    effects = {"disputes": deepcopy(empty), "details": deepcopy(empty)}
    effects[kind] = {
        **empty,
        "activated_record_ids": list(activated),
        "retired_record_ids": list(retired),
        "operations": [
            {
                "result_id": "result",
                "relation": relation,
                "target_record_ids": list(targets),
                "retired_target_ids": list(retired),
                "source_references": [
                    {
                        "turn_id": "turn",
                        "role": "advocate",
                        "quoted": "The exact requested account.",
                    }
                ],
            }
        ],
    }
    return {
        "contract": "material_execution_v1",
        "id": "mex_fixture",
        "owner": {
            "matter_id": "matter",
            "advocate_id": "adv",
            "turn_id": "turn",
            "offer_digest": "a" * 64,
        },
        "expected_version": 1,
        "resulting_version": 2,
        "persistence": "prepared_for_commit",
        "effects": effects,
        "requests": [
            {
                "request_index": 0,
                "material_purposes": ["interpretation_review"] if requested_review else [],
                "record_requirement": {"kind": "review" if requested_review else "none"},
            }
        ],
        "stages": {
            "dispute_extraction": {"state": "returned"},
            "dispute_review": {"state": "no_candidates" if kind != "disputes" else review},
            "detail_extraction": {"state": reader},
            "detail_review": {"state": review},
        },
    }


def unit(status, *, effects=(), current=(), complete=False, progress=()):
    return {
        "request_index": 0,
        "blocks": [{"id": "owner", "text": "A supported result."}],
        "sufficiency": {"status": "complete" if complete else "partial", "block_id": "owner"},
        "progress_updates": list(progress),
        "work": {"existing_id": "selected-task", "create": False},
        "record_outcome": {
            "status": status,
            "block_id": "owner",
            "effect_ids": list(effects),
            "current_record_ids": list(current),
            "reason": "The selected result.",
        },
    }


def effect_id(evidence):
    return next(iter(effect_catalogue(evidence)))


def test_real_owned_addition_passes_and_id_is_deterministic_without_mutation():
    evidence = receipt()
    original = deepcopy(evidence)
    identity = effect_id(evidence)
    validate_record_outcome(
        unit("performed", effects=[identity], complete=True), evidence, ["result"]
    )
    assert identity == effect_id(deepcopy(evidence))
    assert evidence == original


@pytest.mark.parametrize(("reader", "review"), [("not_run", "checked"), ("returned", "not_run")])
def test_positive_operations_cannot_substitute_for_executed_and_checked_reading(reader, review):
    evidence = receipt(reader=reader, review=review)
    with pytest.raises(SchemaViolation, match="unread, unchanged or unadmitted"):
        validate_record_outcome(
            unit("performed", effects=[effect_id(evidence)]), evidence, ["result"]
        )


def test_proposal_and_held_observation_are_not_active_performed_effects():
    evidence = receipt(activated=())
    evidence["effects"]["details"]["held_record_ids"] = ["result"]
    with pytest.raises(SchemaViolation):
        validate_record_outcome(unit("performed", effects=[effect_id(evidence)]), evidence, [])


@pytest.mark.parametrize("relation", ["corrects", "withdraws"])
def test_revision_requires_actual_retirement_and_valid_revision_passes(relation):
    missing = receipt(
        relation=relation,
        targets=["prior"],
        activated=[] if relation == "withdraws" else ["result"],
    )
    with pytest.raises(SchemaViolation):
        validate_record_outcome(
            unit("performed", effects=[effect_id(missing)]),
            missing,
            [] if relation == "withdraws" else ["result", "prior"],
        )
    actual = receipt(
        relation=relation,
        targets=["prior"],
        retired=["prior"],
        activated=[] if relation == "withdraws" else ["result"],
    )
    validate_record_outcome(
        unit("performed", effects=[effect_id(actual)]),
        actual,
        [] if relation == "withdraws" else ["result"],
    )


def test_material_contradiction_preserves_target_and_dispute_successor_can_retire_it():
    material = receipt(relation="contradicts", targets=["prior"])
    validate_record_outcome(
        unit("performed", effects=[effect_id(material)]), material, ["result", "prior"]
    )
    material["effects"]["details"]["retired_record_ids"] = ["prior"]
    material["effects"]["details"]["operations"][0]["retired_target_ids"] = ["prior"]
    with pytest.raises(SchemaViolation):
        validate_record_outcome(
            unit("performed", effects=[effect_id(material)]), material, ["result"]
        )
    dispute = receipt(kind="disputes", relation="contradicts", targets=["prior"], retired=["prior"])
    validate_record_outcome(unit("performed", effects=[effect_id(dispute)]), dispute, ["result"])


def test_explicit_held_scope_reconciliation_can_produce_a_real_owned_correction():
    evidence = receipt(relation="corrects", targets=["held-prior"], activated=["result"])
    evidence["effects"]["details"].update(
        before_record_ids=[],
        after_record_ids=["result"],
        before_held_record_ids=["held-prior"],
        after_held_record_ids=[],
    )
    validate_record_outcome(unit("performed", effects=[effect_id(evidence)]), evidence, ["result"])
    selected = next(iter(effect_catalogue(evidence).values()))
    assert selected["retired_target_ids"] == []
    assert selected["removed_target_ids"] == ["held-prior"]
    still_held = deepcopy(evidence)
    still_held["effects"]["details"]["after_held_record_ids"] = ["held-prior"]
    with pytest.raises(SchemaViolation):
        validate_record_outcome(
            unit("performed", effects=[effect_id(still_held)]), still_held, ["result"]
        )


def test_already_current_uses_owned_state_without_needing_a_past_receipt():
    validate_record_outcome(
        unit("already_current", current=["prior"], complete=True), None, ["prior"]
    )
    with pytest.raises(SchemaViolation, match="active owned"):
        validate_record_outcome(unit("already_current", current=["foreign"]), None, ["prior"])
    evidence = receipt()
    with pytest.raises(SchemaViolation, match="not a past operation"):
        validate_record_outcome(
            unit("already_current", current=["result"], effects=[effect_id(evidence)]),
            evidence,
            ["result"],
        )


def test_review_no_change_allows_zero_candidates_but_not_skipped_or_unrequested_review():
    evidence = receipt(activated=(), requested_review=True, review="no_candidates")
    for kind in ("disputes", "details"):
        evidence["effects"][kind]["operations"] = []
    requirement = evidence["requests"][0]["record_requirement"]
    for review in ("dispute_review", "detail_review"):
        evidence["stages"][review]["account_coverage"] = {
            "contract": "independent_account_coverage_v1", "state": "complete",
            "reason": "The complete original scope is already faithfully represented.",
            "missing_source_ids": [], "review_scope": {"requests": [{
                "request_index": 0, "record_requirement": deepcopy(requirement)}]},
        }
    validate_record_outcome(
        unit("review_no_change", current=["prior"], complete=True), evidence, ["prior"]
    )
    skipped = deepcopy(evidence)
    skipped["stages"]["detail_extraction"]["state"] = "not_run"
    with pytest.raises(SchemaViolation, match="actual reading"):
        validate_record_outcome(unit("review_no_change"), skipped, ["prior"])
    unrequested = deepcopy(evidence)
    unrequested["requests"][0]["record_requirement"]["kind"] = "none"
    with pytest.raises(SchemaViolation, match="actual requested reading"):
        validate_record_outcome(unit("review_no_change"), unrequested, ["prior"])


def test_valid_non_effect_completion_and_partial_unresolved_work_remain_deliverable():
    validate_record_outcome(unit("none", complete=True), None, [])
    validate_record_outcome(unit("unresolved"), None, [])
    with pytest.raises(SchemaViolation, match="cannot complete"):
        validate_record_outcome(unit("unresolved", complete=True), None, [])
    with pytest.raises(SchemaViolation, match="cannot complete"):
        validate_record_outcome(
            unit("unresolved", progress=[{"target_id": "$work", "status": "complete"}]), None, []
        )
    with pytest.raises(SchemaViolation, match="cannot complete"):
        validate_record_outcome(
            unit("unresolved", progress=[{"target_id": "selected-task", "status": "complete"}]),
            None,
            [],
        )
    validate_record_outcome(
        unit("unresolved", progress=[{"target_id": "answered-question", "status": "complete"}]),
        None,
        [],
    )


def test_repeated_checked_model_selectors_normalize_without_repairing_owned_receipts():
    evidence = receipt()
    identity = effect_id(evidence)
    repeated = unit("performed", effects=[identity, identity])
    validate_record_outcome(repeated, evidence, ["result"])
    assert repeated["record_outcome"]["effect_ids"] == [identity]
    already = unit("already_current", current=["second", "first", "second"])
    validate_record_outcome(already, None, ["first", "second"])
    assert already["record_outcome"]["current_record_ids"] == ["second", "first"]
    unknown = unit("performed", effects=[identity, "foreign", identity])
    with pytest.raises(SchemaViolation):
        validate_record_outcome(unknown, evidence, ["result"])
    assert unknown["record_outcome"]["effect_ids"] == [identity, "foreign", identity]
    corrupted = deepcopy(evidence)
    corrupted["effects"]["details"]["operations"].append(
        deepcopy(corrupted["effects"]["details"]["operations"][0])
    )
    with pytest.raises(ExecutionEvidenceInvalid):
        effect_catalogue(corrupted)


def test_populated_inapplicable_metadata_and_foreign_effects_are_not_silently_repaired():
    evidence = receipt()
    with pytest.raises(SchemaViolation, match="none cannot carry"):
        validate_record_outcome(unit("none", effects=[effect_id(evidence)]), evidence, ["result"])
    with pytest.raises(SchemaViolation, match="this turn"):
        validate_record_outcome(unit("performed", effects=["foreign"]), evidence, ["result"])


def test_malformed_code_evidence_is_core_integrity_failure_not_content_fallback():
    evidence = receipt()
    evidence["effects"]["details"]["operations"][0]["retired_target_ids"] = ["foreign"]
    with pytest.raises(ExecutionEvidenceInvalid):
        effect_catalogue(evidence)


def test_legacy_missing_declaration_is_explicitly_unassessed_not_new_completion_evidence():
    old = unit("none", complete=True)
    old.pop("record_outcome")
    assert validate_record_outcome(old, None, []) is None
