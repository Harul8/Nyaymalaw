"""The propose_source_deadline door; all chronology/currentness checks remain native."""

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.deadline_proposals import _CONTROLS, DEADLINE, SCHEMAS, VERSION


def build_tool(*, run) -> RegisteredTool:
    def propose_source_deadline(args, context):
        return run("propose_source_deadline", args, context)

    return RegisteredTool(
        ToolDefinition(
            "propose_source_deadline",
            "Append a private source-backed conditional deadline from exact working clauses "
            "and one explicit attributed observation, retaining every competing event and old row. "
            "No on-date, legal selection, accepted task or calendar adjustment is established.",
            SCHEMAS[DEADLINE],
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        propose_source_deadline,
        required_act=Act.RECORD,
    )
