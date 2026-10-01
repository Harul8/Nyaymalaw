"""The read_working_inventory model-facing door over its existing native owners."""

from __future__ import annotations

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.Archives.legal_brain.reason.working_record import _CONTROLS, READ_TOOL, VERSION
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, owner) -> RegisteredTool:
    def read(_args, context):
        try:
            matter, parent = current(context)
            inventory = owner.build(parent, matter)
            return envelope(
                READ_TOOL,
                inventory,
                context,
                {"inventory_identity": inventory.identity, "inventory": inventory.payload},
            )
        except ReviewRefused as exc:
            raise ToolRefused(str(exc)) from exc

    return RegisteredTool(
        ToolDefinition(
            READ_TOOL,
            "Read exact current private work, needs and "
            "source/fact identities. Execution is not law or established fact.",
            object_schema({}),
        ),
        ToolKind.CONTROL,
        VERSION,
        True,
        _CONTROLS,
        read,
    )
