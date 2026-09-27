"""Safe stages from a committed journal, never model text or legal advice."""

from __future__ import annotations

import json
import re
from datetime import datetime

from nm.advise.turn_receipt_contracts import fingerprint, release_index
from nm.legal_brain.loop_contracts import LoopRecord, StepKind, StopReason

STAGES = {
    StepKind.START: "Recorded work started.",
    StepKind.MODEL_STARTED: "Assessing the recorded file.",
    StepKind.MODEL_RETURNED: "An assessment was received; checks are still required.",
    StepKind.TOOL_STARTED: "Checking the relevant material.",
    StepKind.TOOL_RETURNED: "A material check was recorded.",
    StepKind.FAILURE: "Part of the work could not complete.",
}
STOP_LABELS = {
    StopReason.PROPOSAL: "A draft was prepared; it has not been released as advice.",
    StopReason.QUESTION: "A question was prepared; checks are still required.",
    StopReason.CONVERSATION: "A conversational reply was prepared; it has not been released.",
    StopReason.BUDGET: "Work paused at its resource limit.",
    StopReason.CANCELLED: "Work was cancelled or its session ended.",
    StopReason.NO_PROGRESS: "Work paused because further useful progress was not established.",
    StopReason.PROVIDER: "Work paused because a service was unavailable.",
    StopReason.INTERRUPTED: "Work was interrupted; completion has not been confirmed.",
    StopReason.REFUSED: "Work stopped at a permission or quality boundary.",
    StopReason.CONTEXT: "Work paused because the checked file could not fit safely.",
}


class InvalidProgressCursor(ValueError):
    pass


def cursor_at(record: LoopRecord, sequence: int) -> str:
    if type(sequence) is not int or not 0 <= sequence <= len(record.events):
        raise InvalidProgressCursor("The saved progress position is not on this work record.")
    identity = record.events[sequence - 1].fingerprint if sequence else record.identity.fingerprint
    return f"{sequence}.{identity}"


def resume_position(record: LoopRecord, cursor: str | None) -> int:
    if cursor is None:
        return 0
    match = re.fullmatch(r"(0|[1-9][0-9]{0,8})\.([a-f0-9]{64})", cursor)
    if not match:
        raise InvalidProgressCursor("The saved progress position is not valid.")
    sequence = int(match[1])
    if cursor != cursor_at(record, sequence):
        raise InvalidProgressCursor("The saved progress position belongs to different work.")
    return sequence


def project_event(record: LoopRecord, sequence: int) -> dict:
    if type(sequence) is not int or not 1 <= sequence <= len(record.events):
        raise InvalidProgressCursor("The saved stage is not on this work record.")
    event = record.events[sequence - 1]
    if event.kind is StepKind.STOP:
        try:
            reason = StopReason(event.payload.get("reason"))
        except (TypeError, ValueError):
            reason = None
        label = STOP_LABELS.get(reason, "Work ended; its completion has not been established.")
        state = (
            "requires_checks" if reason in (
                StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION) else "stopped"
        )
    else:
        label, state = STAGES[event.kind], "working"
    return {
        "sequence": sequence,
        "cursor": cursor_at(record, sequence),
        "at": event.at,
        "label": label,
        "state": state,
        "working_not_advice": True,
    }


def recorded_scope(record: LoopRecord) -> dict:
    """Historic checked scope, not a model's claim that a dispute was assessed.

    The exact source-file digest and owned identities are checked before any
    supplied label is displayed. Missing/old/malformed context has a named
    absence; neither today's board nor tool arguments can fill it in.
    """
    absent = {
        "state": "not_established",
        "disputes": [],
        "shared_stages": True,
        "separate_dispute_progress": "not_established",
    }
    if not record.events:
        return absent
    try:
        context = record.events[0].payload["context"]
        brief = context["brief"]
        source = json.loads(brief["source_record_json"])
        selected = brief["selected_issue_ids"]
        if (
            context["schema"] != 1
            or brief["matter_id"] != record.identity.matter_id
            or brief["advocate_id"] != record.identity.advocate_id
            or source["id"] != record.identity.matter_id
            or source["advocate_id"] != record.identity.advocate_id
            or not isinstance(selected, list)
            or any(not isinstance(item, str) or not item.strip() for item in selected)
            or len(set(selected)) != len(selected)
            or fingerprint({key: value for key, value in source.items() if key != "version"})
            != brief["snapshot_id"]
        ):
            return absent
        threads = source["threads"]
        if not isinstance(threads, list):
            return absent
        labels = {row["id"]: row["label"] for row in threads}
        if len(labels) != len(threads) or not set(selected) <= set(labels):
            return absent
        if any(not isinstance(labels[item], str) or not labels[item].strip() for item in selected):
            return absent
        return {
            "state": "recorded",
            "disputes": [{"issue_id": item, "label": labels[item]} for item in selected],
            "shared_stages": True,
            "separate_dispute_progress": "not_established",
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return absent


def links_released_turn(matter, record: LoopRecord) -> bool:
    """A coincident turn id is insufficient to attach work to a released answer."""
    approved, problems = release_index(matter)
    receipt = approved.get(record.identity.turn_id)
    return bool(
        not problems
        and receipt is not None
        and matter.id == record.identity.matter_id
        and matter.advocate_id == record.identity.advocate_id
        and receipt.offer_fingerprint == record.identity.offer_hash
    )


def progress(record: LoopRecord, *, after: str | None = None, linked_turn: bool = False) -> dict:
    position = resume_position(record, after)
    return {
        "turn_id": record.identity.turn_id,
        "terminal": record.terminal,
        "result_state": "not_released",
        "linked_released_turn": linked_turn is True,
        "scope": recorded_scope(record),
        "cursor": cursor_at(record, len(record.events)),
        "events": [
            project_event(record, sequence)
            for sequence in range(position + 1, len(record.events) + 1)
        ],
    }


def sse_frame(row: dict) -> bytes:
    # Only this closed projection is permitted here. An arbitrary payload or
    # supplied SSE event id cannot become a second transport for model prose.
    expected = {"sequence", "cursor", "at", "label", "state", "working_not_advice"}
    states = dict.fromkeys(STAGES.values(), "working")
    states.update(
        {
            label: "requires_checks"
            if reason in (StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION)
            else "stopped"
            for reason, label in STOP_LABELS.items()
        }
    )
    states["Work ended; its completion has not been established."] = "stopped"
    if (
        set(row) != expected
        or row["working_not_advice"] is not True
        or type(row["sequence"]) is not int
        or row["sequence"] < 1
        or not isinstance(row["label"], str)
        or row["label"] not in states
        or row["state"] != states[row["label"]]
        or datetime.fromisoformat(row["at"]).utcoffset() is None
    ):
        raise ValueError("Only a safe persisted-progress projection may be streamed")
    match = re.fullmatch(r"([0-9]{1,9})\.[a-f0-9]{64}", row["cursor"])
    if not match or int(match[1]) != row["sequence"]:
        raise InvalidProgressCursor("The progress identity is not safe for transport.")
    body = json.dumps(row, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return f"id: {row['cursor']}\nevent: progress\ndata: {body}\n\n".encode("utf-8")
