"""Safe stages from a committed journal, never model text or legal advice."""

from __future__ import annotations

import json
import re
from datetime import datetime

from nm.advise.turn_receipt_contracts import fingerprint, release_index
from nm.legal_brain.orchestrate.loop_contracts import LoopRecord, StepKind, StopReason

REQUIREMENTS_STAGE = (
    "Source-linked information needs were proposed for this dispute; "
    "their applicability has not been assessed."
)
PROVISION_STAGE = "A provision was read; its application has not been assessed."
AUTHORITY_STAGE = "An authority passage was read; its legal effect has not been assessed."
AUTHORITY_SEARCH_STAGE = "Authority candidates were found; none is yet legal support."
OPPOSITION_STAGE = (
    "A source-linked opposition pass was recorded for this dispute; "
    "its conclusions have not been independently assessed."
)
CROSS_OPPOSITION_STAGE = (
    "Cross-dispute opposition work was recorded; its conclusions have not been "
    "independently assessed."
)
SCOPED_STAGES = frozenset({REQUIREMENTS_STAGE, OPPOSITION_STAGE})
SHARED_TYPED_STAGES = frozenset({
    PROVISION_STAGE, AUTHORITY_STAGE, AUTHORITY_SEARCH_STAGE, CROSS_OPPOSITION_STAGE,
})

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
UNKNOWN_STOP_LABEL = "Work ended; its completion has not been established."


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
    """Project one stage using only the supplied sealed record."""
    return _project_event(record, sequence, None)


def _project_event(record: LoopRecord, sequence: int, scope: dict | None) -> dict:
    if type(sequence) is not int or not 1 <= sequence <= len(record.events):
        raise InvalidProgressCursor("The saved stage is not on this work record.")
    event = record.events[sequence - 1]
    if event.kind is StepKind.STOP:
        try:
            reason = StopReason(event.payload.get("reason"))
        except (TypeError, ValueError):
            reason = None
        label = STOP_LABELS.get(reason, UNKNOWN_STOP_LABEL)
        state = (
            "requires_checks" if reason in (
                StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION) else "stopped"
        )
    else:
        label, state = STAGES[event.kind], "working"
    row = {
        "sequence": sequence,
        "cursor": cursor_at(record, sequence),
        "at": event.at,
        "label": label,
        "state": state,
        "working_not_advice": True,
    }
    dispute_index = _recorded_requirement_dispute(record, sequence, scope)
    if dispute_index is not None:
        row.update(label=REQUIREMENTS_STAGE, dispute_index=dispute_index)
    else:
        typed = _recorded_source_or_opposition(record, sequence, scope)
        if typed is not None:
            row["label"] = typed[0]
            if typed[1] is not None:
                row["dispute_index"] = typed[1]
    return row


