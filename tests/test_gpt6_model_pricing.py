"""Published release IDs and disjoint cache billing; no provider calls."""
from decimal import Decimal

import pytest

from nm.shared.model_config import TokenPricing, load, token_pricing
from nm.shared.model_port import ConfigurationError, Tier

pytestmark = pytest.mark.class_a


def test_authorized_release_names_resolve_without_inventing_dated_snapshots():
    cfg = load({"NM_MODEL_PROVIDER": "openai", "NM_MODEL_ROUTINE": "gpt-6-luna",
        "NM_MODEL_HARD": "gpt-6.1-sol", "NM_MODEL_JUDGE": "gpt-6.1-sol",
        "NM_ALLOW_SAME_MODEL_REVIEW": "true", "NM_EMBED_MODEL": "text-embedding-3-large"})
    assert cfg.for_tier(Tier.ROUTINE).model == "gpt-6-luna"
    assert cfg.for_tier(Tier.HARD).model == cfg.for_tier(Tier.JUDGE).model == "gpt-6.1-sol"
    with pytest.raises(ConfigurationError, match="floating alias"):
        load({"NM_MODEL_PROVIDER": "openai", "NM_MODEL_ROUTINE": "gpt-6-other"})


@pytest.mark.parametrize("model,rates", [
    ("gpt-6-luna", (100, 10, 125, 500)),
    ("gpt-6.1-sol", (2000, 100, 2500, 10000)),
])
def test_pricing_partitions_input_without_charging_cache_writes_twice(model, rates):
    p = token_pricing(model)
    ordinary, cached, write, output = rates
    assert p.cost_micro_usd(1000, 1000) == ordinary + output
    assert p.cost_micro_usd(1000, 0, cached_tokens=1000) == cached
    assert p.cost_micro_usd(1000, 0, cache_write_tokens=1000) == write
    assert p.cost_micro_usd(3000, 1000, cached_tokens=1000, cache_write_tokens=1000) == sum(rates)
    assert p.reserve_micro_usd(1000, 1000) == write + output


def test_long_context_boundary_prices_entire_request_and_rounds_up():
    p = token_pricing("gpt-6.1-sol")
    assert p.cost_micro_usd(272000, 100) == 545000
    assert p.cost_micro_usd(272001, 100) == 1089504
    assert p.reserve_micro_usd(272001, 100) == 1361505
    assert token_pricing("gpt-6-luna").cost_micro_usd(1, 0) == 1
    assert token_pricing("gpt-6-luna").cost_usd(1, 0) == pytest.approx(0.0000001)


@pytest.mark.parametrize("incoming,outgoing,cached,writes", [
    (100, 0, 60, 50), (True, 0, 0, 0), (100, -1, 0, 0), (100, 0, -1, 0),
])
def test_invalid_usage_cannot_be_discounted(incoming, outgoing, cached, writes):
    with pytest.raises(ConfigurationError):
        token_pricing("gpt-6-luna").cost_micro_usd(incoming, outgoing,
            cached_tokens=cached, cache_write_tokens=writes)


def test_unestablished_write_price_and_model_are_not_free():
    with pytest.raises(ConfigurationError, match="Cache writes"):
        TokenPricing(Decimal(1), Decimal(1)).cost_micro_usd(100, 0, cache_write_tokens=1)
    with pytest.raises(ConfigurationError):
        token_pricing("unknown")
