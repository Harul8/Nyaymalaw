"""The identify_act model-facing door over its existing native owners."""

from __future__ import annotations

from datetime import date

from nm.legal_brain.orchestrate.tools import (
    _STRING,
    Assessment,
    Availability,
    OfferRole,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, manifest, version, source_version) -> RegisteredTool:
    def identify(args, _context):
        resolution = manifest.identify(args["name"], date.fromisoformat(args["as_of"]))
        data = (
            {"act": resolution.entry.act_name, "basis": resolution.basis.value}
            if resolution.entry is not None
            else {}
        )
        return ToolEnvelope(
            "identify_act",
            version,
            ToolKind.SOURCE,
            ToolOutcome.RESULTS if data else ToolOutcome.NO_RESULTS,
            Availability.AVAILABLE,
            Assessment.SUPPORTED,
            {
                "index": "exact Act manifest",
                "source_version": source_version,
                "locators": [resolution.entry.act_name] if data else [],
            },
            data,
        )

    return RegisteredTool(
        ToolDefinition(
            "identify_act",
            "Identify an Act exactly; this never ranks a guessed statute.",
            object_schema({"name": _STRING, "as_of": _STRING}),
        ),
        ToolKind.SOURCE,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        identify,
        offer_role=OfferRole.OPTIONAL,
    )
