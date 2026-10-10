"""A finite shared recovery budget preserves capacity for checked reply repair.

Scripted judgments exercise reservation and dispatch mechanics only. Two reserved
calls are an availability floor, not proof every semantic recovery can finish.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from nm.brain.checked import claim_recovery
from nm.brain.turn import _CountedModel
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Prompt, Tier, Usage
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    authority_plan,
    expression_block,
    supplied_law,
    unit,
    verdict,
)

pytestmark = pytest.mark.class_a

UPSTREAM = "extract_legal_details:correction"
WRITER = "continue_conversation:correction"
REVIEWER = "verify_continuation:correction"
LIMITED = "continue_conversation:limited_review"


class Inner:
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        return ModelResult(
            text=None, data={}, tier=tier, provider="offline", model="offline",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def dispatch(model, phase):
    """Consume a successful reservation through the same counted dispatch owner."""
    assert claim_recovery(model, phase)
    model.structured(Prompt(system="Owned recovery test", user="{}",
                            operation=phase.partition(":")[0]), {}, Tier.JUDGE)


def test_default_reserve_prevents_upstream_starvation_without_raising_shared_limit():
    model = _CountedModel(Inner())
    for _ in range(6):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, UPSTREAM)
    dispatch(model, WRITER)
    dispatch(model, REVIEWER)
    assert not claim_recovery(model, LIMITED)
    assert not claim_recovery(model, UPSTREAM)
    budget = model.metrics()["recovery"]
    assert budget["limit"] == budget["reserved_calls"] == budget["dispatched_calls"] == 8
    assert [row["recovery_phase"] for row in model.metrics()["model_calls"]][-2:] == [
        WRITER, REVIEWER]


def test_explicit_zero_reserve_keeps_the_original_unpartitioned_budget():
    model = _CountedModel(Inner(), reply_recovery_reserve=0)
    for _ in range(8):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, WRITER)
    budget = model.metrics()["recovery"]
    assert budget["reserved_calls"] == budget["dispatched_calls"] == budget["limit"] == 8


def test_reply_calls_already_consumed_release_the_remaining_shared_capacity():
    model = _CountedModel(Inner())
    dispatch(model, WRITER)
    dispatch(model, REVIEWER)
    for _ in range(6):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, LIMITED)
    assert model.metrics()["recovery"]["reserved_calls"] == 8


def test_one_early_reply_call_preserves_only_the_one_remaining_reply_permit():
    model = _CountedModel(Inner())
    dispatch(model, REVIEWER)
    for _ in range(6):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, UPSTREAM)
    dispatch(model, LIMITED)
    assert model.metrics()["recovery"]["reserved_calls"] == 8


def test_concurrent_upstream_claims_preserve_reply_capacity_in_the_same_turn_ledger():
    model = _CountedModel(Inner())

    def attempt(_):
        if not claim_recovery(model, UPSTREAM):
            return False
        model.structured(Prompt(system="Owned concurrent recovery test", user="{}",
                                operation="extract_legal_details"), {}, Tier.JUDGE)
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(20))) == 6
    dispatch(model, WRITER)
    dispatch(model, REVIEWER)
    budget = model.metrics()["recovery"]
    assert budget["reserved_calls"] == budget["dispatched_calls"] == 8


@pytest.mark.parametrize("unrelated", [
    "continue_conversation:unrelated", "verify_continuation_fake:correction",
    "unrelated:continue_conversation:correction", "continue_conversation",
])
def test_unrelated_phase_cannot_borrow_the_reply_reserve(unrelated):
    model = _CountedModel(Inner())
    for _ in range(6):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, unrelated)
    dispatch(model, WRITER)
    dispatch(model, LIMITED)
    assert model.metrics()["recovery"]["reserved_calls"] == 8


def test_explicit_three_call_reserve_can_cover_correction_review_and_limited_review():
    model = _CountedModel(Inner(), reply_recovery_reserve=3)
    for _ in range(5):
        dispatch(model, UPSTREAM)
    assert not claim_recovery(model, UPSTREAM)
    for phase in (WRITER, REVIEWER, LIMITED):
        dispatch(model, phase)
    assert not claim_recovery(model, REVIEWER)
    assert model.metrics()["recovery"]["dispatched_calls"] == 8


@pytest.mark.parametrize("upstream,available", [(3, 5), (6, 2)])
def test_reply_floor_is_not_a_cap_on_distinct_bounded_reply_invocations(upstream, available):
    model = _CountedModel(Inner())
    for _ in range(upstream):
        dispatch(model, UPSTREAM)
    # In a mixed request, initial/replacement/limited reviews can each need
    # correction. The one writer retry and limited review remain distinct calls.
    phases = (REVIEWER, WRITER, REVIEWER, LIMITED, REVIEWER)
    for phase in phases[:available]:
        dispatch(model, phase)
    assert not claim_recovery(model, phases[available] if available < len(phases) else WRITER)
    assert model.metrics()["recovery"]["dispatched_calls"] == 8


@pytest.mark.parametrize("limit", [0, 1, 2])
def test_reply_reserve_is_clamped_to_the_explicit_total_limit(limit):
    model = _CountedModel(Inner(), recovery_limit=limit, reply_recovery_reserve=99)
    assert not claim_recovery(model, UPSTREAM)
    for _ in range(limit):
        dispatch(model, REVIEWER)
    assert not claim_recovery(model, WRITER)
    budget = model.metrics()["recovery"]
    assert budget["reserved_calls"] == budget["dispatched_calls"] == budget["limit"] == limit


@pytest.mark.parametrize("reserve", [-1, True, 1.5, "2"])
def test_reply_reserve_requires_a_nonnegative_integer(reserve):
    with pytest.raises(ValueError):
        _CountedModel(Inner(), reply_recovery_reserve=reserve)


def test_repeated_reviewer_phase_has_no_duplicate_label_false_rejection():
    model = _CountedModel(Inner(), recovery_limit=2)
    dispatch(model, REVIEWER)
    dispatch(model, REVIEWER)
    assert not claim_recovery(model, REVIEWER)
    assert model.metrics()["recovery"]["dispatched_calls"] == 2


def test_abandoning_reply_context_does_not_refund_or_relabel_a_later_call():
    model = _CountedModel(Inner())
    assert claim_recovery(model, WRITER)
    model.abandon_recovery(WRITER)
    for _ in range(6):
        dispatch(model, UPSTREAM)
    dispatch(model, REVIEWER)
    assert not claim_recovery(model, LIMITED)
    metrics = model.metrics()
    assert metrics["recovery"]["reserved_calls"] == 8
    assert metrics["recovery"]["dispatched_calls"] == 7
    assert metrics["recovery"]["events"][0]["state"] == "not_dispatched"
    assert metrics["model_calls"][0]["recovery_phase"] == UPSTREAM


def test_claiming_a_new_reply_permit_does_not_reset_an_undispatched_reservation():
    model = _CountedModel(Inner(), recovery_limit=2)
    assert claim_recovery(model, WRITER)
    dispatch(model, LIMITED)
    assert not claim_recovery(model, REVIEWER)
    budget = model.metrics()["recovery"]
    assert budget["reserved_calls"] == 2 and budget["dispatched_calls"] == 1
    assert budget["events"][0]["state"] == "not_dispatched"


def unsafe_legal_proposal():
    proposed = unit()
    proposed["blocks"].insert(1, expression_block(
        "unsupported-law", "assessment", operator="checked_legal", uncertainty="none"))
    return proposed


@pytest.mark.parametrize("reserve,upstream,delivered", [(2, 6, True), (0, 8, False)])
def test_owned_response_boundary_can_review_a_safe_subset_after_upstream_recovery(
        reserve, upstream, delivered):
    proposed = unsafe_legal_proposal()
    accepted = verdict(0)
    accepted["verdicts"][0]["record_check"] = {
        "outcome": "unfinished",
        "reason": "The independently checked subset makes no completed legal claim.",
    }
    responses = [{} for _ in range(upstream)] + [{"units": [proposed]}]
    if delivered:
        responses += [{"units": [proposed]}, accepted]
    inner = ContinuationModel(responses)
    model = _CountedModel(inner, reply_recovery_reserve=reserve)
    for _ in range(upstream):
        dispatch(model, UPSTREAM)
    result = _continue(model, plan=authority_plan(), checked_sources=supplied_law())
    budget = model.metrics()["recovery"]
    assert budget["reserved_calls"] == budget["dispatched_calls"] == 8
    assert "unsupported-law" not in str(result.units)
    if delivered:
        assert result.coverage[0]["state"] == "partial"
        assert [row["id"] for row in result.units[0]["blocks"]] == ["account-0", "limit-0"]
        assert result.units[0]["blocks"][0]["text"] == (
            'Your message includes: “I have a signed receipt.”')
        assert [row["phase"] for row in budget["events"]][-2:] == [WRITER, LIMITED]
    else:
        assert result.units == () and result.coverage[0]["state"] == "unavailable"
        assert not any(prompt.operation == "verify_continuation" for prompt, _ in inner.calls)
