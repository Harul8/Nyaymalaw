"""The propose_limitation_selection model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.reviewed_limitation_selection import (
    SELECTION_SCHEMA,
    VERSION,
    _binding,
    _candidate_envelope,
)
from nm.legal_brain.tools import RegisteredTool, ToolKind, ToolRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, store, source_generation, source_current) -> RegisteredTool:
    def propose(args, context):
        matter, thread = file_of(context, args["thread_id"])
        try:
            parents = tuple(row for row in matter.loop_records if row.identity == context.identity)
            if len(parents) != 1:
                raise ReviewRefused(
                    "The proposed premises need their actual admitted parent journal"
                )
            binding = _binding(
                matter,
                thread,
                args,
                parents[0],
                source_generation=source_generation,
                source_current=source_current,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ToolRefused(str(exc)) from exc
        if store.load(matter.id) != matter:
            raise ToolRefused("The file moved while its selection was proposed")
        return _candidate_envelope(binding, matter.id)

    return RegisteredTool(
        ToolDefinition(
            "propose_limitation_selection",
            "Propose exact source-span and event-identity "
            "bindings for independent review after this author turn. Preserve every chronology "
            "entry; this proposal is not a reviewed result and cannot confirm any fact.",
            SELECTION_SCHEMA,
        ),
        ToolKind.COMPUTATION,
        VERSION,
        True,
        (
            "test_unreviewed_event_selection_cannot_supply_calculation_inputs",
            "test_event_selection_requires_full_current_chronology_and_exact_primary_spans",
        ),
        propose,
    )
