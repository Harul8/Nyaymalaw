"""BK-31 — advocate-held recovery and unmistakable workspace context."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.adapters.store.directory import FileDirectory
from nm.domain.advocate import (
    AdvocateIdentity,
    Credential,
    Enrolment,
    enrol,
    new_recovery_codes,
    recovery_code_matches,
    utcnow,
)

pytestmark = pytest.mark.class_a

PASSWORD = "Password1!"
NEW_PASSWORD = "Different2!"


def test_domain_recovery_codes_are_typeable_unique_and_single_use():
    codes, records = new_recovery_codes()

    assert len(codes) == len(records) == 10
    assert len(set(codes)) == len(codes)
    assert all(re.fullmatch(r"[0-9A-F]{4}(?:-[0-9A-F]{4}){4}", code)
               for code in codes)
    assert all(recovery_code_matches(record, code.lower().replace("-", " "))
               for code, record in zip(codes, records, strict=True))
    assert not recovery_code_matches(records[0], codes[1])
    assert not recovery_code_matches(
        replace(records[0], used_at=utcnow().isoformat()), codes[0])


def _register(client, email="recovery@chambers.in"):
    token = client.invite(
        email,
        name="R Recovery",
        enrolment="TS/4321/2014",
        practice="Commercial litigation",
        firm_id="Harul Chambers",
    )
    response = client.post(
        "/api/register",
        headers={"x-enrolment-invitation": token},
        json={"password": PASSWORD, "password_again": PASSWORD},
    )
    assert response.status_code == 200, response.text
    codes = response.json().get("recovery_codes")
    assert len(codes or []) >= 8
    assert len(set(codes)) == len(codes)
    return email, codes


def _recover(client, advocate_id, code, password=NEW_PASSWORD):
    return client.post("/api/recover", json={
        "advocate_id": advocate_id,
        "recovery_code": code,
        "password": password,
        "password_again": password,
    })


def test_registration_returns_recovery_codes_once_and_stores_only_salted_hashes(client):
    advocate_id, codes = _register(client)
    record = json.loads(
        (client.directory._advocates / f"{advocate_id}.nm").read_text(encoding="utf8"))
    stored = record["recovery_codes"]

    assert len(stored) == len(codes)
    assert all({"id", "salt", "hash", "used_at"} == set(item) for item in stored)
    assert len({item["salt"] for item in stored}) == len(stored)
    raw = json.dumps(record)
    assert all(code not in raw for code in codes)

    signed_in = client.sign_in(advocate_id, password=PASSWORD, fresh=True)
    assert "recovery_codes" not in signed_in.get("/api/session").json()


def test_a_legacy_advocate_receives_one_code_set_after_the_next_valid_sign_in(client):
    legacy = "legacy@chambers.in"
    client.sign_in(legacy, password=PASSWORD, fresh=True)
    path = client.directory._advocates / f"{legacy}.nm"
    record = json.loads(path.read_text(encoding="utf8"))
    record.pop("recovery_codes")
    path.write_text(json.dumps(record, indent=2), encoding="utf8")

    first = TestClient(client.app)
    response = first.post("/api/login", json={
        "advocate_id": legacy, "password": PASSWORD,
    })
    assert response.status_code == 200
    assert len(response.json().get("recovery_codes") or []) >= 8

    second = TestClient(client.app)
    response = second.post("/api/login", json={
        "advocate_id": legacy, "password": PASSWORD,
    })
    assert response.status_code == 200
    assert "recovery_codes" not in response.json()


def test_successful_recovery_changes_password_consumes_code_and_revokes_sessions(client):
    advocate_id, codes = _register(client)
    first = client.sign_in(advocate_id, password=PASSWORD, fresh=True)
    second = client.sign_in(advocate_id, password=PASSWORD, fresh=True)
    public = TestClient(client.app)

    typed_code = codes[0].lower().replace("-", " ")
    recovered = _recover(public, advocate_id, typed_code)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == {"recovered": True, "sessions_ended": 2}

    assert first.get("/api/session").status_code == 401
    assert second.get("/api/session").status_code == 401
    assert TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    }).status_code == 401
    assert TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": NEW_PASSWORD,
    }).status_code == 200
    record = json.loads(
        (client.directory._advocates / f"{advocate_id}.nm").read_text(encoding="utf8"))
    assert sum(item["used_at"] is not None for item in record["recovery_codes"]) == 1


def test_unknown_wrong_and_used_recovery_codes_have_one_response_and_no_secret_in_audit(client):
    advocate_id, codes = _register(client)
    public = TestClient(client.app)
    wrong = _recover(public, advocate_id, "wrong-code")
    unknown = _recover(public, "nobody@chambers.in", "wrong-code")
    good = _recover(public, advocate_id, codes[0])
    used = _recover(public, advocate_id, codes[0], "Another3!")

    assert good.status_code == 200
    assert {wrong.status_code, unknown.status_code, used.status_code} == {403}
    assert wrong.json() == unknown.json() == used.json()
    audit = client.directory._audit.read_text(encoding="utf8")
    attempts = client.directory._attempts.read_text(encoding="utf8")
    assert codes[0] not in audit + attempts
    assert "wrong-code" not in audit + attempts


def test_two_directory_instances_cannot_consume_the_same_recovery_code(tmp_path):
    directory = FileDirectory(tmp_path, key="test-key")
    from nm.domain.advocate import AdvocateIdentity, Enrolment

    codes = directory.enrol(Enrolment(
        identity=AdvocateIdentity(
            id="race@chambers.in", email="race@chambers.in", name="Race",
            enrolment="TS/99/2010", practice="Civil", firm_id="Race Chambers"),
        credential=enrol(PASSWORD),
    ))
    other = FileDirectory(tmp_path, key="test-key")

    def use(instance):
        return instance.recover(
            "race@chambers.in", codes[0], enrol(NEW_PASSWORD), utcnow())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(use, (directory, other)))
    assert sorted(result.success for result in results) == [False, True]
    assert sum(result.sessions_ended for result in results) == 0


def test_sign_in_cannot_cross_a_recovery_account_claim(client):
    advocate_id, _codes = _register(client, "claim@chambers.in")
    claim = client.directory._claim_recovery(advocate_id)
    assert claim is not None
    try:
        refused = TestClient(client.app).post("/api/login", json={
            "advocate_id": advocate_id, "password": PASSWORD,
        })
        assert refused.status_code == 503
        assert refused.json()["detail"] == (
            "Account access is changing. Try sign-in again in a moment.")
    finally:
        claim.release()

    assert TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    }).status_code == 200

    # The worker exits without calling release. An OS claim must disappear
    # with its file handle; a create/delete sentinel would strand the account.
    crashed = """
