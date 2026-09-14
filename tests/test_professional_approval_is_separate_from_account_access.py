"""Real privileged exceptions, not ordinary private files, need professional review."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from nm.domain.advocate import utcnow
from nm.domain.professional_access import ProfessionalApproval, professional_status

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
    from nm.adapters.store.directory import FileDirectory

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


def test_unapproved_account_keeps_ordinary_file_access_but_cannot_declare_exception(client):
    from nm.edge.api import application

    def open_ordinary_file(turn_id):
        response = client.post("/api/turn", json={
            "turn_id": turn_id,
            "message": "we act for the plaintiff. the goods were never paid for.",
            "today": "2026-08-31"})
        assert response.status_code == 200, response.text
        released = response.json()
        assert released["committed"] == "committed" and released["input_admitted"] is True
        saved = application().store.load(released["matter_id"])
        assert saved is not None and saved.advocate_id == "adv_demo"
        assert any(receipt.turn_id == turn_id for receipt in saved.turn_receipts)
        return saved.id

    assert client.directory.professional_approval("adv_demo") is None
    matter_id = open_ordinary_file("unapproved-first-ordinary-file")
    before = application().store.load(matter_id)
    assert client.get(f"/api/matters/{matter_id}").status_code == 200
    for suffix in ("cover", "casefile", "emergency"):
        assert client.get(f"/api/matters/{matter_id}/{suffix}").status_code == 200
    refused = client.post(f"/api/matters/{matter_id}/emergency", json={
        "request_key": "unapproved", "basis": "A supplied urgent risk", "hours": 1,
        "professional_approval": {"state": "approved"}})
    assert refused.status_code == 403 and "professional approval" in refused.text
    assert application().store.load(matter_id) == before
    assert client.get("/api/session").status_code == 200
    second = open_ordinary_file("unapproved-second-ordinary-file")
    assert second != matter_id
    # Identify each creation by its receipt, not list position: equally recent
    # files may legitimately sort either way without becoming the same file.
    listed_ids = {row["matter_id"] for row in client.get("/api/matters").json()["matters"]}
    assert {matter_id, second} <= listed_ids
    assert client.get(f"/api/matters/{second}").status_code == 200


def test_current_approval_does_not_grant_matter_authority(client):
    from nm.edge.api import application

    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    approve_fixture_account(client.directory)
    matter_id = _matter(client)
    refused = client.post(f"/api/matters/{matter_id}/concede", json={
        "acting_as": "deciding", "on": "the disputed point"})
    assert refused.status_code == 403
    assert not application().store.load(matter_id).decisions
    outsider = client.sign_in("unrelated-actor", fresh=True)
    approve_fixture_account(client.directory, "unrelated-actor")
    assert outsider.get(f"/api/matters/{matter_id}/cover").status_code == 404
    assert outsider.post(f"/api/matters/{matter_id}/emergency", json={
        "request_key": "other-file", "basis": "stated danger"}).status_code == 404


def test_revoked_approval_refuses_core_handoff_replay_but_not_safety_revocation(client):
    from nm.core.turn import TurnInput, TurnRefused
    from nm.edge.api import application

    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    approval = approve_fixture_account(client.directory)
    matter_id = _matter(client)
    path = f"/api/matters/{matter_id}/emergency"
    declared = client.post(path, json={"request_key": "approved", "basis": "stated risk"})
    assert declared.status_code == 200, declared.text
    engine = application().engine
    turn = TurnInput(advocate_id="adv_demo", matter_id=matter_id,
                     turn_id="protected-replay", message="must not become a fact",
                     work_product="protective_triage")
    assert engine.run(turn).answer.blocked is False
    saved = application().store.load(matter_id)
    at = utcnow()
    client.directory.record_professional_approval(
        approval.revoke("synthetic-operator", "review withdrawn", at), expected_version=1, now=at)
    with pytest.raises(TurnRefused, match="no longer live"):
        engine.run(turn)
    assert application().store.load(matter_id) == saved
    read = client.get(path).json()
    assert read["permits_protective_handoff"] is False
    assert "no screen exception" in read["said"]
    revoked = client.post(path, json={"revoke": True,
                                     "governing_ref": read["governing_ref"],
                                     "expected_version": read["version"]})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["state"] == "emergency_revoked"
    assert client.get(f"/api/matters/{matter_id}/cover").status_code == 200


def test_unavailable_profile_reader_refuses_exception_without_blocking_ordinary_turn(
        client, monkeypatch):
    from nm.edge.api import application

    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    read_attempts = []

    def unavailable(account):
        read_attempts.append(account)
        raise OSError("synthetic approval store failure")

    monkeypatch.setattr(application().engine, "_professional_approval", unavailable)
    matter_id = _matter(client)
    assert read_attempts == [], \
        "ordinary served intake/advice must not consult professional approval"
    assert application().store.load(matter_id).turn_receipts[-1].input_admitted is True
    denied = client.post(f"/api/matters/{matter_id}/emergency", json={
        "request_key": "unavailable", "basis": "stated risk"})
    assert denied.status_code == 403
    assert read_attempts == ["adv_demo"]
    assert client.get(f"/api/matters/{matter_id}/cover").status_code == 200


def test_runtime_failure_of_the_professional_port_cannot_break_login_or_session(
        client, monkeypatch):
    from nm.edge.api import application

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


@pytest.mark.parametrize("change", ["missing", "malformed", "expired", "future"])
def test_live_exception_is_rechecked_against_the_actual_approval_owner(client, monkeypatch, change):
    from nm.core.turn import TurnInput
    from nm.edge.api import application

    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    approval = approve_fixture_account(client.directory, valid_for=timedelta(minutes=30))
    matter_id = _matter(client)
    path = f"/api/matters/{matter_id}/emergency"
    assert client.post(path, json={"request_key": "original", "basis": "stated risk"}) \
        .status_code == 200
    engine = application().engine
    assert engine.professional_access("adv_demo")["state"] == "approved"
    if change in ("missing", "malformed", "future"):
        account = client.directory._read("adv_demo")
        assert isinstance(account["professional_approval"], str)
        if change == "missing":
            del account["professional_approval"]
        elif change == "malformed":
            account["professional_approval"] = {"state": "approved", "schema": 1}
        else:
            records = client.directory._professional_records(account, "adv_demo")
            records[-1]["approved_at"] = (approval.approved_at + timedelta(minutes=1)).isoformat()
            envelope = {"schema": 1, "records": records}
            account["professional_approval"] = client.directory._cipher.encrypt(
                json.dumps(envelope).encode("utf8")).decode("ascii")
        client.directory._replace_advocate(client.directory._advocate_path("adv_demo"), account)
    else:
        instant = approval.valid_until
        monkeypatch.setattr(engine, "_clock", lambda: instant)
    assert engine.professional_access("adv_demo")["state"] == "unapproved"
    original = application().store.load(matter_id)
    from nm.domain.emergency import latest

    assert latest(original.emergencies, engine._clock()) is not None, \
        "the declaration itself must remain live to isolate the professional-approval guard"
    denied = engine.run(TurnInput(
        advocate_id="adv_demo", matter_id=matter_id, turn_id=f"denied-{change}",
        message="unadmitted secret", work_product="protective_triage"))
    assert denied.answer.blocked is True
    saved = application().store.load(matter_id)
    assert saved.facts == original.facts and saved.screens == original.screens
    assert saved.emergency_triage[-1]["permitted"] is False
    assert "unadmitted secret" not in str(saved.emergency_triage)
    assert client.post(path, json={"request_key": "new", "basis": "stated risk"}).status_code == 403
    assert client.get("/api/session").status_code == 200
    assert client.get(f"/api/matters/{matter_id}/cover").status_code == 200


def test_operator_cli_hashes_the_real_review_artifact_without_exposing_it(
        client, tmp_path, monkeypatch, capsys):
    from nm.edge.api import application

    from backend.operations.professional_approval import main

    artifact = tmp_path / "synthetic-review.txt"
    artifact.write_bytes(b"Synthetic operator-reviewed artifact; not an actual qualification")
    monkeypatch.setattr("nm.bootstrap.composition.Application", lambda: application())
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
