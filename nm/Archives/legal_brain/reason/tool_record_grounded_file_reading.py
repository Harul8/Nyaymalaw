"""The record_grounded_file_reading model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

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
from nm.Archives.legal_brain.reason.grounded_file_tools import (
    _CONTROLS,
    _STRING,
    VERSION,
    GroundedReadingMutation,
    _derive,
)
from nm.Archives.legal_brain.understand import parties, posture
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.file_mutation_contracts import neutral


def build_tool(*, store, today) -> RegisteredTool:
    def read(args, context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
            or args["thread_id"] not in context.issue_ids
            or not context.original_message.strip()
        ):
            raise ToolRefused("The file reading needs the authenticated current selected file.")
        proposal = {name: args[name] for name in ("events", "posture", "parties")}
        try:
            reference = today()
            after, detail = _derive(
                matter,
                thread_id=args["thread_id"],
                fact_id=args["fact_id"],
                turn_id=context.identity.turn_id,
                reference=reference,
                proposal=proposal,
            )
            if after == matter:
                return ToolEnvelope(
                    "record_grounded_file_reading",
                    VERSION,
                    ToolKind.MATTER,
                    ToolOutcome.RESULTS,
                    Availability.PARTIAL,
                    Assessment.NOT_ASSESSED,
                    {
                        "matter_id": matter.id,
                        "matter_version": matter.version,
                        "snapshot": digest(neutral(asdict(matter))),
                    },
                    detail,
                    "No new field was established; the proposed readings remain unconfirmed.",
                )
            mutation = GroundedReadingMutation(
                matter,
                after,
                matter.advocate_id,
                args["thread_id"],
                args["fact_id"],
                context.identity.turn_id,
                reference,
                proposal,
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ToolRefused(str(exc)) from exc
        envelope = ToolEnvelope(
            "record_grounded_file_reading",
            VERSION,
            ToolKind.MATTER,
            ToolOutcome.RESULTS,
            Availability.PARTIAL,
            Assessment.NOT_ASSESSED,
            {
                "matter_id": matter.id,
                "matter_version": matter.version,
                "snapshot": mutation.identity,
            },
            detail,
            "These source-bound interpretations are not human-confirmed facts, party "
            "directions or established legal applicability. No deadline was computed.",
        )
        return PreparedToolResult(envelope, mutation)

    properties = {
        "thread_id": _STRING,
        "fact_id": _STRING,
        "events": {
            "type": "array",
            "maxItems": 40,
            "items": object_schema({"event_quote": _STRING, "date_expression": {"type": "string"}}),
        },
        "posture": {
            key: value for key, value in posture.POSTURE_SCHEMA.items() if key != "x-nm-read"
        },
        "parties": {
            key: value for key, value in parties.PARTIES_SCHEMA.items() if key != "x-nm-read"
        },
    }

    return RegisteredTool(
        ToolDefinition(
            "record_grounded_file_reading",
            "Read the date, representation and named parties from an exact current scoped "
            "advocate account using the existing owners. Preserve allegations, uncertainty "
            "and the whole original account. A quoted fragment is not proof; no human "
            "confirmation, governing cause, party direction or deadline is inferred.",
            object_schema(properties),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        read,
        required_act=Act.RECORD,
    )
