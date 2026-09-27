"""The finish_research child-only source-bound handoff door."""

from __future__ import annotations

from nm.legal_brain.tools import object_schema
from nm.shared.model_port import ToolDefinition, require_schema

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}
DEFINITION = ToolDefinition(
    "finish_research",
    "Return exact retrieved extracts and tentative source-bound observations. "
    "No facts, acts, procedural completion or advice are established by this return.",
    object_schema(
        {
            "findings": {
                "type": "array",
                "items": object_schema({"id": _STRING, "locator": _STRING, "quote": _STRING}),
            },
            "observations": {
                "type": "array",
                "items": object_schema(
                    {
                        "issue_id": _STRING,
                        "text": _STRING,
                        "finding_ids": _STRINGS,
                        "premise_ids": _STRINGS,
                    }
                ),
            },
        }
    ),
)


def finish(*, handoff, session, arguments, captured, opposition, definition=DEFINITION):
    require_schema(arguments, definition.parameters)
    return handoff(session, arguments, captured, opposition=opposition)
