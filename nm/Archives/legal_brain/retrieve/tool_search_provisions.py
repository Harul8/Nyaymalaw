"""Model-facing provision discovery; a ranked candidate is never legal support."""

from __future__ import annotations

from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.tool_catalogue import _CONTROLS, VERSION, _source
from nm.Archives.legal_brain.orchestrate.tools import _STRING, RegisteredTool, ToolKind, object_schema
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version) -> RegisteredTool:
    def discover(args, _context):
        if search is None:
            return _source(
                "search_provisions", "chunks.db bare_act full provision text",
                source_version, (), {}, available=False,
                reason="The held-provision search reader is not configured.",
            )
        result = search.search_provisions(args["query"], act=args["act"], limit=args["limit"])
        return _source(
            "search_provisions", result.index, result.snapshot_id or source_version,
            [row.locator for row in result.candidates],
            asdict(result) if result.candidates else {},
            available=result.coverage is not Coverage.NOT_ASSESSED,
            partial=result.coverage is not Coverage.ANSWERED,
            reason=result.why,
        )

    return RegisteredTool(
        ToolDefinition(
            "search_provisions",
            "Rank held provision wording. Results are candidates, not applicable law or "
            "legal support; read a candidate by exact Act, section and governing date.",
            object_schema({
                "query": _STRING,
                "act": {"type": ["string", "null"], "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        discover,
    )
