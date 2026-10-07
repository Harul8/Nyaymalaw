"""Extract private dispute and objective proposals with exact original support."""
from __future__ import annotations

from copy import deepcopy
import json
import re

from nm.brain.message_labels import validate_label
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)

CONTRACT = "disputes_objectives_v2"
LEGACY_CONTRACT = "disputes_objectives_v1"
COLLECTIONS = {"disputes": "dispute", "objectives": "objective"}
_TASK = """Purpose: Identify only the disputes and substantive matter objectives
communicated or revised by the latest message. Return internal proposals only.

Look for:
1. Start with what the latest message contributes. Earlier messages resolve its
   references; they are not a backlog to extract again. A social exchange, neutral
   background or instruction about NM's work alone contributes neither category.
   Return empty arrays when the latest message contributes no dispute or objective.
2. A dispute is an expressed disagreement, contested conduct, claim, refusal or
   unresolved conflict affecting someone's position in the underlying situation.
   A matter objective is a party's desired substantive result in that situation.
   Producing an NM output or controlling how NM works is a work instruction, not
   that substantive result. If a work request also states a matter objective,
   extract only that objective. Do not infer a conflict from an ordinary event,
   invent an objective for a dispute, or force the two collections to be paired.
3. Preserve whose account, position or objective it is, including opposing or
   quoted positions, uncertainty, conditions, negations and hypothetical scope.
   Capture a correction or withdrawal as such, not as continued affirmative
   intent. Do not decide legal merit or add facts, remedies or legal conclusions.
4. Select the supplied passage IDs supporting each description. The selected
   current words must communicate, revise or specifically request review of that
   item; mere conversation continuity is insufficient. Include earlier words only
   when needed to understand this contribution. Mark substantive
   original account as support and a reference or review instruction as context.
   NM's earlier wording is context only. A review request can authorise examining
   earlier original account; the request itself does not substantiate that account.

Outcome: Return disputes and objectives as independent arrays. Each item has a
concise attributed description, selections and uncertainty (null if no unresolved
interpretation needs recording). Each selection contains a supplied passage_id
and purpose=support or context. The complete original messages are shown as
ordered selectable passages. These boundaries are navigation aids, not units of
meaning; select several when needed to preserve context and qualifications.
Code retains their exact words; do not copy or rewrite quotations. Use empty
arrays when neither category is expressed. Return no general fact catalogue,
action plan, reply draft, execution status or forced pairing of the two lists."""
_FIRST_PROMPT = """Message: You receive the user's opening message as ordered
original passages with code-assigned IDs and the original speaker.

""" + _TASK
_FOLLOW_UP_PROMPT = """Message: You receive the complete earlier conversation,
followed by the user's latest message. Ordered original passages have code-assigned
IDs and speakers. Prior NM interpretations are not original evidence.

""" + _TASK

_TEXT = {"type": "string", "minLength": 1}
_PASSAGE = {"type": "object", "additionalProperties": False,
    "required": ["source_id", "quote", "purpose"], "properties": {
        "source_id": _TEXT, "quote": _TEXT,
        "purpose": {"type": "string", "enum": ["support", "context"]},
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1}, "passage_id": _TEXT}}
_ITEM = {"type": "object", "additionalProperties": False,
    "required": ["description", "passages", "uncertainty"], "properties": {
        "description": _TEXT,
        "passages": {"type": "array", "minItems": 1, "items": _PASSAGE},
        "uncertainty": {"type": ["string", "null"]}}}
_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": list(COLLECTIONS), "properties": {
        kind: {"type": "array", "items": _ITEM} for kind in COLLECTIONS}}
_ENVELOPE = {**_SCHEMA, "properties": {kind: {"type": "array"} for kind in COLLECTIONS}}
_SELECTION = {"type": "object", "additionalProperties": False,
    "required": ["passage_id", "purpose"], "properties": {
        "passage_id": _TEXT, "purpose": _PASSAGE["properties"]["purpose"]}}
_SELECTED_ITEM = {"type": "object", "additionalProperties": False,
    "required": ["description", "selections", "uncertainty"], "properties": {
        "description": _TEXT,
        "selections": {"type": "array", "minItems": 1, "items": _SELECTION},
        "uncertainty": {"type": ["string", "null"]}}}
_SELECTED_SCHEMA = {**_SCHEMA, "properties": {
    kind: {"type": "array", "items": _SELECTED_ITEM} for kind in COLLECTIONS}}


def _passage_input(sources):
    """Present all original words once; code, not the model, owns exact spans."""
    presented, choices = [], {}
    for source in sources:
        original = source["message"]
        parts = []
        for part in re.split(r"(?<=[.!?;\n])", original["text"]):
            if part:
                if not part.strip() and parts:
                    parts[-1] += part
                else:
                    parts.append(part)
        offset, passages = 0, []
        for index, part in enumerate(parts, 1):
            identity = f"{source['id']}:p{index}"
            choices[identity] = {"source_id": source["id"], "quote": part,
                                 "start": offset, "end": offset + len(part)}
            passages.append({"id": identity, "text": part})
            offset += len(part)
        presented.append({"id": source["id"], "message": {
            **{key: deepcopy(value) for key, value in original.items() if key != "text"},
            "passages": passages}})
    return presented, choices


