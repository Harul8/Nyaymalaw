"""The model port. PRD §7.4.

THE RULE THIS FILE EXISTS TO ENFORCE
------------------------------------
Steps declare a TIER. They never name a model. Everything about provider
independence follows from that one rule, so the vocabulary here is the
product's -- prompt, schema, tier, cacheable prefix -- and never any
provider's parameter names.

If this port ever exposes OpenAI's parameter shapes, its tool-call JSON, or
its `logprobs`, then it is OpenAI wearing an interface and the second adapter
will not fit it. The contract is the INTERSECTION of what providers offer.

FOUR TIERS, NOT TWO
-------------------
Two tiers cannot express two rules the spec already commits to:

  * `judge` must resolve to a model DIFFERENT from the one under test. With
    only routine/hard, a judged run on a `hard` step would be graded by the
    model that wrote it -- the correlated-failure case tenet P4 exists to
    prevent.
  * `embed` has an entirely different lifecycle. Changing it invalidates every
    vector in the corpus, so it is read and verified, never chosen at run time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class Tier(str, Enum):
    """What a step declares instead of a model."""

    ROUTINE = "routine"
    HARD = "hard"
    JUDGE = "judge"
    EMBED = "embed"


# ---------------------------------------------------------------- errors ---
# Providers signal these differently. The port raises the same small set so the
# retry, degrade, and fail-the-need-not-the-turn policies in PRD §7.4.4 hold
# identically whichever adapter is live.


class ModelError(Exception):
    """Base for every failure the port normalises."""


class RateLimited(ModelError):
    """Transient. Bounded retry with backoff, and the retries are counted."""


class ProviderUnavailable(ModelError):
    """The provider could not be reached. Fail the NEED, never the turn."""


class ContextOverflow(ModelError):
    """The prompt exceeds the tier's declared budget.

    A typed error, NEVER a truncation. Silent truncation produces an answer
    that looks complete and was reasoned from a fraction of the material.
    """


class ContentRefused(ModelError):
    """The provider declined on content grounds.

    Surfaced as itself and never reported as a legal finding: a refusal about
    a violent assault is a provider behaviour, not a fact about the matter.
    """


class SchemaViolation(ModelError):
    """Structured output did not satisfy the schema after bounded retry.

    NEVER best-effort parsed. Lenient parsing is how an invented vocabulary
    once entered the system and emptied a charge map; an unrecognised value is
    treated as absent, never as valid.
    """


class TierUnavailable(ModelError):
    """The requested tier cannot be served and no downgrade was authorised."""


class ConfigurationError(ModelError):
    """The model configuration is refused at startup rather than used.

    Raised for an unpinned alias, an unlisted provider, or a `judge` tier that
    resolves to the model under test.
    """


# ------------------------------------------------------------- data types ---


@dataclass(frozen=True)
class Prompt:
    """A prompt in the product's vocabulary.

    `system` is the CACHEABLE PREFIX. An adapter that supports prompt caching
    uses it; one that does not no-ops and reports zero cache hits. The product
    must not behave differently, only cost differently -- which is why the
    prefix must stay stable across calls, and therefore why matter-specific
    content belongs in `user`, never in `system`.
    """

    user: str
    system: str | None = None

    def __post_init__(self) -> None:
        if not self.user or not self.user.strip():
            raise ValueError("Prompt.user must not be empty")


@dataclass(frozen=True)
class Usage:
    """Normalised accounting. PRD §7.4.2.

    One shape across every provider, or TurnMetrics becomes provider-shaped and
    the cost baseline stops comparing across a switch. Provider-native extras
    are carried opaquely for diagnostics and are never read by the core.
    """

    tokens_in: int
    tokens_out: int
    cost_usd: float
    cached_tokens: int = 0
    provider_extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResult:
    text: str | None
    data: dict[str, Any] | None
    tier: Tier
    provider: str
    model: str
    usage: Usage
    latency_ms: int
    retries: int = 0
    downgraded_from: Tier | None = None

    def __post_init__(self) -> None:
        if self.text is None and self.data is None:
            raise ValueError("ModelResult carries neither text nor data")

    @property
    def was_downgraded(self) -> bool:
        """A downgrade is NEVER silent -- it is recorded, surfaced, and where it
        touched a judgement-tier output, stated in the answer."""
        return self.downgraded_from is not None


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    provider: str
    usage: Usage


# ------------------------------------------------------------------ port ---


# ------------------------------------------------- the port's own validator ---


# WHY THIS IS IN THE PORT AND NOT IN AN ADAPTER
#
# It was in `scripted.py`, and only the scripted adapter called it. The
# OpenAI adapter parsed the JSON and returned it -- and the provider runs
# with `strict` off -- so on the path that actually ships, an `enum` in a
# schema was decoration. A role read declaring eleven permitted values
# came back "claimant" and reached the core.
#
# A guard that is right in the double and absent from the real adapter is
# not a guard, and E-005 could not see the difference because the contract
# suite never asserted that an out-of-enum value is refused.
#
# The port owns its contract. Every adapter calls this.
#: Keys THIS PRODUCT adds to a declared schema for its own use.
#:
#: They are ours, they are namespaced so they cannot be mistaken for JSON
#: Schema, and they are STRIPPED at the provider boundary by `on_the_wire`.
NM_SCHEMA_KEYS = ("x-nm-read",)


def on_the_wire(schema) -> dict:
    """The schema as the PROVIDER sees it. Our metadata removed.

    WHY THIS EXISTS, MEASURED ON 31 AUGUST 2026
    --------------------------------------------
    The scripted provider needs to know which read a schema is, so a key was
    added to each schema naming it. It was called `title`, which is ordinary
    JSON Schema, and the whole schema was passed to OpenAI verbatim.

    The live date read then stopped returning `events` — every call raised
    `SchemaViolation: required property 'events' is missing`. Because
    `SchemaViolation` is a `ModelError`, the engine caught it, fired G-MODEL
    `unavailable`, and returned no rows. NO DATED FACT WAS CREATED ON ANY LIVE
    TURN, and since that path fires a gate rather than recording a violation,
    nothing in the output said so. Limitation was NOT_COMPUTED on every served
    turn for want of an accrual date, which read as an ordinary silence.

    The entire offline suite was green throughout, because the scripted
    provider answers from the key and never validates the way the real one
    does. CLAUDE.md §8: a guard that is right in the core and wrong at the
    composition root is not a guard.

    So our metadata is namespaced `x-nm-*` — obviously not JSON Schema, and
    impossible to mistake for something the provider should see — and this is
    the one place it comes off. A future key is covered by adding it to
    `NM_SCHEMA_KEYS`, not by remembering to strip it at each adapter.
    """
    return {k: v for k, v in dict(schema).items() if k not in NM_SCHEMA_KEYS}


def require_schema(data: Any, schema: Mapping[str, Any]) -> None:
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


@runtime_checkable
class ModelPort(Protocol):
    """What the core declares. Adapters implement it; the core never imports one."""

    @property
    def provider(self) -> str:
        """The provider name this adapter serves, for TurnMetrics."""
        ...

    def resolved_model(self, tier: Tier) -> str:
        """The pinned, dated snapshot this tier resolves to.

        Never a floating alias: providers move aliases, and a moved metric must
        be distinguishable from a regression you caused.
        """
        ...

    def context_budget(self, tier: Tier) -> int:
        """Tokens a step may build to for this tier.

        The budget belongs to the PORT, not to the provider, and is chosen as
        what the smallest supported provider can hold. A prompt built to fill
        one provider's window does not port, and discovering that at switch
        time defeats the whole design.
        """
        ...

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        ...

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        """Structured output, abstracted HERE rather than at the call site.

        Providers differ on JSON mode, tool use, and schema enforcement. A call
        site that constructs a provider-specific tool definition has leaked the
        provider into the core.
        """
        ...

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        ...
