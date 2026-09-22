"""The OpenAI adapter.

It translates the port's vocabulary into this provider's. Nothing above it
knows that `system` becomes a message role, that structured output uses
`response_format`, or that rate limits arrive as a 429 -- which is the whole
point: that knowledge lives here and nowhere else.

The `openai` package is imported LAZILY, inside the constructor. Importing it
at module scope would make `nm.adapters.model` unimportable without the extra
installed, and the scripted adapter -- which every class-A test depends on --
lives in the same package.
"""
from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping
from typing import Any

from nm.adapters.model._budget import guard_budget
from nm.adapters.model.call_budget import CallBudget
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, TierConfig
from nm.domain.budget import Completion
from nm.domain.external_ai import ModelPermissionRefused
from nm.domain.text import blank
from nm.ports.model import (
    ConfigurationError,
    ContentRefused,
    ContextOverflow,
    EmbeddingResult,
    ModelResult,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    RateLimited,
    SchemaViolation,
    Tier,
    Usage,
    on_the_wire,
    require_schema,
)

MAX_RETRIES = 3
_BACKOFF_BASE = 0.5


#: HOW A PROVIDER SAYS IT STOPPED, mapped to what that means for legal work.
#:
#: ONE TABLE RATHER THAN A COMPARISON AT EACH CALL SITE. The reason the length
#: stop went unnoticed for as long as it did is that exactly one reason was
#: ever compared, in one place, and nothing enumerated the rest.
#:
#: AN UNRECOGNISED REASON IS NOT ESTABLISHED, never complete. A provider that
#: adds a stop reason tomorrow must not have it read as "finished" by a table
#: written today.
_FINISH_REASONS: dict[str, Completion] = {
    "stop": Completion.COMPLETE,
    "end_turn": Completion.COMPLETE,
    "length": Completion.LENGTH_LIMITED,
    "max_tokens": Completion.LENGTH_LIMITED,
    "content_filter": Completion.FILTERED,
}


def _completion_of(reason) -> Completion:
    if reason is None:
        return Completion.NOT_ESTABLISHED
    return _FINISH_REASONS.get(str(reason).strip().lower(),
                               Completion.NOT_ESTABLISHED)


