"""Tier -> provider + pinned model resolution, read from the environment.

Everything switchable lives in `.env`; NO OTHER FILE CHANGES when the provider
changes. This module is the only place that reads it.

Three things are refused at STARTUP rather than used (PRD §7.4.3, §7.4.5):

  * a floating alias instead of a dated snapshot
  * a provider that is not on the permitted allow-list
  * a `judge` tier resolving to the same model as the tier it would judge

Each is a ConfigurationError, not a warning. A warning here becomes a silently
mis-measured baseline, an unreviewed third party holding privileged client
material, or a judge grading its own homework.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from nm.ports.model import ConfigurationError, Tier, TierUnavailable

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
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-5.1": (1.25, 10.00),
    "text-embedding-3-large": (0.13, 0.0),
    "scripted": (0.0, 0.0),
}

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

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.price_in + tokens_out * self.price_out) / 1_000_000


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
    if not _PINNED.search(model):
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
