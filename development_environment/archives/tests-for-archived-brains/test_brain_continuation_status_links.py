"""Offline typed-link witnesses; no provider/browser calls.

These tests certify owned display/link mechanics, not whether a question is
useful, an effect satisfies the advocate, or a substantive reply is sufficient.
"""
from copy import deepcopy

import pytest

from nm.brain.continuation import _read_units
from nm.brain.evidence_rendering import rendered_block
from tests.test_brain_continuation import ContinuationModel, _operation_names
from tests.test_brain_continuation_record_outcome import run, verdict
from tests.test_brain_record_acknowledgement_contract import inputs, render

SPANS = {
    "L1": {"id": "L1", "turn_id": "current", "role": "advocate",
           "text": "The handover was on 4 May."},
    "L2": {"id": "L2", "turn_id": "current", "role": "advocate",
           "text": "I have not confirmed who received the receipt."},
}
ROLES = {"questions": ("question", "question"),
         "next_work": ("next_work", "next_step")}


def proposal(identity, operator, *, kind=None):
    role = {"record_result": "completion", "source_account": "account",
            "comparison": "account", "question": "question",
            "next_work": "next_step", "limitation": "limitation"}[operator]
    sources = [] if operator == "record_result" else ["L1"]
    if operator == "comparison":
        sources.append("L2")
    return {"id": identity, "kind": kind or role, "uncertainty": "none",
            "evidence_expression": {
                "operator": operator, "source_ids": sources, "record_ids": [],
                "focus": "attribution" if operator in ("question", "next_work") else "none"}}


def displayed(identity, operator, *, kind=None):
    return rendered_block(proposal(identity, operator, kind=kind),
                          spans=SPANS, records={}, sources={})


def link(field, identity):
    return {"id": "owned-proposal", "block_id": identity,
            "purpose": "Clarify the attributed recipient." if field == "questions"
            else "Examine the attributed recipient.", "target_ids": [], "existing_id": ""}


def expression_inputs(status="performed", *, checked=True):
    continuation, receipt, catalogue = inputs(status, checked=checked)
    continuation["units"][0]["blocks"] = [displayed("owned-block", "record_result")]
    return continuation, receipt, catalogue


def fresh(row, *, index=0):
    result = deepcopy(row)
    result["request_index"] = index
    result.pop("record_check", None)
    result.pop("work")
    result["work_selector"] = "$new_task"
    return result


def fresh_owner(status="performed"):
    continuation, receipt, catalogue = expression_inputs(status, checked=False)
    row = fresh(continuation["units"][0])
    row["blocks"] = [proposal("owned-block", "record_result")]
    return row, receipt, catalogue


def independent_peer():
    row, _, _ = fresh_owner()
    row.update(request_index=1, blocks=[proposal("independent-account", "source_account")],
               sufficiency={"status": "partial", "block_id": "independent-account"},
               record_outcome={"status": "none", "block_id": "", "effect_ids": [],
                               "current_record_ids": [], "reason": "No record effect requested."})
    return row


def admitted(row, receipt, catalogue):
    return _read_units({"units": [row]}, (0,), SPANS, catalogue, {},
                       execution_receipt=receipt)


@pytest.mark.parametrize("field", ROLES)
def test_legitimate_fixed_followup_survives_preview_and_checked_status_composition(field):
    operator, kind = ROLES[field]
    row, receipt, catalogue = fresh_owner()
    # The operator owns meaning; a redundant writer label must not erase it.
    row["blocks"].append(proposal("independent-followup", operator, kind="completion"))
    row[field] = [link(field, "independent-followup")]
    valid, issues = admitted(row, receipt, catalogue)
    assert issues == {}
    followup = deepcopy(valid[0]["blocks"][1])
    assert followup["kind"] == kind
    preview = render({"units": [valid[0]]}, receipt, catalogue, require_checked=False)
    assert preview["units"][0]["blocks"][1] == followup
    preview["units"][0]["record_check"] = {
        "outcome": "fulfilled", "reason": "The synthetic owned effect is admitted."}
    final = render(preview, receipt, catalogue)
    assert final["units"][0]["blocks"][1] == followup
    assert final["units"][0][field] == [link(field, "independent-followup")]
    assert final["units"][0]["record_outcome"]["block_id"] == "owned-block"
    assert len(final["units"][0]["blocks"]) == 2
    assert final["units"][0]["blocks"][0]["text"] == (
        "Saved record changes:\nNew entry: The handover was on 4 May.")
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


