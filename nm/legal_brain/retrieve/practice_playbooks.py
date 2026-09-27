"""Actual playbook catalogue and bounded pointer inspection via existing readers."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
)
from nm.legal_brain.retrieve.practice_playbooks_port import PlaybooksUnavailable


def playbook_tools(playbooks, *, snapshot, evidence, search=None):
    def current():
        try:
            if playbooks.load().version != snapshot.version:
                raise ToolRefused("The owner playbooks changed; start a new admitted turn.")
        except PlaybooksUnavailable as exc:
            raise ToolRefused(str(exc)) from exc

    def envelope(name, data, context):
        return ToolEnvelope(
            name,
            snapshot.version,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "operation": name,
                "turn_id": context.identity.turn_id,
                "playbooks_version": snapshot.version,
            },
            {
                "metadata_only": True,
                "establishes_facts_or_law": False,
                "grants_permission": False,
                **data,
            },
            "Owner guidance is navigation, not legal authority; read the pointed sources.",
        )

    controls = ("test_playbook_tools_keep_guidance_distinct_from_law_and_permission",)
    from nm.legal_brain.retrieve.tool_read_playbook_catalogue import (
        build_tool as read_playbook_catalogue_tool,
    )
    from nm.legal_brain.retrieve.tool_read_practice_playbook import (
        build_tool as read_practice_playbook_tool,
    )

    return (
        read_playbook_catalogue_tool(
            current=current, envelope=envelope, snapshot=snapshot, controls=controls
        ),
        read_practice_playbook_tool(
            current=current,
            envelope=envelope,
            snapshot=snapshot,
            evidence=evidence,
            search=search,
            controls=controls,
        ),
    )
