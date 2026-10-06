"""Offline scripted integration checks; no live model quality is asserted.

Run with declared typed outcomes and independent scripted verdicts. Browser,
provider/API tests and real-model semantic judgments remain unverified.
"""

from copy import deepcopy

import pytest

from nm.brain.continuation import _MODEL_UNIT, _UNIT
from nm.brain.execution_contracts import RECORD_OUTCOME_CONTRACT, effect_catalogue
from nm.brain.history import IncompleteConversation
from nm.shared.model_port import SchemaViolation, require_schema
from tests.brain_continuation_fixture import citation_units
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    _operation_names,
    conversation_plan,
    unit,
)
from tests.test_brain_continuation import (
    verdict as base_verdict,
)


def verdict(*indexes, outcome="not_requested"):
    rows = base_verdict(*indexes)
    for row in rows["verdicts"]:
        row["record_check"] = {
            "outcome": outcome,
            "reason": "The explicit offline judgment is scoped to this typed case.",
        }
    return rows


def evidence(*, reader="returned", review="checked", malformed=False,
             record_requirement=None):
    empty = {
        "activated_record_ids": [],
        "retired_record_ids": [],
        "held_record_ids": [],
        "outside_owned_record_ids": [],
        "operations": [],
    }
    effects = {"disputes": deepcopy(empty), "details": deepcopy(empty)}
    effects["details"].update(
        activated_record_ids=["saved-observation"],
        operations=[
            {
                "result_id": "saved-observation",
                "relation": "new",
                "target_record_ids": [],
                "retired_target_ids": [],
                "source_references": [
                    {
                        "turn_id": "current",
                        "role": "advocate",
                        "quoted": "The handover was on 4 May.",
                    }
                ],
            }
        ],
    )
    if malformed:
        effects["details"]["activated_record_ids"].append("saved-observation")
    receipt = {
        "contract": "material_execution_v1",
        "id": "mex_scripted_outcome",
        "owner": {
            "matter_id": "matter",
            "advocate_id": "adv",
            "turn_id": "current",
            "offer_digest": "a" * 64,
        },
        "expected_version": 1,
        "resulting_version": 2,
        "persistence": "prepared_for_commit",
        "requests": [{"request_index": 0, "record_requirement": deepcopy(
            record_requirement if record_requirement is not None else {
                "kind": "change", "target_ids": [], "operation": "new",
                "success_condition": "The original dated account is faithfully represented.",
            })}],
        "effects": effects,
        "record_changes": [],
        "stages": {
            "dispute_extraction": {"state": "returned"},
            "dispute_review": {"state": "no_candidates"},
            "detail_extraction": {"state": reader},
            "detail_review": {"state": review},
        },
    }
    if not malformed and reader == "returned" and review == "checked":
        # This explicitly scripted fixture represents one actually admitted
        # new entry. Use its code-derived effect identity and the exact entry
        # shown by material(), not a writer's requested outcome or prose.
        identity = next(iter(effect_catalogue(receipt)))
        receipt["record_changes"] = [{
            "effect_id": identity, "kind": "details", "relation": "new",
            "before_records": [], "after_record": deepcopy(material(receipt)["rows"][0]),
        }]
    return receipt


def no_record_requirement():
    return {"kind": "none", "target_ids": [], "operation": "none", "success_condition": ""}


def material(receipt):
    return {
        "state": "ok",
        "rows": [
            {
                "id": "saved-observation",
                "label": "Reported handover date",
                "statement": "The handover was on 4 May.",
                "quoted": "The handover was on 4 May.",
                "source_turn_id": "current",
            }
        ],
        "coverage": {"state": "ok", "execution": receipt},
    }


def declaration(status, *, owner="account-0", effects=(), current=()):
    return {
        "status": status,
        "block_id": owner,
        "effect_ids": list(effects),
        "current_record_ids": list(current),
        "reason": "The selected typed result.",
    }


def declared_unit(status, *, index=0, effects=(), current=()):
    proposed = unit(index=index, text="You report the handover date as 4 May.")
    proposed["record_outcome"] = declaration(
        status, owner=f"account-{index}", effects=effects, current=current
    )
    return proposed