def _recorded_source_or_opposition(
    record: LoopRecord, sequence: int, scope: dict | None
) -> tuple[str, int | None] | None:
    """Execution-only source/oppose stages from paired committed tool receipts.

    Ordinary source tools carry no dispute target, so their progress stays
    shared even if their words appear relevant to one dispute. A set-aside is
    only a private candidate in this journal; it is deliberately absent here.
    """
    if sequence < 2 or record.events[sequence - 1].kind is not StepKind.TOOL_RETURNED:
        return None
    started, returned = record.events[sequence - 2 : sequence]
    if started.kind is not StepKind.TOOL_STARTED:
        return None
    try:
        from nm.legal_brain.orchestrate.loop_contracts import digest
        from nm.legal_brain.orchestrate.tools import (
            Assessment,
            Availability,
            Effect,
            ToolKind,
            ToolOutcome,
            ToolRefused,
        )
        from nm.legal_brain.reason.opposition_work import (
            PASSES,
            OppositionRequest,
            _check_saved_extracts,
            check_observations,
            scoped_premises,
        )
        from nm.legal_brain.retrieve.evidence_port import Finding, SourceKind
        from nm.legal_brain.retrieve.tool_sources import (
            findings_from_envelope,
            source_envelopes_from_event,
            tool_envelope_from_record,
        )

        call, payload = started.payload["call"], returned.payload
        name = call["name"]
        if (
            set(call) != {"call_id", "name", "arguments"}
            or not isinstance(call["arguments"], dict)
            or call["call_id"] != payload["call_id"]
        ):
            return None
        envelope = tool_envelope_from_record(payload["receipt"])
        if (
            envelope.tool != name
            or envelope.kind is not ToolKind.SOURCE
            or envelope.outcome is not ToolOutcome.RESULTS
            or envelope.availability is not Availability.AVAILABLE
            or envelope.effect is not Effect.CONTINUE
        ):
            return None
        versions = {
            "read_provision": {"foundation-v2", "foundation-dated-v3"},
            "read_paragraph": {"owner-wrappers-v1"},
            "read_judgment": {"owner-wrappers-v1"},
            "search_authority": {"foundation-v2", "foundation-dated-v3"},
            "search_authorities": {"owner-wrappers-v1"},
        }
        if name in versions:
            if envelope.version not in versions[name]:
                return None
            if name in {"read_provision", "read_paragraph", "read_judgment"}:
                # A search hit or metadata-only result is not an exact read.
                kind = (SourceKind.PROVISION if name == "read_provision"
                        else SourceKind.AUTHORITY)
                findings = findings_from_envelope(envelope)
                windows = envelope.data.get("captured_windows", [])
                if (not findings and not windows
                        or not isinstance(windows, list)
                        or any(finding.source_kind is not kind for finding in findings)
                        or any(not isinstance(window, dict)
                               or window.get("source_kind") != kind.value
                               or window.get("locator") not in envelope.receipt["locators"]
                               or window.get("legal_metadata") != "not_assessed"
                               for window in windows)):
                    return None
                return (PROVISION_STAGE if name == "read_provision" else AUTHORITY_STAGE, None)
            return AUTHORITY_SEARCH_STAGE, None
        if name not in PASSES or envelope.version != "nested-research-v1":
            return None
        if envelope.assessment is not Assessment.NOT_ASSESSED:
            return None
        args = call["arguments"]
        if (set(args) != {"question", "issue_ids"}
                or not isinstance(args["question"], str) or not args["question"].strip()
                or not isinstance(args["issue_ids"], list)):
            return None
        request = OppositionRequest(name, args["question"], tuple(args["issue_ids"]))
        result = envelope.data
        task = envelope.receipt.get("task_result")
        if (
            task != {key: value for key, value in result.items() if key != "findings"}
            or result.get("admitted_as_facts") is not False
            or result.get("advice_released") is not False
            or not isinstance(result.get("opposition_work"), dict)
            or result.get("reused_from") is not None
            or payload.get("child_released") is not False
        ):
            return None
        raw = result["opposition_work"]
        body = {key: value for key, value in raw.items() if key != "work_identity"}
        if (
            raw.get("work_identity") != digest(body)
            or raw.get("schema") != 1
            or raw.get("tool") != name
            or raw.get("question") != args["question"]
            or raw.get("issue_ids") != args["issue_ids"]
            or raw.get("assessment") != "not_assessed"
            or raw.get("advice_released") is not False
            or raw.get("full_readiness") != "not_assessed"
            or raw.get("case", {}).get("matter_id") != record.identity.matter_id
            or raw.get("case", {}).get("advocate_id") != record.identity.advocate_id
            or raw.get("case", {}).get("issue_ids") != sorted(args["issue_ids"])
            or raw.get("case", {}).get("pass") != PASSES[name]
        ):
            return None
        captured = tuple(
            finding for source in source_envelopes_from_event(returned)
            for finding in findings_from_envelope(source)
        )
        if not captured or any(Finding.from_record(item) not in captured
                               for item in raw["sources"]):
            return None
        _check_saved_extracts(raw)
        if any(row.get("semantic_assessment") != "not_assessed"
               for row in raw["research"]["observations"]):
            return None
        check_observations(
            request, raw["research"]["observations"],
            finding_ids={row["id"] for row in raw["research"]["findings"]},
            premise_ids={row["id"] for row in raw["case"]["facts"]},
            premise_by_issue=scoped_premises(raw["case"]),
        )
        scope = recorded_scope(record) if scope is None else scope
        if scope["state"] != "recorded":
            return None
        indexes = [index for index, dispute in enumerate(scope["disputes"], 1)
                   if dispute["issue_id"] in request.issue_ids]
        if len(indexes) != len(request.issue_ids):
            return None
        if name == "oppose_matter":
            return (CROSS_OPPOSITION_STAGE, None) if len(indexes) >= 2 else None
        return (OPPOSITION_STAGE, indexes[0]) if len(indexes) == 1 else None
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, ToolRefused):
        return None


