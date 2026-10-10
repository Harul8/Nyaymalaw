"""Declared effects cannot vanish through mode or follow-up bookkeeping."""
from copy import deepcopy

import pytest

from nm.brain.conversation import WorkItem
from tests.test_brain_continuation import (
    ContinuationModel,
    _operation_names,
    conversation_plan,
    unit,
)
from tests.test_brain_continuation_record_outcome import declaration, evidence, run, verdict

pytestmark = pytest.mark.class_a
ORIGINAL_ACCOUNT = 'Your message includes: “The handover was on 4 May.”'
SOURCED_QUESTION = (
    'What needs clarification about the meaning of the following account? ' + ORIGINAL_ACCOUNT)


def owned_inputs(*, mode="substantive", kind="change", mixed=False):
    required = {"kind": kind, "target_ids": ["saved-observation"],
                "operation": "corrects" if kind == "change" else "none",
                "success_condition": "The original reported date is faithfully represented."}
    receipt = evidence()
    receipt["record_changes"] = []
    receipt["requests"][0].update(response_mode=mode, record_requirement=required)
    first = WorkItem(request="Examine the original dated account",
                     relation="new", matter_scope="proposed", priority="ordinary",
                     next_step="answer", response_mode=mode, record_requirement=required)
    items = [first]
    if mixed:
        ordinary = {"kind": "none", "target_ids": [], "operation": "none",
                    "success_condition": ""}
        items.append(WorkItem(request="Explain this attributed account",
                              relation="new", matter_scope="proposed", priority="ordinary",
                              next_step="answer", record_requirement=ordinary))
        receipt["requests"].append({"request_index": 1, "response_mode": "substantive",
                                     "record_requirement": ordinary})
    return receipt, conversation_plan(items=tuple(items))


def record_unit(*, status="none", followup=False):
    value = unit(text="I changed and saved every requested record.")
    value["blocks"][0]["kind"] = "completion"
    value["blocks"] = value["blocks"][:2] if followup else value["blocks"][:1]
    if not followup:
        value["questions"] = []
    value["sufficiency"] = {"status": "needs_input" if followup else "partial",
                            "block_id": "question-0" if followup else "account-0"}
    value["record_outcome"] = declaration(status, owner="account-0") if status != "none" else {
        "status": "none", "block_id": "", "effect_ids": [],
        "current_record_ids": [], "reason": ""}
    return value


@pytest.mark.parametrize("mode", ["substantive", "record_acknowledgement"])
@pytest.mark.parametrize("kind", ["change", "review"])
@pytest.mark.parametrize("followup", [False, True])
def test_none_cannot_bypass_declared_record_work_and_only_failed_unit_is_repaired(
        mode, kind, followup):
    receipt, plan = owned_inputs(mode=mode, kind=kind, mixed=True)
    bad, ordinary = record_unit(followup=followup), unit(1)
    corrected = record_unit(status="unresolved", followup=followup)

    def repair(payload):
        assert [row["request_index"] for row in payload["correction"]["validation_issues"]] == [0]
        mismatch = payload["correction"]["validation_issues"][0]["issue"]
        assert "declared record review/change" in mismatch
        assert [row["request_index"] for row in payload["work_items"]] == [0]
        return {"units": [deepcopy(corrected)]}

    model = ContinuationModel([{"units": [bad, ordinary]}, verdict(1),
                               repair, verdict(0, outcome="unfinished")])
    result = run(model, receipt, plan=plan)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation",
                                      "continue_conversation", "verify_continuation"]
    assert [row["state"] for row in result.coverage] == ["ok", "ok"]
    assert result.units[0]["record_outcome"]["status"] == "unresolved"
    assert result.units[0]["record_check"]["outcome"] == "unfinished"
    assert result.units[1]["blocks"][0]["text"] == ORIGINAL_ACCOUNT
    if followup:
        assert result.units[0]["questions"] == corrected["questions"]
        assert result.units[0]["blocks"][1]["text"] == SOURCED_QUESTION
    statuses = {row["request_index"]: row["record_outcome_statuses"]
                for row in model.calls[0][1]["work_items"]}
    assert "none" not in statuses[0]
    assert "none" in statuses[1]
    assert "none" not in model.schemas[2]["properties"]["units"]["items"]["properties"][
        "record_outcome"]["properties"]["status"]["enum"]
    assert all(row["request_index"] != 0 for row in model.calls[1][1]["units"])
    assert any(row["gate"] == "G-EFFECT" for row in result.gate_events)


