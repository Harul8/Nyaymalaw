"""Offline status-expression and historical-renderer witnesses.

These tests certify deterministic display ownership and replay dispatch, not
semantic adequacy, persistence, provider behavior or useful task completion.
Historical fixtures are authored independently of the fresh renderer.
"""
from copy import deepcopy

import pytest

from nm.brain.execution_contracts import ExecutionEvidenceInvalid
from tests.test_brain_continuation_status_links import (
    ROLES,
    displayed,
    expression_inputs,
    link,
)
from tests.test_brain_record_acknowledgement_contract import inputs, render


@pytest.mark.parametrize("status", ["performed", "unresolved"])
@pytest.mark.parametrize("require_checked", [False, True])
def test_repeated_dedicated_status_composition_is_idempotent(status, require_checked):
    continuation, receipt, catalogue = expression_inputs(status)
    first = render(continuation, receipt, catalogue, require_checked=require_checked)
    saved_request = deepcopy(receipt["requests"][0])
    second = render(first, receipt, catalogue, require_checked=require_checked)
    assert second == first
    assert receipt["requests"][0] == saved_request
    assert second["units"][0]["record_outcome"]["block_id"] == "owned-block"
    assert len(second["units"][0]["blocks"]) == 1


@pytest.mark.parametrize("status", ["performed", "unresolved"])
def test_record_result_operator_retains_status_identity_after_kind_changes(status):
    continuation, receipt, catalogue = expression_inputs(status)
    receipt["requests"][0]["response_mode"] = "substantive"
    first = render(continuation, receipt, catalogue)
    changed_label = deepcopy(first)
    changed_label["units"][0]["blocks"][0]["kind"] = "account"
    second = render(changed_label, receipt, catalogue)
    assert second == first
    assert second["units"][0]["record_outcome"]["block_id"] == "owned-block"
    assert len(second["units"][0]["blocks"]) == 1


@pytest.mark.parametrize("operator", ["source_account", "comparison", "limitation"])
def test_pure_acknowledgement_preserves_independent_substantive_expression(operator):
    continuation, receipt, catalogue = expression_inputs()
    peer = displayed("independent-substantive", operator)
    continuation["units"][0]["blocks"].append(peer)
    original = deepcopy(peer)
    final = render(continuation, receipt, catalogue)
    unit = final["units"][0]
    assert unit["blocks"][1] == original
    assert len(unit["blocks"]) == 2
    assert unit["blocks"][0]["evidence_expression"]["operator"] == "record_result"
    assert unit["record_outcome"]["block_id"] == "owned-block"
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


def test_effect_only_acknowledgement_uses_exact_checked_effect_and_one_status_block():
    continuation, receipt, catalogue = expression_inputs()
    original_effects = deepcopy(continuation["units"][0]["record_outcome"]["effect_ids"])
    final = render(continuation, receipt, catalogue)
    unit = final["units"][0]
    assert len(unit["blocks"]) == 1
    assert unit["record_outcome"]["effect_ids"] == original_effects
    assert unit["blocks"][0]["text"] == (
        "Saved record changes:\nNew entry: The handover was on 4 May.")
    assert receipt["requests"][0]["acknowledgement_delivery"] == "code_only"


@pytest.mark.parametrize("version", [None, "record_acknowledgement_v2"])
def test_historical_acknowledgement_replay_keeps_saved_legacy_rendering(version):
    continuation, receipt, catalogue = inputs()
    request = receipt["requests"][0]
    request["acknowledgement_delivery"] = "code_only"
    if version is not None:
        request["acknowledgement_contract"] = version
    # Legacy snapshots deliberately predate the closed expression contract.
    peer = deepcopy(continuation["units"][0]["blocks"][0])
    peer.update(id="legacy-account", kind="account", text="Historical display words.")
    continuation["units"][0]["blocks"].append(peer)
    final = render(continuation, receipt, catalogue, replay=True)
    assert [block["id"] for block in final["units"][0]["blocks"]] == [
        "owned-block", "legacy-account"]
    expected_kinds = ["completion", "account"] if version is None else [
        "acknowledgment", "acknowledgment"]
    assert [block["kind"] for block in final["units"][0]["blocks"]] == expected_kinds
    assert all(block["text"] == "Saved record changes:\nNew entry: The handover was on 4 May."
               for block in final["units"][0]["blocks"])
    assert request.get("acknowledgement_contract") == version


def test_unknown_saved_acknowledgement_contract_cannot_reuse_fresh_renderer():
    continuation, receipt, catalogue = expression_inputs()
    receipt["requests"][0]["acknowledgement_contract"] = "unknown-status-renderer"
    with pytest.raises(ExecutionEvidenceInvalid, match="contract is unsupported"):
        render(continuation, receipt, catalogue, replay=True)


