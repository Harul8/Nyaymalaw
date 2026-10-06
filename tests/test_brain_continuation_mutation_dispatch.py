"""Writer presentation removes proof duplication without narrowing source meaning."""
import json
from copy import deepcopy

import pytest

from nm.brain import continuation as owner
from nm.brain.execution_contracts import ExecutionEvidenceInvalid
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, model_mutation_context
from nm.shared.model_port import OutputTruncated, estimate_tokens
from tests.brain_mutation_dispatch_fixture import (
    check_backend,
    check_presentation,
    context,
    input_payload,
)
from tests.test_brain_continuation import (
    ContinuationModel,
    _operation_names,
    conversation_plan,
    unit,
    verdict,
)

pytestmark = pytest.mark.class_a


def run(model, inputs):
    return owner.continue_conversation(model, **inputs)


def pending_unit(index=0):
    """The declared existing-record review has not achieved its requested result."""
    proposed = unit(index)
    proposed["record_outcome"].update(
        status="unresolved", block_id=f"limit-{index}",
        reason="The independently declared review of the original record remains unfinished.")
    return proposed


def pending_verdict(*indexes):
    reviewed = verdict(*indexes)
    for row in reviewed["verdicts"]:
        row["record_check"] = {
            "outcome": "unfinished",
            "reason": "The explicit fixture judgment certifies no completed record review.",
        }
    return reviewed


def test_writer_presents_once_and_preserves_full_backend_scope_and_exact_conversation(monkeypatch):
    inputs = context()
    raw = input_payload(owner, inputs)
    before = deepcopy(inputs)
    presented, handoffs = [], []
    present = owner.model_mutation_context
    verify = owner.verify_continuation

    def presentation(value):
        presented.append(deepcopy(value))
        return present(value)

    def handoff(model, *, input_payload, units):
        check_backend(input_payload)
        handoffs.append(deepcopy(input_payload))
        return verify(model, input_payload=input_payload, units=units)

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    monkeypatch.setattr(owner, "verify_continuation", handoff)
    model = ContinuationModel([{"units": [pending_unit()]}, pending_verdict(0)])
    result = run(model, inputs)
    assert result.coverage[0]["state"] == "ok"
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert len(presented) == len(handoffs) == 1
    check_presentation(model.calls[0][1], raw)
    check_backend(presented[0])
    assert inputs == before
    assert handoffs[0]["material_coverage"]["execution"]["mutation_authorities"] == (
        raw["material_coverage"]["execution"]["mutation_authorities"])


def test_writer_preflight_uses_lean_proof_but_keeps_the_entire_large_original_account():
    inputs = context(repeats=600)
    raw = input_payload(owner, inputs)
    lean = json.dumps(model_mutation_context(raw), ensure_ascii=False, separators=(",", ":"))
    full = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    budget = estimate_tokens(owner._SYSTEM + lean) + 4097
    assert estimate_tokens(owner._SYSTEM + full) + 4096 > budget

    class BudgetedModel(ContinuationModel):
        def context_budget(self, tier):
            return budget if not self.calls else 1_000_000

    model = BudgetedModel([{"units": [pending_unit()]}, pending_verdict(0)])
    result = run(model, inputs)
    assert result.coverage[0]["state"] == "ok"
    check_presentation(model.calls[0][1], raw)
    original = inputs["conversation"].messages[0]
    assert "".join(span["text"] for span in model.calls[0][1]["earlier_conversation"][0][
        "source_spans"]) == original.text
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]


def test_truncation_guidance_does_not_present_the_same_lean_ledger_twice(monkeypatch):
    inputs = context()
    presents = []
    present = owner.model_mutation_context

    def presentation(value):
        check_backend(value)
        presents.append(deepcopy(value))
        return present(value)

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    model = ContinuationModel([OutputTruncated("Scripted complete-budget exhaustion"),
                               {"units": [pending_unit()]}, pending_verdict(0)])
    result = run(model, inputs)
    assert result.coverage[0]["state"] == "ok"
    assert _operation_names(model) == ["continue_conversation", "continue_conversation",
                                      "verify_continuation"]
    assert len(presents) == 2
    assert "output_budget_guidance" not in presents[0]
    assert "output_budget_guidance" in presents[1]
    assert model.output_limits[:2] == [4096, 8192]


def test_corrupt_tagged_ledger_cannot_be_hidden_by_model_presentation():
    inputs = context()
    ledger = inputs["material"]["coverage"]["execution"]["mutation_authorities"]
    ledger["authorities"][0]["target_ids"].append("unowned-record")
    model = ContinuationModel([])
    with pytest.raises(ExecutionEvidenceInvalid, match="changed after scope admission"):
        run(model, inputs)
    assert model.calls == []


def test_unadmitted_contract_tag_stays_verbatim_and_only_failed_draft_is_repaired(monkeypatch):
    inputs = context()
    inputs["plan"] = conversation_plan(items=conversation_plan().items * 2)
    receipt = inputs["material"]["coverage"]["execution"]
    receipt["requests"].append({"request_index": 1, "record_requirement": {
        "kind": "none", "target_ids": [], "operation": "none", "success_condition": "",
    }})
    good, bad = pending_unit(0), pending_unit(1)
    bad["contract"] = AUTHORITY_CONTRACT
    presentations = []
    present = owner.model_mutation_context

    def presentation(value):
        assert "correction" not in value
        check_backend(value)
        presentations.append(deepcopy(value))
        return present(value)

    def repair(payload):
        assert [row["request_index"] for row in payload["work_items"]] == [1]
        assert [row["request_index"] for row in payload["correction"]["validation_issues"]] == [1]
        assert payload["correction"]["rejected_units"][0]["contract"] == AUTHORITY_CONTRACT
        return {"units": [pending_unit(1)]}

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    model = ContinuationModel([{"units": [good, bad]}, pending_verdict(0), repair,
                               pending_verdict(1)])
    result = run(model, inputs)
    assert [row["state"] for row in result.coverage] == ["ok", "ok"]
    assert _operation_names(model) == ["continue_conversation", "verify_continuation",
                                      "continue_conversation", "verify_continuation"]
    assert len(presentations) == 2
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [0]
    assert all("contract" not in row for row in result.units)
    assert result.units[0]["blocks"][0]["text"] == (
        'Your message includes: “I have a signed receipt.”')
