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
from collections.abc import Mapping
from typing import Any

from nm.adapters.model._budget import guard_budget
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, TierConfig
from nm.domain.text import blank
from nm.ports.model import (
    ConfigurationError,
    ContentRefused,
    ContextOverflow,
    EmbeddingResult,
    ModelResult,
    Prompt,
    ProviderUnavailable,
    RateLimited,
    SchemaViolation,
    Tier,
    Usage,
    require_schema,
)

MAX_RETRIES = 3
_BACKOFF_BASE = 0.5


class OpenAIModelAdapter:
    def __init__(self, config: ModelConfig, client: Any | None = None) -> None:
        self._config = config
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
        kwargs: dict[str, Any] = {"api_key": cfg.api_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        self._client = OpenAI(**kwargs)

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

        kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages}
        if max_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "nm_result", "strict": False, "schema": dict(schema)},
            }

        resp, retries = self._retrying_counted(
            lambda: self._client.chat.completions.create(**kwargs))

        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "content_filter":
            raise ContentRefused(
                "the provider refused on content grounds. This is a provider "
                "behaviour, not a fact about the matter.")
        raw = choice.message.content or ""

        data = None
        text: str | None = raw
        if schema is not None:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SchemaViolation(f"response was not valid JSON: {exc}") from exc
            # THE DECLARED SCHEMA IS ENFORCED HERE, not by the provider.
            # `strict` is off above, so the provider treats `enum` as a
            # hint -- and a role read declaring eleven permitted values
            # returned "claimant", which reached the core. The port owns
            # this check so every adapter applies the same one.
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
        )

    def _retrying(self, fn):
        return self._retrying_counted(fn)[0]

    def _retrying_counted(self, fn) -> tuple[Any, int]:
        """Bounded retry with backoff. Retries are COUNTED and returned --
        an invisible retry is an invisible cost."""
        last: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn(), attempt
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
