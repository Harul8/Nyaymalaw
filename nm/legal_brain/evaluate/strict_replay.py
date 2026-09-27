"""Execute a bounded actual tool population in an owned isolated worker.

This does not replay ToolEnvelopes or permission answers. The real registry,
file handlers and pure authority policy run against a newly encrypted clone.
Only the worker process installs transport/spawn refusal; the server and parent
process retain their ordinary environment. The current production composition
and delegated/context owners deliberately remain unsupported until captured.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from nm.legal_brain.common.principles_port import PrinciplesSnapshot
from nm.legal_brain.evaluate.replay_capture_contracts import (
    PortOperation,
    ReplayCaptureRefused,
    ReplayComparison,
    StrictReplayCapture,
    closed,
    inspect_capture,
    instant,
)
from nm.legal_brain.orchestrate.loop import LoopRunner
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopRecord, StepKind, digest
from nm.legal_brain.orchestrate.tool_discovery import discovery_tools
from nm.legal_brain.orchestrate.tools import Boundary, ToolRefused, foundation_tools
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceNeed, EvidenceResult, Finding
from nm.legal_brain.retrieve.manifest_sources import Manifest
from nm.open_matter.commission_contracts import Commission
from nm.shared.authority_contracts import Act, capacity_for, permits
from nm.shared.budget_contracts import Budget, Spend
from nm.shared.model_port import Prompt, Tier
from nm.shared.model_replay import ReplayModel
from nm.shared.store_file_store import FileMatterStore, _decode, _enc, _matter
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.write_tools import write_tools


class Tape:
    """Consume each actual owner invocation exactly once, never a default input."""

    def __init__(self, name, rows):
        self.name, self.rows, self.position = name, rows, 0

    def take(self):
        if self.position >= len(self.rows):
            raise ReplayCaptureRefused(self.name + ": capture exhausted at actual invocation")
        value = self.rows[self.position]
        self.position += 1
        return value

    def remaining(self):
        return len(self.rows) - self.position


def _evidence_result(raw):
    closed(
        raw,
        {"coverage", "findings", "missing", "searched_stores", "assumption", "search_note"},
        "captured EvidenceResult",
    )
    data = dict(raw)
    data["coverage"] = Coverage(data["coverage"])
    if not isinstance(data["findings"], list) or not isinstance(data["searched_stores"], list):
        raise ReplayCaptureRefused("captured evidence: typed finite lists are required")
    for name in ("missing", "assumption", "search_note"):
        if data[name] is not None and not isinstance(data[name], str):
            raise ReplayCaptureRefused("captured evidence: missing and limits remain text or null")
    if any(not isinstance(item, str) or not item.strip() for item in data["searched_stores"]):
        raise ReplayCaptureRefused("captured evidence: searched owners must be explicit")
    data["findings"] = tuple(Finding.from_record(item) for item in data["findings"])
    data["searched_stores"] = tuple(data["searched_stores"])
    return EvidenceResult(**data)


def validate_port_exchange(row):
    """A finite port operation accepts owner values, never a saved tool answer."""
    operation = PortOperation(row["operation"])
    arguments = row["arguments"]
    if operation is PortOperation.READ_PROVISION:
        closed(arguments, {"act", "section", "as_of"}, "read provision port arguments")
        if any(
            not isinstance(arguments[key], str) or not arguments[key].strip()
            for key in ("act", "section")
        ):
            raise ReplayCaptureRefused("read provision: exact instrument and section are required")
        if date.fromisoformat(arguments["as_of"]).isoformat() != arguments["as_of"]:
            raise ReplayCaptureRefused("read provision: exact governing date is required")
    else:
        names = set(EvidenceNeed.__dataclass_fields__)
        closed(arguments, names, "fetch port arguments")
        if type(arguments["want_authority"]) is not bool:
            raise ReplayCaptureRefused("fetch: authority intent is an actual Boolean")
        if not isinstance(arguments["parties"], list) or any(
            not isinstance(item, str) for item in arguments["parties"]
        ):
            raise ReplayCaptureRefused("fetch: parties are finite text match keys")
        for name in ("question", "jurisdiction", "account"):
            if not isinstance(arguments[name], str):
                raise ReplayCaptureRefused("fetch: actual query inputs are text")
        for name in ("forum", "cause_of_action", "provision_hint"):
            if arguments[name] is not None and not isinstance(arguments[name], str):
                raise ReplayCaptureRefused("fetch: absent optional query inputs stay null")
        _decode(EvidenceNeed, arguments)
    return _evidence_result(row["result"])


class FrozenEvidence:
    def __init__(self, tape, generation):
        self.tape, self.generation = tape, generation
        self.attempts = []

    def _read(self, operation, arguments):
        self.attempts.append(digest({"operation": operation, "arguments": arguments}))
        row = self.tape.take()
        if (
            row["operation"] != operation
            or row["arguments"] != arguments
            or row["source_generation"] != self.generation
        ):
            raise ReplayCaptureRefused("typed port invocation/generation differs from capture")
        return validate_port_exchange(row)

    def read_provision(self, act, section, as_of):
        return self._read(
            PortOperation.READ_PROVISION.value,
            {"act": act, "section": section, "as_of": as_of.isoformat()},
        )

    def fetch(self, need):
        if not isinstance(need, EvidenceNeed):
            raise ReplayCaptureRefused("fetch: an actual typed EvidenceNeed is required")
        return self._read(PortOperation.FETCH.value, _enc(need))


class FrozenPrinciples:
    def __init__(self, raw):
        self.snapshot = PrinciplesSnapshot(**raw)

    def load(self):
        return self.snapshot


class FrozenModel:
    """Exact model-call replay, with stable admitted identity after exhaustion."""

    def __init__(self, record, definitions):
        self.adapter = ReplayModel.from_loop(record, definitions)
        self.identity = record.events[0].payload["model_identity"]

    @property
    def provider(self):
        return self.identity["provider"]

    def resolved_model(self, tier):
        if tier.value != self.identity["tier"]:
            raise ReplayCaptureRefused("model tier differs from its captured admission")
        return self.identity["model"]

    def tool_call(self, *args, **kwargs):
        return self.adapter.tool_call(*args, **kwargs)


class PermissionTape:
    """Reconstruct authority from the actual clone and observed owner inputs."""

    def __init__(self, tape, store, generation):
        self.tape, self.store, self.generation = tape, store, generation
        self.registry = None
        self.attempts = []

    def check(self, phase, name, context):
        row = self.tape.take()
        actual = {
            "phase": phase,
            "tool": name,
            "matter_id": context.identity.matter_id,
            "actor_id": context.identity.advocate_id,
            "current_version": context.current_version,
        }
        self.attempts.append(digest(actual))
        if any(row[key] != value for key, value in actual.items()):
            raise ReplayCaptureRefused("permission owner invocation differs from capture")
        if row["source_state"] != "current" or row["source_generation"] != self.generation:
            return Boundary(False, "The admitted legal sources or practice tables changed.")
        if not row["session_current"] or actual["matter_id"] not in row["scope_matter_ids"]:
            return Boundary(False, "The session or controlled matter scope no longer permits work.")
        matter = self.store.load(actual["matter_id"])
        if (
            matter is None
            or matter.advocate_id != actual["actor_id"]
            or matter.version != context.current_version
        ):
            return Boundary(False, "The complete checked file is not available at this version.")
        act = self.registry.authority_for(name)
        if act is Act.ACT_EXTERNALLY:
            return Boundary(False, "External action is disabled in an isolated replay.")
        commission = Commission.from_stored(matter.commission)
        acting_as = capacity_for(
            actual["actor_id"],
            matter.authority_bindings,
            commission.version if commission else 0,
            instant(row["policy_at"]),
            claimed=row["claimed_capacity"],
        )
        ruling = permits(actual["actor_id"], acting_as, act)
        return Boundary(ruling.authorises(), ruling.why)

    def before(self, name, _arguments, context):
        return self.check("before", name, context)

    def after(self, envelope, context):
        return self.check("after", envelope.tool, context)


def build_registry(store, *, permission, evidence, manifest, generation, principles, today):
    """Fixed owned profile; no capture-selected callbacks or importable factories."""
    registry = foundation_tools(
        store,
        evidence,
        manifest=manifest,
        source_version=generation,
        before=permission.before,
        after=permission.after,
    )
    registry = registry.extend(write_tools(store, today=today))
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    permission.registry = registry
    return registry


def _prior_records(capture, records):
    target = _decode(LoopRecord, capture["target"])
    by_identity = {}
    for record in records:
        if not isinstance(record, LoopRecord) or not record.terminal:
            raise ReplayCaptureRefused("prior journal: a complete sealed owned record is required")
        record.__post_init__()
        for event in record.events:
            event.__post_init__()
        key = record.identity.fingerprint
        if key in by_identity:
            raise ReplayCaptureRefused("prior journal: duplicate sealed parent")
        if (
            record.identity.matter_id != target.identity.matter_id
            or record.identity.advocate_id != target.identity.advocate_id
            or record.identity.mode != target.identity.mode
            or record.identity.turn_id == target.identity.turn_id
            or record.identity.matter_version + len(record.events)
            > capture["initial_matter"]["version"]
        ):
            raise ReplayCaptureRefused("prior journal: foreign, target or post-admission parent")
        by_identity[key] = record
    wanted = []
    for ref in capture["journal_refs"]:
        record = by_identity.pop(digest(ref["identity"]), None)
        if (
            record is None
            or record.identity.as_dict() != ref["identity"]
            or record.events[-1].fingerprint != ref["terminal_identity"]
        ):
            raise ReplayCaptureRefused("prior journal: exact referenced sealed parent unavailable")
        wanted.append(record)
    if by_identity:
        raise ReplayCaptureRefused("prior journal: unreferenced population was supplied")
    return target, tuple(wanted)


def _population(record):
    return tuple(
        digest({"kind": event.kind.value, "payload": event.payload})
        for event in record.events
        if event.kind
        in (StepKind.TOOL_STARTED, StepKind.TOOL_RETURNED, StepKind.FAILURE, StepKind.STOP)
    )


def execute_owned(capture, *, prior_journals, store):
    """Trusted worker helper. Public callers use run_isolated, not this seam."""
    data = capture.payload
    readiness = inspect_capture(capture)
    if not readiness.ready:
        return ReplayComparison(readiness.state, capture.identity, readiness.missing)
    target, prior = _prior_records(data, prior_journals)
    if _enc(target) != data["target"]:
        raise ReplayCaptureRefused("target journal contains unowned or noncanonical fields")
    if not target.terminal:
        raise ReplayCaptureRefused(
            "target journal: incomplete historical dispatch is not replayable"
        )
    initial = _matter(data["initial_matter"])
    canonical_source = _enc(initial)
    canonical_source.pop("loop_records")
    if canonical_source != data["initial_matter"]:
        raise ReplayCaptureRefused("initial checked source contains unowned or noncanonical fields")
    if (
        initial.id != target.identity.matter_id
        or initial.advocate_id != target.identity.advocate_id
        or initial.version != target.identity.matter_version
    ):
        raise ReplayCaptureRefused("initial checked source does not bind the target admission")
    if store.load(initial.id) is not None:
        raise ReplayCaptureRefused("isolated store must be newly empty, not an existing checkout")
    initial = replace(initial, loop_records=prior)
    store.commit(initial, expected_version=0)
    tapes = {name: Tape(name, rows) for name, rows in data["tapes"].items()}
    ports = Tape("typed ports", data["port_exchanges"])
    for row in data["port_exchanges"]:
        validate_port_exchange(row)
    generation = data["owner_versions"]["sources"]
    evidence = FrozenEvidence(ports, generation)
    permission = PermissionTape(tapes["boundaries"], store, generation)
    principles = FrozenPrinciples(data["principles"])
    if principles.snapshot.version != target.identity.principles_version:
        raise ReplayCaptureRefused("principles differ from the admitted owner version")
    manifest = _decode(Manifest, data["manifest"])
    registry = build_registry(
        store,
        permission=permission,
        evidence=evidence,
        manifest=manifest,
        generation=generation,
        principles=principles,
        today=lambda: date.fromisoformat(tapes["forum_day"].take()),
    )
    if registry.version != target.identity.tools_version:
        raise ReplayCaptureRefused("actual registered population/version differs from capture")
    model = FrozenModel(target, registry.definitions)
    raw_limits = data["limits"]
    raw_budget = dict(raw_limits["budget"])
    raw_budget["spend"] = Spend(**raw_budget["spend"])
    limits = LoopLimits(
        Budget(**raw_budget),
        raw_limits["max_steps"],
        raw_limits["per_call_tokens"],
        raw_limits["max_stagnant_steps"],
    )

    def cost_ceiling(input_tokens, output_tokens, tier):
        row = tapes["cost"].take()
        if (row["input_tokens"], row["output_tokens"], row["tier"]) != (
            input_tokens,
            output_tokens,
            tier.value,
        ):
            raise ReplayCaptureRefused("cost ceiling: actual priced inputs differ")
        return row["usd"]

    log = MatterLoopLog(store, advocate_id=initial.advocate_id)
    runner = LoopRunner(
        model=model,
        tools=registry,
        log=log,
        cost_ceiling=cost_ceiling,
        monotonic=tapes["monotonic"].take,
        clock=lambda: instant(tapes["clock"].take()),
        current_matter=store.load,
    )
    failure = ""
    try:
        runner.run(
            target.identity,
            Prompt(**data["prompt"]),
            limits,
            tier=Tier(data["run"]["tier"]),
            cancelled=tapes["cancelled"].take,
            context_record=data["run"]["context_record"],
            feedback_identity=data["run"]["feedback_identity"],
            scope_identity=data["run"]["scope_identity"],
        )
    except (ReplayCaptureRefused, ToolRefused, ValueError, PermissionError) as exc:
        failure = type(exc).__name__ + ": " + str(exc)
    actual = log.read(target.identity)
    current = store.load(initial.id)
    source = _enc(current)
    source.pop("loop_records")
    final_identity = digest(source)
    expected_population, actual_population = (
        _population(target),
        _population(actual) if actual else (),
    )
    differences = []
    if failure:
        differences.append(failure)
    if actual != target:
        differences.append("actual_attempts_results_or_event_chain_differ")
    if expected_population != actual_population:
        differences.append("actual_tool_mutation_population_differ")
    if final_identity != data["final_matter_identity"]:
        differences.append("actual_final_checked_matter_differs")
    for name, tape in (*tapes.items(), ("typed_ports", ports)):
        if tape.remaining():
            differences.append(name + ": unconsumed captured inputs")
    if model.adapter.position != len(model.adapter.records):
        differences.append("unconsumed captured model calls")
    return ReplayComparison(
        "diverged" if differences else "matched",
        capture.identity,
        tuple(differences),
        expected_population,
        actual_population,
        final_identity,
    )


def _no_transport(event, _arguments):
    if event.startswith("socket.") or event in (
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
    ):
        raise PermissionError(
            "Strict replay worker disables network transport and child processes."
        )


def _install_worker_boundary():
    # A worker is one-shot. This permanent hook never runs in the live process.
    os.environ.clear()
    sys.addaudithook(_no_transport)
    import socket

    try:
        socket.socket()
    except PermissionError:
        return True
    raise ReplayCaptureRefused("worker transport refusal could not be established")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReplayCaptureRefused("duplicate JSON field in strict capture")
        result[key] = value
    return result


def _worker():
    network_blocked = _install_worker_boundary()
    packet = json.loads(sys.stdin.read(20_000_001), object_pairs_hook=_unique_object)
    closed(packet, {"capture", "prior_journals"}, "worker packet")
    capture = StrictReplayCapture.from_dict(packet["capture"])
    prior = tuple(_decode(LoopRecord, row) for row in packet["prior_journals"])
    try:
        with tempfile.TemporaryDirectory(prefix="nm-strict-replay-") as directory:
            store = FileMatterStore(Path(directory), key=secrets.token_hex(32))
            result = execute_owned(capture, prior_journals=prior, store=store)
    except (ReplayCaptureRefused, TypeError, ValueError, PermissionError) as exc:
        result = ReplayComparison(
            "refused", capture.identity, (type(exc).__name__ + ": " + str(exc),)
        )
    result = replace(result, network_blocked=network_blocked, credentials_absent=not os.environ)
    sys.stdout.write(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False))


def run_isolated(capture, *, prior_journals=()):
    readiness = inspect_capture(capture)
    if not readiness.ready:
        return ReplayComparison(
            readiness.state,
            capture.identity if isinstance(capture, StrictReplayCapture) else "",
            readiness.missing,
        )
    # No user-derived command, factory, environment, executable or path.
    packet = json.dumps(
        {"capture": capture.payload, "prior_journals": [_enc(row) for row in prior_journals]},
        allow_nan=False,
    )
    command = [sys.executable, "-I", str(Path(__file__).resolve())]
    environment = {
        name: os.environ[name]
        for name in ("SystemRoot", "WINDIR", "TEMP", "TMP")
        if name in os.environ
    }
    completed = subprocess.run(
        command,
        input=packet,
        text=True,
        encoding="utf8",
        capture_output=True,
        timeout=30,
        check=False,
        env=environment,
    )
    if completed.returncode or len(completed.stdout) > 2_000_000:
        return ReplayComparison("refused", capture.identity, ("isolated_worker_failed",))
    try:
        raw = json.loads(completed.stdout, object_pairs_hook=_unique_object)
        result = ReplayComparison(
            **{
                **raw,
                "differences": tuple(raw["differences"]),
                "expected_population": tuple(raw["expected_population"]),
                "actual_population": tuple(raw["actual_population"]),
            }
        )
        if (
            result.capture_identity != capture.identity
            or not result.network_blocked
            or not result.credentials_absent
            or result.released
        ):
            raise ReplayCaptureRefused("isolated worker boundary/result could not be established")
        return result
    except (TypeError, ValueError, KeyError) as exc:
        return ReplayComparison(
            "refused", capture.identity, ("isolated_worker_result_invalid", type(exc).__name__)
        )


if __name__ == "__main__":
    _worker()
