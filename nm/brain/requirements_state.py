"""Project source-linked legal work items for the current dispute record."""
from __future__ import annotations

import hashlib
import json

from nm.work_the_file.matter_contracts import Matter


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def subject_fingerprint(dispute: dict, material: list[dict]) -> str:
    """Change only when the attributed subject of legal research changes."""
    subject = {key: dispute.get(key) for key in (
        "id", "label", "statement", "quoted", "identification")}
    linked = [
        {key: item.get(key) for key in (
            "id", "kind", "statement", "quoted", "basis", "importance",
            "source_turn_id")}
        for item in material
    ]
    return _digest({"dispute": subject,
                    "material": sorted(linked, key=lambda item: str(item["id"]))})


def _valid_row(row: object, material_ids: set[str]) -> bool:
    if not isinstance(row, dict):
        return False
    if any(not isinstance(row.get(key), str) or not row[key].strip()
           for key in ("label", "need", "why")):
        return False
    if len(row["label"]) > 120 or row.get("force") not in (
            "required", "strengthening"):
        return False
    sources, source_ids = row.get("sources"), row.get("source_ids")
    linked = row.get("material_ids")
    if (not isinstance(sources, list) or not isinstance(source_ids, list)
            or not sources or len(sources) != len(source_ids)
            or len(source_ids) != len(set(source_ids))
            or not isinstance(linked, list) or len(linked) != len(set(linked))
            or any(not isinstance(item, str) for item in linked)
            or not set(linked) <= material_ids
            or row.get("record_status") != (
                "mentioned" if linked else "not_mentioned")):
        return False
    for expected_id, source in zip(source_ids, sources, strict=True):
        if (not isinstance(expected_id, str) or not expected_id
                or not isinstance(source, dict)
                or source.get("id") != expected_id
                or source.get("kind") not in ("provision", "judgment")
                or any(not isinstance(source.get(key), str)
                       or not source[key].strip()
                       for key in ("title", "locator", "text"))):
            return False
        verification = source.get("verification")
        if not isinstance(verification, dict):
            return False
        support = verification.get("support_excerpt")
        scope = verification.get("scope_excerpt")
        scope_status = verification.get("scope_status")
        reason = verification.get("reason")
        if (not isinstance(support, str) or not support.strip()
                or len(support) > 800 or support not in source["text"]
                or not isinstance(scope, str) or len(scope) > 800
                or (scope and (not scope.strip() or scope not in source["text"]))
                or scope_status not in (
                    "established", "asked_to_establish", "no_special_condition")
                or (scope_status == "no_special_condition") != (not scope)
                or not isinstance(reason, str) or not reason.strip()
                or len(reason) > 500):
            return False
    return True


def requirements_record(matter: Matter, *, disputes: dict,
                        material: dict) -> dict:
    """Keep a read only while its dispute and attributed material remain current."""
    if disputes.get("state") != "ok" or material.get("state") != "ok":
        return {"state": "incomplete", "by_dispute": {},
                "status_by_dispute": {}, "diagnostics_by_dispute": {},
                "diagnostics": [
                    "the dispute or material record is incomplete"]}
    active = {row["id"]: row for row in disputes["rows"]
              if row.get("identification") == "identified"}
    by_dispute = {dispute_id: [] for dispute_id in active}
    statuses = {dispute_id: "unassessed" for dispute_id in active}
    diagnostics_by_dispute = {dispute_id: [] for dispute_id in active}
    fingerprints = {
        dispute_id: subject_fingerprint(
            row, [*material.get("by_dispute", {}).get(dispute_id, []),
                  *material.get("matter", [])])
        for dispute_id, row in active.items()
    }
    material_ids = {
        dispute_id: {item["id"] for item in [
            *material.get("by_dispute", {}).get(dispute_id, []),
            *material.get("matter", [])]}
        for dispute_id in active
    }
    diagnostics: list[str] = []
    state = "ok"

    def invalidate(dispute_id: str) -> None:
        statuses[dispute_id] = "unavailable"
        by_dispute[dispute_id] = []
        diagnostics_by_dispute[dispute_id] = []

    for turn in matter.brain_chat:
        response = turn.get("response")
        if not isinstance(response, dict):
            state = "incomplete"
            diagnostics.append("a saved legal read could not be inspected")
            for dispute_id in active:
                invalidate(dispute_id)
            continue
        reads = response.get("requirements_read", [])
        if (not isinstance(reads, list)
                or (reads and (turn.get("committed") is not True
                               or turn.get("release_state") != "released"
                               or response.get("turn_id") != turn.get("turn_id")))):
            state = "incomplete"
            diagnostics.append("a saved legal read has no released turn")
            for dispute_id in active:
                invalidate(dispute_id)
            continue
        seen: set[str] = set()
        for read in reads:
            if not isinstance(read, dict):
                state = "incomplete"
                diagnostics.append("a saved legal read is invalid")
                continue
            dispute_id = read.get("dispute_id")
            if dispute_id not in active or read.get("fingerprint") != fingerprints.get(dispute_id):
                continue
            rows = read.get("rows")
            status = read.get("state")
            queries = read.get("queries")
            read_diagnostics = read.get("diagnostics", [])
            if (dispute_id in seen or status not in ("ok", "partial", "unavailable")
                    or not isinstance(rows, list)
                    or (status == "unavailable" and rows)
                    or not isinstance(queries, list)
                    or any(not isinstance(query, str) or not query.strip()
                           for query in queries)
                    or not isinstance(read_diagnostics, list)
                    or any(not isinstance(problem, str)
                           for problem in read_diagnostics)
                    or any(not _valid_row(row, material_ids[dispute_id])
                           for row in rows)):
                state = "incomplete"
                diagnostics.append("a saved legal read lacks valid attributed sources")
                invalidate(dispute_id)
                continue
            if status in ("ok", "partial") and rows and read.get(
                    "verification") != "source_support_v4":
                diagnostics.append(
                    "saved legal items predate independent source verification")
                invalidate(dispute_id)
                continue
            seen.add(dispute_id)
            statuses[dispute_id] = status
            by_dispute[dispute_id] = rows
            diagnostics_by_dispute[dispute_id] = read_diagnostics
            for problem in read_diagnostics:
                if isinstance(problem, str) and problem.strip():
                    diagnostics.append(problem)
    return {"state": state, "by_dispute": by_dispute,
            "status_by_dispute": statuses, "diagnostics": diagnostics,
            "diagnostics_by_dispute": diagnostics_by_dispute,
            "fingerprints": fingerprints}
