"""Independent review coverage is complete, attributable and bounded."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.continuation import _input
from nm.brain.continuation_verification import verify_continuation
from nm.brain.conversation import Conversation
from nm.shared.model_port import Tier
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import (
    ContinuationModel,
    conversation_plan,
    mixed_purpose_unit,
    reviewed_units,
    unit,
    verdict,
)


def review(payload, *indexes):
    return reviewed_verdicts(payload, verdict(*indexes))


def checked(model, *units):
    if any("evidence_expression" in block for unit in units for block in unit["blocks"]):
        payload = _input(Conversation(()), "I have a signed receipt.", conversation_plan(),
                         None, None, None, None, (), "latest")[0]
        rendered = tuple(reviewed_units(payload, *units))
        return verify_continuation(model, input_payload=payload, units=rendered)
    # Explicit historical/internal review fixtures retain their old wire shape.
    return verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": []}}, units=units)


def test_shared_recovery_exhaustion_preserves_checked_response_peer():
    class BoundedModel(ContinuationModel):
        def __init__(self):
            super().__init__([lambda payload: review(payload, 0)])
            self.claims = []

        def claim_recovery(self, phase):
            self.claims.append(phase)
            return False

    model = BoundedModel()
    result = checked(model, unit(0), unit(1))

    assert result.decisions[0][0] is True
    assert result.unavailable == (1,)
    assert len(model.calls) == 1
    assert model.claims == ["verify_continuation:correction"]


def test_a_legal_premise_in_an_account_overrides_whole_unit_acceptance():
    proposed = unit(text="The reported agreement creates an enforceable payment obligation.")

    def mistaken_accept(payload):
        data = review(payload, 0)
        data["verdicts"][0]["block_checks"][0].update(
            requires_legal_support=True, verdict="reject",
            reason="Enforceability is a legal consequence, not an attributed reported fact.")
        return data

    model = ContinuationModel([mistaken_accept])
    result = checked(model, proposed)

    assert result.unavailable == ()
    assert result.decisions[0][0] is False
    assert "account-0" in result.decisions[0][1]
    assert "actual selected checked legal passage" in result.decisions[0][1]
    assert len(model.calls) == 1 and model.tiers == [Tier.JUDGE]


@pytest.mark.parametrize("section", ["questions", "next_work"])
def test_hidden_proposal_purpose_overrides_whole_unit_acceptance(section):
    proposed = mixed_purpose_unit()

    def mistaken_accept(payload):
        data = review(payload, 0)
        selected = next(row for row in data["verdicts"][0]["proposal_checks"]
                        if row["section"] == section)
        selected.update(purpose_expressed=False,
                        reason="The stated purpose is absent from the linked visible words.")
        return data

    model = ContinuationModel([mistaken_accept])
    result = checked(model, proposed)

    assert result.decisions[0][0] is False and result.unavailable == ()
    assert section in result.decisions[0][1]
    assert proposed[section][0]["id"] in result.decisions[0][1]
    assert len(model.calls) == 1


def test_a_rejected_block_overrides_acceptance_and_preserves_a_valid_request_peer():
    def mixed_review(payload):
        data = review(payload, 0, 1)
        data["verdicts"][0]["block_checks"][1].update(
            verdict="reject", reason="The question assumes an unreported event.")
        return data

    model = ContinuationModel([mixed_review])
    result = checked(model, unit(0), unit(1))

    assert result.decisions[0][0] is False
    assert result.decisions[1][0] is True
    assert result.unavailable == () and len(model.calls) == 1


@pytest.mark.parametrize("fault", ["missing_block", "duplicate_block", "foreign_block",
                                  "missing_proposal", "wrong_proposal_owner", "duplicate_proposal"])
def test_incomplete_review_repairs_only_the_unread_peer_once(fault):
    bad = mixed_purpose_unit()
    bad["request_index"] = 1
    original = deepcopy(bad)

    def incomplete(payload):
        data = review(payload, 0, 1)
        row = data["verdicts"][1]
        if fault == "missing_block":
            row["block_checks"].pop()
        elif fault == "duplicate_block":
            row["block_checks"][1] = deepcopy(row["block_checks"][0])
        elif fault == "foreign_block":
            row["block_checks"][0]["block_id"] = "unknown-owner"
        elif fault == "missing_proposal":
            row["proposal_checks"].pop()
        elif fault == "wrong_proposal_owner":
            row["proposal_checks"][0]["block_id"] = "next-work"
        else:
            row["proposal_checks"][1] = deepcopy(row["proposal_checks"][0])
        return data

    def repaired(payload):
        assert payload["units"] == reviewed_units(payload["input"], original)
        assert payload["validation_issues"][0]["request_index"] == 1
        assert "checks" in payload["validation_issues"][0]["issue"]
        return review(payload, 1)

    model = ContinuationModel([incomplete, repaired])
    result = checked(model, unit(0), bad)

    assert {index: accepted for index, (accepted, _) in result.decisions.items()} == {
        0: True, 1: True}
    assert result.unavailable == ()
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [1]
    assert len(model.calls) == 2 and model.tiers == [Tier.JUDGE, Tier.JUDGE]


def test_repeated_missing_review_coverage_keeps_the_valid_peer_and_stops():
    def missing(payload):
        data = review(payload, *(row["request_index"] for row in payload["units"]))
        next(row for row in data["verdicts"] if row["request_index"] == 1)["block_checks"] = []
        return data

    model = ContinuationModel([missing, missing])
    result = checked(model, unit(0), unit(1))

    assert set(result.decisions) == {0} and result.decisions[0][0] is True
    assert result.unavailable == (1,)
    assert len(model.calls) == 2
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [1]


def test_an_old_whole_unit_only_verdict_is_unread_and_never_accepted():
    class WholeUnitOnlyModel(ContinuationModel):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            row = result.data["verdicts"][0]
            row.pop("block_checks")
            row.pop("proposal_checks")
            return replace(result, data={"verdicts": [row]})

    model = WholeUnitOnlyModel([verdict(0), verdict(0)])
    result = checked(model, unit())

    assert result.decisions == {} and result.unavailable == (0,)
    assert len(model.calls) == 2
    assert "block_checks" in model.calls[1][1]["validation_issues"][0]["issue"]
