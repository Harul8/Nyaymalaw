"""Owned conversation context and atomic receipts; no model or legal decisions.

The existing sealed store owns persistence. This version owns the exact transcript,
its chain and replay, independently of future prompt or renderer implementations.
Stage results passed to commit_turn must already have passed their admission owner.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

CONTRACT = "core_conversation_v1"
HEADER = "core_conversation"


class ConversationRefused(Exception):
    def __init__(self, why, *, status=409, code="history_unavailable",
                 committed="not_committed", retryable=False):
        super().__init__(why)
        self.why, self.status, self.code = why, status, code
        self.committed, self.retryable = committed, retryable


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def chat_matter_id(advocate_id, chat_id):
    return "chat_" + digest([advocate_id, chat_id])


def _nonempty(value):
    return type(value) is str and bool(value.strip())


def checked_rows(matter, advocate_id):
    if matter.advocate_id != advocate_id:
        raise ConversationRefused("Conversation not available.", status=404)
    header = matter.intake_answers.get(HEADER)
    if not isinstance(header, dict) or header.get("contract") != CONTRACT:
        raise ConversationRefused(
            "This historical conversation is preserved but cannot be continued by this engine.",
            code="historical_conversation", committed="previously_committed")
    previous = None
    last_version = 0
    try:
        if (not _nonempty(header["chat_id"])
                or chat_matter_id(advocate_id, header["chat_id"]) != matter.id
                or type(header["turn_count"]) is not int
                or header["turn_count"] != len(matter.brain_chat)):
            raise ValueError("conversation header")
        for sequence, row in enumerate(matter.brain_chat, 1):
            body = {k: v for k, v in row.items() if k != "digest"}
            request = row["request"]
            response = row["response"]
            if (row["contract"] != CONTRACT or type(row["sequence"]) is not int
                    or row["sequence"] != sequence
                    or row["previous"] != previous or row["digest"] != digest(body)
                    or row["matter_id"] != matter.id or row["advocate_id"] != advocate_id
                    or row["chat_id"] != header["chat_id"]
                    or request != {"advocate_id": advocate_id, "chat_id": header["chat_id"],
                                   "turn_id": row["turn_id"], "message": row["message"]}
                    or not _nonempty(row["message"]) or not _nonempty(row["turn_id"])
                    or type(row["state_version"]) is not int
                    or not last_version < row["state_version"] <= matter.version
                    or response["turn_id"] != row["turn_id"]
                    or response["chat_id"] != header["chat_id"]
                    or response["matter_id"] is not None
                    or response["matter_version"] != row["state_version"]
                    or response["committed"] != "committed"
                    or response["input_admitted"] is not True
                    or response["replayed"] is not False
                    or type(response["elements"]) is not list
                    or any(type(e) is not dict or type(e.get("text")) is not str
                           for e in response["elements"])
                    or response.get("service_status") is not None
                    and type(response["service_status"]) is not str
                    or type(row["records"]) is not dict or type(row["work"]) is not list
                    or type(row["activities"]) is not dict):
                raise ValueError("conversation receipt")
            previous, last_version = row["digest"], row["state_version"]
        if header["tail_digest"] != previous:
            raise ValueError("conversation tail")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConversationRefused(
            "The saved conversation could not be read reliably. Its records are unchanged.",
            committed="previously_committed") from exc
    return deepcopy(matter.brain_chat)


@dataclass(frozen=True)
class TurnContext:
    matter: Matter
    chat_id: str
    turn_id: str
    message: str
    rows: tuple[dict, ...]
    replay: dict | None = None

    @property
    def request(self):
        return {"advocate_id": self.matter.advocate_id, "chat_id": self.chat_id,
                "turn_id": self.turn_id, "message": self.message}

    def payload(self):
        conversation = []
        for row in self.rows:
            conversation.append({"source_id": row["turn_id"] + ":advocate",
                                 "turn_id": row["turn_id"], "speaker": "advocate",
                                 "record_role": "original_account", "text": row["message"]})
            response = row["response"]
            text = "\n\n".join(e["text"] for e in response["elements"])
            conversation.append({"source_id": row["turn_id"] + ":nm",
                                 "turn_id": row["turn_id"], "speaker": "nm",
                                 "record_role": "nm_interpretation", "text": text})
            if response.get("service_status"):
                conversation.append({"source_id": row["turn_id"] + ":service",
                                     "turn_id": row["turn_id"], "speaker": "service",
                                     "record_role": "service_status",
                                     "text": response["service_status"]})
        latest = {"source_id": self.turn_id + ":advocate", "turn_id": self.turn_id,
                  "speaker": "advocate", "record_role": "original_account", "text": self.message}
        return {"position": "follow_up" if self.rows else "first", "latest": latest,
                "conversation": conversation,
                "current_records": deepcopy(self.rows[-1]["records"]) if self.rows else {},
                "saved_work": deepcopy(self.rows[-1]["work"]) if self.rows else []}


def open_turn(store, *, advocate_id, message, turn_id, chat_id=None, matter_id=None,
              expected_version=None):
    if not all(_nonempty(v) for v in (advocate_id, message, turn_id)):
        raise ConversationRefused("A message and request identity are required.", status=422)
    if matter_id is not None:
        raise ConversationRefused("Reopen this conversation from My work before continuing.")
    if chat_id is not None and not _nonempty(chat_id):
        raise ConversationRefused("A valid conversation identity is required.", status=422)
    if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
        raise ConversationRefused("A valid conversation version is required.", status=422)
    identity = chat_id or "new_" + digest([advocate_id, turn_id])[:32]
    stored_id = chat_matter_id(advocate_id, identity)
    try:
        matter = store.load(stored_id)
    except (OSError, ValueError) as exc:
        raise ConversationRefused("The conversation could not be loaded reliably.") from exc
    if matter is None and chat_id is not None:
        raise ConversationRefused("The conversation could not be found. Reopen it before continuing.")
    rows = checked_rows(matter, advocate_id) if matter else ()
    matter = matter or Matter(id=stored_id, advocate_id=advocate_id,
                              title="Conversation", brain_ready=False)
    context = TurnContext(matter, identity, turn_id, message, rows)
    for row in rows:
        if row["turn_id"] == turn_id:
            if row["request"] != context.request:
                raise ConversationRefused("This request identity belongs to a different message.",
                                          code="request_conflict", committed="previously_committed")
            return replace(context, replay={**row["response"], "replayed": True})
    if expected_version is not None and expected_version != matter.version:
        raise ConversationRefused("The conversation changed. Reopen it before continuing.",
                                  code="stale_version")
    return context


def commit_turn(store, context, *, elements, activities, records=None, work=None,
                service_status=None, metrics=None, session_current=lambda: False):
    """Save already-admitted work and its exact public response in one CAS write."""
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
    if context.replay is not None:
        return deepcopy(context.replay)
    version = context.matter.version + 1
    response = {"turn_id": context.turn_id, "matter_id": None, "chat_id": context.chat_id,
                "route": "core_engine", "mode": "conversation", "mode_statement": "",
                "blocked": False, "blocked_reason": None, "elements": deepcopy(elements),
                "material": [], "material_coverage": {}, "briefing": {}, "board_changes": [],
                "composed": [], "continuation": {}, "metrics": deepcopy(metrics or {}),
                "replayed": False, "committed": "committed", "input_admitted": True,
                "matter_version": version, "at": datetime.now(timezone.utc).isoformat(),
                "service_status": service_status}
    previous = context.rows[-1] if context.rows else {}
    row = {"contract": CONTRACT, "sequence": len(context.rows) + 1,
           "previous": previous.get("digest"), "state_version": version,
           "turn_id": context.turn_id, "matter_id": context.matter.id,
           "advocate_id": context.matter.advocate_id, "chat_id": context.chat_id,
           "message": context.message, "request": context.request, "response": response,
           "activities": deepcopy(activities),
           "records": deepcopy(records if records is not None else previous.get("records", {})),
           "work": deepcopy(work if work is not None else previous.get("work", []))}
    row["digest"] = digest(row)
    metadata = {**context.matter.intake_answers, HEADER: {
        "contract": CONTRACT, "chat_id": context.chat_id,
        "turn_count": len(context.rows) + 1, "tail_digest": row["digest"]}}
    candidate = replace(context.matter, brain_chat=(*context.rows, row),
                        intake_answers=metadata, version=version)
    checked_rows(candidate, context.matter.advocate_id)
    try:
        committed = store.commit(candidate, expected_version=context.matter.version)
    except (OSError, StaleWrite):
        try:
            committed = store.load(context.matter.id)
        except (OSError, ValueError):
            committed = None
    if committed is not None:
        for saved in checked_rows(committed, context.matter.advocate_id):
            if saved["turn_id"] == context.turn_id and saved["request"] == context.request:
                if not session_current():
                    raise ConversationRefused("Sign in again to reopen your saved conversation.",
                                              status=401, committed="committed")
                return deepcopy(saved["response"])
    raise ConversationRefused("The save could not be confirmed. Retry the same message safely.",
                              status=503, code="save_unconfirmed", committed="unconfirmed",
                              retryable=True)