def run(model, receipt, **kwargs):
    return _continue(
        model,
        latest="The handover was on 4 May.",
        latest_turn_id="current",
        material=material(receipt),
        **kwargs,
    )


def test_fresh_wire_requires_declaration_but_legacy_internal_unit_remains_untracked():
    raw = unit()
    raw.pop("record_outcome", None)
    require_schema(raw, _UNIT)
    wire = citation_units({"record_catalogue": {}}, {"units": [raw]})["units"][0]
    wire.pop("record_outcome")
    with pytest.raises(SchemaViolation, match="record_outcome"):
        require_schema(wire, _MODEL_UNIT)


def test_checked_owned_performed_result_reaches_review_once_and_only_then_is_sealed():
    receipt = evidence()
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])
    proposed["blocks"][0]["record_ids"] = ["saved-observation"]
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert model.calls[0][1]["record_effect_catalogue"][identity]["performed"] is True
    assert "record_outcome_contract" not in model.calls[1][1]["units"][0]
    assert result.units[0]["record_outcome_contract"] == RECORD_OUTCOME_CONTRACT
    assert result.units[0]["record_outcome"]["effect_ids"] == [identity]
    assert result.coverage[0]["state"] == "ok"


def test_checked_repeated_selector_is_normalized_once_without_writer_retry():
    receipt = evidence()
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity, identity])
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["effect_ids"] == [identity]
    assert receipt["effects"]["details"]["activated_record_ids"] == ["saved-observation"]


def test_skipped_extraction_gets_one_local_writer_correction_to_truthful_unresolved():
    receipt = evidence(reader="not_run")
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])

    def correct(payload):
        assert "record_outcome" in payload["correction"]["validation_issues"][0]["issue"]
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised["record_outcome"] = declaration("unresolved", owner="limit-0")
        return {"units": [revised]}

    model = ContinuationModel([{"units": [proposed]}, correct, verdict(0, outcome="unfinished")])
    result = run(model, receipt)
    assert _operation_names(model) == [
        "continue_conversation",
        "continue_conversation",
        "verify_continuation",
    ]
    assert result.units[0]["record_outcome"]["status"] == "unresolved"
    assert result.units[0]["sufficiency"]["status"] == "needs_input"


def test_bad_effect_peer_does_not_retry_or_discard_independent_good_peer():
    receipt = evidence(record_requirement=no_record_requirement())
    receipt["requests"].append({"request_index": 1, "record_requirement": {
        "kind": "change", "target_ids": [], "operation": "new",
        "success_condition": "The independently requested new account is faithfully represented.",
    }})
    identity = next(iter(effect_catalogue(receipt)))
    good = declared_unit("none", index=0)
    bad = declared_unit("performed", index=1, effects=[identity, "foreign-effect"])

    def repair(payload):
        assert [row["request_index"] for row in payload["correction"]["validation_issues"]] == [1]
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised["record_outcome"] = declaration("unresolved", owner="limit-1")
        return {"units": [revised]}

    plan = conversation_plan(items=conversation_plan().items * 2)
    model = ContinuationModel(
        [{"units": [good, bad]}, verdict(0), repair, verdict(1, outcome="unfinished")]
    )
    result = run(model, receipt, plan=plan)
    assert [row["request_index"] for row in result.units] == [0, 1]
    checks = [
        payload["units"]
        for prompt, payload in model.calls
        if prompt.operation == "verify_continuation"
    ]
    assert [len(rows) for rows in checks] == [1, 1]
    assert checks[0][0]["record_outcome"]["status"] == "none"


def test_corrupt_code_owned_identity_stops_before_either_model_call():
    model = ContinuationModel([])
    with pytest.raises(IncompleteConversation, match="execution"):
        run(model, evidence(malformed=True))
    assert model.calls == []


def test_current_state_noop_does_not_need_a_new_operation_or_save_claim():
    receipt = evidence(reader="not_run", review="not_run")
    proposed = declared_unit("already_current", current=["saved-observation"])
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["status"] == "already_current"
    assert result.units[0]["record_outcome"]["effect_ids"] == []


