"""Deterministic continuation proposals for extraction and persistence tests."""
from __future__ import annotations

from copy import deepcopy

from tests.brain_reader_fixture import source_treatment_reply


def expression_units(payload, data):
    """Author closed expressions for declared ordinary legacy fixture drafts.

    This is test-data migration, not a semantic reader or production repair.
    The fixture's block kind declares its purpose; owned source/finding IDs
    declare its evidence. Original fixture prose is deliberately not interpreted.
    Explicit expressions and malformed attacks stay untouched, including any
    forbidden display fields appended to an expression by an adversarial hook.
    Tests for false prose must now fabricate that forbidden field explicitly.
    """
    result = deepcopy(data)
    if not isinstance(result, dict) or not isinstance(result.get("units"), list):
        return result
    records = payload.get("record_catalogue", {})
    legacy_fields = {"id", "kind", "text", "span_ids", "record_ids",
                     "legal_source_ids", "inline_citations", "uncertainty"}
    required = legacy_fields - {"inline_citations"}
    for unit in result["units"]:
        if not isinstance(unit, dict) or not isinstance(unit.get("blocks"), list):
            continue
        outcome = unit.get("record_outcome", {})
        for index, block in enumerate(unit["blocks"]):
            if (not isinstance(block, dict) or "evidence_expression" in block
                    or not required <= block.keys() or not block.keys() <= legacy_fields
                    or not isinstance(block["text"], str)
                    or any(not isinstance(block[field], list)
                           or any(not isinstance(identity, str) for identity in block[field])
                           for field in ("span_ids", "record_ids", "legal_source_ids"))):
                continue
            citations = block.get("inline_citations", [])
            if (not isinstance(citations, list) or any(
                    not isinstance(citation, dict)
                    or set(citation) != {"text", "legal_source_id"}
                    or not isinstance(citation["text"], str)
                    or not isinstance(citation["legal_source_id"], str)
                    or citation["legal_source_id"] not in block["legal_source_ids"]
                    or citation["text"] not in block["text"]
                    for citation in citations)):
                continue
            source_ids = list(block["span_ids"])
            record_ids = list(block["record_ids"])
            legal_ids = list(block["legal_source_ids"])
            findings = [identity for identity in record_ids
                        if records.get(identity, {}).get("type") in ("requirement", "research")]
            if legal_ids:
                # Both checked findings and individually checked passages are
                # legitimate owned selections. A standalone passage retains
                # its checked statement; no finding wrapper is manufactured.
                selected = set(legal_ids)
                for identity, row in records.items():
                    finding = row.get("record", {})
                    if (row.get("type") in ("requirement", "research")
                            and set(finding.get("source_ids", [])).intersection(selected)
                            and identity not in findings):
                        findings.append(identity)
                supported_ids = {source for identity in findings
                                 for source in records[identity]["record"].get("source_ids", [])}
                supported_ids.update(payload.get("legal_sources", {}))
                if not selected <= supported_ids:
                    continue
            kind, focus = block["kind"], "none"
            if kind == "completion" and outcome.get("status", "none") != "none":
                operator, source_ids, record_ids = "record_result", [], []
            elif kind == "question":
                operator, focus = "question", "meaning"
            elif kind == "next_step":
                operator, focus = "next_work", "meaning"
            elif findings or legal_ids:
                operator, record_ids = "checked_legal", findings
            elif kind in ("account", "assessment", "completion"):
                operator = "source_account" if source_ids or record_ids else "acknowledgment"
            elif kind == "limitation":
                operator = "limitation"
            else:
                continue
            expression = {"operator": operator, "source_ids": source_ids,
                          "record_ids": record_ids, "focus": focus}
            if operator == "checked_legal" and legal_ids:
                expression["legal_source_ids"] = legal_ids
            unit["blocks"][index] = {
                "id": block["id"], "kind": kind, "uncertainty": block["uncertainty"],
                "evidence_expression": expression,
            }
    return result


