"""Discover actual registered capabilities; metadata never grants permission.

The live registry and versioned owner guide are the only sources. This adds no
legal table, copied prompt, scenario routing or model-authored capability. Its
exact inspection receipt can load a schema through the trusted offer owner;
discovery metadata alone neither loads a schema nor grants execution authority.
"""

from __future__ import annotations

from collections.abc import Callable

from nm.legal_brain.principles_port import PrinciplesPort
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    ToolRegistry,
)

VERSION = "registered-discovery-v1"


def discovery_tools(
    current_registry: Callable[[], ToolRegistry], principles: PrinciplesPort
) -> tuple[RegisteredTool, ...]:
    def registry_for(context):
        registry = current_registry()
        if (
            not isinstance(registry, ToolRegistry)
            or registry.version != context.identity.tools_version
        ):
            raise ToolRefused("The capability registry changed; start from its current contract.")
        return registry

    def envelope(name, context, registry, data):
        return ToolEnvelope(
            name,
            VERSION,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.SUPPORTED,
            {
                "operation": name,
                "turn_id": context.identity.turn_id,
                "registry_version": registry.version,
            },
            {
                "metadata_only": True,
                "grants_permission": False,
                "establishes_law_or_case_facts": False,
                **data,
            },
        )

    from nm.legal_brain.tool_discover_tools import build_tool as discover_tools_tool
    from nm.legal_brain.tool_inspect_tool import build_tool as inspect_tool_tool
    from nm.legal_brain.tool_read_owner_guide import build_tool as read_owner_guide_tool

    return (
        discover_tools_tool(registry_for=registry_for, envelope=envelope),
        inspect_tool_tool(registry_for=registry_for, envelope=envelope),
        read_owner_guide_tool(registry_for=registry_for, envelope=envelope, principles=principles),
    )
