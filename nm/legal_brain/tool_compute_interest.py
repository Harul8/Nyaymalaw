"""The compute_interest model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.brain_finalization import neutral
from nm.legal_brain.interest_calculation_contracts import InterestNotAssessed, compute_interest
from nm.legal_brain.reviewed_interest_selection import _TEXT, COMPUTE, VERSION
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_unavailable_tool(*, file_of, tool_version) -> RegisteredTool:
    def interest(_args, context):
        matter = file_of(context)
        return ToolEnvelope(
            "compute_interest",
            tool_version,
            ToolKind.COMPUTATION,
            ToolOutcome.FAILED,
            Availability.UNAVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "inputs": {},
                "method": "No reviewed interest-rule/calculation owner is configured",
                "input_receipts": [
                    {
                        "kind": "recorded_file",
                        "matter_id": matter.id,
                        "matter_version": matter.version,
                    }
                ],
            },
            {},
            "No reviewed contractual/statutory interest rule and calculation owner is configured. "
            "No rate, principal, compounding convention or payment allocation is assumed.",
        )

    return RegisteredTool(
        ToolDefinition(
            "compute_interest",
            "Report the unavailable reviewed interest rule; never estimate interest.",
            object_schema({}),
        ),
        ToolKind.COMPUTATION,
        tool_version,
        True,
        ("test_interest_absence_never_becomes_estimated_arithmetic",),
        interest,
    )


def build_tool(*, current, owner, reviews, store, controls) -> RegisteredTool:
    def compute(args, context):
        matter, _parent = current(context)
        if context.issue_ids and args["thread_id"] not in context.issue_ids:
            raise ToolRefused("Interest cannot move another dispute's monetary inputs")
        binding = reviews.resolve(matter, context, args["selection_id"]) if reviews else None
        inputs = {"matter_id": matter.id, "matter_version": matter.version, **args}
        receipts = [
            {
                "kind": "current_recorded_file",
                "snapshot": owner.source_owner.build(_parent, matter).payload["file_snapshot"],
            }
        ]
        reason, result = "", None
        if binding is None or binding.candidate["thread_id"] != args["thread_id"]:
            reason = (
                "Current exact bindings and sealed independent selection review are unavailable."
            )
        elif any(row["state"] == "not_assessed" for row in binding.candidate["coverage"]):
            reason = (
                "A current monetary/payment/competing-rule coverage judgment remains unassessed."
            )
        else:
            try:
                result = compute_interest(binding.inputs)
                receipts.append(
                    {
                        "kind": "independently_reviewed_interest_selection",
                        "package_id": binding.package.id,
                        "package_identity": binding.package.identity,
                        "selection_identity": binding.inputs.selection_identity,
                        "observations": [
                            neutral(asdict(row))
                            for row in (
                                binding.inputs.principal,
                                binding.inputs.rate,
                                *(payment.observation for payment in binding.inputs.payments),
                            )
                        ],
                    }
                )
                # Reconstruct again after arithmetic; no saved PASS defeats a source correction.
                again = reviews.resolve(store.load(matter.id), context, args["selection_id"])
                if again is None or again.package.identity != binding.package.identity:
                    raise InterestNotAssessed(
                        "Current source/selection identity changed during computation."
                    )
            except (InterestNotAssessed, ArithmeticError, ValueError) as exc:
                result, reason = None, str(exc)
        return ToolEnvelope(
            COMPUTE,
            VERSION,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS if result is not None else ToolOutcome.FAILED,
            Availability.AVAILABLE if result is not None else Availability.UNAVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "inputs": inputs,
                "method": "source literals + explicit conventions + independent saved review",
                "input_receipts": receipts,
            },
            result or {},
            reason
            or "Conditional arithmetic; factual truth and legal entitlement remain unestablished.",
        )

    return RegisteredTool(
        ToolDefinition(
            COMPUTE,
            "Compute conditional exact interest from current source "
            "observations and reviewed saved selections; never infer conventions.",
            object_schema({"thread_id": _TEXT, "selection_id": _TEXT}),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        False,
        controls,
        compute,
    )
