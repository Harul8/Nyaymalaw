"""The oppose model-facing door over the native bounded dispatcher."""

from __future__ import annotations

from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}


def build_tool(*, dispatcher, policy) -> RegisteredTool:
    def run(args, context):
        return dispatcher.run("oppose", args, context)

    return RegisteredTool(
        ToolDefinition(
            "oppose",
            "Test the supported case critically: strongest source-grounded contrary arguments, "
            "unresolved premises and judicial questions. Never invent what an opponent or judge "
            "will do. These are tentative observations, not facts.",
            object_schema({"question": _STRING, "issue_ids": _STRINGS}),
        ),
        ToolKind.SOURCE,
        "nested-research-v1",
        False,
        (
            "test_real_parent_dispatch_shares_spend_and_never_creates_a_second_writer",
            "test_a_child_cannot_inherit_write_or_terminal_aliases",
        ),
        run,
        delegation=policy,
    )
