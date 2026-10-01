"""The add_issue door; source-bound native questions are not certified answers."""

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.Archives.legal_brain.reason.issue_contracts import IssueKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.matter_contracts import Side
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def add_issue(args, context):
        return prepare("add_issue", args, context)

    return RegisteredTool(
        ToolDefinition(
            "add_issue",
            "Record a question supported by the current advocate words, "
            "without deleting standing questions or certifying its answer.",
            object_schema(
                {
                    "thread_id": _STRING,
                    "statement": _STRING,
                    "kind": {"type": "string", "enum": [k.value for k in IssueKind]},
                    "runs_against": {"type": "string", "enum": [s.value for s in Side]},
                    "quoted": _STRING,
                }
            ),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        add_issue,
        required_act=Act.RECORD,
    )
