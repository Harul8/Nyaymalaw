"""A FORGOTTEN PASSWORD IS REPLACED THROUGH AN EMAILED LINK. Implementation Plan F-A-03.

Each rule below is asserted on the served routes or the real directory, with
the failure it refuses:

    one answer         a known address, an unknown one and an account with no
                       email get the same response, so the door is no roster probe
    single use         a link changes the password once and never again
    expiry             a link past its lifetime changes nothing
    generation         a password change retires every link issued before it
    passwords first    a mismatch, or a password the rules refuse, leaves the link unspent
    sessions           a reset ends every earlier session
    nothing in clear   the token and the new password are on no file in the clear
    no poisoned link   a configured public URL wins over the request's Host header,
                       and a mailbox channel without one sends nothing
    limits             requests per address and failed links per source are paused
    concurrency        two workers cannot both spend one link
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from nm.adapters.mail.outbox import FileOutbox
from nm.adapters.store.directory import FileDirectory
from nm.domain import attempts
from nm.domain.advocate import (
    PASSWORD_RESET_MINUTES,
    AccountSecurity,
    AdvocateIdentity,
    Enrolment,
    PasswordReset,
    enrol,
    new_password_reset,
    token_fingerprint,
    utcnow,
)
from nm.domain.mail import MailMessage, password_reset_mail
from nm.ports.directory import AccountBusy

from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a

PASSWORD = "Cinder-lantern-42"
NEW_PASSWORD = "Harbour-meadow-17!"
OTHER_PASSWORD = "Quarry-willow-55!"
EMAIL = "forgot@example.com"
LINK = re.compile(r"(https?://\S+?/#reset=([A-Za-z0-9_-]+))")


def _register(client, email=EMAIL, password=PASSWORD):
    from tests.registration import CONSENT

    response = client.post("/api/register", json={
        "email": email, "password": password, "password_again": password,
        "consent": CONSENT})
    assert response.status_code == 200, response.text


def _forgot(client, email=EMAIL, **kwargs):
    return client.post("/api/password/forgot", json={"email": email}, **kwargs)


def _reset(client, token, password=NEW_PASSWORD, again=None):
    return client.post("/api/password/reset", json={
        "token": token, "password": password,
        "password_again": password if again is None else again})


def _login(client, email=EMAIL, password=PASSWORD):
    return TestClient(client.app).post(
        "/api/login", json={"advocate_id": email, "password": password})


def reset_link_for(client, email=EMAIL) -> tuple[str, str]:
    """(link, token) from the newest reset message queued for this address."""
    messages = client.outbox.messages_for(email)
    assert messages, f"no reset message was queued for {email}"
    found = LINK.search(messages[-1]["text"])
    assert found, "the queued message carries no reset link"
    return found.group(1), found.group(2)


# ================================ the domain =================================

def test_a_link_is_single_use_expiring_and_bound_to_one_credential_generation():
    now = utcnow()
    token, reset = new_password_reset("Forgot@Example.com", AccountSecurity(3), now)
    assert reset.advocate_id == "forgot@example.com"
    assert reset.token_fingerprint == token_fingerprint(token) != token
    assert token not in json.dumps(reset.as_dict())
    assert PasswordReset.from_dict(reset.as_dict()) == reset

    current = AccountSecurity(3)
    lifetime = timedelta(minutes=PASSWORD_RESET_MINUTES)
    assert reset.why_not(security=current, now=now) is None
    assert reset.why_not(security=current, now=now + lifetime - timedelta(seconds=1)) is None
    assert "expired" in reset.why_not(security=current, now=now + lifetime)
    assert "password changed" in reset.why_not(
        security=current.with_new_credential(), now=now)
    assert "already used" in replace(reset, consumed_at=now).why_not(
        security=current, now=now)


def test_the_reset_message_states_its_lifetime_single_use_and_effect():
    message = password_reset_mail(EMAIL, "http://testserver/#reset=abc")
    assert message.to == EMAIL and message.purpose == "password-reset"
    assert "http://testserver/#reset=abc" in message.text
    assert f"{PASSWORD_RESET_MINUTES} minutes" in message.text
    assert "works once" in message.text and "every device" in message.text
    for broken in ("", "http://x/#reset=a b", "http://x/\r\nBcc: y@example.com"):
        with pytest.raises(ValueError):
            password_reset_mail(EMAIL, broken)
    with pytest.raises(ValueError):
        MailMessage(to="Not An Email", subject="s", text="t", purpose="p")
    with pytest.raises(ValueError):
        MailMessage(to=EMAIL, subject="a\nBcc: y@example.com", text="t", purpose="p")


# =============================== the served door =============================

def test_known_unknown_and_undeliverable_accounts_get_one_answer(client):
    _register(client)
    client.directory.enrol(Enrolment(
        identity=AdvocateIdentity(id="noemail@example.com", name="No Email"),
        credential=enrol(PASSWORD)))
    answers = [_forgot(client, address) for address in (
        EMAIL, "nobody@example.com", "noemail@example.com")]
    assert [answer.status_code for answer in answers] == [202] * 3
    assert answers[0].json() == answers[1].json() == answers[2].json()
    assert answers[0].json()["detail"].startswith("If an account exists")
    assert len(client.outbox.messages_for(EMAIL)) == 1
    assert client.outbox.messages_for("nobody@example.com") == ()
    assert client.outbox.messages_for("noemail@example.com") == ()


def test_a_link_resets_the_password_once_and_ends_every_session(client):
    _register(client)
    one = client.sign_in(EMAIL, password=PASSWORD, fresh=True)
    two = client.sign_in(EMAIL, password=PASSWORD, fresh=True)
    assert _forgot(client).status_code == 202
    link, token = reset_link_for(client)
    assert link == f"http://testserver/#reset={token}"

    done = _reset(client, token)
    assert done.status_code == 200, done.text
    assert done.json() == {"reset": True, "sessions_ended": 2}
    assert one.get("/api/session").status_code == 401
    assert two.get("/api/session").status_code == 401
    assert _login(client).status_code == 401
    assert _login(client, password=NEW_PASSWORD).status_code == 200

    replayed = _reset(client, token, OTHER_PASSWORD)
    assert replayed.status_code == 400
    assert _login(client, password=OTHER_PASSWORD).status_code == 401
    assert _login(client, password=NEW_PASSWORD).status_code == 200


def test_used_superseded_unknown_and_expired_links_have_one_refusal(client, monkeypatch):
    from nm.edge import api

    _register(client)
    assert _forgot(client).status_code == 202
    _, first = reset_link_for(client)
    assert _forgot(client).status_code == 202
    _, second = reset_link_for(client)
    assert first != second
    assert _reset(client, second).status_code == 200  # retires `first` as well

    refusals = [_reset(client, first, OTHER_PASSWORD),
                _reset(client, second, OTHER_PASSWORD),
                _reset(client, "not-a-real-link", OTHER_PASSWORD)]
    assert _forgot(client).status_code == 202
    _, late = reset_link_for(client)
    later = utcnow() + timedelta(minutes=PASSWORD_RESET_MINUTES + 1)
    monkeypatch.setattr(api, "utcnow", lambda: later)
    refusals.append(_reset(client, late, OTHER_PASSWORD))

    assert [refusal.status_code for refusal in refusals] == [400] * 4
    assert len({refusal.text for refusal in refusals}) == 1, "refusals differ by cause"
    assert "not valid or has expired" in refusals[0].json()["detail"]
    assert _login(client, password=NEW_PASSWORD).status_code == 200


def test_the_passwords_are_checked_before_the_link_is_spent(client):
    _register(client)
    assert _forgot(client).status_code == 202
    _, token = reset_link_for(client)
    mismatch = _reset(client, token, NEW_PASSWORD, "Different-pass-99!")
    weak = _reset(client, token, "weak")
    assert mismatch.status_code == 400 and "do not match" in mismatch.json()["detail"]
    assert weak.status_code == 400 and "password" in weak.json()["detail"]
    assert _reset(client, token).status_code == 200


def test_no_token_or_new_password_is_written_anywhere_in_the_clear(client):
    _register(client)
    assert _forgot(client).status_code == 202
    _, token = reset_link_for(client)
    assert _reset(client, token).status_code == 200
    root = client.directory._root
    assert (root / "password-resets" / f"{token_fingerprint(token)}.nm").exists()
    scanned = 0
    for path in root.rglob("*"):
        if path.is_file():
            scanned += 1
            raw = path.read_bytes()
            assert token.encode() not in raw, path
            assert NEW_PASSWORD.encode() not in raw, path
    assert scanned >= 4, "the scan read almost nothing and would pass anything"


def test_a_configured_public_url_wins_over_the_request_host(client, monkeypatch):
    from nm.edge import api

    _register(client)
    monkeypatch.setattr(api.application(), "environment",
                        {"NM_PUBLIC_URL": "https://nyaymalaw.example/"})
    poisoned = _forgot(client, headers={
        "host": "attacker.example", "origin": "http://attacker.example"})
    assert poisoned.status_code == 202, poisoned.text
    text = client.outbox.messages_for(EMAIL)[-1]["text"]
    assert "https://nyaymalaw.example/#reset=" in text
    assert "attacker.example" not in text


def test_a_mailbox_channel_without_a_public_url_sends_nothing(client, monkeypatch, caplog):
    from nm.edge import api

    class Mailbox:
        delivers_to_mailbox = True

        def __init__(self) -> None:
            self.sent: list[MailMessage] = []

        def send(self, message: MailMessage) -> None:
            self.sent.append(message)

    _register(client)
    mailbox = Mailbox()
    monkeypatch.setattr(api.application(), "mail", mailbox)
    monkeypatch.setattr(api.application(), "environment", {})
    with caplog.at_level(logging.ERROR, logger="nm.account_mail"):
        assert _forgot(client).status_code == 202
    assert mailbox.sent == []
    assert "NM_PUBLIC_URL" in caplog.text

    monkeypatch.setattr(api.application(), "environment",
                        {"NM_PUBLIC_URL": "https://nyaymalaw.example"})
    assert _forgot(client).status_code == 202
    assert len(mailbox.sent) == 1
    assert "https://nyaymalaw.example/#reset=" in mailbox.sent[0].text


def test_reset_requests_are_limited_per_address_whether_or_not_it_exists(client):
    _register(client)
    paused = []
    for address in (EMAIL, "nobody@example.com"):
        for _ in range(attempts.PER_ADVOCATE):
            assert _forgot(client, address).status_code == 202
        refused = _forgot(client, address)
        assert refused.status_code == 429, refused.text
        paused.append(refused.json())
    assert paused[0] == paused[1], "the pause says whether the account exists"


def test_failed_links_are_limited_per_source(client):
    for _ in range(attempts.PER_ADVOCATE):
        assert _reset(client, "not-a-real-link").status_code == 400
    assert _reset(client, "not-a-real-link").status_code == 429


def test_the_reset_doors_refuse_a_foreign_or_missing_origin(client):
    from nm.edge import api

    _register(client)
    with TestClient(api.app) as raw:
        for headers in ({}, {"Origin": "https://foreign.example"}):
            assert raw.post("/api/password/forgot", json={"email": EMAIL},
                            headers=headers).status_code == 403
            assert raw.post("/api/password/reset", json={
                "token": "x", "password": NEW_PASSWORD, "password_again": NEW_PASSWORD,
            }, headers=headers).status_code == 403
    assert client.outbox.messages_for(EMAIL) == ()


def test_the_health_report_says_where_reset_links_actually_go(client):
    health = client.get("/api/health").json()
    assert health["account_mail"].startswith("LOCAL OUTBOX ONLY")


# ============================== the directory ================================

def _enrolled(tmp_path) -> FileDirectory:
    directory = FileDirectory(tmp_path, key=KEY)
    directory.enrol(Enrolment(
        identity=AdvocateIdentity(id=EMAIL, name=EMAIL, email=EMAIL),
        credential=enrol(PASSWORD)))
    return directory


def test_two_workers_cannot_both_spend_one_link(tmp_path):
    token = _enrolled(tmp_path).issue_password_reset(EMAIL, utcnow())
    assert token
    workers = [FileDirectory(tmp_path, key=KEY) for _ in range(2)]
    credentials = [enrol(NEW_PASSWORD), enrol(OTHER_PASSWORD)]

    def spend(number: int) -> bool:
        try:
            return workers[number].reset_password(
                token, credentials[number], utcnow()).success
        except AccountBusy:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(spend, range(2)))
    assert sorted(results) == [False, True]
    verified = FileDirectory(tmp_path, key=KEY)
    assert sum(verified.authenticate(EMAIL, password) is not None
               for password in (NEW_PASSWORD, OTHER_PASSWORD)) == 1


def test_a_reset_that_cannot_claim_the_account_changes_nothing(tmp_path):
    directory = _enrolled(tmp_path)
    token = directory.issue_password_reset(EMAIL, utcnow())
    claim = directory._claim_account(EMAIL)
    assert claim is not None
    try:
        with pytest.raises(AccountBusy):
            FileDirectory(tmp_path, key=KEY).reset_password(
                token, enrol(NEW_PASSWORD), utcnow())
    finally:
        claim.release()
    assert directory.authenticate(EMAIL, PASSWORD) is not None
    assert directory.reset_password(token, enrol(NEW_PASSWORD), utcnow()).success


def test_the_outbox_is_sealed_and_names_no_address(tmp_path):
    outbox = FileOutbox(tmp_path, key=KEY)
    assert not (tmp_path / "outbox").exists(), "composing the outbox wrote to disk"
    outbox.send(password_reset_mail(EMAIL, "http://testserver/#reset=secret-token-value"))
    files = list((tmp_path / "outbox").glob("*.nm"))
    assert len(files) == 1
    raw = files[0].read_bytes()
    assert b"secret-token-value" not in raw and EMAIL.encode() not in raw
    assert EMAIL not in files[0].name
    assert outbox.messages_for(EMAIL.upper())[0]["purpose"] == "password-reset"
    stranger = FileOutbox(tmp_path, key="a-different-installation-key")
    assert stranger.messages_for(EMAIL) == ()
    assert stranger.unreadable() == 1, "an unreadable message was dropped silently"
    with pytest.raises(TypeError):
        outbox.send({"to": EMAIL})
