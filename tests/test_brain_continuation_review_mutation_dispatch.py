"""Reviewer presentation preserves full immutable backend evidence dependencies."""
import json
from copy import deepcopy

import pytest

from nm.brain import continuation as writer
from nm.brain import continuation_verification as owner
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, model_mutation_context
from nm.shared.model_port import SchemaViolation, estimate_tokens
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.brain_mutation_dispatch_fixture import (
    check_backend,
    check_presentation,
    context,
    input_payload,
)
from tests.test_brain_continuation import ContinuationModel, unit, verdict

pytestmark = pytest.mark.class_a


def test_reviewer_presents_once_and_backend_decision_uses_full_evidence(monkeypatch):
    raw = input_payload(writer, context())
    before = deepcopy(raw)
    presentations, decisions = [], []
    present, decision = owner.model_mutation_context, owner._decision

    def presentation(value):
        presentations.append(deepcopy(value))
        return present(value)

    def backend(*args, **kwargs):
        assert kwargs["input_payload"] is raw
        check_backend(kwargs["input_payload"])
        decisions.append(deepcopy(kwargs["input_payload"]))
        return decision(*args, **kwargs)

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    monkeypatch.setattr(owner, "_decision", backend)
    model = ContinuationModel([verdict(0)])
    result = owner.verify_continuation(model, input_payload=raw, units=(unit(),))
    assert result.decisions[0][0] is True
    assert result.unavailable == ()
    assert len(model.calls) == len(presentations) == len(decisions) == 1
    check_presentation(model.calls[0][1]["input"], raw)
    assert raw == before


def test_reviewer_preflight_uses_presented_proof_without_trimming_original_words():
    raw = input_payload(writer, context(repeats=600))
    proposed = unit()
    dispatch = {"input": raw, "units": [proposed]}
    lean = json.dumps(model_mutation_context(dispatch), ensure_ascii=False, separators=(",", ":"))
    full = json.dumps(dispatch, ensure_ascii=False, separators=(",", ":"))
    budget = estimate_tokens(owner._SYSTEM + lean) + 4097
    assert estimate_tokens(owner._SYSTEM + full) + 4096 > budget

    class BudgetedModel(ContinuationModel):
        def context_budget(self, tier):
            return budget

    model = BudgetedModel([verdict(0)])
    result = owner.verify_continuation(model, input_payload=raw, units=(proposed,))
    assert result.decisions[0][0] is True
    assert len(model.calls) == 1
    check_presentation(model.calls[0][1]["input"], raw)


def test_reviewer_correction_starts_again_from_full_context_and_keeps_checked_peer(monkeypatch):
    raw = input_payload(writer, context())
    before = deepcopy(raw)
    presentations = []
    present = owner.model_mutation_context

    def presentation(value):
        check_backend(value)
        presentations.append(deepcopy(value))
        return present(value)

    def incomplete(payload):
        data = reviewed_verdicts(payload, verdict(0, 1))
        data["verdicts"][1]["block_checks"].pop()
        return data

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    model = ContinuationModel([incomplete, verdict(1)])
    result = owner.verify_continuation(model, input_payload=raw, units=(unit(0), unit(1)))
    assert result.decisions[0][0] and result.decisions[1][0]
    assert len(model.calls) == len(presentations) == 2
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [1]
    assert raw == before
    for _, payload in model.calls:
        check_presentation(payload["input"], raw)


def test_reviewer_refuses_a_corrupt_ledger_before_dispatch_instead_of_presenting_permits():
    raw = input_payload(writer, context())
    raw["material_coverage"]["execution"]["mutation_authorities"]["seal"] = "forged"
    model = ContinuationModel([])
    with pytest.raises(SchemaViolation, match="changed after scope admission"):
        owner.verify_continuation(model, input_payload=raw, units=(unit(),))
    assert model.calls == []


def test_untrusted_reply_tag_is_preserved_as_draft_data_without_becoming_scope_proof(monkeypatch):
    raw = input_payload(writer, context())
    proposed = unit()
    proposed["contract"] = AUTHORITY_CONTRACT
    original = deepcopy(proposed)
    presentations = []
    present = owner.model_mutation_context

    def presentation(value):
        assert value is raw
        check_backend(value)
        presentations.append(deepcopy(value))
        return present(value)

    def reject_draft(payload):
        assert payload["units"] == [original]
        return verdict(0, accept=False, reason="The unadmitted draft has an undeclared field.")

    monkeypatch.setattr(owner, "model_mutation_context", presentation)
    model = ContinuationModel([reject_draft])
    result = owner.verify_continuation(model, input_payload=raw, units=(proposed,))
    assert result.decisions[0][0] is False
    assert len(model.calls) == len(presentations) == 1
    assert proposed == original
    assert model.calls[0][1]["units"] == [original]
