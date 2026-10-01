"""The read_private_file_inputs door over current source and private-file owners."""

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.private_file_tools import _CONTROLS, READ, SCHEMAS, VERSION


def build_tool(*, run) -> RegisteredTool:
    def read_private_file_inputs(args, context):
        return run("read_private_file_inputs", args, context)

    return RegisteredTool(
        ToolDefinition(
            "read_private_file_inputs",
            "Read exact current primary clauses, scoped observations and private "
            "object fingerprints.",
            SCHEMAS[READ],
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        read_private_file_inputs,
        required_act=Act.READ,
    )
