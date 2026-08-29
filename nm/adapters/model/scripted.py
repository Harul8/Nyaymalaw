"""The scripted adapter. Deterministic, offline, free.

It exists for two reasons, and the second is the important one:

  1. Class-A and class-B tests need a model that costs nothing and never varies.
  2. IT IS THE SECOND PROVIDER. Provider independence is proved by SWITCHING,
     not by having an interface -- an abstraction nobody has switched is an
     unexercised claim, the same shape as a guard with no production caller.
     This adapter is what makes that switch runnable on every commit instead of
     only when a second API key appears.

It implements the SAME contract suite as the real adapters. If a change to the
port fits OpenAI and not this one, the port has become OpenAI-shaped and the
design has quietly failed.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from nm.adapters.model._budget import estimate_tokens, guard_budget
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, TierConfig
from nm.ports.model import (
    EmbeddingResult,
    ModelResult,
    Prompt,
    SchemaViolation,
    Tier,
    Usage,
)

Responder = Callable[[Prompt, Tier], str]


_tokens = estimate_tokens  # one owner: nm.adapters.model._budget


class ScriptedModelAdapter:
    """Serves canned or rule-derived responses. Never touches the network."""

    def __init__(
        self,
        config: ModelConfig,
        responses: Mapping[str, str] | None = None,
        responder: Responder | None = None,
    ) -> None:
        self._config = config
        self._responses = dict(responses or {})
        self._responder = responder
        self.calls: list[tuple[Tier, Prompt]] = []

    # ------------------------------------------------------------- port ---
    @property
    def provider(self) -> str:
        return "scripted"

    def resolved_model(self, tier: Tier) -> str:
        return f"scripted:{self._cfg(tier).model}"

    def context_budget(self, tier: Tier) -> int:
        return CONTEXT_BUDGET[tier]

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        text = self._respond(prompt, tier)
        return self._result(text, None, prompt, tier, started)

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        raw = self._respond(prompt, tier)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # NEVER best-effort parsed. Lenient parsing is how an invented
            # vocabulary once emptied a charge map.
            raise SchemaViolation(f"scripted response is not JSON: {exc}") from exc
        _require_schema(data, schema)
        return self._result(None, data, prompt, tier, started)

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        cfg = self._cfg(Tier.EMBED)
        vectors = tuple(_deterministic_vector(t) for t in texts)
        n = sum(_tokens(t) for t in texts)
        return EmbeddingResult(
            vectors=vectors, model=cfg.model, provider=self.provider,
            usage=Usage(tokens_in=n, tokens_out=0, cost_usd=0.0),
        )

    # -------------------------------------------------------- internals ---
    def _cfg(self, tier: Tier) -> TierConfig:
        return self._config.for_tier(tier)

    def _guard_budget(self, prompt: Prompt, tier: Tier) -> None:
        guard_budget(prompt, tier)

    def _respond(self, prompt: Prompt, tier: Tier) -> str:
        if self._responder is not None:
            return self._responder(prompt, tier)
        for needle, reply in self._responses.items():
            if needle.lower() in prompt.user.lower():
                return reply
        return self._responses.get("__default__", "SCRIPTED")

    def _result(self, text, data, prompt: Prompt, tier: Tier, started: float) -> ModelResult:
        cfg = self._cfg(tier)
        t_in = _tokens((prompt.system or "") + prompt.user)
        t_out = _tokens(text or json.dumps(data))
        return ModelResult(
            text=text, data=data, tier=tier, provider=self.provider,
            model=self.resolved_model(tier),
            usage=Usage(tokens_in=t_in, tokens_out=t_out,
                        cost_usd=cfg.cost(t_in, t_out), cached_tokens=0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _deterministic_vector(text: str, dim: int = 16) -> tuple[float, ...]:
    """Stable pseudo-embedding. Not semantically meaningful and not pretending
    to be -- it exists so the port's embed() has a testable shape."""
    acc = [0.0] * dim
    for i, ch in enumerate(text):
        acc[i % dim] += (ord(ch) % 17) / 17.0
    norm = sum(v * v for v in acc) ** 0.5 or 1.0
    return tuple(round(v / norm, 6) for v in acc)


def _require_schema(data: Any, schema: Mapping[str, Any]) -> None:
    """The subset of JSON Schema the port promises across providers.

    Deliberately small: the port contract is the INTERSECTION of what providers
    offer, and a validator richer than that intersection would let a call site
    depend on something the next adapter cannot honour.
    """
    if schema.get("type") == "object":
        if not isinstance(data, dict):
            raise SchemaViolation(f"expected an object, got {type(data).__name__}")
        for key in schema.get("required", []):
            if key not in data:
                raise SchemaViolation(f"required property {key!r} is missing")
        props = schema.get("properties", {})
        for key, spec in props.items():
            if key in data:
                _require_type(key, data[key], spec)
    elif schema.get("type") == "array" and not isinstance(data, list):
        raise SchemaViolation(f"expected an array, got {type(data).__name__}")


_TYPES = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "object": dict, "array": list}


def _require_type(key: str, value: Any, spec: Mapping[str, Any]) -> None:
    want = spec.get("type")
    if want and want in _TYPES and not isinstance(value, _TYPES[want]):
        raise SchemaViolation(
            f"property {key!r} should be {want}, got {type(value).__name__}")
    if "enum" in spec and value not in spec["enum"]:
        # An unrecognised value is treated as ABSENT, never as valid.
        raise SchemaViolation(
            f"property {key!r} value {value!r} is outside the permitted "
            f"vocabulary {spec['enum']}")
