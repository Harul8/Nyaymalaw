"""EVERY PAID CALL IS METERED against its account (owner decision O24; plan AN.17), whatever its outcome:
charged at the cost the provider's usage established, kept as not established where there is none, and
never charged for what NM refused before sending. Offline: a recording adapter stands in for the
provider, and the records go into the real usage store so their shape is the store's."""
from __future__ import annotations

import asyncio

import pytest

from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import CALL_FIELDS
from nm.shared.budget_contracts import Completion
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_metered import MeteredModel
from nm.shared.model_port import (ModelResult, OutputTruncated, Prompt, ProviderUnavailable, SchemaViolation,
                                  Tier, TierUnavailable, Transcription, Usage, UsageLimitReached)

pytestmark = pytest.mark.class_a

PROMPT = Prompt(system="Read the brief.", user="the client's words", operation="core_understanding")
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def receipt(cost=0.00027, model="gpt-6-luna", retries=0, written=0):
    usage = Usage(1200, 300, cost, 200, {"cache_write_tokens": written, "response_id": "resp_1"})
    return ModelResult(text=None, data={"a": "b"}, tier=Tier.ROUTINE, provider="openai", model=model,
                       usage=usage, latency_ms=5, retries=retries, completion=Completion.COMPLETE)


class Provider:
    """Answers, or fails, as the test says."""

    provider = "openai"

    def __init__(self, outcome):
        self.outcome = outcome

    def resolved_model(self, tier):
        return "gpt-6-luna"

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    complete = tool_call = None


@pytest.fixture
def kept(tmp_path):
    store = FileUsage(tmp_path / "usage.sqlite")
    records = []

    def record(call):
        records.append(call)
        store.record("advocate@chambers.in", call)  # the store refuses any other shape
    record.store = store
    record.records = records
    return record


def run(outcome, kept):
    model = MeteredModel(inner=Provider(outcome), record=kept)
    return model, (lambda: model.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=500))


def test_the_meter_answers_the_whole_port_it_wraps_and_speech():
    from nm.shared.model_port import ModelPort

    for name in [name for name in dir(ModelPort) if not name.startswith("_")] + ["transcribe", "live_transcription"]:
        assert hasattr(MeteredModel, name), f"MeteredModel does not answer {name!r}"


def test_an_answered_call_is_charged_at_its_receipt(kept):
    model, call = run(receipt(cost=0.00027, written=40, retries=1), kept)
    assert call().data == {"a": "b"}
    assert kept.records == [{"kind": "structured", "operation": "core_understanding", "tier": "routine",
                             "model": "gpt-6-luna", "outcome": "ok", "attempts": 2, "tokens_in": 1200,
                             "tokens_out": 300, "cached_tokens": 200, "cache_write_tokens": 40,
                             "audio_seconds": None, "micro_usd": 270}]
    assert tuple(kept.records[0]) == CALL_FIELDS and model.dropped == 0
    assert kept.store.standing("advocate@chambers.in")["spent"] == 270


def test_a_refused_answer_still_costs_what_the_provider_charged(kept):
    rejected = SchemaViolation("a required field was missing", rejected_result=receipt(cost=0.0005))
    _, call = run(rejected, kept)
    with pytest.raises(SchemaViolation):
        call()
    assert kept.records[0]["outcome"] == "SchemaViolation" and kept.records[0]["micro_usd"] == 500
    assert kept.records[0]["model"] == "gpt-6-luna"


def test_a_cut_off_answer_is_charged_at_the_receipt_on_its_error(kept):
    cut = OutputTruncated("stopped at the output limit", usage=Usage(900, 4000, 0.0021), retries=0)
    _, call = run(cut, kept)
    with pytest.raises(OutputTruncated):
        call()
    record = kept.records[0]
    assert (record["outcome"], record["micro_usd"], record["tokens_out"]) == ("OutputTruncated", 2100, 4000)
    assert record["model"] == "gpt-6-luna"  # the model the tier asked for, whose prices made the cost


@pytest.mark.parametrize("failure", [ProviderUnavailable("connection dropped", retries=2),
                                     UsageLimitReached("insufficient_quota")])
