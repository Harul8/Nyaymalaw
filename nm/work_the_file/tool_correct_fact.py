"""The correct_fact door; prior words and native dependency checks stay owned."""

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def correct_fact(args, context):
        return prepare("correct_fact", args, context)

    return RegisteredTool(
        ToolDefinition(
            "correct_fact",
            "Propose an explicit correction to an exact current file entry, "
            "preserving the earlier words and reopening dependent work.",
            object_schema({"old_fact_id": _STRING, "quoted": _STRING}),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        correct_fact,
        required_act=Act.RECORD,
    )
