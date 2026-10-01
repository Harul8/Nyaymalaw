"""Conditional arithmetic over actual working sources and attributed events.

No trigger, track, counting convention, extension or court calendar is decided
here. This does not create a Deadline, review a legal selection, or mutate the
file. All competing/undated observations remain in its complete scoped receipt.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable

from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
)
from nm.Archives.legal_brain.reason.source_writes import _parent
from nm.Archives.legal_brain.reason.working_record import (
    MAX_INVENTORY_CHARACTERS,
    WorkingRecordOwner,
)
from nm.Archives.legal_brain.reason.working_record_contracts import ReferenceKind
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.json_values import same_json_value
from nm.work_the_file.date_resolution import resolve
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.file_mutation_contracts import neutral
from nm.work_the_file.original_instruction import read_original_instruction

VERSION = "conditional-procedural-arithmetic-v1"
READ = "read_procedural_calculation_inputs"
COMPUTE = "compute_procedural_period"
_TEXT = {"type": "string", "minLength": 1}
_CONTROLS = (
    "test_actual_loop_computes_only_conditional_arithmetic_without_losing_competing_events",
    "test_arithmetic_cannot_invent_inputs_or_register_a_legal_deadline",
)
_LIMIT = (
    "Conditional calendar addition only. Selection has no independent legal review; "
    "trigger association, applicability, track, counting convention, extension and "
    "court-calendar adjustments are not established. No legal deadline is registered."
)


def _population(inventory, thread_id):
    references = inventory.references
    thread_ref = references.get("thread:" + thread_id)
    if thread_ref is None or thread_ref["reference"]["kind"] != ReferenceKind.THREAD.value:
        raise ToolRefused("The target dispute is outside the complete admitted working scope.")
    value = thread_ref["value"]
    chronology = value["chronology"]
    if (
        type(chronology) is not list
        or any(type(ident) is not str for ident in chronology)
        or len(chronology) != len(set(chronology))
    ):
        raise ToolRefused("The full attributed chronology is ambiguous or unreadable.")
    facts = []
    for ident in chronology:
        reference = references.get("fact:" + ident)
        if (
            reference is None
            or reference["reference"]["kind"] != ReferenceKind.FACT.value
            or thread_id not in reference["thread_ids"]
        ):
            raise ToolRefused("A chronology entry lost its exact scoped working fact owner.")
        facts.append(reference)
    by_id = {row["value"]["id"]: row["value"] for row in facts}
    raw_observations = value["event_observations"]
    if type(raw_observations) is not list:
        raise ToolRefused("The complete event population is unreadable.")
    observations = tuple(EventObservation.restore(raw) for raw in raw_observations)
    if len({row.identity for row in observations}) != len(observations):
        raise ToolRefused("Repeated event identities do not establish one trigger.")
    for raw, observation in zip(raw_observations, observations, strict=True):
        fact = by_id.get(observation.source_fact)
        if (
            not same_json_value(raw, neutral(asdict(observation)))
            or fact is None
            or type(fact["version"]) is not int
            or fact["version"] != observation.source_version
            or fact["statement"] != observation.account
            or fact["superseded_by"]
            or fact["conflicts_with"]
            or fact["confirmed"] is False
            or fact["confirmed"] is not None
            and type(fact["confirmed"]) is not bool
            or observation.on is not None
            and resolve(observation.date_expression, observation.reference) != observation.on
        ):
            raise ToolRefused(
                "An observation lost its current complete attributed account/date owner."
            )
    return thread_ref, tuple(facts), observations


def procedural_calculation_tools(
    store,
    *,
    owner: WorkingRecordOwner,
    source_generation: str,
    current_source_generation: Callable[[], str],
) -> tuple[RegisteredTool, ...]:
    """Optional read-only tools; current WorkingRecordOwner supplies all evidence."""
    if (
        not isinstance(owner, WorkingRecordOwner)
        or owner.source_current is None
        or type(source_generation) is not str
        or not source_generation.strip()
        or not callable(current_source_generation)
    ):
        raise ValueError("Conditional arithmetic needs its actual working/source generation owners")

    def current(args, context, name):
        try:
            if current_source_generation() != source_generation:
                raise ToolRefused("The admitted source generation is no longer current.")
            matter = store.load(context.identity.matter_id)
            if (
                matter is None
                or matter.advocate_id != context.identity.advocate_id
                or matter.version != context.current_version
            ):
                raise ToolRefused("Conditional arithmetic needs its exact current owned file.")
            parent = _parent(matter, context.identity.turn_id, context.identity.advocate_id)
            call = parent.events[-1].payload["call"]
            if (
                parent.identity != context.identity
                or call["name"] != name
                or not same_json_value(call["arguments"], args)
            ):
                raise ToolRefused("The request differs from its actual reserved parent operation.")
            original = read_original_instruction(parent)
            if original.state != "recorded" or original.text != context.original_message:
                raise ToolRefused("The complete authenticated request is not the tool's input.")
            inventory = owner.build(parent, matter)
            thread_id = args["thread_id"]
            if type(thread_id) is not str or not thread_id.strip() or len(thread_id) > 100:
                raise ToolRefused("The target is a bounded exact dispute identity.")
            thread_ref, facts, observations = _population(inventory, thread_id)
            sources = []
            for reference in inventory.references.values():
                if reference["reference"]["kind"] == ReferenceKind.SOURCE.value:
                    value = reference["value"]
                    if value["generation"] != source_generation:
                        raise ToolRefused(
                            "A working source belongs to another admitted generation."
                        )
                    sources.append(reference)
            return matter, inventory, thread_ref, facts, observations, sources
        except (ReviewRefused, KeyError, TypeError, ValueError) as exc:
            raise ToolRefused(
                "The complete current working input cannot be reconstructed."
            ) from exc

    def envelope(name, args, inventory, data, *, reason=_LIMIT):
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False)) > MAX_INVENTORY_CHARACTERS:
            raise ToolRefused("The complete conditional input/result exceeds its owned ceiling.")
        return ToolEnvelope(
            name,
            VERSION,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS,
            Availability.PARTIAL,
            Assessment.NOT_ASSESSED,
            {
                "inputs": args,
                "method": "nm.Archives.legal_brain.procedure.limitation.unique_period_in + run_period",
                "source_generation": source_generation,
                "input_receipts": [
                    {
                        "kind": "current_working_inventory",
                        "inventory_identity": inventory.identity,
                        "file_snapshot": inventory.payload["file_snapshot"],
                    }
                ],
            },
            data,
            reason,
        )

    def recheck(args, context, name, initial):
        latest = current(args, context, name)
        if not same_json_value(
            neutral(asdict(latest[0])), neutral(asdict(initial[0]))
        ) or not same_json_value(latest[1].payload, initial[1].payload):
            raise ToolRefused("The actual scoped file or working sources moved during arithmetic.")

    from nm.Archives.legal_brain.procedure.tool_compute_procedural_period import (
        build_tool as compute_procedural_period_tool,
    )
    from nm.Archives.legal_brain.procedure.tool_read_procedural_calculation_inputs import (
        build_tool as read_procedural_calculation_inputs_tool,
    )

    return (
        read_procedural_calculation_inputs_tool(
            current=current, recheck=recheck, envelope=envelope
        ),
        compute_procedural_period_tool(
            current=current, recheck=recheck, envelope=envelope, source_generation=source_generation
        ),
    )
