"""ONE contract suite, run against EVERY adapter.

This is the file that makes provider independence real rather than aspirational.
If a change to the port fits OpenAI and not the scripted adapter, the port has
become OpenAI-shaped and the design has quietly failed -- and this suite is what
notices.

The OpenAI adapter is exercised through a fake client rather than the network:
these are class-A tests and must run every commit in seconds, offline and free.
The live check against the real API is a separate, deliberate class-C test.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.ports.model import (
    ContextOverflow,
    ModelPort,
    ModelResult,
    Prompt,
    RateLimited,
    SchemaViolation,
    Tier,
    TierUnavailable,
)

pytestmark = pytest.mark.class_a

SCHEMA = {
    "type": "object",
    "required": ["side"],
    "properties": {
        "side": {"type": "string", "enum": ["moving", "defending", "unknown"]},
        "confidence": {"type": "number"},
    },
}


def _config(**overrides) -> ModelConfig:
    tiers = {
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", "gpt-4o-mini-2024-07-18", "k", None),
        Tier.EMBED: TierConfig(Tier.EMBED, "openai", "text-embedding-3-large", "k", None),
        Tier.JUDGE: TierConfig(Tier.JUDGE, "openai", "gpt-5.1", "k", None),
    }
    tiers.update(overrides)
    return ModelConfig(tiers=tiers)


class _FakeOpenAI:
    """Minimal stand-in for the OpenAI client, shaped like the real response."""

    def __init__(self, content: str = "SCRIPTED", *, fail_times: int = 0, exc=None,
                 finish_reason: str = "stop"):
        self._content = content
        self._fail_times = fail_times
        self._exc = exc
        self._finish = finish_reason
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.embeddings = SimpleNamespace(create=self._embed)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._exc or RuntimeError("boom")
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=self._content),
                finish_reason=self._finish)],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=3)),
        )

    def _embed(self, **kwargs):
        n = len(kwargs["input"])
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3]) for _ in range(n)],
            usage=SimpleNamespace(prompt_tokens=5))


def scripted() -> ScriptedModelAdapter:
    return ScriptedModelAdapter(_config(), responses={"__default__": "an answer"})


def openai_ok(content: str = "an answer") -> OpenAIModelAdapter:
    return OpenAIModelAdapter(_config(), client=_FakeOpenAI(content))


ADAPTERS = {"scripted": scripted, "openai": openai_ok}


# ==========================================================================
# THE CONTRACT — every adapter must satisfy every test below.
# ==========================================================================

@pytest.fixture(params=sorted(ADAPTERS), ids=sorted(ADAPTERS))
def adapter(request):
    return ADAPTERS[request.param]()


@pytest.mark.eval_id("E-005")
def test_adapter_satisfies_the_port_protocol(adapter):
    assert isinstance(adapter, ModelPort)


def test_provider_and_resolved_model_are_reported(adapter):
    assert adapter.provider
    resolved = adapter.resolved_model(Tier.ROUTINE)
    assert "gpt-4o-mini-2024-07-18" in resolved


@pytest.mark.eval_id("E-004h")
def test_context_budget_is_declared_by_the_port_not_the_provider(adapter):
    """The budget is the smallest supported window, so a prompt built to it
    ports. Every adapter must report the same number."""
    assert adapter.context_budget(Tier.ROUTINE) == 100_000


@pytest.mark.eval_id("E-006")
def test_complete_returns_normalised_usage(adapter):
    r = adapter.complete(Prompt(user="who moves first?"), Tier.ROUTINE)
    assert isinstance(r, ModelResult)
    assert r.text
    assert r.tier is Tier.ROUTINE
    assert r.usage.tokens_in > 0 and r.usage.tokens_out > 0
    assert r.usage.cost_usd >= 0.0
    assert r.latency_ms >= 0
    assert r.downgraded_from is None and not r.was_downgraded


def test_structured_returns_parsed_data_and_no_text(adapter):
    payload = json.dumps({"side": "defending", "confidence": 0.9})
    a = ScriptedModelAdapter(_config(), responses={"__default__": payload}) \
        if adapter.provider == "scripted" else openai_ok(payload)
    r = a.structured(Prompt(user="which side?"), SCHEMA, Tier.ROUTINE)
    assert r.data == {"side": "defending", "confidence": 0.9}
    assert r.text is None


def test_the_cacheable_prefix_is_accepted_by_every_adapter(adapter):
    r = adapter.complete(Prompt(user="q", system="stable prefix"), Tier.ROUTINE)
    assert r.usage.cached_tokens >= 0  # a no-op is valid; a crash is not


def test_embed_returns_vectors_and_usage(adapter):
    r = adapter.embed(("alpha", "beta"))
    assert len(r.vectors) == 2
    assert all(len(v) > 0 for v in r.vectors)
    assert r.model == "text-embedding-3-large"


@pytest.mark.eval_id("E-004d")
def test_an_unconfigured_tier_raises_with_its_reason(adapter):
    """THE COUNTEREXAMPLE for the silent downgrade.

    `hard` is not configured. Asking for it must raise TierUnavailable saying
    so -- never quietly serve from `routine`, which would be defect shape S1
    wearing a performance optimisation.
    """
    with pytest.raises(TierUnavailable) as exc:
        adapter.complete(Prompt(user="hard question"), Tier.HARD)
    assert "earned" in str(exc.value).lower() or "not configured" in str(exc.value).lower()


@pytest.mark.eval_id("E-004d")
def test_context_overflow_is_typed_never_a_truncation(adapter):
    """THE COUNTEREXAMPLE: silent truncation produces an answer that looks
    complete and was reasoned from a fraction of the material."""
    huge = "x" * (100_000 * 4 + 400_000)
    with pytest.raises(ContextOverflow):
        adapter.complete(Prompt(user=huge), Tier.ROUTINE)


@pytest.mark.eval_id("E-004e")
def test_a_schema_violation_is_never_best_effort_parsed(adapter):
    """THE COUNTEREXAMPLE: lenient parsing is how an invented vocabulary once
    entered the system and emptied a charge map.

    THIS TEST USED TO SKIP THE OPENAI ADAPTER, on the stated ground that
    "enum enforcement is the provider's". It is not: the adapter sends
    `strict: False`, so the provider treats `enum` as a hint -- and a role
    read declaring eleven permitted values returned "claimant", which
    reached the core.

    E-005 says both adapters pass the SAME suite. They did, because the
    suite had written itself an exemption for the one adapter that ships.
    A test that skips the production path does not test less; it reports
    PASS about something it did not run.
    """
    bad = json.dumps({"side": "aggrieved_party"})  # outside the vocabulary
    a = ScriptedModelAdapter(_config(), responses={"__default__": bad}) \
        if adapter.provider == "scripted" else openai_ok(bad)
    with pytest.raises(SchemaViolation) as exc:
        a.structured(Prompt(user="which side?"), SCHEMA, Tier.ROUTINE)
    assert "vocabulary" in str(exc.value)


def test_a_required_property_missing_is_refused_by_every_adapter(adapter):
    """The other half of the contract, and it was never checked at all.

    Stated over the adapter fixture rather than over a named pair, so an
    adapter added later is covered the day it is added.
    """
    bad = json.dumps({"unrelated": "value"})
    a = ScriptedModelAdapter(_config(), responses={"__default__": bad}) \
        if adapter.provider == "scripted" else openai_ok(bad)
    with pytest.raises(SchemaViolation) as exc:
        a.structured(Prompt(user="which side?"), SCHEMA, Tier.ROUTINE)
    assert "required" in str(exc.value)


def test_non_json_structured_output_raises_rather_than_returning_none(adapter):
    a = ScriptedModelAdapter(_config(), responses={"__default__": "not json at all"}) \
        if adapter.provider == "scripted" else openai_ok("not json at all")
    with pytest.raises(SchemaViolation):
        a.structured(Prompt(user="q"), SCHEMA, Tier.ROUTINE)


def test_an_empty_prompt_is_refused_at_construction(adapter):
    with pytest.raises(ValueError):
        Prompt(user="   ")


# ==========================================================================
# Adapter-specific: error normalisation and retry accounting.
# ==========================================================================

def test_openai_rate_limit_is_normalised_and_retried_with_a_count():
    class RateLimitError(Exception):
        pass

    client = _FakeOpenAI("recovered", fail_times=2, exc=RateLimitError("429 rate limit"))
    a = OpenAIModelAdapter(_config(), client=client)
    r = a.complete(Prompt(user="q"), Tier.ROUTINE)
    assert r.text == "recovered"
    assert r.retries == 2, "an invisible retry is an invisible cost"


def test_openai_rate_limit_beyond_the_bound_surfaces_as_typed():
    class RateLimitError(Exception):
        pass

    client = _FakeOpenAI(fail_times=99, exc=RateLimitError("429 rate limit"))
    a = OpenAIModelAdapter(_config(), client=client)
    with pytest.raises(RateLimited):
        a.complete(Prompt(user="q"), Tier.ROUTINE)


def test_openai_content_refusal_is_not_reported_as_a_finding():
    a = OpenAIModelAdapter(_config(), client=_FakeOpenAI("", finish_reason="content_filter"))
    from nm.ports.model import ContentRefused
    with pytest.raises(ContentRefused):
        a.complete(Prompt(user="describe the assault"), Tier.ROUTINE)


def test_the_system_prompt_is_sent_first_and_unchanged():
    """The cacheable prefix only caches if it is stable and leading."""
    client = _FakeOpenAI()
    a = OpenAIModelAdapter(_config(), client=client)
    a.complete(Prompt(user="q", system="PREFIX"), Tier.ROUTINE)
    msgs = client.calls[0]["messages"]
    assert msgs[0] == {"role": "system", "content": "PREFIX"}
    assert msgs[1]["role"] == "user"
