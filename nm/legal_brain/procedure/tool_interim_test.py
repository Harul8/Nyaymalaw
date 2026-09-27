"""The interim_test model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.common.curation_contracts import Curation
from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, VERSION, _enum
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.interim_relief_port import InterimRelief
from nm.shared.model_port import ToolDefinition


def build_tool(*, tables, table_unavailable, table_result) -> RegisteredTool:
    def interim(args, _context):
        if tables is None or tables.interim is None:
            return table_unavailable("interim_test")
        relief = InterimRelief(args["relief"])
        curation = tables.interim.coverage(relief)
        test = tables.interim.test_for(relief) if curation is Curation.CURATED else None
        return table_result("interim_test", curation, [asdict(test)] if test else [])

    return RegisteredTool(
        ToolDefinition(
            "interim_test",
            "Read the exact curated relief test; an uncurated relief is not borrowed.",
            object_schema({"relief": _enum(InterimRelief)}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        interim,
    )
