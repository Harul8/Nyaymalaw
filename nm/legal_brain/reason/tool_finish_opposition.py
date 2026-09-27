"""The finish_opposition child-only source-bound handoff door."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import object_schema
from nm.legal_brain.reason.opposition_work import KINDS
from nm.shared.model_port import ToolDefinition, require_schema

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}
DEFINITION = ToolDefinition(
    "finish_opposition",
    "Return source-bound private contrary positions, replies and judicial "
    "vulnerabilities for this exact pass. No legal readiness, fact or advice is established.",
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
                        "id": _STRING,
                        "issue_ids": _STRINGS,
                        "kind": {"type": "string", "enum": list(KINDS)},
                        "text": _STRING,
                        "finding_ids": _STRINGS,
                        "premise_ids": _STRINGS,
                        "response_to": _STRING,
                        "no_supported_reply": {"type": "boolean"},
                        "course": _STRING,
                    }
                ),
            },
        }
    ),
)


def finish(*, handoff, session, arguments, captured, opposition, definition=DEFINITION):
    require_schema(arguments, definition.parameters)
    return handoff(session, arguments, captured, opposition=opposition)
