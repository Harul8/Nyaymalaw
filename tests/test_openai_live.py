"""One live call against the real provider. Class C: deliberate, not on every commit.

Everything else about the adapter is proved offline against a fake client. This
file exists for the one thing a fake cannot prove: that the pinned snapshot in
`.env` is real, that the key works, and that the provider's structured-output
shape is what the adapter assumes.

Skipped automatically when no key is configured, so it never blocks a commit.
Run it on purpose:

    python -m pytest tests/test_openai_live.py -m class_c -q
"""
from __future__ import annotations

import pytest

from nm.adapters.model.config import load, load_dotenv
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.ports.model import Prompt, Tier

pytestmark = pytest.mark.class_c


@pytest.fixture(scope="module")
def adapter():
    load_dotenv()
    cfg = load()
    if not cfg.for_tier(Tier.ROUTINE).api_key:
        pytest.skip("no NM_MODEL_API_KEY configured")
    return OpenAIModelAdapter(cfg)


def test_the_pinned_snapshot_is_real_and_answers(adapter):
    r = adapter.complete(
        Prompt(user="Reply with exactly the word: ACK",
               system="You are a test harness. Obey literally."),
        Tier.ROUTINE, max_tokens=16)
    assert r.text and "ACK" in r.text.upper()
    assert r.model == "gpt-4o-mini-2024-07-18"
    assert r.usage.tokens_in > 0 and r.usage.tokens_out > 0
    assert r.usage.cost_usd > 0, "a live call that costs nothing is not being metered"


def test_structured_output_matches_the_shape_the_adapter_assumes(adapter):
    # STRICT MODE REJECTS THIS SCHEMA WITHOUT `additionalProperties`.
    #
    # Caught the moment strict was turned on: a 400 naming `context=()`, the
    # root object. Worth keeping in mind for anyone writing a schema by hand —
    # the provider does not degrade to a hint, it refuses the call, which is
    # the failure mode you want and is not the one people expect.
    schema = {
        "type": "object",
        "required": ["side"],
        "additionalProperties": False,
        "properties": {"side": {"type": "string",
                                "enum": ["moving", "defending", "unknown"]}},
    }
    r = adapter.structured(
        Prompt(user="A landlord issued a quit notice to our client. "
                    "Whose side is our client on -- moving or defending? "
                    "If it cannot be determined, say unknown."),
        schema, Tier.ROUTINE, max_tokens=64)
    assert r.data is not None and r.text is None
    assert r.data["side"] in {"moving", "defending", "unknown"}


def test_the_judge_tier_resolves_to_a_different_model(adapter):
    """Tenet P4, verified against the live configuration rather than asserted."""
    from nm.adapters.model.config import load as reload
    cfg = reload()
    if not cfg.configured(Tier.JUDGE):
        pytest.skip("judge tier not configured")
    assert cfg.for_tier(Tier.JUDGE).model != cfg.for_tier(Tier.ROUTINE).model
