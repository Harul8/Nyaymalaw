"""The propose_source_calendar door over exact, unadjusted native calendar candidates."""

from nm.legal_brain.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.deadline_proposals import _CONTROLS, CALENDAR, SCHEMAS, VERSION


def build_tool(*, run) -> RegisteredTool:
    def propose_source_calendar(args, context):
        return run("propose_source_calendar", args, context)

    return RegisteredTool(
        ToolDefinition(
            "propose_source_calendar",
            "Record a private calendar candidate from exact current source/court clauses and "
            "verbatim full ISO dates. Never invent closures, weekdays, holidays, "
            "complete population "
            "or legal effect; no date adjustment or established deadline.",
            SCHEMAS[CALENDAR],
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        propose_source_calendar,
        required_act=Act.RECORD,
    )