def _recorded_requirement_dispute(
    record: LoopRecord, sequence: int, scope: dict | None = None
) -> int | None:
    """Only a committed, source-bound tool receipt yields this neutral stage.

    No proposed need, reason, source text or model-written label is projected.
    The separately checked rationale channel owns explanations of that work.
    """
    if sequence < 2 or record.events[sequence - 1].kind is not StepKind.TOOL_RETURNED:
        return None
    started, returned = record.events[sequence - 2 : sequence]
    if started.kind is not StepKind.TOOL_STARTED:
        return None
    try:
        from nm.legal_brain.orchestrate.tools import (
            Assessment,
            Availability,
            Effect,
            ToolKind,
            ToolOutcome,
        )
        from nm.legal_brain.reason.requirements_contracts import Requirement
        from nm.legal_brain.reason.source_writes import VERSION as REQUIREMENTS_VERSION
        from nm.legal_brain.retrieve.tool_sources import tool_envelope_from_record

        call, payload = started.payload["call"], returned.payload
        envelope = tool_envelope_from_record(payload["receipt"])
        data, receipt = envelope.data, envelope.receipt
        if (
            set(call) != {"call_id", "name", "arguments"}
            or call["name"] != "record_requirements"
            or call["call_id"] != payload["call_id"]
            or envelope.tool != call["name"]
            or envelope.version != REQUIREMENTS_VERSION
            or envelope.kind is not ToolKind.MATTER
            or envelope.outcome is not ToolOutcome.RESULTS
            or envelope.availability is not Availability.AVAILABLE
            or envelope.assessment is not Assessment.NOT_ASSESSED
            or envelope.effect is not Effect.CONTINUE
            or receipt["matter_id"] != record.identity.matter_id
            or receipt["snapshot"] != payload.get("mutation_identity")
            or not isinstance(receipt.get("source_version"), str)
            or not receipt["source_version"].strip()
            or set(data) != {
                "thread_id", "requirements", "states_derived", "facts_established",
                "legal_interpretation",
            }
            or call["arguments"].get("thread_id") != data["thread_id"]
            or data["states_derived"] is not True
            or data["facts_established"] is not False
            or data["legal_interpretation"] != "not_assessed"
            or not isinstance(data["requirements"], list)
            or not data["requirements"]
        ):
            return None
        for raw in data["requirements"]:
            requirement = Requirement.restore(raw)
            if (
                requirement is None
                or not requirement.locator.strip()
                or len(requirement.source_identity) != 64
                or any(char not in "0123456789abcdef" for char in requirement.source_identity)
            ):
                return None
        scope = recorded_scope(record) if scope is None else scope
        if scope["state"] != "recorded":
            return None
        return next(
            (index for index, dispute in enumerate(scope["disputes"], 1)
             if dispute["issue_id"] == data["thread_id"]),
            None,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _committed_opening_disputes(record: LoopRecord, known: set[str]) -> list[dict]:
    """Extend historic scope only with the actual source-bound write receipt.

    A proposed label alone is not a dispute. The paired returned event is the
    runner's atomic mutation boundary; its identity and original quoted words
    must agree with the same write owner that admitted the new thread.
    """
    try:
        from nm.legal_brain.orchestrate.loop_contracts import digest
        from nm.legal_brain.orchestrate.tools import (
            Assessment,
            Availability,
            Effect,
            ToolKind,
            ToolOutcome,
        )
        from nm.legal_brain.retrieve.tool_sources import tool_envelope_from_record
        from nm.work_the_file.file_mutation import assertion_identity, dispute_identity
        from nm.work_the_file.original_instruction import read_original_instruction
        from nm.work_the_file.write_tools import VERSION as WRITE_VERSION

        start = record.events[0].payload
        if start.get("scope_identity") != digest({"requested_issue_ids": []}):
            return []
        original = read_original_instruction(record)
        if original.state != "recorded":
            return []
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    additions = []
    for index in range(1, len(record.events)):
        started, returned = record.events[index - 1 : index + 1]
        if started.kind is not StepKind.TOOL_STARTED or returned.kind is not StepKind.TOOL_RETURNED:
            continue
        try:
            call, payload = started.payload["call"], returned.payload
            if set(call) != {"call_id", "name", "arguments"} or call["name"] != "create_dispute":
                continue
            args = call["arguments"]
            if (not isinstance(args, dict) or set(args) != {"label", "quoted"}
                    or any(not isinstance(args[key], str) or not args[key].strip()
                           for key in ("label", "quoted"))
                    or args["quoted"] not in original.text
                    or payload["call_id"] != call["call_id"]):
                continue
            envelope = tool_envelope_from_record(payload["receipt"])
            data, receipt = envelope.data, envelope.receipt
            thread_id = dispute_identity(
                record.identity.matter_id, record.identity.turn_id,
                args["quoted"], args["label"],
            )
            if (
                envelope.tool != call["name"]
                or envelope.version != WRITE_VERSION
                or envelope.kind is not ToolKind.MATTER
                or envelope.outcome is not ToolOutcome.RESULTS
                or envelope.availability is not Availability.AVAILABLE
                or envelope.assessment is not Assessment.NOT_ASSESSED
                or envelope.effect is not Effect.CONTINUE
                or receipt["matter_id"] != record.identity.matter_id
                or receipt["matter_version"] != record.identity.matter_version + index
                or receipt["snapshot"] != payload.get("mutation_identity")
                or not isinstance(payload.get("checked_snapshot"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", payload["checked_snapshot"])
                or not isinstance(receipt["snapshot"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", receipt["snapshot"])
                or set(data) != {
                    "operation", "changed_fields", "thread_id", "fact_id", "unassessed",
                    "merged_existing", "selected_span", "asserted_only",
                }
                or data["operation"] != "create_dispute"
                or data["changed_fields"] not in (["threads", "facts"], ["threads"])
                or data["thread_id"] != thread_id
                or data["fact_id"] != assertion_identity(
                    record.identity.matter_id, record.identity.turn_id, original.text
                )
                or data["selected_span"] != args["quoted"]
                or data["unassessed"] is not True
                or data["merged_existing"] is not False
                or data["asserted_only"] is not True
                or thread_id in known
            ):
                continue
            known.add(thread_id)
            additions.append({"issue_id": thread_id, "label": args["label"]})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return additions


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
        disputes = [{"issue_id": item, "label": labels[item]} for item in selected]
        disputes.extend(_committed_opening_disputes(record, set(selected)))
        return {
            "state": "recorded",
            "disputes": disputes,
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
    scope = recorded_scope(record)
    return {
        "turn_id": record.identity.turn_id,
        "terminal": record.terminal,
        "result_state": "not_released",
        "linked_released_turn": linked_turn is True,
        "scope": scope,
        "cursor": cursor_at(record, len(record.events)),
        "events": [
            _project_event(record, sequence, scope)
            for sequence in range(position + 1, len(record.events) + 1)
        ],
    }


def label_states() -> dict[str, str]:
    """EVERY stage label this projection can emit, with its state.

    The one population: the transport below accepts exactly these, and the
    page's working display must name each of them (LB-82).
    """
    states = dict.fromkeys(STAGES.values(), "working")
    states.update(
        {
            label: "requires_checks"
            if reason in (StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION)
            else "stopped"
            for reason, label in STOP_LABELS.items()
        }
    )
    states[UNKNOWN_STOP_LABEL] = "stopped"
    states[REQUIREMENTS_STAGE] = "working"
    states.update(dict.fromkeys(SHARED_TYPED_STAGES | SCOPED_STAGES, "working"))
    return states


def sse_frame(row: dict) -> bytes:
    # Only this closed projection is permitted here. An arbitrary payload or
    # supplied SSE event id cannot become a second transport for model prose.
    expected = {"sequence", "cursor", "at", "label", "state", "working_not_advice"}
    scoped = "dispute_index" in row
    if scoped:
        expected.add("dispute_index")
    states = label_states()
    if (
        set(row) != expected
        or row["working_not_advice"] is not True
        or type(row["sequence"]) is not int
        or row["sequence"] < 1
        or not isinstance(row["label"], str)
        or row["label"] not in states
        or row["state"] != states[row["label"]]
        or (row["label"] in SCOPED_STAGES) != scoped
        or scoped and (
            row["label"] not in SCOPED_STAGES
            or type(row["dispute_index"]) is not int
            or not 1 <= row["dispute_index"] <= 1000
        )
        or datetime.fromisoformat(row["at"]).utcoffset() is None
    ):
        raise ValueError("Only a safe persisted-progress projection may be streamed")
    match = re.fullmatch(r"([0-9]{1,9})\.[a-f0-9]{64}", row["cursor"])
    if not match or int(match[1]) != row["sequence"]:
        raise InvalidProgressCursor("The progress identity is not safe for transport.")
    body = json.dumps(row, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return f"id: {row['cursor']}\nevent: progress\ndata: {body}\n\n".encode("utf-8")
