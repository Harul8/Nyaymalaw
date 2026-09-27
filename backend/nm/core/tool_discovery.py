"""Discover actual registered capabilities; metadata never grants permission.

The live registry and versioned owner guide are the only sources. This adds no
legal table, copied prompt, scenario routing or model-authored capability. Its
exact inspection receipt can load a schema through the trusted offer owner;
discovery metadata alone neither loads a schema nor grants execution authority.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from nm.core.tools import (
    Assessment,
    Availability,
    OfferRole,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    ToolRegistry,
    object_schema,
)
from nm.ports.model import ToolDefinition
from nm.ports.principles import PrinciplesPort

VERSION = "registered-discovery-v1"


def discovery_tools(current_registry: Callable[[], ToolRegistry],
                    principles: PrinciplesPort) -> tuple[RegisteredTool, ...]:
    def registry_for(context):
        registry = current_registry()
        if (not isinstance(registry, ToolRegistry)
                or registry.version != context.identity.tools_version):
            raise ToolRefused("The capability registry changed; start from its current contract.")
        return registry

    def envelope(name, context, registry, data):
        return ToolEnvelope(name, VERSION, ToolKind.CONTROL, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.SUPPORTED,
            {"operation": name, "turn_id": context.identity.turn_id,
             "registry_version": registry.version},
            {"metadata_only": True, "grants_permission": False,
             "establishes_law_or_case_facts": False, **data})

    def discover(args, context):
        registry = registry_for(context)
        query = args["query"].strip()
        if len(query) > 2000:
            raise ToolRefused("The capability search exceeds its bound.")
        words = set(query.casefold().split())
        definitions = registry.definitions
        ranked = sorted(definitions, key=lambda row: (
            -sum(word in (row.name + " " + row.description).casefold() for word in words),
            row.name))
        # Ranking only. Zero overlap does not say a capability is absent.
        return envelope("discover_tools", context, registry, {
            "registered_count": len(definitions), "returned_count": len(ranked),
            "tools": [{"name": row.name, "description": row.description,
                       "required_act": registry.authority_for(row.name).value}
                      for row in ranked],
            "ranking_only": True})

    def inspect(args, context):
        registry = registry_for(context)
        rows = [row for row in registry.definitions if row.name == args["name"]]
        if len(rows) != 1:
            raise ToolRefused("That exact tool is not registered; no capability was inferred.")
        return envelope("inspect_tool", context, registry, {
            "definition": asdict(rows[0]),
            "required_act": registry.authority_for(rows[0].name).value})

    def guide(args, context):
        registry = registry_for(context)
        snapshot = principles.load()
        if (snapshot.version != context.identity.principles_version
                or args["expected_version"] != snapshot.version):
            raise ToolRefused(
                "The owner guide changed; it cannot replace the admitted instructions.")
        return envelope("read_owner_guide", context, registry, {
            "guide_version": snapshot.version, "text": snapshot.text,
            "trust": "owner_guidance_not_permission_or_legal_authority"})

    rows = (
        ("discover_tools", "List actual registered capabilities without approving actions.",
         {"query": {"type": "string"}}, discover),
        ("inspect_tool", "Read the exact schema of a registered tool; no guessed alias.",
         {"name": {"type": "string", "minLength": 1}}, inspect),
        ("read_owner_guide", "Read the admitted owner guide, not law or action authority.",
         {"expected_version": {"type": "string", "minLength": 1}}, guide),
    )
    return tuple(RegisteredTool(
        ToolDefinition(name, description, object_schema(shape)), ToolKind.CONTROL, VERSION, True,
        ("test_discovery_is_the_actual_registry_not_a_second_catalogue",), handler,
        offer_role=OfferRole.SCHEMA_LOADER if name == "inspect_tool" else OfferRole.INITIAL)
        for name, description, shape, handler in rows)
