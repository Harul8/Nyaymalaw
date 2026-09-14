"""The India review is a bounded counsel packet, never agent-signed evidence.

BK-85-AC3 needs a qualified person's dated judgment.  These Class-A checks
prove that the packet asks that person the complete question, stays aligned to
the four later CHOICE proposals and fails when a dangerous proposition is
planted.  They deliberately do not convert the unsigned packet into PASS.
"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
import yaml

from assurance.control_plane import blueprint
from assurance.control_plane.india_applicability import (
    SOURCE,
    TEMPLATE,
    VIEW,
    check,
    evidence_template,
    load,
    render,
)

pytestmark = pytest.mark.class_a


def _inputs():
    document = load()
    contracts = blueprint.load_contracts()
    return document, contracts["decisions"], contracts["approvals"]


def _one(rows, identifier):
    found = [row for row in rows if row["id"] == identifier]
    assert len(found) == 1
    return found[0]


def test_the_complete_packet_is_machine_checked_by_the_main_control_plane():
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    assert check(contracts["applicability"], contracts["decisions"], contracts["approvals"]) == []
    assert blueprint.check_all(modules, registry, contracts) == []


def test_the_main_control_plane_requires_and_executes_the_applicability_contract():
    modules, registry = blueprint.load()
    missing = blueprint.load_contracts()
    assert missing.pop("applicability")
    assert blueprint.check_all(modules, registry, missing) == [
        "execution contracts: unknown or missing population"
    ]

    mutated = blueprint.load_contracts()
    _one(mutated["applicability"]["incident_clocks"], "CLOCK-CERT-IN")["clock"] = "within_72_hours"
    errors = blueprint.check_all(modules, registry, mutated)
    assert any("current six-hour clock" in error for error in errors), errors


def test_the_reader_view_and_unsigned_template_are_exact_derivatives():
    document, _, _ = _inputs()
    assert VIEW.read_text(encoding="utf-8") == render(document)
    assert json.loads(TEMPLATE.read_text(encoding="utf-8")) == evidence_template(document)
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert template["template_status"].startswith("NOT_EVIDENCE")
    assert template["record"]["result"] is None
    assert template["target"] == \
        "docs/backlog/evidence/BK-85-AC3-counsel_review.json"
    assert template["record"]["schema"] == 2
    assert set(template["record"]["actor"]) == {"person_id", "name"}
    assert set(template["record"]["authority"]) == {"role", "basis", "evidence"}
    assert set(template["record"]["attestation"]) == {"ref", "sha256"}
    assert template["record"]["configuration_identity"] is None


def test_nothing_in_the_packet_claims_counsel_or_adoption_authority():
    document, decisions, approvals = _inputs()
    assert document["status"] == "COUNSEL_REVIEW_REQUIRED"
    assert document["counsel_signoff"]["state"] == "not_recorded"
    assert approvals["records"] == []
    assert {row["id"] for row in document["approval_packets"]} == {
        "CHOICE-01",
        "CHOICE-07",
        "CHOICE-08",
        "CHOICE-10",
    }
    for packet in document["approval_packets"]:
        assert packet["state"] == "not_recorded"
        choice = _one(decisions["choices"], packet["id"])
        assert choice["approval"] is None
        assert "packet" not in choice["approval_required_for"]

    registry = yaml.safe_load(
        (SOURCE.parents[1] / "backlog" / "status.yaml").read_text(encoding="utf-8")
    )
    criterion = _one(
        [ac for item in registry["items"] for ac in item.get("acceptance") or []], "BK-85-AC3"
    )
    recorded = (criterion.get("evidence") or {}).get("counsel_review") or {}
    assert recorded.get("result") in (None, "", "NOT_RUN")


def test_current_and_notified_future_incident_clocks_stay_distinct():
    document, _, _ = _inputs()
    clocks = {row["id"]: row for row in document["incident_clocks"]}
    assert clocks["CLOCK-CERT-IN"]["clock"] == "within_6_hours"
    assert clocks["CLOCK-CERT-IN"]["operative_status"] == "operative_now"
    assert clocks["CLOCK-DPDP-PRINCIPAL"]["clock"] == "without_delay"
    assert clocks["CLOCK-DPDP-PRINCIPAL"]["operative_status"] == "future_from_2027-05-13"
    assert (
        clocks["CLOCK-DPDP-BOARD"]["clock"] == "without_delay_then_detailed_report_within_72_hours"
    )
    assert clocks["CLOCK-DPDP-BOARD"]["operative_status"] == "future_from_2027-05-13"


def _plant(document, probe):
    if probe == "blanket_processor":
        for row in document["role_by_purpose"]:
            row["nm_role"] = "data_processor"
    elif probe == "all_dpdp_operative":
        _one(document["legal_sources"], "IN-02")["operative_status"] = "operative_now"
    elif probe == "blanket_localisation":
        _one(document["legal_sources"], "IN-02")["claim_boundary"] = (
            "The law requires every byte to remain in India."
        )
    elif probe == "cert_clock_diluted":
        _one(document["incident_clocks"], "CLOCK-CERT-IN")["clock"] = "within_72_hours"
    elif probe == "future_dpdp_made_current":
        _one(document["incident_clocks"], "CLOCK-DPDP-BOARD")["operative_status"] = "operative_now"
    elif probe == "training_default_open":
        _one(document["permissions"], "PERMISSION-IMPROVEMENT")["product_rule"] = (
            "permitted_by_terms"
        )
    elif probe == "claim_exemption_blanket":
        _one(document["permissions"], "PERMISSION-CLAIM")["future_dpdp_position"] = (
            "all_legal_work_exempt"
        )
    elif probe == "log_floor_shortened":
        _one(document["retention"], "RETENTION-SECURITY-LOG")["current_minimum"] = "30_days"
    elif probe == "holds_erased":
        _one(document["retention"], "RETENTION-MATTER")["hold_rule"] = "none"
    elif probe == "reservations_emptied":
        document["review_reservations"].clear()
    elif probe == "authority_self_certified":
        document["counsel_signoff"]["authority_shape"] = "qualified counsel"
    elif probe == "choice_digest_stale":
        _one(document["approval_packets"], "CHOICE-01")["proposal_sha256"] = "0" * 64
    elif probe == "choice_marked_approved":
        _one(document["approval_packets"], "CHOICE-07")["state"] = "approved"
    elif probe == "approval_precedes_review":
        _one(document["approval_packets"], "CHOICE-08")["sequence"] = "before_review"
    elif probe == "nonofficial_legal_source":
        _one(document["legal_sources"], "IN-09")["official_url"] = (
            "https://example.invalid/legal-summary"
        )
    else:  # pragma: no cover - the parametrisation is the population
        raise AssertionError(f"unknown planted probe {probe}")


@pytest.mark.parametrize(
    "probe,expected",
    [
        ("blanket_processor", "blanket processor"),
        ("all_dpdp_operative", "phased DPDP commencement"),
        ("blanket_localisation", "blanket statutory localisation"),
        ("cert_clock_diluted", "six-hour clock"),
        ("future_dpdp_made_current", "future Board clock"),
        ("training_default_open", "prohibited by default"),
        ("claim_exemption_blanket", "stated as blanket"),
        ("log_floor_shortened", "current CERT-In log floor"),
        ("holds_erased", "ignores legal holds"),
        ("reservations_emptied", "reservations are absent"),
        ("authority_self_certified", "stated and evidenced"),
        ("choice_digest_stale", "stale against decisions.json"),
        ("choice_marked_approved", "register says 'not_recorded'"),
        ("approval_precedes_review", "not ordered after"),
        ("nonofficial_legal_source", "official Indian source"),
    ],
)
def test_fifteen_planted_legal_and_authority_failures_turn_the_gate_red(probe, expected):
    document, decisions, approvals = _inputs()
    mutated = deepcopy(document)
    _plant(mutated, probe)
    assert mutated != document, "the planted probe must change an existing field"
    errors = check(mutated, decisions, approvals)
    assert any(expected in error for error in errors), (probe, errors)
