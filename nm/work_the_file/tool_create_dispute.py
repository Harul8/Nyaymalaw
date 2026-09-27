"""The create_dispute door; the native file mutation owner remains shared."""

from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def create_dispute(args, context):
        return prepare("create_dispute", args, context)

    return RegisteredTool(
        ToolDefinition(
            "create_dispute",
            "Record a new source-bound unassessed dispute, including the first "
            "on an empty file. Inspect existing disputes first; similar labels or parties "
            "never establish that two disputes are one. This assigns no party or legal position.",
            object_schema({"label": _STRING, "quoted": _STRING}),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        create_dispute,
        required_act=Act.RECORD,
    )
