"""The research model-facing door over the native bounded dispatcher."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}


def build_tool(*, dispatcher, policy) -> RegisteredTool:
    def run(args, context):
        return dispatcher.run("research", args, context)

    return RegisteredTool(
        ToolDefinition(
            "research",
            "Delegate a bounded source-reading task with fresh checked case data, not this "
            "conversation's conclusions. Findings still need independent review.",
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
