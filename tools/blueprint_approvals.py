"""Check adoption-record structure, never verify a signature or grant authority.

Readiness reports the presence of manual records honestly. It deliberately has
no Boolean bypass or 'valid' state: BK-80 owns the future verified resolver.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from tools.evidence_verification import (
    EvidenceVerifier,
    UnavailableVerifier,
    Verification,
    canonical_json,
)


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


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


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
    reasons: tuple[str, ...]
    record: str | None = None
    availability: str = "available"
    attempted_scope: dict | None = None

    @property
    def why(self) -> str:
        return "; ".join(self.reasons)

    @property
    def authorises(self) -> bool:
        """ONLY `valid`. Every other state is a refusal that reads differently
        to a person and identically to a gate."""
        return self.availability == "available" and self.state == VALID


EVALUATION_UNAVAILABLE = "evaluation_unavailable"


def _resolution(state: str, reason: str | Iterable[str], record: str | None = None,
                *, available: bool = True,
                attempted_scope: dict | None = None) -> Resolution:
    reasons = (reason,) if isinstance(reason, str) else tuple(reason)
    return Resolution(
        state, reasons, record,
        "available" if available else EVALUATION_UNAVAILABLE,
        attempted_scope,
    )


def _unavailable(reasons: Iterable[str], record: str | None,
                 attempted_scope: dict) -> Resolution:
    return _resolution(UNVERIFIED, reasons, record, available=False,
                       attempted_scope=attempted_scope)


def _artifact_equal(left: object, right: object) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def _verification_reasons(check: Verification) -> list[str]:
    return list(check.reasons) or ["the verifier supplied no reason"]


def _authenticate_record(row: dict, verifier: EvidenceVerifier, *,
                         required_approvers: frozenset[str],
                         gate: str, at: datetime) -> tuple[list[str], list[str]]:
    """Return unavailable and unverified reasons for the adoption itself."""
    unavailable: list[str] = []
    refused: list[str] = []
    approvers = row.get("approvers") or []
    people = frozenset(str(person.get("person_id")) for person in approvers
                       if isinstance(person, dict) and person.get("person_id"))
    missing = sorted(required_approvers - people)
    if missing:
        refused.append("required joint approver(s) are absent: " + ", ".join(missing))

    payload = {key: value for key, value in row.items() if key != "signed_record"}
    signed = verifier.signed_payload(
        row.get("signed_record"), purpose=f"approval {row.get('id')} signed record",
        expected_payload=payload, required_signers=people,
    )
    if not signed.verified:
        target = unavailable if not signed.available else refused
        target.extend(_verification_reasons(signed))

    approved_at = _instant(row.get("approved_at"))
    if approved_at is None:
        refused.append("approval time is not a timezone-bearing instant")
        return unavailable, refused
    for person in approvers:
        if not isinstance(person, dict):
            refused.append("an approver row is malformed")
            continue
        checked = verifier.authority(
            person.get("authority_evidence"),
            person_id=str(person.get("person_id") or ""),
            role=str(person.get("role") or ""),
            basis=str(person.get("authority_basis") or ""),
            scope=f"approval:{row.get('choice')}:{gate}",
            at=approved_at,
        )
        if not checked.verified:
            target = unavailable if not checked.available else refused
            target.extend(_verification_reasons(checked))
    return unavailable, refused


def _authenticate_revocation(revocation: dict, row: dict,
                             verifier: EvidenceVerifier) -> tuple[list[str], list[str]]:
    unavailable: list[str] = []
    refused: list[str] = []
    person = revocation.get("revoked_by") or {}
    person_id = str(person.get("person_id") or "")
    payload = {key: value for key, value in revocation.items()
               if key != "signed_record"}
    signed = verifier.signed_payload(
        revocation.get("signed_record"),
        purpose=f"revocation {revocation.get('id')}",
        expected_payload=payload, required_signers=frozenset({person_id}),
    )
    if not signed.verified:
        target = unavailable if not signed.available else refused
        target.extend(_verification_reasons(signed))
    effective_at = _instant(revocation.get("effective_at"))
    if effective_at is None:
        refused.append("revocation time is not a timezone-bearing instant")
        return unavailable, refused
    authority = verifier.authority(
        person.get("authority_evidence"), person_id=person_id,
        role=str(person.get("role") or ""),
        basis=str(person.get("authority_basis") or ""),
        scope=f"revoke:{row.get('choice')}:{(row.get('scope') or {}).get('gate')}",
        at=effective_at,
    )
    if not authority.verified:
        target = unavailable if not authority.available else refused
        target.extend(_verification_reasons(authority))
    return unavailable, refused


def resolve(store: dict | None, choices: dict, packets: dict, *,
            choice: str, gate: str, packet: str | None = None,
            proposal_sha256: str | None = None,
            environment: str | None = None,
            release_profile: str | None = None,
            release_manifest: object | None = None,
            configuration: object | None = None,
            coverage_manifest: object | None = None,
            capabilities: Iterable[str] | None = None,
            data_classes: Iterable[str] | None = None,
            run_id: str | None = None,
            used_run_ids: frozenset[str] = frozenset(),
            required_approvers: frozenset[str] = frozenset(),
            verifier: EvidenceVerifier | None = None,
            time_available: bool = True,
            now: datetime | None = None,
            schema: dict | None = None) -> Resolution:
    """The state of one CHOICE's adoption, for one gate and one packet."""
    attempted_scope = {
        "gate": gate, "environment": environment,
        "release_profile": release_profile,
        "release_manifest": release_manifest, "configuration": configuration,
        "coverage_manifest": coverage_manifest, "packet": packet,
        "capabilities": sorted(capabilities or ()),
        "data_classes": sorted(data_classes or ()), "run_id": run_id,
    }
    if not time_available:
        return _unavailable(["the trusted time source is unavailable"], None,
                            attempted_scope)
    moment = now or datetime.now(timezone.utc)
    verifier = verifier or UnavailableVerifier()

    if not isinstance(store, dict) or not isinstance(store.get("records"), list):
        # The bytes could not be interpreted as a register. That is an
        # unavailable assessment, not a successfully-read empty population.
        return _unavailable(
            ["the adoption register is unavailable or unreadable, which is not "
             "the same as no approval having been given"], None, attempted_scope)

    if schema is not None:
        structural = check_approvals(store, schema, choices, packets)
        if structural:
            return _resolution(
                UNVERIFIED, f"the adoption register does not verify: {structural[0]}",
                attempted_scope=attempted_scope)
    candidates = [row for row in store["records"]
                  if row.get("choice") == choice]
    if not candidates:
        return _resolution(NOT_RECORDED, f"no adoption record names {choice}",
                           attempted_scope=attempted_scope)

    if not required_approvers:
        return _unavailable(
            ["the required human-approval policy was not supplied"], None,
            attempted_scope)

    # AUTHENTICATE BEFORE SELECTING. Scope and supersession live inside the
    # signed payload; using either to choose a candidate first would let an
    # unsigned index row decide which real approval the resolver sees. Every
    # candidate for this choice is checked. A malformed competing record is a
    # safe refusal, never a reason to fall back to a broader old permission.
    for candidate in candidates:
        candidate_gate = str((candidate.get("scope") or {}).get("gate") or gate)
        unavailable, refused = _authenticate_record(
            candidate, verifier, required_approvers=required_approvers,
            gate=candidate_gate, at=moment,
        )
        if unavailable:
            return _unavailable(
                ["a competing approval cannot be evaluated", *unavailable],
                str(candidate.get("id") or "") or None, attempted_scope)
        if refused:
            return _resolution(
                UNVERIFIED,
                ["an unverified competing approval prevents permission", *refused],
                str(candidate.get("id") or "") or None,
                attempted_scope=attempted_scope)

    superseded_by: dict[str, list[str]] = {}
    for candidate in candidates:
        for prior in candidate.get("supersedes") or []:
            superseded_by.setdefault(str(prior), []).append(
                str(candidate.get("id")))
    active = [candidate for candidate in candidates
              if str(candidate.get("id")) not in superseded_by]

    def applies(candidate: dict) -> bool:
        scope = candidate.get("scope") or {}
        return (scope.get("gate") == gate
                and (packet is None or packet in (scope.get("packets") or [])))

    applicable = [candidate for candidate in active if applies(candidate)]
    if len(applicable) > 1:
        labels = ", ".join(sorted(str(row.get("id")) for row in applicable))
        return _resolution(
            UNVERIFIED,
            f"multiple current approval records ({labels}) govern this gate and "
            "packet; an explicit authenticated supersession is required",
            attempted_scope=attempted_scope)
    if not applicable:
        retired = [candidate for candidate in candidates
                   if applies(candidate)
                   and str(candidate.get("id")) in superseded_by]
        if retired:
            prior = max(retired, key=lambda r: str(r.get("approved_at") or ""))
            replacements = ", ".join(sorted(
                superseded_by[str(prior.get("id"))]))
            return _resolution(
                STALE,
                f"{prior.get('id')} was superseded by verified record(s) "
                f"{replacements}, whose scope does not authorise this attempt",
                str(prior.get("id")), attempted_scope=attempted_scope)
        newest = max(candidates, key=lambda r: str(r.get("approved_at") or ""))
        return _resolution(
            OUT_OF_SCOPE,
            f"no current verified record for {choice} names gate {gate!r}"
            + (f" and packet {packet}" if packet is not None else ""),
            str(newest.get("id")), attempted_scope=attempted_scope)

    row = applicable[0]
    label = row.get("id")

    for revocation in store.get("revocations") or []:
        effective_at = _instant(revocation.get("effective_at"))
        if (revocation.get("approval_id") == label and effective_at is not None
                and effective_at <= moment):
            unavailable, refused = _authenticate_revocation(
                revocation, row, verifier)
            if unavailable:
                return _unavailable(
                    ["a recorded revocation cannot be evaluated", *unavailable],
                    label, attempted_scope)
            if refused:
                return _resolution(
                    UNVERIFIED,
                    ["an unverified competing revocation prevents permission", *refused],
                    label, attempted_scope=attempted_scope)
            return _resolution(
                REVOKED,
                f"{label} was revoked at {revocation.get('effective_at')}: "
                f"{revocation.get('reason') or 'no reason recorded'}",
                label, attempted_scope=attempted_scope)

    valid_until = _instant(row.get("valid_until"))
    effective_from = _instant(row.get("effective_from"))
    if valid_until is None or effective_from is None:
        return _resolution(
            UNVERIFIED, f"{label} has unreadable validity dates", label,
            attempted_scope=attempted_scope)
    if valid_until <= moment:
        return _resolution(EXPIRED, f"{label} expired at {row.get('valid_until')}",
                           label, attempted_scope=attempted_scope)
    if moment < effective_from:
        return _resolution(
            UNVERIFIED,
            f"{label} does not take effect until {row.get('effective_from')}",
            label, attempted_scope=attempted_scope)

    scope = row.get("scope") or {}
    if scope.get("gate") != gate:
        return _resolution(
            OUT_OF_SCOPE, f"{label} approves the {scope.get('gate')!r} gate and "
            f"this is {gate!r}", label, attempted_scope=attempted_scope)
    if packet is not None and packet not in (scope.get("packets") or []):
        return _resolution(OUT_OF_SCOPE, f"{label} does not name packet {packet}",
                           label, attempted_scope=attempted_scope)

    for field, attempted in (("environment", environment),
                             ("release_profile", release_profile)):
        if attempted is None:
            return _unavailable([f"the attempted {field} was not supplied"], label,
                                attempted_scope)
        if scope.get(field) != attempted:
            return _resolution(
                OUT_OF_SCOPE, f"{label} does not permit {field} {attempted!r}",
                label, attempted_scope=attempted_scope)
    for field, attempted in (("capabilities", set(capabilities or ())),
                             ("data_classes", set(data_classes or ()))):
        if not attempted:
            return _unavailable([f"the attempted {field} population is empty"], label,
                                attempted_scope)
        missing = sorted(attempted - set(scope.get(field) or ()))
        if missing:
            return _resolution(
                OUT_OF_SCOPE, f"{label} does not permit {field}: {', '.join(missing)}",
                label, attempted_scope=attempted_scope)
    approved_run = scope.get("run_id")
    if gate in ("approved_real_model", "paid_or_long_load") and run_id is None:
        return _unavailable(["the attempted bounded run identity was not supplied"],
                            label, attempted_scope)
    if approved_run != run_id:
        return _resolution(
            OUT_OF_SCOPE, f"{label} permits run {approved_run!r}, not {run_id!r}",
            label, attempted_scope=attempted_scope)
    if run_id is not None and run_id in used_run_ids:
        return _resolution(
            OUT_OF_SCOPE, f"bounded run {run_id!r} has already consumed its approval",
            label, attempted_scope=attempted_scope)

    if proposal_sha256 is not None and row.get("proposal_sha256") != proposal_sha256:
        return _resolution(
            STALE, f"{label} approved proposal {row.get('proposal_sha256')} and "
            f"the current proposal is {proposal_sha256}", label,
            attempted_scope=attempted_scope)
    if proposal_sha256 is None:
        choice_row = next((candidate for candidate in choices.get("choices") or []
                           if candidate.get("id") == choice), None)
        if choice_row is None:
            return _unavailable([f"the current proposal {choice} is unavailable"],
                                label, attempted_scope)
        proposal_sha256 = hashlib.sha256(canonical_json(choice_row)).hexdigest()
        if row.get("proposal_sha256") != proposal_sha256:
            return _resolution(
                STALE, f"{label} approved a different proposal identity", label,
                attempted_scope=attempted_scope)

    artifact_attempts = {
        "release_manifest": release_manifest,
        "configuration": configuration,
        "coverage_manifest": coverage_manifest,
    }
    for field, attempted in artifact_attempts.items():
        if attempted is None:
            return _unavailable([f"the attempted {field} identity was not supplied"],
                                label, attempted_scope)
        if not _artifact_equal(scope.get(field), attempted):
            return _resolution(
                STALE, f"{label} approved a different {field} identity", label,
                attempted_scope=attempted_scope)
        checked = verifier.integrity(scope.get(field), purpose=f"{label} {field}")
        if not checked.verified:
            reasons = _verification_reasons(checked)
            if not checked.available:
                return _unavailable(reasons, label, attempted_scope)
            return _resolution(UNVERIFIED, reasons, label,
                               attempted_scope=attempted_scope)

    for condition in row.get("conditions") or []:
        checked = verifier.condition(
            condition.get("evidence"), approval_id=str(label),
            condition_id=str(condition.get("id") or ""),
            requirement=str(condition.get("requirement") or ""), at=moment,
        )
        if not checked.verified:
            reasons = _verification_reasons(checked)
            if not checked.available:
                return _unavailable(reasons, label, attempted_scope)
            return _resolution(UNVERIFIED, reasons, label,
                               attempted_scope=attempted_scope)

    # Authority is checked again at attempted use. A valid signature proves a
    # historical act; it does not make a lapsed delegation current forever.
    for person in row.get("approvers") or []:
        checked = verifier.authority(
            person.get("authority_evidence"),
            person_id=str(person.get("person_id") or ""),
            role=str(person.get("role") or ""),
            basis=str(person.get("authority_basis") or ""),
            scope=f"approval:{choice}:{gate}", at=moment,
        )
        if not checked.verified:
            reasons = _verification_reasons(checked)
            if not checked.available:
                return _unavailable(reasons, label, attempted_scope)
            return _resolution(UNVERIFIED, reasons, label,
                               attempted_scope=attempted_scope)

    return _resolution(
        VALID, f"{label} authorises {choice} at the {gate} gate", label,
        attempted_scope=attempted_scope)


