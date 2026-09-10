"""Check adoption-record structure, never verify a signature or grant authority.

Readiness reports the presence of manual records honestly. It deliberately has
no Boolean bypass or 'valid' state: BK-80 owns the future verified resolver.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import re

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


def _formats() -> FormatChecker:
    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def instant(value):
        if not isinstance(value, str):
            return True  # Schema type owns the refusal.
        if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
                r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value):
            return False
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None

    return checker


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _local_refs(value: object, root: dict, *, is_root: bool = False) -> list[str]:
    """Refuse remote resolution and dangling pointers without any network I/O."""
    errors = []
    if isinstance(value, dict):
        if not is_root and ("$id" in value or "$schema" in value):
            errors.append("approval schema: nested identity/metaschema rebasing is forbidden")
        if "$dynamicRef" in value or "$recursiveRef" in value:
            errors.append("approval schema: dynamic/recursive resolution is forbidden")
        for key, child in value.items():
            if key == "$ref":
                if not isinstance(child, str) or not child.startswith("#/"):
                    errors.append("approval schema: references must be local pointers")
                    continue
                target = root
                for part in child[2:].split("/"):
                    part = part.replace("~1", "/").replace("~0", "~")
                    if not isinstance(target, dict) or part not in target:
                        errors.append(f"approval schema: dangling reference {child}")
                        break
                    target = target[part]
            else:
                errors.extend(_local_refs(child, root))
    elif isinstance(value, list):
        for child in value:
            errors.extend(_local_refs(child, root))
    return errors


def check_approvals(store: dict | None, schema: dict, choices: dict, packets: dict) -> list[str]:
    """Structure, catalogue references and event chronology only; no attestation PASS."""
    if store is None:
        return ["approvals: register unavailable (missing, unreadable or invalid JSON); "
                "approval evaluation unavailable, not an empty adoption register"]
    if not isinstance(schema, dict):
        return ["approval schema: expected an object"]
    if (schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("$id") != "urn:nm:blueprint:adoption-records:1"):
        return ["approval schema: unsupported identity or metaschema"]
    errors = _local_refs(schema, schema, is_root=True)
    if errors:
        return errors
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        return [f"approval schema: invalid schema: {error.message}"]
    validator = Draft202012Validator(schema, format_checker=_formats())
    errors = [f"approvals: {'/'.join(map(str, error.absolute_path)) or '/'}: {error.message}"
              for error in sorted(validator.iter_errors(store),
                                  key=lambda e: str(list(e.absolute_path)))]
    if errors:
        return errors
    choice_map = {row["id"]: row for row in choices["choices"]}
    packet_map = {row["id"]: row for row in packets["packets"]}
    rows = store["records"]
    ids = [row["id"] for row in rows]
    records = {row["id"]: row for row in rows}
    for identifier, count in Counter(ids).items():
        if count > 1:
            errors.append(f"approvals: duplicate record {identifier}")
    for row in rows:
        label = row["id"]
        choice = choice_map.get(row["choice"])
        if choice is None:
            errors.append(f"{label}: unknown choice {row['choice']}")
        elif row["scope"]["gate"] not in choice["approval_required_for"]:
            errors.append(f"{label}: gate does not apply to choice")
        for packet in row["scope"]["packets"]:
            if packet not in packet_map:
                errors.append(f"{label}: unknown packet {packet}")
            elif row["choice"] not in packet_map[packet]["decisions"]:
                errors.append(f"{label}: choice does not govern packet {packet}")
        if not (_instant(row["approved_at"]) <= _instant(row["effective_from"])
                < _instant(row["valid_until"])):
            errors.append(f"{label}: require approved_at <= effective_from < valid_until")
        for kind, key in (("approvers", "person_id"), ("conditions", "id")):
            values = [entry[key] for entry in row[kind]]
            if len(values) != len(set(values)):
                errors.append(f"{label}: duplicate {kind} identity")
        for prior_id in row["supersedes"]:
            prior = records.get(prior_id)
            if prior is None:
                errors.append(f"{label}: unknown superseded record {prior_id}")
            elif (prior_id == label or prior["choice"] != row["choice"]
                  or _instant(prior["approved_at"]) >= _instant(row["approved_at"])):
                errors.append(f"{label}: supersession requires older record of the same choice")
    revocation_ids = [row["id"] for row in store["revocations"]]
    if len(revocation_ids) != len(set(revocation_ids)):
        errors.append("approvals: duplicate revocation identity")
    for row in store["revocations"]:
        prior = records.get(row["approval_id"])
        if prior is None:
            errors.append(f"{row['id']}: unknown revoked record {row['approval_id']}")
        elif _instant(row["effective_at"]) < _instant(prior["approved_at"]):
            errors.append(f"{row['id']}: revocation predates approval")
    return errors


def adoption_labels(store: dict | None, choices: dict) -> dict[str, str]:
    """One source for CLI/workbook presence labels, not an authority resolver."""
    if (not isinstance(store, dict)
            or set(store) != {"schema", "purpose", "records", "revocations"}
            or type(store.get("schema")) is not int or store["schema"] != 1
            or not isinstance(store.get("records"), list)
            or not isinstance(store.get("revocations"), list)
            or any(not isinstance(row, dict)
                   or not isinstance(row.get("id"), str)
                   or not isinstance(row.get("choice"), str)
                   for row in store["records"])):
        return {choice["id"]: "approval evaluation unavailable / manual verification required"
                for choice in choices["choices"]}
    labels = {}
    for choice in choices["choices"]:
        matching = [row for row in store["records"]
                    if isinstance(row, dict) and row.get("choice") == choice["id"]]
        if not matching:
            labels[choice["id"]] = "no adoption record recorded"
        else:
            identifiers = ", ".join(sorted(str(row.get("id", "malformed")) for row in matching))
            labels[choice["id"]] = ("approval not machine-resolved / manual verification "
                                    f"required ({identifiers})")
    return labels


def adoption_blockers(store: dict | None, choices: dict) -> list[str]:
    """Presence-only report. Call after structural checks; never grants a gate.

    Even a populated, perfectly shaped record is unverified. The checker does
    not fetch signed artifacts, establish human authority, or evaluate scope.
    """
    return [f"{choice}: {label}; this checker has not verified authority, scope, "
            "validity, revocation or evidence."
            for choice, label in adoption_labels(store, choices).items()]