@pytest.mark.parametrize("followup", [False, True])
def test_persistent_none_under_substantive_delivery_is_not_sent_to_a_wrong_acceptor(followup):
    receipt, plan = owned_inputs()
    bad = record_unit(followup=followup)
    model = ContinuationModel([{"units": [bad]}, {"units": [deepcopy(bad)]}])
    result = run(model, receipt, plan=plan)
    assert _operation_names(model) == ["continue_conversation", "continue_conversation"]
    assert result.units == ()
    assert result.coverage[0]["state"] == "unavailable"
    assert "none" not in model.schemas[0]["properties"]["units"]["items"]["properties"][
        "record_outcome"]["properties"]["status"]["enum"]


def test_correct_mixed_owner_and_followup_are_normalized_without_retry_or_loss():
    receipt, plan = owned_inputs(mixed=True)
    supported = record_unit(status="unresolved", followup=True)
    supported["blocks"][0].update(kind="account", text="You report the original dated account.")
    ordinary = unit(1)
    model = ContinuationModel([{"units": [supported, ordinary]},
                               {"verdicts": [*verdict(0, outcome="unfinished")["verdicts"],
                                             *verdict(1)["verdicts"]]}])
    result = run(model, receipt, plan=plan)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    first = result.units[0]
    assert first["blocks"][0]["text"] == ORIGINAL_ACCOUNT
    assert first["questions"] == supported["questions"]
    assert first["blocks"][1]["text"] == SOURCED_QUESTION
    assert first["record_outcome"]["block_id"] not in (
        supported["blocks"][0]["id"], supported["blocks"][1]["id"])
    assert first["blocks"][-1]["text"] == "The requested record work remains unfinished."
    assert result.units[1]["record_outcome"]["status"] == "none"


def test_already_current_result_is_admitted_without_an_invented_fresh_write():
    receipt, plan = owned_inputs()
    supported = record_unit(status="already_current")
    supported["record_outcome"]["current_record_ids"] = ["saved-observation"]
    supported["sufficiency"]["status"] = "complete"
    model = ContinuationModel([{"units": [supported]}, verdict(0, outcome="fulfilled")])
    result = run(model, receipt, plan=plan)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["status"] == "already_current"
    assert result.units[0]["record_outcome"]["effect_ids"] == []
    assert result.units[0]["blocks"][0]["text"].startswith("Current record entries:")


def test_correct_ordinary_none_remains_a_supported_answer_without_a_record_notice():
    receipt, plan = owned_inputs()
    ordinary_requirement = {"kind": "none", "target_ids": [], "operation": "none",
                            "success_condition": ""}
    receipt["requests"][0]["record_requirement"] = ordinary_requirement
    ordinary_plan = conversation_plan(items=(WorkItem(
        request="Explain the attributed account", relation="new", matter_scope="proposed",
        priority="ordinary", next_step="answer", record_requirement=ordinary_requirement),))
    supported = unit()
    model = ContinuationModel([{"units": [supported]}, verdict(0)])
    result = run(model, receipt, plan=ordinary_plan)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["record_outcome"]["status"] == "none"
    assert len(result.units[0]["blocks"]) == len(supported["blocks"])
    assert "none" in model.schemas[0]["properties"]["units"]["items"]["properties"][
        "record_outcome"]["properties"]["status"]["enum"]
