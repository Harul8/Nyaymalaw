"""The treatment model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.evidence_port import TreatmentState
from nm.legal_brain.search_port import ResolutionState
from nm.legal_brain.tool_catalogue import _CONTROLS, _STRING, VERSION, _source
from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, search, source_version, source_unavailable) -> RegisteredTool:
    def treatment(args, _context):
        if search is None:
            return source_unavailable("treatment")
        identity = search.case_identity(args["case_id"])
        if identity.state is not ResolutionState.RESOLVED:
            return _source(
                "treatment",
                "case identity and citator",
                source_version,
                (),
                {},
                available=identity.state is not ResolutionState.INDEX_UNAVAILABLE,
                reason=identity.why,
            )
        result = search.treatment(args["case_id"])
        return _source(
            "treatment",
            "case identity and citator",
            source_version,
            (args["case_id"],),
            asdict(result),
            partial=result.state is TreatmentState.NOT_CHECKED,
            assessed=result.state is not TreatmentState.NOT_CHECKED,
            reason=result.scope if result.state is TreatmentState.NOT_CHECKED else "",
        )

    return RegisteredTool(
        ToolDefinition(
            "treatment",
            "Read later treatment for an exact held case, preserving unchecked scope.",
            object_schema({"case_id": _STRING}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        treatment,
    )
