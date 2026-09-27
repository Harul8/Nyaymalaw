"""The read_turn model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, matter_result) -> RegisteredTool:
    def read_turn(args, context):
        matter = file_of(context)
        receipt = next(
            (row for row in matter.turn_receipts if row.turn_id == args["turn_id"]), None
        )
        if receipt is None:
            return matter_result("read_turn", matter, {}, found=False)
        receipt.validated_answer()
        return matter_result("read_turn", matter, asdict(receipt))

    return RegisteredTool(
        ToolDefinition(
            "read_turn",
            "Read an exact committed turn after compaction, not an unserved draft.",
            object_schema({"turn_id": _STRING}),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        read_turn,
    )
