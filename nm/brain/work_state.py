"""Project scoped work and questions from the one released conversation record."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from nm.brain.conversation import IncompleteConversation
from nm.brain.source_snapshots import source_snapshots

PROGRESS_STATUSES = (
    "pending", "complete", "promised", "unavailable", "deferred", "cancelled")
PROGRESS_KINDS = ("task", "question")
PROGRESS_VERSION = 2
_SECTIONS = (("questions", "question"), ("next_work", "task"))
_SUFFICIENCY = ("complete", "partial", "needs_input", "not_completed")


def _fail(reason: str) -> None:
    raise IncompleteConversation("The saved work progress is incomplete: " + reason)


def _text(value: object, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail("an attributable value is missing")
    return value


def _ids(value: object) -> list[str]:
    if (not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(value) != len(set(value))):
        _fail("reference identities are invalid")
    return value


def _progress_id(matter_id: str, turn_id: str, request_index: int,
                 section: str, local_id: str = "") -> str:
    identity = dict(matter_id=matter_id, turn_id=turn_id,
                    request_index=request_index, section=section, local_id=local_id)
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "wp_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _catalogue(progress: dict) -> dict[str, dict]:
    if not isinstance(progress, dict) or progress.get("state") != "ok":
        _fail("the prior progress catalogue is unreadable")
    rows = progress.get("rows")
    if not isinstance(rows, list):
        _fail("the prior progress catalogue has no rows")
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or row.get("kind") not in PROGRESS_KINDS
                or row.get("status") not in PROGRESS_STATUSES):
            _fail("a prior progress entry is unreadable")
        identity = _text(row.get("id"))
        _text(row.get("text"))
        if identity in result:
            _fail("prior progress identities conflict")
        result[identity] = row
    return result


def _blocks(unit: dict) -> dict[str, dict]:
    rows = unit.get("blocks")
    if (not isinstance(rows, list) or not rows
            or unit.get("verification") != "source_aware_continuation_v1"):
        _fail("a progress unit has no checked displayed owner")
    blocks = {}
    for block in rows:
        if not isinstance(block, dict):
            _fail("a progress block is unreadable")
        identity = _text(block.get("id"))
        _text(block.get("text"))
        for field in ("span_ids", "record_ids", "legal_source_ids"):
            _ids(block.get(field))
        if identity in blocks or not isinstance(block.get("references"), list):
            _fail("displayed progress identities conflict")
        try:
            source_snapshots(block["references"])
        except ValueError as exc:
            _fail(str(exc))
        references = {item["id"]: item for item in block["references"]}
        selected = [*block["span_ids"], *block["record_ids"], *block["legal_source_ids"]]
        if len(selected) != len(set(selected)) or set(selected) != references.keys():
            _fail("a displayed progress source cannot be resolved")
        for identity in block["span_ids"]:
            if references[identity].get("type") != "conversation":
                _fail("an attributed span has the wrong source kind")
        for identity in block["record_ids"]:
            if references[identity].get("type") not in ("dispute", "material", "requirement"):
                _fail("a record has the wrong source kind")
        for identity in block["legal_source_ids"]:
            if references[identity].get("type") != "legal":
                _fail("a legal passage has the wrong source kind")
        blocks[block["id"]] = block
    sufficiency = unit.get("sufficiency")
    if (not isinstance(sufficiency, dict)
            or sufficiency.get("status") not in _SUFFICIENCY
            or sufficiency.get("block_id") not in blocks):
        _fail("task sufficiency has no displayed explanation")
    return blocks


def _known(identity: str, kind: str, previous: dict) -> None:
    if identity and (identity not in previous or previous[identity]["kind"] != kind):
        _fail("a progress link has no authorised prior owner")


def _update(update: dict, previous: dict, blocks: dict) -> dict:
    if not isinstance(update, dict):
        _fail("a progress transition is unreadable")
    target = update.get("target_id")
    if target not in previous or update.get("status") not in PROGRESS_STATUSES:
        _fail("a progress transition names an unknown entry or state")
    block = blocks.get(update.get("block_id"))
    if block is None:
        _fail("a progress transition has no displayed explanation")
    _text(update.get("reason"))
    spans = _ids(update.get("span_ids"))
    advocate_spans = {reference["id"] for reference in block["references"]
                      if reference.get("type") == "conversation"
                      and reference.get("role") == "advocate"}
    if not set(spans) <= set(block["span_ids"]) & advocate_spans:
        _fail("a progress transition has no attributable advocate span")
    needs_answer = previous[target]["kind"] == "question" and update["status"] == "complete"
    if (needs_answer or update["status"] in (
            "promised", "unavailable", "deferred", "cancelled")) and not spans:
        _fail("a progress transition needs the advocate's supporting words")
    if not block["references"]:
        _fail("a progress transition has no source support")
    return block


def seal_progress(continuation: dict, *, matter_id: str, turn_id: str,
                  plan, prior_progress: dict) -> dict:
    """Assign stable identities only to independently accepted request units."""
    _text(matter_id)
    _text(turn_id)
    previous = _catalogue(prior_progress)
    result = deepcopy(continuation)
    if not isinstance(result, dict) or not isinstance(result.get("units"), list):
        _fail("the continuation is unreadable")
    seen = set()
    updated_ids = set()
    for unit in result["units"]:
        if not isinstance(unit, dict):
            _fail("a continuation unit is unreadable")
        index = unit.get("request_index")
        if type(index) is not int or not 0 <= index < len(plan.items) or index in seen:
            _fail("a continuation unit has no interpreted scope")
        seen.add(index)
        if "progress_version" in unit:
            _fail("a model proposal already contains server progress metadata")
        blocks = _blocks(unit)
        item = plan.items[index]
        intent = getattr(item, "intent", None)
        if intent not in ("request", "contribution"):
            _fail("the interpreted work has no request or contribution intent")
        if not isinstance(unit.get("work"), dict):
            _fail("a scoped work association is unreadable")
        unit["work"].update(request=item.request, relation=item.relation,
                            matter_scope=item.matter_scope, intent=intent)
        _seal_unit(unit, previous, blocks, matter_id, turn_id, index)
        targets = {update["target_id"] for update in unit["progress_updates"]}
        if targets & updated_ids:
            _fail("different request units claim the same progress transition")
        updated_ids.update(targets)
        unit["progress_version"] = PROGRESS_VERSION
    return result


def _seal_unit(unit: dict, previous: dict, blocks: dict, matter_id: str,
               turn_id: str, index: int, *, sealed: bool = False,
               strict: bool = True) -> None:
    work = unit.get("work")
    if not isinstance(work, dict) or type(work.get("create")) is not bool:
        _fail("a scoped work association is unreadable")
    existing = _text(work.get("existing_id"), empty=True)
    if existing and work["create"]:
        _fail("a work association cannot create and reuse an entry")
    _known(existing, "task", previous)
    intent = work.get("intent")
    if intent is None and strict:
        _fail("work intent was not supplied by interpretation")
    if intent not in (None, "request", "contribution"):
        _fail("a work intent is invalid")
    if strict and intent == "request" and not (existing or work["create"]):
        _fail("a requested outcome has no durable task association")
    if strict and intent == "contribution" and work["create"]:
        _fail("a contribution cannot create an unrequested task")
    work["progress_id"] = (existing or _progress_id(matter_id, turn_id, index, "request")
                           if existing or work["create"] else "")
    owned_blocks = set()
    for section, kind in _SECTIONS:
        links = unit.get(section)
        if not isinstance(links, list):
            _fail("question or work proposals are unreadable")
        seen = set()
        for link in links:
            if not isinstance(link, dict):
                _fail("a question or work proposal is unreadable")
            identity = _text(link.get("id"))
            existing = _text(link.get("existing_id"), empty=True)
            if (identity in seen or link.get("block_id") not in blocks
                    or (strict and link["block_id"] in owned_blocks)):
                _fail("a question or work proposal has no distinct displayed owner")
            seen.add(identity)
            owned_blocks.add(link["block_id"])
            _text(link.get("purpose"))
            _ids(link.get("target_ids"))
            _known(existing, kind, previous)
            link["progress_id"] = existing or _progress_id(
                matter_id, turn_id, index, section, identity)
    updates = unit.get("progress_updates")
    if not isinstance(updates, list):
        _fail("progress transitions are unreadable")
    seen = set()
    available = dict(previous)
    if work["progress_id"]:
        available.setdefault(work["progress_id"], {"kind": "task"})
    for update in updates:
        if not isinstance(update, dict):
            _fail("a progress transition is unreadable")
        target = update.get("target_id")
        if target == "$work":
            if not work["progress_id"]:
                _fail("the local work reference has no selected task")
            update["target_id"] = work["progress_id"]
        elif target not in previous and not (
                sealed and target == work["progress_id"] and work["create"]):
            _fail("a progress transition names an unknown entry")
        _update(update, available, blocks)
        if update["target_id"] in seen:
            _fail("a unit gives conflicting transitions to one entry")
        seen.add(update["target_id"])
    reopening = {update["target_id"] for update in updates if update["status"] == "pending"}
    for section, _ in _SECTIONS:
        for link in unit[section]:
            identity = link["existing_id"]
            if identity and previous[identity]["status"] != "pending" and identity not in reopening:
                _fail("a resolved or suspended proposal was repeated without a supported change")


def _read_words(prior_conversation, turns: tuple) -> dict[tuple[str, str], str]:
    words = {}

    def remember(turn_id: str, role: str, text: str) -> None:
        key = (_text(turn_id), role)
        _text(text)
        if key in words and words[key] != text:
            _fail("conversation words conflict")
        words[key] = text

    for message in prior_conversation:
        remember(message.turn_id, message.role, message.text)
    seen = set()
    for row in turns:
        if not isinstance(row, dict) or row.get("turn_id") in seen:
            _fail("saved turn identities conflict")
        turn_id = _text(row.get("turn_id"))
        seen.add(turn_id)
        response = row.get("response")
        if (not isinstance(response, dict) or response.get("turn_id") != turn_id
                or row.get("committed") is not True or row.get("release_state") != "released"
                or not isinstance(row.get("elements"), list)
                or row["elements"] != response.get("elements")):
            _fail("a saved turn is not consistently released")
        remember(turn_id, "advocate", row.get("message"))
        if any(not isinstance(element, dict) or not isinstance(element.get("text"), str)
               for element in row["elements"]):
            _fail("a saved answer is unreadable")
        remember(turn_id, "nm", "\n".join(element["text"] for element in row["elements"]
                                           if element["text"].strip()))
    return words


def _displayed(unit: dict, blocks: dict, row: dict, words: dict,
               allowed_turn_ids: set[str]) -> None:
    for block in blocks.values():
        matches = [element for element in row["elements"]
                   if element.get("continuation_request_index") == unit["request_index"]
                   and element.get("continuation_block_id") == block["id"]]
        if len(matches) != 1 or matches[0]["text"] != block["text"]:
            _fail("progress and displayed answer identities disagree")
        sources = source_snapshots(block["references"])
        element = matches[0]
        if (element.get("sources", []) != sources
                or element.get("source") != (sources[0] if sources else None)
                or element.get("refs", []) != [source["locator"] for source in sources]):
            _fail("progress and displayed sources disagree")
        for reference in block["references"]:
            if reference["type"] == "conversation":
                key = (reference["turn_id"], reference["role"])
                if (key not in words or key[0] not in allowed_turn_ids
                        or reference["text"] not in words[key]
                        or (key == (row["turn_id"], "nm"))):
                    _fail("a progress source is not an attributable saved passage")


def _entry(identity: str, *, kind: str, origin: str, text: str, purpose: str,
           targets: list, task_id: str | None, turn_id: str, index: int,
           block_id: str, matter_scope: str) -> dict:
    return dict(id=identity, kind=kind, origin=origin, text=text, purpose=purpose,
                status="pending", target_ids=deepcopy(targets), task_id=task_id,
                source_turn_id=turn_id, request_index=index, block_id=block_id,
                last_update_turn_id=turn_id, reason=purpose, matter_scope=matter_scope)


def _event(events: list, row: dict, *, turn_id: str, index: int,
           block_id: str, reason: str, status: str, spans: list,
           action: str) -> None:
    events.append(dict(target_id=row["id"], action=action, status=status,
                       turn_id=turn_id, request_index=index, block_id=block_id,
                       reason=reason, span_ids=deepcopy(spans)))
    if action != "referenced":
        row.update(status=status, last_update_turn_id=turn_id, reason=reason)


def project_work(matter, *, prior_conversation=()) -> dict:
    """Replay validated scoped progress without modifying facts or closing a matter."""
    turns = matter.brain_chat
    words = _read_words(prior_conversation, turns)
    active, events = {}, []
    current_turn_ids = {row["turn_id"] for row in turns}
    allowed_turn_ids = {message.turn_id for message in prior_conversation
                        if message.turn_id not in current_turn_ids}
    untracked = bool(allowed_turn_ids)
    for row in turns:
        if row.get("advocate_id") != matter.advocate_id or row.get("matter_id") != str(matter.id):
            _fail("a saved progress turn belongs to another owner")
        allowed_turn_ids.add(row["turn_id"])
        continuation = row["response"].get("continuation")
        if continuation is None:
            continue
        if not isinstance(continuation, dict) or not isinstance(continuation.get("units"), list):
            _fail("the saved continuation is unreadable")
        previous = deepcopy(active)
        seen = set()
        updated_ids = set()
        for unit in continuation["units"]:
            if not isinstance(unit, dict):
                _fail("a saved continuation unit is unreadable")
            index = unit.get("request_index")
            if type(index) is not int or index < 0 or index in seen:
                _fail("saved request identities conflict")
            seen.add(index)
            blocks = _blocks(unit)
            _displayed(unit, blocks, row, words, allowed_turn_ids)
            version = unit.get("progress_version")
            if version is None:
                if any(field in unit for field in ("work", "progress_updates")):
                    _fail("server progress metadata is missing")
                untracked = True
            elif type(version) is not int or version not in (1, PROGRESS_VERSION):
                _fail("the saved progress version is unsupported")
            elif version == 1:
                untracked = True
            _project_unit(unit, previous, active, events, blocks, str(matter.id),
                          row["turn_id"], index, tracked=version is not None)
            targets = {update["target_id"] for update in unit.get("progress_updates", [])}
            if targets & updated_ids:
                _fail("saved request units claim the same progress transition")
            updated_ids.update(targets)
    active_work = "\n".join(row["text"] for row in active.values()
                            if row["kind"] == "task" and row["origin"] == "requested"
                            and row["status"] in ("pending", "promised", "unavailable"))
    return dict(state="ok", rows=deepcopy(list(active.values())), events=events,
                active_work=active_work,
                coverage={"older_progress": "untracked" if untracked else "tracked"},
                diagnostics=(["Earlier work has no recorded status; read its conversation."]
                             if untracked else []))


def _project_unit(unit: dict, previous: dict, active: dict, events: list,
                  blocks: dict, matter_id: str, turn_id: str, index: int,
                  *, tracked: bool) -> None:
    expected = deepcopy(unit)
    work_id = ""
    if tracked:
        _seal_unit(expected, previous, blocks, matter_id, turn_id, index, sealed=True,
                   strict=unit["progress_version"] == PROGRESS_VERSION)
        if expected != unit:
            _fail("saved server progress identities disagree")
        work = unit["work"]
        for field in ("request", "relation", "matter_scope"):
            _text(work.get(field))
        if work["relation"] not in ("continues", "changes", "aside", "new", "uncertain"):
            _fail("a saved work relationship is invalid")
        if work["matter_scope"] not in ("current", "proposed", "none", "other", "uncertain"):
            _fail("a saved work scope is invalid")
        work_id = work["progress_id"]
        if work["create"]:
            origin = "requested" if work.get("intent") == "request" else "unassessed"
            _create(active, events, _entry(work_id, kind="task", origin=origin,
                    text=work["request"], purpose=work["request"], targets=[], task_id=None,
                    turn_id=turn_id, index=index, block_id=unit["sufficiency"]["block_id"],
                    matter_scope=work["matter_scope"]))
    scope = (active[work_id]["matter_scope"] if work_id else
             unit["work"]["matter_scope"] if tracked else "uncertain")
    for section, kind in _SECTIONS:
        links = unit.get(section)
        if not isinstance(links, list):
            _fail("saved question or work proposals are unreadable")
        local_ids = set()
        for link in links:
            if not isinstance(link, dict):
                _fail("a saved progress proposal is unreadable")
            local_id = _text(link.get("id"))
            if local_id in local_ids or link.get("block_id") not in blocks:
                _fail("a saved proposal has no distinct displayed owner")
            local_ids.add(local_id)
            _text(link.get("purpose"))
            _ids(link.get("target_ids"))
            identity = (link["progress_id"] if tracked else _progress_id(
                matter_id, turn_id, index, section, local_id))
            if tracked and link["existing_id"]:
                _event(events, active[identity], turn_id=turn_id, index=index,
                       block_id=link["block_id"], reason=link["purpose"],
                       status=active[identity]["status"], spans=[], action="referenced")
            else:
                _create(active, events, _entry(identity, kind=kind, origin="proposed",
                        text=blocks[link["block_id"]]["text"], purpose=link["purpose"],
                        targets=link["target_ids"], task_id=work_id or None,
                        turn_id=turn_id, index=index, block_id=link["block_id"],
                        matter_scope=scope))
    if not tracked:
        return
    for update in unit["progress_updates"]:
        _event(events, active[update["target_id"]], turn_id=turn_id, index=index,
               block_id=update["block_id"], reason=update["reason"],
               status=update["status"], spans=update["span_ids"], action="transition")


def _create(active: dict, events: list, entry: dict) -> None:
    if entry["id"] in active:
        _fail("a new progress identity already exists")
    active[entry["id"]] = entry
    _event(events, entry, turn_id=entry["source_turn_id"], index=entry["request_index"],
           block_id=entry["block_id"], reason=entry["purpose"], status="pending",
           spans=[], action="created")
