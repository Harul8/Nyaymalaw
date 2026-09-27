"""The resolve_citation model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION, _source
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.retrieve.search_port import ResolutionState
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version, source_unavailable) -> RegisteredTool:
    def resolve(args, _context):
        if search is None:
            return source_unavailable("resolve_citation")
        result = search.resolve(args["citation"])
        return _source(
            "resolve_citation",
            "exact reporter identity index",
            source_version,
            (result.case_id,) if result.case_id else (),
            asdict(result) if result.state is ResolutionState.RESOLVED else {},
            available=result.state is not ResolutionState.INDEX_UNAVAILABLE,
            assessed=result.state is ResolutionState.RESOLVED,
            reason=result.why
            or (
                "Exact identity is not a semantic/legal support assessment."
                if result.state is not ResolutionState.RESOLVED
                else ""
            ),
        )

    return RegisteredTool(
        ToolDefinition(
            "resolve_citation",
            "Resolve only an exact reporter key; never offer a guessed case.",
            object_schema({"citation": _STRING}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        resolve,
    )
