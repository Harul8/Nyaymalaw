"""TurnMetrics, and the invariant violations recorded on every turn.

TWO RULES THIS FILE ENFORCES
----------------------------
1. Metrics are written even when the turn FAILS. Otherwise the most
   diagnostically valuable turns -- the ones that crashed -- are the only ones
   with no record.
2. Violations land in a STORE, not a log line. A test whose failures are not
   collected is not a test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    ADMIT = "admit"
    DERIVE = "derive"
    EMIT = "emit"


class Outcome(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"          # a gate refused; the block IS the answer
    GATED = "gated"              # a grounding violation withheld the output
    FAILED = "failed"


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    gating: bool = False


@dataclass
class TurnMetrics:
    turn_id: str
    matter_id: str | None = None
    outcome: Outcome = Outcome.FAILED
    failed_phase: Phase | None = None
    failure: str | None = None
    latency_ms: int = 0
    llm_calls: int = 0
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    model_mix: dict[str, int] = field(default_factory=dict)
    tier_downgrades: list[dict[str, str]] = field(default_factory=list)
    stages: dict[str, int] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)
    evidence_rounds: int = 0
    evidence_bound_hit: bool = False

    def record_call(self, result) -> None:
        """Every model call counts -- including a streamed one.

        A streamed turn once recorded `llm_calls: 0`, which made an entire turn
        invisible to the cost baseline.
        """
        self.llm_calls += 1
        self.retries += getattr(result, "retries", 0)
        self.tokens_in += result.usage.tokens_in
        self.tokens_out += result.usage.tokens_out
        self.cached_tokens += result.usage.cached_tokens
        self.cost_usd += result.usage.cost_usd
        key = f"{result.provider}/{result.model}"
        self.model_mix[key] = self.model_mix.get(key, 0) + 1
        if result.downgraded_from is not None:
            # A downgrade is NEVER silent.
            self.tier_downgrades.append(
                {"from": result.downgraded_from.value, "to": result.tier.value,
                 "model": key})

    def violate(self, rule: str, detail: str, *, gating: bool = False) -> None:
        self.violations.append(Violation(rule=rule, detail=detail, gating=gating))

    @property
    def gating_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.gating]

    def as_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "matter_id": self.matter_id,
            "outcome": self.outcome.value,
            "failed_phase": self.failed_phase.value if self.failed_phase else None,
            "failure": self.failure,
            "latency_ms": self.latency_ms,
            "llm_calls": self.llm_calls,
            "retries": self.retries,
            "tokens": {"in": self.tokens_in, "out": self.tokens_out,
                       "cached": self.cached_tokens},
            "cost_usd": round(self.cost_usd, 6),
            "model_mix": dict(self.model_mix),
            "tier_downgrades": list(self.tier_downgrades),
            "stages": dict(self.stages),
            "evidence_rounds": self.evidence_rounds,
            "evidence_bound_hit": self.evidence_bound_hit,
            "violations": [
                {"rule": v.rule, "detail": v.detail, "gating": v.gating}
                for v in self.violations
            ],
        }
