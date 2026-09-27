"""The rank_authorities model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION, _source
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, authority_weight, source_version) -> RegisteredTool:
    def weight(args, _context):
        if authority_weight is None:
            return _source(
                "rank_authorities",
                "authority weight owner",
                source_version,
                (),
                {},
                available=False,
                reason="The case identity and authority-weight reader is not configured.",
            )
        result = authority_weight.weigh(tuple(args["locators"]))
        return _source(
            "rank_authorities",
            "authority weight owner",
            source_version,
            args["locators"],
            asdict(result) if result.weighings else {},
            reason=result.why or "Authority weighting is a recorded rule, not semantic support.",
        )

    return RegisteredTool(
        ToolDefinition(
            "rank_authorities",
            "Ask the existing court/bench owner, never rank by model preference.",
            object_schema(
                {"locators": {"type": "array", "items": _STRING, "minItems": 1, "maxItems": 20}}
            ),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        weight,
    )
