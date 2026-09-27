"""The discover_tools model-facing door over its existing native owners."""

from __future__ import annotations

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
    def discover(args, context):
        registry = registry_for(context)
        query = args["query"].strip()
        if len(query) > 2000:
            raise ToolRefused("The capability search exceeds its bound.")
        words = set(query.casefold().split())
        definitions = registry.definitions
        ranked = sorted(
            definitions,
            key=lambda row: (
                -sum(word in (row.name + " " + row.description).casefold() for word in words),
                row.name,
            ),
        )
        # Ranking only. Zero overlap does not say a capability is absent.
        return envelope(
            "discover_tools",
            context,
            registry,
            {
                "registered_count": len(definitions),
                "returned_count": len(ranked),
                "tools": [
                    {
                        "name": row.name,
                        "description": row.description,
                        "required_act": registry.authority_for(row.name).value,
                    }
                    for row in ranked
                ],
                "ranking_only": True,
            },
        )

    return RegisteredTool(
        ToolDefinition(
            "discover_tools",
            "List actual registered capabilities without approving actions.",
            object_schema({"query": {"type": "string"}}),
        ),
        ToolKind.CONTROL,
        VERSION,
        True,
        ("test_discovery_is_the_actual_registry_not_a_second_catalogue",),
        discover,
        offer_role=OfferRole.INITIAL,
    )
