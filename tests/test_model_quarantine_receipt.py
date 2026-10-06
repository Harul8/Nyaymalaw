"""A completed rejected response is diagnostic evidence, never a valid read."""
from dataclasses import replace

import pytest

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage


def receipt():
    return ModelResult(None, {"units": [{"id": "owned", "value": "unsupported"}]},
                       Tier.ROUTINE, "test", "reader", Usage(5, 3, 0.01), 7, retries=2,
                       completion=Completion.COMPLETE)


def test_quarantined_receipt_is_copied_and_preserves_rejected_accounting():
    result = receipt()
    error = SchemaViolation("Declared vocabulary rejected", rejected_result=result)
    result.data["units"][0]["value"] = "later mutation"
    assert str(error) == "Declared vocabulary rejected"
    assert isinstance(error, SchemaViolation)
    assert error.rejected_result.data["units"][0]["value"] == "unsupported"
    assert (error.usage, error.latency_ms, error.retries) == (result.usage, 7, 2)


@pytest.mark.parametrize("completion", [state for state in Completion
                                        if state is not Completion.COMPLETE])
def test_noncomplete_receipts_cannot_supply_quarantine(completion):
    with pytest.raises(ValueError, match="completed structured"):
        SchemaViolation("rejected", rejected_result=replace(receipt(), completion=completion))


@pytest.mark.parametrize("changes", [
    {"data": []}, {"text": "prose"}, {"tier": "routine"},
    {"latency_ms": -1}, {"retries": True},
    {"data": {"number": float("nan")}}, {"data": {"unknown": object()}},
    {"data": {1: "non-string key"}}, {"data": {"tuple": (1, 2)}},
])
def test_quarantine_requires_normalized_unambiguous_json_receipt(changes):
    with pytest.raises(ValueError):
        SchemaViolation("rejected", rejected_result=replace(receipt(), **changes))


@pytest.mark.parametrize("changes", [
    {"usage": Usage(1, 1, 0)}, {"latency_ms": 8}, {"retries": 3},
])
def test_quarantine_cannot_replace_rejected_accounting(changes):
    with pytest.raises(ValueError, match="accounting"):
        SchemaViolation("rejected", rejected_result=receipt(), **changes)


def test_ordinary_errors_keep_backward_compatible_accounting_and_no_quarantine():
    usage = Usage(2, 1, 0)
    error = SchemaViolation("ordinary", usage=usage, latency_ms=4, retries=1)
    assert error.rejected_result is None
    assert (error.usage, error.latency_ms, error.retries) == (usage, 4, 1)
