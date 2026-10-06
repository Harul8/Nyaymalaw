"""Project scoped work and questions from the one released conversation record."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from nm.brain.conversation import IncompleteConversation
from nm.brain.execution_contracts import (
    RECORD_OUTCOME_CONTRACT,
    ExecutionEvidenceInvalid,
    effect_catalogue,
    validate_record_outcome,
    validate_review_completion,
)
from nm.brain.source_snapshots import inline_source_links, source_snapshots
from nm.shared.model_port import SchemaViolation

PROGRESS_STATUSES = (
    "pending", "complete", "promised", "unavailable", "deferred", "cancelled")
PROGRESS_KINDS = ("task", "question")
PROGRESS_VERSION = 3
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



RECORD_SNAPSHOT_CONTRACT = "record_result_snapshot_v1"
RECORD_SEAL_CONTRACT = "saved_record_outcome_v1"
_RECORD_STATUSES = {
    "none": "not_requested", "performed": "fulfilled", "already_current": "fulfilled",
    "review_no_change": "no_change_justified", "unresolved": "unfinished",
}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def _requirement(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            "kind", "target_ids", "operation", "success_condition"}:
        _fail("a retained record requirement is incomplete")
    targets = _ids(value["target_ids"])
    kind, operation = value["kind"], value["operation"]
    condition = _text(value["success_condition"], empty=True)
    if kind not in ("none", "review", "change"):
        _fail("a retained record requirement has an unknown kind")
    if kind == "none" and (targets or operation != "none" or condition.strip()):
        _fail("a non-record requirement carries substantive work")
    if kind == "review" and (operation != "none" or not condition.strip()):
        _fail("a retained review requirement is contradictory")
    if kind == "change" and (
            operation not in ("new", "adds", "corrects", "contradicts", "withdraws")
            or not condition.strip() or (operation == "new" and targets)
            or (operation != "new" and not targets)):
        _fail("a retained change requirement is contradictory")
    return deepcopy(value)


def _receipt_evidence(receipt: object) -> dict:
    if not isinstance(receipt, dict):
        _fail("a declared record result has no execution receipt")
    try:
        effect_catalogue(receipt)
    except ExecutionEvidenceInvalid as exc:
        _fail(str(exc))
    result = deepcopy(receipt)
    result.pop("persistence", None)
    return result


def record_result_snapshot(*, execution_receipt: dict, record_catalogue: dict) -> dict:
    """Copy the full owned result catalogue, never promote held observations."""
    _receipt_evidence(execution_receipt)
    if not isinstance(record_catalogue, dict):
        _fail("the resulting record catalogue is unreadable")
    records = {}
    for identity, value in record_catalogue.items():
        _text(identity)
        if not isinstance(value, dict) or value.get("type") not in ("dispute", "material"):
            _fail("a result snapshot contains a non-owned record kind")
        record = value.get("record")
        if (not isinstance(record, dict) or record.get("id") != identity
                or ("id" in value and value["id"] != identity)
                or record.get("matter_scope") not in ("current", "proposed")):
            _fail("a result snapshot has no exact active owned identity")
        records[identity] = deepcopy(value)
    return {"contract": RECORD_SNAPSHOT_CONTRACT, "receipt_id": execution_receipt["id"],
            "owner": deepcopy(execution_receipt["owner"]),
            "resulting_version": execution_receipt["resulting_version"],
            "record_catalogue": records}


def validate_record_result_snapshot(snapshot: dict, receipt: dict, *, matter_id: str,
                                    advocate_id: str, turn_id: str,
                                    committed: bool = False) -> None:
    expected = record_result_snapshot(
        execution_receipt=receipt,
        record_catalogue=snapshot.get("record_catalogue") if isinstance(snapshot, dict) else None)
    if expected != snapshot:
        _fail("the saved result snapshot does not match its execution owner/version")
    owner = receipt["owner"]
    if (owner["matter_id"] != matter_id or owner["advocate_id"] != advocate_id
            or owner["turn_id"] != turn_id
            or (committed and receipt.get("persistence") != "committed")):
        _fail("the saved result snapshot has another owner or an uncommitted receipt")


def _requirement_origin(matter_id: str, turn_id: str, index: int, identity: str) -> dict:
    return {"matter_id": matter_id, "turn_id": turn_id,
            "request_index": index, "progress_id": identity}


def _checked_progress(unit: dict) -> dict[str, dict]:
    rows = unit.get("progress_checks")
    if not isinstance(rows, list):
        _fail("a fresh record result has no independently checked progress")
    updates = {row["target_id"]: row for row in unit["progress_updates"]}
    result = {}
    for check in rows:
        if not isinstance(check, dict) or set(check) != {
                "target_id", "status", "scope_preserved", "result_supported", "verdict", "reason"}:
            _fail("an independent progress check is unreadable")
        identity = _text(check["target_id"])
        if identity == "$work":
            identity = check["target_id"] = unit["work"]["progress_id"]
        if (identity not in updates or identity in result
                or check["status"] != updates[identity]["status"]
                or check["scope_preserved"] is not True
                or check["result_supported"] is not True or check["verdict"] != "accept"):
            _fail("an independent progress check does not support its exact transition")
        _text(check["reason"])
        result[identity] = check
    if result.keys() != updates.keys():
        _fail("independent progress checks do not cover each transition exactly once")
    return result


def _matching_requirement(requirement: dict, unit: dict, receipt: dict | None,
                          snapshot: dict | None, *, completing: bool,
                          task_id: str | None = None) -> None:
    kind = requirement["kind"]
    if kind == "none":
        return
    outcome = unit["record_outcome"]
    status = outcome["status"]
    if status == "none" or (completing and status == "unresolved"):
        _fail("the requested record result is absent or unfinished")
    if kind == "review":
        try:
            validate_review_completion(unit, receipt, requirement=requirement,
                                       task_id=task_id)
        except (SchemaViolation, ExecutionEvidenceInvalid) as exc:
            _fail(str(exc))
        return
    if status == "review_no_change":
        _fail("a review-only result cannot fulfill the retained change requirement")
    if status == "performed":
        catalogue = effect_catalogue(receipt)
        selected = [catalogue[identity] for identity in outcome["effect_ids"]]
        targets = set(requirement["target_ids"])
        matching = [row for row in selected if row["performed"] is True
                    and row["relation"] == requirement["operation"]
                    and (not targets or set(row["target_record_ids"]) & targets)]
        represented = {identity for row in matching for identity in row["target_record_ids"]}
        if not matching or not targets <= represented:
            _fail("the retained change has no relevant admitted operation for its exact targets")
    elif status == "already_current":
        # The reviewer establishes the semantic condition. Code checks every
        # positive reference against THIS turn's active result, not future state.
        if not outcome["current_record_ids"] or snapshot is None:
            _fail("an already-current result has no owned result snapshot")


def _seal_record_outcome(unit: dict, previous: dict, *, receipt: dict | None,
                         snapshot: dict | None, matter_id: str, turn_id: str,
                         index: int, sealed: bool = False) -> None:
    declared = unit.get("record_outcome")
    current = _requirement(unit.get("record_requirement"))
    relevant = [{"owner": "current_request", "request_index": index,
                 "record_requirement": current}]
    work = unit["work"]
    available = dict(previous)
    if work["progress_id"] and work["create"]:
        available[work["progress_id"]] = {
            "kind": "task", "record_requirement": work["record_requirement"],
            "record_requirement_origin": work["record_requirement_origin"]}
    for update in unit["progress_updates"]:
        target = available[update["target_id"]]
        if target["kind"] == "task" and update["status"] == "complete":
            relevant.append({"owner": "completed_task", "target_id": update["target_id"],
                             "record_requirement": _requirement(target.get("record_requirement")),
                             "record_requirement_origin": deepcopy(
                                 target.get("record_requirement_origin"))})
    if receipt is not None:
        requests = [row for row in receipt["requests"]
                    if isinstance(row, dict) and row.get("request_index") == index]
        if len(requests) != 1 or requests[0].get("record_requirement") != current:
            _fail("the execution request differs from its full interpreted requirement")
    fresh_requirement = any(row["record_requirement"] is not None for row in relevant)
    if declared is None:
        if fresh_requirement:
            _fail("fresh requested work has no reviewed record outcome")
        if "record_outcome_seal" in unit or "record_outcome_contract" in unit:
            _fail("a record outcome seal has no declared result")
        return
    if (unit.get("record_outcome_contract") != RECORD_OUTCOME_CONTRACT
            or not isinstance(unit.get("record_check"), dict)
            or set(unit["record_check"]) != {"outcome", "reason"}):
        _fail("the declared record result has no independent review owner")
    check = unit["record_check"]
    status = declared.get("status") if isinstance(declared, dict) else None
    if status not in _RECORD_STATUSES or check["outcome"] != _RECORD_STATUSES[status]:
        _fail("the independently reviewed record result contradicts its declaration")
    _text(check["reason"])
    _checked_progress(unit)
    if status != "none" and (receipt is None or snapshot is None):
        _fail("a consequential record result has no same-turn execution and snapshot")
    try:
        validate_record_outcome(unit, receipt,
                                snapshot["record_catalogue"] if snapshot is not None else ())
    except (SchemaViolation, ExecutionEvidenceInvalid) as exc:
        _fail(str(exc))
    for requirement in relevant:
        if requirement["record_requirement"] is not None:
            _matching_requirement(requirement["record_requirement"], unit, receipt, snapshot,
                                  completing=requirement["owner"] == "completed_task",
                                  task_id=(None if work["create"]
                                           and requirement.get("target_id") == work["progress_id"]
                                           else requirement.get("target_id")))
    owned_unit = deepcopy(unit)
    owned_unit.pop("record_outcome_seal", None)
    payload = {"matter_id": matter_id, "turn_id": turn_id, "request_index": index,
               "requirements": relevant, "unit": owned_unit,
               "execution": _receipt_evidence(receipt) if receipt is not None else None,
               "record_snapshot": deepcopy(snapshot)}
    digest = _digest(payload)
    expected = {"contract": RECORD_SEAL_CONTRACT, "version": 1,
                "id": "ros_" + digest,
                "receipt_id": receipt["id"] if receipt is not None else None,
                "resulting_version": receipt["resulting_version"] if receipt is not None else None,
                "requirements": deepcopy(relevant),
                "review": deepcopy(check),
                "digest": digest}
    if sealed:
        if unit.get("record_outcome_seal") != expected:
            _fail("the saved record result seal disagrees with its original owned evidence")
    else:
        if "record_outcome_seal" in unit:
            _fail("a model proposal already contains a server record result seal")
        unit["record_outcome_seal"] = expected


def _snapshot_sources(snapshot: dict, words: dict, allowed: set[str], turn_id: str) -> None:
    for value in snapshot["record_catalogue"].values():
        record = value["record"]
        source = record.get("source_turn_id")
        quoted = record.get("quoted")
        references = record.get("prior_references", [])
        if not isinstance(references, list):
            _fail("a saved result record has unreadable original sources")
        references = [{"turn_id": source, "role": "advocate", "quoted": quoted}, *references]
        for reference in references:
            if not isinstance(reference, dict) or reference.get("role") not in ("advocate", "nm"):
                _fail("a saved result record has an unknown source owner")
            key = (reference.get("turn_id"), reference["role"])
            quote = reference.get("quoted")
            if (key not in words or key[0] not in allowed or key == (turn_id, "nm")
                    or not isinstance(quote, str)
                    or not quote.strip() or quote not in words[key]):
                _fail("a saved result record differs from its original transcript")


def _legacy_work_evidence(row: dict) -> bool:
    # Absence alone cannot distinguish a bare courtesy from bare historical
    # substantive work. Only saved structural evidence discloses a known gap.
    for value in (row, row["response"]):
        if any(value.get(field) for field in (
                "active_work_after", "tasks", "questions", "next_work", "work_id", "task_id")):
            return True
        progress = value.get("progress")
        if isinstance(progress, dict) and progress.get("rows"):
            return True
        if value.get("needs_work") is True or value.get("blocked") is True:
            return True
    return False


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
            if references[identity].get("type") not in (
                    "dispute", "material", "requirement", "research"):
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
                  plan, prior_progress: dict, execution_receipt: dict | None = None,
                  record_snapshot: dict | None = None) -> dict:
    """Assign stable identities only to independently accepted request units."""
    _text(matter_id)
    _text(turn_id)
    previous = _catalogue(prior_progress)
    result = deepcopy(continuation)
    if not isinstance(result, dict) or not isinstance(result.get("units"), list):
        _fail("the continuation is unreadable")
    if record_snapshot is not None:
        if execution_receipt is None:
            _fail("a result snapshot has no execution owner")
        validate_record_result_snapshot(
            record_snapshot, execution_receipt, matter_id=matter_id,
            advocate_id=execution_receipt["owner"]["advocate_id"], turn_id=turn_id)
        result["record_snapshot"] = deepcopy(record_snapshot)
    elif "record_snapshot" in result:
        _fail("a model proposal already contains a server result snapshot")
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
        if any(field in unit for field in ("record_requirement", "record_outcome_seal")):
            _fail("a model proposal already contains server requirement metadata")
        blocks = _blocks(unit)
        item = plan.items[index]
        unit["record_requirement"] = _requirement(getattr(item, "record_requirement", None))
        intent = getattr(item, "intent", None)
        if intent not in ("request", "contribution"):
            _fail("the interpreted work has no request or contribution intent")
        if not isinstance(unit.get("work"), dict):
            _fail("a scoped work association is unreadable")
        unit["work"].update(request=item.request, relation=item.relation,
                            matter_scope=item.matter_scope, intent=intent)
        if any(field in unit["work"] for field in (
                "record_requirement", "record_requirement_origin", "progress_id")):
            _fail("a model proposal already contains server task requirement metadata")
        _seal_unit(unit, previous, blocks, matter_id, turn_id, index)
        unit["progress_version"] = PROGRESS_VERSION
        _seal_record_outcome(unit, previous, receipt=execution_receipt,
                             snapshot=record_snapshot, matter_id=matter_id,
                             turn_id=turn_id, index=index)
        targets = {update["target_id"] for update in unit["progress_updates"]}
        if targets & updated_ids:
            _fail("different request units claim the same progress transition")
        updated_ids.update(targets)
        unit["progress_version"] = PROGRESS_VERSION
    return result


def _seal_unit(unit: dict, previous: dict, blocks: dict, matter_id: str,
               turn_id: str, index: int, *, sealed: bool = False,
               strict: bool = True, requirements: bool = True) -> None:
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
    if requirements:
        requirement = (previous[existing].get("record_requirement") if existing else
                       unit.get("record_requirement") if work["create"] else None)
        origin = (previous[existing].get("record_requirement_origin") if existing else
                  _requirement_origin(matter_id, turn_id, index, work["progress_id"])
                  if work["create"] else None)
        if sealed and (work.get("record_requirement") != requirement
                       or work.get("record_requirement_origin") != origin):
            _fail("a saved task narrowed or replaced its original record requirement")
        work["record_requirement"] = _requirement(requirement)
        work["record_requirement_origin"] = deepcopy(origin)
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
            if identity in seen or link.get("block_id") not in blocks:
                _fail("a question or work proposal has no distinct identity or displayed owner")
            seen.add(identity)
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
        available.setdefault(work["progress_id"], {
            "kind": "task", "record_requirement": work.get("record_requirement")})
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
        try:
            links = inline_source_links(block, sources)
        except ValueError as exc:
            _fail(str(exc))
        if element.get("inline_citations", []) != (links or []):
            _fail("progress and displayed inline citations disagree")
        for reference in block["references"]:
            if reference["type"] == "conversation":
                key = (reference["turn_id"], reference["role"])
                if (key not in words or key[0] not in allowed_turn_ids
                        or reference["text"] not in words[key]
                        or (key == (row["turn_id"], "nm"))):
                    _fail("a progress source is not an attributable saved passage")


def _entry(identity: str, *, kind: str, origin: str, text: str, purpose: str,
           targets: list, task_id: str | None, turn_id: str, index: int,
           block_id: str, matter_scope: str, record_requirement: dict | None = None,
           record_requirement_origin: dict | None = None) -> dict:
    result = dict(id=identity, kind=kind, origin=origin, text=text, purpose=purpose,
                status="pending", target_ids=deepcopy(targets), task_id=task_id,
                source_turn_id=turn_id, request_index=index, block_id=block_id,
                last_update_turn_id=turn_id, reason=purpose, matter_scope=matter_scope)
    if kind == "task":
        result.update(record_requirement=_requirement(record_requirement),
                      record_requirement_origin=deepcopy(record_requirement_origin),
                      record_outcome_coverage=("untracked" if record_requirement is None
                                               else "pending"))
    return result


def _event(events: list, row: dict, *, turn_id: str, index: int,
           block_id: str, reason: str, status: str, spans: list,
           action: str) -> None:
    events.append(dict(target_id=row["id"], action=action, status=status,
                       turn_id=turn_id, request_index=index, block_id=block_id,
                       reason=reason, span_ids=deepcopy(spans)))
    if action != "referenced":
        row.update(status=status, last_update_turn_id=turn_id, reason=reason)


def project_work(matter, *, prior_conversation=(),
                 allow_prepared_turn_id: str | None = None) -> dict:
    """Replay validated scoped progress without modifying facts or closing a matter."""
    turns = matter.brain_chat
    if allow_prepared_turn_id is not None and (
            not isinstance(allow_prepared_turn_id, str) or not turns
            or turns[-1].get("turn_id") != allow_prepared_turn_id):
        _fail("prepared projection is limited to the final constructed current turn")
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
            untracked = untracked or _legacy_work_evidence(row)
            continue
        if not isinstance(continuation, dict) or not isinstance(continuation.get("units"), list):
            _fail("the saved continuation is unreadable")
        snapshot = continuation.get("record_snapshot")
        coverage = row["response"].get("material_coverage")
        receipt = coverage.get("execution") if isinstance(coverage, dict) else None
        if snapshot is not None:
            prepared = (row["turn_id"] == allow_prepared_turn_id
                        and isinstance(receipt, dict)
                        and receipt.get("persistence") == "prepared_for_commit")
            validate_record_result_snapshot(
                snapshot, receipt, matter_id=str(matter.id), advocate_id=matter.advocate_id,
                turn_id=row["turn_id"], committed=not prepared)
            if receipt["owner"]["offer_digest"] != row.get("offer_digest"):
                _fail("the result snapshot names different accepted instructions")
            if prepared:
                if (receipt["expected_version"] != getattr(matter, "version", None)
                        or receipt["resulting_version"] != matter.version + 1):
                    _fail("the prepared result does not match its exact current matter version")
            elif hasattr(matter, "version") and receipt["resulting_version"] > matter.version:
                _fail("the saved result version is later than its durable matter")
            _snapshot_sources(snapshot, words, allowed_turn_ids, row["turn_id"])
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
            elif type(version) is not int or version not in (1, 2, PROGRESS_VERSION):
                _fail("the saved progress version is unsupported")
            elif version == 1:
                untracked = True
            receipt_requests = receipt.get("requests", []) if isinstance(receipt, dict) else []
            updates = unit.get("progress_updates", [])
            if not isinstance(receipt_requests, list) or not isinstance(updates, list):
                _fail("saved record goals or progress transitions are unreadable")
            inherited_completion = any(
                isinstance(update, dict) and update.get("status") == "complete"
                and previous.get(update.get("target_id"), {}).get("record_requirement") is not None
                for update in updates)
            current_requirement = any(
                isinstance(request, dict) and request.get("request_index") == index
                and request.get("record_requirement") is not None
                for request in receipt_requests)
            if version != PROGRESS_VERSION and (
                    snapshot is not None or current_requirement or inherited_completion
                    or unit.get("record_requirement") is not None
                    or any(field in unit for field in (
                        "record_outcome", "record_outcome_seal", "record_outcome_contract"))):
                _fail("fresh record-result metadata cannot bypass saved validation "
                      "as legacy progress")
            _project_unit(unit, previous, active, events, blocks, str(matter.id),
                          row["turn_id"], index, tracked=version is not None,
                          receipt=receipt, snapshot=snapshot)
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
                  *, tracked: bool, receipt: dict | None = None,
                  snapshot: dict | None = None) -> None:
    expected = deepcopy(unit)
    work_id = ""
    if tracked:
        _seal_unit(expected, previous, blocks, matter_id, turn_id, index, sealed=True,
                   strict=unit["progress_version"] >= 2,
                   requirements=unit["progress_version"] == PROGRESS_VERSION)
        if unit["progress_version"] == PROGRESS_VERSION:
            if "record_requirement" not in unit:
                _fail("saved fresh work is missing its record requirement declaration")
            _seal_record_outcome(expected, previous, receipt=receipt, snapshot=snapshot,
                                 matter_id=matter_id, turn_id=turn_id, index=index, sealed=True)
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
                    matter_scope=work["matter_scope"],
                    record_requirement=work.get("record_requirement"),
                    record_requirement_origin=work.get("record_requirement_origin")))
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
        task = active[update["target_id"]]
        if task["kind"] == "task" and update["status"] == "complete":
            task["record_outcome_coverage"] = (
                "checked" if task.get("record_requirement") is not None
                and unit.get("record_outcome_seal") else "untracked")
            if unit.get("record_outcome_seal"):
                task["record_outcome_seal"] = deepcopy(unit["record_outcome_seal"])


def _create(active: dict, events: list, entry: dict) -> None:
    if entry["id"] in active:
        _fail("a new progress identity already exists")
    active[entry["id"]] = entry
    _event(events, entry, turn_id=entry["source_turn_id"], index=entry["request_index"],
           block_id=entry["block_id"], reason=entry["purpose"], status="pending",
           spans=[], action="created")
