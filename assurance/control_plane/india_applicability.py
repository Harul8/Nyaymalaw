"""Validate and render the dated India applicability review packet.

This module does not give legal advice and cannot make BK-85-AC3 pass.  It
keeps the review population, its legal propositions, the unsigned counsel
boundary and the later adoption packets machine-checkable so that a qualified
reviewer is asked to decide the actual product rather than approve a checklist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

SOURCE = ROOT / "docs" / "blueprint" / "india_applicability_review.json"
VIEW = ROOT / "docs" / "blueprint" / "INDIA_APPLICABILITY_REVIEW.md"
TEMPLATE = ROOT / "docs" / "blueprint" / "BK-85-AC3.counsel-review.template.json"

TOP_LEVEL = {
    "schema",
    "artifact",
    "criterion",
    "status",
    "as_of",
    "jurisdiction",
    "scope",
    "legal_sources",
    "role_by_purpose",
    "permissions",
    "retention",
    "incident_clocks",
    "accountability",
    "review_reservations",
    "reassessment_triggers",
    "counsel_signoff",
    "approval_packets",
}
REQUIRED_SOURCES = {f"IN-{number:02}" for number in range(1, 11)}
REQUIRED_PURPOSES = {
    "PURPOSE-ACCOUNT",
    "PURPOSE-MATTER",
    "PURPOSE-CONFLICT",
    "PURPOSE-SUPPORT",
    "PURPOSE-SECURITY",
    "PURPOSE-BILLING",
    "PURPOSE-EXPORT",
    "PURPOSE-IMPROVEMENT",
}
REQUIRED_PERMISSIONS = {
    "PERMISSION-ACCOUNT",
    "PERMISSION-MATTER",
    "PERMISSION-THIRD-PARTY",
    "PERMISSION-CLAIM",
    "PERMISSION-SECURITY",
    "PERMISSION-IMPROVEMENT",
    "PERMISSION-CHILD-SPECIAL",
}
REQUIRED_RETENTION = {
    "RETENTION-MATTER",
    "RETENTION-ACCOUNT",
    "RETENTION-SECURITY-LOG",
    "RETENTION-INCIDENT",
    "RETENTION-BACKUP",
    "RETENTION-AUTHORITY",
}
REQUIRED_CLOCKS = {
    "CLOCK-INTERNAL",
    "CLOCK-CERT-IN",
    "CLOCK-DPDP-PRINCIPAL",
    "CLOCK-DPDP-BOARD",
    "CLOCK-CONTRACT",
    "CLOCK-SECTOR-COURT",
}
REQUIRED_ACCOUNTABILITY = {
    "OWNER-FIRM",
    "OWNER-NM-PURPOSE",
    "OWNER-PRIVACY-LEGAL",
    "OWNER-CERT-POC",
    "OWNER-INCIDENT",
    "OWNER-RETENTION",
    "OWNER-PROCESSOR",
    "OWNER-COUNSEL",
    "OWNER-RELEASE",
}
APPROVAL_CHOICES = {"CHOICE-01", "CHOICE-07", "CHOICE-08", "CHOICE-10"}
OFFICIAL_HOSTS = ("meity.gov.in", "indiacode.nic.in", "cert-in.org.in", "mha.gov.in")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
STRUCTURED_RECORD_FIELDS = {
    "schema", "criterion", "level", "result", "subject", "method",
    "actor", "authority", "rubric", "population", "reservations",
    "observed_at", "subject_identity", "configuration_identity",
    "attestation",
}


class DuplicateJSONKeyError(ValueError):
    """An ambiguous authored legal record is unreadable, not best-effort data."""


def _unique_keys(pairs: list[tuple]) -> dict:
    value = {}
    for key, child in pairs:
        if key in value:
            raise DuplicateJSONKeyError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def load(path: Path = SOURCE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)


def proposal_digest(choice: dict) -> str:
    payload = json.dumps(choice, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def source_digest(document: dict) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _rows(document: dict, field: str, required: set[str], errors: list[str]) -> dict[str, dict]:
    rows = document.get(field)
    if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows):
        errors.append(f"India applicability {field}: empty or malformed population")
        return {}
    identifiers = [row.get("id") for row in rows]
    if len(identifiers) != len(set(identifiers)):
        errors.append(f"India applicability {field}: duplicate ids")
    if set(identifiers) != required:
        errors.append(
            f"India applicability {field}: expected {sorted(required)}, "
            f"got {sorted(map(str, identifiers))}"
        )
    return {str(row.get("id")): row for row in rows}


def _nonempty(row: dict, fields: tuple[str, ...], where: str, errors: list[str]) -> None:
    for field in fields:
        if row.get(field) in (None, "", [], {}):
            errors.append(f"{where}: missing {field}")


def check(document: dict, decisions: dict, approvals: dict | None) -> list[str]:
    """Return every structural, legal-boundary and catalogue-reconciliation defect."""
    errors: list[str] = []
    if not isinstance(document, dict) or set(document) != TOP_LEVEL:
        return ["India applicability: unsupported schema or fields"]
    if document.get("schema") != 1 or document.get("artifact") != "counsel_ready_draft":
        errors.append("India applicability: unsupported artifact identity")
    if document.get("criterion") != "BK-85-AC3":
        errors.append("India applicability: criterion must be BK-85-AC3")
    if document.get("status") != "COUNSEL_REVIEW_REQUIRED":
        errors.append("India applicability: an unsigned packet must remain COUNSEL_REVIEW_REQUIRED")
    as_of = _instant(document.get("as_of"))
    if as_of is None:
        errors.append("India applicability: as_of must be a timezone-bearing instant")
    if document.get("jurisdiction") != "India":
        errors.append("India applicability: this packet is limited to India")

    scope = document.get("scope")
    if not isinstance(scope, dict):
        errors.append("India applicability scope: missing object")
    else:
        _nonempty(
            scope,
            ("service", "operating_assumptions", "excluded_without_separate_review"),
            "India applicability scope",
            errors,
        )

    sources = _rows(document, "legal_sources", REQUIRED_SOURCES, errors)
    for identifier, row in sources.items():
        _nonempty(
            row,
            (
                "title",
                "instrument",
                "authority",
                "published_on",
                "operative_status",
                "commencement",
                "official_url",
                "applies_to",
                "claim_boundary",
            ),
            identifier,
            errors,
        )
        url = str(row.get("official_url") or "")
        if not url.startswith("https://") or not any(host in url for host in OFFICIAL_HOSTS):
            errors.append(
                f"{identifier}: legal proposition does not point to an official Indian source"
            )
    commencement = sources.get("IN-02", {})
    if (
        commencement.get("instrument") != "G.S.R. 843(E)"
        or commencement.get("operative_status") != "partially_operative"
    ):
        errors.append("IN-02: phased DPDP commencement is not preserved")
    rules = sources.get("IN-03", {})
    if (
        rules.get("instrument") != "G.S.R. 846(E)"
        or rules.get("operative_status") != "partially_operative"
    ):
        errors.append("IN-03: phased DPDP Rules commencement is not preserved")
    if "not blanket localisation" not in str(commencement.get("claim_boundary") or "").lower():
        errors.append(
            "IN-02: India-only policy has been confused with blanket statutory localisation"
        )

    roles = _rows(document, "role_by_purpose", REQUIRED_PURPOSES, errors)
    allowed_roles = {
        "data_fiduciary",
        "data_processor",
        "not_applicable",
        "conditional_by_operation",
    }
    for identifier, row in roles.items():
        _nonempty(
            row,
            ("purpose", "firm_role", "nm_role", "provider_role", "accountability", "boundary"),
            identifier,
            errors,
        )
        for field in ("firm_role", "nm_role", "provider_role"):
            if row.get(field) not in allowed_roles:
                errors.append(f"{identifier}: {field} is not a purpose-specific legal role")
    nm_roles = {row.get("nm_role") for row in roles.values()}
    if not {"data_fiduciary", "data_processor"}.issubset(nm_roles):
        errors.append("India applicability roles: one blanket processor/fiduciary label covers NM")

    permissions = _rows(document, "permissions", REQUIRED_PERMISSIONS, errors)
    for identifier, row in permissions.items():
        _nonempty(
            row,
            (
                "purpose",
                "current_position",
                "future_dpdp_position",
                "product_rule",
                "decision_owner",
                "reservations",
            ),
            identifier,
            errors,
        )
    improvement = permissions.get("PERMISSION-IMPROVEMENT", {})
    if improvement.get("product_rule") != "matter_content_prohibited_by_default":
        errors.append("PERMISSION-IMPROVEMENT: matter content is not prohibited by default")
    claim = permissions.get("PERMISSION-CLAIM", {})
    if "not_blanket" not in str(claim.get("future_dpdp_position") or ""):
        errors.append("PERMISSION-CLAIM: the future legal-claim exemption is stated as blanket")

    retention = _rows(document, "retention", REQUIRED_RETENTION, errors)
    for identifier, row in retention.items():
        _nonempty(
            row,
            (
                "record_class",
                "current_duty",
                "ordinary_rule",
                "hold_rule",
                "erasure_restore_rule",
                "owner",
            ),
            identifier,
            errors,
        )
    security_log = retention.get("RETENTION-SECURITY-LOG", {})
    if security_log.get("current_minimum") != "180_days_in_India_for_ICT_logs":
        errors.append("RETENTION-SECURITY-LOG: current CERT-In log floor is missing")
    if security_log.get("future_dpdp_floor") != "one_year_from_2027-05-13_where_rule_6_applies":
        errors.append(
            "RETENTION-SECURITY-LOG: future DPDP security-log floor is missing or premature"
        )
    if any(row.get("hold_rule") == "none" for row in retention.values()):
        errors.append("India applicability retention: a record class ignores legal holds")

    clocks = _rows(document, "incident_clocks", REQUIRED_CLOCKS, errors)
    for identifier, row in clocks.items():
        _nonempty(
            row,
            (
                "trigger",
                "clock",
                "operative_status",
                "recipient",
                "owner",
                "minimum_action",
                "boundary",
            ),
            identifier,
            errors,
        )
    cert = clocks.get("CLOCK-CERT-IN", {})
    if cert.get("clock") != "within_6_hours" or cert.get("operative_status") != "operative_now":
        errors.append("CLOCK-CERT-IN: current six-hour clock is missing")
    principal = clocks.get("CLOCK-DPDP-PRINCIPAL", {})
    board = clocks.get("CLOCK-DPDP-BOARD", {})
    if (principal.get("clock"), principal.get("operative_status")) != (
        "without_delay",
        "future_from_2027-05-13",
    ):
        errors.append("CLOCK-DPDP-PRINCIPAL: future without-delay clock is misstated")
    if (board.get("clock"), board.get("operative_status")) != (
        "without_delay_then_detailed_report_within_72_hours",
        "future_from_2027-05-13",
    ):
        errors.append("CLOCK-DPDP-BOARD: future Board clock is misstated")

    owners = _rows(document, "accountability", REQUIRED_ACCOUNTABILITY, errors)
    for identifier, row in owners.items():
        _nonempty(
            row,
            ("role", "answerable_for", "cannot_delegate", "required_before"),
            identifier,
            errors,
        )

    reservations = document.get("review_reservations")
    if not isinstance(reservations, list) or len(reservations) < 8:
        errors.append("India applicability: material counsel reservations are absent")
    else:
        for index, row in enumerate(reservations, 1):
            if not isinstance(row, dict):
                errors.append(f"India applicability reservation {index}: malformed")
                continue
            _nonempty(
                row,
                ("id", "question", "owner", "blocks", "review_evidence"),
                f"India applicability reservation {index}",
                errors,
            )
    triggers = document.get("reassessment_triggers")
    if (
        not isinstance(triggers, list)
        or len(triggers) < 6
        or any(not str(x).strip() for x in triggers)
    ):
        errors.append("India applicability: reassessment triggers are incomplete")

    signoff = document.get("counsel_signoff")
    if not isinstance(signoff, dict):
        errors.append("India applicability counsel signoff: missing")
    else:
        _nonempty(
            signoff,
            (
                "state",
                "target",
                "required_reviewer",
                "required_record_fields",
                "authority_shape",
                "validity_rule",
                "signing_instruction",
            ),
            "India applicability counsel signoff",
            errors,
        )
        if (
            signoff.get("state") != "not_recorded"
            or signoff.get("target")
            != "docs/backlog/evidence/BK-85-AC3-counsel_review.json"
        ):
            errors.append(
                "India applicability counsel signoff: unsigned work looks "
                "signed or targets the wrong record"
            )
        authority = signoff.get("authority_shape") or {}
        evidence = authority.get("evidence") if isinstance(authority, dict) else None
        if (
            set(authority) != {"role", "basis", "evidence"}
            or not isinstance(evidence, dict)
            or set(evidence) != {"ref", "sha256"}
        ):
            errors.append(
                "India applicability counsel signoff: authority is not stated and evidenced"
            )
        if set(signoff.get("required_record_fields") or ()) != STRUCTURED_RECORD_FIELDS:
            errors.append(
                "India applicability counsel signoff: required fields do not match "
                "the authenticated structured-evidence boundary"
            )

    packets = _rows(document, "approval_packets", APPROVAL_CHOICES, errors)
    choice_rows = (
        {row.get("id"): row for row in decisions.get("choices", []) if isinstance(row, dict)}
        if isinstance(decisions, dict)
        else {}
    )
    approval_rows = approvals.get("records") if isinstance(approvals, dict) else None
    for identifier, packet in packets.items():
        _nonempty(
            packet,
            (
                "state",
                "sequence",
                "proposal_sha256",
                "approval_required_for",
                "approver",
                "required_inputs",
                "conditions",
                "must_not_claim",
            ),
            identifier,
            errors,
        )
        choice = choice_rows.get(identifier)
        if choice is None:
            errors.append(f"{identifier}: approval packet names no registered choice")
            continue
        if packet.get("proposal_sha256") != proposal_digest(choice):
            errors.append(f"{identifier}: approval packet is stale against decisions.json")
        if packet.get("approval_required_for") != choice.get("approval_required_for"):
            errors.append(f"{identifier}: approval gates differ from decisions.json")
        if packet.get("approver") != choice.get("approver"):
            errors.append(f"{identifier}: required approvers differ from decisions.json")
        # Register availability/shape has one owner: check_approvals.  Reconcile
        # status only when that population can actually be read; treating an
        # unavailable register as an empty list would turn "unknown" into
        # "nothing recorded", while reporting a competing structural error
        # here would mask the canonical approval failure in check_all.
        if isinstance(approval_rows, list):
            matching = [
                row
                for row in approval_rows
                if isinstance(row, dict) and row.get("choice") == identifier
            ]
            expected_state = "not_recorded" if not matching else "recorded_pending_resolution"
            if packet.get("state") != expected_state:
                errors.append(
                    f"{identifier}: packet says {packet.get('state')!r}; "
                    f"register says {expected_state!r}"
                )
        if packet.get("sequence") != "after_current_BK-85-AC3_counsel_review":
            errors.append(f"{identifier}: adoption is not ordered after the applicability review")
    return errors


def _cell(value: object) -> str:
    if isinstance(value, list):
        return "<br>".join(_cell(child) for child in value)
    value = str(value)
    if re.fullmatch(r"[a-z0-9_]+", value):
        value = value.replace("_", " ")
    return value.replace("|", "\\|").replace("\n", " ")


def render(document: dict) -> str:
    """Render the canonical packet as a reviewable human view."""
    digest = source_digest(document)
    lines = [
        "<!-- GENERATED by assurance/control_plane/india_applicability.py; "
        "edit india_applicability_review.json -->",
        f"<!-- source-sha256: {digest} -->",
        "",
        "# India applicability review packet",
        "",
        f"**Status:** {document['status']}",
        f"**As at:** {document['as_of']}",
        f"**Criterion:** {document['criterion']}",
        "**Effect:** Counsel-ready analysis only. It is not a legal opinion, "
        "adoption record, or PASS.",
        "",
        "## Scope and non-claims",
        "",
        document["scope"]["service"],
        "",
        "Operating assumptions: " + _cell(document["scope"]["operating_assumptions"]),
        "",
        "Excluded without separate review: "
        + _cell(document["scope"]["excluded_without_separate_review"]),
        "",
        "## Operative instruments and dates",
        "",
        "| ID | Instrument | Published | Position at review date | Applies to | Boundary |",
        "|---|---|---|---|---|---|",
    ]
    for row in document["legal_sources"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(row[k])
                for k in (
                    "id",
                    "instrument",
                    "published_on",
                    "operative_status",
                    "applies_to",
                    "claim_boundary",
                )
            )
            + " |"
        )
    lines += ["", "Official sources:", ""]
    for row in document["legal_sources"]:
        lines.append(
            f"- [{row['id']} — {row['title']}]({row['official_url']}): {row['commencement']}"
        )
    lines += [
        "",
        "## Legal roles by purpose",
        "",
        "| Purpose | Firm | NM | Provider | Accountability | Boundary |",
        "|---|---|---|---|---|---|",
    ]
    for row in document["role_by_purpose"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(row[k])
                for k in (
                    "purpose",
                    "firm_role",
                    "nm_role",
                    "provider_role",
                    "accountability",
                    "boundary",
                )
            )
            + " |"
        )
    lines += [
        "",
        "## Permissions and prohibitions",
        "",
        "| Purpose | Current position | Future DPDP position | Product rule | "
        "Owner | Reservations |",
        "|---|---|---|---|---|---|",
    ]
    for row in document["permissions"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(row[k])
                for k in (
                    "purpose",
                    "current_position",
                    "future_dpdp_position",
                    "product_rule",
                    "decision_owner",
                    "reservations",
                )
            )
            + " |"
        )
    lines += [
        "",
        "## Retention, holds, deletion and restore",
        "",
        "| Record class | Current duty/floor | Ordinary rule | Hold rule | "
        "Erasure/restore | Owner |",
        "|---|---|---|---|---|---|",
    ]
    for row in document["retention"]:
        floor = "; ".join(
            _cell(value)
            for value in (row.get("current_minimum"), row.get("future_dpdp_floor"))
            if value
        )
        lines.append(
            "| "
            + " | ".join(
                map(
                    _cell,
                    (
                        row["record_class"],
                        row["current_duty"] + "; " + floor,
                        row["ordinary_rule"],
                        row["hold_rule"],
                        row["erasure_restore_rule"],
                        row["owner"],
                    ),
                )
            )
            + " |"
        )
    lines += [
        "",
        "## Incident clocks",
        "",
        "| Trigger | Clock | Status | Recipient | Owner | Minimum action | Boundary |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in document["incident_clocks"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(row[k])
                for k in (
                    "trigger",
                    "clock",
                    "operative_status",
                    "recipient",
                    "owner",
                    "minimum_action",
                    "boundary",
                )
            )
            + " |"
        )
    lines += [
        "",
        "Run all potentially applicable clocks in parallel from the earliest "
        "known trigger. Do not wait for perfect classification before "
        "escalation or an available-information notice.",
        "",
        "## Accountability",
        "",
        "| Role | Answerable for | Cannot delegate | Required before |",
        "|---|---|---|---|",
    ]
    for row in document["accountability"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(row[k])
                for k in ("role", "answerable_for", "cannot_delegate", "required_before")
            )
            + " |"
        )
    lines += ["", "## Reservations counsel must resolve", ""]
    for row in document["review_reservations"]:
        lines.append(
            f"- **{row['id']} — {row['question']}** Owner: {row['owner']}. "
            f"Blocks: {_cell(row['blocks'])}. Evidence: {row['review_evidence']}"
        )
    lines += ["", "## Mandatory reassessment triggers", ""] + [
        f"- {x}" for x in document["reassessment_triggers"]
    ]
    signoff = document["counsel_signoff"]
    lines += [
        "",
        "## Counsel sign-off boundary",
        "",
        f"Current state: **{signoff['state']}**. The signed record belongs at "
        f"`{signoff['target']}`.",
        "",
        signoff["required_reviewer"],
        "",
        signoff["validity_rule"],
        "",
        signoff["signing_instruction"],
        "",
        "A typed name, role label, framework mapping, or this generated packet cannot confer PASS.",
        "",
        "## Later confidential-pilot and production approvals",
        "",
        "These are prepared inputs, not approvals. The applicability review "
        "comes first; exact scoped adoption follows.",
        "",
        "| Choice | State | Gates | Required approver | Required inputs |",
        "|---|---|---|---|---|",
    ]
    for row in document["approval_packets"]:
        lines.append(
            "| "
            + " | ".join(
                map(
                    _cell,
                    (
                        row["id"],
                        row["state"],
                        row["approval_required_for"],
                        row["approver"],
                        row["required_inputs"],
                    ),
                )
            )
            + " |"
        )
    lines += [
        "",
        "An approval must be a signed, expiring, exact-scope record in "
        "`approvals.json`; it cannot repair failed evidence or authorise a "
        "broader gate, processor, capability, data class or release.",
        "",
    ]
    return "\n".join(lines)


def evidence_template(document: dict) -> dict:
    signoff = document["counsel_signoff"]
    return {
        "template_status": "NOT_EVIDENCE_FILL_AND_SIGN_BEFORE_MOVING_TO_TARGET",
        "target": signoff["target"],
        "record": {
            "schema": 2,
            "criterion": "BK-85-AC3",
            "level": "counsel_review",
            "result": None,
            "subject": None,
            "method": {"procedure": "REVIEW-PRIVACY", "steps": []},
            "actor": {"person_id": None, "name": None},
            "authority": {
                "role": None,
                "basis": None,
                "evidence": {"ref": None, "sha256": None},
            },
            "rubric": {"identity": "REVIEW-PRIVACY", "findings": []},
            "population": {"count": None, "described": None},
            "reservations": None,
            "observed_at": None,
            "subject_identity": {
                "kind": "external", "valid_from": None, "valid_until": None,
            },
            "configuration_identity": None,
            "attestation": {"ref": None, "sha256": None},
        },
        "instructions": signoff["signing_instruction"] + " The attestation must "
                        "authenticate this exact record without the attestation field, "
                        "and the configured authority issuer must authenticate the "
                        "reviewer's evidence:counsel_review grant.",
    }


def write_views(document: dict) -> None:
    VIEW.write_text(render(document), encoding="utf-8", newline="\n")
    TEMPLATE.write_text(
        json.dumps(evidence_template(document), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "render"))
    args = parser.parse_args()
    from assurance.control_plane.blueprint import load_contracts

    document = load()
    contracts = load_contracts()
    errors = check(document, contracts["decisions"], contracts["approvals"])
    if args.command == "render" and not errors:
        write_views(document)
    for error in errors:
        print(f"FAIL: {error}")
    print(f"India applicability: {len(errors)} problems; counsel state {document.get('status')}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
