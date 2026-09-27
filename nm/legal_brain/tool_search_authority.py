"""The search_authority model-facing door over its existing native owners."""

from __future__ import annotations

from datetime import date

from nm.legal_brain.evidence_port import EvidenceNeed
from nm.legal_brain.tools import _STRING, OfferRole, RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, evidence, source_result, version) -> RegisteredTool:
    def authority(args, _context):
        return source_result(
            "search_authority",
            evidence.fetch(
                EvidenceNeed(
                    question=args["query"],
                    governing_date=date.fromisoformat(args["as_of"]),
                    jurisdiction=args["jurisdiction"],
                    want_authority=True,
                )
            ),
        )

    return RegisteredTool(
        ToolDefinition(
            "search_authority",
            "Search relevant authority; ranking is not exact identity.",
            object_schema({"query": _STRING, "as_of": _STRING, "jurisdiction": _STRING}),
        ),
        ToolKind.SOURCE,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        authority,
        offer_role=OfferRole.OPTIONAL,
    )
