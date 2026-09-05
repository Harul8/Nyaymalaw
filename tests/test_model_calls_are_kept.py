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

from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import KEEP, Call, TracedModel, read_name
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.ports.model import ModelPort, Prompt, Tier
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

OPENING = ("We act for the plaintiff at Hyderabad. The agreement is dated "
           "15 April 1984.")


def _engine(tmp_path, inner=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=inner or ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=_Evidence(), model=model), store


def _trace(tmp_path, message=OPENING):
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=date(2026, 9, 5),
                               message=message))
    return store.transcripts_for(out.matter.id)[-1]


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

def test_every_call_is_named_by_the_read_it_served(tmp_path):
    """`llm_calls: 11` and eleven named reads are different records, and the
    difference is the whole point."""
    trace = _trace(tmp_path)["model_calls"]
    reads = [c["read"] for c in trace["calls"]]
    assert trace["count"] == len(reads) > 0
    assert "dates" in reads and "posture" in reads, reads
    assert "unnamed" not in reads, (
        f"a schema reached the model with no x-nm-read marker: {reads}")


def test_an_empty_answer_is_recorded_as_its_own_fact(tmp_path):
    """THE FIELD THIS WAS BUILT FOR.

    `ModelResult` refuses to hold neither text nor data, so an empty answer
    arrives as an empty CONTAINER -- `{"events": []}` -- which is
    indistinguishable downstream from a real "nothing happened". B-088 is
    exactly that case, and it must be visible without re-deriving it from the
    answer bytes.
    """
    trace = _trace(tmp_path)["model_calls"]
    assert "empty" in trace
    for call in trace["calls"]:
        assert isinstance(call["empty"], bool)
    empty = [c["read"] for c in trace["calls"] if c["empty"]]
    assert trace["empty"] == len(empty)


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
    from nm.adapters.model.traced import _clip
    clipped = _clip(long)
    assert len(clipped) < len(long)
    assert "not kept" in clipped, clipped
    assert _clip("short") == "short"


# ============================== drained per turn ============================

def test_a_turn_does_not_carry_the_previous_turn_s_calls(tmp_path):
    """An instance lives for the process. A trace that accumulated would put
    one matter's words into another matter's transcript, which is a
    disclosure and not a tidiness problem."""
    engine, store = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=date(2026, 9, 5),
                                 message=OPENING))
    engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                         today=date(2026, 9, 5),
                         message="The notice was served on 2 January 2025."))

    one, two = store.transcripts_for(first.matter.id)

    # STATED AS THE DRAIN, not as a comparison of prompts. Two turns can
    # legitimately send an identical prompt -- a read whose input did not
    # change between them -- so a repeated prompt is not evidence of a leak
    # and asserting on one would fail for a reason that is not the rule.
    for transcript in (one, two):
        assert transcript["model_calls"]["count"] == transcript["llm_calls"]
    assert [c["n"] for c in two["model_calls"]["calls"]][:1] == [1], (
        "the second turn's ordinals continue from the first, so its trace "
        "was never drained and carries the earlier turn's calls")


def test_the_two_counts_of_one_thing_must_agree(tmp_path):
    """THE CHECK THAT WOULD HAVE CAUGHT IT IMMEDIATELY.

    Measured on 5 September 2026: the tracer read `usage.input_tokens`, which
    this port does not have. It raised inside every read; the reads' own
    `except` correctly recorded four AttributeErrors as violations -- and the
    transcript then reported that the turn made ZERO model calls, which is
    exactly what a turn that made none looks like.

    `llm_calls` is counted by the turn after a read returns; the trace is
    written by the port as the call is made. Two routes to one number, so a
    disagreement means one of them is lying about what happened.
    """
    transcript = _trace(tmp_path)
    assert transcript["model_calls"]["count"] == transcript["llm_calls"] > 0
    disagreements = [v for v in transcript.get("violations", ())
                     if "disagree about how many" in str(v.get("detail"))]
    assert not disagreements, disagreements


def test_a_tracer_that_records_nothing_is_a_violation_and_not_a_silence(
        tmp_path):
    """THE POSITIVE CONTROL, planted on the real path.

    A tracer that quietly stops recording is indistinguishable from a quiet
    turn. Driven with one that drops everything, because the check has to be
    shown failing in the direction that actually happened.
    """
    class Mute(TracedModel):
        def take(self) -> dict:
            super().take()
            return {"calls": [], "count": 0, "empty": 0, "failed": 0,
                    "dropped": 0}

    store = FileMatterStore(tmp_path, key=KEY)
    engine = TurnEngine(
        store=store, evidence=_Evidence(),
        model=Mute(inner=ScriptedModelAdapter(
            _model_config(), responses={"__default__": "Issue the notice."})))
    out = engine.run(TurnInput(advocate_id="adv_1", today=date(2026, 9, 5),
                               message=OPENING))

    transcript = store.transcripts_for(out.matter.id)[-1]
    assert any("disagree about how many" in str(v.get("detail"))
               for v in transcript.get("violations", ())), (
        "a trace recording nothing on a turn that made calls passed silently")


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

def test_the_prompts_are_not_on_disk_in_the_clear(tmp_path):
    """A prompt carries everything the advocate has said.

    `file_store` already draws this line: `record_metrics` is plaintext
    BECAUSE it carries no client words, and `record_turn` gets the matter
    cipher because it does. The trace rides in the transcript, so it inherits
    the cipher -- and that is worth asserting on the BYTES rather than
    trusting, because the whole convention of the metrics directory is that
    its contents are safe to read.
    """
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=date(2026, 9, 5),
                               message=OPENING))
    assert store.transcripts_for(out.matter.id)[-1]["model_calls"]["count"] > 0

    for path in tmp_path.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert b"15 April 1984" not in blob, (
                f"the advocate's words are in the clear in {path.name}")
            assert b"You extract" not in blob, (
                f"a system prompt is in the clear in {path.name}")
