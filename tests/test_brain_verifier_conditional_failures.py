"""A failed conditional review preserves trusted peers and keeps its scope unread."""

import json

import pytest

from nm.brain import dispute_verification
from nm.shared.model_port import (
    ConfigurationError,
    ContentRefused,
    ContextOverflow,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    RateLimited,
    Tier,
    TierUnavailable,
)
from tests.brain_verdict_quarantine_support import (
    SCOPE,
    WORDS,
    Judge,
    LedgerJudge,
    broken_sibling,
    envelope,
    proposals,
    review,
    source_treatments,
)

pytestmark = pytest.mark.class_a

RECOVERABLE = [ProviderUnavailable, ContextOverflow, OutputTruncated, ContentRefused, RateLimited]


@pytest.mark.parametrize("kind", ["material", "dispute"])
@pytest.mark.parametrize("error_type", RECOVERABLE)
def test_conditional_failure_keeps_checked_peer_and_exposes_unread_scope(kind, error_type):
    judge = Judge([broken_sibling, error_type("Conditional dispatch unavailable.")])
    result = review(kind, judge)
    assert result["accepted"] == proposals(kind)[:1]
    assert result["unread"] == ["C2" if kind == "dispute" else "D2"]
    assert result["coverage"]["state"] == "unassessed"
    prior_key = "prior_assessment" if kind == "dispute" else "previous_assessment"
    assert result["coverage"][prior_key]["state"] == "complete"
    assert len(judge.calls) == 2
    if kind == "dispute":
        assert result["status"]["state"] == "partial"
        assert error_type.__name__ in result["status"]["conditional_review_failure"]


@pytest.mark.parametrize("kind", ["material", "dispute"])
@pytest.mark.parametrize("error_type", RECOVERABLE)
def test_initial_transport_failure_is_not_converted_into_an_empty_result(kind, error_type):
    judge = Judge([error_type("Initial dispatch unavailable.")])
    with pytest.raises(error_type):
        review(kind, judge)
    assert len(judge.calls) == 1


@pytest.mark.parametrize("kind", ["material", "dispute"])
@pytest.mark.parametrize("error_type", [ConfigurationError, TierUnavailable])
def test_conditional_configuration_or_review_tier_failure_still_propagates(kind, error_type):
    judge = Judge([broken_sibling, error_type("Independent review integrity unavailable.")])
    with pytest.raises(error_type):
        review(kind, judge)
    assert len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["material", "dispute"])
def test_conditional_failure_without_a_partial_result_sink_still_propagates(kind):
    judge = Judge([broken_sibling, ProviderUnavailable("Conditional dispatch unavailable.")])
    with pytest.raises(ProviderUnavailable):
        review(kind, judge, requested=False, sinks=False)
    assert len(judge.calls) == 2


@pytest.mark.parametrize("kind", ["material", "dispute"])
def test_local_conditional_context_failure_clears_attribution_without_refunding_budget(kind):
    judge = LedgerJudge([broken_sibling, envelope], overflow_on_correction=True)
    result = review(kind, judge)
    phase = ("verify_disputes:correction" if kind == "dispute"
             else "verify_material_grounding:correction")
    assert result["accepted"] == proposals(kind)[:1]
    assert result["coverage"]["state"] == "unassessed"
    assert len(judge.calls) == 1 and judge.reservations == [phase]
    assert judge.abandoned == [phase] and judge.pending is None
    following = Prompt(json.dumps({"candidates": [], "review_scope": SCOPE}),
                       operation="independent_following_read")
    judge.structured(following, judge.calls[0]["schema"], Tier.JUDGE, max_tokens=4096)
    assert judge.dispatched == [
        ("verify_disputes" if kind == "dispute" else "verify_material_grounding", None),
        ("independent_following_read", None),
    ]
    assert judge.reservations == [phase]


def test_dispute_audit_alone_exposes_conditional_unread_units_and_keeps_peer():
    judge = Judge([broken_sibling, ProviderUnavailable("Conditional dispatch unavailable.")])
    audit = []
    accepted = dispute_verification.verify_disputes(
        judge, candidates=proposals("dispute"), earlier=(), latest=WORDS,
        active_disputes=(), source_treatments=source_treatments(), audit=audit,
    )
    assert accepted == proposals("dispute")[:1]
    assert audit[0]["verdict"] == "accept"
    assert audit[1]["candidate_id"] == "C2"
    assert audit[1]["admission_issue"] == "review_unavailable"
    assert len(judge.calls) == 2