def test_a_call_with_no_receipt_is_kept_and_its_cost_is_not_established(kept, failure):
    _, call = run(failure, kept)
    with pytest.raises(type(failure)):
        call()
    record = kept.records[0]
    assert record["micro_usd"] is None and record["model"] == "" and record["tokens_in"] is None
    assert record["outcome"] == type(failure).__name__
    assert record["attempts"] == failure.retries + 1
    assert kept.store.standing("advocate@chambers.in")["spent"] == 0


@pytest.mark.parametrize("refusal", [TierUnavailable("the hard tier is not configured"),
                                     ModelPermissionRefused("Open AI data sharing in your profile")])
def test_nothing_is_recorded_for_what_nm_refused_before_sending(kept, refusal):
    _, call = run(refusal, kept)
    with pytest.raises(type(refusal)):
        call()
    assert kept.records == []


def test_a_record_that_cannot_be_kept_never_fails_the_paid_call():
    def broken(call):
        raise OSError("disk full")
    model = MeteredModel(inner=Provider(receipt()), record=broken)
    assert model.structured(PROMPT, SCHEMA, Tier.ROUTINE).data == {"a": "b"}
    assert model.dropped == 1


class Speech:
    provider = "openai"

    def __init__(self, seconds):
        self.seconds = seconds

    def transcribe(self, audio, **request):
        return Transcription(text="dictated words", provider="openai", model="gpt-transcribe", latency_ms=9,
                             usage={"type": "duration", "seconds": self.seconds})

    async def live_transcription(self, **request):
        return Live()


class Live:
    model, seconds, closed = "gpt-live-transcribe", 30.0, False

    def words(self):
        return "so far"

    async def close(self):
        self.closed = True


def test_a_recording_is_charged_by_the_minute_at_the_duration_reported(kept):
    model = MeteredModel(inner=Speech(60), record=kept)
    assert model.transcribe(b"RIFF", file_name="note.wav", media_type="audio/wav").text == "dictated words"
    record = kept.records[0]
    assert (record["kind"], record["model"], record["audio_seconds"]) == ("transcribe", "gpt-transcribe", 60.0)
    assert record["micro_usd"] == 4500  # USD 0.0045 a minute (nm/shared/model_config.py)
    assert record["operation"] == "transcription"  # never the file's name


def test_a_live_dictation_is_charged_for_the_audio_sent_when_it_closes(kept):
    model = MeteredModel(inner=Speech(0), record=kept)

    async def dictate():
        session = await model.live_transcription(minutes=6)
        assert session.words() == "so far" and kept.records == []
        await session.close()
        await session.close()  # closing twice is metered once
        return session

    asyncio.run(dictate())
    assert len(kept.records) == 1
    record = kept.records[0]
    assert (record["kind"], record["audio_seconds"], record["micro_usd"]) == ("live_transcription", 30.0, 8500)


def test_a_recording_whose_duration_is_not_reported_is_kept_uncharged(kept):
    model = MeteredModel(inner=Speech(None), record=kept)
    model.transcribe(b"RIFF", file_name="note.wav", media_type="audio/wav")
    assert kept.records[0]["audio_seconds"] is None and kept.records[0]["micro_usd"] is None


def test_each_advocates_bound_model_is_metered_innermost_when_a_record_is_given(monkeypatch):
    """The OpenAI route's binding (nm/app/model_permission.py): the policy outside, the tracer inside
    it, and the meter next to the bound adapter, so a refused dispatch is never metered."""
    from nm.app import model_permission
    from nm.shared.model_policed import PolicedModel
    from nm.shared.model_traced import TracedModel

    class Adapter:
        def for_matter_text(self, authorize, *, page_images=False, audio_model=None):
            self.bound = Provider(receipt())
            return self.bound

    monkeypatch.setattr(model_permission, "require_permission", lambda *args, **kwargs: None)
    adapter, records = Adapter(), []
    model = model_permission.bind_text_model(adapter, directory=None, account_id="advocate@chambers.in",
                                             config=None, session_current=lambda: True, record=records.append)
    assert isinstance(model, PolicedModel) and isinstance(model.inner, TracedModel)
    assert isinstance(model.inner.inner, MeteredModel) and model.inner.inner.inner is adapter.bound
    plain = model_permission.bind_text_model(adapter, directory=None, account_id="advocate@chambers.in",
                                             config=None, session_current=lambda: True)
    assert plain.inner.inner is adapter.bound  # without a record nothing is metered, as before
