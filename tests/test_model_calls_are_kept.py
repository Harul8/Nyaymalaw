"""Every model call is kept — what was asked, what came back, and whether it was empty.

WHY THIS EXISTS
-----------------
`TurnMetrics` records `llm_calls: 11`. It does not record which eleven, what
any was asked, what came back, or which returned nothing.

That gap was paid for. B-088 -- the correction read fires on one run and not
the next, on identical input -- was diagnosed by running GS-15 twice and
DIFFING TWO TRANSCRIPTS BY HAND. Nothing on the record said what the read was
given or what it answered, and the unit suite could not see it either: every
reader here is tested by handing it an answer and checking the guards, which
proves the guards and says nothing about whether the read produces the answer.

NOT A VENDOR, AND THAT WAS MEASURED
-------------------------------------
Langfuse and Opik were surveyed on 5 September 2026. Both are genuinely
open-source and both REQUIRE A RUNNING SERVER: Langfuse self-hosted is six
containers at a recommended 4 CPU / 16 GiB / 100 GiB, and Opik's
`configure(use_local=True)` connects to a Docker or Kubernetes deployment
rather than running offline. Neither is needed to close the gap -- the gap is
that the records do not exist. Both accept OTLP, so exporting them later is an
adapter that touches nothing here.
"""
from __future__ import annotations


import pytest

from nm.shared.model_port import ModelPort, Prompt, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.model_traced import KEEP, Call, TracedModel, read_name
from tests.test_turn_contract import _model_config

pytestmark = pytest.mark.class_a

OPENING = ("We act for the plaintiff at Hyderabad. The agreement is dated "
           "15 April 1984.")


# ============================ the wrapper is transparent ====================

def test_it_is_a_model_port():
    """Structural conformance, checked rather than assumed.

    The whole design rests on the core not knowing this exists. A wrapper that
    is missing a method fails at the first call site that uses it, which on a
    turn engine of this size is somewhere deep in a branch that runs rarely.
    """
    traced = TracedModel(inner=ScriptedModelAdapter(_model_config()))
    assert isinstance(traced, ModelPort)
    for name in ("provider", "resolved_model", "context_budget", "complete",
                 "structured", "embed"):
        assert hasattr(traced, name), f"the wrapper does not carry {name}"


def test_the_provider_and_the_model_are_the_inner_ones():
    """A wrapper that reported ITSELF as the provider would put `traced` into
    TurnMetrics, the cost baseline and the health endpoint."""
    inner = ScriptedModelAdapter(_model_config())
    traced = TracedModel(inner=inner)
    assert traced.provider == inner.provider
    assert traced.resolved_model(Tier.ROUTINE) \
        == inner.resolved_model(Tier.ROUTINE)


# ================================ the record ================================


def test_a_call_that_raised_is_still_recorded():
    """Recording on the way back keeps NOTHING when there is no way back, and
    the call that failed is the one most worth having."""
    class Angry(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kw):
            raise RuntimeError("the provider fell over")

    traced = TracedModel(inner=Angry(_model_config()))
    with pytest.raises(RuntimeError):
        traced.structured(Prompt(user="what is the date?"),
                          {"x-nm-read": "dates"}, Tier.ROUTINE)

    (call,) = traced.calls
    assert call.read == "dates"
    assert "RuntimeError: the provider fell over" in call.failed
    assert call.user == "what is the date?", (
        "the prompt was lost, which is the one thing needed to reproduce it")


def test_a_long_prompt_says_that_it_was_clipped():
    """A prompt silently cut at a boundary is a diagnosis pointing at the
    wrong line."""
    traced = TracedModel(inner=ScriptedModelAdapter(_model_config()))
    long = "x" * (KEEP + 500)
    traced._keep(Call(ordinal=1, kind="structured", read="dates",
                      tier="routine", model="m", provider="p", latency_ms=1))
    from nm.shared.model_traced import _clip
    clipped = _clip(long)
    assert len(clipped) < len(long)
    assert "not kept" in clipped, clipped
    assert _clip("short") == "short"


# ============================== drained per turn ============================


# ============================= what is not traced ===========================

def test_embedding_calls_are_not_traced():
    """A DECISION, not an omission. An embedding carries no prompt and no
    answer a person can read; what it would contribute is a latency and a
    count, both of which TurnMetrics already holds. Keeping the corpus text
    would put the largest payloads in the build into every transcript to
    record the least diagnostic call."""
    calls: list = []

    class Embedder(ScriptedModelAdapter):
        def embed(self, texts):
            calls.append(texts)
            return None

    traced = TracedModel(inner=Embedder(_model_config()))
    traced.embed(("a paragraph",))
    assert calls == [("a paragraph",)]
    assert traced.calls == [], "an embedding was written into the trace"


def test_a_schema_with_no_marker_is_named_rather_than_left_blank():
    """A blank reads as "no schema was sent", which is a different and more
    serious thing than "the schema was not labelled"."""
    assert read_name({"x-nm-read": "dates"}) == "dates"
    assert read_name({"title": "Something"}) == "Something"
    assert read_name({}) == "no schema — free text"
    assert read_name(None) == "no schema — free text"
    assert read_name({"type": "object"}) == "unnamed"


# ============================== and it is sealed ============================

