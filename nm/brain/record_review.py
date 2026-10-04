"""Shared attestations for attributed account content and record transitions.

These contracts make decisions in existing record-review calls explicit; this
module neither calls a model nor interprets source text.
"""
from __future__ import annotations

from nm.shared.model_port import SchemaViolation


def review_contract_issue(error: SchemaViolation) -> str:
    """Keep the schema path and failure without copying a returned enum value."""
    message = str(error)
    if " value " in message and "outside the permitted vocabulary" in message:
        return message.split(" value ", 1)[0] + " is outside the permitted vocabulary"
    return message


def review_issues_text(issues: dict[str, tuple[str, ...]]) -> str:
    """Render only contract diagnostics associated with pending candidate IDs."""
    return "; ".join(f"{identity}: " + ", ".join(messages)
                     for identity, messages in issues.items())


def candidate_account_ids(candidate, latest: dict, prior: dict) -> set[str]:
    """Select only advocate spans already attributed to this proposal."""
    if candidate is None:
        return set(latest) | {key for key, ref in prior.items() if ref.role == "advocate"}
    selected = {key for key, text in latest.items() if candidate.quoted in text}
    selected.update(key for key, ref in prior.items() if ref.role == "advocate"
                    and any(ref.turn_id == linked.turn_id and ref.role == linked.role
                            and linked.quoted in ref.quoted
                            for linked in candidate.prior_references))
    return selected


def restoration_peer_ids(candidate_id: str, targets: dict[str, set[str]]) -> tuple[str, ...]:
    """Only other proposals selecting at least one of this proposal's targets."""
    return tuple(key for key, selected in targets.items()
                 if key != candidate_id and selected.intersection(targets[candidate_id]))


def review_properties(source_ids: tuple[str, ...], target_ids: tuple[str, ...],
                      candidate_ids: tuple[str, ...]) -> dict:
    def ids(values):
        return {"type": "array", "items": {"type": "string", "enum": list(values) or [""]},
                **({"maxItems": 0} if not values else {})}

    return {
        "account_check": {
            "type": "object", "additionalProperties": False,
            "required": ["content_role", "supported", "introduces_legal_analysis",
                         "source_ids", "reason"],
            "properties": {
                "content_role": {"type": "string", "enum": [
                    "reported_matter_account", "examination_material", "nm_analysis", "uncertain"]},
                "supported": {"type": "boolean"},
                "introduces_legal_analysis": {"type": "boolean"},
                "source_ids": ids(source_ids),
                "reason": {"type": "string", "minLength": 1, "maxLength": 500},
            },
        },
        "target_checks": {
            "type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["target_id", "identity_relation", "account_preserved",
                             "required_peer_ids", "reason"],
                "properties": {
                    "target_id": {"type": "string", "enum": list(target_ids) or [""]},
                    "identity_relation": {"type": "string", "enum": [
                        "same_underlying_account", "duplicate", "restore_invalid_interpretation",
                        "different", "uncertain"]},
                    "account_preserved": {"type": "boolean"},
                    "required_peer_ids": ids(candidate_ids),
                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                },
            },
        },
    }


def validate_record_checks(row: dict, *, source_ids: set[str], target_ids: set[str],
                           candidate_id: str, candidates: dict[str, set[str]],
                           issues: list[str] | None = None) -> bool:
    """Validate ownership before evaluating positive independent attestations."""
    account = row["account_check"]
    sources = account["source_ids"]
    targets = row["target_checks"]
    selected = [target["target_id"] for target in targets]
    if len(sources) != len(set(sources)):
        raise SchemaViolation("account_check.source_ids contains duplicate IDs")
    if not set(sources) <= source_ids:
        raise SchemaViolation("account_check.source_ids contains unowned source IDs")
    if len(selected) != len(set(selected)):
        raise SchemaViolation("target_checks contains duplicate target IDs")
    if not set(selected) <= target_ids:
        raise SchemaViolation("target_checks contains unowned target IDs")
    if row["verdict"] == "accept" and set(selected) != target_ids:
        raise SchemaViolation(
            "accept is missing target_checks for " + ", ".join(sorted(target_ids - set(selected))))
    if not account["reason"].strip():
        raise SchemaViolation("account_check.reason is empty")
    for target in targets:
        peers = target["required_peer_ids"]
        identity = target["target_id"]
        if not target["reason"].strip():
            raise SchemaViolation(f"target_checks for {identity}: reason is empty")
        if len(peers) != len(set(peers)):
            raise SchemaViolation(f"target_checks for {identity}: required_peer_ids repeats an ID")
        if candidate_id in peers:
            raise SchemaViolation(
                f"target_checks for {identity}: required_peer_ids includes itself")
        if any(peer not in candidates or identity not in candidates[peer] for peer in peers):
            raise SchemaViolation(
                f"target_checks for {identity}: required_peer_ids selects an unowned peer")
    conflicts = []
    if account["content_role"] != "reported_matter_account":
        conflicts.append("accept conflicts with account_check.content_role="
                         + account["content_role"])
    if not account["supported"]:
        conflicts.append("accept conflicts with account_check.supported=false")
    if account["introduces_legal_analysis"]:
        conflicts.append("accept conflicts with account_check.introduces_legal_analysis=true")
    if not sources:
        conflicts.append("accept requires nonempty attributable account_check.source_ids")
    for target in targets:
        identity = target["target_id"]
        if not target["account_preserved"]:
            conflicts.append(f"accept conflicts with target {identity}: account_preserved=false")
        if target["identity_relation"] not in (
                "same_underlying_account", "duplicate", "restore_invalid_interpretation"):
            conflicts.append(f"accept conflicts with target {identity}: identity_relation="
                             + target["identity_relation"])
    if row["verdict"] == "accept" and issues is not None:
        issues.extend(conflicts)
    return not conflicts


def admitted_record_decisions(decisions: dict[str, dict]) -> dict[str, dict]:
    """Withhold dependent retirements when a required atomic successor is absent."""
    result = {key: dict(value) for key, value in decisions.items()}
    changed = True
    while changed:
        changed = False
        for row in result.values():
            missing = [peer for target in row["target_checks"]
                       for peer in target["required_peer_ids"]
                       if result.get(peer, {}).get("verdict") != "accept"]
            if row["verdict"] == "accept" and missing:
                raw = dict(row)
                row.update(verdict="reject", operation_supported=False,
                           reason="A required successor was unsupported; the prior account stays.",
                           model_decision=raw,
                           admission_issue="required_restoration_peer_unavailable",
                           missing_peer_ids=list(dict.fromkeys(missing)))
                changed = True
    return result
