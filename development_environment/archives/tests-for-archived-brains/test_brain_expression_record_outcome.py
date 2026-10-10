"""Receipt rendering owns status expressions without changing historical prose."""
from copy import deepcopy

import pytest

from nm.brain.evidence_rendering import EVIDENCE_EXPRESSION_CONTRACT, rendered_block
from nm.brain.execution_contracts import (
    ExecutionEvidenceInvalid,
    canonical_record_acknowledgements,
)
from tests.test_brain_execution_contracts import receipt

pytestmark = pytest.mark.class_a


def fixture(kind="account", *, operator="source_account"):
    source = {"L1": {"id": "L1", "role": "advocate", "turn_id": "turn",
                      "text": "The date is not confirmed."}}
    block = rendered_block({"id": "account", "kind": kind, "uncertainty": "reported",
                            "evidence_expression": {
                                "operator": operator,
                                "source_ids": [] if operator == "record_result" else ["L1"],
                                "record_ids": [], "focus": "none"}},
                           spans=source, records={}, sources={})
    evidence = receipt(activated=())
    evidence["requests"][0]["record_requirement"] = {"kind": "change"}
    evidence["record_changes"] = []
    unit = {"request_index": 0, "blocks": [block], "questions": [], "next_work": [],
            "record_outcome": {"status": "unresolved", "block_id": "account",
                               "effect_ids": [], "current_record_ids": [], "reason": "Pending."},
            "record_check": {"outcome": "unfinished", "reason": "The date was not changed."}}
    return {"units": [unit]}, evidence


@pytest.mark.parametrize("kind", ["account", "question", "assessment", "next_step"])
def test_added_status_has_its_own_expression_and_preserves_substantive_owner(kind):
    continuation, evidence = fixture(kind)
    original = deepcopy(continuation["units"][0]["blocks"][0])
    result = canonical_record_acknowledgements(continuation, evidence, record_catalogue={})
    account, status = result["units"][0]["blocks"]
    assert account == original
    assert status["text"] == "The requested record work remains unfinished."
    assert status["expression_contract"] == EVIDENCE_EXPRESSION_CONTRACT
    assert status["evidence_expression"] == {
        "operator": "record_result", "source_ids": [], "record_ids": [], "focus": "none"}
    assert canonical_record_acknowledgements(
        result, deepcopy(evidence), record_catalogue={}, replay=True) == result


def test_completion_owner_is_rendered_from_unfinished_receipt_not_its_expression_quote():
    continuation, evidence = fixture("completion", operator="record_result")
    result = canonical_record_acknowledgements(continuation, evidence, record_catalogue={})
    block, = result["units"][0]["blocks"]
    assert block["text"] == "The requested record work remains unfinished."
    assert block["evidence_expression"]["operator"] == "record_result"


def test_unknown_expression_contract_is_not_silently_repaired_by_status_rendering():
    continuation, evidence = fixture("completion", operator="record_result")
    continuation["units"][0]["blocks"][0]["expression_contract"] = "unknown"
    with pytest.raises(ExecutionEvidenceInvalid):
        canonical_record_acknowledgements(continuation, evidence, record_catalogue={})


def test_legacy_status_does_not_acquire_a_new_expression_certification():
    continuation, evidence = fixture("completion")
    block = continuation["units"][0]["blocks"][0]
    block.pop("evidence_expression")
    block.pop("expression_contract")
    result = canonical_record_acknowledgements(continuation, evidence, record_catalogue={})
    assert "evidence_expression" not in result["units"][0]["blocks"][0]
    assert "expression_contract" not in result["units"][0]["blocks"][0]
