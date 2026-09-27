"""The quote_matter model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.open_matter.matter_documents_port import DocumentRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, matter_result, matter_documents) -> RegisteredTool:
    def quote_matter(args, context):
        matter = file_of(context)
        try:
            quote = matter_documents.quote(
                matter.id, matter.advocate_id, context.current_version, **args
            )
        except DocumentRefused as exc:
            raise ToolRefused(str(exc)) from exc
        return matter_result("quote_matter", matter, asdict(quote))

    return RegisteredTool(
        ToolDefinition(
            "quote_matter",
            "Quote an exact owned admitted-document version and original text span.",
            object_schema(
                {
                    "original_id": _STRING,
                    "asset_version": {"type": "integer", "minimum": 1},
                    "source_sha256": _STRING,
                    "derivative_sha256": _STRING,
                    "number": {"type": "integer", "minimum": 1},
                    "location_kind": {"type": "string", "enum": ["page", "part"]},
                    "part": _STRING,
                    "start": {"type": "integer", "minimum": 0},
                    "end": {"type": "integer", "minimum": 1},
                }
            ),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        quote_matter,
    )
