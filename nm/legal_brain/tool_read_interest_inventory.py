"""The read_interest_inventory model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.interest_calculation_contracts import InterestNotAssessed
from nm.legal_brain.reviewed_interest_selection import _TEXT, READ, VERSION
from nm.legal_brain.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, owner, controls) -> RegisteredTool:
    def read(args, context):
        matter, parent = current(context)
        try:
            return envelope(READ, context, owner.inventory(parent, matter, args["thread_id"]))
        except (ReviewRefused, InterestNotAssessed, ValueError) as exc:
            raise ToolRefused(str(exc)) from exc

    return RegisteredTool(
        ToolDefinition(
            READ,
            "Read the entire current scoped interest input population.",
            object_schema({"thread_id": _TEXT}),
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        controls,
        read,
    )