def _resolve_selections(item, choices):
    require_schema(item, _SELECTED_ITEM)
    passages = []
    for selection in item["selections"]:
        choice = choices.get(selection["passage_id"])
        if choice is None:
            raise SchemaViolation(f"Unknown selected passage {selection['passage_id']}")
        passages.append({**deepcopy(choice), "passage_id": selection["passage_id"],
                         "purpose": selection["purpose"]})
    return {"description": item["description"], "passages": passages,
            "uncertainty": item["uncertainty"]}


def _sources(sources):
    if not isinstance(sources, list) or not sources:
        raise SchemaViolation("Extraction needs the complete ordered original sources")
    catalogue = {}
    for index, source in enumerate(sources):
        identity = "current" if index == len(sources) - 1 else f"history_{index + 1}"
        if (not isinstance(source, dict) or set(source) != {"id", "message"}
                or source["id"] != identity or not isinstance(source["message"], dict)):
            raise SchemaViolation("Extraction sources need their owned ordered identities")
        message = source["message"]
        if (message.get("role") not in ("advocate", "nm")
                or not isinstance(message.get("text"), str) or not message["text"].strip()
                or identity == "current" and message["role"] != "advocate"):
            raise SchemaViolation("Extraction sources need the original speaker and words")
        catalogue[identity] = message
    return catalogue


def _check_item(item, catalogue):
    require_schema(item, _ITEM)
    if not item["description"].strip():
        raise SchemaViolation("The extracted description is blank")
    passages, support = [], False
    for passage in item["passages"]:
        identity, quote = passage["source_id"], passage["quote"]
        source = catalogue.get(identity)
        if source is None:
            raise SchemaViolation(f"Passage selected unknown source {identity}")
        if not quote.strip():
            raise SchemaViolation(f"Passage in {identity} is blank")
        if "passage_id" in passage:
            _, owned = _passage_input([{"id": identity, "message": source}])
            choice = owned.get(passage["passage_id"])
            if choice is None or any(passage.get(key) != value for key, value in choice.items()):
                raise SchemaViolation(f"Selected passage in {identity} differs from its owned identity")
        if "start" in passage or "end" in passage:
            start, end = passage.get("start"), passage.get("end")
            if (start is None or end is None or end > len(source["text"])
                    or source["text"][start:end] != quote):
                raise SchemaViolation(f"Passage endpoints in {identity} differ from the original words")
        else:
            # Historical quote-selected records retain their original check.
            start = source["text"].find(quote)
            if start < 0:
                raise SchemaViolation(f"Quote in {identity} is not exact original text: {quote!r}")
            if source["text"].find(quote, start + 1) >= 0:
                raise SchemaViolation(f"Quote in {identity} occurs more than once; select a wider unique passage: {quote!r}")
        if passage["purpose"] == "support":
            if source["role"] != "advocate":
                raise SchemaViolation(f"NM source {identity} cannot substantiate its own interpretation")
            support = True
        checked = {**deepcopy(passage), "start": start, "end": start + len(quote)}
        if checked not in passages:
            passages.append(checked)
    source_ids = list(dict.fromkeys(row["source_id"] for row in passages))
    if "current" not in source_ids or not support:
        raise SchemaViolation("An item needs current-message context and original advocate support")
    uncertainty = item["uncertainty"]
    if isinstance(uncertainty, str) and not uncertainty.strip():
        uncertainty = None
    return {"description": item["description"], "passages": passages,
            "uncertainty": uncertainty, "source_ids": source_ids}


def _prepare(data, sources, *, choices=None):
    require_schema(data, _ENVELOPE)
    catalogue = _sources(sources)
    proposal, issues = {kind: [] for kind in COLLECTIONS}, []
    for kind, prefix in COLLECTIONS.items():
        for index, item in enumerate(data[kind], 1):
            identity = f"{prefix}:{index}"
            try:
                selected = _resolve_selections(item, choices) if choices is not None else item
                checked = _check_item(selected, catalogue)
            except SchemaViolation as exc:
                issues.append({"unit": identity, "reason": str(exc),
                               "rejected_proposal": deepcopy(item)})
            else:
                proposal[kind].append({**checked, "id": identity, "state": "proposed"})
    return {"contract": CONTRACT if choices is not None else LEGACY_CONTRACT,
            "state": "prepared_unreviewed", "proposal": proposal,
            "sources": deepcopy(sources), "issues": issues}


