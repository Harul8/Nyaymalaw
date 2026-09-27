"""The procedural_periods model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.common.curation_contracts import Curation
from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _NULLABLE_DATE, VERSION, _enum
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.procedural_period_port import Track
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.matter_contracts import Role


def build_tool(*, tables, table_unavailable, table_result, read_primary) -> RegisteredTool:
    def procedural(args, _context):
        if tables is None or tables.procedural is None:
            return table_unavailable("procedural_periods")
        role, track = Role(args["role"]), Track(args["track"])
        curation = tables.procedural.coverage(role)
        if curation is not Curation.CURATED:
            return table_result("procedural_periods", curation, [])
        engaged = tables.procedural.engaged(role, track)
        undecided = tables.procedural.undecided(role, track)
        guide = [{**asdict(row.period), "engagement": row.why} for row in engaged]
        guide += [
            {**asdict(row), "engagement": "The track is not established."} for row in undecided
        ]
        return table_result(
            "procedural_periods",
            curation,
            guide,
            [read_primary(row["act"], row["provision"], args["as_of"]) for row in guide],
        )

    return RegisteredTool(
        ToolDefinition(
            "procedural_periods",
            "Read curated clocks and primary text for the exact role/track.",
            object_schema({"role": _enum(Role), "track": _enum(Track), "as_of": _NULLABLE_DATE}),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        procedural,
    )
