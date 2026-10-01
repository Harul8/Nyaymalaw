"""Trusted runtime observations, stored only in the existing protected journal.

This is a capture producer, not another brain, release gate or review child.
The fixed foundation port population can be replayed; production context,
specialist and full-port injection deliberately remain unpopulated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime

from nm.Archives.legal_brain.common.principles_port import PrinciplesSnapshot
from nm.Archives.legal_brain.evaluate.replay_capture_contracts import (
    PortOperation,
    ReplayCaptureRefused,
    ReplayProfile,
    StrictReplayCapture,
    closed,
    inspect_capture,
    instant,
)
from nm.Archives.legal_brain.evaluate.runtime_port_tape import (
    CONTRACTS,
    NativePortRecorder,
    validate_exchange,
)
from nm.Archives.legal_brain.evaluate.strict_replay import PermissionTape, Tape, validate_port_exchange
from nm.Archives.legal_brain.orchestrate.controlled_brain import EvaluationScope
from nm.Archives.legal_brain.orchestrate.controlled_generations import GenerationGuard
from nm.Archives.legal_brain.orchestrate.controlled_registry_composition import ControlledRegistryPorts
from nm.Archives.legal_brain.orchestrate.generations_port import GenerationUnavailable
from nm.Archives.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopLimits,
    LoopOutcome,
    LoopRecord,
    StepKind,
    digest,
)
from nm.Archives.legal_brain.orchestrate.tool_catalogue import PracticeTables
from nm.Archives.legal_brain.retrieve.evidence_port import EvidenceNeed, EvidenceResult
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest
from nm.Archives.legal_brain.understand.brain_context import ContextPolicy, ContextSession
from nm.shared.model_port import Prompt, Tier
from nm.shared.store_file_store import FileMatterStore, _enc
from nm.shared.store_loop_log import MatterLoopLog

PURPOSE = "strict_runtime_capture_v1"
SUFFIX = ":capture:" + PURPOSE
LIMITATIONS = (
    "controlled_composition_and_full_port_injection_not_populated",
    "context_source_owner_injection_not_populated",
    "nested_child_and_independent_review_capture_not_populated",
    "fresh_world_and_engine_comparison_not_populated",
)


def is_capture_record(record):
    """A receipt purpose, never a turn-name alias for a lead/review operation."""
    return bool(record.events and record.events[0].payload.get("purpose") == PURPOSE)


def _source(matter):
    value = _enc(matter)
    value.pop("loop_records")
    return value


@dataclass(frozen=True)
class SavedRuntimeCapture:
    capture: StrictReplayCapture
    journal: LoopRecord
    prior_journals: tuple
    metadata: dict

    @property
    def readiness(self):
        return inspect_capture(self.capture)


class RuntimeCaptureOwner:
    """Composition-only binding to real file, generation, scope and time owners.

    No client path, executable, import or provider configuration enters this
    contract. Read calls never seal or create a key. A legacy insecure store is
    not a capture store, even when its other test operations are permitted.
    """

    def __init__(
        self, *, store, scope, guard, session_current, clock, monotonic, forum_day, cost_ceiling
    ):
        if (
            not isinstance(store, FileMatterStore)
            or store._sealer is None
            or not isinstance(scope, EvaluationScope)
            or not isinstance(guard, GenerationGuard)
            or not all(
                callable(value)
                for value in (session_current, clock, monotonic, forum_day, cost_ceiling)
            )
        ):
            raise ReplayCaptureRefused("runtime capture requires actual protected owner bindings")
        self.store, self.scope, self.guard = store, scope, guard
        self.session_current = session_current
        self._clock, self._monotonic = clock, monotonic
        self._forum_day, self._cost_ceiling = forum_day, cost_ceiling
        self.log = MatterLoopLog(store, advocate_id=scope.advocate_id)

    def _current(self, matter_id, *, require_sources=True):
        if require_sources:
            self.guard.require_current()
        if matter_id not in self.scope.matter_ids or self.session_current() is not True:
            raise ReplayCaptureRefused("runtime capture is outside its actual current scope")
        matter = self.store.load(matter_id)
        if matter is None or matter.advocate_id != self.scope.advocate_id:
            raise ReplayCaptureRefused("runtime capture needs its current owned matter")
        if require_sources:
            self.guard.require_current()
        if self.session_current() is not True:
            raise ReplayCaptureRefused("runtime capture session changed while opening the file")
        return matter

    def begin(self, matter_id, *, profile=ReplayProfile.CONTROLLED):
        if not isinstance(profile, ReplayProfile):
            raise ReplayCaptureRefused("runtime capture uses a fixed owned profile")
        initial = self._current(matter_id)
        if any(not row.terminal for row in initial.loop_records):
            raise ReplayCaptureRefused("capture_incomplete: an initial journal is not terminal")
        if self._current(matter_id) != initial:
            raise ReplayCaptureRefused("runtime capture admission changed before observation")
        return RuntimeCaptureSession(self, initial, profile)

    def read(self, target_identity):
        if not isinstance(target_identity, LoopIdentity):
            raise ReplayCaptureRefused("capture read needs an actual exact target identity")
        # A historical capture is not current-world advice. Its sealed frozen
        # generation may outlive publication changes; custody/scope still apply.
        matter = self._current(target_identity.matter_id, require_sources=False)
        if target_identity.advocate_id != self.scope.advocate_id:
            raise ReplayCaptureRefused("capture target belongs to another actor")
        targets = [row for row in matter.loop_records if row.identity == target_identity]
        captures = [
            row
            for row in matter.loop_records
            if row.identity.turn_id == target_identity.turn_id + SUFFIX
        ]
        if len(targets) != 1 or not targets[0].terminal or len(captures) != 1:
            raise ReplayCaptureRefused("capture_incomplete: exact target/capture unavailable")
        target, journal = targets[0], captures[0]
        if not journal.terminal or len(journal.events) != 2 or not is_capture_record(journal):
            raise ReplayCaptureRefused(
                "capture_incomplete: runtime capture has no terminal receipt"
            )
        start, stop = journal.events[0].payload, journal.events[-1].payload
        closed(
            start,
            {"schema", "purpose", "target", "terminal", "capture_identity", "metadata_identity"},
            "runtime capture admission",
        )
        closed(
            stop,
            {"schema", "purpose", "released", "capture", "metadata"},
            "runtime capture receipt",
        )
        version = start["schema"]
        metadata_names = {"scope", "generation_binding", "context_policy", "limitations"}
        if version == 2:
            metadata_names.add("native_port_exchanges")
        metadata = closed(
            stop["metadata"],
            metadata_names,
            "runtime capture owner metadata",
        )
        capture = StrictReplayCapture.from_dict(stop["capture"])
        expected_scope = self._scope_record()
        if (
            type(start["schema"]) is not int
            or start["schema"] not in (1, 2)
            or type(stop["schema"]) is not int
            or stop["schema"] != version
            or start["purpose"] != PURPOSE
            or stop["purpose"] != PURPOSE
            or stop["released"] is not False
            or start["target"] != target.identity.as_dict()
            or start["terminal"] != target.events[-1].fingerprint
            or capture.payload["target"] != _enc(target)
            or start["capture_identity"] != capture.identity
            or start["metadata_identity"] != digest(metadata)
            or journal.identity.offer_hash != digest(start)
            or journal.identity.matter_id != target.identity.matter_id
            or journal.identity.advocate_id != target.identity.advocate_id
            or journal.identity.principles_version != target.identity.principles_version
            or journal.identity.tools_version != target.identity.tools_version
            or journal.identity.mode is not target.identity.mode
            or journal.identity.matter_version < target.identity.matter_version + len(target.events)
            or metadata["scope"] != expected_scope
            or capture.payload["owner_versions"]["sources"]
            != digest(metadata["generation_binding"])
            or metadata["limitations"] != list(LIMITATIONS)
        ):
            raise ReplayCaptureRefused("runtime capture differs from its actual protected owners")
        if version == 2:
            native = metadata["native_port_exchanges"]
            if type(native) is not list or len(native) > 10000:
                raise ReplayCaptureRefused("runtime capture has no finite native port population")
            for exchange in native:
                validate_exchange(exchange)
                if exchange["generation"] != capture.payload["owner_versions"]["sources"]:
                    raise ReplayCaptureRefused(
                        "runtime native port generation differs from admission"
                    )
            if native and capture.payload["profile"] != ReplayProfile.CONTROLLED.value:
                raise ReplayCaptureRefused(
                    "The foundation profile does not replay native full ports"
                )
        context = capture.payload["run"]["context_record"]
        policy = metadata["context_policy"]
        if context:
            ContextPolicy(**closed(policy, {"max_tokens", "reserve_tokens"}, "context policy"))
            ContextSession._require_record_shape(context)
        elif policy is not None:
            raise ReplayCaptureRefused("runtime capture cannot invent a context policy")
        by_identity = {row.identity.fingerprint: row for row in matter.loop_records}
        prior = []
        for ref in capture.payload["journal_refs"]:
            row = by_identity.get(digest(ref["identity"]))
            if (
                row is None
                or not row.terminal
                or row.identity.as_dict() != ref["identity"]
                or row.events[-1].fingerprint != ref["terminal_identity"]
                or row.identity.matter_version + len(row.events)
                > capture.payload["initial_matter"]["version"]
            ):
                raise ReplayCaptureRefused("runtime capture prior journal is missing or changed")
            prior.append(row)
        if self._current(matter.id, require_sources=False) != matter:
            raise ReplayCaptureRefused(
                "runtime capture changed while reading its sealed population"
            )
        return SavedRuntimeCapture(capture, journal, tuple(prior), metadata)

    def _scope_record(self):
        return {
            "approval_reference": self.scope.approval_reference,
            "advocate_id": self.scope.advocate_id,
            "matter_ids": sorted(self.scope.matter_ids),
            "mode": self.scope.mode.value,
        }


class RuntimeCaptureSession:
    def __init__(self, owner, initial, profile):
        self.owner, self.initial, self.profile = owner, initial, profile
        self.tapes = {
            name: []
            for name in ("clock", "monotonic", "forum_day", "cancelled", "cost", "boundaries")
        }
        self.exchanges = []
        self.bound = None
        self.finished = False
        self.registry_ports_observed = False
        self.permissions = ObservedPermissions(self)
        self.native_ports = NativePortRecorder(
            generation=owner.guard.version, require_current=self._native_current
        )

    def _native_current(self):
        if self.finished:
            raise ReplayCaptureRefused("native source read occurred after capture closure")
        if self.profile is not ReplayProfile.CONTROLLED:
            raise ReplayCaptureRefused("The foundation profile does not replay native full ports")
        return self.owner._current(self.initial.id)

    def native_port(self, owner, actual):
        """Observe an existing typed reader; no port grants or writer are added."""
        self._native_current()
        return self.native_ports.wrap(owner, actual)

    def observe_registry_ports(self, ports: ControlledRegistryPorts) -> ControlledRegistryPorts:
        """Instrument every native reader in the one controlled registry input.

        This is deliberately a closed projection rather than an ad-hoc list of
        popular readers. A newly added composition port must be classified here
        before a capture can continue. Snapshot/model/principles inputs are not
        native calls and need their own capture/verification; this does not make
        the controlled profile replay-ready.
        """
        self._native_current()
        if self.registry_ports_observed:
            raise ReplayCaptureRefused("controlled native registry ports were already projected")
        if not isinstance(ports, ControlledRegistryPorts):
            raise ReplayCaptureRefused("native observation needs actual controlled registry ports")
        mapped = {
            "evidence": "evidence",
            "search": "search",
            "authority_weight": "authority",
            "matter_documents": "documents",
            "playbooks": "playbooks",
        }
        snapshots = {"manifest", "model", "principles", "playbook_snapshot", "tables"}
        if {field.name for field in fields(ControlledRegistryPorts)} != set(mapped) | snapshots:
            raise ReplayCaptureRefused("controlled registry gained an unclassified capture port")
        table_ports = {
            "elements": "elements",
            "institution": "institution",
            "interim": "interim",
            "procedural": "procedural",
            "filing": "filing",
            "governing": "governing",
        }
        if {field.name for field in fields(PracticeTables)} != set(table_ports) | {"version"}:
            raise ReplayCaptureRefused("practice tables gained an unclassified capture port")
        if set(mapped.values()) | set(table_ports.values()) != set(CONTRACTS):
            raise ReplayCaptureRefused("native port contracts gained an unclassified owner")
        tables = replace(
            ports.tables,
            **{
                name: self.native_port(owner, getattr(ports.tables, name))
                if getattr(ports.tables, name) is not None
                else None
                for name, owner in table_ports.items()
            },
        )
        observed = replace(
            ports,
            tables=tables,
            **{
                name: self.native_port(owner, getattr(ports, name))
                if getattr(ports, name) is not None
                else None
                for name, owner in mapped.items()
            },
        )
        self._native_current()
        self.registry_ports_observed = True
        return observed

    def bind(
        self,
        identity,
        prompt,
        limits,
        *,
        principles,
        manifest,
        tier=Tier.ROUTINE,
        context_session=None,
        feedback_identity="",
        scope_identity="",
    ):
        if self.bound is not None or self.finished:
            raise ReplayCaptureRefused("runtime capture binds one actual admission exactly once")
        if (
            not isinstance(identity, LoopIdentity)
            or not isinstance(prompt, Prompt)
            or not isinstance(limits, LoopLimits)
            or not isinstance(principles, PrinciplesSnapshot)
            or not isinstance(manifest, Manifest)
            or not isinstance(tier, Tier)
            or identity.matter_id != self.initial.id
            or identity.advocate_id != self.initial.advocate_id
            or identity.matter_version != self.initial.version
            or identity.mode is not self.owner.scope.mode
            or identity.principles_version != principles.version
            or identity.offer_hash != digest(asdict(prompt))
            or self.owner._current(self.initial.id) != self.initial
        ):
            raise ReplayCaptureRefused("runtime capture admission is not its actual checked source")
        context, policy = {}, None
        if context_session is not None:
            if (
                not isinstance(context_session, ContextSession)
                or context_session.brief.matter_id != self.initial.id
                or context_session.brief.advocate_id != self.initial.advocate_id
                or context_session.principles != principles
                or context_session.system != prompt.system
            ):
                raise ReplayCaptureRefused("runtime capture context has different actual owners")
            context, policy = context_session.to_record(), asdict(context_session.policy)
        self.bound = {
            "identity": identity,
            "prompt": asdict(prompt),
            "limits": _enc(limits),
            "start_budget": limits.budget.as_dict(),
            "principles": asdict(principles),
            "manifest": _enc(manifest),
            "run": {
                "tier": tier.value,
                "context_record": context,
                "feedback_identity": feedback_identity,
                "scope_identity": scope_identity,
            },
            "context_policy": policy,
        }

    def _observe(self, name, callback, encode=lambda value: value):
        if self.finished:
            raise ReplayCaptureRefused("runtime observation occurred after capture closure")
        result = callback()
        self.tapes[name].append(encode(result))
        return result

    def clock(self):
        return self._observe("clock", self.owner._clock, lambda value: value.isoformat())

    def monotonic(self):
        return self._observe("monotonic", self.owner._monotonic)

    def forum_day(self):
        return self._observe("forum_day", self.owner._forum_day, lambda value: value.isoformat())

    def cancelled(self, callback):
        return self._observe("cancelled", callback)

    def cost_ceiling(self, input_tokens, output_tokens, tier):
        if self.finished:
            raise ReplayCaptureRefused("runtime price observation occurred after capture closure")
        value = self.owner._cost_ceiling(input_tokens, output_tokens, tier)
        self.tapes["cost"].append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tier": tier.value,
                "usd": value,
            }
        )
        return value

    def evidence(self, actual):
        return CapturedEvidence(self, actual)

    def finish(self, outcome):
        if self.finished or self.bound is None or not isinstance(outcome, LoopOutcome):
            raise ReplayCaptureRefused("capture_incomplete: actual bound terminal work is required")
        matter = self.owner._current(self.initial.id)
        record, data = outcome.record, self.bound
        if (
            record.identity != data["identity"]
            or not record.terminal
            or self.owner.log.read(record.identity) != record
            or matter.version != record.identity.matter_version + len(record.events)
        ):
            raise ReplayCaptureRefused(
                "capture_incomplete: terminal differs or later work intervened"
            )
        start = record.events[0].payload
        if (
            start.get("context") != data["run"]["context_record"]
            or start.get("feedback_identity") != data["run"]["feedback_identity"]
            or start.get("scope_identity") != data["run"]["scope_identity"]
            or start.get("budget") != data["start_budget"]
            or start.get("max_steps") != data["limits"]["max_steps"]
            or start.get("per_call_tokens") != data["limits"]["per_call_tokens"]
            or start.get("max_stagnant_steps") != data["limits"]["max_stagnant_steps"]
            or start.get("model_identity", {}).get("tier") != data["run"]["tier"]
        ):
            raise ReplayCaptureRefused("runtime capture inputs differ from their actual START")
        capture = StrictReplayCapture.from_dict(
            {
                "schema": 1,
                "profile": self.profile.value,
                "initial_matter": _source(self.initial),
                "initial_matter_identity": digest(_source(self.initial)),
                "journal_refs": [
                    {
                        "identity": row.identity.as_dict(),
                        "terminal_identity": row.events[-1].fingerprint,
                    }
                    for row in self.initial.loop_records
                ],
                "target": _enc(record),
                "principles": data["principles"],
                "manifest": data["manifest"],
                "prompt": data["prompt"],
                "limits": data["limits"],
                "run": data["run"],
                "owner_versions": {"sources": self.owner.guard.version},
                "tapes": self.tapes,
                "port_exchanges": self.exchanges,
                "final_matter_identity": digest(_source(matter)),
            }
        )
        metadata = {
            "scope": self.owner._scope_record(),
            "generation_binding": self.owner.guard.binding,
            "context_policy": data["context_policy"],
            "limitations": list(LIMITATIONS),
            "native_port_exchanges": self.native_ports.rows,
        }
        admission = {
            "schema": 2,
            "purpose": PURPOSE,
            "target": record.identity.as_dict(),
            "terminal": record.events[-1].fingerprint,
            "capture_identity": capture.identity,
            "metadata_identity": digest(metadata),
        }
        ident = LoopIdentity(
            matter.id,
            matter.advocate_id,
            record.identity.turn_id + SUFFIX,
            digest(admission),
            record.identity.principles_version,
            record.identity.tools_version,
            matter.version,
            record.identity.mode,
        )
        if any(row.identity.turn_id == ident.turn_id for row in matter.loop_records):
            raise ReplayCaptureRefused("runtime capture cannot overwrite an existing capture")
        self.owner._current(matter.id)
        first = LoopEvent.create(
            1, StepKind.START, self.owner._clock().isoformat(), admission, ident.fingerprint
        )
        self.owner.log.append(ident, first)
        self.owner._current(matter.id)
        stop = {
            "schema": 2,
            "purpose": PURPOSE,
            "released": False,
            "capture": capture.payload,
            "metadata": metadata,
        }
        last = LoopEvent.create(
            2, StepKind.STOP, self.owner._clock().isoformat(), stop, first.fingerprint
        )
        self.owner.log.append(ident, last)
        self.finished = True
        self.owner._current(matter.id)
        return self.owner.read(record.identity)


class CapturedEvidence:
    """Only supported actual typed public-law operations are callable here."""

    def __init__(self, capture, actual):
        self.capture, self.actual = capture, actual

    def _read(self, operation, arguments, callback):
        if self.capture.finished:
            raise ReplayCaptureRefused("source read occurred after capture closure")
        self.capture.owner._current(self.capture.initial.id)
        result = callback()
        self.capture.owner._current(self.capture.initial.id)
        if not isinstance(result, EvidenceResult):
            raise ReplayCaptureRefused("capture port returned no actual typed EvidenceResult")
        exchange = {
            "operation": operation,
            "arguments": arguments,
            "result": _enc(result),
            "source_generation": self.capture.owner.guard.version,
        }
        validate_port_exchange(exchange)
        self.capture.exchanges.append(exchange)
        return result

    def read_provision(self, act, section, as_of):
        if not isinstance(as_of, date):
            raise ReplayCaptureRefused("actual provision read needs a typed governing date")
        return self._read(
            PortOperation.READ_PROVISION.value,
            {"act": act, "section": section, "as_of": as_of.isoformat()},
            lambda: self.actual.read_provision(act, section, as_of),
        )

    def fetch(self, need):
        if not isinstance(need, EvidenceNeed):
            raise ReplayCaptureRefused("actual fetch needs its typed EvidenceNeed")
        return self._read(PortOperation.FETCH.value, _enc(need), lambda: self.actual.fetch(need))


class ObservedPermissions(PermissionTape):
    def __init__(self, capture):
        self.capture = capture
        super().__init__(
            Tape("observed permission owners", capture.tapes["boundaries"]),
            capture.owner.store,
            capture.owner.guard.version,
        )

    def check(self, phase, name, context):
        if self.capture.finished:
            raise ReplayCaptureRefused("permission observation occurred after capture closure")
        owner = self.capture.owner
        try:
            binding = owner.guard.observe()
            state = "current" if binding == owner.guard.binding else "changed"
            generation = digest(binding)
        except GenerationUnavailable:
            state, generation = "unavailable", None
        now = owner._clock()
        if not isinstance(now, datetime):
            raise ReplayCaptureRefused("permission owner requires its actual aware policy clock")
        instant(now.isoformat())
        self.tape.rows.append(
            {
                "phase": phase,
                "tool": name,
                "matter_id": context.identity.matter_id,
                "actor_id": context.identity.advocate_id,
                "current_version": context.current_version,
                "session_current": owner.session_current() is True,
                "scope_matter_ids": sorted(owner.scope.matter_ids),
                "source_generation": generation,
                "source_state": state,
                "claimed_capacity": None,
                "policy_at": now.isoformat(),
            }
        )
        return super().check(phase, name, context)
