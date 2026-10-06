"""Observable outcome nodes; semantic prose remains independently judged."""
from copy import deepcopy

import pytest

from nm.brain import execution_contracts as contracts
from nm.brain.execution_contracts import ExecutionEvidenceInvalid
from tests.test_brain_record_acknowledgement_contract import inputs

pytestmark = pytest.mark.class_a


def render(continuation, receipt, catalogue, **kwargs):
    return contracts.canonical_record_acknowledgements(
        continuation, receipt, record_catalogue=catalogue, **kwargs)


def nodes(*, kind="completion", mode="substantive", status="unresolved", checked=True):
    continuation, receipt, catalogue = inputs(status, checked=checked)
    receipt["requests"][0]["response_mode"] = mode
    continuation["units"][0]["blocks"][0]["kind"] = kind
    return continuation, receipt, catalogue


@pytest.mark.parametrize("mode", ["substantive", "record_acknowledgement"])
@pytest.mark.parametrize("checked", [False, True])
def test_completion_text_is_code_owned_in_every_delivery_mode(mode, checked):
    continuation, receipt, catalogue = nodes(mode=mode, checked=checked)
    lie = "I saved the revision and completed every requested task."
    continuation["units"][0]["blocks"][0]["text"] = lie
    original = deepcopy(continuation)
    result = render(continuation, receipt, catalogue, require_checked=checked)
    unit = result["units"][0]
    assert unit["blocks"][0]["text"] == "The requested record work remains unfinished."
    assert unit["record_outcome"]["status"] == "unresolved"
    assert unit["progress_updates"] == []
    assert receipt["requests"][0]["acknowledgement_contract"] == (
        contracts.RECORD_ACKNOWLEDGEMENT_CONTRACT)
    assert receipt["requests"][0]["acknowledgement_delivery"] == "code_only"
    assert continuation == original


@pytest.mark.parametrize("mode", ["substantive", "record_acknowledgement"])
@pytest.mark.parametrize("field", ["questions", "next_work"])
def test_independent_followup_does_not_disable_record_status(mode, field):
    continuation, receipt, catalogue = nodes(mode=mode)
    unit = continuation["units"][0]
    question = deepcopy(unit["blocks"][0])
    question.update(id="independent-followup", kind="question",
                    text="Which original account changed?")
    unit["blocks"].append(question)
    unit[field] = [{"id": "followup", "block_id": question["id"]}]
    original = deepcopy(unit)
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0]["text"] == "The requested record work remains unfinished."
    assert result["blocks"][1] == original["blocks"][1]
    assert result[field] == original[field]
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


@pytest.mark.parametrize("kind", ["account", "assessment", "question"])
def test_shared_substantive_owner_gets_separate_fixed_node_without_losing_meaning(kind):
    continuation, receipt, catalogue = nodes(kind=kind)
    unit = continuation["units"][0]
    unit["blocks"][0]["text"] = "The original reported account remains attributed and uncertain."
    if kind == "question":
        unit["questions"] = [{"id": "clarification", "block_id": "owned-block"}]
    original = deepcopy(unit)
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0] == original["blocks"][0]
    assert result["questions"] == original["questions"]
    assert result["sufficiency"] == original["sufficiency"]
    assert len(result["blocks"]) == 2
    assert result["record_outcome"]["block_id"] == result["blocks"][1]["id"]
    assert result["blocks"][1]["id"] != result["blocks"][0]["id"]
    assert result["blocks"][1]["text"] == "The requested record work remains unfinished."
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


def test_new_status_node_is_stable_across_final_rendering_and_durable_replay():
    continuation, receipt, catalogue = nodes(kind="account")
    before_review = render(continuation, receipt, catalogue, require_checked=False)
    final = render(before_review, receipt, catalogue)
    original_receipt = deepcopy(receipt)
    assert render(final, receipt, catalogue, replay=True) == final
    assert receipt == original_receipt
    assert len(final["units"][0]["blocks"]) == 2


