"""The propose_fee_selection model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused
from nm.legal_brain.procedure.fee_calculation_contracts import FeeNotAssessed
from nm.legal_brain.procedure.reviewed_fee_selection import FEE_SELECTION_SCHEMA, PROPOSE, VERSION
from nm.legal_brain.verify.brain_finalization import neutral
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.model_port import SchemaViolation, ToolDefinition


def build_tool(*, current, envelope, owner, controls) -> RegisteredTool:
    def propose(args, context):
        matter, parent = current(context)
        try:
            binding = owner.bind(parent, matter, args)
            again, latest = current(context)
            if owner.bind(latest, again, args).package != binding.package:
                raise ReviewRefused("The fee source selection changed during binding")
        except (ReviewRefused, FeeNotAssessed, SchemaViolation) as exc:
            raise ToolRefused(str(exc)) from exc
        return envelope(
            PROPOSE,
            context,
            {
                "candidate": args,
                "derived_inputs": neutral(asdict(binding.inputs)),
                "selection_reviewed": False,
                "released": False,
            },
            selection_identity=digest(args),
        )

    return RegisteredTool(
        ToolDefinition(
            PROPOSE,
            "Propose exact-source fee literals/conventions/version/date for independent "
            "review; "
            "never supply an authored rate, amount or approval.",
            FEE_SELECTION_SCHEMA,
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        controls,
        propose,
    )
