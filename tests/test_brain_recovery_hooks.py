"""Conditional response repairs use the caller's shared budget and retain peers."""
from nm.brain.conversation import WorkItem
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    _operation_names,
    conversation_plan,
    unit,
    verdict,
)


class DeniedRecoveryModel(ContinuationModel):
    def __init__(self, replies, denied_phase):
        super().__init__(replies)
        self.denied_phase = denied_phase
        self.recovery_claims = []

    def claim_recovery(self, phase):
        self.recovery_claims.append(phase)
        return phase != self.denied_phase


def two_items():
    return conversation_plan(items=tuple(
        WorkItem(request=request, relation="new", matter_scope="proposed", priority="ordinary",
                 next_step="answer", reply="A supported reply remains to be checked.")
        for request in ("Summarise the attributed receipt account.",
                        "Identify the consequential missing account distinction.")))


def test_writer_budget_exhaustion_retains_independently_checked_peer():
    model = DeniedRecoveryModel(
        [{"units": [unit(0), {"request_index": 1}]}, verdict(0)],
        "continue_conversation:correction")
    result = _continue(model, plan=two_items())
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert model.recovery_claims == ["continue_conversation:correction"]
    assert [row["request_index"] for row in result.units] == [0]
    assert [row["state"] for row in result.coverage] == ["ok", "unavailable"]


def test_reviewer_budget_exhaustion_retains_valid_reviewed_peer():
    model = DeniedRecoveryModel(
        [{"units": [unit(0), unit(1)]}, verdict(0)], "verify_continuation:correction")
    result = _continue(model, plan=two_items())
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert model.recovery_claims == ["verify_continuation:correction"]
    assert [row["request_index"] for row in result.units] == [0]
    assert [row["state"] for row in result.coverage] == ["ok", "unavailable"]
