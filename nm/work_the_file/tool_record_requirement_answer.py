"""The record_requirement_answer door over the single native requirement writer."""

from nm.legal_brain.requirements_contracts import State
from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def record_requirement_answer(args, context):
        return prepare("record_requirement_answer", args, context)

    return RegisteredTool(
        ToolDefinition(
            "record_requirement_answer",
            "Read an advocate reply against an exact existing "
            "requirement. Held means supplied information, not proven facts.",
            object_schema(
                {
                    "thread_id": _STRING,
                    "requirement_key": _STRING,
                    "answer": {"type": "string", "enum": [s.value for s in State]},
                    "quoted": _STRING,
                    "due_expression": {"type": "string"},
                }
            ),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        record_requirement_answer,
        required_act=Act.RECORD,
    )
