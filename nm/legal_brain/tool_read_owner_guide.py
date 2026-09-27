"""The read_owner_guide model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.tool_discovery import VERSION
from nm.legal_brain.tools import OfferRole, RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, registry_for, envelope, principles) -> RegisteredTool:
    def guide(args, context):
        registry = registry_for(context)
        snapshot = principles.load()
        if (
            snapshot.version != context.identity.principles_version
            or args["expected_version"] != snapshot.version
        ):
            raise ToolRefused(
                "The owner guide changed; it cannot replace the admitted instructions."
            )
        return envelope(
            "read_owner_guide",
            context,
            registry,
            {
                "guide_version": snapshot.version,
                "text": snapshot.text,
                "trust": "owner_guidance_not_permission_or_legal_authority",
            },
        )

    return RegisteredTool(
        ToolDefinition(
            "read_owner_guide",
            "Read the admitted owner guide, not law or action authority.",
            object_schema({"expected_version": {"type": "string", "minLength": 1}}),
        ),
        ToolKind.CONTROL,
        VERSION,
        True,
        ("test_discovery_is_the_actual_registry_not_a_second_catalogue",),
        guide,
        offer_role=OfferRole.INITIAL,
    )