class OpenAIModelAdapter:
    def __init__(self, config: ModelConfig, client: Any | None = None,
                 call_budget: CallBudget | None = None) -> None:
        self._config = config
        self._call_budget = call_budget
        self._before_dispatch: Callable[[], None] | None = None
        if client is not None:
            self._client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise ConfigurationError(
                "the openai package is not installed. `pip install -e .[openai]`"
            ) from exc
        cfg = config.for_tier(Tier.ROUTINE)
        if blank(cfg.api_key):
            raise ConfigurationError(
                "NM_MODEL_API_KEY is not set (or is still the placeholder). "
                "An unconfigured key is a hard failure, never a silent no-op."
            )
        import httpx
        # The approved recipient must not redirect text/credentials elsewhere.
        # Disable implicit environment proxies as well as transport redirects.
        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key, "max_retries": 0,
            "http_client": httpx.Client(follow_redirects=False, trust_env=False),
            "base_url": cfg.base_url or "https://api.openai.com/v1",
        }
        self._client = OpenAI(**kwargs)

    def for_matter_text(self, before_dispatch: Callable[[], None]) -> OpenAIModelAdapter:
        """Request-bound authority, shared transport; no shared consent state."""
        bound = OpenAIModelAdapter(self._config, client=self._client, call_budget=self._call_budget)
        bound._before_dispatch = before_dispatch
        return bound

    def with_call_budget(self, budget: CallBudget) -> OpenAIModelAdapter:
        bound = OpenAIModelAdapter(self._config, client=self._client, call_budget=budget)
        bound._before_dispatch = self._before_dispatch
        return bound

    # ------------------------------------------------------------- port ---
    @property
    def provider(self) -> str:
        return "openai"

    def resolved_model(self, tier: Tier) -> str:
        return self._cfg(tier).model

    def context_budget(self, tier: Tier) -> int:
        return CONTEXT_BUDGET[tier]

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        return self._call(prompt, tier, schema=None, max_tokens=max_tokens)

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        return self._call(prompt, tier, schema=schema, max_tokens=max_tokens)

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        if self._before_dispatch is not None or self._call_budget is not None:
            raise ModelPermissionRefused("Matter-text permission does not enable embeddings.")
        cfg = self._cfg(Tier.EMBED)
        resp = self._retrying(lambda: self._client.embeddings.create(
            model=cfg.model, input=list(texts)))
        vectors = tuple(tuple(d.embedding) for d in resp.data)
        t_in = getattr(getattr(resp, "usage", None), "prompt_tokens", 0) or 0
        return EmbeddingResult(
            vectors=vectors, model=cfg.model, provider=self.provider,
            usage=Usage(tokens_in=t_in, tokens_out=0, cost_usd=cfg.cost(t_in, 0)),
        )

    # -------------------------------------------------------- internals ---
    def _cfg(self, tier: Tier) -> TierConfig:
        return self._config.for_tier(tier)

    def _call(self, prompt: Prompt, tier: Tier, schema, max_tokens) -> ModelResult:
        if self._before_dispatch is not None and (
                (prompt.system is not None and not isinstance(prompt.system, str))
                or not isinstance(prompt.user, str)):
            raise ModelPermissionRefused("Only text is permitted; raw media cannot be sent.")
        cfg = self._cfg(tier)
        # The port's budget, enforced BEFORE the call and identically to every
        # other adapter. Relying on the provider to report overflow would make
        # the budget a provider concept and let a prompt that does not port
        # pass locally.
        guard_budget(prompt, tier)
        started = time.perf_counter()

        messages = []
        if prompt.system:
            # The cacheable prefix. This provider caches long stable prefixes
            # automatically, so the port's contract is honoured by keeping the
            # system message first and stable rather than by an explicit flag.
            messages.append({"role": "system", "content": prompt.system})
        messages.append({"role": "user", "content": prompt.user})

        kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages, "store": False}
        if max_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                # STRICT. The provider compiles the schema into a grammar and
                # MASKS any token that would break it, so an enum violation
                # becomes unemittable rather than caught afterwards — a role
                # read declaring eleven permitted values returned "claimant"
                # and it reached the core.
                #
                # `require_schema` in the port STAYS. One mechanism at the
                # wire and one at the boundary is not duplication here: the
                # scripted adapter has no grammar, and a second provider might
                # treat `strict` as advisory. The port's check is the one that
                # applies to every adapter.
                "json_schema": {"name": "nm_result", "strict": True,
                                # OUR METADATA NEVER GOES OVER THE WIRE.
                                # See `nm.ports.model.on_the_wire`.
                                "schema": on_the_wire(schema)},
            }

        resp, retries = self._retrying_counted(
            lambda: self._client.chat.completions.create(**kwargs), model=cfg.model)

        choice = resp.choices[0]
        completion = _completion_of(getattr(choice, "finish_reason", None))
        if completion is Completion.FILTERED:
            raise ContentRefused(
                "the provider refused on content grounds. This is a provider "
                "behaviour, not a fact about the matter.")
        # THE LENGTH STOP WAS NOT CHECKED AT ALL. BK-49-AC1.
        #
        # `content_filter` was, and `length` was not -- so a response cut off
        # at the token limit came back as an ordinary answer. With a text read
        # it ends mid-sentence; with a structured read the JSON can still
        # close its braces and pass `require_schema`, and what is missing left
        # no trace for any downstream check to find.
        #
        # It is RAISED rather than returned because this method's contract is
        # a complete result. `ModelResult.completion` carries the same fact on
        # every other path, so a caller that wants whatever arrived can see it
        # without this method pretending the answer finished.
        if completion is Completion.LENGTH_LIMITED:
            raise OutputTruncated(
                "the provider stopped at the output limit, so this answer "
                "ends where the budget did rather than where the reasoning "
                "did. It is unfinished, not short.")
        raw = choice.message.content or ""

        data = None
        text: str | None = raw
        if schema is not None:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SchemaViolation(f"response was not valid JSON: {exc}") from exc
            # THE DECLARED SCHEMA IS ENFORCED HERE, not by the provider.
            # Provider strict output is defence in depth, not a substitute
            # for validating the actual returned bytes. The port owns this
            # check so every adapter applies the same contract.
            require_schema(data, schema)
            text = None

        usage = getattr(resp, "usage", None)
        t_in = getattr(usage, "prompt_tokens", 0) or 0
        t_out = getattr(usage, "completion_tokens", 0) or 0
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0

        return ModelResult(
            text=text, data=data, tier=tier, provider=self.provider, model=cfg.model,
            usage=Usage(tokens_in=t_in, tokens_out=t_out,
                        cost_usd=cfg.cost(t_in, t_out), cached_tokens=cached),
            latency_ms=int((time.perf_counter() - started) * 1000),
            retries=retries,
            completion=completion,
        )

    def _retrying(self, fn):
        return self._retrying_counted(fn)[0]

    def _retrying_counted(self, fn, *, model: str = "") -> tuple[Any, int]:
        """Bounded retry with backoff. Retries are COUNTED and returned --
        an invisible retry is an invisible cost."""
        last: Exception | None = None
        for attempt in range(MAX_RETRIES):
            if self._before_dispatch is not None:
                self._before_dispatch()
            reservation = self._call_budget.reserve(model) if self._call_budget else None
            try:
                response = fn()
                if reservation:
                    self._call_budget.settle(reservation, response)
                return response, attempt
            except Exception as exc:  # noqa: BLE001 - re-raised as typed below
                normalised = _normalise(exc)
                last = normalised
                if isinstance(normalised, RateLimited) and attempt < MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.2))
                    continue
                raise normalised from exc
        raise last  # pragma: no cover - loop always returns or raises


def _normalise(exc: Exception) -> Exception:
    """Map provider-specific failures onto the port's typed errors.

    Matching on the class name rather than importing openai's exception tree
    keeps this working when the package is absent (the scripted path) and when
    the SDK reorganises its exceptions.
    """
    name = type(exc).__name__
    msg = str(exc)
    low = msg.lower()
    if name in ("RateLimitError",) or "rate limit" in low or "429" in low:
        return RateLimited(msg)
    if "context_length_exceeded" in low or "maximum context length" in low:
        return ContextOverflow(msg)
    if name in ("APIConnectionError", "APITimeoutError", "InternalServerError") or \
            "connection" in low or "timeout" in low:
        return ProviderUnavailable(msg)
    if "content_filter" in low or "content policy" in low:
        return ContentRefused(msg)
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return ConfigurationError(msg)
    return ProviderUnavailable(msg)
