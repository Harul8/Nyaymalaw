"""The read_limitation_candidates model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.reviewed_limitation_selection import _TEXT, VERSION, selection_inventory
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, store, source_generation, source_current) -> RegisteredTool:
    def inventory(args, context):
        matter, thread = file_of(context, args["thread_id"])
        try:
            data = selection_inventory(
                matter, thread, source_generation=source_generation, source_current=source_current
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ToolRefused(str(exc)) from exc
        if store.load(matter.id) != matter:
            raise ToolRefused("The file moved during the selection inventory")
        return ToolEnvelope(
            "read_limitation_candidates",
            VERSION,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "inputs": args,
                "method": "recorded event and captured primary-source inventory",
                "input_receipts": [{"matter_id": matter.id, "snapshot": data["snapshot_id"]}],
            },
            data,
            "These are recorded source observations and candidate legal reads, not findings.",
        )

    return RegisteredTool(
        ToolDefinition(
            "read_limitation_candidates",
            "Read exact recorded event and current captured legal "
            "source identities. No Article or legal trigger is selected by this inventory.",
            object_schema({"thread_id": _TEXT}),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        True,
        (
            "test_unreviewed_event_selection_cannot_supply_calculation_inputs",
            "test_event_selection_requires_full_current_chronology_and_exact_primary_spans",
        ),
        inventory,
    )
