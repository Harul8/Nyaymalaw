"""The propose_action door over the native preparation-only drafting-content owner."""

from nm.act.action_proposal_tool import SCHEMA, VERSION
from nm.legal_brain.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition


def build_tool(*, prepare) -> RegisteredTool:
    def propose_action(args, context):
        return prepare(args, context)

    return RegisteredTool(
        ToolDefinition(
            "propose_action",
            "Prepare a consequential-action proposal using an exact existing owned "
            "drafting package. "
            "The digest comes from that package. An optional destination is quoted "
            "from the current "
            "instruction; otherwise it remains absent. Never approve, send, file, settle, "
            "record arrival "
            "or invent authority. Only whole-file scope is supported.",
            SCHEMA,
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        ("test_conversational_action_preparation_uses_actual_draft_and_never_approves",),
        propose_action,
        required_act=Act.RECORD,
    )
