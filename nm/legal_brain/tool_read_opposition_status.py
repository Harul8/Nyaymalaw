"""The read_opposition_status model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.opposition_work import PASSES, VERSION, _saved_work, controls, status_for_work
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool(*, store, provider, model) -> RegisteredTool:
    def read(_arguments, context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("Opposition status requires the current authenticated file.")
        from nm.legal_brain.nested_research import _parent_reads

        captured = _parent_reads(matter, context.identity)
        control = controls(context, provider(), model())
        latest = {}
        for raw, reference in _saved_work(matter):
            if set(raw["issue_ids"]) <= set(context.issue_ids):
                state = status_for_work(matter, raw, captured, control)
                latest[(raw["tool"], tuple(sorted(raw["issue_ids"])))] = {
                    "pass": PASSES[raw["tool"]],
                    "issue_ids": raw["issue_ids"],
                    "state": state,
                    "work_identity": raw["work_identity"],
                    "record": reference,
                    "private_work": raw["research"] if state == "current_unreviewed" else None,
                    "assessment": "not_assessed",
                    "advice_released": False,
                }
        expected = [
            (tool, (issue,))
            for issue in context.issue_ids
            for tool in ("oppose_early", "oppose_full")
        ]
        if len(matter.threads) > 1 and {row.id for row in matter.threads} <= set(context.issue_ids):
            expected.append(("oppose_matter", tuple(sorted(row.id for row in matter.threads))))
        rows = [
            latest.get(
                key,
                {
                    "pass": PASSES[key[0]],
                    "issue_ids": list(key[1]),
                    "state": "not_assessed",
                    "assessment": "not_assessed",
                    "advice_released": False,
                },
            )
            for key in expected
        ]
        return ToolEnvelope(
            "read_opposition_status",
            VERSION,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {"operation": "read_opposition_status", "turn_id": context.identity.turn_id},
            {
                "passes": rows,
                "full_readiness": "not_assessed",
                "readiness_reason": "The key-detail threshold has not been adopted.",
                "complete": False,
                "advice_released": False,
            },
            "A work receipt is not independent legal assessment or completion.",
        )

    return RegisteredTool(
        ToolDefinition(
            "read_opposition_status",
            "Read saved early, full and cross-dispute opposition work. "
            "Use current source-checked work without repeating paid work. None clears advice or "
            "establishes full-pass readiness; decide the useful next task from the actual gaps.",
            object_schema({}),
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        (
            "test_three_distinct_passes_are_saved_and_never_complete_merits",
            "test_changed_dispute_stales_only_its_work_and_the_cross_pass",
        ),
        read,
    )
