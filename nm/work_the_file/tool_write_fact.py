"""The write_fact door over the existing attributed file mutation owner."""

from nm.legal_brain.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.write_tools import _CONTROLS, _STRING, VERSION


def build_tool(*, prepare) -> RegisteredTool:
    def write_fact(args, context):
        return prepare("write_fact", args, context)

    return RegisteredTool(
        ToolDefinition(
            "write_fact",
            "Record an exact current advocate assertion on existing disputes.",
            object_schema(
                {
                    "quoted": _STRING,
                    "thread_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "items": _STRING,
                    },
                }
            ),
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        write_fact,
        required_act=Act.RECORD,
    )