import os
import sys
from nm.adapters.store.directory import FileDirectory
claim = FileDirectory(sys.argv[1], key='test-key')._claim_recovery(sys.argv[2])
assert claim is not None
os._exit(0)
"""
    subprocess.run(
        [sys.executable, "-c", crashed, str(client.directory._root), advocate_id],
        check=True,
    )
    after_crash = FileDirectory(
        client.directory._root, key="test-key")._claim_recovery(advocate_id)
    assert after_crash is not None
    after_crash.release()


def test_login_and_session_name_one_server_owned_active_workspace(client):
    advocate_id, _codes = _register(client, "workspace@chambers.in")
    login = TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    })
    assert login.status_code == 200
    workspace = login.json()["workspace"]
    assert workspace == {
        "id": "Harul Chambers",
        "label": "Harul Chambers",
        "scope": "the matters held for this advocate",
    }

    current = TestClient(client.app)
    current.post("/api/login", json={"advocate_id": advocate_id, "password": PASSWORD})
    assert current.get("/api/session").json()["workspace"] == workspace


def test_a_legacy_advocate_without_a_firm_gets_a_truthful_private_workspace(client):
    client.directory.enrol(Enrolment(
        identity=AdvocateIdentity(
            id="private@chambers.in", name="R Kumar", email="private@chambers.in"),
        credential=enrol(PASSWORD),
    ))
    legacy = TestClient(client.app)
    assert legacy.post("/api/login", json={
        "advocate_id": "private@chambers.in", "password": PASSWORD,
    }).status_code == 200
    workspace = legacy.get("/api/session").json()["workspace"]
    assert workspace == {
        "id": "advocate:private@chambers.in",
        "label": "R Kumar's private workspace",
        "scope": "the matters held for this advocate",
    }


def test_active_workspace_reaches_the_masthead_before_matter_rendering(client):
    advocate_id, _codes = _register(client, "visible-workspace@chambers.in")
    login = TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    })
    assert login.json()["workspace"]["label"] == "Harul Chambers"

    root = Path(__file__).resolve().parents[1]
    page = (root / "web" / "index.html").read_text(encoding="utf8")
    script = (root / "web" / "app.js").read_text(encoding="utf8")
    show = script.index("function showApplication(advocate, workspace)")
    workspace = script.index("$('workspace-name').textContent", show)
    matters = script.index("showMatterList();", show)
    assert show < workspace < matters
    assert 'id="workspace-context" aria-label="Active workspace"' in page
    assert not re.search(r'<select\b[^>]*(?:workspace|firm)', page, re.I)


def test_recovery_requires_matching_valid_new_password_before_it_can_consume_a_code(client):
    advocate_id, codes = _register(client)
    public = TestClient(client.app)
    mismatch = public.post("/api/recover", json={
        "advocate_id": advocate_id, "recovery_code": codes[0],
        "password": NEW_PASSWORD, "password_again": "Mismatch3!",
    })
    weak = _recover(public, advocate_id, codes[0], "weak")
    good = _recover(public, advocate_id, codes[0])
    assert mismatch.status_code == 400
    assert weak.status_code == 400
    assert good.status_code == 200


def test_failed_recovery_attempts_reach_the_shared_rate_limit(client):
    advocate_id, _codes = _register(client)
    public = TestClient(client.app)
    for _ in range(5):
        assert _recover(public, advocate_id, "wrong-code").status_code == 403
    paused = _recover(public, advocate_id, "wrong-code")
    assert paused.status_code == 429
    assert "Too many failed recovery attempts" in paused.json()["detail"]


def test_recovery_record_carries_credential_shape_not_a_password(client):
    advocate_id, codes = _register(client)
    result = client.directory.recover(
        advocate_id, codes[0], enrol(NEW_PASSWORD), utcnow())
    assert result.success is True
    record = json.loads(
        (client.directory._advocates / f"{advocate_id}.nm").read_text(encoding="utf8"))
    assert set(record["credential"]) == set(Credential.__dataclass_fields__)
    assert PASSWORD not in json.dumps(record)
    assert NEW_PASSWORD not in json.dumps(record)
