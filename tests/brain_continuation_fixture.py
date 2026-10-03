"""Deterministic continuation proposals for extraction and persistence tests."""
from __future__ import annotations

from copy import deepcopy


def citation_units(payload, data):
    """Supply declared anchors for old offline drafts, preserving explicit invalid anchors."""
    result = deepcopy(data)
    if not isinstance(result, dict) or not isinstance(result.get("units"), list):
        return result
    for unit in result["units"]:
        if not isinstance(unit, dict) or not isinstance(unit.get("blocks"), list):
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
        row.setdefault("block_checks", [{
            "block_id": block["id"],
            "requires_legal_support": bool(block["legal_source_ids"]),
            "verdict": "accept", "reason": "The scripted block retains its selected support.",
        } for block in unit["blocks"]])
        row.setdefault("proposal_checks", [{
            "section": section, "proposal_id": link["id"], "block_id": link["block_id"],
            "purpose_expressed": True, "verdict": "accept",
            "reason": "The scripted purpose is expressed by its displayed owner.",
        } for section in ("questions", "next_work") for link in unit[section]])
    return result


def interpretation(data):
    return {**{key: value for key, value in data.items() if key != "active_work_after"},
            "items": [{**item, "intent": item.get("intent", "request"),
                       "research_question": item.get("research_question", "")}
                      for item in data["items"]]}


def continuation_reply(operation, payload, *, scripted_items=()):
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
    needs_legal_work = any(item["next_step"] == "legal_work"
                           for item in payload["work_items"])
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
        elif item["next_step"] == "answer" and not needs_legal_work:
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
        units.append({
            "request_index": index,
            "blocks": [{"id": f"block:{index}", "kind": kind, "text": text,
                        "span_ids": [latest_id], "record_ids": record_ids,
                        "legal_source_ids": legal_ids,
                        "uncertainty": "conditional" if legal_ids else "reported"}],
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
