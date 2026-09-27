"""The approved independent model has exact, non-free, versioned cost terms."""
import pytest

from nm.shared.model_config import TierConfig, load, require_priced_snapshot
from nm.shared.model_port import ConfigurationError, Tier

pytestmark = pytest.mark.class_a


def test_the_dated_verifier_and_author_are_distinct_priced_snapshots():
    config = load({
        "NM_MODEL_PROVIDER": "openai",
        "NM_MODEL_ROUTINE": "gpt-4o-mini-2024-07-18",
        "NM_MODEL_JUDGE": "gpt-5.1-2025-11-13",
        "NM_EMBED_MODEL": "text-embedding-3-large",
    })
    author = require_priced_snapshot(config.for_tier(Tier.ROUTINE), provider="openai")
    verifier = require_priced_snapshot(config.for_tier(Tier.JUDGE), provider="openai")
    assert author.model != verifier.model
    assert verifier.price_in == 1.25 and verifier.price_out == 10.0
    assert verifier.cost(1000, 1000) == pytest.approx(0.01125)
    assert author.cost(1000, 1000) == pytest.approx(0.00075)


@pytest.mark.parametrize("name", ["gpt-5.1-unknown", "gpt-5.1-2025-11-14", "unpriced-model"])
def test_an_unpriced_verifier_cannot_be_accepted_as_zero_cost(name):
    config = TierConfig(Tier.JUDGE, "openai", name, None, None)
    with pytest.raises(ConfigurationError, match="versioned price"):
        require_priced_snapshot(config, provider="openai")


def test_using_the_author_snapshot_as_the_judge_still_fails():
    with pytest.raises(ConfigurationError, match="same model"):
        load({
            "NM_MODEL_PROVIDER": "openai",
            "NM_MODEL_ROUTINE": "gpt-4o-mini-2024-07-18",
            "NM_MODEL_JUDGE": "gpt-4o-mini-2024-07-18",
            "NM_EMBED_MODEL": "text-embedding-3-large",
        })
