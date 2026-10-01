"""The oppose_full model-facing door over the native bounded dispatcher."""

from __future__ import annotations

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}


def build_tool(*, dispatcher, policy) -> RegisteredTool:
    def run(args, context):
        return dispatcher.run("oppose_full", args, context)

    return RegisteredTool(
        ToolDefinition(
            "oppose_full",
            "Privately test one dispute's strongest contrary case, supported reply or explicit "
            "absence of one with a course, and judicial vulnerabilities. The key-details "
            "readiness threshold is not adopted: this cannot complete merits.",
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
