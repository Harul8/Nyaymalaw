"""Extract private dispute and objective proposals with exact original support."""
from __future__ import annotations

from copy import deepcopy
import json
import re

from nm.brain.message_labels import validate_label
from nm.shared.text_contracts import split_passages
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)

# Each passage contract fixes the rule that cut the original words into
# selectable passages and the shape of a record. A saved record is always
# re-checked with the rule it was made with, so changing either needs a new
# contract, never an edit to an old one -- including any change to the shared
# sentence-end definition below.
CONTRACT = "disputes_objectives_v3"  # Sentence-end passages; titled records with an operation on saved items.
PASSAGE_LEGACY_CONTRACT = "disputes_objectives_v2"  # Cut after every . ! ? ; and line break.
LEGACY_CONTRACT = "disputes_objectives_v1"  # Model-copied quotes; no owned passages.
COLLECTIONS = {"disputes": "dispute", "objectives": "objective"}
OPERATIONS = ("new", "adds", "corrects", "contradicts", "resolves", "withdraws")
CLOSING_OPERATIONS = frozenset({"resolves", "withdraws"})
_SAVED_PREFIX = {"disputes": "D", "objectives": "O"}
_SAVED_ID = re.compile(r"[DO][1-9][0-9]*")
_RECORD_FIELDS = ("title", "description", "operation", "target_id", "passages", "uncertainty",
                  "clarification")
