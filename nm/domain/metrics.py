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

from nm.domain.gates import Response, gate
from nm.domain.text import refuses_blank_text


class Phase(str, Enum):
    ADMIT = "admit"
    DERIVE = "derive"
    EMIT = "emit"


class Outcome(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"          # a gate refused; the block IS the answer
    GATED = "gated"              # a grounding violation withheld the output
    FAILED = "failed"


@refuses_blank_text("detail")
@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    gating: bool = False


@refuses_blank_text("detail")
@dataclass(frozen=True)
class GateFiring:
    """A gate that fired on this turn, and what the MATRIX said to do about it.

    The response is looked up, never passed in. That is the whole reason the
    matrix exists: before it, each call site decided for itself whether its
    condition blocked, withheld or was merely logged, and the specification
    ended up claiming the product failed closed on one thing while nine others
    quietly blocked.
    """

    gate_id: str
    state: str
    detail: str
    response: str


@refuses_blank_text()
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
    gates_fired: list[GateFiring] = field(default_factory=list)
    grounding: dict = field(default_factory=dict)
    evidence_rounds: int = 0
    evidence_bound_hit: bool = False
    posture_reads: int = 0
    """Model calls spent READING what the advocate stated, not deriving.

    Reading the posture is what settles the gate; derivation is what the gate
    exists to prevent. Counting them together makes "nothing was computed
    behind a closed gate" uncheckable -- a blocked turn legitimately spends one
    cheap extraction call and must spend nothing else."""
    binding_reads: int = 0
    """Model calls spent deciding WHICH THREAD an account belongs to.

    The same category as `posture_reads` and counted separately from it only so
    each gate's spend is attributable. A turn blocked by G-THREAD has legitimately
    paid for the read that discovered the ambiguity -- that read is what settles
    the gate, and refusing to spend it would mean never discovering the second
    dispute at all."""

    chronology_reads: int = 0
    """Model calls spent building the DATE CHART.

    An ADMIT-phase read like the other two, and counted apart only so each
    one's spend is attributable. C5 requires the chart before any opinion on
    the thread, so it runs before a gate has decided anything -- and a DATE IS
    NOT SIDE-DEPENDENT: the 15th of April is the 15th of April whichever party
    you act for, which is the test E-034 actually applies."""

    @property
    def settling_reads(self) -> int:
        """Calls made in ADMIT -- establishing the FILE, not deriving an answer.

        The property every "nothing was computed behind a closed gate" check
        subtracts. Asserting a flat `llm_calls == 0` conflates the two and has
        to be relaxed -- rather than tightened -- the moment another read is
        needed before a gate can decide, which has now happened three times:
        the posture, the thread binding, and the date chart.

        What belongs here is precisely what is NOT side-dependent. A
        recommendation is; an authority set is; a date is not."""
        return self.posture_reads + self.binding_reads + self.chronology_reads

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

    def fire(self, gate_id: str, state: str, detail: str) -> Response:
        """Record a gate firing and return what the matrix says to do.

        The caller does NOT decide. It reports the condition and obeys the
        response, so changing whether something blocks or withholds is a change
        to one table rather than a hunt through the code for the call site that
        got it wrong.
        """
        g = gate(gate_id)
        if state not in g.states:
            raise ValueError(
                f"{gate_id} has no state {state!r}; its vocabulary is "
                f"{list(g.states)}. An out-of-vocabulary state is blanked, not "
                f"accepted (PRD D9).")
        self.gates_fired.append(
            GateFiring(gate_id=gate_id, state=state, detail=detail,
                       response=g.response.value))
        if g.response is Response.WITHHOLD:
            self.violate(gate_id, detail, gating=True)
        return g.response

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
            "posture_reads": self.posture_reads,
            "binding_reads": self.binding_reads,
            "chronology_reads": self.chronology_reads,
            "evidence_bound_hit": self.evidence_bound_hit,
            "gates_fired": [
                {"gate": g.gate_id, "state": g.state, "response": g.response,
                 "detail": g.detail}
                for g in self.gates_fired
            ],
            "grounding": dict(self.grounding),
            "violations": [
                {"rule": v.rule, "detail": v.detail, "gating": v.gating}
                for v in self.violations
            ],
        }
