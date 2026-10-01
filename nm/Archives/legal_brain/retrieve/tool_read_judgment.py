"""The read_judgment model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _LIMIT, _STRING, VERSION, _source
from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
from nm.Archives.legal_brain.retrieve.tool_sources import capture_paragraph, combine_captures
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version, source_unavailable) -> RegisteredTool:
    def judgment(args, _context):
        if search is None:
            return source_unavailable("read_judgment")
        result = search.expand(
            args["case_id"], query=args["query"], limit=args["limit"], after=args["after"]
        )
        return _source(
            "read_judgment",
            result.index,
            source_version,
            [row.locator for row in result.paragraphs],
            asdict(result) if result.paragraphs else {},
            available=result.coverage is not Coverage.NOT_ASSESSED,
            partial=result.complete is not True or result.next_after is not None,
            capture=combine_captures(
                *(
                    capture_paragraph(
                        row,
                        index=result.index,
                        source_version=(
                            result.identity.corpus_version if result.identity else source_version
                        ),
                    )
                    for row in result.paragraphs
                )
            ),
            reason=result.why or "This is an indexed paragraph window, not verified legal support.",
        )

    return RegisteredTool(
        ToolDefinition(
            "read_judgment",
            "Read a bounded index window, showing continuation and exclusions.",
            object_schema(
                {
                    "case_id": _STRING,
                    "query": {"type": ["string", "null"]},
                    "limit": _LIMIT,
                    "after": {"type": ["string", "null"]},
                }
            ),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        judgment,
    )
