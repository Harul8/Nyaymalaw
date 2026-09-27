"""The compute_procedural_period model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.legal_brain.procedure import limitation
from nm.legal_brain.procedure.procedural_calculation import (
    _CONTROLS,
    _LIMIT,
    _TEXT,
    COMPUTE,
    VERSION,
)
from nm.legal_brain.reason.working_record import REFERENCE_SCHEMA, exact_reference
from nm.legal_brain.reason.working_record_contracts import ReferenceKind
from nm.legal_brain.retrieve.evidence_port import Finding
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.authority_contracts import Act
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.file_mutation_contracts import neutral


def build_tool(*, current, recheck, envelope, source_generation) -> RegisteredTool:
    def compute(args, context):
        inputs = current(args, context, COMPUTE)
        _matter, inventory, thread_ref, facts, observations, sources = inputs
        try:
            reference = exact_reference(inventory, args["source_reference"])
            source = next((row for row in sources if row["reference"] == reference.as_dict()), None)
            if (
                source is None
                or reference.kind is not ReferenceKind.SOURCE
                or "finding" not in source["value"]
            ):
                raise ToolRefused("The period has no exact current typed primary working source.")
            finding = Finding.from_record(source["value"]["finding"])
            if finding.supports is False or finding.source_blocking_reason:
                raise ToolRefused("A known unsupported primary source cannot supply a clock.")
            start, end = args["start"], args["end"]
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(finding.span)
            ):
                raise ToolRefused(
                    "The selected period must be an exact nonempty current source span."
                )
            quote = finding.span[start:end]
            if not quote.strip():
                raise ToolRefused("A blank source span establishes no period.")
            if (
                type(args["reason"]) is not str
                or not args["reason"].strip()
                or len(args["reason"]) > 16000
            ):
                raise ToolRefused("The conditional interpretation needs bounded nonblank words.")
            observation = next(
                (row for row in observations if row.identity == args["trigger_observation_id"]),
                None,
            )
            if observation is None:
                raise ToolRefused(
                    "The selected trigger is not one exact current scoped observation."
                )
            period = limitation.unique_period_in(quote)
            answer = (
                limitation.run_period(observation.on, period)
                if period is not None and observation.on is not None
                else None
            )
        except (ReviewRefused, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ToolRefused(
                "The requested selection is outside the conditional arithmetic contract."
            ) from exc
        data = {
            "thread_id": args["thread_id"],
            "thread_reference": thread_ref["reference"],
            "source_reference": reference.as_dict(),
            "source_generation": source_generation,
            "source": source["value"],
            "clause": {"start": start, "end": end, "quote": quote},
            "chronology": facts,
            "observations": [row.as_dict() for row in observations],
            "selected_observation_id": observation.identity,
            "selected_observation": observation.as_dict(),
            "reason": args["reason"],
            "period": neutral(asdict(period)) if period is not None else None,
            "conditional_date": answer.isoformat() if answer is not None else None,
            "arithmetic_verified": answer is not None,
            "selection_independently_reviewed": False,
            "legal_deadline_established": False,
            "legal_applicability_established": False,
            "factual_truth_established": False,
            "holiday_adjusted": False,
            "deadline_registered": False,
            "released": False,
            "client_ready": False,
        }
        reason = _LIMIT
        if answer is None:
            reason += (
                " No date was computed: the trigger is undated or "
                "the clause has no single supported period."
            )
        recheck(args, context, COMPUTE, inputs)
        return envelope(COMPUTE, args, inventory, data, reason=reason)

    return RegisteredTool(
        ToolDefinition(
            COMPUTE,
            "Add a unique source-quoted calendar period to one attributed current observation. "
            "Conditional arithmetic only: no independent legal selection review, "
            "court-calendar "
            "adjustment, established fact, established deadline or file mutation.",
            object_schema(
                {
                    "thread_id": _TEXT,
                    "source_reference": REFERENCE_SCHEMA,
                    "start": {"type": "integer", "minimum": 0},
                    "end": {"type": "integer", "minimum": 1},
                    "trigger_observation_id": _TEXT,
                    "reason": _TEXT,
                }
            ),
        ),
        ToolKind.COMPUTATION,
        VERSION,
        True,
        _CONTROLS,
        compute,
        required_act=Act.READ,
    )