def resolve_packet_approvals(
        store: dict | None, choices: dict, packets: dict, *,
        packet: str, gate: str, environment: str,
        release_profile: str, release_manifest: object,
        configuration: object, coverage_manifest: object,
        capabilities: Iterable[str], data_classes: Iterable[str],
        run_id: str | None, proposal_sha256: Mapping[str, str],
        required_approvers: Mapping[str, frozenset[str]],
        verifier: EvidenceVerifier, used_run_ids: frozenset[str] = frozenset(),
        time_available: bool = True, now: datetime | None = None,
        schema: dict | None = None) -> dict[str, Resolution]:
    """Resolve only the choices applicable to one actual packet attempt.

    This is deliberately not named ``packet_eligible``: approval is one
    prerequisite and cannot make incomplete build/evidence/deployment gates
    disappear. Callers combine these resolutions with those separate gates.
    """
    packet_row = next((row for row in packets.get("packets") or []
                       if row.get("id") == packet), None)
    if packet_row is None:
        unavailable = _unavailable(
            [f"unknown attempted packet {packet}"], None,
            {"packet": packet, "gate": gate})
        return {"__packet__": unavailable}
    choice_map = {row.get("id"): row for row in choices.get("choices") or []}
    applicable = [choice_id for choice_id in packet_row.get("decisions") or []
                  if gate in ((choice_map.get(choice_id) or {})
                              .get("approval_required_for", []))]
    return {
        choice_id: resolve(
            store, choices, packets, choice=choice_id, gate=gate, packet=packet,
            proposal_sha256=proposal_sha256.get(choice_id),
            environment=environment, release_profile=release_profile,
            release_manifest=release_manifest, configuration=configuration,
            coverage_manifest=coverage_manifest, capabilities=capabilities,
            data_classes=data_classes, run_id=run_id,
            used_run_ids=used_run_ids,
            required_approvers=required_approvers.get(choice_id, frozenset()),
            verifier=verifier, time_available=time_available, now=now,
            schema=schema,
        )
        for choice_id in applicable
    }