def test_two_bad_effect_declarations_retain_reviewed_facts_with_specific_unresolved_owner():
    receipt = evidence(reader="not_run")
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])
    model = ContinuationModel(
        [
            {"units": [proposed]},
            {"units": [proposed]},
            verdict(0, outcome="unfinished"),
        ]
    )
    result = run(model, receipt)
    assert _operation_names(model) == [
        "continue_conversation",
        "continue_conversation",
        "verify_continuation",
    ]
    assert result.coverage[0]["state"] == "partial"
    released = result.units[0]
    assert released["record_outcome"]["status"] == "unresolved"
    account, limitation, status = released["blocks"]
    assert account["id"] == "account-0"
    assert account["text"] == 'Your message includes: “The handover was on 4 May.”'
    assert limitation["id"] == "limit-0"
    assert limitation["evidence_expression"]["operator"] == "limitation"
    assert released["record_outcome"]["block_id"] == status["id"] != "limit-0"
    assert status["evidence_expression"]["operator"] == "record_result"
    assert status["text"] == "The requested record work remains unfinished."
    assert released["questions"] == released["next_work"] == released["progress_updates"] == []
    assert released["sufficiency"]["status"] == "partial"
    assert released["record_outcome_contract"] == RECORD_OUTCOME_CONTRACT


def test_unresolved_edit_can_complete_independent_answered_prior_question_once():
    receipt = evidence(reader="not_run", review="not_run")
    proposed = declared_unit("unresolved")
    proposed["progress_updates"] = [
        {
            "target_id": "date-question",
            "status": "complete",
            "block_id": "account-0",
            "reason": "The advocate supplied the asked-for date.",
            "span_ids": ["L1"],
        }
    ]
    progress = {
        "state": "ok",
        "rows": [
            {
                "id": "date-question",
                "kind": "question",
                "status": "pending",
                "text": "What handover date do you report?",
            }
        ],
        "events": [],
        "coverage": {},
        "diagnostics": [],
    }
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="unfinished")])
    result = run(model, receipt, progress=progress)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["status"] == "unresolved"
    assert result.units[0]["progress_updates"][0]["target_id"] == "date-question"
    assert result.units[0]["progress_updates"][0]["status"] == "complete"


def test_unresolved_edit_cannot_complete_its_own_selected_task():
    receipt = evidence(reader="not_run", review="not_run")
    proposed = declared_unit("unresolved")
    proposed["progress_updates"] = [
        {
            "target_id": "$work",
            "status": "complete",
            "block_id": "account-0",
            "reason": "Unsupported claimed edit completion.",
            "span_ids": ["L1"],
        }
    ]
    model = ContinuationModel(
        [
            {"units": [proposed]},
            {"units": [proposed]},
            verdict(0, outcome="unfinished"),
        ]
    )
    result = run(model, receipt)
    assert result.coverage[0]["state"] == "partial"
    assert result.units[0]["progress_updates"] == []
    assert result.units[0]["record_outcome"]["status"] == "unresolved"