def extraction_units(prepared):
    """Check the owned saved projection without asking a model to re-interpret it."""
    if (not isinstance(prepared, dict)
            or set(prepared) != {"contract", "state", "proposal", "sources", "issues"}
            or prepared["contract"] not in (CONTRACT, LEGACY_CONTRACT) or prepared["state"] != "prepared_unreviewed"
            or not isinstance(prepared["proposal"], dict)
            or set(prepared["proposal"]) != set(COLLECTIONS)
            or not isinstance(prepared["issues"], list)):
        raise SchemaViolation("Unknown dispute/objective extraction contract")
    catalogue, units = _sources(prepared["sources"]), {}
    for kind, prefix in COLLECTIONS.items():
        if not isinstance(prepared["proposal"][kind], list):
            raise SchemaViolation("Extraction needs both collections")
        for item in prepared["proposal"][kind]:
            if (not isinstance(item, dict)
                    or set(item) != {"id", "state", "description", "passages", "uncertainty", "source_ids"}
                    or not isinstance(item["id"], str) or not item["id"].startswith(prefix + ":")
                    or not item["id"][len(prefix) + 1:].isdigit()
                    or int(item["id"][len(prefix) + 1:]) < 1 or item["id"] in units
                    or item["state"] != "proposed" or not isinstance(item["passages"], list)):
                raise SchemaViolation("Extraction item has an inconsistent owned identity or shape")
            raw = {key: deepcopy(item[key]) for key in ("description", "passages", "uncertainty")}
            passage_fields = {"source_id", "quote", "purpose", "start", "end"}
            if prepared["contract"] == CONTRACT:
                passage_fields.add("passage_id")
            for passage in raw["passages"]:
                if not isinstance(passage, dict) or set(passage) != passage_fields:
                    raise SchemaViolation("Saved extraction passage has an unknown shape")
            checked = {**_check_item(raw, catalogue), "id": item["id"], "state": "proposed"}
            if checked != item:
                raise SchemaViolation("Saved extraction differs from its exact original passage")
            units[item["id"]] = {"kind": kind, "proposal": deepcopy(item)}
    held = set()
    for issue in prepared["issues"]:
        if (not isinstance(issue, dict) or set(issue) != {"unit", "reason", "rejected_proposal"}
                or not isinstance(issue["unit"], str) or issue["unit"] in units or issue["unit"] in held
                or not isinstance(issue["reason"], str) or not issue["reason"].strip()):
            raise SchemaViolation("Extraction has an inconsistent held unit")
        held.add(issue["unit"])
    return units


def extract_disputes_objectives(model: ModelPort, message: str, *, label: str,
                               history: list[dict], history_complete: bool) -> dict:
    """One focused call; the turn owns correction, independent review and saving."""
    validate_label({"label": label})  # Diagnostic label never supplies extraction meaning.
    if history_complete is not True or not isinstance(history, list):
        raise ValueError("Complete conversation history is required")
    earlier = [{"id": f"history_{index}", "message": deepcopy(entry)}
               for index, entry in enumerate(history, 1)]
    current = {"id": "current", "message": {"role": "advocate", "text": message}}
    sources = [*earlier, current]
    try:
        _sources(sources)
    except SchemaViolation as exc:
        raise ValueError(str(exc)) from exc
    presented, choices = _passage_input(sources)
    payload = {"earlier_conversation": presented[:-1]} if earlier else {}
    payload["current_message"] = presented[-1]
    schema = deepcopy(_SELECTED_SCHEMA)
    for kind in COLLECTIONS:
        schema["properties"][kind]["items"]["properties"]["selections"]["items"]["properties"]["passage_id"] = {
            **_TEXT, "enum": list(choices)}
    prompt = Prompt(system=_FOLLOW_UP_PROMPT if earlier else _FIRST_PROMPT,
                    user=json.dumps(payload, ensure_ascii=False), operation="extract_disputes_objectives")
    limit = max(2048, estimate_tokens(message) * 4)
    if estimate_tokens(prompt.system + prompt.user + json.dumps(schema)) + limit > model.context_budget(Tier.ROUTINE):
        raise ContextOverflow("The complete dispute/objective extraction exceeds the context budget")
    try:
        result = model.structured(prompt, schema, Tier.ROUTINE, max_tokens=limit)
    except SchemaViolation as exc:
        if exc.rejected_result is None:
            raise
        result = exc.rejected_result
    if not result.usable:
        raise ModelError("Dispute/objective extraction did not complete", usage=result.usage,
                         latency_ms=result.latency_ms, retries=result.retries)
    try:
        if result.text is not None:
            raise SchemaViolation("Extraction requires structured proposals, not response prose")
        return _prepare(result.data, sources, choices=choices)
    except SchemaViolation as exc:
        raise SchemaViolation(str(exc), usage=result.usage, latency_ms=result.latency_ms,
                              retries=result.retries) from exc
