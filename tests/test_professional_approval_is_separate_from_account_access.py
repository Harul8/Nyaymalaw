"""Real privileged exceptions, not ordinary private files, need professional review."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from nm.arrive.advocate_contracts import utcnow
from nm.arrive.professional_access_contracts import ProfessionalApproval, professional_status

pytestmark = pytest.mark.class_a


def approve_fixture_account(directory, account_id="adv_demo", *, now=None,
                            valid_for=timedelta(days=7)):
    """Explicit synthetic operator review for a protected-operation test ONLY.

    Never installed on the shared client: ordinary accounts remain unapproved.
    The digest is of identified test bytes, not invented qualification evidence.
    """
    at = now or utcnow()
    current = ProfessionalApproval.from_record(directory.professional_approval(account_id))
    version = current.version if current else 0
    approval = ProfessionalApproval(
        account_id=account_id, reviewer_id="synthetic-independent-operator",
        basis="Synthetic review for isolated protected-operation test only",
        evidence_ref="fixture:synthetic-professional-review-not-a-real-qualification",
        evidence_sha256=hashlib.sha256(b"synthetic review artifact; test only").hexdigest(),
        approved_at=at, valid_until=at + valid_for, version=version + 1)
    directory.record_professional_approval(approval, expected_version=version, now=at)
    return approval


def test_professional_approval_is_durable_attributed_and_compare_and_set(client, tmp_path):
    from nm.arrive.store_directory import FileDirectory
    from tests.test_turn_contract import KEY

    before = client.directory._read("adv_demo")
    assert client.directory.professional_approval("adv_demo") is None
    at = utcnow()
    approval = approve_fixture_account(client.directory, now=at)
    fresh = FileDirectory(tmp_path, key=KEY)
    assert fresh.professional_approval("adv_demo") == approval.as_dict()
    after = fresh._read("adv_demo")
    assert {k: v for k, v in after.items() if k != "professional_approval"} == before
    raw = (tmp_path / "advocates" / "adv_demo.nm").read_text(encoding="utf8")
    assert approval.evidence_ref not in raw and approval.basis not in raw
    assert isinstance(json.loads(raw)["professional_approval"], str)
    with pytest.raises(ValueError, match="moved"):
        fresh.record_professional_approval(approval, expected_version=0, now=at)
    assert fresh.professional_approval("adv_demo") == approval.as_dict()
    with pytest.raises(ValueError, match="different operator"):
        replace(approval, reviewer_id="ADV_DEMO")
    revoked = approval.revoke("synthetic-operator", "review withdrawn", at)
    fresh.record_professional_approval(revoked, expected_version=1, now=at)
    assert fresh.professional_approval("adv_demo") == revoked.as_dict()
    assert professional_status(revoked.as_dict(), "adv_demo", at)["state"] == "unapproved"
    assert len(fresh._professional_records(fresh._read("adv_demo"), "adv_demo")) == 2


@pytest.mark.parametrize("mutation", [
    "absent", "false", "string", "schema_boolean", "unknown_field", "self_review",
    "no_digest", "no_expiry", "naive_review", "wrong_subject", "future", "expired", "revoked",
])
def test_untrusted_approval_records_fail_closed(client, mutation):
    at = utcnow()
    approval = approve_fixture_account(client.directory, now=at)
    record = approval.as_dict()
    if mutation == "absent":
        record = None
    elif mutation == "false":
        record = False
    elif mutation == "string":
        record = "approved"
    elif mutation == "schema_boolean":
        record["schema"] = True
    elif mutation == "unknown_field":
        record["override"] = True
    elif mutation == "self_review":
        record["reviewer_id"] = "ADV_DEMO"
    elif mutation == "no_digest":
        record["evidence_sha256"] = ""
    elif mutation == "no_expiry":
        record["valid_until"] = None
    elif mutation == "naive_review":
        record["approved_at"] = at.replace(tzinfo=None).isoformat()
    elif mutation == "wrong_subject":
        record["account_id"] = "someone-else"
    elif mutation == "future":
        record["approved_at"] = (at + timedelta(hours=1)).isoformat()
    elif mutation == "expired":
        record["approved_at"] = (at - timedelta(hours=2)).isoformat()
        record["valid_until"] = at.isoformat()
    elif mutation == "revoked":
        record = approval.revoke("synthetic-operator", "withdrawn", at).as_dict()
    assert json.dumps(record, sort_keys=True) != json.dumps(approval.as_dict(), sort_keys=True)
    assert professional_status(approval.as_dict(), "adv_demo", at)["state"] == "approved"
    assert professional_status(record, "adv_demo", at)["state"] == "unapproved"


def test_runtime_failure_of_the_professional_port_cannot_break_login_or_session(
        client, monkeypatch):
    from nm.app.api import application

    attempted = []

    def unavailable(account):
        attempted.append(account)
        raise RuntimeError("synthetic dispatch unavailable; do not expose this detail")

    # Inject the actual composed port, not a replacement HTTP handler or status
    # projection. Authentication itself remains the real password/session path.
    monkeypatch.setattr(application().directory, "professional_approval", unavailable)
    client.cookies.clear()
    signed = client.post("/api/login", json={
        "advocate_id": "adv_demo", "password": "Fixture-password-not-a-secret-1"})
    assert signed.status_code == 200, signed.text
    assert signed.json()["professional_approval"]["state"] == "unapproved"
    session = client.get("/api/session")
    assert session.status_code == 200, session.text
    assert session.json()["advocate"]["id"] == "adv_demo"
    assert session.json()["professional_approval"]["state"] == "unapproved"
    assert attempted == ["adv_demo", "adv_demo"]
    assert "synthetic dispatch" not in signed.text + session.text


def test_operator_cli_hashes_the_real_review_artifact_without_exposing_it(
        client, tmp_path, monkeypatch, capsys):
    from nm.app.api import application
    from operations.professional_approval import main

    artifact = tmp_path / "synthetic-review.txt"
    artifact.write_bytes(b"Synthetic operator-reviewed artifact; not an actual qualification")
    monkeypatch.setattr("nm.app.composition.Application", lambda: application())
    expiry = utcnow() + timedelta(days=2)
    assert main(["approve", "--account", "adv_demo", "--operator", "synthetic-reviewer",
                 "--basis", "Synthetic reviewed evidence", "--expected-version", "0",
                 "--evidence", str(artifact), "--valid-until", expiry.isoformat()]) == 0
    record = client.directory.professional_approval("adv_demo")
    printed = capsys.readouterr().out
    assert "approved" in printed and record["basis"] not in printed
    assert str(artifact) not in printed and "synthetic-reviewer" not in printed
    assert record["evidence_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert record["evidence_ref"] == str(artifact.resolve())
    assert main(["revoke", "--account", "adv_demo", "--operator", "synthetic-reviewer",
                 "--basis", "Synthetic withdrawal", "--expected-version", "1"]) == 0
    assert client.directory.professional_approval("adv_demo")["version"] == 2
