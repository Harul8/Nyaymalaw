"""The check_candidate_independently model-facing independent-review door."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind
from nm.legal_brain.verify.early_independent_review import SCHEMA, TOOL, VERSION
from nm.shared.model_port import ToolDefinition


def build_tool(*, service, policy) -> RegisteredTool:
    def check(args, context):
        return service.run(args, context)

    return RegisteredTool(
        ToolDefinition(
            TOOL,
            "Independently check one exact already-recorded candidate before continuing. "
            "No source text, verdict, grant, fact confirmation or release is accepted "
            "as an argument. This private read cannot authorize publication or "
            "arithmetic inputs.",
            SCHEMA,
        ),
        ToolKind.CONTROL,
        VERSION,
        False,
        (
            "test_actual_open_loop_dispatches_a_distinct_independent_verifier",
            "test_early_positive_requires_its_actual_exact_response",
        ),
        check,
        delegation=policy,
    )
