"""Exact saved user input, kept separate from model prose and legal truth.

The caller still owns authentication, finite evaluation scope and sealed-journal
currentness. This decoder never grants permission. Historical records without
an admitted input use only the actual first dispatch, never a model response,
tool result, context summary or a guessed reconstruction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from nm.legal_brain.orchestrate.loop_contracts import LoopMode, LoopRecord, StepKind, digest
from nm.shared.model_port import Prompt

LEAD_OPERATION = "controlled_legal_brain"
TRUST = "user_instruction_not_established_fact_or_legal_authority"


class InstructionRefused(ValueError):
    """An original-input record is malformed or disagrees with its actual admission."""


@dataclass(frozen=True)
class OriginalInstruction:
    state: str
    text: str = ""
    text_identity: str = ""
    provenance: str = "not_recorded"

    def __post_init__(self):
        if any(not isinstance(value, str) for value in (
                self.state, self.text, self.text_identity, self.provenance)):
            raise ValueError("Original input fields have an explicit typed recorded/absent state")
        if self.state == "not_recorded":
            if self.text or self.text_identity or self.provenance != "not_recorded":
                raise ValueError("An absent instruction cannot invent recorded words")
        elif (self.state != "recorded" or not isinstance(self.text, str) or not self.text.strip()
                or self.text_identity != digest(self.text)
                or self.provenance not in {"sealed_turn_admission", "sealed_first_dispatch"}):
            raise ValueError("An original instruction needs exact supplied words and provenance")

    def as_dict(self):
        return {"state": self.state, "text": self.text, "text_identity": self.text_identity,
                "provenance": self.provenance, "material_kind": "advocate_original_instruction",
                "trust": TRUST}


@dataclass(frozen=True)
class PriorInstruction:
    record: LoopRecord
    original: OriginalInstruction
    selected_issue_ids: tuple[str, ...]


def prior_instructions(matter, *, actor: str, mode: LoopMode,
                       before_version: int) -> tuple[PriorInstruction, ...]:
    """One admission owner for prior supplied words, never authority or truth.

    Only completed lead work admitted before this turn participates. Special
    research, review and display journals are not original advocate inputs.
    Callers still own the current session, finite scope and permission boundary.
    """
    if (not isinstance(actor, str) or not actor.strip() or matter.advocate_id != actor
            or not isinstance(mode, LoopMode) or type(before_version) is not int
            or not 1 <= before_version <= matter.version):
        raise InstructionRefused("Prior input needs its owned mode and admitted version")
    rows, seen = [], set()
    for saved in sorted(matter.loop_records, key=lambda row: (
            row.identity.matter_version, row.identity.turn_id)):
        if (not saved.terminal or saved.identity.mode is not mode
                or saved.identity.matter_version + len(saved.events) > before_version):
            continue
        start = saved.events[0].payload
        if "max_steps" not in start or "per_call_tokens" not in start:
            continue
        try:
            captured = json.loads(start.get("context", {}).get("brief", {}).get("text", "null"))
            if not isinstance(captured, dict) or captured.get("material_kind") != (
                    "checked_matter_file"):
                continue
            issues = captured["data"]["selected_issue_ids"]
            if (not isinstance(issues, list) or any(
                    not isinstance(value, str) or not value.strip() for value in issues)
                    or len(set(issues)) != len(issues)
                    or saved.identity.matter_id != matter.id
                    or saved.identity.advocate_id != actor
                    or saved.identity.turn_id in seen):
                raise InstructionRefused("The original input has a foreign or ambiguous scope")
            seen.add(saved.identity.turn_id)
            rows.append(PriorInstruction(saved, read_original_instruction(saved), tuple(issues)))
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, InstructionRefused):
                raise
            raise InstructionRefused("The prior lead input cannot be verified") from exc
    return tuple(rows)


def capture_original_instruction(prompt: Prompt) -> dict:
    """Called by the trusted runner before dispatch, never by a model or HTTP body."""
    if (not isinstance(prompt, Prompt) or not isinstance(prompt.user, str)
            or not prompt.user.strip()):
        raise ValueError("A captured original input needs exact nonblank caller words")
    return _capture(prompt.user, prompt.system, prompt.operation)


def _capture(user, system, operation):
    return {"schema": 1, "text": user, "text_identity": digest(user), "operation": operation,
            "request_identity": digest({"user": user, "system": system, "operation": operation})}


def _dispatch(record):
    events = [event for event in record.events if event.kind is StepKind.MODEL_STARTED]
    if not events:
        return None
    try:
        raw = events[0].payload["prompt"]
        if (not isinstance(raw, dict) or not isinstance(raw.get("user"), str)
                or not raw["user"].strip()
                or digest({"user": raw["user"], "system": raw["system"],
                           "operation": raw["operation"]}) != record.identity.offer_hash):
            raise InstructionRefused("The original dispatch differs from its admitted request")
        return raw
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InstructionRefused):
            raise
        raise InstructionRefused("The original dispatch has no recoverable exact input") from exc


def read_original_instruction(record: LoopRecord) -> OriginalInstruction:
    """Only the lead's exact original user text; never unchecked response words.

    The reviewed-preview caller must first verify the actor, actual journal,
    session and current finite grant. A missing historical input is stated as
    missing even when a later STOP contains model prose.
    """
    if not isinstance(record, LoopRecord) or not record.events:
        raise InstructionRefused("An original input needs its actual saved loop")
    dispatch = _dispatch(record)
    raw = record.events[0].payload.get("original_instruction")
    if raw is None:
        if dispatch is None or dispatch.get("operation") != LEAD_OPERATION:
            return OriginalInstruction("not_recorded")
        return OriginalInstruction("recorded", dispatch["user"], digest(dispatch["user"]),
                                   "sealed_first_dispatch")
    try:
        if (not isinstance(raw, dict) or set(raw) != {
                "schema", "text", "text_identity", "operation", "request_identity"}
                or type(raw["schema"]) is not int or raw["schema"] != 1
                or not isinstance(raw["text"], str) or not raw["text"].strip()
                or raw["text_identity"] != digest(raw["text"])
                or raw["request_identity"] != record.identity.offer_hash):
            raise InstructionRefused("The captured original input differs from its admission")
        if dispatch is not None:
            if raw != _capture(dispatch["user"], dispatch["system"], dispatch["operation"]):
                raise InstructionRefused(
                    "The admitted input differs from its first actual dispatch")
        else:
            # Actual lead ContextSessions capture their prefix at admission.
            # Reconstruct only its request fingerprint; never return that prefix.
            context = record.events[0].payload.get("context", {})
            if (not isinstance(context, dict) or "system" not in context
                    or digest({"user": raw["text"], "system": context["system"],
                               "operation": raw["operation"]}) != record.identity.offer_hash):
                raise InstructionRefused("The pre-dispatch input has no exact captured prefix")
        if raw["operation"] != LEAD_OPERATION:
            return OriginalInstruction("not_recorded")
        return OriginalInstruction("recorded", raw["text"], raw["text_identity"],
                                   "sealed_turn_admission")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InstructionRefused):
            raise
        raise InstructionRefused("The saved original input cannot be verified") from exc
