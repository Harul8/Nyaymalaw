"""Public accounts are private account access, never professional approval.

These use actual directory persistence and the served routes. Email validation
is syntactic: there is deliberately no fake delivery or mailbox verification.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from nm.adapters.store.directory import FileDirectory
from nm.domain import attempts
from nm.domain.advocate import (
    AdvocateIdentity,
    Enrolment,
    enrol,
    registration_email,
    utcnow,
)
from nm.ports.directory import AlreadyEnrolled, RegistrationUnavailable
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
PASSWORD = "Cinder-lantern-42"
OTHER_PASSWORD = "Another-lantern-73"
EMAIL = "reader+private@example.com"


def _register(client, email=EMAIL, **extra):
    return client.post("/api/register", json={
        "email": email, "password": PASSWORD, "password_again": PASSWORD, **extra})


def _login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/login", json={"advocate_id": email, "password": password})


def test_email_and_password_create_a_private_account_without_an_invitation(client):
    client.cookies.clear()
    result = _register(client, " Reader+Private@Example.com ")
    assert result.status_code == 200, result.text
    assert result.json()["advocate_id"] == EMAIL
    assert result.json()["name"] == EMAIL
    codes = result.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    assert not result.headers.get("set-cookie"), "registration minted credentials"
    assert client.get("/api/session").status_code == 401
    identity = client.directory.identity(EMAIL)
    assert identity == AdvocateIdentity(id=EMAIL, name=EMAIL, email=EMAIL)
    signed = _login(client, "READER+PRIVATE@EXAMPLE.COM")
    assert signed.status_code == 200, signed.text
    assert signed.json()["workspace"]["id"] == f"advocate:{EMAIL}"
    assert signed.json()["professional_approval"]["state"] == "unapproved"
    assert "recovery_codes" not in signed.json(), "initial codes were disclosed twice"
    stored = client.directory._advocate_path(EMAIL).read_text(encoding="utf8")
    assert PASSWORD not in stored
    assert all(code not in stored for code in codes)


@pytest.mark.parametrize("field", [
    "name", "firm_id", "enrolment", "practice", "role", "roles", "verified",
    "approved", "professional_approval", "advocate_id", "email_verified",
])
def test_public_registration_cannot_supply_profile_or_authority_fields(client, field):
    refused = _register(client, **{field: "caller-controlled"})
    assert refused.status_code == 422, refused.text
    assert client.directory.identity(EMAIL) is None
    assert not client.directory._registration_attempts.exists()


def test_a_new_account_can_sign_in_create_and_reopen_only_its_own_matter(client):
    # No operator provisioning or professional-approval fixture participates.
    client.cookies.clear()
    assert _register(client).status_code == 200
    assert _login(client).status_code == 200
    opened = client.post("/api/matters/intake", json={
        "request_key": "private-first-file", "title": "My first supplied file",
        "parties": {"Supplied client": "client"},
    })
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]
    assert opened.json()["facts_established"] is False
    assert client.get(f"/api/matters/{matter_id}").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get(f"/api/matters/{matter_id}").status_code == 401
    assert _login(client).status_code == 200
    assert client.get(f"/api/matters/{matter_id}").status_code == 200
    assert client.get("/api/session").json()["professional_approval"]["state"] == "unapproved"
    assert client.post("/api/logout").status_code == 200
    stranger = "different+private@example.com"
    assert _register(client, stranger).status_code == 200
    signed = _login(client, stranger)
    assert signed.status_code == 200, signed.text
    assert signed.json()["workspace"]["id"] != f"advocate:{EMAIL}"
    assert client.get(f"/api/matters/{matter_id}").status_code == 404
    assert matter_id not in client.get("/api/matters").text
    assert "My first supplied file" not in client.get("/api/matters").text


def test_public_login_refusals_do_not_disclose_account_state(client):
    assert _register(client).status_code == 200
    sealed_id = "unreadable@example.com"
    client.directory._advocate_path(sealed_id).write_bytes(b"not-readable-account")
    client.cookies.clear()
    responses = [_login(client, account, "Wrong-password-1") for account in (
        EMAIL, "not-enrolled@example.com", sealed_id, "../account-escape",
    )]
    assert [response.status_code for response in responses] == [401] * 4
    answers = [response.json() for response in responses]
    assert len(answers) == 4 and all(row == answers[0] for row in answers)
    assert "not accepted" in answers[0]["detail"]
    assert client.get("/api/session").status_code == 401
    assert _login(client).status_code == 200, "neutral failures broke valid authentication"


def test_the_longest_public_email_roundtrips_through_its_real_account_store(client):
    longest = "a" * 64 + "@" + ".".join(["b" * 63, "c" * 63, "d" * 61])
    assert len(longest) == 254
    assert registration_email(longest) == longest
    created = _register(client, longest)
    assert created.status_code == 200, created.text
    path = client.directory._advocate_path(longest)
    assert path.parent == client.directory._advocates_by_digest
    assert len(path.name) <= 255
    restarted = FileDirectory(client.directory._root, key=KEY)
    assert restarted.authenticate(longest.upper(), PASSWORD).id == longest
    assert _login(client, longest).status_code == 200
    recovered = client.post("/api/recover", json={
        "advocate_id": longest.upper(), "recovery_code": created.json()["recovery_codes"][0],
        "password": OTHER_PASSWORD, "password_again": OTHER_PASSWORD,
    })
    assert recovered.status_code == 200, recovered.text
    assert _login(client, longest, OTHER_PASSWORD).status_code == 200
    assert _register(client, longest.upper()).status_code == 409
    before = path.read_bytes()
    assert _register(client, longest + "e").status_code == 422
    assert path.read_bytes() == before
    assert client.directory._advocate_path(EMAIL) == client.directory._advocates / f"{EMAIL}.nm"


@pytest.mark.parametrize("damage", [
    "nonobject", "missing_identity", "identity_mismatch", "identity_extra",
    "credential_missing", "credential_extra", "credential_bad_hash",
])
def test_malformed_account_records_have_the_same_neutral_login_refusal(client, damage):
    assert _register(client).status_code == 200
    path = client.directory._advocate_path(EMAIL)
    original = path.read_bytes()
    record = json.loads(original)
    if damage == "nonobject":
        record = []
    elif damage == "missing_identity":
        del record["identity"]
    elif damage == "identity_mismatch":
        record["identity"]["id"] = "someone-else@example.com"
    elif damage == "identity_extra":
        record["identity"]["verified"] = True
    elif damage == "credential_missing":
        del record["credential"]
    elif damage == "credential_extra":
        record["credential"]["verified"] = True
    else:
        record["credential"]["salt"] = "not-hex"
    path.write_text(json.dumps(record), encoding="utf8")
    client.cookies.clear()
    refused = _login(client)
    unknown = _login(client, "absent@example.com")
    assert refused.status_code == unknown.status_code == 401
    assert refused.json() == unknown.json()
    assert client.get("/api/session").status_code == 401
    path.write_bytes(original)
    assert _login(client).status_code == 200


def test_duplicate_public_registration_never_replaces_credentials(client):
    first = _register(client)
    assert first.status_code == 200
    path = client.directory._advocate_path(EMAIL)
    original = path.read_bytes()
    duplicate = _register(client, EMAIL.upper(), password=OTHER_PASSWORD,
                          password_again=OTHER_PASSWORD)
    assert duplicate.status_code == 409, duplicate.text
    assert EMAIL not in duplicate.text.lower()
    assert "already" not in duplicate.text.lower()
    assert "recovery" in duplicate.text.lower()
    assert "recovery_codes" not in duplicate.json()
    assert path.read_bytes() == original
    assert _login(client, password=OTHER_PASSWORD).status_code == 401
    assert _login(client).status_code == 200
    # The initially delivered recovery set still works after the refused retry.
    recovery = client.post("/api/recover", json={
        "advocate_id": EMAIL, "recovery_code": first.json()["recovery_codes"][0],
        "password": OTHER_PASSWORD, "password_again": OTHER_PASSWORD,
    })
    assert recovery.status_code == 200, recovery.text
    assert _login(client, password=OTHER_PASSWORD).status_code == 200


@pytest.mark.parametrize("email", [
    None, "", "  ", "not-an-email", "a@@example.com", "a@example", "a@.com",
    ".a@example.com", "a..b@example.com", "a.@example.com", "a@-example.com",
    "a@example-.com", "a@exam_ple.com", "a@example.com.", "a b@example.com",
    "../a@example.com", "a/b@example.com", "a\\b@example.com", "a*tag@example.com",
    "a\n@example.com", "a@example.com\r\n", "a\x00@example.com", "अ@example.com",
    "a@exämple.com", "a" * 65 + "@example.com", "a@" + "x" * 64 + ".com",
    "a" * 64 + "@" + ".".join(["b" * 63] * 3), " " * 321 + "a@example.com",
])
def test_public_email_refuses_unsupported_or_aliasing_handles(email):
    with pytest.raises(ValueError, match="email"):
        registration_email(email)


@pytest.mark.parametrize(("offered", "expected"), [
    (" Advocate+File@Example.COM ", "advocate+file@example.com"),
    ("a.b@example.com", "a.b@example.com"),
    ("ab@example.com", "ab@example.com"),
    ("a+one@example.com", "a+one@example.com"),
    ("a+two@example.com", "a+two@example.com"),
    ("a" * 64 + "@example.com", "a" * 64 + "@example.com"),
    ("a@" + "b" * 63 + ".com", "a@" + "b" * 63 + ".com"),
])
def test_public_email_preserves_distinct_usable_mailboxes(offered, expected):
    assert registration_email(offered) == expected


def test_public_registration_admission_counts_successes_and_survives_restart(
        client, monkeypatch):
    from nm.edge import api

    now = utcnow()
    monkeypatch.setattr(api, "utcnow", lambda: now)
    for number in range(attempts.PER_SOURCE):
        created = _register(client, f"created-{number}@example.com")
        assert created.status_code == 200, created.text
    doc = json.loads(client.directory._registration_attempts.read_text(encoding="utf8"))
    assert len(doc["attempts"]) == attempts.PER_SOURCE
    restarted = FileDirectory(client.directory._root, key=KEY)
    monkeypatch.setattr(api.application(), "directory", restarted)
    before = restarted._registration_attempts.read_bytes()
    refused = _register(client, "one-too-many@example.com")
    assert refused.status_code == 429, refused.text
    assert int(refused.headers["retry-after"]) > 0
    assert restarted.identity("one-too-many@example.com") is None
    assert restarted._registration_attempts.read_bytes() == before
    monkeypatch.setattr(api, "utcnow", lambda: now + attempts.WINDOW)
    assert _register(client, "after-window@example.com").status_code == 200
    retained = json.loads(restarted._registration_attempts.read_text(encoding="utf8"))
    assert len(retained["attempts"]) == 1, "expired populations were not pruned"


def test_public_registration_limits_repeated_account_attempts_across_sources(tmp_path):
    directory = FileDirectory(tmp_path, key=KEY)
    now = utcnow()
    for number in range(attempts.PER_ADVOCATE):
        assert directory.admit_registration(EMAIL, f"source-{number}", now).allowed
    restarted = FileDirectory(tmp_path, key=KEY)
    refused = restarted.admit_registration(EMAIL, "another-source", now)
    assert not refused.allowed and refused.retry_after.total_seconds() > 0
    assert restarted.admit_registration("another@example.com", "another-source", now).allowed


@pytest.mark.parametrize("damage", [
    b"not-json", b"null", b"[]", b'{"schema":true,"attempts":[]}',
    b'{"schema":1,"attempts":[null]}', b'{"schema":1,"attempts":[],"extra":true}',
    b'{"schema":1,"attempts":[{"at":"bad","email":"bad","source":"bad"}]}',
])
def test_public_registration_refuses_unreadable_admission(client, damage):
    client.directory._registration_attempts.write_bytes(damage)
    refused = _register(client)
    assert refused.status_code == 503, refused.text
    assert "try again later" in refused.text.lower()
    assert EMAIL not in refused.text
    assert client.directory.identity(EMAIL) is None
    assert client.directory._registration_attempts.read_bytes() == damage


def test_public_registration_refuses_failed_durable_admission_before_hashing(
        client, monkeypatch):
    import nm.domain.advocate as advocate

    def cannot_write(path, blob):
        raise OSError("synthetic admission storage failure")

    def must_not_hash(password):
        raise AssertionError("unadmitted request reached expensive password derivation")

    monkeypatch.setattr(client.directory, "_replace_advocate", cannot_write)
    monkeypatch.setattr(advocate, "enrol", must_not_hash)
    refused = _register(client)
    assert refused.status_code == 503, refused.text
    assert client.directory.identity(EMAIL) is None
    assert "synthetic" not in refused.text


def test_registration_admission_is_shared_across_directory_instances(tmp_path):
    one, two = (FileDirectory(tmp_path, key=KEY) for _ in range(2))
    claim = one._claim_path(one._registration_lock)
    assert claim is not None
    try:
        with pytest.raises(RegistrationUnavailable):
            two.admit_registration(EMAIL, "source", utcnow())
        assert not one._registration_attempts.exists()
    finally:
        claim.release()
    assert two.admit_registration(EMAIL, "source", utcnow()).allowed


def test_public_admissions_cannot_turn_concurrent_creation_into_overwrite(tmp_path):
    now = utcnow()
    identities = [FileDirectory(tmp_path, key=KEY) for _ in range(2)]
    credentials = [enrol(password) for password in (PASSWORD, OTHER_PASSWORD)]
    for directory in identities:
        assert directory.admit_registration(EMAIL, "source", now).allowed
    barrier = threading.Barrier(2)

    def create(number):
        barrier.wait()
        try:
            identities[number].enrol(Enrolment(
                identity=AdvocateIdentity(id=EMAIL, name=EMAIL, email=EMAIL),
                credential=credentials[number], created_at=now))
            return "created"
        except AlreadyEnrolled:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, range(2)))
    assert sorted(outcomes) == ["created", "refused"]
    directory = FileDirectory(tmp_path, key=KEY)
    assert sum(directory.authenticate(EMAIL, password) is not None
               for password in (PASSWORD, OTHER_PASSWORD)) == 1


def test_public_registration_capacity_never_evicts_live_admissions(tmp_path, monkeypatch):
    import nm.adapters.store.directory as storage

    monkeypatch.setattr(storage, "REGISTRATION_MAX_RECORDS", 2)
    directory = FileDirectory(tmp_path, key=KEY)
    now = utcnow()
    for number in range(2):
        assert directory.admit_registration(f"mail-{number}@example.com", "source", now).allowed
    before = directory._registration_attempts.read_bytes()
    with pytest.raises(RegistrationUnavailable):
        directory.admit_registration(EMAIL, "new-source", now)
    assert directory._registration_attempts.read_bytes() == before
    assert directory.admit_registration(EMAIL, "new-source", now + attempts.WINDOW).allowed


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "https://foreign.example"}, {"Origin": "null"},
    {"Origin": "http://testserver.attacker.example"},
    {"Referer": "http://testserver.attacker.example/signup"},
    {"Origin": "https://foreign.example", "Referer": "http://testserver/"},
])
def test_public_registration_refuses_foreign_or_missing_origin(client, headers):
    from nm.edge import api

    # This client has no browser-header fixture: absence must remain absent.
    with TestClient(api.app) as raw:
        response = raw.post("/api/register", json={
            "email": EMAIL, "password": PASSWORD, "password_again": PASSWORD,
        }, headers=headers)
    assert response.status_code == 403, response.text
    assert client.directory.identity(EMAIL) is None
    assert not client.directory._registration_attempts.exists()
    assert _register(client).status_code == 200, "same-origin positive path was lost"


def test_invitation_lane_cannot_be_redirected_to_an_email(client):
    token = client.invite("invited@example.com", name="Invited advocate", firm_id="firm-one")
    body = {"email": EMAIL, "password": PASSWORD, "password_again": PASSWORD}
    refused = client.post("/api/register", json=body,
                          headers={"X-Enrolment-Invitation": token})
    assert refused.status_code == 422, refused.text
    assert client.directory.identity(EMAIL) is None
    assert client.directory.identity("invited@example.com") is None
    assert not client.directory._registration_attempts.exists()
    del body["email"]
    accepted = client.post("/api/register", json=body,
                           headers={"X-Enrolment-Invitation": token})
    assert accepted.status_code == 200, accepted.text
    assert client.directory.identity("invited@example.com").firm_id == "firm-one"


def test_supplied_invalid_invitation_never_falls_back_to_public_signup(client):
    for invitation in ("", " ", "unknown-token"):
        refused = client.post("/api/register", json={
            "email": EMAIL, "password": PASSWORD, "password_again": PASSWORD,
        }, headers={"X-Enrolment-Invitation": invitation})
        assert refused.status_code == 422, refused.text
    assert client.directory.identity(EMAIL) is None
    assert not client.directory._registration_attempts.exists()


def test_a_future_admission_clock_is_unknown_not_an_empty_population(tmp_path):
    directory = FileDirectory(tmp_path, key=KEY)
    now = utcnow()
    assert directory.admit_registration(EMAIL, "source", now).allowed
    before = directory._registration_attempts.read_bytes()
    with pytest.raises(RegistrationUnavailable):
        directory.admit_registration("other@example.com", "source", now - timedelta(seconds=1))
    assert directory._registration_attempts.read_bytes() == before


@pytest.mark.parametrize("field", ["email", "password", "password_again"])
def test_invalid_registration_shapes_never_echo_submitted_secrets(client, field):
    secret = "Never-Echo-This-Secret-83"
    body = {"email": EMAIL, "password": PASSWORD, "password_again": PASSWORD}
    body[field] = {"secret": secret}
    refused = client.post("/api/register", json=body)
    assert refused.status_code == 422, refused.text
    assert secret not in refused.text
    assert all(set(row) == {"loc", "type", "msg"} for row in refused.json()["detail"])
    assert client.directory.identity(EMAIL) is None
    assert not client.directory._registration_attempts.exists()


def test_an_unrecognised_field_name_is_not_a_validation_echo(client):
    secret = "Never-Echo-This-Secret-83"
    refused = _register(client, **{secret: "also private"})
    assert refused.status_code == 422
    assert secret not in refused.text and "also private" not in refused.text
    assert refused.json()["detail"][0]["loc"][-1] == "unrecognised_field"


@pytest.mark.parametrize("field", ["password", "password_again"])
def test_oversized_registration_passwords_refuse_before_admission(client, field):
    secret = "Oversized-secret-83-" + "x" * 1024
    refused = _register(client, **{field: secret})
    assert refused.status_code == 422, refused.text
    assert secret not in refused.text
    assert not client.directory._registration_attempts.exists()
    assert client.directory.identity(EMAIL) is None


def test_the_largest_registration_password_still_signs_in_and_is_not_disclosed(client):
    password = "Valid-long-password-83-".ljust(1024, "x")
    assert len(password) == 1024
    created = _register(client, password=password, password_again=password)
    assert created.status_code == 200, created.text
    assert password not in created.text
    assert _login(client, password=password).status_code == 200
    generation = client.get("/api/session").json()["recovery_generation"]
    proof = client.post("/api/reauthenticate", json={"password": password})
    assert proof.status_code == 200, proof.text
    assert password not in proof.text
    rotated = client.post("/api/recovery-codes/rotate", json={
        "proof": proof.json()["proof"], "expected_recovery_generation": generation,
    })
    assert rotated.status_code == 200, rotated.text
    assert len(rotated.json()["recovery_codes"]) == 10
    assert set(rotated.json()["recovery_codes"]).isdisjoint(created.json()["recovery_codes"])
    replacement = "Replacement-long-password-94-".ljust(1024, "y")
    recovered = client.post("/api/recover", json={
        "advocate_id": EMAIL, "recovery_code": rotated.json()["recovery_codes"][0],
        "password": replacement, "password_again": replacement,
    })
    assert recovered.status_code == 200, recovered.text
    assert replacement not in recovered.text
    assert _login(client, password=password).status_code == 401
    assert _login(client, password=replacement).status_code == 200
    assert client.post("/api/reauthenticate", json={"password": replacement}).status_code == 200


def test_existing_long_credentials_still_sign_in_and_reauthenticate(client):
    # Operator/legacy records are not rewritten by a public request-shape bound.
    password = "Legacy-password-83-".ljust(2048, "z")
    account = "legacy-long@example.com"
    client.directory.enrol(Enrolment(
        identity=AdvocateIdentity(id=account, name=account, email=account),
        credential=enrol(password)))
    assert _login(client, account, password).status_code == 200
    confirmed = client.post("/api/reauthenticate", json={"password": password})
    assert confirmed.status_code == 200, confirmed.text
    assert password not in confirmed.text


@pytest.mark.parametrize("field", ["password", "password_again"])
def test_recovery_uses_the_same_new_password_bound_without_consuming_a_code(client, field):
    created = _register(client)
    assert created.status_code == 200
    path = client.directory._advocate_path(EMAIL)
    before = path.read_bytes()
    body = {
        "advocate_id": EMAIL, "recovery_code": created.json()["recovery_codes"][0],
        "password": OTHER_PASSWORD, "password_again": OTHER_PASSWORD,
    }
    secret = "Oversized-new-password-84-".ljust(1025, "x")
    body[field] = secret
    refused = client.post("/api/recover", json=body)
    assert refused.status_code == 422, refused.text
    assert secret not in refused.text
    assert body["recovery_code"] not in refused.text
    assert path.read_bytes() == before
    body[field] = OTHER_PASSWORD
    assert client.post("/api/recover", json=body).status_code == 200
    assert _login(client, password=OTHER_PASSWORD).status_code == 200


def test_validation_callback_is_registered_on_the_served_application(client):
    from fastapi.exceptions import RequestValidationError

    from nm.edge import api

    assert client.app.exception_handlers[RequestValidationError] is api.invalid_request
    secret = "Do-not-return-this-private-value-87"
    refused = client.post("/api/register", json={
        "email": EMAIL, "password": [secret], "password_again": PASSWORD,
    })
    assert refused.status_code == 422, refused.text
    assert secret not in refused.text
    assert refused.json()["detail"] == [{
        "loc": ["body", "password"], "type": "string_type",
        "msg": "The supplied value is not valid for this field.",
    }]
    assert _register(client).status_code == 200


def test_an_unreadable_professional_predecessor_cannot_reach_the_update(client, monkeypatch):
    from dataclasses import replace

    from nm.domain.professional_access import ProfessionalApproval
    from tests.test_professional_approval_is_separate_from_account_access import (
        approve_fixture_account,
    )

    at = utcnow()
    first = approve_fixture_account(client.directory, now=at)
    replacement_at = at + timedelta(minutes=1)
    replacement = replace(first, version=2, approved_at=replacement_at)
    account = client.directory._advocate_path(first.account_id)
    before = account.read_bytes()
    original_reader = ProfessionalApproval.from_record
    observed = []

    def invalidated_reader(row):
        parsed = original_reader(row)
        observed.append(parsed)
        # The history boundary parsed it; the consumer's subsequent read is
        # now unestablished. This is a reader-contract fault, not legal data.
        return parsed if len(observed) == 1 else None

    with monkeypatch.context() as fault:
        fault.setattr(ProfessionalApproval, "from_record", staticmethod(invalidated_reader))
        with pytest.raises(ValueError, match="history is unreadable"):
            client.directory.record_professional_approval(
                replacement, expected_version=1, now=replacement_at)
    assert observed == [first, first], "the consumer boundary was not exercised"
    assert account.read_bytes() == before, "a failed guard changed the sealed history"
    saved = client.directory.record_professional_approval(
        replacement, expected_version=1, now=replacement_at)
    assert saved == replacement.as_dict(), "refusal must release its account claim"