def test_missing_fresh_wire_outcome_gets_bounded_correction_and_keeps_good_peer():
    class MissingFirstOutcome(ContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "continue_conversation" and len(self.calls) == 1:
                result.data["units"][1].pop("record_outcome")
            return result

    receipt = evidence(record_requirement=no_record_requirement())
    receipt["requests"].append({"request_index": 1,
                                "record_requirement": no_record_requirement()})
    first = declared_unit("none", index=0)
    second = declared_unit("none", index=1)
    plan = conversation_plan(items=conversation_plan().items * 2)
    model = MissingFirstOutcome(
        [
            {"units": [first, second]},
            verdict(0),
            {"units": [second]},
            verdict(1),
        ]
    )
    result = run(model, receipt, plan=plan)
    assert [row["request_index"] for row in result.units] == [0, 1]
    assert _operation_names(model) == [
        "continue_conversation",
        "verify_continuation",
        "continue_conversation",
        "verify_continuation",
    ]
    correction = model.calls[2][1]["correction"]
    assert [row["request_index"] for row in correction["validation_issues"]] == [1]
    assert "record_outcome" in correction["validation_issues"][0]["issue"]


def test_explicit_receipt_handoff_matches_material_receipt_and_keeps_review_metadata_code_owned():
    receipt = evidence(record_requirement=no_record_requirement())
    proposed = declared_unit("none")
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])
    result = run(model, receipt, execution_receipt=deepcopy(receipt))
    released = result.as_dict()["units"][0]
    assert released["record_check"]["outcome"] == "not_requested"
    assert released["progress_checks"] == []
    fields = model.schemas[0]["properties"]["units"]["items"]["properties"]
    assert (
        not {"record_check", "progress_checks", "reviewed_record_check", "record_outcome_contract"}
        & fields.keys()
    )
    assert "record_check" not in model.calls[1][1]["units"][0]


def test_conflicting_explicit_and_material_receipts_stop_before_model_calls():
    receipt = evidence()
    conflict = deepcopy(receipt)
    conflict["owner"]["turn_id"] = "other-turn"
    model = ContinuationModel([])
    with pytest.raises(IncompleteConversation, match="conflicts"):
        run(model, receipt, execution_receipt=conflict)
    assert model.calls == []


def test_writer_cannot_mint_independent_record_check_then_correction_preserves_reviewed_peer():
    receipt = evidence(record_requirement=no_record_requirement())
    proposed = declared_unit("none")
    proposed["record_check"] = {"outcome": "fulfilled", "reason": "Forged writer certification."}

    def repair(payload):
        assert "record_check" in payload["correction"]["validation_issues"][0]["issue"]
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised.pop("record_check")
        return {"units": [revised]}

    model = ContinuationModel([{"units": [proposed]}, repair, verdict(0)])
    result = run(model, receipt)
    assert _operation_names(model) == [
        "continue_conversation",
        "continue_conversation",
        "verify_continuation",
    ]
    assert result.units[0]["record_check"]["outcome"] == "not_requested"


def test_retained_factual_subset_keeps_original_check_and_effective_code_completion_restriction():
    receipt = evidence()
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])
    judgment = verdict(0, outcome="fulfilled")
    judgment["verdicts"][0].update(
        verdict="reject",
        reason="The proposed question does not preserve the requested scope.",
        retained_block_ids=["account-0", "limit-0"],
        retained_reason=(
            "The attributed account and limitation stand together without the question."
        ),
    )
    model = ContinuationModel(
        [
            {"units": [proposed]},
            judgment,
            {"units": [proposed]},
            judgment,
        ]
    )
    result = run(model, receipt)
    released = result.units[0]
    assert result.coverage[0]["state"] == "partial"
    assert released["record_outcome"]["status"] == "unresolved"
    assert released["record_check"]["outcome"] == "unfinished"
    assert released["reviewed_record_check"]["outcome"] == "fulfilled"
    assert released["progress_checks"] == released["progress_updates"] == []