@pytest.mark.parametrize("field", ROLES)
def test_matching_links_may_share_expression_and_reuse_owned_pending_identity(field):
    operator, _ = ROLES[field]
    row, receipt, catalogue = fresh_owner()
    row["blocks"].append(proposal("shared-followup", operator, kind="completion"))
    saved_kind = "question" if field == "questions" else "task"
    progress = {"state": "ok", "rows": [{
        "id": "saved-need", "kind": saved_kind, "status": "pending",
        "text": "Examine the original account's attribution."}]}
    prior = link(field, "shared-followup")
    prior.update(existing_id="saved-need",
                 target_ids=["saved-observation", "saved-observation"])
    additional = link(field, "shared-followup")
    additional.update(id="additional-need", purpose="Examine another attributed distinction.")
    row[field] = [prior, additional]
    valid, issues = _read_units({"units": [row]}, (0,), SPANS, catalogue, {}, progress,
                               execution_receipt=receipt)
    assert issues == {}
    assert set(valid) == {0}
    assert valid[0][field][0] == {**prior, "target_ids": ["saved-observation"]}
    assert valid[0][field][1] == additional
    assert valid[0]["blocks"][1]["evidence_expression"]["operator"] == operator


@pytest.mark.parametrize("field", ROLES)
@pytest.mark.parametrize("operator", ["record_result", "source_account"])
def test_fresh_links_reject_wrong_operator_preserving_independent_peer(field, operator):
    row, receipt, catalogue = fresh_owner()
    if operator == "source_account":
        row["blocks"].append(proposal("linked-account", operator))
        owner = "linked-account"
    else:
        owner = "owned-block"
    row[field] = [link(field, owner)]
    receipt["requests"].append({"request_index": 1, "record_requirement": {
        "kind": "none", "target_ids": [], "operation": "none", "success_condition": ""}})
    valid, issues = _read_units({"units": [row, independent_peer()]}, (0, 1),
                               SPANS, catalogue, {}, execution_receipt=receipt)
    assert set(valid) == {1}
    assert set(issues) == {0}
    assert f"{field}[0]" in issues[0]
    assert valid[1]["blocks"][0]["evidence_expression"]["operator"] == "source_account"
    assert valid[1]["record_outcome"]["status"] == "none"


@pytest.mark.parametrize("field", ROLES)
def test_typed_link_correction_uses_existing_writer_bound_before_response_review(field):
    row, receipt, _ = fresh_owner()
    row[field] = [link(field, "owned-block")]

    def repair(payload):
        assert "correction" in payload, "A wrong typed link must be corrected before review"
        issues = payload["correction"]["validation_issues"]
        assert [issue["request_index"] for issue in issues] == [0]
        assert f"{field}[0]" in issues[0]["issue"]
        rejected = payload["correction"]["rejected_units"]
        assert [unit["request_index"] for unit in rejected] == [0]
        fixed = deepcopy(rejected[0])
        fixed["blocks"].append(proposal("actual-followup", ROLES[field][0]))
        fixed[field][0]["block_id"] = "actual-followup"
        return {"units": [fixed]}

    model = ContinuationModel([
        {"units": [row]}, repair, verdict(0, outcome="fulfilled")])
    result = run(model, receipt)
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    assert [unit["request_index"] for unit in result.units] == [0]
    assert result.units[0][field][0]["block_id"] == "actual-followup"
    assert result.units[0]["record_outcome"]["effect_ids"] == row["record_outcome"]["effect_ids"]
