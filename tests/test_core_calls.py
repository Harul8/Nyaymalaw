"""Shared correction and receipts; terminal gates never reenter draft recovery."""
import json

import pytest

from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, TurnCalls
from nm.shared.model_port import ContextOverflow, ModelError, Prompt, SchemaViolation, Tier, Usage
from tests.test_core_understanding import Model, unit

pytestmark = pytest.mark.class_a
SCHEMA = {"type": "object"}


def call(ledger, operation="write"):
    return ledger.structured(Prompt(user='{"original":"Exact words"}', system="Stable instruction",
                                    operation=operation), SCHEMA, Tier.ROUTINE, max_tokens=200)


def test_one_shared_correction_across_stages_with_original_context_and_exact_feedback():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    attempts = []
    def activity():
        attempts.append(call(ledger))
        if len(attempts) == 1: raise SchemaViolation("unit u2 selected a foreign source")
        return "checked replacement"
    assert ledger.checked("write", activity) == "checked replacement"
    sent = json.loads(model.calls[1][0].user)
    assert sent["original"] == "Exact words"
    assert "u2" in sent["correction"]["mismatch"]
    assert sent["correction"]["rejected_draft"] == model.data
    assert model.calls[0][0].system == model.calls[1][0].system
    with pytest.raises(CorrectionUnavailable):
        ledger.correct("understand", lambda: call(ledger, "understand"), mismatch="other unit")
    assert ledger.metrics()["llm_calls"] == 2
    assert ledger.metrics()["draft_corrections"] == 1


def test_feedback_never_enters_independent_reviewer():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    def rewrite_and_review():
        call(ledger)
        call(ledger, "review")
    ledger.correct("write", rewrite_and_review, mismatch="source mismatch", rejected={"unsafe": "draft"})
    assert "correction" in json.loads(model.calls[0][0].user)
    assert "correction" not in json.loads(model.calls[1][0].user)


def test_nested_activity_cannot_reset_bound_and_rejection_clears_feedback():
    ledger = TurnCalls(Model({"units": [unit()]}))
    def nested():
        return ledger.correct("inner", lambda: None, mismatch="inner")
    with pytest.raises(CorrectionUnavailable): ledger.correct("outer", nested, mismatch="outer")
    assert ledger.correction is None
    assert ledger.correction_used


def test_terminal_gate_never_uses_draft_recovery_or_another_call():
    ledger = TurnCalls(Model({"units": [unit()]}))
    with pytest.raises(ReleaseWithheld):
        ledger.checked("write", lambda: ledger.withhold("G-GROUND terminal TURN/NONE"))
    assert not ledger.correction_used
    with pytest.raises(ReleaseWithheld): call(ledger)
    with pytest.raises(ReleaseWithheld): ledger.correct("write", lambda: None, mismatch="new label")
    assert not ledger.calls


def test_failed_dispatch_keeps_unknown_usage_distinct_from_zero():
    class Down(Model):
        def structured(self, *args, **kw): raise ModelError("No usage receipt", retries=2)
    ledger = TurnCalls(Down({"units": [unit()]}))
    with pytest.raises(ModelError): ledger.checked("write", lambda: call(ledger))
    metrics = ledger.metrics()
    assert metrics["usage_unconfirmed_calls"] == 1
    assert metrics["reported_transport_retries"] == 2
    assert metrics["calls"][0]["cost_usd"] is None
    assert not ledger.correction_used


def test_rejected_completed_output_retains_usage_for_repair():
    class Rejected(Model):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            raise SchemaViolation("shape", rejected_result=result)
    ledger = TurnCalls(Rejected({"units": [unit()]}))
    with pytest.raises(SchemaViolation): ledger.checked("write", lambda: call(ledger))
    metrics = ledger.metrics()
    assert metrics["llm_calls"] == 2
    assert metrics["tokens_in"] == 2
    assert metrics["usage_unconfirmed_calls"] == 0
    assert ledger.last_output is not None


def test_correction_context_checked_before_dispatch_without_trimming():
    model = Model({"units": [unit()]}, budget=500)
    ledger = TurnCalls(model)
    with pytest.raises(ContextOverflow):
        ledger.correct("write", lambda: call(ledger), mismatch="x " * 3000)
    assert not model.calls
    assert not ledger.calls
    assert ledger.correction_used


def test_unknown_previous_draft_does_not_leak_into_next_feedback():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    call(ledger)
    assert ledger.last_output
    def fail(*args, **kwargs): raise ModelError("unavailable", usage=Usage(0, 0, 0))
    model.structured = fail
    with pytest.raises(ModelError): call(ledger, "different")
    assert ledger.last_output is None
