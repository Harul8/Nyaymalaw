"""The propose_legal_premise door; exact proposal checks stay in the native owner."""

from nm.legal_brain.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.private_file_tools import _CONTROLS, PREMISE, SCHEMAS, VERSION


def build_tool(*, run) -> RegisteredTool:
    def propose_legal_premise(args, context):
        return run("propose_legal_premise", args, context)

    return RegisteredTool(
        ToolDefinition(
            "propose_legal_premise",
            "Propose an inferred private legal premise from actual primary clauses and scoped "
            "observations. Never state advocate instruction or establish law. Exact replacement "
            "identity is required; independent release remains with the existing reviewers.",
            SCHEMAS[PREMISE],
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        propose_legal_premise,
        required_act=Act.RECORD,
    )
