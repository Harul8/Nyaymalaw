"""The court_fee model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.procedure.fee_calculation_contracts import FeeNotAssessed, compute_fee
from nm.legal_brain.procedure.filing_requirement_port import Requirement
from nm.legal_brain.procedure.reviewed_fee_selection import _TEXT, COMPUTE, VERSION
from nm.legal_brain.verify.brain_finalization import neutral
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, owner, reviews, controls) -> RegisteredTool:
    def compute(args, context):
        matter, parent = current(context)
        if context.issue_ids and args["thread_id"] not in context.issue_ids:
            raise ToolRefused("Fee arithmetic cannot transfer another dispute's selected values")
        try:
            snapshot = owner.source_owner.build(parent, matter).payload["file_snapshot"]
        except ReviewRefused as exc:
            raise ToolRefused(str(exc)) from exc
        binding = reviews.resolve(matter, context, args["selection_id"]) if reviews else None
        receipts = [{"kind": "current_recorded_file", "snapshot": snapshot}]
        result, reason = None, ""
        if binding is None or binding.candidate["thread_id"] != args["thread_id"]:
            reason = (
                "Current exact fee bindings and sealed independent same-judge review "
                "are unavailable."
            )
        elif any(row["state"] == "not_assessed" for row in binding.candidate["coverage"]):
            reason = "A schedule/value/competing-source coverage judgment remains unassessed."
        else:
            try:
                result = compute_fee(binding.inputs)
                again, _latest = current(context)
                restored = reviews.resolve(again, context, args["selection_id"])
                if restored is None or restored.package.identity != binding.package.identity:
                    raise FeeNotAssessed(
                        "The exact schedule/input/review changed during arithmetic."
                    )
                receipts.append(
                    {
                        "kind": "independently_reviewed_fee_selection",
                        "package_id": binding.package.id,
                        "package_identity": binding.package.identity,
                        "derived_inputs": neutral(asdict(binding.inputs)),
                    }
                )
            except (FeeNotAssessed, ArithmeticError) as exc:
                result, reason = None, str(exc)
        return ToolEnvelope(
            COMPUTE,
            VERSION,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS if result is not None else ToolOutcome.FAILED,
            Availability.AVAILABLE if result is not None else Availability.UNAVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "inputs": {"matter_id": matter.id, "matter_version": matter.version, **args},
                "method": "exact source literals + explicit fee conventions + "
                "sealed independent selection review",
                "input_receipts": receipts,
            },
            result or {},
            reason
            or "Conditional schedule arithmetic; lawful fee, valuation and jurisdiction "
            "remain unestablished.",
        )

    return RegisteredTool(
        ToolDefinition(
            COMPUTE,
            "Compute conditional exact fee schedule arithmetic from current saved "
            "independently "
            "checked selections; never claim a legally payable fee or pecuniary jurisdiction.",
            object_schema({"thread_id": _TEXT, "selection_id": _TEXT}),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        False,
        controls,
        compute,
    )


def build_unavailable_tool(*, tables, version, controls) -> RegisteredTool:
    def court_fee(_args, _context):
        readiness = (
            tables.filing.readiness(Requirement.COURT_FEES)
            if (tables is not None and tables.filing is not None)
            else None
        )
        reason = (
            readiness.why or "The versioned court-fee computation rule is not configured."
            if readiness
            else "The court-fee source readiness reader is not configured."
        )
        return ToolEnvelope(
            "court_fee",
            version,
            ToolKind.COMPUTATION,
            ToolOutcome.FAILED,
            Availability.UNAVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "inputs": {},
                "method": "FilingRequirementPort.readiness; no fee arithmetic",
                "input_receipts": [asdict(readiness)] if readiness else [],
            },
            {},
            reason,
        )

    return RegisteredTool(
        ToolDefinition(
            "court_fee",
            "Name the missing versioned fee rule; never estimate a fee.",
            object_schema({}),
        ),
        ToolKind.COMPUTATION,
        version,
        True,
        controls,
        court_fee,
    )
