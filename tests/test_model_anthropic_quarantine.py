"""Completed rejected envelopes stay errors while owned rows remain inspectable."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContentRefused,
    ModelResult,
    OutputTruncated,
    SchemaViolation,
    Tier,
)
from tests.model_quarantine_support import (
    MIXED,
    PROMPT,
    SCHEMA,
    adapter,
)

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("provider", ["anthropic"])
@pytest.mark.parametrize("tier", [Tier.ROUTINE, Tier.JUDGE])
def test_completed_schema_failure_keeps_an_untrusted_object_and_actual_receipt(provider, tier):
    model, calls, response = adapter(provider)
    with pytest.raises(SchemaViolation, match="vocabulary") as caught:
        model.structured(PROMPT, SCHEMA, tier, max_tokens=512)
    error = caught.value
    rejected = error.rejected_result
    assert isinstance(rejected, ModelResult) and rejected.data == MIXED
    assert rejected.completion is Completion.COMPLETE and rejected.text is None
    assert rejected.tier is tier and rejected.provider == provider
    assert rejected.model == model.resolved_model(tier)
    assert rejected.usage == error.usage and rejected.usage.tokens_in == 20
    assert (rejected.latency_ms, rejected.retries) == (error.latency_ms, error.retries)
    assert len(calls) == 1
    if provider == "anthropic":
        response.content[0].input["items"][0]["state"] = "altered after dispatch"
        assert rejected.data == MIXED


@pytest.mark.parametrize("provider", ["anthropic"])
def test_correct_complete_output_still_returns_the_original_result(provider):
    good = {"items": [{"id": "one", "state": "supported"}]}
    model, calls, _ = adapter(provider, data=good)
    result = model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert result.data == good and result.usable and len(calls) == 1


@pytest.mark.parametrize("provider", ["anthropic"])
@pytest.mark.parametrize("outcome", ["limit", "refusal", "unknown"])
def test_incomplete_or_refused_bytes_never_get_a_quarantine(provider, outcome):
    reasons = {
        "openai": {"limit": "length", "refusal": "content_filter", "unknown": "new_reason"},
        "anthropic": {"limit": "max_tokens", "refusal": "refusal", "unknown": "new_reason"},
    }
    model, calls, _ = adapter(provider, finish=reasons[provider][outcome])
    expected = {"limit": OutputTruncated, "refusal": ContentRefused, "unknown": SchemaViolation}
    with pytest.raises(expected[outcome]) as caught:
        model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert getattr(caught.value, "rejected_result", None) is None
    assert caught.value.usage.tokens_out == 12 and len(calls) == 1


@pytest.mark.parametrize("variant", ["wrong_tool", "two_tools", "unsupported", "nonobject", "nan"])
def test_anthropic_ambiguous_or_nonjson_tool_output_has_no_quarantine(variant):
    tool = SimpleNamespace(type="tool_use", id="result-1", name="nm_result", input=MIXED)
    blocks = [copy.deepcopy(tool)]
    if variant == "wrong_tool":
        blocks[0].name = "another_tool"
    elif variant == "two_tools":
        blocks.append(copy.deepcopy(tool))
    elif variant == "unsupported":
        blocks.append(SimpleNamespace(type="unrecognized"))
    elif variant == "nonobject":
        blocks[0].input = ["unowned"]
    else:
        blocks[0].input = {"items": [], "unsupported": float("nan")}
    model, _, _ = adapter("anthropic", blocks=blocks)
    with pytest.raises(SchemaViolation) as caught:
        model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert caught.value.rejected_result is None and caught.value.usage.tokens_in == 20

