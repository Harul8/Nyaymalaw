"""The read_source_document model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import (
    _CONTROLS,
    _LIMIT,
    _STRING,
    VERSION,
    _enum,
    _source,
)
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.retrieve.evidence_port import SourceKind
from nm.legal_brain.retrieve.tool_sources import capture_document
from nm.shared.model_port import ToolDefinition


def build_tool(*, evidence, source_version) -> RegisteredTool:
    def source_document(args, _context):
        result = evidence.document(
            args["locator"], SourceKind(args["kind"]), start=args["start"], count=args["count"]
        )
        if result.state == "read" and not result.snapshot_id.strip():
            return _source(
                "read_source_document",
                result.store or "corpus document reader",
                "not_established",
                (),
                {},
                available=False,
                reason="The read has no source snapshot identity; its text cannot be accepted.",
            )
        return _source(
            "read_source_document",
            result.store or "corpus document reader",
            result.snapshot_id or source_version,
            [row[0] for row in result.segments],
            asdict(result) if result.state == "read" else {},
            available=result.state != "no_reader",
            partial=bool(result.excluded) or not result.whole,
            capture=capture_document(result, kind=SourceKind(args["kind"])),
            reason="The source was not held."
            if result.state == "not_held"
            else "The corpus document reader is not available."
            if result.state == "no_reader"
            else "This located source window is material to assess, not an approved conclusion.",
        )

    return RegisteredTool(
        ToolDefinition(
            "read_source_document",
            "Read a held corpus document window without a path or URL.",
            object_schema(
                {
                    "locator": _STRING,
                    "kind": _enum(SourceKind),
                    "start": {"type": "integer", "minimum": 0},
                    "count": _LIMIT,
                }
            ),
        ),
        ToolKind.SOURCE,
        VERSION,
        True,
        _CONTROLS,
        source_document,
    )
