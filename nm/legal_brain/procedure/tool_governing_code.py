"""The governing_code model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import (
    _CONTROLS,
    _NULLABLE_DATE,
    VERSION,
    _date,
    _enum,
)
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.governing_law_port import Limb, Pending
from nm.shared.model_port import ToolDefinition


def build_tool(*, tables, table_unavailable, table_result) -> RegisteredTool:
    def governing(args, _context):
        if tables is None or tables.governing is None:
            return table_unavailable("governing_code")
        limb = Limb(args["limb"])
        curation = tables.governing.coverage(limb)
        result = tables.governing.governing(
            limb, _date(args["on"]) if args["on"] else None, Pending(args["pending"])
        )
        guide = (
            [{**asdict(result), "curated_from": result.rule.curated_from}]
            if result.rule is not None
            else []
        )
        return table_result("governing_code", curation, guide)

    return RegisteredTool(
        ToolDefinition(
            "governing_code",
            "Consult the existing succession owner; unknown premises stay unknown.",
            object_schema({"limb": _enum(Limb), "on": _NULLABLE_DATE, "pending": _enum(Pending)}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        governing,
    )
