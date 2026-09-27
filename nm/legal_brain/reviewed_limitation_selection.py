"""Recorded event selections reviewed by the existing independent claim owner.

These tools propose bindings, not facts or verdicts. Only replay of an actual
sealed independent dispatch can supply v2 calculation inputs. Reviewing a
selection does not confirm its attributed events: those dates remain conditional.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from nm.legal_brain import limitation, premise
from nm.legal_brain.brain_release import IndependentReview, ReviewRefused, ReviewService
from nm.legal_brain.calculation_tools import CalculationSource, calculation_snapshot
from nm.legal_brain.evidence_port import Finding
from nm.legal_brain.loop_contracts import LoopOutcome, LoopRecord, StepKind, StopReason, digest
from nm.legal_brain.tool_sources import (
    findings_from_envelope,
    source_envelopes_from_event,
    tool_envelope_from_record,
)
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.verifier import EvidencePackage, EvidenceSpan
from nm.shared.json_values import same_json_value
from nm.shared.model_port import SchemaViolation, require_schema
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.matter_contracts import Fact

VERSION = "event-limitation-selection-v2"
SourceCurrent = Callable[[Finding, str], bool]
_TEXT = {"type": "string", "minLength": 1}
_NULL_TEXT = {"type": ["string", "null"], "minLength": 1}
_CLAUSE = object_schema(
    {
        "source_id": _TEXT,
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
    }
)
_FACTOR = object_schema(
    {
        "observation_id": _TEXT,
        "clause": _CLAUSE,
        "kind": {
            "type": "string",
            "enum": [
                row.value
                for row in limitation.FactorKind
                if row is not limitation.FactorKind.NOT_ASSESSED
            ],
        },
        "effect": {
            "type": "string",
            "enum": ["restart", "exclude_elapsed_days", "exclude_inclusive_days"],
        },
        "end_observation_id": _NULL_TEXT,
        "reason": _TEXT,
    }
)
_COVERAGE = object_schema(
    {
        "fact_id": _TEXT,
        "state": {"type": "string", "enum": [row.value for row in limitation.Applied]},
        "clause": {**_CLAUSE, "type": ["object", "null"]},
        "reason": _TEXT,
    }
)
_EVENT_COVERAGE = object_schema(
    {
        "observation_id": _TEXT,
        "state": {"type": "string", "enum": [row.value for row in limitation.Applied]},
        "clause": {**_CLAUSE, "type": ["object", "null"]},
        "reason": _TEXT,
    }
)
_PRIVATE_PREMISE = object_schema(
    {
        "kind": {"type": "string", "enum": [row.value for row in premise.Kind]},
        "statement": _TEXT,
        "basis": {"type": "string", "enum": ["inferred", "unestablished", "stated"]},
        "reason": _TEXT,
        "alternatives": {"type": "array", "items": _TEXT},
        "source_clauses": {"type": "array", "items": _CLAUSE},
        "observation_ids": {"type": "array", "items": _TEXT},
        "instruction_span": {
            **object_schema(
                {
                    "start": {"type": "integer", "minimum": 0},
                    "end": {"type": "integer", "minimum": 1},
                }
            ),
            "type": ["object", "null"],
        },
    }
)
SELECTION_SCHEMA = object_schema(
    {
        "thread_id": _TEXT,
        "snapshot_id": _TEXT,
        "article": _CLAUSE,
        "accrual_observation_id": _TEXT,
        "alternative_observation_ids": {"type": "array", "items": _TEXT},
        "factors": {"type": "array", "items": _FACTOR},
        "chronology": {"type": "array", "items": _COVERAGE},
        "events": {"type": "array", "items": _EVENT_COVERAGE},
        "premises": {"type": ["array", "null"], "items": _PRIVATE_PREMISE},
        "reason": _TEXT,
    }
)


def _wire(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda item: item.isoformat() if hasattr(item, "isoformat") else item.value,
            ensure_ascii=False,
            allow_nan=False,
        )
    )


@dataclass(frozen=True)
class SourceChoice:
    id: str
    source: CalculationSource
    generation: str

    def as_dict(self):
        return {
            "id": self.id,
            "generation": self.generation,
            "source": {
                "turn_id": self.source.turn_id,
                "call_id": self.source.call_id,
                "event_fingerprint": self.source.event_fingerprint,
                "finding": self.source.finding.as_record(),
            },
        }


@dataclass(frozen=True)
class SelectedClause:
    choice: SourceChoice
    start: int
    end: int

    @property
    def text(self):
        return self.choice.source.finding.span[self.start : self.end]


@dataclass(frozen=True)
class EventFactor:
    observation: EventObservation
    end: EventObservation | None
    clause: SelectedClause
    kind: limitation.FactorKind
    effect: str
    reason: str


@dataclass(frozen=True)
class ChronologyDecision:
    fact: Fact
    state: limitation.Applied
    clause: SelectedClause | None
    reason: str


@dataclass(frozen=True)
class EventDecision:
    observation: EventObservation
    state: limitation.Applied
    clause: SelectedClause | None
    reason: str


@dataclass(frozen=True)
class LimitationInputsV2:
    """A replayable reviewed binding, not a caller-authored review flag."""

    snapshot_id: str
    parent_turn_id: str
    package_id: str
    package_identity: str
    source_generation: str
    premises: premise.Premises
    premise_origin: str
    premise_clauses: tuple[SelectedClause, ...]
    article: SelectedClause
    accrual: EventObservation
    observations: tuple[EventObservation, ...]
    chronology: tuple[Fact, ...]
    alternatives: tuple[EventObservation, ...]
    factors: tuple[EventFactor, ...]
    decisions: tuple[ChronologyDecision, ...]
    event_decisions: tuple[EventDecision, ...]
    reason: str

    def __post_init__(self):
        for population, kind in (
            (self.observations, EventObservation),
            (self.chronology, Fact),
            (self.alternatives, EventObservation),
            (self.factors, EventFactor),
            (self.decisions, ChronologyDecision),
            (self.event_decisions, EventDecision),
            (self.premise_clauses, SelectedClause),
        ):
            if type(population) is not tuple or any(type(row) is not kind for row in population):
                raise ValueError("Reviewed v2 inputs preserve their exact typed populations")
        if type(self.accrual) is not EventObservation or type(self.article) is not SelectedClause:
            raise ValueError("Reviewed v2 inputs retain exact event and legal-clause owners")


@dataclass(frozen=True)
class SelectionBinding:
    inputs: LimitationInputsV2
    package: EvidencePackage
    candidate: dict


@dataclass(frozen=True)
class LimitationSelectionReview:
    bindings: tuple[SelectionBinding, ...]
    review: IndependentReview | None

    @property
    def unresolved(self):
        released = () if self.review is None else self.review.result.released
        return tuple(row for row in self.bindings if row.package not in released)


def _owned_population(matter, thread):
    from nm.work_the_file.date_resolution import resolve

    if (
        type(thread.chronology) is not tuple
        or len(set(thread.chronology)) != len(thread.chronology)
        or len({row.id for row in matter.facts}) != len(matter.facts)
    ):
        raise ReviewRefused("The calculation chronology has ambiguous fact identities")
    current = {row.id: row for row in matter.facts}
    if any(ident not in current for ident in thread.chronology):
        raise ReviewRefused("A calculation chronology entry has no recorded fact owner")
    facts = tuple(current[ident] for ident in thread.chronology)
    if any(
        type(row) is not Fact
        or type(row.version) is not int
        or row.confirmed is not None
        and type(row.confirmed) is not bool
        for row in facts
    ):
        raise ReviewRefused("Recorded facts must retain their exact typed owner fields")
    if type(thread.event_observations) is not tuple:
        raise ReviewRefused("The event reading population is not its recorded tuple")
    observations = tuple(EventObservation.restore(raw) for raw in thread.event_observations)
    if len({row.identity for row in observations}) != len(observations):
        raise ReviewRefused("Duplicate event identities cannot select one legal trigger")
    for row in observations:
        fact = current.get(row.source_fact)
        if (
            fact is None
            or fact.id not in thread.chronology
            or type(fact.version) is not int
            or fact.version != row.source_version
            or fact.statement != row.account
            or fact.superseded_by
            or fact.conflicts_with
            or fact.confirmed is False
            or row.on is not None
            and resolve(row.date_expression, row.reference) != row.on
        ):
            raise ReviewRefused("An event observation lost its exact current attributed source")
    owned = premise.Premises.from_stored(thread.premises)
    # The legacy decoder is permissive for old files; this new boundary must
    # not silently coerce, discard duplicates or erase unknown premise members.
    if len({row.kind for row in owned.items}) != len(owned.items) or not same_json_value(
        _wire(list(thread.premises)), _wire(list(owned.as_rows()))
    ):
        raise ReviewRefused("The recorded premise population is unreadable or ambiguous")
    return facts, observations, owned


def _sources(matter, generation, source_current):
    from nm.legal_brain.brain_assessment import _primary_read

    if type(generation) is not str or not generation.strip() or not callable(source_current):
        raise ReviewRefused("No actual current primary-source owner is configured")
    choices, ids = [], set()
    for record in matter.loop_records:
        if (
            type(record) is not LoopRecord
            or record.identity.matter_id != matter.id
            or record.identity.advocate_id != matter.advocate_id
        ):
            raise ReviewRefused("The source journal is foreign or unreadable")
        calls = {}
        for event in record.events:
            if event.kind is StepKind.TOOL_STARTED:
                call = event.payload["call"]
                if call["call_id"] in calls:
                    raise ReviewRefused("An actual source dispatch is duplicated")
                calls[call["call_id"]] = call
            if event.kind is not StepKind.TOOL_RETURNED:
                continue
            call = calls.pop(event.payload["call_id"], None)
            parent = tool_envelope_from_record(event.payload["receipt"])
            if call is None or call["name"] != parent.tool:
                raise ReviewRefused("A primary-source result lost its actual matching dispatch")
            for envelope in source_envelopes_from_event(event):
                if (
                    envelope.availability is Availability.UNAVAILABLE
                    or envelope.outcome is not ToolOutcome.RESULTS
                    or envelope.receipt.get("source_version") != generation
                ):
                    continue
                captured = findings_from_envelope(envelope)
                for raw_read in envelope.receipt.get("primary_reads", []):
                    primary = _primary_read(raw_read)
                    for finding, raw in zip(primary.findings, raw_read["findings"], strict=True):
                        if (
                            not any(
                                same_json_value(row.as_record(), finding.as_record())
                                for row in captured
                            )
                            or not same_json_value(raw, finding.as_record())
                            or finding.supports is False
                            or finding.source_blocking_reason
                            or finding.governing_date is None
                            or source_current(finding, generation) is not True
                        ):
                            continue
                        source = CalculationSource(
                            record.identity.turn_id, call["call_id"], event.fingerprint, finding
                        )
                        ident = digest(
                            {
                                "source": {
                                    "turn": source.turn_id,
                                    "call": source.call_id,
                                    "event": source.event_fingerprint,
                                    "finding": finding.as_record(),
                                },
                                "generation": generation,
                            }
                        )
                        if ident in ids:
                            raise ReviewRefused("A primary source identity is ambiguous")
                        ids.add(ident)
                        choices.append(SourceChoice(ident, source, generation))
    return tuple(choices)


def selection_inventory(matter, thread, *, source_generation, source_current):
    """All current recorded events are offered; never sort dates into a trigger."""
    facts, observations, owned = _owned_population(matter, thread)
    choices = _sources(matter, source_generation, source_current)
    return {
        "thread_id": thread.id,
        "snapshot_id": calculation_snapshot(matter, thread),
        "source_generation": source_generation,
        "sources": [row.as_dict() for row in choices],
        "chronology": _wire([asdict(row) for row in facts]),
        "observations": [row.as_dict() for row in observations],
        "premises": _wire(list(owned.as_rows())),
        "missing_canonical_premises": [row.value for row in premise.Kind if owned.of(row) is None],
        "selection_reviewed": False,
        "factual_truth_established": False,
    }


def _describe(value, path="subject"):
    """Reversible field lines, not JSON quotation marks masquerading as law quotes."""
    if isinstance(value, dict):
        return "\n".join(_describe(value[key], path + "." + key) for key in sorted(value))
    if isinstance(value, list):
        return (
            "\n".join(_describe(item, f"{path}[{index}]") for index, item in enumerate(value))
            or path + " = []"
        )
    if isinstance(value, str):
        encoded = value.replace("\\", "\\\\").replace('"', "\\u0022")
        encoded = encoded.replace("“", "\\u201c").replace("”", "\\u201d")
        return path + " = " + encoded
    return path + " = " + json.dumps(value, allow_nan=False)


def _binding(matter, thread, candidate, parent, *, source_generation, source_current):
    from nm.work_the_file.original_instruction import read_original_instruction

    require_schema(candidate, SELECTION_SCHEMA)
    facts, observations, owned = _owned_population(matter, thread)
    snapshot = calculation_snapshot(matter, thread)
    if candidate["thread_id"] != thread.id or candidate["snapshot_id"] != snapshot:
        raise ReviewRefused("The proposed selection belongs to a different current snapshot")
    sources = {row.id: row for row in _sources(matter, source_generation, source_current)}
    events = {row.identity: row for row in observations}
    original = read_original_instruction(parent)

    def clause(raw):
        if raw is None:
            return None
        choice = sources.get(raw["source_id"])
        start, end = raw["start"], raw["end"]
        if (
            choice is None
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(choice.source.finding.span)
            or not choice.source.finding.span[start:end].strip()
        ):
            raise ReviewRefused("A legal clause has no exact current primary-source span")
        return SelectedClause(choice, start, end)

    def observed(ident, *, dated=True):
        row = events.get(ident)
        if row is None or dated and row.on is None:
            raise ReviewRefused("A selected clock event has no exact current resolved date basis")
        return row

    canonical = owned
    premise_clauses = []
    if candidate["premises"] is None:
        if len(owned.items) != len(tuple(premise.Kind)):
            raise ReviewRefused("No complete recorded or private candidate premise owner exists")
        premise_origin = "recorded_thread"
    else:
        raw_premises = candidate["premises"]
        if len(raw_premises) != len(tuple(premise.Kind)) or tuple(
            row["kind"] for row in raw_premises
        ) != tuple(row.value for row in premise.REQUIRED):
            raise ReviewRefused(
                "A private selection needs exactly the three distinct ordered premises"
            )
        rows = []
        for raw in raw_premises:
            selected_clauses = tuple(clause(row) for row in raw["source_clauses"])
            referenced = raw["observation_ids"]
            if len(set(referenced)) != len(referenced) or any(
                row not in events for row in referenced
            ):
                raise ReviewRefused("A premise cites missing or duplicate current event identities")
            basis = premise.Basis(raw["basis"])
            span = raw["instruction_span"]
            if basis is premise.Basis.STATED:
                if (
                    original.state != "recorded"
                    or span is None
                    or type(span["start"]) is not int
                    or type(span["end"]) is not int
                    or not 0 <= span["start"] < span["end"] <= len(original.text)
                    or original.text[span["start"] : span["end"]] != raw["statement"]
                ):
                    raise ReviewRefused(
                        "A stated premise needs its exact admitted instruction span"
                    )
                source = f"instruction:{original.text_identity}:{span['start']}:{span['end']}"
            else:
                if (
                    span is not None
                    or basis is premise.Basis.INFERRED
                    and (not selected_clauses or not referenced)
                ):
                    raise ReviewRefused("An inferred premise needs exact legal and event sources")
                source = ";".join(row.choice.id for row in selected_clauses)
            premise_clauses.extend(selected_clauses)
            inferred_from = raw["reason"] if basis is premise.Basis.INFERRED else ""
            rows.append(
                premise.Premise(
                    premise.Kind(raw["kind"]),
                    raw["statement"],
                    basis,
                    source=source,
                    inferred_from=inferred_from,
                    alternatives=tuple(raw["alternatives"]),
                )
            )
        owned = premise.Premises(tuple(rows))
        premise_origin = "private_review_candidate"

    article = clause(candidate["article"])
    accrual = observed(candidate["accrual_observation_id"])
    alternative_ids = candidate["alternative_observation_ids"]
    if len(set(alternative_ids)) != len(alternative_ids) or accrual.identity in alternative_ids:
        raise ReviewRefused("Competing event selections have duplicate or selected identities")
    alternatives = tuple(observed(ident, dated=False) for ident in alternative_ids)
    factors = []
    for raw in candidate["factors"]:
        event = observed(raw["observation_id"])
        end = observed(raw["end_observation_id"]) if raw["end_observation_id"] else None
        if (
            raw["effect"] == "restart"
            and end is not None
            or raw["effect"] != "restart"
            and (end is None or end.on < event.on)
            or event.identity == accrual.identity
            or any(row.observation.identity == event.identity for row in factors)
        ):
            raise ReviewRefused("A clock-moving effect is contradictory or duplicated")
        factors.append(
            EventFactor(
                event,
                end,
                clause(raw["clause"]),
                limitation.FactorKind(raw["kind"]),
                raw["effect"],
                raw["reason"],
            )
        )
    applied = {
        accrual.source_fact,
        *(row.observation.source_fact for row in factors),
        *(row.end.source_fact for row in factors if row.end),
    }
    rows = candidate["chronology"]
    if tuple(row["fact_id"] for row in rows) != tuple(row.id for row in facts):
        raise ReviewRefused("The selection must preserve every chronology entry in owned order")
    decisions = []
    for fact, raw in zip(facts, rows, strict=True):
        state, selected = limitation.Applied(raw["state"]), clause(raw["clause"])
        if (
            (state is limitation.Applied.APPLIED) != (fact.id in applied)
            or state is limitation.Applied.NO_EFFECT
            and selected is None
            or state is limitation.Applied.NOT_ASSESSED
            and selected is not None
        ):
            raise ReviewRefused("A chronology state lacks its reviewed factual/legal association")
        decisions.append(ChronologyDecision(fact, state, selected, raw["reason"]))
    applied_events = {
        accrual.identity,
        *(row.observation.identity for row in factors),
        *(row.end.identity for row in factors if row.end),
    }
    event_rows = candidate["events"]
    if tuple(row["observation_id"] for row in event_rows) != tuple(
        row.identity for row in observations
    ):
        raise ReviewRefused("The selection must preserve every source event in owned order")
    event_decisions = []
    for event, raw in zip(observations, event_rows, strict=True):
        state, selected = limitation.Applied(raw["state"]), clause(raw["clause"])
        if (
            (state is limitation.Applied.APPLIED) != (event.identity in applied_events)
            or state is limitation.Applied.NO_EFFECT
            and selected is None
            or state is limitation.Applied.NOT_ASSESSED
            and selected is not None
            or event.identity in alternative_ids
            and state is not limitation.Applied.NOT_ASSESSED
        ):
            raise ReviewRefused("A source event state lacks its exact reviewed association")
        event_decisions.append(EventDecision(event, state, selected, raw["reason"]))
    for row in decisions:
        if row.state is limitation.Applied.NO_EFFECT and any(
            event.observation.source_fact == row.fact.id
            and event.state is not limitation.Applied.NO_EFFECT
            for event in event_decisions
        ):
            raise ReviewRefused("A no-effect account cannot hide an undecided source event")
    all_clauses = (
        article,
        *premise_clauses,
        *(row.clause for row in factors),
        *(row.clause for row in decisions if row.clause),
        *(row.clause for row in event_decisions if row.clause),
    )
    spans = tuple(
        EvidenceSpan(f"selection_clause_{index}", row.choice.source.finding, row.start, row.end)
        for index, row in enumerate(all_clauses)
    )
    context = {
        "candidate": candidate,
        "source_generation": source_generation,
        "observations": [row.as_dict() for row in observations],
        "premises": _wire(list(owned.as_rows())),
        "canonical_premises": _wire(list(canonical.as_rows())),
        "premise_origin": premise_origin,
        "original_instruction": original.as_dict(),
        "sources": [row.choice.as_dict() for row in all_clauses],
    }
    ident = digest(context)
    package = EvidencePackage(
        "limitation_selection_" + ident,
        "Review this legal-selection proposal, not factual truth or a deadline. Its selected "
        "Article, exact period/trigger clause, jurisdiction and date association must follow "
        "from the captured clauses and the original attributed accounts. Each proposed applied "
        "or no-effect chronology state and clock-moving operation needs that same legal and "
        "factual support. NOT_ASSESSED is an explicit gap, never a no-effect finding. A resolved "
        "event date is only a source reading, not a confirmed Fact.date. Preserve all inferred "
        "premises, denials, undated events and alternatives; do not select by earliest date or "
        "model memory. A favorable review establishes only the support for this conditional "
        "selection. Field lines below preserve exact strings with backslash escapes; u0022, "
        "u201c and u201d denote their original quotation characters.\n" + _describe(context),
        spans,
        facts,
    )
    inputs = LimitationInputsV2(
        snapshot,
        parent.identity.turn_id,
        package.id,
        package.identity,
        source_generation,
        owned,
        premise_origin,
        tuple(premise_clauses),
        article,
        accrual,
        observations,
        facts,
        alternatives,
        tuple(factors),
        tuple(decisions),
        tuple(event_decisions),
        candidate["reason"],
    )
    return SelectionBinding(inputs, package, candidate)


def limitation_selection_tools(store, *, source_generation, source_current):
    """No model dispatch, write mutation, approval flag or new budget inside a tool."""

    def file_of(context, thread_id):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("The event selection needs this actor's exact current file")
        if context.issue_ids and thread_id not in context.issue_ids:
            raise ToolRefused("The selected dispute is outside this admitted issue scope")
        matches = tuple(row for row in matter.threads if row.id == thread_id)
        if len(matches) != 1:
            raise ToolRefused("The selected dispute is missing or ambiguous")
        return matter, matches[0]

    from nm.legal_brain.tool_propose_limitation_selection import (
        build_tool as propose_limitation_selection_tool,
    )
    from nm.legal_brain.tool_read_limitation_candidates import (
        build_tool as read_limitation_candidates_tool,
    )

    return (
        read_limitation_candidates_tool(
            file_of=file_of,
            store=store,
            source_generation=source_generation,
            source_current=source_current,
        ),
        propose_limitation_selection_tool(
            file_of=file_of,
            store=store,
            source_generation=source_generation,
            source_current=source_current,
        ),
    )


def _candidate_envelope(binding, matter_id):
    return ToolEnvelope(
        "propose_limitation_selection",
        VERSION,
        ToolKind.COMPUTATION,
        ToolOutcome.RESULTS,
        Availability.AVAILABLE,
        Assessment.NOT_ASSESSED,
        {
            "inputs": binding.candidate,
            "method": "candidate exact limitation selection; no review",
            "input_receipts": [{"matter_id": matter_id, "snapshot": binding.inputs.snapshot_id}],
            "subject": binding.package.identity,
            "source_generation": binding.inputs.source_generation,
        },
        {
            "candidate": binding.candidate,
            "selection_reviewed": False,
            "factual_truth_established": False,
        },
        "Candidate only: no independent selection review or factual confirmation has occurred.",
    )


def prepare_limitation_selections(outcome, matter, *, source_generation, source_current):
    bindings, calls, threads = [], {}, set()
    for event in outcome.record.events:
        if event.kind is StepKind.TOOL_STARTED:
            call = event.payload["call"]
            if call["call_id"] in calls:
                raise ReviewRefused("The selection's actual dispatch identity is duplicated")
            calls[call["call_id"]] = call
        if event.kind is not StepKind.TOOL_RETURNED:
            continue
        call = calls.pop(event.payload["call_id"], None)
        raw = event.payload["receipt"]
        if raw.get("tool") != "propose_limitation_selection":
            continue
        if call is None or call["name"] != raw["tool"]:
            raise ReviewRefused("A selection candidate has no exact actual dispatch")
        candidate = call["arguments"]
        ident = candidate["thread_id"]
        thread = matter.thread(ident)
        if thread is None or ident in threads:
            raise ReviewRefused("The author turn has missing or competing selection candidates")
        binding = _binding(
            matter,
            thread,
            candidate,
            outcome.record,
            source_generation=source_generation,
            source_current=source_current,
        )
        if not same_json_value(json.loads(_candidate_envelope(binding, matter.id).wire()), raw):
            raise ReviewRefused("The selection receipt differs from its actual owned candidate")
        threads.add(ident)
        bindings.append(binding)
    return tuple(bindings)


class LimitationSelectionReviewService:
    """After-terminal selection review shares the existing whole-task ledger."""

    def __init__(self, reviewer: ReviewService, *, source_generation, source_current):
        if not isinstance(reviewer, ReviewService) or not callable(source_current):
            raise ValueError(
                "Selection review requires actual independent and current-source owners"
            )
        self.reviewer, self.source_generation, self.source_current = (
            reviewer,
            source_generation,
            source_current,
        )

    def review(self, outcome, *, cancelled=lambda: False, max_model_calls=None, budget=None):
        def prepare(parent, matter):
            return prepare_limitation_selections(
                parent,
                matter,
                source_generation=self.source_generation,
                source_current=self.source_current,
            )

        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = prepare(outcome, matter)
        if not bindings:
            return LimitationSelectionReview((), None)
        packages = tuple(row.package for row in bindings)

        def current(parent, file, proposed):
            if tuple(row.package for row in prepare(parent, file)) != proposed:
                raise ReviewRefused("The limitation selection subjects moved before review")

        def captured(parent, file, proposed):
            current(parent, file, proposed)
            return tuple(
                dict.fromkeys(span.finding for package in proposed for span in package.spans)
            )

        # The shared review owner validates/rolls up this current ledger. Never
        # alter the sealed parent outcome or synthesize a fresh child budget.
        options = dict(
            current_owner=current,
            current_sources=captured,
            cancelled=cancelled,
            max_model_calls=max_model_calls,
        )
        if budget is not None:
            options["budget"] = budget
        review = self.reviewer.review_packages(outcome, packages, **options)
        return LimitationSelectionReview(bindings, review)


class _RecordedLog:
    def __init__(self, records):
        self.records = records

    def read(self, identity):
        matches = tuple(row for row in self.records if row.identity == identity)
        if len(matches) != 1:
            raise ReviewRefused("The independent selection has no unique sealed journal")
        return matches[0]


def resolve_limitation_inputs(
    matter,
    thread,
    context=None,
    *,
    source_generation,
    source_current,
    now=None,
    parent_turn_id=None,
):
    """Replay current subjects and paid independent receipts, never stored PASS flags.

    Different current positive selections are ambiguous. No timestamp, newest
    turn or date ordering arbitrarily chooses between them.
    """
    from nm.legal_brain.brain_assessment import saved_package_reviews
    from nm.legal_brain.loop import _budget_from

    now = now or datetime.now(timezone.utc)
    if (
        now.tzinfo is None
        or type(matter.loop_records) is not tuple
        or any(type(row) is not LoopRecord for row in matter.loop_records)
        or context is not None
        and (
            context.identity.matter_id != matter.id
            or context.identity.advocate_id != matter.advocate_id
            or context.issue_ids
            and thread.id not in context.issue_ids
        )
    ):
        return None
    matching = []
    log = _RecordedLog(matter.loop_records)
    for parent in matter.loop_records:
        if (
            not parent.terminal
            or ":verify:" in parent.identity.turn_id
            or context is not None
            and parent.identity.mode is not context.identity.mode
            or parent_turn_id is not None
            and parent.identity.turn_id != parent_turn_id
        ):
            continue
        try:
            at = datetime.fromisoformat(parent.events[-1].at)
            if at.tzinfo is None or at > now:
                continue
            outcome = LoopOutcome(
                StopReason(parent.events[-1].payload["reason"]),
                parent,
                _budget_from(parent.events[-1].payload["budget"]),
                parent.events[-1].payload.get("proposal", {}),
            )
            bindings = prepare_limitation_selections(
                outcome, matter, source_generation=source_generation, source_current=source_current
            )
            bindings = tuple(row for row in bindings if row.candidate["thread_id"] == thread.id)
            if len(bindings) != 1:
                continue
            binding = bindings[0]
            reviewed_id = f"{parent.identity.turn_id}:verify:{binding.package.id}"
            saved = log.read(
                next(
                    row.identity
                    for row in matter.loop_records
                    if row.identity.turn_id == reviewed_id
                )
            )
            reviewed_at = datetime.fromisoformat(saved.events[-1].at)
            if not saved.terminal or reviewed_at.tzinfo is None or reviewed_at > now:
                continue
            review = saved_package_reviews(outcome, (binding.package,), matter, log)
            if review.result.released == (binding.package,):
                matching.append(binding.inputs)
        except (ReviewRefused, SchemaViolation, ValueError, TypeError, KeyError, StopIteration):
            continue
    return matching[0] if len(matching) == 1 else None
