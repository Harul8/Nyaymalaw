"""Provider-neutral, durable work receipts; never an approval to release advice."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from nm.shared.budget_contracts import Budget


def digest(value: object) -> str:
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(wire.encode("utf8")).hexdigest()


class LoopMode(str, Enum):
    RECORDED = "recorded"
    SYNTHETIC = "synthetic"


class StepKind(str, Enum):
    START = "start"
    MODEL_STARTED = "model_started"
    MODEL_RETURNED = "model_returned"
    TOOL_STARTED = "tool_started"
    TOOL_RETURNED = "tool_returned"
    FAILURE = "failure"
    STOP = "stop"


class StopReason(str, Enum):
    PROPOSAL = "proposal_needs_checks"
    QUESTION = "question_needs_checks"
    CONVERSATION = "conversation_needs_checks"
    BUDGET = "budget"
    CANCELLED = "cancelled"
    NO_PROGRESS = "no_progress"
    PROVIDER = "provider_unavailable"
    INTERRUPTED = "interrupted_outcome_unknown"
    REFUSED = "boundary_refused"
    CONTEXT = "context_cannot_fit"


@dataclass(frozen=True)
class LoopIdentity:
    matter_id: str
    advocate_id: str
    turn_id: str
    offer_hash: str
    principles_version: str
    tools_version: str
    matter_version: int
    mode: LoopMode

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not v.strip() for v in (
                self.matter_id, self.advocate_id, self.turn_id)):
            raise ValueError("a loop records the matter, actor and turn identities")
        for value in (self.offer_hash, self.principles_version, self.tools_version):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("loop versions are exact SHA256 identities")
        if type(self.matter_version) is not int or self.matter_version < 1:
            raise ValueError("the checked file has a positive committed version")
        if not isinstance(self.mode, LoopMode):
            raise ValueError("foundation loops only accept recorded or synthetic mode")

    @property
    def fingerprint(self) -> str:
        return digest(self.as_dict())

    def as_dict(self) -> dict:
        return {"matter_id": self.matter_id, "advocate_id": self.advocate_id,
                "turn_id": self.turn_id, "offer_hash": self.offer_hash,
                "principles_version": self.principles_version,
                "tools_version": self.tools_version,
                "matter_version": self.matter_version, "mode": self.mode.value}


@dataclass(frozen=True)
class LoopEvent:
    sequence: int
    kind: StepKind
    at: str
    payload_json: str
    previous: str
    fingerprint: str

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("event sequence is a positive integer")
        if not isinstance(self.kind, StepKind):
            raise ValueError("unknown loop event kind")
        if datetime.fromisoformat(self.at).utcoffset() is None:
            raise ValueError("event time records its timezone")
        payload = json.loads(self.payload_json, parse_constant=_invalid_number)
        if not isinstance(payload, dict):
            raise ValueError("event payload is a closed JSON object")
        if self.fingerprint != digest(self.body()):
            raise ValueError("event contents differ from their recorded identity")

    def body(self) -> dict:
        return {"sequence": self.sequence, "kind": self.kind.value, "at": self.at,
                "payload": self.payload_json, "previous": self.previous}

    @classmethod
    def create(cls, sequence: int, kind: StepKind, at: str,
               payload: dict, previous: str) -> "LoopEvent":
        wire = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        body = {"sequence": sequence, "kind": kind.value, "at": at,
                "payload": wire, "previous": previous}
        return cls(sequence, kind, at, wire, previous, digest(body))

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)


def _invalid_number(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


@dataclass(frozen=True)
class LoopRecord:
    identity: LoopIdentity
    events: tuple[LoopEvent, ...] = ()
    __stored_fields_closed__ = True

    def __post_init__(self) -> None:
        previous = self.identity.fingerprint
        for index, event in enumerate(self.events, 1):
            if not isinstance(event, LoopEvent) or event.sequence != index:
                raise ValueError("the saved loop log is contiguous and typed")
            if event.previous != previous:
                raise ValueError("the saved loop log has a changed or omitted event")
            if index == 1 and event.kind is not StepKind.START:
                raise ValueError("the loop starts with a saved identity and budget")
            if index > 1 and self.events[index - 2].kind is StepKind.STOP:
                raise ValueError("nothing is appended after a terminal receipt")
            previous = event.fingerprint

    @property
    def terminal(self) -> bool:
        return bool(self.events and self.events[-1].kind is StepKind.STOP)


@dataclass(frozen=True)
class LoopLimits:
    budget: Budget
    max_steps: int
    per_call_tokens: int
    max_stagnant_steps: int = 2

    def __post_init__(self) -> None:
        values = (self.max_steps, self.per_call_tokens, self.max_stagnant_steps,
                  self.budget.max_ms, self.budget.max_tokens)
        if any(type(v) is not int or v <= 0 for v in values):
            raise ValueError("a loop requires positive step, token and time limits")
        if not math.isfinite(self.budget.max_cost_usd) or self.budget.max_cost_usd <= 0:
            raise ValueError("a loop requires a positive finite whole-task cost limit")


@dataclass(frozen=True)
class LoopOutcome:
    reason: StopReason
    record: LoopRecord
    budget: Budget
    proposal: dict = field(default_factory=dict)
    """Unreleased candidate, not an Answer and not an advocate-visible channel."""