def test_supported_legal_explanation_and_its_exact_anchors_survive_status_rendering():
    continuation, receipt, catalogue = nodes()
    unit = continuation["units"][0]
    legal = deepcopy(unit["blocks"][0])
    legal.update(id="supported-law", kind="assessment", text="An independently checked legal rule.",
                 legal_source_ids=["owned-law"], inline_citations=[
                     {"text": "checked legal rule", "legal_source_id": "owned-law"}])
    unit["blocks"].append(legal)
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][1] == legal
    assert result["blocks"][0]["legal_source_ids"] == []


def test_wrong_judgment_cannot_make_missing_effect_a_performed_outcome():
    continuation, receipt, catalogue = nodes(status="performed")
    receipt["record_changes"] = []
    with pytest.raises(ExecutionEvidenceInvalid, match="unperformed change"):
        render(continuation, receipt, catalogue)


def test_current_state_uses_owned_entry_without_inventing_prior_change():
    continuation, receipt, catalogue = nodes(status="already_current")
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0]["text"] == "Current record entries:\nThe handover was on 4 May."
    assert result["record_outcome"]["effect_ids"] == []


def test_false_operation_inside_unrestricted_account_remains_a_semantic_dependency():
    continuation, receipt, catalogue = nodes(kind="account")
    lie = "I corrected and saved every requested record."
    continuation["units"][0]["blocks"][0]["text"] = lie
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0]["text"] == lie
    assert result["blocks"][1]["text"] == "The requested record work remains unfinished."
    assert result["record_check"]["outcome"] == "unfinished"


def test_non_record_answer_is_not_rewritten_into_record_status():
    continuation, receipt, catalogue = nodes()
    continuation["units"][0]["record_outcome"].update(
        status="none", block_id="", reason="", effect_ids=[], current_record_ids=[])
    continuation["units"][0]["record_check"]["outcome"] = "not_requested"
    receipt["requests"][0]["record_requirement"] = {"kind": "none"}
    original = deepcopy(continuation)
    assert render(continuation, receipt, catalogue) == original
    assert "acknowledgement_contract" not in receipt["requests"][0]


@pytest.mark.parametrize("mode", ["substantive", "record_acknowledgement"])
def test_unstamped_legacy_replay_retains_the_original_delivery_mode(mode):
    continuation, receipt, catalogue = nodes(mode=mode)
    original = deepcopy(continuation)
    result = render(continuation, receipt, catalogue, replay=True)
    if mode == "substantive":
        assert result == original
        assert "acknowledgement_delivery" not in receipt["requests"][0]
    else:
        block = result["units"][0]["blocks"][0]
        assert block["text"] == "The requested record work remains unfinished."
        assert block["kind"] == "completion"
    assert "acknowledgement_contract" not in receipt["requests"][0]


def test_stamped_v2_mixed_replay_preserves_its_original_followup_behavior():
    continuation, receipt, catalogue = nodes(mode="record_acknowledgement")
    receipt["requests"][0].update(acknowledgement_contract="record_acknowledgement_v2",
                                  acknowledgement_delivery="substantive_followup")
    continuation["units"][0]["questions"] = [{"id": "followup", "block_id": "owned-block"}]
    original_continuation = deepcopy(continuation)
    original_receipt = deepcopy(receipt)
    assert render(continuation, receipt, catalogue, replay=True) == original_continuation
    assert receipt == original_receipt


@pytest.mark.parametrize("version", ["unknown", "", 3])
def test_unknown_renderer_contract_is_never_silently_reinterpreted(version):
    continuation, receipt, catalogue = nodes()
    receipt["requests"][0]["acknowledgement_contract"] = version
    with pytest.raises(ExecutionEvidenceInvalid, match="contract is unsupported"):
        render(continuation, receipt, catalogue, replay=True)


def test_partial_non_record_work_keeps_specific_limit_without_invented_pending_record_task():
    continuation, receipt, catalogue = nodes(kind="account")
    receipt["requests"][0]["record_requirement"] = {"kind": "none"}
    original = deepcopy(continuation)
    assert render(continuation, receipt, catalogue) == original
    assert "acknowledgement_contract" not in receipt["requests"][0]