def citation_units(payload, data):
    """Supply declared anchors for old offline drafts, preserving explicit invalid anchors."""
    result = deepcopy(data)
    if not isinstance(result, dict) or not isinstance(result.get("units"), list):
        return result
    for unit in result["units"]:
        if not isinstance(unit, dict) or not isinstance(unit.get("blocks"), list):
            continue
        association = unit.get("work")
        if ("work_selector" not in unit and isinstance(association, dict)
                and set(association) == {"existing_id", "create"}
                and isinstance(association["existing_id"], str)
                and type(association["create"]) is bool
                and not (association["existing_id"] and association["create"])):
            unit["work_selector"] = (association["existing_id"] or
                                     ("$new_task" if association["create"] else "$no_task"))
            unit.pop("work")
        # Explicit ordinary legacy-wire declaration only; typed effectful tests
        # supply their own outcome and independent judgment.
        unit.setdefault("record_outcome", {
            "status": "none", "block_id": "", "effect_ids": [],
            "current_record_ids": [], "reason": "",
        })
        if payload.get("response_expression_contract") == "evidence_expression_v1":
            continue
        for block in unit["blocks"]:
            if not isinstance(block, dict) or "inline_citations" in block:
                continue
            sources = list(block.get("legal_source_ids", []))
            for identity in block.get("record_ids", []):
                record = payload["record_catalogue"].get(identity, {})
                if record.get("type") in ("requirement", "research"):
                    sources.extend(record["record"]["source_ids"])
            sources = list(dict.fromkeys(sources))
            phrases = [block["text"]] if len(sources) == 1 else block["text"].splitlines()
            if len(phrases) < len(sources):
                raise AssertionError(
                    "A multi-passage offline draft needs explicit supported anchors")
            block["inline_citations"] = [
                {"text": phrase, "legal_source_id": identity}
                for identity, phrase in zip(sources, phrases, strict=False)]
    if payload.get("response_expression_contract") == "evidence_expression_v1":
        return expression_units(payload, result)
    return result


def reviewed_verdicts(payload, data):
    """Declare successful item coverage for normal offline reviewer fixtures.

    Explicit subchecks, including deliberately malformed or rejected checks,
    are preserved. This helper supplies no production semantic decisions.
    """
    result = deepcopy(data)
    units = {unit["request_index"]: unit for unit in payload["units"]}
    if not isinstance(result, dict) or not isinstance(result.get("verdicts"), list):
        return result
    for row in result["verdicts"]:
        if not isinstance(row, dict) or row.get("request_index") not in units:
            continue
        unit = units[row["request_index"]]
        # Scripted ordinary/no-effect legacy fixtures only. Effectful cases
        # provide their own independent disposition; never derive it from receipts.
        if unit.get("record_outcome", {}).get("status", "none") == "none":
            row.setdefault("record_check", {
                "outcome": "not_requested",
                "reason": "The ordinary scripted fixture seeks no record result.",
            })
        row.setdefault("retained_block_ids", [])
        row.setdefault("retained_reason", "")
        row.setdefault("block_checks", [{
            "block_id": block["id"],
            "requires_legal_support": bool(block["legal_source_ids"]),
            "verdict": "accept", "reason": "The scripted block retains its selected support.",
        } for block in unit["blocks"]])
        row.setdefault("proposal_checks", [{
            "section": section, "proposal_id": link["id"], "block_id": link["block_id"],
            "purpose_expressed": True, "identity_preserved": True, "verdict": "accept",
            "reason": "The scripted purpose is expressed by its displayed owner.",
        } for section in ("questions", "next_work") for link in unit[section]])
        row.setdefault("work_check", {
            "existing_id": unit["work"]["existing_id"], "scope_preserved": True,
            "verdict": "accept", "reason": "The scripted work retains its selected scope.",
        })
        row.setdefault("progress_checks", [{
            "target_id": update["target_id"], "status": update["status"],
            "scope_preserved": True, "result_supported": True, "verdict": "accept",
            "reason": "The scripted transition retains its scoped attributed support.",
        } for update in unit["progress_updates"]])
        questions = {item["id"]: item for item in payload["input"]["progress"]["rows"]
                     if item["kind"] == "question"}
        resolutions = {link["existing_id"]: {
            "question_id": link["existing_id"], "status": questions[link["existing_id"]]["status"],
            "block_id": link["block_id"],
        } for link in unit["questions"] if link["existing_id"] in questions}
        resolutions.update({update["target_id"]: {
            "question_id": update["target_id"], "status": update["status"],
            "block_id": update["block_id"],
        } for update in unit["progress_updates"] if update["target_id"] in questions})
        row.setdefault("question_resolutions", list(resolutions.values()))
    return result


def no_record_requirement():
    """An explicit fixture declaration; no request meaning is inferred."""
    return {
        "kind": "none",
        "target_ids": [],
        "operation": "none",
        "success_condition": "",
    }


