"""Completed rejected envelopes stay errors while owned rows remain inspectable."""

from __future__ import annotations

import json
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


@pytest.mark.parametrize("provider", ["openai"])
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


@pytest.mark.parametrize("provider", ["openai"])
def test_correct_complete_output_still_returns_the_original_result(provider):
    good = {"items": [{"id": "one", "state": "supported"}]}
    model, calls, _ = adapter(provider, data=good)
    result = model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert result.data == good and result.usable and len(calls) == 1


@pytest.mark.parametrize("provider", ["openai"])
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


@pytest.mark.parametrize("raw", [
    '{"items":', '[{"id":"one"}]', 'null',
    '{"items":[],"items":[{"id":"two","state":"foreign"}]}',
    '{"items":[],"unsupported":NaN}',
])
def test_openai_malformed_nonobject_or_ambiguous_json_has_no_quarantine(raw):
    model, _, _ = adapter("openai", raw=raw)
    with pytest.raises(SchemaViolation) as caught:
        model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert caught.value.rejected_result is None and caught.value.usage.tokens_in == 20


@pytest.mark.parametrize("kwargs", [
    {"extra_choices": 1}, {"tool_calls": [SimpleNamespace(id="other")]},
    {"refusal": "provider refusal"},
])
def test_openai_nonunique_or_refused_message_has_no_quarantine(kwargs):
    model, _, _ = adapter("openai", **kwargs)
    with pytest.raises(SchemaViolation) as caught:
        model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert caught.value.rejected_result is None


@pytest.mark.parametrize("raw", [
    '{"items":[],"items":[]}',
    '{"items":[{"id":"one","state":"supported","state":"supported"}]}',
])
def test_openai_identical_duplicate_json_values_do_not_block_correct_output(raw):
    model, calls, _ = adapter("openai", raw=raw)
    result = model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert result.data == json.loads(raw) and result.usable and len(calls) == 1


def test_openai_conflicting_boolean_and_number_keys_are_not_treated_as_identical():
    model, _, _ = adapter("openai", raw='{"items":[],"extra":true,"extra":1}')
    with pytest.raises(SchemaViolation, match="conflicting") as caught:
        model.structured(PROMPT, SCHEMA, Tier.ROUTINE)
    assert caught.value.rejected_result is None

