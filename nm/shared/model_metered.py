"""EVERY PAID CALL, METERED: what each request to the AI service cost, for the account it was made for
(owner decision O24, 25 Oct 2026; plan AN.17).

    model = PolicedModel(inner=TracedModel(inner=MeteredModel(inner=adapter, record=...)), ...)

WHY A WRAPPER, AND WHY INNERMOST
----------------------------------
`TracedModel` and `PolicedModel` already answer why a wrapper and not a check inside each adapter: one
owner of one decision, which an adapter cannot be written without. This one sits next to the adapter,
inside the tracer and the policy, so it sees exactly what the adapter was asked to send - a dispatch
the policy refused never reaches it - and a tracer's retry of an unconfigured tier on the routine tier
is metered once, as the call it was.

WHAT IS RECORDED (owner, O24: "measure every API call expense regardless of success or failed
response"): one record for each port call that sends work, whatever its outcome. A call the provider
answered carries its receipt, on its result or on its error (`ModelError.usage`: "a rejected response
still cost money"), and is charged at the cost the adapter established from the provider's own usage
report. A call that failed without one is kept with its failure and its attempts, its cost not
established and charged nothing. NOT RECORDED: a refusal NM makes before anything is sent - the
advocate's permission (`ModelPermissionRefused`, not a model error), a tier that is not configured
(`TierUnavailable`) or an allowance used up (below).

WHAT IS LEFT, BEFORE EVERY CALL (owner, 3 Nov 2026, plan AN.37, D42 and D46: "we should stop the conversation in the
middle if the usage is run out -- we should check the usage left before every call"): `before` is asked before each call is
sent - text, embeddings, a recording, live dictation - and refuses it, unsent and unrecorded, once the account's allowance is
used up. A call already sent finishes and is charged.

Speech is priced by the minute (`AUDIO_PRICE_PER_MINUTE`): a recording at the duration the provider
reports, a live dictation at the audio sent, when it closes.

AN ATTEMPT LET GO THAT MAY HAVE BEEN BILLED IS A RECORD OF ITS OWN (plan AN.52, 52i4, D215; the review's F-31). The
transport sends a request again where the one before it failed in a way that may pass; where the client stopped waiting or the
connection was lost, the provider may have done the work and billed it all the same. One record of the call - answered, at the
answering attempt's cost - read as a whole cost in the operator's totals. Each such attempt is kept as a record of its own,
before the call's: outcome 'abandoned', one attempt, its cost not established and so charged to no allowance, counted among the
costs not established. The call's own record is as it was, its attempts counting every attempt.

A RECORD NEVER FAILS A CALL. The call has been made and paid for; like a trace that cannot be kept, a
record that cannot be kept is counted in `dropped` and logged, never raised into the advocate's work.
What a record holds is fixed (nm/arrive/usage_port.py, CALL_FIELDS): names and numbers, no prompt,
message, file name or answer.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from nm.shared.model_port import ModelError, ModelPort, Tier, TierUnavailable
from nm.shared.model_transport import attempts_let_go

log = logging.getLogger(__name__)


def _micro(cost_usd) -> int | None:
    """A receipt's cost in millionths of a dollar, rounded up; None where it is not a cost."""
    if type(cost_usd) not in (int, float) or not math.isfinite(cost_usd) or cost_usd < 0:
        return None
    return int((Decimal(str(cost_usd)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def _audio_micro(model: str, seconds) -> int | None:
    """Speech at its price by the minute; None where the price or the duration is not established."""
    from nm.shared.model_config import AUDIO_PRICE_PER_MINUTE

    rate = AUDIO_PRICE_PER_MINUTE.get(model)
    if rate is None or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        return None
    try:
        cost = Decimal(rate) * Decimal(str(seconds)) * 1_000_000 / 60
    except InvalidOperation:
        return None
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def _int(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


@dataclass
class MeteredModel:
    """Any `ModelPort`, with every paid call recorded against one account."""

    inner: ModelPort
    #: Keeps one record (nm/arrive/usage_port.py, CALL_FIELDS) against the account this model serves.
    record: Callable[[dict], None]
    #: Asked before each call is sent (plan AN.37, D42): raises to refuse it - the account's allowance used up - and the call
    #: is then neither sent nor recorded. None: nothing is asked.
    before: Callable[[], None] | None = None
    dropped: int = 0
    """Records this failed to KEEP. Not calls that failed."""

    # -------------------------------------------------- pass-through -------

    @property
    def provider(self) -> str:
        return self.inner.provider

    def resolved_model(self, tier: Tier) -> str:
        return self.inner.resolved_model(tier)

    def context_budget(self, tier: Tier) -> int:
        return self.inner.context_budget(tier)

    # ------------------------------------------------------- metered -------

    def complete(self, prompt, tier: Tier, *, max_tokens: int | None = None):
        return self._metered("complete", prompt, tier,
                             lambda: self.inner.complete(prompt, tier, max_tokens=max_tokens))

    def structured(self, prompt, schema: Mapping[str, Any], tier: Tier, *, max_tokens: int | None = None):
        return self._metered("structured", prompt, tier,
                             lambda: self.inner.structured(prompt, schema, tier, max_tokens=max_tokens))

    def tool_call(self, prompt, tools, tier, *, messages=(), max_tokens=None):
        return self._metered("tool_call", prompt, tier, lambda: self.inner.tool_call(
            prompt, tools, tier, messages=messages, max_tokens=max_tokens))

    def embed(self, texts: tuple[str, ...]):
        return self._metered("embed", None, Tier.EMBED, lambda: self.inner.embed(texts))

    def transcribe(self, audio: bytes, **request):
        self._ask_before()
        with attempts_let_go() as let_go:
            try:
                heard = self.inner.transcribe(audio, **request)
            except TierUnavailable:
                raise
            except ModelError as exc:
                self._keep_let_go(let_go, "transcribe", "transcription", "", lambda: "")
                self._keep(lambda: self._failed("transcribe", "transcription", "", exc))
                raise
        self._keep_let_go(let_go, "transcribe", "transcription", "", lambda: heard.model)
        self._keep(lambda: self._heard(heard))
        return heard

    async def live_transcription(self, **request):
        self._ask_before()
        try:
            session = await self.inner.live_transcription(**request)
        except TierUnavailable:
            raise
        except ModelError as exc:
            self._keep(lambda: self._failed("live_transcription", "live_dictation", "", exc))
            raise
        return _MeteredLive(session, self)

    # ------------------------------------------------------ the record -----

    def _ask_before(self) -> None:
        """Refuse a call before it is sent where `before` says so (D42); nothing is recorded, for nothing was sent."""
        if self.before is not None:
            self.before()

    def _metered(self, kind: str, prompt, tier: Tier, run):
        operation = getattr(prompt, "operation", None) or ("embed" if kind == "embed" else "")
        self._ask_before()
        with attempts_let_go() as let_go:
            try:
                result = run()
            except TierUnavailable:
                raise  # NM's own refusal before anything was sent; the tracer may use the routine tier.
            except ModelError as exc:
                self._keep_let_go(let_go, kind, operation, tier.value, lambda: self.inner.resolved_model(tier))
                self._keep(lambda: self._failed(kind, operation, tier.value, exc,
                                                asked=lambda: self.inner.resolved_model(tier)))
                raise
        self._keep_let_go(let_go, kind, operation, tier.value, lambda: result.model)
        self._keep(lambda: self._answered(kind, operation, tier.value, result))
        return result

    def _keep_let_go(self, let_go, kind, operation, tier, model) -> None:
        """Each attempt the transport let go after the provider may have done the work, as a record of its own (52i4)."""
        for _ in let_go:
            self._keep(lambda: self._call(kind, operation, tier, model(), "abandoned", 0))

    def _answered(self, kind, operation, tier, result):
        """An answered call, at the cost the adapter established from the provider's usage report."""
        usage = result.usage
        extra = getattr(usage, "provider_extra", None) or {}
        return self._call(kind, operation, tier, result.model, "ok", result.retries,
                          tokens_in=usage.tokens_in, tokens_out=usage.tokens_out,
                          cached_tokens=usage.cached_tokens,
                          cache_write_tokens=_int(extra.get("cache_write_tokens")),
                          micro_usd=_micro(usage.cost_usd))

    def _heard(self, heard):
        """A recording heard, by the minute at the duration the provider reports."""
        usage = heard.usage if isinstance(heard.usage, Mapping) else {}
        seconds = usage.get("seconds") if usage.get("type") == "duration" else None
        return self._call("transcribe", "transcription", "", heard.model, "ok", heard.retries,
                          audio_seconds=seconds if type(seconds) in (int, float) else None,
                          micro_usd=_audio_micro(heard.model, seconds))

    def _failed(self, kind, operation, tier, exc, asked=None):
        """A failed call: charged at the receipt it carries, if the provider answered (then the model is
        the one the tier asked for, whose prices made the cost); otherwise its cost is not established."""
        usage = getattr(exc, "usage", None)
        if usage is None:
            return self._call(kind, operation, tier, "", type(exc).__name__, exc.retries)
        rejected = getattr(exc, "rejected_result", None)
        model = getattr(rejected, "model", None) or (asked() if asked else "")
        extra = getattr(usage, "provider_extra", None) or {}
        return self._call(kind, operation, tier, model, type(exc).__name__, exc.retries,
                          tokens_in=usage.tokens_in, tokens_out=usage.tokens_out,
                          cached_tokens=usage.cached_tokens,
                          cache_write_tokens=_int(extra.get("cache_write_tokens")),
                          micro_usd=_micro(usage.cost_usd))

    @staticmethod
    def _call(kind, operation, tier, model, outcome, retries, *, tokens_in=None, tokens_out=None,
              cached_tokens=None, cache_write_tokens=None, audio_seconds=None, micro_usd=None) -> dict:
        return {"kind": kind, "operation": operation or "", "tier": tier or "", "model": model or "",
                "outcome": outcome, "attempts": (retries if type(retries) is int and retries >= 0 else 0) + 1,
                "tokens_in": _int(tokens_in), "tokens_out": _int(tokens_out),
                "cached_tokens": _int(cached_tokens), "cache_write_tokens": cache_write_tokens,
                "audio_seconds": audio_seconds, "micro_usd": micro_usd}

    def _keep(self, build) -> None:
        """Build one record and keep it. Both happen here, after the call: neither a receipt this
        cannot read nor a store that cannot write may fail a call that was made and paid for."""
        try:
            self.record(build())
        except Exception:  # noqa: BLE001 -- a record must never fail a call that was made and paid for
            self.dropped += 1
            log.warning("A paid call could not be recorded against its account", exc_info=True)


class _MeteredLive:
    """A live dictation whose audio is metered when it closes: the provider is paid for the audio sent."""

    def __init__(self, session, meter: MeteredModel):
        self._session, self._meter, self._kept = session, meter, False

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def close(self) -> None:
        try:
            await self._session.close()
        finally:
            if not self._kept:
                self._kept = True
                self._meter._keep(self._sent)

    def _sent(self):
        seconds = getattr(self._session, "seconds", None)
        model = getattr(self._session, "model", "") or ""
        return self._meter._call("live_transcription", "live_dictation", "", model, "ok", 0,
                                 audio_seconds=seconds if type(seconds) in (int, float) else None,
                                 micro_usd=_audio_micro(model, seconds))
