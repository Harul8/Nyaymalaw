"""Append-only source-owned deadline/calendar candidates, never verified dates.

There is no authenticated court-calendar, counting-convention or legal-selection
owner here. A current source is not its legal application. Every new Deadline
therefore retains on=None; a quoted calendar entry never adjusts arithmetic.
Closed candidate records live in existing ledger Node.value and sealed journal,
not new store fields, and retain all competing/undated attributed observations.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Callable

from nm.Archives.legal_brain.orchestrate.loop_contracts import digest
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    PreparedToolResult,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.Archives.legal_brain.procedure import limitation
from nm.Archives.legal_brain.procedure.procedural_calculation import _population
from nm.Archives.legal_brain.reason.source_writes import _parent
from nm.Archives.legal_brain.reason.working_record import (
    REFERENCE_SCHEMA,
    WorkingRecordOwner,
    exact_reference,
)
from nm.Archives.legal_brain.reason.working_record_contracts import ReferenceKind
from nm.Archives.legal_brain.retrieve.evidence_port import Finding
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.clock_contracts import today as forum_today
from nm.shared.json_values import same_json_value
from nm.shared.model_port import SchemaViolation, require_schema
from nm.work_the_file import dependency
from nm.work_the_file.deadlines import Deadline, DeadlineKind, from_stored
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral
from nm.work_the_file.original_instruction import InstructionRefused, read_original_instruction

VERSION = "source-owned-conditional-deadline-proposals-v2"
DEADLINE = "propose_source_deadline"
CALENDAR = "propose_source_calendar"
MAX_CANDIDATE_CHARACTERS = 64000
_TEXT = {"type": "string", "minLength": 1}
_CLAUSE = object_schema(
    {
        "reference": REFERENCE_SCHEMA,
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
    }
)
_CALENDAR_REF = {**REFERENCE_SCHEMA, "type": ["object", "null"]}
SCHEMAS = {
    DEADLINE: object_schema(
        {
            "thread_id": _TEXT,
            "kind": {
                "type": "string",
                "enum": [
                    row.value
                    for row in DeadlineKind
                    if row is not DeadlineKind.INFORMATION_FOLLOWUP
                ],
            },
            "period_clause": _CLAUSE,
            "trigger_observation_id": _TEXT,
            "action_clause": _CLAUSE,
            "consequence_clause": _CLAUSE,
            "calendar_reference": _CALENDAR_REF,
            "reason": _TEXT,
        }
    ),
    CALENDAR: object_schema(
        {
            "thread_id": _TEXT,
            "court_clause": _CLAUSE,
            "entries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": object_schema({"clause": _CLAUSE, "date_expression": _TEXT}),
            },
            "reason": _TEXT,
        }
    ),
}
_CONTROLS = (
    "test_actual_loop_appends_only_conditional_deadlines_and_calendar_candidates",
    "test_deadline_proposals_recheck_sources_at_atomic_commit",
)
_LIMIT = (
    "Private source-backed product proposal only. Legal selection, court scope, "
    "counting convention, calendar completeness and applicable adjustments lack "
    "authenticated independent owners. No verified legal deadline, accepted task, "
    "filing authority or factual truth is established."
)


def _wire(value):
    text = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    if len(text) > MAX_CANDIDATE_CHARACTERS:
        raise ToolRefused("The complete proposal exceeds its finite owned ceiling.")
    return text


def _row_identity(row):
    return digest(neutral(asdict(row)))


def _deadline_node(row):
    return "conditional_deadline:" + row.thread + ":" + _row_identity(row)


def _calendar_node(thread_id, candidate):
    material = {key: value for key, value in candidate.items() if key != "node_name"}
    return "conditional_calendar:" + thread_id + ":" + digest(material)


def _ledger(matter):
    raw = matter.dependencies
    ledger = dependency.Ledger.from_stored(raw)
    if raw and not same_json_value(raw, ledger.as_dict()):
        raise ToolRefused("A partial or unreadable dependency history cannot receive a proposal.")
    if len({(row.kind, row.id) for row in ledger.tracked}) != len(ledger.tracked) or len(
        {row.name for row in ledger.nodes}
    ) != len(ledger.nodes):
        raise ToolRefused("The standing dependency population is ambiguous.")
    return ledger


def _inputs(
    matter, *, turn_id, operation, args, owner, source_generation, current_source_generation
):
    require_schema(args, SCHEMAS[operation])
    if (
        type(args["thread_id"]) is not str
        or not args["thread_id"].strip()
        or len(args["thread_id"]) > 100
        or not args["reason"].strip()
        or len(args["reason"]) > 16000
    ):
        raise ToolRefused("Proposal words and exact dispute identities must remain bounded.")
    if current_source_generation() != source_generation:
        raise ToolRefused("The actual admitted source generation changed.")
    parent = _parent(matter, turn_id, matter.advocate_id)
    call = parent.events[-1].payload["call"]
    if call["name"] != operation or not same_json_value(call["arguments"], args):
        raise ToolRefused("The candidate differs from the actual reserved parent operation.")
    original = read_original_instruction(parent)
    if original.state != "recorded":
        raise ToolRefused("A proposal needs its whole authenticated supplied instruction.")
    inventory = owner.build(parent, matter)
    thread_ref, facts, observations = _population(inventory, args["thread_id"])
    sources = [
        row
        for row in inventory.references.values()
        if row["reference"]["kind"] == ReferenceKind.SOURCE.value
    ]
    if any(row["value"]["generation"] != source_generation for row in sources):
        raise ToolRefused("A working source belongs to another admitted generation.")
    return parent, original, inventory, thread_ref, facts, observations, sources


def _clause(inventory, raw, findings):
    reference = exact_reference(inventory, raw["reference"])
    held = inventory.references[reference.id]
    if reference.kind is not ReferenceKind.SOURCE or "finding" not in held["value"]:
        raise ToolRefused("A raw or non-source window cannot impose a clock or calendar.")
    finding = Finding.from_record(held["value"]["finding"])
    if finding.supports is False or finding.source_blocking_reason:
        raise ToolRefused("Known unsupported source material cannot supply a proposal.")
    start, end = raw["start"], raw["end"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(finding.span)
        or not finding.span[start:end].strip()
    ):
        raise ToolRefused("The proposal needs an exact nonempty current source clause.")
    key = dependency.authority_id(finding)
    previous = findings.get(key)
    if previous is not None and dependency.authority_digest(previous) != (
        dependency.authority_digest(finding)
    ):
        raise ToolRefused("The same authority key has competing captured fingerprints.")
    findings[key] = finding
    return {
        "reference": reference.as_dict(),
        "start": start,
        "end": end,
        "quote": finding.span[start:end],
    }


def _calendar_entries(inventory, entries, findings):
    result = []
    for raw in entries:
        clause = _clause(inventory, raw["clause"], findings)
        expression = raw["date_expression"]
        if type(expression) is not str or len(expression) != 10:
            raise ToolRefused("Calendar candidates currently require verbatim full ISO dates.")
        parsed = date.fromisoformat(expression)
        if parsed.isoformat() != expression or expression not in clause["quote"]:
            raise ToolRefused("A calendar date must occur verbatim in its exact current clause.")
        row = {
            "clause": clause,
            "date_expression": expression,
            "on": expression,
            "legal_effect_established": False,
        }
        if row in result:
            raise ToolRefused("Repeated calendar entries add no source support.")
        result.append(row)
    return result


def _prior_calendar(inventory, raw, ledger, findings, *, thread_id, source_generation):
    if raw is None:
        return None
    reference = exact_reference(inventory, raw)
    value = inventory.references[reference.id]["value"]
    if (
        reference.kind is not ReferenceKind.WORK
        or value.get("state") != "returned"
        or value["call"]["name"] != CALENDAR
    ):
        raise ToolRefused("A calendar pointer must name its actual completed private proposal.")
    receipt = value["result"]
    candidate = receipt["data"]
    name = _calendar_node(thread_id, candidate)
    node = ledger.node(name)
    if (
        receipt["tool"] != CALENDAR
        or receipt["version"] != VERSION
        or candidate["thread_id"] != thread_id
        or candidate["source_generation"] != source_generation
        or candidate["calendar_complete"] is not False
        or candidate["calendar_adjustments_established"] is not False
        or node is None
        or node.value != _wire(candidate)
        or node.currency in (dependency.Currency.STALE, dependency.Currency.REWORKING)
        or not _population_proof_current(ledger, node, thread_id)
        or candidate["node_name"] != name
    ):
        raise ToolRefused("The calendar proposal is absent, changed, stale or mis-scoped.")
    # A prior execution receipt alone is not a current source. Reopen every
    # exact clause/date through this current inventory and reader owner.
    _clause(inventory, candidate["court_clause"], findings)
    replayed = _calendar_entries(
        inventory,
        [
            {"clause": entry["clause"], "date_expression": entry["date_expression"]}
            for entry in candidate["entries"]
        ],
        findings,
    )
    if not same_json_value(replayed, candidate["entries"]):
        raise ToolRefused("The calendar entries differ from their current source words.")
    return {"reference": reference.as_dict(), "candidate": candidate, "adjustments_applied": False}


def _derive(
    matter,
    *,
    turn_id,
    operation,
    args,
    owner,
    source_generation,
    current_source_generation,
    reference,
):
    if type(reference) is not date:
        raise ToolRefused("The proposal uses its actual trusted calendar reference.")
    initial = _inputs(
        matter,
        turn_id=turn_id,
        operation=operation,
        args=args,
        owner=owner,
        source_generation=source_generation,
        current_source_generation=current_source_generation,
    )
    parent, original, inventory, thread_ref, facts, observations, sources = initial
    thread = matter.thread(args["thread_id"])
    ledger, file_affected, _ = dependency.sync_inputs(
        _ledger(matter),
        matter,
        reason="The current recorded event/file population changed before proposal derivation.",
        at=reference.isoformat(),
        by=matter.advocate_id,
    )
    findings = {}
    data = {
        "version": VERSION,
        "thread_id": thread.id,
        "thread_reference": thread_ref["reference"],
        "source_generation": source_generation,
        "instruction_identity": original.text_identity,
        "instruction_provenance": original.provenance,
        "sources": sources,
        "chronology": facts,
        "observations": [row.as_dict() for row in observations],
        "reason": args["reason"],
        "calendar_complete": False,
        "calendar_adjustments_established": False,
        "counting_convention_established": False,
        "legal_selection_established": False,
        "legal_deadline_established": False,
        "factual_truth_established": False,
        "advocate_task_accepted": False,
        "authorises_action": False,
        "released": False,
        "client_ready": False,
    }
    if operation == CALENDAR:
        data["court_clause"] = _clause(inventory, args["court_clause"], findings)
        data["entries"] = _calendar_entries(inventory, args["entries"], findings)
        data["unresolved"] = [
            "Complete court/date population",
            "Applicable court scope",
            "Legal effect of each quoted entry",
            "Non-ISO or unstated calendar dates",
        ]
        # Name is derived from the closed record before adding the name itself.
        name = "conditional_calendar:" + thread.id + ":" + digest(data)
        data["node_name"] = name
        changed = thread
    else:
        period_clause = _clause(inventory, args["period_clause"], findings)
        action = _clause(inventory, args["action_clause"], findings)
        consequence = _clause(inventory, args["consequence_clause"], findings)
        observation = next(
            (row for row in observations if row.identity == args["trigger_observation_id"]), None
        )
        if observation is None:
            raise ToolRefused("The proposed trigger is not one exact current scoped observation.")
        period = limitation.unique_period_in(period_clause["quote"])
        on = (
            limitation.run_period(observation.on, period)
            if observation.on is not None and period is not None
            else None
        )
        calendar = _prior_calendar(
            inventory,
            args["calendar_reference"],
            ledger,
            findings,
            thread_id=thread.id,
            source_generation=source_generation,
        )
        support_identity = digest(
            {
                "source_generation": source_generation,
                "period_clause": period_clause,
                "action_clause": action,
                "consequence_clause": consequence,
                "observation": observation.as_dict(),
                "calendar": calendar,
            }
        )
        row = Deadline(
            thread.id,
            DeadlineKind(args["kind"]),
            source="Private product proposal; exact support "
            + support_identity
            + "; quoted source: "
            + period_clause["quote"],
            action="Proposed action, applicability unestablished. Source quote: " + action["quote"],
            owner=matter.advocate_id,
            consequence="Consequence unestablished; source quote: " + consequence["quote"],
            on=None,
            conditional_on=on,
        )
        old = tuple(from_stored(raw, thread=thread.id) for raw in thread.deadlines)
        identities = [_row_identity(item) for item in old]
        if len(set(identities)) != len(identities) or _row_identity(row) in identities:
            raise ToolRefused(
                "The standing register is ambiguous or this exact proposal already exists."
            )
        name = _deadline_node(row)
        data.update(
            deadline=neutral(asdict(row)),
            period_clause=period_clause,
            action_clause=action,
            consequence_clause=consequence,
            selected_observation=observation.as_dict(),
            period=neutral(asdict(period)) if period is not None else None,
            arithmetic_verified=on is not None,
            support_identity=support_identity,
            calendar_proposal=calendar,
            node_name=name,
            unresolved=[
                "Legal trigger and competing event effects",
                "Applicable clock/track",
                "Counting convention",
                "Authenticated court calendar and legal selection",
            ],
        )
        changed = replace(
            thread,
            deadlines=(*thread.deadlines, row),
            assessed=tuple(marker for marker in thread.assessed if marker != "deadlines"),
        )
    if ledger.node(name) is not None:
        raise ToolRefused("This exact private proposal is already recorded; append nothing twice.")
    ledger, affected, _ = dependency.sync_inputs(
        ledger,
        matter,
        tuple(findings.values()),
        reason="Source-backed private proposal observed the exact current file/source inputs.",
        at=reference.isoformat(),
        by=matter.advocate_id,
    )
    affected = tuple(sorted(set((*file_affected, *affected))))
    rests = [dependency.Rest(dependency.InputKind.AUTHORITY, ident) for ident in findings]
    rests.append(
        dependency.Rest(
            dependency.InputKind.EVENT_POPULATION, dependency.event_population_id(thread.id)
        )
    )
    if operation == DEADLINE:
        rests.extend(
            dependency.Rest(dependency.InputKind.FACT, fact["value"]["id"]) for fact in facts
        )
    rests.append(
        dependency.Rest(
            dependency.InputKind.UNKNOWN,
            "unestablished_legal_selection_count_calendar:" + thread.id,
        )
    )
    ledger = dependency.record(
        ledger,
        dependency.Node(
            name,
            _wire(data),
            tuple(rests),
            shown="Private conditional source-backed proposal",
            reason=_LIMIT,
            computed_at=reference.isoformat(),
        ),
    )
    after = replace(
        matter.with_thread(changed), version=matter.version, dependencies=ledger.as_dict()
    )
    repeated = _inputs(
        matter,
        turn_id=turn_id,
        operation=operation,
        args=args,
        owner=owner,
        source_generation=source_generation,
        current_source_generation=current_source_generation,
    )
    if not same_json_value(initial[2].payload, repeated[2].payload):
        raise ToolRefused(
            "The complete current working sources changed during proposal derivation."
        )
    return after, data, affected


@dataclass(frozen=True)
class DeadlineProposalMutation(FileMutation):
    operation: str
    turn_id: str
    reference: date
    proposed: dict
    owner: WorkingRecordOwner
    source_generation: str
    current_source_generation: Callable[[], str]

    def __post_init__(self):
        object.__setattr__(self, "proposed", deepcopy(self.proposed))
        if (
            self.operation not in (DEADLINE, CALENDAR)
            or not isinstance(self.owner, WorkingRecordOwner)
            or self.owner.source_current is None
            or type(self.source_generation) is not str
            or not self.source_generation.strip()
            or not callable(self.current_source_generation)
        ):
            raise ValueError(
                "A deadline proposal needs its exact operation and actual source owners."
            )
        super().__post_init__()

    def _validate_projection(self):
        try:
            expected, _, _ = _derive(
                self.before,
                turn_id=self.turn_id,
                operation=self.operation,
                args=self.proposed,
                owner=self.owner,
                source_generation=self.source_generation,
                current_source_generation=self.current_source_generation,
                reference=self.reference,
            )
        except (ReviewRefused, InstructionRefused, SchemaViolation) as exc:
            raise ToolRefused(
                "The prepared proposal lost its exact source/instruction owner."
            ) from exc
        if not same_json_value(neutral(asdict(expected)), neutral(asdict(self.after))):
            raise ValueError(
                "The prepared deadline/calendar projection differs from its typed owner."
            )
        super()._validate_projection()

    def _thread_projection(self, before, after, facts):
        if before.id == self.proposed["thread_id"]:
            after = replace(after, deadlines=before.deadlines)
        super()._thread_projection(before, after, facts)

    def _digest(self):
        return digest(
            {
                "base": super()._digest(),
                "operation": self.operation,
                "turn_id": self.turn_id,
                "reference": self.reference.isoformat(),
                "proposed": self.proposed,
                "source_generation": self.source_generation,
            }
        )


def _population_proof_current(ledger, node, thread_id) -> bool:
    population_id = dependency.event_population_id(thread_id)
    edges = tuple(
        rest
        for rest in node.rests_on
        if rest.kind is dependency.InputKind.EVENT_POPULATION and rest.id == population_id
    )
    tracked = ledger.input_of(dependency.InputKind.EVENT_POPULATION, population_id)
    return (
        len(edges) == 1
        and tracked is not None
        and not tracked.withdrawn
        and edges[0].version == tracked.version
    )


def deadline_proposal_currency(ledger, row) -> tuple[str, str] | None:
    """Root projection hook; exact candidate rows never borrow limitation currency."""
    if not isinstance(row, Deadline):
        return None
    node = ledger.node(_deadline_node(row))
    if node is None:
        return None
    try:
        raw = json.loads(node.value)
        if (
            raw["version"] != VERSION
            or raw["node_name"] != node.name
            or not same_json_value(raw["deadline"], neutral(asdict(row)))
            or row.on is not None
            or raw["legal_deadline_established"] is not False
        ):
            raise ValueError("damaged private candidate")
    except (KeyError, TypeError, ValueError):
        return "not_established", "The private deadline source/candidate record is unreadable."
    population_id = dependency.event_population_id(row.thread)
    edges = tuple(
        rest
        for rest in node.rests_on
        if rest.kind is dependency.InputKind.EVENT_POPULATION and rest.id == population_id
    )
    tracked = ledger.input_of(dependency.InputKind.EVENT_POPULATION, population_id)
    if len(edges) != 1 or tracked is None:
        return (
            "not_established",
            "The private candidate lacks exact recorded-event population proof.",
        )
    if node.currency in (dependency.Currency.STALE, dependency.Currency.REWORKING):
        return "stale", node.stale_because or "An exact source or attributed event changed."
    if not _population_proof_current(ledger, node, row.thread):
        return "stale", "The exact recorded event readings or chronology membership changed."
    return "not_established", _LIMIT


def deadline_proposal_tools(
    store,
    *,
    owner: WorkingRecordOwner,
    source_generation: str,
    current_source_generation: Callable[[], str],
    today=forum_today,
) -> tuple[RegisteredTool, ...]:
    """No model calls, new budgets, human approval fields or invented calendar."""
    if (
        not isinstance(owner, WorkingRecordOwner)
        or owner.source_current is None
        or type(source_generation) is not str
        or not source_generation.strip()
        or not callable(current_source_generation)
        or not callable(today)
    ):
        raise ValueError("Deadline proposals require their actual working/source/clock owners.")

    def run(operation, args, context):
        try:
            matter = store.load(context.identity.matter_id)
            if (
                matter is None
                or matter.advocate_id != context.identity.advocate_id
                or matter.version != context.current_version
            ):
                raise ToolRefused("A proposal needs its exact current owned file version.")
            parent = _parent(matter, context.identity.turn_id, context.identity.advocate_id)
            original = read_original_instruction(parent)
            if parent.identity != context.identity or original.text != context.original_message:
                raise ToolRefused("The supplied authenticated original instruction changed.")
            reference = today()
            after, data, _ = _derive(
                matter,
                turn_id=context.identity.turn_id,
                operation=operation,
                args=args,
                owner=owner,
                source_generation=source_generation,
                current_source_generation=current_source_generation,
                reference=reference,
            )
            mutation = DeadlineProposalMutation(
                matter,
                after,
                matter.advocate_id,
                operation,
                context.identity.turn_id,
                reference,
                args,
                owner,
                source_generation,
                current_source_generation,
            )
            envelope = ToolEnvelope(
                operation,
                VERSION,
                ToolKind.MATTER,
                ToolOutcome.RESULTS,
                Availability.PARTIAL,
                Assessment.NOT_ASSESSED,
                {
                    "matter_id": matter.id,
                    "matter_version": matter.version,
                    "snapshot": mutation.identity,
                    "source_generation": source_generation,
                },
                data,
                _LIMIT,
            )
            return PreparedToolResult(envelope, mutation)
        except (
            ReviewRefused,
            InstructionRefused,
            SchemaViolation,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ToolRefused(
                "The proposal lacks its exact current scoped source/typed owner."
            ) from exc

    from nm.work_the_file.tool_propose_source_calendar import build_tool as propose_source_calendar
    from nm.work_the_file.tool_propose_source_deadline import build_tool as propose_source_deadline

    return (propose_source_deadline(run=run), propose_source_calendar(run=run))