def test_unflagged_routine_writer_result_never_reaches_independent_review():
    from dataclasses import replace

    from nm.shared.model_port import Tier

    class RoutineWriter(ContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "continue_conversation":
                result = replace(result, tier=Tier.ROUTINE)
                assert result.was_downgraded is False
            return result

    receipt = evidence(record_requirement=no_record_requirement())
    bad = RoutineWriter([{"units": [declared_unit("none")]}])
    withheld = run(bad, receipt)
    assert withheld.units == ()
    assert _operation_names(bad) == ["continue_conversation"]
    good = ContinuationModel([{"units": [declared_unit("none")]}, verdict(0)])
    assert run(good, receipt).coverage[0]["state"] == "ok"
    assert _operation_names(good) == ["continue_conversation", "verify_continuation"]


def test_actual_partial_effects_survive_unassessed_wider_review_without_a_gate_event():
    from dataclasses import replace

    receipt = evidence()
    required = {
        "kind": "review",
        "operation": "none",
        "target_ids": [],
        "success_condition": "Reconcile the whole reported account.",
    }
    receipt["requests"][0]["record_requirement"] = required
    for name in ("dispute_review", "detail_review"):
        receipt["stages"][name]["account_coverage"] = {
            "contract": "independent_account_coverage_v1",
            "state": "unassessed",
            "reason": "The narrower date operation was checked; full omissions remain unresolved.",
            "missing_source_ids": [],
            "review_scope": {
                "requests": [{"request_index": 0, "record_requirement": deepcopy(required)}]
            },
        }
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("unresolved", effects=[identity])
    plan = conversation_plan(
        items=(replace(conversation_plan().items[0], record_requirement=required),)
    )
    model = ContinuationModel([{"units": [proposed]}, verdict(0, outcome="unfinished")])
    result = run(model, receipt, plan=plan)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["effect_ids"] == [identity]
    assert result.gate_events == ()


def test_rejected_full_review_completion_records_only_content_free_coverage_gate_event():
    from dataclasses import replace

    receipt = evidence()
    required = {
        "kind": "review",
        "operation": "none",
        "target_ids": [],
        "success_condition": "Reconcile the whole reported account.",
    }
    receipt["requests"][0]["record_requirement"] = required
    for name in ("dispute_review", "detail_review"):
        receipt["stages"][name]["account_coverage"] = {
            "contract": "independent_account_coverage_v1",
            "state": "partial",
            "reason": "An omission remains outside the checked date correction.",
            "missing_source_ids": [],
            "review_scope": {
                "requests": [{"request_index": 0, "record_requirement": deepcopy(required)}]
            },
        }
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])
    proposed["sufficiency"] = {"status": "complete", "block_id": "account-0"}
    plan = conversation_plan(
        items=(replace(conversation_plan().items[0], record_requirement=required),)
    )

    def correct(payload):
        revised = deepcopy(payload["correction"]["rejected_units"][0])
        revised["sufficiency"]["status"] = "partial"
        revised["record_outcome"] = declaration("unresolved", owner="limit-0", effects=[identity])
        return {"units": [revised]}

    model = ContinuationModel([{"units": [proposed]}, correct, verdict(0, outcome="unfinished")])
    result = run(model, receipt, plan=plan)
    assert len(result.gate_events) == 1
    event = result.as_dict()["gate_events"][0]
    assert event["gate"] == "G-INCOMPLETE" and event["state"] == "partial"
    assert event["attempt"] == 1 and event["request_index"] == 0
    assert event["scope"] == "need" and event["response"] == "disclose"
    assert "4 May" not in str(event) and "saved-observation" not in str(event)
    assert result.units[0]["record_outcome"]["effect_ids"] == [identity]


def test_invalid_positive_effect_gate_is_local_and_normalization_has_no_event():
    receipt = evidence(reader="not_run")
    identity = next(iter(effect_catalogue(receipt)))
    proposed = declared_unit("performed", effects=[identity])
    corrected = deepcopy(proposed)
    corrected["record_outcome"] = declaration("unresolved", owner="limit-0")
    model = ContinuationModel(
        [{"units": [proposed]}, {"units": [corrected]}, verdict(0, outcome="unfinished")]
    )
    result = run(model, receipt)
    assert len(result.gate_events) == 1
    assert result.gate_events[0]["gate"] == "G-EFFECT"
    assert result.gate_events[0]["attempt"] == 1
    valid = evidence()
    owned = next(iter(effect_catalogue(valid)))
    model = ContinuationModel(
        [
            {"units": [declared_unit("performed", effects=[owned, owned])]},
            verdict(0, outcome="fulfilled"),
        ]
    )
    assert run(model, valid).gate_events == ()


def test_corrupt_owned_receipt_consults_core_gate_before_dispatch():
    model = ContinuationModel([])
    with pytest.raises(IncompleteConversation) as problem:
        run(model, evidence(malformed=True))
    assert model.calls == []
    assert problem.value.gate_events[0]["gate"] == "G-CORE"
    assert problem.value.gate_events[0]["scope"] == "turn"
