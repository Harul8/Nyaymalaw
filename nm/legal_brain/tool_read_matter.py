"""The read_matter model-facing door over its existing native owners."""

from __future__ import annotations

import json
from dataclasses import asdict

from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    OfferRole,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    _wire_value,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, store, version) -> RegisteredTool:
    def matter_read(_args, context):
        matter = store.load(context.identity.matter_id)
        if matter is None or matter.advocate_id != context.identity.advocate_id:
            raise ToolRefused("the matter is not available to this actor")
        if matter.version != context.current_version:
            raise ToolRefused("the recorded file changed before this read")
        data = {
            "title": matter.title,
            "facts": [asdict(f) for f in matter.facts],
            "disputes": [asdict(t) for t in matter.threads],
        }
        normalized = json.loads(json.dumps(data, default=_wire_value, allow_nan=False))
        return ToolEnvelope(
            "read_matter",
            version,
            ToolKind.MATTER,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.SUPPORTED,
            {
                "matter_id": matter.id,
                "matter_version": matter.version,
                "snapshot": digest(normalized),
            },
            normalized,
        )

    return RegisteredTool(
        ToolDefinition(
            "read_matter",
            "Read the persisted structured matter registers: recorded facts and "
            "distinct disputes. This read does not enumerate current or earlier authenticated "
            "advocate inputs. Empty arrays mean no entries in those registers, not that no "
            "brief or material was supplied. Consider scoped supplied assertions separately; "
            "this read neither admits them nor establishes their truth.",
            object_schema({}),
        ),
        ToolKind.MATTER,
        version,
        True,
        ("test_each_foundation_tool_refuses_before_its_handler",),
        matter_read,
        offer_role=OfferRole.INITIAL,
    )
