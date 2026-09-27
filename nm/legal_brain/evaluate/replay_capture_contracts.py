"""Closed strict-replay inputs, not a certification of a historic model journal.

The runtime producer must seal these inputs with the owned matter journal. A
valid JSON shape is not evidence that an arbitrary caller observed the inputs.
No capture chooses an executable, import target, storage path or transport.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from nm.legal_brain.orchestrate.loop_contracts import LoopRecord, digest


class ReplayCaptureRefused(ValueError):
    """A required boundary was not captured or its closed contract differs."""


class ReplayProfile(str, Enum):
    FOUNDATION = "foundation-write-discovery-v1"
    CONTROLLED = "controlled-brain-v1"


class PortOperation(str, Enum):
    READ_PROVISION = "evidence.read_provision"
    FETCH = "evidence.fetch"


def closed(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ReplayCaptureRefused(f"{label}: incomplete or unknown fields")
    return value


def sha(value, label):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReplayCaptureRefused(f"{label}: an exact SHA256 identity is required")


def opaque(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ReplayCaptureRefused(f"{label}: a bounded owner token is required")
    if any(character in value for character in ("/", "\\", ":")):
        raise ReplayCaptureRefused(f"{label}: an owner token is not a path or endpoint")


def instant(value):
    if not isinstance(value, str):
        raise ReplayCaptureRefused("clock: a captured timezone-aware timestamp is required")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None or parsed.isoformat() != value:
        raise ReplayCaptureRefused("clock: a canonical timezone-aware timestamp is required")
    return parsed


def finite(value, label, *, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ReplayCaptureRefused(f"{label}: a finite captured amount is required")


@dataclass(frozen=True)
class ReplayReadiness:
    state: str
    missing: tuple[str, ...] = ()

    @property
    def ready(self):
        return self.state == "ready"


@dataclass(frozen=True)
class ReplayComparison:
    state: str
    capture_identity: str
    differences: tuple[str, ...]
    expected_population: tuple[str, ...] = ()
    actual_population: tuple[str, ...] = ()
    actual_final_identity: str = ""
    network_blocked: bool = False
    credentials_absent: bool = False
    released: bool = False


@dataclass(frozen=True)
class StrictReplayCapture:
    payload_json: str

    def __post_init__(self):
        # Direct dataclass construction is not a second permissive parser.
        self.from_dict(json.loads(self.payload_json))

    @classmethod
    def from_dict(cls, value):
        closed(
            value,
            {
                "schema",
                "profile",
                "initial_matter",
                "initial_matter_identity",
                "journal_refs",
                "target",
                "principles",
                "prompt",
                "limits",
                "run",
                "owner_versions",
                "manifest",
                "tapes",
                "port_exchanges",
                "final_matter_identity",
            },
            "strict capture",
        )
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ReplayCaptureRefused("strict capture: unsupported capture version")
        ReplayProfile(value["profile"])
        initial = value["initial_matter"]
        if not isinstance(initial, dict) or "loop_records" in initial:
            raise ReplayCaptureRefused("initial matter: journals must be flat sealed references")
        for name in ("initial_matter_identity", "final_matter_identity"):
            sha(value[name], name)
        if digest(initial) != value["initial_matter_identity"]:
            raise ReplayCaptureRefused("initial matter: captured source identity differs")
        refs = value["journal_refs"]
        if not isinstance(refs, list) or len(refs) > 10000:
            raise ReplayCaptureRefused("journal references: a bounded flat population is required")
        seen = set()
        for row in refs:
            closed(row, {"identity", "terminal_identity"}, "journal reference")
            sha(row["terminal_identity"], "journal terminal")
            ident = digest(row["identity"])
            if ident in seen:
                raise ReplayCaptureRefused("journal references: duplicate parent")
            seen.add(ident)
        closed(value["target"], {"identity", "events"}, "target journal")
        closed(value["principles"], {"text", "sha256"}, "principles")
        sha(value["principles"]["sha256"], "principles")
        closed(value["prompt"], {"user", "system", "operation"}, "prompt")
        closed(
            value["limits"],
            {"budget", "max_steps", "per_call_tokens", "max_stagnant_steps"},
            "limits",
        )
        closed(
            value["run"],
            {"tier", "context_record", "feedback_identity", "scope_identity"},
            "run inputs",
        )
        closed(value["owner_versions"], {"sources"}, "owner versions")
        opaque(value["owner_versions"]["sources"], "source generation")
        closed(
            value["manifest"],
            {"entries", "corpus_version", "reconciled_at"},
            "frozen manifest population",
        )
        tapes = closed(
            value["tapes"],
            {"clock", "monotonic", "forum_day", "cancelled", "cost", "boundaries"},
            "input tapes",
        )
        for name, rows in tapes.items():
            if not isinstance(rows, list) or len(rows) > 100000:
                raise ReplayCaptureRefused(f"{name}: a bounded ordered tape is required")
        for item in tapes["clock"]:
            instant(item)
        previous = -1.0
        for item in tapes["monotonic"]:
            finite(item, "monotonic")
            if item < previous:
                raise ReplayCaptureRefused("monotonic: captured time moved backwards")
            previous = item
        for item in tapes["forum_day"]:
            if not isinstance(item, str) or date.fromisoformat(item).isoformat() != item:
                raise ReplayCaptureRefused("forum day: a captured calendar day is required")
        if any(type(item) is not bool for item in tapes["cancelled"]):
            raise ReplayCaptureRefused("cancelled: captured cancellation states are required")
        for row in tapes["cost"]:
            closed(row, {"input_tokens", "output_tokens", "tier", "usd"}, "cost ceiling")
            if any(
                type(row[key]) is not int or row[key] < 0
                for key in ("input_tokens", "output_tokens")
            ):
                raise ReplayCaptureRefused("cost ceiling: exact token inputs are required")
            finite(row["usd"], "cost ceiling")
        for row in tapes["boundaries"]:
            closed(
                row,
                {
                    "phase",
                    "tool",
                    "matter_id",
                    "actor_id",
                    "current_version",
                    "session_current",
                    "scope_matter_ids",
                    "source_generation",
                    "source_state",
                    "claimed_capacity",
                    "policy_at",
                },
                "permission owner observation",
            )
            if row["phase"] not in ("before", "after"):
                raise ReplayCaptureRefused("permission owner: unknown phase")
            for name in ("tool", "matter_id", "actor_id"):
                opaque(row[name], "permission " + name)
            if row["source_state"] not in ("current", "changed", "unavailable"):
                raise ReplayCaptureRefused("permission owner: a typed generation state is required")
            if row["source_state"] == "unavailable":
                if row["source_generation"] is not None:
                    raise ReplayCaptureRefused("unavailable generation cannot invent an identity")
            else:
                opaque(row["source_generation"], "permission source generation")
            if type(row["current_version"]) is not int or row["current_version"] < 1:
                raise ReplayCaptureRefused("permission owner: exact file version is required")
            if type(row["session_current"]) is not bool:
                raise ReplayCaptureRefused("permission owner: session observation is required")
            population = row["scope_matter_ids"]
            if (
                not isinstance(population, list)
                or not population
                or len(set(population)) != len(population)
            ):
                raise ReplayCaptureRefused("permission owner: finite matter scope is required")
            for item in population:
                opaque(item, "scope matter")
            if row["claimed_capacity"] not in (None, "assisting"):
                raise ReplayCaptureRefused("permission owner: only a narrowing claim is supported")
            instant(row["policy_at"])
        exchanges = value["port_exchanges"]
        if not isinstance(exchanges, list) or len(exchanges) > 10000:
            raise ReplayCaptureRefused("ports: a bounded finite-operation tape is required")
        for row in exchanges:
            closed(row, {"operation", "arguments", "result", "source_generation"}, "port exchange")
            PortOperation(row["operation"])
            opaque(row["source_generation"], "port source generation")
            if not isinstance(row["arguments"], dict) or not isinstance(row["result"], dict):
                raise ReplayCaptureRefused(
                    "ports: typed arguments and typed owner results are required"
                )
        wire = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if len(wire.encode("utf8")) > 16_000_000:
            raise ReplayCaptureRefused("strict capture exceeds its bounded private size")
        instance = object.__new__(cls)
        object.__setattr__(instance, "payload_json", wire)
        return instance

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def identity(self):
        return digest(self.payload)


def inspect_capture(value):
    if isinstance(value, LoopRecord):
        return ReplayReadiness(
            "capture_incomplete",
            (
                "initial_checked_matter_and_flat_prior_journals",
                "clock_and_monotonic_tapes",
                "forum_day_and_cancellation_tapes",
                "cost_ceiling_tape",
                "permission_owner_observations",
                "typed_port_operation_tapes",
            ),
        )
    if not isinstance(value, StrictReplayCapture):
        return ReplayReadiness("capture_incomplete", ("strict_capture_v1",))
    value.__post_init__()
    data = value.payload
    missing = []
    if data["profile"] != ReplayProfile.FOUNDATION.value:
        missing.append("controlled_composition_profile_not_populated")
    if data["run"]["context_record"]:
        missing.append("context_source_owner_injection_not_populated")
    for name in ("clock", "monotonic", "cancelled"):
        if not data["tapes"][name]:
            missing.append(name + "_tape")
    if any(
        (payload := json.loads(event["payload_json"])).get("delegation")
        or "child_steps" in payload
        or "child_transcript" in payload
        for event in data["target"]["events"]
    ):
        missing.append("delegated_child_capture_and_injection")
    return ReplayReadiness("capture_incomplete" if missing else "ready", tuple(missing))
