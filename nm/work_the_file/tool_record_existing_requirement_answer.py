"""The record_existing_requirement_answer door; supplied-fact authority stays native."""

from nm.legal_brain.requirements_contracts import State
from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def record_existing_requirement_answer(args, context):
        return prepare("record_existing_requirement_answer", args, context)

    return RegisteredTool(
        ToolDefinition(
            "record_existing_requirement_answer",
            "Apply or revalidate information already "
            "supplied in an exact current scoped advocate assertion against an existing "
            "requirement. Preserve its attribution, uncertainty and history; do not ask "
            "again merely because law was newly read. An old promise has no new date anchor.",
            object_schema(
                {
                    "thread_id": _STRING,
                    "requirement_key": _STRING,
                    "fact_id": _STRING,
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
        record_existing_requirement_answer,
        required_act=Act.RECORD,
    )
