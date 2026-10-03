"""Validate structured brain reads and offer one feedback-guided correction."""
from __future__ import annotations

import json
from typing import Callable, TypeVar

from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    TierUnavailable,
    estimate_tokens,
    require_schema,
)

_T = TypeVar("_T")


def require_independent_result(result) -> None:
    if result.was_downgraded:
        raise TierUnavailable("The configured independent review was unavailable")


def checked_read(model: ModelPort, prompt: Prompt, schema: dict,
                 output_limit: int, accept: Callable[[dict], _T], *,
                 tier: Tier = Tier.ROUTINE) -> _T:
    """Return one validated read; correct one rejected response in context."""
    current = prompt
    for attempt in range(2):
        result = None
        try:
            result = model.structured(current, schema, tier,
                                      max_tokens=output_limit)
            if tier == Tier.JUDGE:
                require_independent_result(result)
            if not result.usable or not isinstance(result.data, dict):
                raise SchemaViolation("The response was incomplete or not a JSON object")
            require_schema(result.data, schema)
            return accept(result.data)
        except SchemaViolation as exc:
            if attempt:
                raise
            correction = {
                "original_input": json.loads(prompt.user),
                "validation_issue": str(exc),
                "how_to_correct": (
                    "Return the complete declared JSON object. Correct missing "
                    "or invalid fields under the same schema. Use only source "
                    "references and classifications allowed by the input; omit "
                    "unsupported proposals rather than inventing facts, "
                    "citations, or earlier context. If the issue names a saved "
                    "item and required source IDs, include one of those IDs "
                    "only when that item is the intended link; otherwise "
                    "remove or correct the link."),
                "rejected_output": result.data if result is not None else None,
            }
            repair_system = prompt.system + (
                "\n\nMessage: This is a correction of the same read; the prior "
                "response was rejected and was not saved.\n"
                "Purpose: Repair the stated validation failure.\n"
                "Look for: The validation issue and the original attributed "
                "source words.\n"
                "Outcome: Return a complete replacement object under the "
                "same schema, with only supported proposals.")
            repair_user = json.dumps(correction, ensure_ascii=False,
                                     separators=(",", ":"))
            if (estimate_tokens(repair_system + repair_user) + output_limit
                    > model.context_budget(tier)):
                correction.pop("rejected_output")
                repair_user = json.dumps(correction, ensure_ascii=False,
                                         separators=(",", ":"))
            if (estimate_tokens(repair_system + repair_user) + output_limit
                    > model.context_budget(tier)):
                raise ContextOverflow(
                    "The full conversation exceeds the correction context budget") from exc
            current = Prompt(system=repair_system, user=repair_user,
                             operation=prompt.operation)
    raise AssertionError("The correction loop did not return or raise")
