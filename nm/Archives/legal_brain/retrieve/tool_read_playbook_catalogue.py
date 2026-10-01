"""The read_playbook_catalogue model-facing door over its existing native owners."""

from __future__ import annotations

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, snapshot, controls) -> RegisteredTool:
    def catalogue(_args, context):
        current()
        return envelope(
            "read_playbook_catalogue",
            {"population": len(snapshot.catalogue), "playbooks": list(snapshot.catalogue)},
            context,
        )

    return RegisteredTool(
        ToolDefinition(
            "read_playbook_catalogue",
            "Read the admitted owner navigation catalogue; it is not case routing or law.",
            object_schema({}),
        ),
        ToolKind.CONTROL,
        snapshot.version,
        True,
        controls,
        catalogue,
    )