_TASK = """Purpose: Identify the disputes and substantive matter objectives that the
latest message reports, changes or ends, and how each relates to the saved items.
Return internal proposals only.

Look for:
1. What the account says. Read the latest message in the complete conversation.
   Separate the reported situation (conduct, events, positions) from requests for
   NM work, drafts, hypotheticals, legal theories and instructions quoted as
   content. Preserve who said what, negation, chronology, conditions and
   uncertainty. Saved items and NM's earlier wording are NM interpretations, not
   evidence. A request to use or summarise existing content reports nothing new.
2. Whether a dispute is reported. A dispute is reported adverse conduct, or
   incompatible claims, positions or rights between parties, needing a practical
   resolution. It needs no express denial, legal label, known actor or proof. An
   event is not a dispute because it happened, matters or is to be recorded, nor
   because a legal consequence or a future disagreement is possible; it becomes
   one when someone's conduct or position is reported as adverse. NM's own
   misunderstanding is interpretation work, not a party dispute.
   A matter objective is a change in the underlying situation that the message
   reports a party as wanting - such as payment, return, removal, access, or
   something done by another party - in words such as want, need, seek, demand
   or ask for. Anything the user wants NM to do - record, note, remember, review,
   summarise, advise or draft - is a work instruction and never an objective,
   however it is phrased; if a work request also states an objective, extract
   only the objective. Never infer an objective from the existence of a dispute or
   from what a party would usually want: a dispute with no stated desired result
   has no objective, so the two lists need not pair.
3. How many disputes. Group by the underlying conduct or contested right that
   needs one decision, not by sentence, speaker or source. Opposing accounts of
   the same conduct are one dispute that describes each position. A defence, a
   proof gap, missing or unacknowledged evidence, a supporting reason, a legal
   theory or an alternative remedy belongs to the dispute it concerns and is not
   a dispute of its own. Separate two disputes only when resolving one would still
   leave the other reported conflict to decide, such as a different adverse act or
   a different contested entitlement; shared parties, documents or evidence do not
   merge them.
4. How each relates to the saved items. Compare with every saved item of the same
   kind; shared words, people or sources do not make two issues one. Choose one
   operation:
   new - an issue that is not among the saved items;
   adds - a new detail, position or development of a saved item;
   corrects - the user corrects the saved account or NM's formulation of it;
   contradicts - the latest account conflicts with the saved one without being
     presented as a correction;
   resolves - the conflict is reported settled, or the objective achieved;
   withdraws - the user no longer pursues it.
   Every operation except new names that saved item in target_id; new has
   target_id null. Make at most one change to a saved item, report a change only
   when the latest message itself communicates it, and do not repeat an unchanged
   saved item.
5. Support. Select the passage IDs whose words support each item, as many as it
   needs and from any message; the boundaries are navigation aids, not units of
   meaning. Include the latest passages that report or change the item. Mark
   original account as support, and references, review instructions and NM
   wording as context. A request to check NM's saved interpretation authorises
   examining the earlier original account and a supported corrects operation; it
   does not itself substantiate that account.
6. When repair_scope is supplied, preserve its supported_records. Return only
   missing contributions or corrected replacements for unaccepted proposals; do
   not repeat supported records. Re-read original words rather than adopting a
   review formulation as evidence. For interpretation repair, describe the
   restored original dispute or objective, not the request for NM to repair it.

Outcome: Return disputes and objectives as independent arrays. Each item has:
title - a few words naming the conduct or position, adding time or place only to
  distinguish it, with no legal conclusion;
description - one neutral, attributed statement of the whole issue as it now
  stands, including each party's reported position;
operation and target_id as above;
selections - each a supplied passage_id with purpose support or context;
uncertainty - an unresolved interpretation that needs recording, otherwise null;
clarification - null unless the dispute cannot be told apart from another issue
  without one answer (for example which of two transactions it concerns); then
  one question. Never use it to gather facts, evidence, rights or legal details.
Code keeps the exact words; do not copy quotations. Use empty arrays when nothing
is reported. Return no fact catalogue, action plan, reply or completion claim."""
_FIRST_PROMPT = """Message: You receive the user's opening message as ordered
original passages with code-assigned IDs and the original speaker. There are no
saved items yet, so every item is new.

""" + _TASK
_FOLLOW_UP_PROMPT = """Message: You receive the complete earlier conversation,
the saved items and the user's latest message. Ordered original passages have
code-assigned IDs and speakers. Saved items are the open disputes (D1, D2 ...)
and objectives (O1, O2 ...) that NM recorded earlier; like prior NM wording they
are interpretations to compare against, not original evidence.

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
    "required": ["title", "description", "operation", "target_id", "selections",
                 "uncertainty", "clarification"], "properties": {
        "title": _TEXT, "description": _TEXT,
        "operation": {"type": "string", "enum": list(OPERATIONS)},
        "target_id": {"type": ["string", "null"]},
        "selections": {"type": "array", "minItems": 1, "items": _SELECTION},
        "uncertainty": {"type": ["string", "null"]},
        "clarification": {"type": ["string", "null"]}}}
_SELECTED_SCHEMA = {**_SCHEMA, "properties": {
    kind: {"type": "array", "items": _SELECTED_ITEM} for kind in COLLECTIONS}}


def _split_at_every_mark(text: str) -> list[str]:
    """The disputes_objectives_v2 rule, kept only to re-check records it made."""
    parts = []
    for part in re.split(r"(?<=[.!?;\n])", text):
        if part:
            if not part.strip() and parts:
                parts[-1] += part
            else:
                parts.append(part)
    return parts


_SEGMENTERS = {CONTRACT: split_passages, PASSAGE_LEGACY_CONTRACT: _split_at_every_mark}


def _passage_input(sources, contract=CONTRACT):
    """Present all original words once; code, not the model, owns exact spans."""
    split = _SEGMENTERS.get(contract)
    if split is None:
        raise SchemaViolation(f"Extraction contract {contract!r} has no owned passages")
    presented, choices = [], {}
    for source in sources:
        original = source["message"]
        parts = split(original["text"])
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
    return {**{key: item[key] for key in _RECORD_FIELDS if key != "passages"}, "passages": passages}


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


def _check_item(item, catalogue, contract=CONTRACT):
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
            _, owned = _passage_input([{"id": identity, "message": source}], contract)
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
        raise SchemaViolation(
            "An item needs current-message context and original advocate support. "
            "Select sources only if the latest message actually contributes to this "
            "item or requests checking NM's interpretation. Otherwise remove the "
            "out-of-scope item; empty arrays are valid. A request to use existing "
            "content for NM work is not a new contribution.")
    uncertainty = item["uncertainty"]
    if isinstance(uncertainty, str) and not uncertainty.strip():
        uncertainty = None
    return {"description": item["description"], "passages": passages,
            "uncertainty": uncertainty, "source_ids": source_ids}


def _check_record(item, catalogue, kind):
    """A current record: owned passages plus its title, operation and named saved item."""
    checked = _check_item({key: item[key] for key in ("description", "passages", "uncertainty")},
                          catalogue, CONTRACT)
    title = item["title"].strip() if isinstance(item["title"], str) else ""
    if not title:
        raise SchemaViolation("An item needs a short title naming the conduct or position")
    operation, target = item["operation"], item["target_id"]
    if operation not in OPERATIONS:
        raise SchemaViolation(f"Unknown operation {operation!r}")
    if (operation == "new") != (target is None):
        raise SchemaViolation("A new item names no saved item; every change names exactly one")
    if target is not None and (not isinstance(target, str) or not _SAVED_ID.fullmatch(target)
                               or target[0] != _SAVED_PREFIX[kind]):
        raise SchemaViolation(f"A {COLLECTIONS[kind]} change must name a saved {COLLECTIONS[kind]}")
    clarification = item["clarification"]
    if clarification is not None:
        if not isinstance(clarification, str):
            raise SchemaViolation("A clarification is one question or null")
        clarification = clarification.strip() or None
    return {"title": title, "description": checked["description"], "operation": operation,
            "target_id": target, "passages": checked["passages"],
            "uncertainty": checked["uncertainty"], "clarification": clarification,
            "source_ids": checked["source_ids"]}


def _checked_saved(saved):
    """Open saved items as the turn owner derived them: {ID: kind}."""
    if not isinstance(saved, (list, tuple)):
        raise ValueError("Saved items must be a list")
    owned = {}
    for row in saved:
        if (not isinstance(row, dict) or set(row) != {"id", "kind", "title", "description"}
                or row["kind"] not in COLLECTIONS or not isinstance(row["id"], str)
                or not _SAVED_ID.fullmatch(row["id"]) or row["id"][0] != _SAVED_PREFIX[row["kind"]]
                or row["id"] in owned
                or any(not isinstance(row[key], str) or not row[key].strip()
                       for key in ("title", "description"))):
            raise ValueError("Each saved item needs its owned ID, kind, title and description")
        owned[row["id"]] = row["kind"]
    return owned


def _prepare(data, sources, *, choices=None, saved=()):
    require_schema(data, _ENVELOPE)
    catalogue = _sources(sources)
    contract = CONTRACT if choices is not None else LEGACY_CONTRACT
    open_ids = _checked_saved(saved)
    proposal, issues, changed = {kind: [] for kind in COLLECTIONS}, [], set()
    for kind, prefix in COLLECTIONS.items():
        for index, item in enumerate(data[kind], 1):
            identity = f"{prefix}:{index}"
            try:
                if choices is None:
                    checked = _check_item(item, catalogue, contract)
                else:
                    checked = _check_record(_resolve_selections(item, choices), catalogue, kind)
                    target = checked["target_id"]
                    if target is not None:
                        if open_ids.get(target) != kind:
                            raise SchemaViolation(
                                f"{target} is not an open saved {COLLECTIONS[kind]}; use operation new "
                                "for an issue that is not saved, or name the open saved item it changes")
                        if target in changed:
                            raise SchemaViolation(f"{target} already has a change from this message")
                        changed.add(target)
            except SchemaViolation as exc:
                issues.append({"unit": identity, "reason": str(exc),
                               "rejected_proposal": deepcopy(item)})
            else:
                proposal[kind].append({**checked, "id": identity, "state": "proposed"})
    return {"contract": contract,
            "state": "prepared_unreviewed", "proposal": proposal,
            "sources": deepcopy(sources), "issues": issues}


def extraction_units(prepared):
    """Check the owned saved projection without asking a model to re-interpret it."""
    if (not isinstance(prepared, dict)
            or set(prepared) != {"contract", "state", "proposal", "sources", "issues"}
            or prepared["contract"] not in (CONTRACT, PASSAGE_LEGACY_CONTRACT, LEGACY_CONTRACT)
            or prepared["state"] != "prepared_unreviewed"
            or not isinstance(prepared["proposal"], dict)
            or set(prepared["proposal"]) != set(COLLECTIONS)
            or not isinstance(prepared["issues"], list)):
        raise SchemaViolation("Unknown dispute/objective extraction contract")
    contract = prepared["contract"]
    record_keys = ({"id", "state", "source_ids", *_RECORD_FIELDS} if contract == CONTRACT
                   else {"id", "state", "description", "passages", "uncertainty", "source_ids"})
    catalogue, units, changed = _sources(prepared["sources"]), {}, set()
    for kind, prefix in COLLECTIONS.items():
        if not isinstance(prepared["proposal"][kind], list):
            raise SchemaViolation("Extraction needs both collections")
        for item in prepared["proposal"][kind]:
            if (not isinstance(item, dict)
                    or set(item) != record_keys
                    or not isinstance(item["id"], str) or not item["id"].startswith(prefix + ":")
                    or not item["id"][len(prefix) + 1:].isdigit()
                    or int(item["id"][len(prefix) + 1:]) < 1 or item["id"] in units
                    or item["state"] != "proposed" or not isinstance(item["passages"], list)):
                raise SchemaViolation("Extraction item has an inconsistent owned identity or shape")
            passage_fields = {"source_id", "quote", "purpose", "start", "end"}
            if contract in _SEGMENTERS:
                passage_fields.add("passage_id")
            for passage in item["passages"]:
                if not isinstance(passage, dict) or set(passage) != passage_fields:
                    raise SchemaViolation("Saved extraction passage has an unknown shape")
            if contract == CONTRACT:
                checked = _check_record({key: deepcopy(item[key]) for key in _RECORD_FIELDS},
                                        catalogue, kind)
                if checked["target_id"] is not None:
                    if checked["target_id"] in changed:
                        raise SchemaViolation("Two saved changes name the same item")
                    changed.add(checked["target_id"])
            else:
                checked = _check_item({key: deepcopy(item[key])
                                       for key in ("description", "passages", "uncertainty")},
                                      catalogue, contract)
            if {**checked, "id": item["id"], "state": "proposed"} != item:
                raise SchemaViolation("Saved extraction differs from its exact original passage")
            units[item["id"]] = {"kind": kind, "proposal": deepcopy(item)}
    held = set()
    for issue in prepared["issues"]:
        if (not isinstance(issue, dict) or set(issue) != {"unit", "reason", "rejected_proposal"}
                or not isinstance(issue["unit"], str) or issue["unit"] in units or issue["unit"] in held
                or issue["unit"].partition(":")[0] not in COLLECTIONS.values()
                or not issue["unit"].partition(":")[2].isdigit()
                or int(issue["unit"].partition(":")[2]) < 1
                or not isinstance(issue["reason"], str) or not issue["reason"].strip()):
            raise SchemaViolation("Extraction has an inconsistent held unit")
        held.add(issue["unit"])
    return units


def open_items(turns) -> list[dict]:
    """The disputes and objectives still open after the saved turns, with stable IDs.

    `turns` is the ordered saved conversation as (units, accepted) pairs: the
    checked extraction units of each turn and the unit IDs its independent review
    accepted. Items are numbered D1, D2 ... and O1, O2 ... in order of first
    acceptance, so replaying the same turns reproduces every ID. A change updates
    the item it names; a resolution or withdrawal closes it, so older wording
    cannot revive it. Records from earlier contracts only ever introduced items.
    """
    order = list(COLLECTIONS)
    items, counts = {}, {kind: 0 for kind in COLLECTIONS}
    for units, accepted in turns:
        ranked = sorted(((identity, unit) for identity, unit in units.items()
                         if unit["kind"] in COLLECTIONS and identity in accepted),
                        key=lambda pair: (order.index(pair[1]["kind"]), int(pair[0].split(":")[1])))
        for _, unit in ranked:
            kind, proposal = unit["kind"], unit["proposal"]
            operation = proposal.get("operation", "new")
            if operation == "new":
                counts[kind] += 1
                identity = f"{_SAVED_PREFIX[kind]}{counts[kind]}"
                items[identity] = {"id": identity, "kind": kind,
                                   "title": proposal.get("title") or proposal["description"],
                                   "description": proposal["description"], "open": True}
                continue
            target = items.get(proposal.get("target_id"))
            if target is None or target["kind"] != kind or not target["open"]:
                raise SchemaViolation("A saved change names no open item of its kind")
            if operation in CLOSING_OPERATIONS:
                target["open"] = False
            else:
                target.update(title=proposal["title"], description=proposal["description"])
    return [{key: value for key, value in item.items() if key != "open"}
            for item in items.values() if item["open"]]


def check_targets(units, saved):
    """Every change in a saved extraction names an item that was open when it was made."""
    open_ids = _checked_saved(saved)
    for identity, unit in units.items():
        target = unit["proposal"].get("target_id")
        if target is not None and open_ids.get(target) != unit["kind"]:
            raise SchemaViolation(f"{identity} names {target}, which was not an open saved item")


def _presented_saved(saved):
    return [{"id": row["id"], "kind": COLLECTIONS[row["kind"]], "title": row["title"],
             "description": row["description"]} for row in saved]


def extract_disputes_objectives(model: ModelPort, message: str, *, label: str,
                               history: list[dict], history_complete: bool,
                               saved=(), _repair_scope=None) -> dict:
    """One focused call; the turn owns correction, independent review and saving."""
    validate_label({"label": label})  # Diagnostic label never supplies extraction meaning.
    if history_complete is not True or not isinstance(history, list):
        raise ValueError("Complete conversation history is required")
    open_ids = _checked_saved(saved)
    if open_ids and not history:
        raise ValueError("Saved items need the earlier conversation they came from")
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
    if earlier:
        payload["saved_items"] = _presented_saved(saved)
    payload["current_message"] = presented[-1]
    if _repair_scope is not None:
        payload["repair_scope"] = deepcopy(_repair_scope)
    schema = deepcopy(_SELECTED_SCHEMA)
    for kind in COLLECTIONS:
        # Each kind needs its own copy: its saved-item choices differ (D... or O...).
        schema["properties"][kind]["items"] = deepcopy(_SELECTED_ITEM)
        properties = schema["properties"][kind]["items"]["properties"]
        properties["selections"]["items"]["properties"]["passage_id"] = {**_TEXT, "enum": list(choices)}
        targets = [identity for identity, owner in open_ids.items() if owner == kind]
        properties["target_id"] = ({"anyOf": [{"type": "string", "enum": targets}, {"type": "null"}]}
                                   if targets else {"type": "null"})
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
        return _prepare(result.data, sources, choices=choices, saved=saved)
    except SchemaViolation as exc:
        raise SchemaViolation(str(exc), usage=result.usage, latency_ms=result.latency_ms,
                              retries=result.retries) from exc


def repair_disputes_objectives(model, prepared, *, supported_unit_ids, gaps, saved=()):
    """One repair call; preserve checked peers and assign fresh owned proposal IDs.

    The caller owns the review, shared allowance and durable attempt lineage.
    This returns proposals, not proof that the repair succeeded.
    """
    units = extraction_units(prepared)
    if prepared["contract"] != CONTRACT:
        raise SchemaViolation("Extraction repair requires the current passage-owned contract")
    check_targets(units, saved)
    if (not isinstance(supported_unit_ids, list) or any(not isinstance(identity, str) for identity in supported_unit_ids)
            or len(set(supported_unit_ids)) != len(supported_unit_ids)
            or any(identity not in units for identity in supported_unit_ids)):
        raise SchemaViolation("Extraction repair needs owned supported unit identities")
    catalogue = _sources(prepared["sources"])
    if not isinstance(gaps, list):
        raise SchemaViolation("Extraction repair needs checked missing contributions")
    for gap in gaps:
        if (not isinstance(gap, dict) or gap.get("kind") not in COLLECTIONS
                or any(key not in gap for key in ("id", "description", "passages", "uncertainty"))):
            raise SchemaViolation("Extraction repair gap has an unknown category")
        checked = _check_item({key: deepcopy(gap[key]) for key in ("description", "passages", "uncertainty")}, catalogue)
        if any(checked[key] != gap.get(key) for key in checked):
            raise SchemaViolation("Extraction repair gap differs from its owned original support")

    def presentation(kind, unit):
        shown = {"id": unit["id"], "kind": kind, "description": unit["description"],
                 "selections": [{"passage_id": span["passage_id"], "purpose": span["purpose"]}
                                for span in unit["passages"]], "uncertainty": unit["uncertainty"]}
        for key in ("title", "operation", "target_id", "contribution"):
            if key in unit:
                shown[key] = unit[key]
        return shown

    supported = set(supported_unit_ids)
    scope = {"supported_records": [presentation(row["kind"], row["proposal"])
                                   for identity, row in units.items() if identity in supported],
        "unaccepted_proposals": [presentation(row["kind"], row["proposal"])
                                 for identity, row in units.items() if identity not in supported],
        "missing_contributions": [presentation(gap["kind"], gap) for gap in gaps],
        "held_proposals": deepcopy(prepared["issues"])}
    sources = prepared["sources"]
    repaired = extract_disputes_objectives(model, sources[-1]["message"]["text"], label="information",
        history=[deepcopy(source["message"]) for source in sources[:-1]], history_complete=True,
        saved=saved, _repair_scope=scope)
    if repaired["sources"] != sources:
        raise SchemaViolation("Extraction repair changed the original source binding")
    merged = deepcopy(repaired)
    offsets = {prefix: max([0, *[int(identity.split(":")[1]) for identity in units
                                if identity.startswith(prefix + ":")],
                           *[int(issue["unit"].split(":")[1]) for issue in prepared["issues"]
                             if issue["unit"].startswith(prefix + ":")]])
               for prefix in COLLECTIONS.values()}
    for kind, prefix in COLLECTIONS.items():
        peers = [deepcopy(row) for row in prepared["proposal"][kind] if row["id"] in supported]
        additions = []
        for row in merged["proposal"][kind]:
            # Only exact repetition is mechanically redundant. Meaning and
            # relationships of differently worded proposals need model review.
            body = {key: value for key, value in row.items() if key != "id"}
            if any(body == {key: value for key, value in peer.items() if key != "id"} for peer in peers):
                continue
            row["id"] = f"{prefix}:{offsets[prefix] + int(row['id'].split(':')[1])}"
            additions.append(row)
        merged["proposal"][kind] = [*peers, *additions]
    for issue in merged["issues"]:
        prefix, index = issue["unit"].split(":")
        issue["unit"] = f"{prefix}:{offsets[prefix] + int(index)}"
    check_targets(extraction_units(merged), saved)
    return merged
