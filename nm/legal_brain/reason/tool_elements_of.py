"""The elements_of model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.common.curation_contracts import Curation
from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, VERSION, _enum
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.matter_contracts import CauseOfAction


def build_tool(*, tables, table_unavailable, table_result) -> RegisteredTool:
    def elements(args, _context):
        if tables is None or tables.elements is None:
            return table_unavailable("elements_of")
        cause = CauseOfAction(args["cause"])
        curation = tables.elements.coverage(cause)
        result = tables.elements.elements_for(cause) if curation is Curation.CURATED else None
        return table_result("elements_of", curation, [asdict(result)] if result else [])

    return RegisteredTool(
        ToolDefinition(
            "elements_of",
            "Read the curated element list and source, not remembered elements.",
            object_schema({"cause": _enum(CauseOfAction)}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        elements,
    )