def test_fresh_status_stamps_v4_instead_of_upgrading_historical_v3_in_place():
    continuation, receipt, catalogue = expression_inputs()
    render(continuation, receipt, catalogue)
    assert receipt["requests"][0]["acknowledgement_contract"] == (
        "record_acknowledgement_v4")


@pytest.mark.parametrize("status", ["performed", "unresolved"])
def test_preview_then_checked_final_is_stable_and_replays_under_its_saved_version(status):
    continuation, receipt, catalogue = expression_inputs(status)
    original = deepcopy(continuation)
    preview = render(continuation, receipt, catalogue, require_checked=False)
    preview_request = deepcopy(receipt["requests"][0])
    assert render(preview, receipt, catalogue, require_checked=False) == preview
    assert receipt["requests"][0] == preview_request
    final = render(preview, receipt, catalogue)
    expected = deepcopy(preview)
    expected["units"][0]["blocks"][0].pop("inline_citations")
    assert final == expected
    saved_request = deepcopy(receipt["requests"][0])
    assert render(final, receipt, catalogue) == final
    assert render(final, receipt, catalogue, replay=True) == final
    assert receipt["requests"][0] == saved_request
    assert continuation == original
    assert final["units"][0]["record_check"] == original["units"][0]["record_check"]


@pytest.mark.parametrize("operator", ["source_account", "comparison", "limitation"])
def test_independent_operator_cannot_become_status_through_mutable_completion_label(operator):
    continuation, receipt, catalogue = expression_inputs()
    receipt["requests"][0]["response_mode"] = "substantive"
    peer = displayed("independent-substantive", operator)
    peer["kind"] = "completion"
    continuation["units"][0]["blocks"].append(peer)
    final = render(continuation, receipt, catalogue)
    assert final["units"][0]["blocks"][1] == peer
    assert final["units"][0]["record_outcome"]["block_id"] == "owned-block"
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


def test_effect_acknowledgement_preserves_substantive_blocks_and_both_typed_followups():
    continuation, receipt, catalogue = expression_inputs()
    unit = continuation["units"][0]
    for operator in ("source_account", "comparison", "limitation"):
        unit["blocks"].append(displayed("independent-" + operator, operator))
    for field, (operator, _) in ROLES.items():
        identity = "independent-" + operator
        unit["blocks"].append(displayed(identity, operator))
        unit[field] = [link(field, identity)]
    original = deepcopy(unit)
    preview = render(continuation, receipt, catalogue, require_checked=False)
    final = render(preview, receipt, catalogue)
    assert final["units"][0]["blocks"][1:] == original["blocks"][1:]
    assert final["units"][0]["questions"] == original["questions"]
    assert final["units"][0]["next_work"] == original["next_work"]
    assert final["units"][0]["record_outcome"] == original["record_outcome"]
    assert final["units"][0]["sufficiency"] == original["sufficiency"]
    assert final["units"][0]["work"] == original["work"]
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"
    assert render(final, receipt, catalogue) == final


@pytest.mark.parametrize("status", ["performed", "unresolved"])
def test_shared_substantive_owner_gets_one_separate_status_node_across_preview_and_final(status):
    continuation, receipt, catalogue = expression_inputs(status)
    peer = displayed("owned-block", "source_account")
    continuation["units"][0]["blocks"] = [peer]
    original = deepcopy(continuation)
    preview = render(continuation, receipt, catalogue, require_checked=False)
    preview_unit = preview["units"][0]
    assert preview_unit["blocks"][0] == peer
    assert len(preview_unit["blocks"]) == 2
    status_id = preview_unit["record_outcome"]["block_id"]
    assert status_id != "owned-block"
    assert preview_unit["blocks"][1]["id"] == status_id
    assert preview_unit["blocks"][1]["evidence_expression"]["operator"] == "record_result"
    assert render(preview, receipt, catalogue, require_checked=False) == preview
    final = render(preview, receipt, catalogue)
    assert final["units"][0]["blocks"][0] == peer
    assert len(final["units"][0]["blocks"]) == 2
    assert final["units"][0]["record_outcome"]["block_id"] == status_id
    assert render(final, receipt, catalogue) == final
    assert render(final, receipt, catalogue, replay=True) == final
    assert continuation == original


def test_fixed_status_still_requires_checked_outcome_after_successful_preview():
    continuation, receipt, catalogue = expression_inputs(checked=False)
    preview = render(continuation, receipt, catalogue, require_checked=False)
    with pytest.raises(ExecutionEvidenceInvalid, match="no checked record outcome"):
        render(preview, receipt, catalogue)


