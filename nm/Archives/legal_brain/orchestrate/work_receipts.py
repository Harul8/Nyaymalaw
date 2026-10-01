"""Exact attempted-work projection, never legal support, facts or permission.

The saved journal is the execution owner. An offered/model-requested tool is
not work performed. Complete tool populations are bounded by refusal, never
silently truncated. Parent and delegated outcomes use the same projection.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.loop_contracts import StepKind, digest
from nm.Archives.legal_brain.retrieve.tool_sources import tool_envelope_from_record
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.json_values import same_json_value
from nm.shared.model_port import ToolCall

MAX_WORK_RECEIPT_CHARACTERS = 128000


def _returned(call, raw):
    envelope = tool_envelope_from_record(raw)
    if call.name != envelope.tool:
        raise ReviewRefused("Actual work differs from its saved tool invocation")
    result = json.loads(envelope.wire())
    # Exact legal words have their own checked-window population in the subject.
    # The complete result digest still binds these fields; no supported Finding
    # is synthesized from an execution receipt.
    data = {key: value for key, value in result["data"].items()
            if key not in {"findings", "captured_windows"}}
    return {"state": "returned", "result_identity": digest(result),
            "result": {**result, "data": data},
            "legal_windows": "see_separate_checked_source_population"}


def _child(trace, parent_payload):
    if (not isinstance(trace, (list, tuple))
            or parent_payload.get("child_released") is not False
            or type(parent_payload.get("child_steps")) is not int
            or any(not isinstance(row, dict) for row in trace)
            or parent_payload["child_steps"] != sum(
                row.get("kind") in {"model_started", "tool_started"} for row in trace)):
        raise ReviewRefused("Delegated work lacks its complete actual dispatch population")
    rows, pending = [], None
    for index, event in enumerate(trace):
        kind = event.get("kind")
        if kind == "tool_started":
            if pending is not None:
                raise ReviewRefused("A child cannot omit an attempted tool outcome")
            pending = ToolCall(**event["call"])
            rows.append({"event_index": index, "call": asdict(pending),
                         "state": "outcome_unknown"})
        elif kind == "tool_returned":
            if pending is None:
                raise ReviewRefused("A child result needs its actual invocation")
            rows[-1].update(_returned(pending, event["receipt"]))
            pending = None
        elif kind == "refused":
            # A refusal before any invocation is also work not performed.
            refusal = {"state": "refused", "error": event.get("error"),
                       "reason": event.get("reason")}
            if pending is None:
                rows.append({"event_index": index, "call": None, **refusal})
            else:
                rows[-1].update(refusal)
                pending = None
    return rows


def work_receipts(record):
    """Derive all attempts from the sealed transcript, including failed reads."""
    rows, pending = [], None
    try:
        for event in record.events:
            payload = event.payload
            if event.kind is StepKind.TOOL_STARTED:
                if pending is not None:
                    raise ReviewRefused("A tool attempt lost its actual outcome")
                pending = ToolCall(**payload["call"])
                rows.append({"event_sequence": event.sequence,
                             "event_identity": event.fingerprint,
                             "call": asdict(pending), "state": "outcome_unknown"})
            elif event.kind is StepKind.TOOL_RETURNED:
                if pending is None or payload.get("call_id") != pending.call_id:
                    raise ReviewRefused("An execution receipt lacks its actual saved attempt")
                rows[-1].update(_returned(pending, payload["receipt"]))
                rows[-1]["outcome_identity"] = event.fingerprint
                if "child_transcript" in payload or "child_steps" in payload:
                    rows[-1]["child_work"] = _child(payload.get("child_transcript"), payload)
                pending = None
            elif event.kind is StepKind.FAILURE and pending is not None:
                if payload.get("call_id") != pending.call_id:
                    raise ReviewRefused("A tool failure differs from the actual attempt")
                rows[-1].update(state=("refused" if payload.get("kind") ==
                    "tool_boundary_refused" else "not_completed"), failure=payload,
                    outcome_identity=event.fingerprint)
                pending = None
        projection = {"trust": "execution_data_not_facts_law_or_authorization",
                      "count": len(rows), "attempts": rows}
        if len(json.dumps(projection, ensure_ascii=False, allow_nan=False)) > (
                MAX_WORK_RECEIPT_CHARACTERS):
            raise ReviewRefused("The complete work population exceeds its review ceiling")
        return projection
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewRefused):
            raise
        raise ReviewRefused("The saved work population is incomplete or malformed") from exc


def require_work_receipts(payload, record):
    """Historical/current readers refuse deleted, invented or changed execution."""
    expected = work_receipts(record)
    if not same_json_value(payload.get("work_receipts"), expected):
        raise ReviewRefused("The reviewed work population differs from its actual saved journal")
    sources = [row for row in payload["quote_sources"] if row["id"] == "work_receipts"]
    text = json.dumps(expected, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if sources != [{"id": "work_receipts", "text": text}]:
        raise ReviewRefused("The work citation differs from its exact attempted population")
