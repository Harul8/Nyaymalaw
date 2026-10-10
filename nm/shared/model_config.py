"""Tier -> provider + pinned model resolution, read from the environment.

Everything switchable lives in `.env`; NO OTHER FILE CHANGES when the provider
changes. This module is the only place that reads it.

Configuration is checked at startup:

  * a floating alias instead of a dated snapshot
  * a provider that is not on the permitted allow-list
  * a same-model review without an explicit deployment policy

Each is a ConfigurationError, not a warning. A warning here becomes a silently
mis-measured baseline, an unreviewed third party holding privileged client
material, or a judge grading its own homework.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from nm.shared.model_port import ConfigurationError, Tier, TierUnavailable

# Every model call sends privileged client material to a third party, so this
# is a confidentiality decision and not only a technical one (tenet 1).
PERMITTED_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "scripted"})

# Tokens a step may build to. Deliberately the smallest supported window, not
# the largest available: a prompt built to fill one provider's context does not
# port, and finding that out at switch time defeats the design.
CONTEXT_BUDGET: dict[Tier, int] = {
    Tier.ROUTINE: 100_000,
    Tier.HARD: 100_000,
    Tier.JUDGE: 100_000,
    Tier.EMBED: 8_000,
}

# USD per 1M tokens. Configuration, versioned with the pins, so a cost figure in
# the baseline is auditable rather than a number nobody can reconstruct.
PRICES: dict[str, tuple[float, float]] = {
    # Owner-directed deployment, 10 October 2026. Official model pages publish
    # these release IDs without dated snapshots. Standard processing prices.
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    # THE OWNER'S MODEL FROM 29 SEPTEMBER 2026 ("from here on use 4.1 mini only"),
    # checked that day against the official model page: $0.40 input, $0.10 cached
    # input, $1.60 output per million; 1M-token context, 32,768 output tokens.
    "gpt-4.1-mini-2025-04-14": (0.40, 1.60),
    "gpt-5.1": (1.25, 10.00),
    # Independent-verifier evaluation pin; checked against the official model
    # page on 27 September 2026. The ledger and provider receipt name this
    # exact snapshot, not a floating alias that might resolve differently.
    "gpt-5.1-2025-11-13": (1.25, 10.00),
    # Measured 5 September 2026 and CHEAPER THAN THE JUDGE, which is the whole
    # reason escalation became affordable: 0.875/7.00 against 5.1's 1.25/10.00.
    # Input has fallen 50% in ~90 days, so this is configuration and not a
    # constant -- a cost figure in the baseline is auditable only if the price
    # it was computed from is versioned beside it.
    "gpt-5.2": (0.875, 7.00),
    "text-embedding-3-large": (0.13, 0.0),
    "scripted": (0.0, 0.0),
}

#: The most output one call can return, per pinned model: with the context budget
#: above, what a spending reservation must cover so it can never under-count.
MAX_OUTPUT: dict[str, int] = {
    "gpt-6-luna": 128_000,
    "gpt-6.1-sol": 128_000,
    "gpt-4o-mini-2024-07-18": 16_384,
    "gpt-4.1-mini-2025-04-14": 32_768,
    "gpt-5.1": 128_000,
    "gpt-5.1-2025-11-13": 128_000,
}

# Official model pages checked 3 October 2026. Billing reservations use the
# provider's full context ceiling, including schema/framing, rather than the
# port's approximate prompt guard. No transcript estimate proves a dollar cap.
BILLING_CONTEXT: dict[str, int] = {
    "gpt-6-luna": 1_050_000,
    "gpt-6.1-sol": 1_050_000,
    "gpt-4o-mini-2024-07-18": 128_000,
    "gpt-4.1-mini-2025-04-14": 1_047_576,
    "gpt-5.1": 400_000,
    "gpt-5.1-2025-11-13": 400_000,
}

# A known alias may return only this checked snapshot. It does not permit
# changing the selected/billed model or trusting arbitrary provider aliases.
RETURNED_MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "gpt-5.1": ("gpt-5.1-2025-11-13",),
}

# Exact published release IDs, not permission to accept arbitrary family aliases.
PUBLISHED_RELEASES = frozenset({"gpt-6-luna", "gpt-6.1-sol"})


@dataclass(frozen=True)
class TokenPricing:
    """Captured billing terms; cached reads and writes partition input tokens."""

    input_rate: Decimal
    output_rate: Decimal
    cached_rate: Decimal | None = None
    write_rate: Decimal | None = None
    long_context_threshold: int | None = None
    input_multiplier: Decimal = Decimal(1)
    output_multiplier: Decimal = Decimal(1)

    def __post_init__(self):
        values = (self.input_rate, self.output_rate, self.cached_rate, self.write_rate,
                  self.input_multiplier, self.output_multiplier)
        if any(value is not None and (not isinstance(value, Decimal)
                or not value.is_finite() or value < 0) for value in values):
            raise ConfigurationError("Token prices must be finite nonnegative decimals")
        if (self.long_context_threshold is not None and
                (type(self.long_context_threshold) is not int or self.long_context_threshold <= 0)):
            raise ConfigurationError("Long-context pricing needs a positive token threshold")

    def as_dict(self):
        return {name: (str(value) if isinstance(value, Decimal) else value)
                for name, value in vars(self).items()}

    def _micro_cost(self, tokens_in, tokens_out, cached_tokens, cache_write_tokens):
        if any(type(value) is not int or value < 0 for value in
               (tokens_in, tokens_out, cached_tokens, cache_write_tokens)):
            raise ConfigurationError("Token usage must be nonnegative integers")
        if cached_tokens + cache_write_tokens > tokens_in:
            raise ConfigurationError("Cache read/write tokens exceed total input")
        if cache_write_tokens and self.write_rate is None:
            raise ConfigurationError("Cache writes require established pricing")
        long = self.long_context_threshold is not None and tokens_in > self.long_context_threshold
        ordinary = tokens_in - cached_tokens - cache_write_tokens
        incoming = (ordinary * self.input_rate
                    + cached_tokens * (self.cached_rate if self.cached_rate is not None else self.input_rate)
                    + cache_write_tokens * (self.write_rate or Decimal(0)))
        return (incoming * (self.input_multiplier if long else 1)
                + tokens_out * self.output_rate * (self.output_multiplier if long else 1))

    def cost_micro_usd(self, tokens_in, tokens_out, *, cached_tokens=0, cache_write_tokens=0):
        return int(self._micro_cost(tokens_in, tokens_out, cached_tokens, cache_write_tokens)
                   .to_integral_value(rounding=ROUND_CEILING))

    def cost_usd(self, tokens_in, tokens_out, *, cached_tokens=0, cache_write_tokens=0):
        return float(self._micro_cost(tokens_in, tokens_out, cached_tokens, cache_write_tokens)
                     / Decimal(1_000_000))

    def reserve_micro_usd(self, input_upper_bound, output_tokens):
        # Never assume a cache hit before the provider returns usage.
        writes = input_upper_bound if self.write_rate is not None and self.write_rate > self.input_rate else 0
        return self.cost_micro_usd(input_upper_bound, output_tokens, cache_write_tokens=writes)


def token_pricing(model: str) -> TokenPricing:
    if model not in PRICES:
        raise ConfigurationError("The selected model has no established token pricing")
    incoming, outgoing = (Decimal(str(value)) for value in PRICES[model])
    if model in PUBLISHED_RELEASES:
        cached, write = {"gpt-6-luna": ("0.01", "0.125"),
                         "gpt-6.1-sol": ("0.10", "2.50")}[model]
        return TokenPricing(incoming, outgoing, Decimal(cached), Decimal(write),
                            272_000, Decimal(2), Decimal("1.5"))
    return TokenPricing(incoming, outgoing)


def reservation_micro_usd(model: str, tier: Tier | None = None) -> int:
    """The worst charge one call on `model` can make, in micro-USD: a full context
    budget of input at its price plus its largest output at its price, rounded up
    (tokens times USD per million tokens is micro-USD). Refuses a model whose price or
    output ceiling is not recorded here."""
    if model not in PRICES or model not in MAX_OUTPUT:
        raise ConfigurationError(f"no recorded price and output ceiling for {model!r}")
    budget = CONTEXT_BUDGET[tier or Tier.ROUTINE]
    return token_pricing(model).reserve_micro_usd(budget, MAX_OUTPUT[model])


# A pin must name a version. These are the shapes a real dated snapshot takes;
# a bare family name is an alias and is refused.
_PINNED = re.compile(
    r"(-\d{4}-\d{2}-\d{2}$)|(-\d{4}$)|(^gpt-5\.\d+$)|(^scripted)"
    r"|(-3-large$)|(-3-small$)"
)

# Tiers that may legitimately be absent. `hard` is absent because escalation is
# earned by measurement and nothing has earned it yet; `judge` because class-D
# runs are deliberate and approved. Asking for an absent tier raises
# TierUnavailable with the reason -- never a silent fallback.
_OPTIONAL_TIERS = frozenset({Tier.HARD, Tier.JUDGE})

_ENV_TIER = {
    Tier.ROUTINE: "NM_MODEL_ROUTINE",
    Tier.HARD: "NM_MODEL_HARD",
    Tier.JUDGE: "NM_MODEL_JUDGE",
    Tier.EMBED: "NM_EMBED_MODEL",
}


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader. Existing environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


@dataclass(frozen=True)
class TierConfig:
    tier: Tier
    provider: str
    model: str
    api_key: str | None
    base_url: str | None

    @property
    def price_in(self) -> float:
        return PRICES.get(self.model, (0.0, 0.0))[0]

    @property
    def price_out(self) -> float:
        return PRICES.get(self.model, (0.0, 0.0))[1]

    def cost(self, tokens_in: int, tokens_out: int, *, cached_tokens=0, cache_write_tokens=0) -> float:
        return token_pricing(self.model).cost_usd(tokens_in, tokens_out,
            cached_tokens=cached_tokens, cache_write_tokens=cache_write_tokens)


def require_priced_snapshot(cfg: TierConfig, *, provider: str) -> TierConfig:
    """Unknown external pricing is unestablished cost, never a free request."""
    prices = PRICES.get(cfg.model)
    if cfg.provider != provider:
        raise ConfigurationError("The configured tier does not belong to this provider adapter")
    if (prices is None or len(prices) != 2 or any(
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in prices) or not any(prices)):
        raise ConfigurationError("The selected snapshot needs an explicit, finite versioned price")
    return cfg


@dataclass(frozen=True)
class ModelConfig:
    tiers: dict[Tier, TierConfig]

    def for_tier(self, tier: Tier) -> TierConfig:
        try:
            return self.tiers[tier]
        except KeyError:
            if tier is Tier.HARD:
                raise TierUnavailable(
                    "the hard tier is not configured. Nothing has yet earned "
                    "escalation: a step moves to `hard` only with a recorded "
                    "measurement showing the quality it bought (PRD §7.4.1). "
                    "Set NM_MODEL_HARD when a measurement justifies it."
                ) from None
            if tier is Tier.JUDGE:
                raise TierUnavailable(
                    "the judge tier is not configured. Class-D runs need "
                    "NM_MODEL_JUDGE set to a model DIFFERENT from the tier under "
                    "test -- a model that produced a straw-man opposing case will "
                    "judge that case strong (tenet P4)."
                ) from None
            raise ConfigurationError(f"tier {tier.value!r} is not configured") from None

    def configured(self, tier: Tier) -> bool:
        return tier in self.tiers

    def providers(self) -> set[str]:
        return {c.provider for c in self.tiers.values()}


def _require_pinned(tier: Tier, model: str) -> None:
    if model not in PUBLISHED_RELEASES and not _PINNED.search(model):
        raise ConfigurationError(
            f"{_ENV_TIER[tier]}={model!r} is a floating alias, not a pinned snapshot. "
            "Providers move aliases, which makes a moved metric indistinguishable "
            "from a regression you caused. Pin a dated version (PRD §7.4.3)."
        )


def _require_permitted(tier: Tier, provider: str) -> None:
    if provider not in PERMITTED_PROVIDERS:
        raise ConfigurationError(
            f"provider {provider!r} for tier {tier.value!r} is not on the permitted "
            f"allow-list {sorted(PERMITTED_PROVIDERS)}. Every model call sends "
            "privileged client material to a third party (PRD §7.4.5)."
        )


def load(env: dict[str, str] | None = None) -> ModelConfig:
    """Resolve every tier, or refuse."""
    e = dict(os.environ if env is None else env)
    default_provider = (e.get("NM_MODEL_PROVIDER") or "").strip().lower()
    if not default_provider:
        raise ConfigurationError("NM_MODEL_PROVIDER is not set")

    tiers: dict[Tier, TierConfig] = {}
    for tier, var in _ENV_TIER.items():
        model = (e.get(var) or "").strip()
        if not model:
            # THREE STATES, not two. `judge` is only needed for class-D runs, so
            # "not configured" is a legitimate state distinct from "configured
            # wrong" -- and asking for it later raises TierUnavailable with the
            # reason, rather than quietly falling back to the model under test.
            if tier in _OPTIONAL_TIERS:
                continue
            raise ConfigurationError(f"{var} is not set")
        _require_pinned(tier, model)

        provider = (e.get(f"NM_MODEL_PROVIDER_{tier.name}") or default_provider).strip().lower()
        _require_permitted(tier, provider)

        key = e.get(f"NM_MODEL_API_KEY_{tier.name}") or e.get("NM_MODEL_API_KEY") or None
        if key in ("", "sk-REPLACE-ME"):
            key = None
        base = e.get(f"NM_MODEL_BASE_URL_{tier.name}") or e.get("NM_MODEL_BASE_URL") or None

        tiers[tier] = TierConfig(tier=tier, provider=provider, model=model,
                                 api_key=key, base_url=base or None)

    same_model_review = e.get("NM_ALLOW_SAME_MODEL_REVIEW", "false").strip().lower()
    if same_model_review not in ("true", "false"):
        raise ConfigurationError("NM_ALLOW_SAME_MODEL_REVIEW must be true or false")
    if same_model_review != "true":
        _check_judge_distinct(tiers)
    return ModelConfig(tiers=tiers)


def _check_judge_distinct(tiers: dict[Tier, TierConfig]) -> None:
    """A judge must not grade its own homework.

    This is what makes tenet P4 enforceable instead of aspirational: the rule
    is stated in the spec, and without a mechanism it is only a hope.
    """
    judge = tiers.get(Tier.JUDGE)
    if judge is None:
        return
    clashes = [
        t.tier.value for t in tiers.values()
        if t.tier in (Tier.ROUTINE, Tier.HARD)
        and t.provider == judge.provider
        and t.model == judge.model
    ]
    if clashes:
        raise ConfigurationError(
            f"NM_MODEL_JUDGE resolves to {judge.provider}/{judge.model}, the same model "
            f"as tier(s) {', '.join(clashes)}. A model that produced a straw-man "
            "opposing case will judge that case strong -- same model, same blind "
            "spot, correlated failure (tenet P4). Point the judge elsewhere, e.g. "
            "NM_MODEL_PROVIDER_JUDGE."
        )
