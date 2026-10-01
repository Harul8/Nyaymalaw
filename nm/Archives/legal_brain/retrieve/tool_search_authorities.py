"""The search_authorities model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _LIMIT, _STRING, VERSION, _source
from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version, source_unavailable) -> RegisteredTool:
    def discover(args, _context):
        if search is None:
            return source_unavailable("search_authorities")
        result = search.discover(
            args["query"],
            court=args["court"],
            from_year=args["from_year"],
            to_year=args["to_year"],
            limit=args["limit"],
        )
        return _source(
            "search_authorities",
            result.index,
            result.identity.corpus_version if result.identity is not None else source_version,
            [row.case_id for row in result.cases],
            asdict(result) if result.cases else {},
            available=result.coverage is not Coverage.NOT_ASSESSED,
            partial=result.coverage is not Coverage.ANSWERED,
            reason=result.why
            or "Ranked cases are candidates, not exact identities or legal support.",
        )

    return RegisteredTool(
        ToolDefinition(
            "search_authorities",
            "Search grouped cases; ranking is never exact case identity.",
            object_schema(
                {
                    "query": _STRING,
                    "court": {"type": ["string", "null"]},
                    "from_year": {"type": ["integer", "null"], "minimum": 1, "maximum": 9999},
                    "to_year": {"type": ["integer", "null"], "minimum": 1, "maximum": 9999},
                    "limit": _LIMIT,
                }
            ),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        discover,
    )
