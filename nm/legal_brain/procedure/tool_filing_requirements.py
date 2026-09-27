"""The filing_requirements model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, VERSION, _enum, _source
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.filing_requirement_port import Requirement
from nm.shared.model_port import ToolDefinition


def build_tool(*, tables, table_unavailable) -> RegisteredTool:
    def filing(args, _context):
        if tables is None or tables.filing is None:
            return table_unavailable("filing_requirements")
        requirement = Requirement(args["requirement"])
        readiness = tables.filing.readiness(requirement)
        # Readiness is itself an answer about availability, not the fee/forum.
        return _source(
            "filing_requirements",
            "versioned filing-source readiness",
            tables.version,
            (f"filing-requirement:{requirement.value}",),
            asdict(readiness),
            partial=not readiness.computable,
            reason=readiness.why
            or "Source readiness alone does not calculate a filing requirement.",
        )

    return RegisteredTool(
        ToolDefinition(
            "filing_requirements",
            "Measure whether the specific forum/valuation/fee source is held.",
            object_schema({"requirement": _enum(Requirement)}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        filing,
    )
