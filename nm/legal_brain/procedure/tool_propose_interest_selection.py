"""The propose_interest_selection model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused
from nm.legal_brain.procedure.interest_calculation_contracts import InterestNotAssessed
from nm.legal_brain.procedure.reviewed_interest_selection import (
    INTEREST_SELECTION_SCHEMA,
    PROPOSE,
    VERSION,
)
from nm.legal_brain.verify.brain_finalization import neutral
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, owner, controls) -> RegisteredTool:
    def propose(args, context):
        matter, parent = current(context)
        try:
            binding = owner.bind(parent, matter, args)
        except (ReviewRefused, InterestNotAssessed, ValueError) as exc:
            raise ToolRefused(str(exc)) from exc
        return envelope(
            PROPOSE,
            context,
            {
                "candidate": args,
                "observations": [
                    neutral(asdict(row))
                    for row in (
                        binding.inputs.principal,
                        binding.inputs.rate,
                        *(payment.observation for payment in binding.inputs.payments),
                    )
                ],
                "selection_reviewed": False,
                "released": False,
            },
            selection_identity=digest(args),
        )

    return RegisteredTool(
        ToolDefinition(
            PROPOSE,
            "Propose exact-source monetary observations and conventions; "
            "Independent review required. No authored monetary or rate values.",
            INTEREST_SELECTION_SCHEMA,
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        controls,
        propose,
    )