def interpretation(data, *, record_requirements=None):
    """Carry only explicit fixture-owned outcomes, including declared no-effect work."""
    result = {**{key: value for key, value in data.items() if key != "active_work_after"},
            "items": [{**item, "intent": item.get("intent", "request"),
                       "response_basis": item.get("response_basis", "legal_authority"
                                                  if item.get("research_question")
                                                  else "conversation_record"),
                       "response_mode": item.get("response_mode", "substantive"),
                       "mutation_scopes": deepcopy(item.get("mutation_scopes", [])),
                       "research_question": item.get("research_question", "")}
                      for item in data["items"]]}
    for index, declared in (record_requirements or {}).items():
        if type(index) is not int or not 0 <= index < len(result["items"]):
            raise ValueError("A scripted record requirement needs its owned item index")
        row = result["items"][index]
        if "record_requirement" in row and row["record_requirement"] != declared:
            raise ValueError("Two fixture owners declared different record requirements")
        row["record_requirement"] = deepcopy(declared)
    return result


def continuation_reply(operation, payload, *, scripted_items=()):
    treatment = source_treatment_reply(operation, payload)
    if treatment is not None:
        return treatment
    if operation == "verify_continuation":
        return reviewed_verdicts(payload, {"verdicts": [{"request_index": unit["request_index"],
                              "verdict": "accept",
                              "reason": "The scripted unit retains its attributed limits."}
                             for unit in payload["units"]]})
    if operation != "continue_conversation":
        return None
    latest_id = payload["latest_message_spans"][0]["id"]
    records = payload["record_catalogue"]
    requirements = {key: row for key, row in records.items()
                    if row["type"] == "requirement"}
    units = []
    fresh = payload.get("response_expression_contract") == "evidence_expression_v1"
    for item in payload["work_items"]:
        index = item["request_index"]
        scripted = scripted_items[index]
        questions = []
        record_ids = []
        legal_ids = []
        if item["next_step"] == "clarify":
            kind, text, status = "question", scripted["clarification"], "needs_input"
            questions = [{"id": f"question:{index}", "block_id": f"block:{index}",
                          "purpose": "Resolve the distinction needed to proceed.",
                          "target_ids": [], "existing_id": ""}]
        elif item["next_step"] == "answer":
            kind, text, status = "completion", scripted["reply"], "complete"
        else:
            kind, status = "limitation", "not_completed"
            text = (scripted["reply"] if item["next_step"] == "legal_work"
                    else "This part requires checked support before a substantive answer.")
            if requirements:
                text = "\n".join(
                    f"{row['record']['label']} "
                    f"({records[row['record']['dispute_id']]['record']['label']})"
                    for row in requirements.values())
                record_ids = list(requirements)
                legal_ids = list(dict.fromkeys(
                    source_id for row in requirements.values()
                    for source_id in row["record"]["source_ids"]))
            missing = sum((state.get("state") if isinstance(state, dict) else state) != "ok"
                          for state in payload["legal_coverage"].values())
            if missing:
                text += (f"\nLegal source checking is incomplete for {missing} "
                         f"dispute{'s' if missing != 1 else ''}.")
        block = {"id": f"block:{index}", "kind": kind, "text": text,
                 "span_ids": [latest_id], "record_ids": record_ids,
                 "legal_source_ids": legal_ids,
                 "uncertainty": "conditional" if legal_ids else "reported"}
        if fresh:
            # These are explicit ordinary fixture purposes. Neither the reply
            # wording nor a successful effect is interpreted by this helper.
            if kind == "question":
                expression = {"operator": "question", "source_ids": [latest_id],
                              "record_ids": [], "focus": "meaning"}
            elif kind == "completion" and (
                    item.get("record_requirement", {}).get("kind", "none") != "none"
                    or item.get("response_mode") == "record_acknowledgement"
                    or "none" not in item.get("record_outcome_statuses", ["none"])):
                expression = {"operator": "record_result", "source_ids": [],
                              "record_ids": [], "focus": "none"}
            elif record_ids:
                expression = {"operator": "checked_legal", "source_ids": [latest_id],
                              "record_ids": record_ids, "focus": "none"}
            else:
                expression = {"operator": "source_account" if kind == "completion"
                              else "limitation", "source_ids": [latest_id],
                              "record_ids": [], "focus": "none"}
            block = {"id": block["id"], "kind": kind, "uncertainty": block["uncertainty"],
                     "evidence_expression": expression}
        units.append({
            "request_index": index,
            "blocks": [block],
            "questions": questions, "next_work": [],
            "sufficiency": {"status": status, "block_id": f"block:{index}"},
            "work": {"existing_id": "", "create": item["intent"] == "request"},
            "progress_updates": [{"target_id": "$work", "status": "complete",
                                  "block_id": f"block:{index}",
                                  "reason": "The requested scoped answer is delivered.",
                                  "span_ids": [latest_id]}]
            if status == "complete" and item["intent"] == "request" else [],
        })
    return citation_units(payload, {"units": units})
