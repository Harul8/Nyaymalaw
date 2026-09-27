"""The ask_advocate model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import (
    _STRING,
    OfferRole,
    RegisteredTool,
    ToolKind,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, terminal, version) -> RegisteredTool:
    def ask_advocate(args, context):
        return terminal("ask_advocate", args, context)

    return RegisteredTool(
        ToolDefinition(
            "ask_advocate",
            "Propose the necessary question; checks still precede delivery.",
            object_schema({"question": _STRING}),
        ),
        ToolKind.CONTROL,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        ask_advocate,
        offer_role=OfferRole.INITIAL,
    )
