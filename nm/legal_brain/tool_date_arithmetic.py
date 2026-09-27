"""The date_arithmetic model-facing door over its existing native owners."""

from __future__ import annotations

from datetime import timedelta

from nm.legal_brain import limitation
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.tool_catalogue import _CONTROLS, _STRING, VERSION, _date
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


def build_tool() -> RegisteredTool:
    def date_arithmetic(args, _context):
        on = _date(args["on"])
        amount = args["amount"]
        try:
            if args["unit"] == "years":
                answer = limitation.add_years(on, amount)
                method = "nm.legal_brain.limitation.add_years"
            elif args["unit"] == "months":
                answer = limitation.add_months(on, amount)
                method = "nm.legal_brain.limitation.add_months"
            else:
                answer = on + timedelta(days=amount)
                method = "calendar timedelta; no court-calendar adjustment"
        except (ValueError, OverflowError) as exc:
            raise ToolRefused(
                "the requested arithmetic lies outside the supported calendar"
            ) from exc
        return ToolEnvelope(
            "date_arithmetic",
            VERSION,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.SUPPORTED,
            {
                "inputs": args,
                "method": method,
                "input_receipts": [
                    {
                        "kind": "tool arguments",
                        "digest": digest(args),
                        "legal_premises_established": False,
                    }
                ],
            },
            {
                "date": answer.isoformat(),
                "holiday_adjusted": False,
                "legal_deadline_established": False,
            },
        )

    return RegisteredTool(
        ToolDefinition(
            "date_arithmetic",
            "Calendar arithmetic only; no unheld holiday or legal rule.",
            object_schema(
                {
                    "on": _STRING,
                    "amount": {"type": "integer", "minimum": -100000, "maximum": 100000},
                    "unit": {"type": "string", "enum": ["years", "months", "days"]},
                }
            ),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        True,
        _CONTROLS,
        date_arithmetic,
    )
