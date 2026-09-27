"""The submit_answer model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import (
    ANSWER_PROPOSAL_SHAPE,
    OfferRole,
    RegisteredTool,
    ToolKind,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, terminal, version) -> RegisteredTool:
    def submit_answer(args, context):
        return terminal("submit_answer", args, context)

    return RegisteredTool(
        ToolDefinition(
            "submit_answer",
            "Propose exact response paragraphs as evidence packages. Each text "
            "is final wording, with exact retrieved quotes, recorded premise IDs, contrary "
            "material and dependencies. Use empty arrays only when genuinely inapplicable. "
            "No unreferenced answer text is delivered; this does not release advice.",
            object_schema(ANSWER_PROPOSAL_SHAPE["properties"]),
        ),
        ToolKind.CONTROL,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        submit_answer,
        offer_role=OfferRole.INITIAL,
    )
