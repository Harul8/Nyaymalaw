"""The read_provision model-facing door over its existing native owners."""

from __future__ import annotations

from datetime import date

from nm.legal_brain.orchestrate.tools import (
    _STRING,
    OfferRole,
    RegisteredTool,
    ToolKind,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.retrieve.evidence_port import Coverage
from nm.shared.model_port import ToolDefinition


def build_tool(
    *, evidence, version, source_version, source_result, dated_provision_reader
) -> RegisteredTool:
    def provision(args, _context):
        if dated_provision_reader is not None:
            from nm.legal_brain.retrieve.tool_sources import DatedProvisionCapture, source_envelope

            captured = dated_provision_reader(
                args["act"], args["section"], date.fromisoformat(args["as_of"])
            )
            if not isinstance(captured, DatedProvisionCapture):
                raise ToolRefused("The dated provision owner returned no typed source capture")
            result = captured.evidence
            if not result.findings and not captured.capture.windows:
                return source_result("read_provision", result)
            complete = result.coverage is Coverage.ANSWERED
            supported = bool(result.findings) and len(result.usable) == len(result.findings)
            return source_envelope(
                "read_provision",
                version,
                "; ".join(result.searched_stores) or "dated provision owner",
                source_version,
                (),
                {
                    "coverage": result.coverage.value,
                    "provision_revision": captured.selection,
                    "assumption": result.assumption,
                    "search_note": result.search_note,
                },
                capture=captured.capture,
                primary_reads=(result,),
                partial=not complete,
                assessed=supported,
                reason=""
                if complete and supported
                else result.missing or captured.selection["reason"],
            )
        return source_result(
            "read_provision",
            evidence.read_provision(
                args["act"], args["section"], date.fromisoformat(args["as_of"])
            ),
        )

    return RegisteredTool(
        ToolDefinition(
            "read_provision",
            "Read a specific provision on the stated governing date.",
            object_schema({"act": _STRING, "section": _STRING, "as_of": _STRING}),
        ),
        ToolKind.SOURCE,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        provision,
        offer_role=OfferRole.OPTIONAL,
    )
