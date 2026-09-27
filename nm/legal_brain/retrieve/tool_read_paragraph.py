"""The read_paragraph model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION, _source
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.retrieve.search_port import ResolutionState
from nm.legal_brain.retrieve.tool_sources import capture_paragraph
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version, source_unavailable) -> RegisteredTool:
    def paragraph(args, _context):
        if search is None:
            return source_unavailable("read_paragraph")
        result = search.passage(args["locator"])
        return _source(
            "read_paragraph",
            "exact authority paragraph reader",
            source_version,
            (result.paragraph.locator,) if result.paragraph else (),
            asdict(result) if result.paragraph else {},
            available=result.state is not ResolutionState.INDEX_UNAVAILABLE,
            capture=capture_paragraph(
                result.paragraph,
                index="exact authority paragraph reader",
                source_version=source_version,
            )
            if result.paragraph
            else None,
            reason=result.why or "The passage is read, but legal support has not been assessed.",
        )

    return RegisteredTool(
        ToolDefinition(
            "read_paragraph",
            "Read a paragraph by exact locator, preserving its attribution.",
            object_schema({"locator": _STRING}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        paragraph,
    )
