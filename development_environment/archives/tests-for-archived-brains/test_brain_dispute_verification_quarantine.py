"""A rejected sibling does not erase an independently admissible verdict."""

from copy import deepcopy

import pytest

from nm.shared.model_port import SchemaViolation, Tier, TierUnavailable
from tests.brain_verdict_quarantine_support import (
    Judge,
    broken_sibling,
    envelope,
    proposals,
    review,
)

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("kind", ["dispute"])
@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("defect", ["missing_account", "foreign_source", "wrong_boolean",
                                   "semantic_contradiction"])
def test_faulty_sibling_stays_unread_and_sound_peer_survives(kind, strict, defect):
    def wrong(payload):
        return broken_sibling(payload, defect)

    judge = Judge([wrong, wrong], strict=strict)
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind)[:1]
    assert result["unread"] == ["C2" if kind == "dispute" else "D2"]
    assert result["coverage"]["state"] == "unassessed"
    correction = judge.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == result["unread"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == [
        "C1" if kind == "dispute" else "D1"]
    assert len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
def test_one_targeted_correction_admits_both_without_rechecking_sound_peer(kind):
    judge = Judge([broken_sibling, envelope])
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind) and result["unread"] == []
    assert result["coverage"]["state"] == "complete"
    correction = judge.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == [
        "C2" if kind == "dispute" else "D2"]
    assert len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
def test_shared_budget_exhaustion_preserves_peer_without_complete_coverage(kind):
    judge = Judge([broken_sibling], recovery=False)
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind)[:1]
    assert len(result["unread"]) == 1 and result["coverage"]["state"] == "unassessed"
    assert len(judge.calls) == 1


@pytest.mark.parametrize("kind", ["dispute"])
@pytest.mark.parametrize("defect", ["unknown_field", "unaddressable_row"])
def test_unknown_shell_is_corrected_or_remains_explicitly_unassessed(kind, defect):
    def wrong(payload):
        result = envelope(payload)
        if defect == "unknown_field":
            result["undeclared_effect"] = {"state": "completed"}
        else:
            result["verdicts"].append({"verdict": "accept"})
        return result

    judge = Judge([wrong, wrong])
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind) and result["unread"] == []
    assert result["coverage"]["state"] == "unassessed"
    assert "$envelope" in result["coverage"]["validation_issue"]
    assert judge.calls[1]["payload"]["candidates"] == [] and len(judge.calls) == 2
    if kind == "dispute":
        assert result["status"]["state"] == "partial"
        assert result["status"]["envelope_unread"]


@pytest.mark.parametrize("kind", ["dispute"])
def test_shell_correction_restores_completion_without_discarding_checked_units(kind):
    def wrong(payload):
        return {**envelope(payload), "undeclared_effect": True}

    judge = Judge([wrong, envelope])
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind) and result["coverage"]["state"] == "complete"
    assert judge.calls[1]["payload"]["candidates"] == [] and len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
def test_coverage_only_correction_preserves_every_checked_verdict(kind):
    def wrong(payload):
        result = envelope(payload)
        del result["coverage"]["state"]
        return result

    judge = Judge([wrong, envelope])
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind) and result["coverage"]["state"] == "complete"
    assert judge.calls[1]["payload"]["candidates"] == [] and len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
@pytest.mark.parametrize("failure", ["wrong_tier", "downgrade"])
def test_quarantine_on_the_wrong_tier_cannot_supply_any_independent_decision(kind, failure):
    judge = Judge([broken_sibling],
                  tier=Tier.ROUTINE if failure == "wrong_tier" else Tier.JUDGE,
                  downgraded_from=Tier.ROUTINE if failure == "downgrade" else None)
    with pytest.raises(TierUnavailable):
        review(kind, judge)
    assert len(judge.calls) == 1


@pytest.mark.parametrize("kind", ["dispute"])
@pytest.mark.parametrize("missing_receipt", ["no_quarantine", "accounting_mismatch"])
def test_missing_or_mismatched_receipt_preserves_whole_error_behavior(kind, missing_receipt):
    judge = Judge([broken_sibling, broken_sibling],
                  quarantine=missing_receipt != "no_quarantine",
                  mismatch=missing_receipt == "accounting_mismatch")
    result = review(kind, judge)
    assert result["accepted"] == () and len(result["unread"]) == 2
    assert result["coverage"]["state"] == "unassessed" and len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
def test_unread_shell_without_an_observable_sink_cannot_claim_whole_review(kind):
    def wrong(payload):
        return {**envelope(payload), "unowned": "ambiguous content"}

    judge = Judge([wrong, wrong])
    with pytest.raises(SchemaViolation, match="envelope remained unread"):
        review(kind, judge, requested=False, sinks=False)
    assert len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["dispute"])
def test_legitimate_no_change_review_still_completes_once(kind):
    judge = Judge([envelope])
    result = review(kind, judge, candidates=())
    assert result["accepted"] == () and result["unread"] == []
    assert result["coverage"]["state"] == "complete" and len(judge.calls) == 1


@pytest.mark.parametrize("kind", ["dispute"])
def test_quarantine_is_not_mutated_by_row_validation_or_correction(kind):
    judge = Judge([broken_sibling, envelope])
    review(kind, judge)
    first = deepcopy(judge.calls[0]["output"])
    assert len(first["verdicts"]) == 2
    assert "account_check" in first["verdicts"][0]
    assert "account_check" not in first["verdicts"][1]
    assert judge.quarantined[0].rejected_result.data == first

