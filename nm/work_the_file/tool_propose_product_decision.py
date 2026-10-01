"""The propose_product_decision door; product proposals never supply human acceptance."""

from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.private_file_tools import _CONTROLS, DECISION, SCHEMAS, VERSION


def build_tool(*, run) -> RegisteredTool:
    def propose_product_decision(args, context):
        return run("propose_product_decision", args, context)

    return RegisteredTool(
        ToolDefinition(
            "propose_product_decision",
            "Record a PRODUCT-origin private settled-question proposal supported "
            "by actual primary "
            "clauses and scoped observations. Never record advocate acceptance, consent, authority "
            "or override an advocate/unknown-origin standing decision.",
            SCHEMAS[DECISION],
        ),
        ToolKind.MATTER,
        VERSION,
        False,
        _CONTROLS,
        propose_product_decision,
        required_act=Act.RECORD,
    )
