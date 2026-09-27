"""The propose_working_record model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.tools import RegisteredTool, ToolKind, ToolRefused
from nm.legal_brain.working_record import _CONTROLS, PROPOSAL_SCHEMA, PROPOSE_TOOL, VERSION
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, owner) -> RegisteredTool:
    def propose(args, context):
        try:
            matter, parent = current(context)
            inventory, _, _ = owner.bind(parent, matter, args)
            return envelope(
                PROPOSE_TOOL,
                inventory,
                context,
                {"candidate": args, "independently_checked": False, "released": False},
            )
        except ReviewRefused as exc:
            raise ToolRefused(str(exc)) from exc

    return RegisteredTool(
        ToolDefinition(
            PROPOSE_TOOL,
            "Annotate actual work per dispute using exact "
            "inventory identities and source quotes. Include reasons for "
            "kept/set-aside/unassessed "
            "judgments. This is private candidate text, not PASS or task relevance. It needs "
            "independent source review after stopping.",
            PROPOSAL_SCHEMA,
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        _CONTROLS,
        propose,
    )
