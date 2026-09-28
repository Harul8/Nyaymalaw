"""The record_requirements model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict, replace

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.orchestrate.tools import (
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
from nm.legal_brain.reason import requirements
from nm.legal_brain.reason.requirements_contracts import Requirement, applicability_identity
from nm.legal_brain.reason.source_writes import (
    _ROW,
    _STRING,
    VERSION,
    SourceRequirementMutation,
    _parent,
    _reading,
)
from nm.legal_brain.retrieve.tool_sources import findings_from_record
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.file_mutation_contracts import neutral


def build_tool(*, store, source_version) -> RegisteredTool:
    def record(args, context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
            or args["thread_id"] not in context.issue_ids
        ):
            raise ToolRefused("The source write needs its current owned and selected dispute.")
        parent = _parent(matter, context.identity.turn_id, context.identity.advocate_id)
        try:
            captured = findings_from_record(parent, source_version=source_version)
            old = next(row for row in matter.threads if row.id == args["thread_id"])
            context_identity = applicability_identity(old, matter.facts)
            reading = _reading(args["requirements"], captured,
                               context_identity=context_identity)
            if any(Requirement.restore(row) is None for row in old.requirements):
                raise ValueError("The earlier checklist is unreadable, not empty.")
            merged = requirements.merge(old.requirements, reading)
            new = replace(
                old,
                requirements=merged,
                requirement_reads={
                    **old.requirement_reads,
                    **{row.locator: row.source_identity for row in reading.requirements},
                },
                requirement_read_contexts={
                    **old.requirement_read_contexts,
                    **{row.locator: context_identity for row in reading.requirements},
                },
            )
            if neutral(asdict(new)) == neutral(asdict(old)):
                return ToolEnvelope(
                    "record_requirements",
                    VERSION,
                    ToolKind.MATTER,
                    ToolOutcome.NO_RESULTS,
                    Availability.AVAILABLE,
                    Assessment.NOT_ASSESSED,
                    {
                        "matter_id": matter.id,
                        "matter_version": matter.version,
                        "source_version": source_version,
                        "snapshot": digest(neutral(asdict(matter))),
                    },
                    {},
                    "The captured requirements are already recorded; no checklist was erased.",
                )
            after = replace(
                matter, threads=tuple(new if row.id == old.id else row for row in matter.threads)
            )
            mutation = SourceRequirementMutation(
                matter,
                after,
                matter.advocate_id,
                old.id,
                context.identity.turn_id,
                source_version,
                reading.requirements,
            )
        except (ValueError, StopIteration) as exc:
            raise ToolRefused(str(exc)) from exc
        return PreparedToolResult(
            ToolEnvelope(
                "record_requirements",
                VERSION,
                ToolKind.MATTER,
                ToolOutcome.RESULTS,
                Availability.AVAILABLE,
                Assessment.NOT_ASSESSED,
                {
                    "matter_id": matter.id,
                    "matter_version": matter.version,
                    "snapshot": mutation.identity,
                    "source_version": source_version,
                },
                {
                    "thread_id": old.id,
                    "requirements": neutral([asdict(row) for row in reading.requirements]),
                    "states_derived": True,
                    "facts_established": False,
                    "legal_interpretation": "not_assessed",
                },
                "Exact retrieved clauses support a checklist proposal; applicability and necessity "
                "still require independent review. No advocate answer or assessment was certified.",
            ),
            mutation,
        )

    definition = ToolDefinition(
        "record_requirements",
        "Record applicable checklist proposals "
        "from exact law already retrieved in this turn for a selected dispute. Preserve prior "
        "requirements. Required versus strengthening is a tentative source-bound interpretation, "
        "not a legal certification. This tool cannot mark held/promised/unavailable or reviewed.",
        object_schema(
            {
                "thread_id": _STRING,
                "requirements": {"type": "array", "minItems": 1, "maxItems": 100, "items": _ROW},
            }
        ),
    )

    return RegisteredTool(
        definition,
        ToolKind.MATTER,
        VERSION,
        False,
        (
            "test_requirements_use_the_actual_parent_read_and_shared_merge",
            "test_requirement_proposals_cannot_certify_answers_or_delete_prior_work",
        ),
        record,
        required_act=Act.RECORD,
    )
