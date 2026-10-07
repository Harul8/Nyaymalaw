"""Extract private dispute and objective proposals with exact original support."""
from __future__ import annotations

from copy import deepcopy
import json

from nm.brain.message_labels import validate_label
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)

CONTRACT = "disputes_objectives_v1"
COLLECTIONS = {"disputes": "dispute", "objectives": "objective"}
_TASK = """Purpose: Identify only the disputes and desired matter outcomes
expressed in the latest message. These are internal proposals, not proved facts.

Look for:
1. Read the complete message in context. Examine meaningful portions, preserving
   their qualifications. The proposed label never excludes content from reading.
   Earlier conversation resolves references; do not repeat earlier items merely
   because they exist in the history.
2. A dispute is an expressed disagreement, contested conduct, claim, refusal or
   unresolved conflict affecting someone's position. An objective is a desired
   result in the matter: what someone wants to achieve, prevent or resolve.
   Extract each independently. Do not infer a dispute from an ordinary event or
   invent an objective for a dispute. A request for NM to perform work is not
   itself a matter objective, although it may also express one.
3. Preserve whose account, position or objective it is, including opposing or
   quoted positions, uncertainty, conditions, negations and hypothetical scope.
   Capture a correction or withdrawal as such, not as continued affirmative
   intent. Do not decide legal merit or add facts, remedies or legal conclusions.
4. Select exact continuous passages supporting each description. Include the
   current words and earlier words needed to understand them. Mark substantive
   original account as support and a reference or review instruction as context.
   NM's earlier wording is context only. A review request can authorise examining
   earlier original account; the request itself does not substantiate that account.

Outcome: Return disputes and objectives as independent arrays. Each item has a
concise attributed description, passages and uncertainty (null if no unresolved
interpretation needs recording). Each passage contains a supplied source_id,
an exact quote and purpose=support or context. Choose enough words to identify
one unambiguous occurrence while preserving relevant qualifications. Use empty
arrays when neither category is expressed. Return no general fact catalogue,
action plan, reply draft, execution status or forced pairing of the two lists."""
_FIRST_PROMPT = """Message: You receive the user's opening message, its proposed
label and a code-assigned source ID. The original words are supplied separately.

""" + _TASK
_FOLLOW_UP_PROMPT = """Message: You receive the user's latest message, its proposed
label and the complete earlier conversation in order, with source IDs, speakers
and original words. Prior NM interpretations are not original evidence.

""" + _TASK

_TEXT = {"type": "string", "minLength": 1}
_PASSAGE = {"type": "object", "additionalProperties": False,
    "required": ["source_id", "quote", "purpose"], "properties": {
        "source_id": _TEXT, "quote": _TEXT,
        "purpose": {"type": "string", "enum": ["support", "context"]}}}
_ITEM = {"type": "object", "additionalProperties": False,
    "required": ["description", "passages", "uncertainty"], "properties": {
        "description": _TEXT,
        "passages": {"type": "array", "minItems": 1, "items": _PASSAGE},
        "uncertainty": {"type": ["string", "null"]}}}
_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": list(COLLECTIONS), "properties": {
        kind: {"type": "array", "items": _ITEM} for kind in COLLECTIONS}}
_ENVELOPE = {**_SCHEMA, "properties": {kind: {"type": "array"} for kind in COLLECTIONS}}


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


def _prepare(data, sources):
    require_schema(data, _ENVELOPE)
    catalogue = _sources(sources)
    proposal, issues = {kind: [] for kind in COLLECTIONS}, []
    for kind, prefix in COLLECTIONS.items():
        for index, item in enumerate(data[kind], 1):
            identity = f"{prefix}:{index}"
            try:
                checked = _check_item(item, catalogue)
            except SchemaViolation as exc:
                issues.append({"unit": identity, "reason": str(exc),
                               "rejected_proposal": deepcopy(item)})
            else:
                proposal[kind].append({**checked, "id": identity, "state": "proposed"})
    return {"contract": CONTRACT, "state": "prepared_unreviewed", "proposal": proposal,
            "sources": deepcopy(sources), "issues": issues}


def extraction_units(prepared):
    """Check the owned saved projection without asking a model to re-interpret it."""
    if (not isinstance(prepared, dict)
            or set(prepared) != {"contract", "state", "proposal", "sources", "issues"}
            or prepared["contract"] != CONTRACT or prepared["state"] != "prepared_unreviewed"
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
            for passage in raw["passages"]:
                if not isinstance(passage, dict) or set(passage) != {"source_id", "quote", "purpose", "start", "end"}:
                    raise SchemaViolation("Saved extraction passage has an unknown shape")
                del passage["start"], passage["end"]
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
    label = validate_label({"label": label})
    if history_complete is not True or not isinstance(history, list):
        raise ValueError("Complete conversation history is required")
    earlier = [{"id": f"history_{index}", "message": deepcopy(entry)}
               for index, entry in enumerate(history, 1)]
    current = {"id": "current", "message": {"role": "advocate", "text": message}}
    sources = [*earlier, current]
    try:
        catalogue = _sources(sources)
    except SchemaViolation as exc:
        raise ValueError(str(exc)) from exc
    payload = {"proposed_label": label, "current_message": current}
    if earlier:
        payload["earlier_conversation"] = earlier
    schema = deepcopy(_SCHEMA)
    for kind in COLLECTIONS:
        schema["properties"][kind]["items"]["properties"]["passages"]["items"]["properties"]["source_id"] = {
            **_TEXT, "enum": list(catalogue)}
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
        return _prepare(result.data, sources)
    except SchemaViolation as exc:
        raise SchemaViolation(str(exc), usage=result.usage, latency_ms=result.latency_ms,
                              retries=result.retries) from exc
