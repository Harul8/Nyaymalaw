"""Typed spending and executable numeric ceilings cannot be decorative."""

from __future__ import annotations

import pytest

from nm.shared.model_port import (
    ConfigurationError,
    Prompt,
    SchemaViolation,
    Tier,
    ToolDefinition,
    Usage,
    require_schema,
)

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize(
    "change",
    [
        {"tokens_in": True},
        {"tokens_in": -1},
        {"tokens_out": 1.5},
        {"cached_tokens": -1},
        {"cached_tokens": 11},
        {"cost_usd": float("nan")},
        {"cost_usd": float("inf")},
        {"cost_usd": -0.01},
        {"cost_usd": True},
        {"cost_usd": "0.01"},
    ],
)
def test_an_invalid_receipt_cannot_change_a_budget(change):
    values = {"tokens_in": 10, "tokens_out": 5, "cached_tokens": 2, "cost_usd": 0.01}
    values.update(change)
    with pytest.raises(ValueError):
        Usage(**values)


def _schema(value):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["count"],
        "properties": {"count": value},
    }


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "integer", "minimum": float("nan")},
        {"type": "number", "maximum": float("inf")},
        {"type": "integer", "minimum": True},
        {"type": "integer", "minimum": "1"},
        {"type": "string", "maximum": 10},
        {"type": "integer", "minimum": 5, "maximum": 3},
    ],
)
def test_bad_bounds_fail_when_the_tool_is_registered_before_any_model_call(spec):
    with pytest.raises(ValueError):
        ToolDefinition("bounded_read", "Read a bounded window.", _schema(spec))


@pytest.mark.parametrize("count", [0, 11, True, 1.5])
def test_nested_numeric_bounds_are_enforced_on_returned_arguments(count):
    schema = _schema({"type": "integer", "minimum": 1, "maximum": 10})
    ToolDefinition("bounded_read", "Read a bounded window.", schema)
    with pytest.raises(SchemaViolation):
        require_schema({"count": count}, schema)


def test_nullable_numeric_bound_is_not_a_guess_and_both_endpoints_are_permitted():
    schema = _schema({"type": ["integer", "null"], "minimum": 1, "maximum": 10})
    ToolDefinition("bounded_read", "Read a bounded window.", schema)
    for count in (None, 1, 10):
        require_schema({"count": count}, schema)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(
    "prices", [None, (float("nan"), 1), (1, float("inf")), (-1, 1), (False, 1), (0, 0)]
)
def test_unknown_or_invalid_snapshot_pricing_cannot_be_a_free_external_call(
    provider, prices, monkeypatch
):
    from dataclasses import replace

    from nm.shared.model_config import PRICES, ModelConfig
    from tests.test_tool_calling_port_contract import TOOL, factory

    model, calls = factory(provider)
    config = model._config
    cfg = replace(config.for_tier(Tier.ROUTINE), model="unpriced-snapshot-2026-09-27")
    model._config = ModelConfig({**config.tiers, Tier.ROUTINE: cfg})
    if prices is not None:
        monkeypatch.setitem(PRICES, cfg.model, prices)
    with pytest.raises(ConfigurationError, match="price"):
        model.tool_call(Prompt("Read this", "Trusted guidance"), (TOOL,), Tier.ROUTINE)
    assert not calls


@pytest.mark.parametrize("cached", [False, None, -1, 101])
def test_bad_openai_cache_detail_retains_known_ordinary_token_spend(cached):
    from types import SimpleNamespace as Namespace

    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    from nm.shared.model_port import ProviderUnavailable
    from tests.test_tool_calling_port_contract import config

    cfg = config("openai").for_tier(Tier.ROUTINE)
    response = Namespace(
        id="measured-call",
        usage=Namespace(
            prompt_tokens=100, completion_tokens=20,
            prompt_tokens_details=Namespace(cached_tokens=cached)
        ),
    )
    with pytest.raises(ProviderUnavailable) as observed:
        OpenAIModelAdapter._usage(response, cfg)
    assert observed.value.usage.tokens_in == 100 and observed.value.usage.tokens_out == 20
    assert observed.value.usage.cost_usd > 0
