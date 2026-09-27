"""The read_fee_inventory model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.legal_brain.procedure.fee_calculation_contracts import FeeNotAssessed
from nm.legal_brain.procedure.reviewed_fee_selection import _TEXT, READ, VERSION
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.model_port import SchemaViolation, ToolDefinition


def build_tool(*, current, envelope, owner, controls) -> RegisteredTool:
    def read(args, context):
        matter, parent = current(context)
        try:
            data = owner.inventory(parent, matter, args["thread_id"])
            again, latest = current(context)
            if owner.inventory(latest, again, args["thread_id"]) != data:
                raise ReviewRefused("The fee inventory changed during reading")
            return envelope(READ, context, data)
        except (ReviewRefused, FeeNotAssessed, SchemaViolation) as exc:
            raise ToolRefused(str(exc)) from exc

    return RegisteredTool(
        ToolDefinition(
            READ,
            "Read the entire current scoped fee source/input population; no installed tariff.",
            object_schema({"thread_id": _TEXT}),
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        controls,
        read,
    )
