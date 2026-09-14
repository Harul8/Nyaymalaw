"""BK-31 — the controlled roster is enforced by one-use invitations.

The invitation fixes who may enrol, their roster profile and which workspace
they enter. Absence, expiry and replay all fail closed and all look the same to
the caller; the registration body has no identity fields to disagree with it.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from nm.adapters.store.directory import FileDirectory
from nm.domain import attempts
from nm.domain.advocate import (
    AdvocateIdentity,
    canonical_id,
    enrol,
    new_invitation,
    token_fingerprint,
    utcnow,
)
from nm.ports.directory import AlreadyEnrolled, InvitationRefused

pytestmark = pytest.mark.class_a

GOOD = {
    "name": "R Kumar",
    "email": "R.Kumar@Example.com",
    "enrolment": "AP/1234/2010",
    "practice": "Hyderabad",
    "firm_id": "firm_rk",
    "password": "Cinder-lantern-42",
    "password_again": "Cinder-lantern-42",
}

REGISTRATION = {
    "password": GOOD["password"],
    "password_again": GOOD["password_again"],
}


def _identity(body: dict = GOOD) -> AdvocateIdentity:
    email = canonical_id(body["email"])
    return AdvocateIdentity(
        id=email, email=email, name=body["name"].strip(),
        enrolment=body.get("enrolment", "").strip(),
        practice=body.get("practice", "").strip(),
        firm_id=body.get("firm_id", "").strip())


def _invite(client, body: dict = GOOD, *, at=None) -> str:
    return client.invite(
        body["email"], name=body["name"],
        enrolment=body.get("enrolment", ""),
        practice=body.get("practice", ""),
        firm_id=body.get("firm_id", ""), at=at)


def _register(client, token: str | None, body: dict = REGISTRATION):
    headers = ({"X-Enrolment-Invitation": token} if token is not None else {})
    return client.post("/api/register", json=body, headers=headers)


def test_a_public_registration_requires_an_email(client):
    """Without an invitation, the public lane requires its own email handle."""
    response = _register(client, None)
    assert response.status_code == 422, response.text
    assert "email" in response.json()["detail"].lower()
    assert client.directory.identity(GOOD["email"]) is None


def test_an_invitation_needs_a_real_lifetime_and_one_line_issuer():
    now = utcnow()
    for lifetime in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError, match="lifetime"):
            new_invitation(_identity(), "operator", now, lifetime)
    with pytest.raises(ValueError, match="audit line"):
        new_invitation(_identity(), "operator\nforged-event", now)


def test_a_blank_invitation_does_not_open_the_door(client):
    for blank in ("", "   ", "\t"):
        assert _register(client, blank).status_code == 403


def test_the_wrong_invitation_is_refused(client):
    for offered in ("guess", "not-nearly-an-invitation", "A" * 64):
        assert _register(client, offered).status_code == 403


def test_the_right_invitation_is_admitted(client):
    response = _register(client, _invite(client))
    assert response.status_code == 200, response.text
    assert response.json()["advocate_id"] == "r.kumar@example.com"


def test_the_refusal_tells_the_advocate_what_to_do_instead(client):
    said = _register(client, "wrong").json()["detail"].lower()
    assert "nothing was saved" in said
    assert "administers" in said


def test_it_is_refused_on_the_wire_and_not_only_in_the_function(client):
    """Incomplete public input fails; the password-only invited lane remains."""
    assert _register(client, None).status_code == 422
    assert _register(client, _invite(client)).status_code == 200


def test_an_unauthorised_attempt_enrols_nobody(client):
    assert _register(client, "wrong").status_code == 403
    assert client.directory.identity(GOOD["email"]) is None
    assert _register(client, _invite(client)).status_code == 200, (
        "the refused attempt left a record behind")


def test_an_invitation_is_single_use_and_cannot_be_replayed(client):
    token = _invite(client)
    assert _register(client, token).status_code == 200
    replay = _register(client, token)
    assert replay.status_code == 403, replay.text


def test_an_expired_invitation_is_refused(client):
    token = _invite(client, at=utcnow() - timedelta(hours=49))
    response = _register(client, token)
    assert response.status_code == 403, response.text
    assert client.directory.identity(GOOD["email"]) is None


def test_the_invitation_owns_identity_profile_and_workspace(client):
    token = _invite(client)
    replacement = {
        **REGISTRATION,
        "email": "stranger@example.com",
        "name": "Someone Else",
        "enrolment": "OTHER/999",
        "practice": "Somewhere Else",
        "firm_id": "another_firm",
    }
    refused = _register(client, token, replacement)
    assert refused.status_code == 422, refused.text
    assert client.directory.identity("stranger@example.com") is None

    # Invalid duplicate identity fields do not burn the invitation. The
    # password-only request succeeds and the sealed invitation's complete
    # roster identity is the one persisted.
    assert _register(client, token).status_code == 200
    assert client.directory.identity(GOOD["email"]) == _identity()


def test_only_a_fingerprint_of_the_invitation_is_stored(client):
    token = _invite(client)
    paths = list(client.directory._invitations.glob("*.nm"))
    assert len(paths) == 1
    raw = paths[0].read_bytes()
    assert token.encode("utf8") not in raw
    assert GOOD["email"].lower().encode("utf8") not in raw, (
        "the invitation roster identity was written without the directory seal")

    record = json.loads(client.directory._cipher.decrypt(raw).decode("utf8"))
    assert record["token_fingerprint"] == token_fingerprint(token)
    assert token not in json.dumps(record)

    assert _register(client, token).status_code == 200
    used = list(client.directory._used_invitations.glob("*.nm"))
    assert len(used) == 1
    assert not list(client.directory._used_invitations.glob("*.json")), (
        "sealed bytes are labelled JSON in the used-invitation store")
    used_raw = used[0].read_bytes()
    assert used_raw == raw, "spending changed the sealed invitation record"
    assert token.encode("utf8") not in used_raw
    assert GOOD["email"].lower().encode("utf8") not in used_raw


def test_the_operator_tool_issues_the_bound_identity_and_prints_the_token_once(
        monkeypatch, capsys):
    from nm.bootstrap import composition

    from backend.operations import invite as command

    issued = []

    class Directory:
        def issue_invitation(self, identity, issued_by, now):
            issued.append((identity, issued_by, now))
            return "one-time-token"

    monkeypatch.setattr(
        composition, "Application",
        lambda: type("App", (), {"directory": Directory()})())
    result = command.main([
        "--email", "R.Kumar@Example.com", "--name", "R Kumar",
        "--enrolment", "AP/1234/2010", "--practice", "Hyderabad",
        "--firm", "firm_rk", "--issued-by", "chambers-admin"])

    assert result == 0
    assert issued[0][0] == _identity()
    assert issued[0][1] == "chambers-admin"
    assert capsys.readouterr().out.count("one-time-token") == 1


def test_repeated_wrong_invitations_are_rate_limited_and_audited_without_the_token(
        client):
    token = "wrong-invitation-that-must-never-be-logged"
    for _ in range(attempts.PER_ADVOCATE):
        assert _register(client, token).status_code == 403
    limited = _register(client, token)
    assert limited.status_code == 429, limited.text
    assert "failed enrolment attempts" in limited.json()["detail"].lower()

    audit = client.directory._audit.read_text(encoding="utf8")
    attempt_log = client.directory._attempts.read_text(encoding="utf8")
    assert "invitation refused" in audit
    assert token not in audit
    assert token not in attempt_log


def test_unknown_expired_and_replayed_invitations_do_not_form_an_oracle(client):
    expired = _invite(client, at=utcnow() - timedelta(hours=49))
    replay = _invite(client)
    assert _register(client, replay).status_code == 200
    answers = [
        _register(client, "unknown").json()["detail"],
        _register(client, expired).json()["detail"],
        _register(client, replay).json()["detail"],
    ]
    assert len(set(answers)) == 1


def test_two_directory_instances_cannot_both_spend_one_invitation(tmp_path):
    identity = _identity()
    credential = enrol(GOOD["password"])

    # Repeat inside one evidence node. The old per-instance locks usually
    # appeared to work and failed only when both adapters crossed the claim
    # point closely enough; one lucky pass is not evidence of exclusion.
    for attempt in range(20):
        root = tmp_path / str(attempt)
        issuer = FileDirectory(root, key="k" * 32)
        token = issuer.issue_invitation(identity, "operator", utcnow())
        barrier = threading.Barrier(2)

        def spend(root=root, barrier=barrier, token=token) -> str:
            directory = FileDirectory(root, key="k" * 32)
            barrier.wait()
            try:
                directory.accept_invitation(
                    token, credential, utcnow())
                return "enrolled"
            except InvitationRefused:
                return "refused"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: spend(), range(2)))
        assert sorted(outcomes) == ["enrolled", "refused"], (
            f"attempt {attempt} did not enforce one filesystem claim: "
            f"{outcomes}")


def test_two_invitations_cannot_race_to_replace_one_advocate(tmp_path):
    """BK-31-AC11. The identity path is also an exclusive claim.

    Invitation fingerprints serialize presentations of one token. They do not
    serialize two different tokens issued for the same identity, so the
    advocate record itself must refuse last-writer-wins.
    """
    identity = _identity()
    credentials = (
        enrol(GOOD["password"]),
        enrol("River-stone-77"),
    )

    for attempt in range(10):
        root = tmp_path / f"identity-{attempt}"
        issuer = FileDirectory(root, key="k" * 32)
        claims = tuple(
            (issuer.issue_invitation(identity, "operator", utcnow()), credential)
            for credential in credentials
        )
        barrier = threading.Barrier(2)

        def spend(claim, root=root, barrier=barrier) -> str:
            token, credential = claim
            directory = FileDirectory(root, key="k" * 32)
            barrier.wait()
            try:
                directory.accept_invitation(
                    token, credential, utcnow())
                return "enrolled"
            except AlreadyEnrolled:
                return "already enrolled"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(spend, claims))
        assert sorted(outcomes) == ["already enrolled", "enrolled"], (
            f"attempt {attempt} allowed last-writer-wins: {outcomes}")

        saved = FileDirectory(root, key="k" * 32)
        working = sum(
            saved.authenticate(identity.id, password) is not None
            for password in (GOOD["password"], "River-stone-77")
        )
        assert working == 1, (
            "the race did not leave exactly one deliberate credential")