def test_status_operator_cannot_launder_an_unknown_expression_rendering_version():
    continuation, receipt, catalogue = expression_inputs()
    continuation["units"][0]["blocks"][0]["expression_contract"] = "unknown-expression"
    with pytest.raises(ExecutionEvidenceInvalid, match="unsupported rendering contract"):
        render(continuation, receipt, catalogue)


def _historical_status(identity, status, *, span_ids=()):
    """Literal saved v3 node, independent of canonical_record_acknowledgements."""
    return {
        "id": identity, "kind": "limitation" if status == "unresolved" else "acknowledgment",
        "uncertainty": "none", "text": (
            "The requested record work remains unfinished." if status == "unresolved" else
            "Saved record changes:\nNew entry: The handover was on 4 May."),
        "evidence_expression": {"operator": "record_result", "source_ids": [],
                                "record_ids": [], "focus": "none"},
        "span_ids": list(span_ids), "record_ids": [], "legal_source_ids": [],
        "expression_contract": "evidence_expression_v1",
    }


def _historical_account(identity):
    return {
        "id": identity, "kind": "account", "uncertainty": "none",
        "text": "Your message includes: “The handover was on 4 May.”",
        "evidence_expression": {"operator": "source_account", "source_ids": ["L1"],
                                "record_ids": [], "focus": "none"},
        "span_ids": ["L1"], "record_ids": [], "legal_source_ids": [],
        "inline_citations": [], "expression_contract": "evidence_expression_v1",
    }


@pytest.mark.parametrize("status", ["performed", "unresolved"])
def test_v3_saved_pure_ack_replays_its_original_overwritten_peer_nodes(status):
    continuation, receipt, catalogue = expression_inputs(status)
    # v3 rewrote every pure-ack block, including an independent source account.
    # Replay preserves that historical result; only fresh v4 corrects selection.
    continuation["units"][0]["blocks"] = [
        _historical_status("owned-block", status),
        _historical_status("historically-overwritten-account", status, span_ids=("L1",)),
    ]
    request = receipt["requests"][0]
    request.update(acknowledgement_contract="record_acknowledgement_v3",
                   acknowledgement_delivery="code_only")
    original = deepcopy(continuation)
    saved_receipt = deepcopy(receipt)
    assert render(continuation, receipt, catalogue, replay=True) == original
    assert render(original, receipt, catalogue, replay=True) == original
    assert continuation == original
    assert receipt == saved_receipt


@pytest.mark.parametrize("status", ["performed", "unresolved"])
def test_v3_saved_substantive_nodes_keep_original_status_and_account_metadata(status):
    continuation, receipt, catalogue = expression_inputs(status)
    continuation["units"][0]["blocks"] = [
        _historical_status("owned-block", status), _historical_account("historical-account")]
    request = receipt["requests"][0]
    request.update(response_mode="substantive",
                   acknowledgement_contract="record_acknowledgement_v3",
                   acknowledgement_delivery="substantive_followup")
    original = deepcopy(continuation)
    saved_receipt = deepcopy(receipt)
    assert render(continuation, receipt, catalogue, replay=True) == original
    assert receipt == saved_receipt


def test_v3_replay_keeps_its_kind_based_status_selection_instead_of_using_v4():
    continuation, receipt, catalogue = expression_inputs()
    old_status = _historical_status("owned-block", "performed")
    old_status["kind"] = "account"
    continuation["units"][0]["blocks"] = [old_status]
    request = receipt["requests"][0]
    request.update(response_mode="substantive",
                   acknowledgement_contract="record_acknowledgement_v3",
                   acknowledgement_delivery="code_only")
    expected = deepcopy(continuation)
    historical_id = "nm_record_outcome_332c731c859a7f1b"
    expected["units"][0]["blocks"].append(_historical_status(historical_id, "performed"))
    expected["units"][0]["record_outcome"]["block_id"] = historical_id
    result = render(continuation, receipt, catalogue, replay=True)
    assert result == expected
    assert request["acknowledgement_contract"] == "record_acknowledgement_v3"
    assert request["acknowledgement_delivery"] == "substantive_followup"
    assert render(result, receipt, catalogue, replay=True) == result


@pytest.mark.parametrize("version", ["unknown-status-renderer", "", 4])
def test_unknown_saved_version_refuses_without_altering_saved_nodes_or_receipt(version):
    continuation, receipt, catalogue = expression_inputs()
    receipt["requests"][0]["acknowledgement_contract"] = version
    before = deepcopy((continuation, receipt))
    with pytest.raises(ExecutionEvidenceInvalid, match="contract is unsupported"):
        render(continuation, receipt, catalogue, replay=True)
    assert (continuation, receipt) == before
