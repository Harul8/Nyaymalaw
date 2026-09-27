"""The withdraw_private_premise door over the single preserved-history mutation owner."""

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.private_file_tools import _CONTROLS, SCHEMAS, VERSION, WITHDRAW


def build_tool(*, run) -> RegisteredTool:
    def withdraw_private_premise(args, context):
        return run("withdraw_private_premise", args, context)

    return RegisteredTool(
        ToolDefinition(
            "withdraw_private_premise",
            "Withdraw only an exact current inferred private premise using exact supplied "
            "correction words. Preserve the original statement/source/alternatives as an "
            "unestablished tombstone and the full prior projection in the immutable journal. "
            "This does not withdraw human decisions, advice acceptance or action permissions.",
            SCHEMAS[WITHDRAW],
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        withdraw_private_premise,
        required_act=Act.RECORD,
    )
