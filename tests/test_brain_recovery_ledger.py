"""Direct recovery-ledger receipts, separately from paired public passages."""

from nm.brain import turn as boundary
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Prompt, Tier, Usage


def test_shared_budget_allows_same_local_correction_for_distinct_invocations():
    class Inner:
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            return ModelResult(text=None, data={}, tier=tier, provider="offline", model="offline",
                               usage=Usage(0, 0, 0), latency_ms=0,
                               completion=Completion.COMPLETE)

    model = boundary._CountedModel(Inner(), recovery_limit=2)
    prompt = Prompt(system="Owned test", user="{}", operation="extract_legal_details")
    for _ in range(2):
        assert model.claim_recovery("extract_legal_details:correction")
        model.structured(prompt, {}, Tier.ROUTINE)
    assert not model.claim_recovery("extract_legal_details:correction")
    receipts = model.metrics()["recovery"]
    assert receipts["reserved_calls"] == receipts["dispatched_calls"] == 2
    assert [row.get("reservation") for row in receipts["events"]] == [1, 2, None]


def test_abandoned_context_reservation_never_labels_next_routine_dispatch():
    class Inner:
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            return ModelResult(text=None, data={}, tier=tier, provider="offline", model="offline",
                               usage=Usage(0, 0, 0), latency_ms=0,
                               completion=Completion.COMPLETE)

    model = boundary._CountedModel(Inner(), recovery_limit=1)
    assert model.claim_recovery("extract_legal_details:correction")
    model.abandon_recovery("extract_legal_details:correction")
    model.structured(Prompt(system="Next Judge", user="{}", operation="verify_disputes"),
                     {}, Tier.JUDGE)
    receipts = model.metrics()
    assert receipts["recovery"]["events"][0]["state"] == "not_dispatched"
    assert receipts["recovery"]["reserved_calls"] == 1
    assert receipts["recovery"]["dispatched_calls"] == 0
    assert "recovery_phase" not in receipts["model_calls"][0]
