"""The inspect_tool model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_discovery import VERSION
from nm.legal_brain.orchestrate.tools import (
    OfferRole,
    RegisteredTool,
    ToolKind,
    ToolRefused,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, registry_for, envelope) -> RegisteredTool:
    def inspect(args, context):
        registry = registry_for(context)
        rows = [row for row in registry.definitions if row.name == args["name"]]
        if len(rows) != 1:
            raise ToolRefused("That exact tool is not registered; no capability was inferred.")
        return envelope(
            "inspect_tool",
            context,
            registry,
            {
                "definition": asdict(rows[0]),
                "required_act": registry.authority_for(rows[0].name).value,
            },
        )

    return RegisteredTool(
        ToolDefinition(
            "inspect_tool",
            "Read the exact schema of a registered tool; no guessed alias.",
            object_schema({"name": {"type": "string", "minLength": 1}}),
        ),
        ToolKind.CONTROL,
        VERSION,
        True,
        ("test_discovery_is_the_actual_registry_not_a_second_catalogue",),
        inspect,
        offer_role=OfferRole.SCHEMA_LOADER,
    )
