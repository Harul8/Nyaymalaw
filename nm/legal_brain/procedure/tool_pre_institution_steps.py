"""The pre_institution_steps model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.common.curation_contracts import Curation
from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _NULLABLE_DATE, VERSION, _enum
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.institution_port import Against
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.matter_contracts import CauseOfAction


def build_tool(*, tables, table_unavailable, table_result, read_primary) -> RegisteredTool:
    def pre_institution(args, _context):
        if tables is None or tables.institution is None:
            return table_unavailable("pre_institution_steps")
        cause, against = CauseOfAction(args["cause"]), Against(args["against"])
        curation = tables.institution.coverage(cause)
        if curation is not Curation.CURATED:
            return table_result("pre_institution_steps", curation, [])
        engaged = tables.institution.engaged(cause, against)
        undecided = tables.institution.undecided(cause, against)
        guide = [{**asdict(row.condition), "engagement": row.why} for row in engaged]
        guide += [
            {**asdict(row), "engagement": "The opponent status is not established."}
            for row in undecided
        ]
        return table_result(
            "pre_institution_steps",
            curation,
            guide,
            [read_primary(row["act"], row["provision"], args["as_of"]) for row in guide],
        )

    return RegisteredTool(
        ToolDefinition(
            "pre_institution_steps",
            "Read curated conditions and their primary provisions.",
            object_schema(
                {"cause": _enum(CauseOfAction), "against": _enum(Against), "as_of": _NULLABLE_DATE}
            ),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        pre_institution,
    )
