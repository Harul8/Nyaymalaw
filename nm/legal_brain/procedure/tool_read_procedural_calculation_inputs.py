"""The read_procedural_calculation_inputs model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.procedure.procedural_calculation import _CONTROLS, _TEXT, READ, VERSION
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, recheck, envelope) -> RegisteredTool:
    def read(args, context):
        inputs = current(args, context, READ)
        _matter, inventory, thread_ref, facts, observations, sources = inputs
        data = {
            "thread_id": args["thread_id"],
            "thread_reference": thread_ref["reference"],
            "sources": sources,
            "chronology": facts,
            "observations": [row.as_dict() for row in observations],
            "selection_independently_reviewed": False,
            "legal_deadline_established": False,
            "factual_truth_established": False,
            "deadline_registered": False,
        }
        recheck(args, context, READ, inputs)
        return envelope(READ, args, inventory, data)

    return RegisteredTool(
        ToolDefinition(
            READ,
            "Read exact working source references and the full attributed event inventory "
            "for one scoped dispute. All competing/undated events remain; "
            "no trigger or legal clock is selected.",
            object_schema({"thread_id": _TEXT}),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        True,
        _CONTROLS,
        read,
        required_act=Act.READ,
    )
