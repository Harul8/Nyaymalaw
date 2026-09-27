"""The read_facts model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.tool_catalogue import _CONTROLS, VERSION
from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, matter_result) -> RegisteredTool:
    def read_facts(_args, context):
        matter = file_of(context)
        return matter_result(
            "read_facts", matter, {"facts": [asdict(fact) for fact in matter.facts]}
        )

    return RegisteredTool(
        ToolDefinition(
            "read_facts",
            "Read recorded facts with their actual words and status.",
            object_schema({}),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        read_facts,
    )
