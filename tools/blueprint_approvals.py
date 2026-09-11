"""Check adoption-record structure, never verify a signature or grant authority.

Readiness reports the presence of manual records honestly. It deliberately has
no Boolean bypass or 'valid' state: BK-80 owns the future verified resolver.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

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


def adoption_blockers(store: dict | None, choices: dict,
                      packets: dict | None = None, *,
                      now: datetime | None = None) -> list[str]:
    """What still stands between each CHOICE and the gate it governs.

    BK-80-AC6 REPLACED THE ABSTENTION. This returned the same sentence for
    every choice -- "this checker has not verified authority, scope, validity,
    revocation or evidence" -- which was honest while nothing resolved and
    became a permanent refusal to look once `resolve` existed.

    It now reports the resolved state per choice and per gate the choice
    declares it is required for, because an approval valid at a packet gate
    says nothing about a deployment gate and reporting one line per choice
    would have to pick one of them to be wrong about.
    """
    if packets is None:
        # NOT ASSESSED, SAID AS A VALUE. Without the packet catalogue the scope
        # half cannot be evaluated at all, and a resolver silently skipping it
        # would report `valid` for an approval that names no packet.
        return [f"{choice}: scope cannot be resolved without the packet "
                f"catalogue; manual verification required"
                for choice in sorted(row["id"] for row in choices["choices"])]
    lines: list[str] = []
    for choice in choices["choices"]:
        for gate in choice.get("approval_required_for") or ["unspecified"]:
            got = resolve(store, choices, packets,
                          choice=choice["id"], gate=gate, now=now)
            if not got.authorises:
                lines.append(f"{choice['id']} at the {gate} gate: "
                             f"{got.state} -- {got.why}")
    return lines


# ------------------------------------------------------------ resolution ---
#
# BK-80-AC6. Everything above is STRUCTURE: does this store parse, do its
# references resolve, is its chronology coherent. None of it answers the
# question a packet actually asks -- MAY THIS DECISION PROCEED -- and the
# labels it produced said only "not machine-resolved" for every choice, which
# was honest while nothing resolved and is a permanent abstention once
# something can.
#
# SEVEN STATES, AND SIX OF THEM ARE REFUSALS. The criterion names them because
# collapsing them loses the only information the reader can act on: `expired`
# is renewed, `revoked` is not, `out_of_scope` means somebody approved a
# different thing, and `stale` means the thing they approved has changed under
# them. A boolean would send all four to the same place.
#
# THIS FUNCTION READS THE APPROVAL STORE AND NOTHING ELSE. It never consults a
# measurement, an evaluation result or a proposal flag -- "resolve scoped
# CHOICE adoption records separately from measurements" is the criterion's
# first clause, and a resolver that could see a PASS would eventually be asked
# to accept one.

NOT_RECORDED = "not_recorded"
UNVERIFIED = "unverified"
VALID = "valid"
STALE = "stale"
EXPIRED = "expired"
REVOKED = "revoked"
OUT_OF_SCOPE = "out_of_scope"

STATES = (NOT_RECORDED, UNVERIFIED, VALID, STALE, EXPIRED, REVOKED, OUT_OF_SCOPE)


@dataclass(frozen=True)
class Resolution:
    """What the approval register says about one decision, at one gate."""

    state: str
    why: str
    record: str | None = None

    @property
    def authorises(self) -> bool:
        """ONLY `valid`. Every other state is a refusal that reads differently
        to a person and identically to a gate."""
        return self.state == VALID


def resolve(store: dict | None, choices: dict, packets: dict, *,
            choice: str, gate: str, packet: str | None = None,
            proposal_sha256: str | None = None,
            configuration: str | None = None,
            now: datetime | None = None,
            schema: dict | None = None) -> Resolution:
    """The state of one CHOICE's adoption, for one gate and one packet."""
    moment = now or datetime.now(timezone.utc)

    if schema is not None:
        structural = check_approvals(store, schema, choices, packets)
        if structural:
            return Resolution(
                UNVERIFIED,
                f"the adoption register does not verify: {structural[0]}")
    if not isinstance(store, dict) or not isinstance(store.get("records"), list):
        # UNVERIFIED, NOT NOT_RECORDED. An unreadable register is not an empty
        # one, and reporting it as "nothing recorded" sends the reader to write
        # an approval that may already exist.
        return Resolution(UNVERIFIED,
                          "the adoption register is unavailable or unreadable, "
                          "which is not the same as no approval having been given")

    superseded = {prior for row in store["records"]
                  for prior in (row.get("supersedes") or [])}
    candidates = [row for row in store["records"]
                  if row.get("choice") == choice and row.get("id") not in superseded]
    if not candidates:
        return Resolution(NOT_RECORDED,
                          f"no adoption record names {choice}")

    row = max(candidates, key=lambda r: str(r.get("approved_at") or ""))
    label = row.get("id")

    for revocation in store.get("revocations") or []:
        if (revocation.get("approval_id") == label
                and _instant(revocation.get("effective_at")) <= moment):
            return Resolution(REVOKED,
                              f"{label} was revoked at "
                              f"{revocation.get('effective_at')}: "
                              f"{revocation.get('reason') or 'no reason recorded'}",
                              label)

    if _instant(row.get("valid_until")) <= moment:
        return Resolution(EXPIRED,
                          f"{label} expired at {row.get('valid_until')}", label)
    if moment < _instant(row.get("effective_from")):
        return Resolution(UNVERIFIED,
                          f"{label} does not take effect until "
                          f"{row.get('effective_from')}", label)

    scope = row.get("scope") or {}
    if scope.get("gate") != gate:
        return Resolution(OUT_OF_SCOPE,
                          f"{label} approves the {scope.get('gate')!r} gate and "
                          f"this is {gate!r}", label)
    if packet is not None and packet not in (scope.get("packets") or []):
        return Resolution(OUT_OF_SCOPE,
                          f"{label} does not name packet {packet}", label)

    if proposal_sha256 is not None and row.get("proposal_sha256") != proposal_sha256:
        return Resolution(STALE,
                          f"{label} approved proposal "
                          f"{row.get('proposal_sha256')} and the current "
                          f"proposal is {proposal_sha256}", label)
    if configuration is not None and scope.get("configuration") != configuration:
        return Resolution(STALE,
                          f"{label} approved configuration "
                          f"{scope.get('configuration')!r} and this is "
                          f"{configuration!r}", label)

    if not (row.get("signed_record") or {}).get("sha256"):
        return Resolution(UNVERIFIED,
                          f"{label} carries no signed record", label)
    qualified = [a for a in row.get("approvers") or []
                 if str(a.get("authority_basis") or "").strip()
                 and (a.get("authority_evidence") or {}).get("sha256")]
    if not qualified:
        return Resolution(UNVERIFIED,
                          f"{label} names no approver whose authority is "
                          f"stated and evidenced", label)
    unmet = [c.get("id") for c in row.get("conditions") or []
             if not (c.get("evidence") or {}).get("sha256")]
    if unmet:
        return Resolution(UNVERIFIED,
                          f"{label} carries conditions with no evidence: "
                          f"{', '.join(map(str, unmet))}", label)

    return Resolution(VALID,
                      f"{label} authorises {choice} at the {gate} gate", label)
