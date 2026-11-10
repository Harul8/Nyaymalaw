"""Offline SMTP contract tests; every socket is replaced, never a real send.

Plan AN.48, owner decision D168 (10 Nov 2026): Gmail sends NM's account mail. The owner's exception admits it through a gate of its
own, for account mail alone; every other route's gate still refuses it. The sender signs in with a Google app password (or an OAuth
access token) read from a local file at each send, and the secret is in no error, log or message. All values here are synthetic.
"""

import logging
import smtplib
import ssl
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from nm.app.composition import GMAIL_BASIS, build_mail, gmail_policy
from nm.arrive.mail_contracts import confirmation_mail, password_reset_mail
from nm.arrive.mail_gmail import GMAIL_PROCESSOR, MAIL_CLASSES, DisabledMail, GmailMail
from nm.arrive.mail_port import MailNotConfirmed
from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Sink
from nm.shared.egress_policy import egress_policy

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
#: Synthetic, in the groups of four Google shows an app password in.
APP_PASSWORD = "abcd efgh ijkl mnop"
SIGNED_IN_WITH = "abcdefghijklmnop"
SENDER = "sender@example.test"
ADVOCATE = "recipient@example.test"
KEY = "Synthetic-gmail-store-key-61"


class PermittedFixture:
    def __init__(self):
        self.calls = []

    def permit(self, *args):
        self.calls.append(args)


@pytest.fixture
def smtp(monkeypatch):
    observed = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context):
            observed.append(("connect", host, port, timeout, context))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            observed.append(("ehlo",))

        def auth(self, mechanism, callback):
            observed.append(("auth", mechanism, callback(), callback(b"challenge")))

        def login(self, user, password):
            observed.append(("login", user, password))

        def send_message(self, message, *, from_addr, to_addrs):
            observed.append(("send", message, from_addr, to_addrs))
            return {}

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return observed, FakeSMTP


@pytest.fixture
def transport(tmp_path, smtp):
    token = tmp_path / "synthetic-token"
    token.write_text("synthetic-AccessToken", encoding="utf8")
    observed, fake = smtp
    gate = PermittedFixture()
    adapter = GmailMail(SENDER, token, gate, enabled=True)
    return adapter, gate, observed, fake


@pytest.fixture
def app_password(tmp_path, smtp):
    secret = tmp_path / "synthetic-app-password"
    secret.write_text(APP_PASSWORD + "\n", encoding="utf8")
    observed, fake = smtp
    gate = PermittedFixture()
    adapter = GmailMail(SENDER, None, gate, enabled=True, password_file=secret)
    return adapter, gate, observed, fake


def gmail_settings(secret, **more):
    return {"NM_MAIL_PROVIDER": "gmail", "NM_MAIL_DELIVERY": "enabled", "NM_MAIL_SENDER": SENDER,
            "NM_GMAIL_APP_PASSWORD_FILE": str(secret), **more}


# ------------------------------------------------------------------ the sender, signing in with an access token ---

def test_gmail_is_disabled_before_secret_access_or_network(transport):
    adapter, gate, observed, _ = transport
    adapter.token_file.unlink()
    disabled = GmailMail(adapter.sender, adapter.token_file, gate)
    with pytest.raises(MailNotConfirmed, match="disabled"):
        disabled.send(confirmation_mail(ADVOCATE, "123456"))
    assert not observed and not gate.calls
    assert disabled.delivers_to_mailbox is False


def test_account_mail_uses_verified_tls_single_recipient_and_oauth(transport):
    adapter, gate, observed, _ = transport
    adapter.send(confirmation_mail(ADVOCATE, "123456"))
    assert len(gate.calls) == 1 and gate.calls[0][1] == GMAIL_PROCESSOR
    _, host, port, timeout, context = observed[0]
    assert (host, port, timeout) == ("smtp.gmail.com", 465, 10)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert observed[2][1] == "XOAUTH2"
    assert observed[2][2] == "user=sender@example.test\x01auth=Bearer synthetic-AccessToken\x01\x01"
    assert observed[2][3] == ""
    assert observed[3][3] == [ADVOCATE]
    assert "123456" in observed[3][1].get_content()
    assert "synthetic-AccessToken" not in str(observed[3][1])


@pytest.mark.parametrize("failure", ["authentication", "recipient", "timeout"])
def test_transport_failures_are_redacted_and_never_retried(transport, monkeypatch, failure):
    adapter, _, observed, smtp = transport

    def fail(*args, **kwargs):
        if failure == "authentication":
            raise smtplib.SMTPAuthenticationError(
                535, b"synthetic-AccessToken recipient@example.test"
            )
        if failure == "timeout":
            raise TimeoutError("synthetic-AccessToken")
        return {ADVOCATE: (550, b"synthetic-AccessToken")}

    monkeypatch.setattr(smtp, "auth" if failure == "authentication" else "send_message", fail)
    with pytest.raises(MailNotConfirmed) as raised:
        adapter.send(confirmation_mail(ADVOCATE, "123456"))
    assert "could not be confirmed" in str(raised.value)
    assert "synthetic-AccessToken" not in str(raised.value)
    assert ADVOCATE not in str(raised.value)
    assert sum(event[0] == "connect" for event in observed) == 1


def test_replacing_local_access_token_is_used_on_next_send(transport):
    adapter, _, observed, _ = transport
    adapter.send(confirmation_mail(ADVOCATE, "123456"))
    adapter.token_file.write_text("replacement-AccessToken", encoding="utf8")
    adapter.send(confirmation_mail(ADVOCATE, "654321"))
    assert "replacement-AccessToken" in [event for event in observed if event[0] == "auth"][-1][2]


# ------------------------------------------------------------------ the sender, signing in with an app password (D168) ---

def test_an_app_password_signs_in_over_verified_tls_and_sends_one_message(app_password):
    adapter, gate, observed, _ = app_password
    adapter.send(password_reset_mail(ADVOCATE, "https://nyaymalaw.example/app#reset=synthetic-link"))
    assert gate.calls == [(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)]
    _, host, port, timeout, context = observed[0]
    assert (host, port, timeout) == ("smtp.gmail.com", 465, 10)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    # The spaces Google shows between the groups are not part of the password; no access token is asked for.
    assert observed[1:3] == [("ehlo",), ("login", SENDER, SIGNED_IN_WITH)]
    assert not [event for event in observed if event[0] == "auth"]
    (_, message, sender, to), = [event for event in observed if event[0] == "send"]
    assert (sender, to, message["From"], message["To"]) == (SENDER, [ADVOCATE], SENDER, ADVOCATE)
    assert "reset=synthetic-link" in message.get_content()
    assert SIGNED_IN_WITH not in str(message) and "abcd" not in str(message)


@pytest.mark.parametrize("failure", ["sign-in", "recipient", "timeout"])
def test_an_app_password_failure_says_nothing_of_the_secret_and_is_not_retried(app_password, monkeypatch, caplog, capsys, failure):
    adapter, _, observed, smtp = app_password

    def fail(*args, **kwargs):
        if failure == "sign-in":
            raise smtplib.SMTPAuthenticationError(535, f"{SIGNED_IN_WITH} {ADVOCATE} not accepted".encode())
        if failure == "timeout":
            raise TimeoutError(SIGNED_IN_WITH)
        return {ADVOCATE: (550, SIGNED_IN_WITH.encode())}

    monkeypatch.setattr(smtp, "login" if failure == "sign-in" else "send_message", fail)
    with caplog.at_level(logging.DEBUG), pytest.raises(MailNotConfirmed) as raised:
        adapter.send(confirmation_mail(ADVOCATE, "123456"))
    said = str(raised.value)
    assert said == "Email acceptance could not be confirmed. No automatic retry was sent."
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    printed = capsys.readouterr()
    for secret in (SIGNED_IN_WITH, "abcd efgh"):
        assert secret not in said and secret not in caplog.text and secret not in printed.out + printed.err
    assert ADVOCATE not in said
    assert sum(event[0] == "connect" for event in observed) == 1


@pytest.mark.parametrize("way", ["app password", "access token"])
def test_a_secret_file_saved_with_a_byte_order_mark_is_read_without_it(transport, app_password, way):
    """Some Windows tools (PowerShell 5.1's UTF-8, older Notepad) begin a UTF-8 file with a byte-order mark; it is no part of
    the secret, so the sender still signs in."""
    adapter, _, observed, _ = app_password if way == "app password" else transport
    secret, wanted = ((adapter.password_file, APP_PASSWORD) if way == "app password" else
                      (adapter.token_file, "synthetic-AccessToken"))
    secret.write_bytes(b"\xef\xbb\xbf" + wanted.encode("utf8") + b"\r\n")
    adapter.send(confirmation_mail(ADVOCATE, "123456"))
    if way == "app password":
        assert ("login", SENDER, SIGNED_IN_WITH) in observed
    else:
        assert [event[2] for event in observed if event[0] == "auth"] == [
            "user=sender@example.test\x01auth=Bearer synthetic-AccessToken\x01\x01"]


def test_a_replaced_app_password_is_read_at_the_next_send(app_password):
    adapter, _, observed, _ = app_password
    adapter.send(confirmation_mail(ADVOCATE, "123456"))
    adapter.password_file.write_text("qrst uvwx yzab cdef", encoding="utf8")
    adapter.send(confirmation_mail(ADVOCATE, "654321"))
    assert [event[2] for event in observed if event[0] == "login"] == [SIGNED_IN_WITH, "qrstuvwxyzabcdef"]


@pytest.mark.parametrize("held", ["missing", "empty", "too long", "a control character"])
def test_an_app_password_file_that_holds_no_password_is_refused_before_any_connection(app_password, held):
    adapter, _, observed, _ = app_password
    if held == "missing":
        adapter.password_file.unlink()
    else:
        adapter.password_file.write_text({"empty": "  \n", "too long": "a" * 300,
                                          "a control character": "abcd\x07efgh"}[held], encoding="utf8")
    with pytest.raises(MailNotConfirmed, match="could not be confirmed"):
        adapter.send(confirmation_mail(ADVOCATE, "123456"))
    assert not observed


def test_the_sender_signs_in_one_way_from_an_absolute_file(tmp_path):
    gate, secret = PermittedFixture(), tmp_path / "secret"
    for token, password in ((secret, secret), (None, None), (None, Path("relative-secret"))):
        with pytest.raises(ValueError, match="one absolute local credential-file path"):
            GmailMail(SENDER, token, gate, enabled=True, password_file=password)
    for sender in ("Not An Address", ""):
        with pytest.raises(ValueError):
            GmailMail(sender, None, gate, enabled=True, password_file=secret)


# ------------------------------------------------------------------ the owner's exception, at the composition root ---

def test_configuration_alone_sends_nothing_and_every_other_gate_still_refuses_gmail(tmp_path, smtp):
    observed, _ = smtp
    lines = []
    gate = Gatekeeper(policy=egress_policy(ROOT), audit=lines.append)
    adapter, _, mail_gate = build_mail({"NM_MAIL_PROVIDER": "gmail"}, tmp_path, "unused", gate)
    assert isinstance(adapter, DisabledMail) and mail_gate is gate and adapter.delivers_to_mailbox is False
    with pytest.raises(MailNotConfirmed, match="disabled"):
        adapter.send(confirmation_mail(ADVOCATE, "123456"))
    secret = tmp_path / "app-password"
    secret.write_text(APP_PASSWORD, encoding="utf8")
    build_mail(gmail_settings(secret), tmp_path, "unused", gate)
    # NM's own inventory admits no mail provider: building the owner's exception changed nothing about it.
    with pytest.raises(EgressRefused):
        gate.permit(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)
    assert not observed


def test_the_owners_exception_admits_gmail_for_account_mail_and_for_nothing_else(tmp_path, smtp):
    observed, _ = smtp
    lines = []
    gate = Gatekeeper(policy=egress_policy(ROOT), audit=lines.append)
    secret = tmp_path / "app-password"
    secret.write_text(APP_PASSWORD, encoding="utf8")
    adapter, processor, mail_gate = build_mail(gmail_settings(secret), tmp_path, "unused", gate)
    assert isinstance(adapter, GmailMail) and adapter.delivers_to_mailbox and processor == GMAIL_PROCESSOR
    assert mail_gate is not gate and adapter.gate is mail_gate and mail_gate.policy == gmail_policy()
    (exception,) = mail_gate.policy.processing_exceptions
    assert exception.basis == GMAIL_BASIS == "OWNER-2026-11-10-GLOBAL-GMAIL-ACCOUNT-MAIL"
    assert (exception.processor_id, exception.region, exception.purpose) == (GMAIL_PROCESSOR, "global", Sink.MAIL)
    for classes in (MAIL_CLASSES, (DataClass.OPERATIONAL,), (DataClass.RESTRICTED,)):
        mail_gate.permit(Sink.MAIL, GMAIL_PROCESSOR, classes)
    refused = [((Sink.MAIL, GMAIL_PROCESSOR, (DataClass.CLIENT_MATTER,)), {}),
               ((Sink.MAIL, GMAIL_PROCESSOR, (DataClass.OPERATIONAL, DataClass.CLIENT_MATTER)), {}),
               ((Sink.MAIL, "openai", MAIL_CLASSES), {}),
               ((Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES), {"purpose": Sink.MODEL})]
    refused += [((sink, GMAIL_PROCESSOR, (DataClass.OPERATIONAL,)), {}) for sink in Sink if sink is not Sink.MAIL]
    for args, kwargs in refused:
        with pytest.raises(EgressRefused):
            mail_gate.permit(*args, **kwargs)
    # Both gates write to the one outgoing-data log, in its content-free lines.
    assert any(line.startswith("egress permitted sink=mail processor=gmail-account-mail") for line in lines)
    assert sum(line.startswith("egress REFUSED") for line in lines) == len(refused)
    adapter.send(confirmation_mail(ADVOCATE, "123456"))
    assert ("login", SENDER, SIGNED_IN_WITH) in observed
    assert not any(SIGNED_IN_WITH in line or ADVOCATE in line or "123456" in line for line in lines)


@pytest.mark.parametrize("settings", [
    {"NM_GMAIL_TOKEN_FILE": "{secret}"},           # both ways at once: which one signs in is not guessed
    {"NM_GMAIL_APP_PASSWORD_FILE": ""},            # no way at all
    {"NM_MAIL_SENDER": ""},                        # no sender
    {"NM_GMAIL_APP_PASSWORD_FILE": "relative"},    # not an absolute path
])
def test_gmail_without_one_way_to_sign_in_is_refused_at_start(tmp_path, settings):
    secret = tmp_path / "app-password"
    secret.write_text(APP_PASSWORD, encoding="utf8")
    gate = Gatekeeper(policy=egress_policy(ROOT), audit=None)
    with pytest.raises(ValueError):
        build_mail(gmail_settings(secret, **{name: value.format(secret=secret) for name, value in settings.items()}),
                   tmp_path, "unused", gate)


# ------------------------------------------------------------------ the served application ---

@pytest.fixture
def served_with_gmail(tmp_path, smtp, monkeypatch):
    from nm.app import api
    from nm.app.composition import Application
    from nm.app.main import create_app
    from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
    from nm.arrive.store_directory import FileDirectory
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_turn import ScriptedModel, searcher

    secret = tmp_path / "app-password"
    secret.write_text(APP_PASSWORD, encoding="utf8")
    directory = FileDirectory(tmp_path, key=KEY)
    directory.enrol(Enrolment(AdvocateIdentity(ADVOCATE, "Advocate", email=ADVOCATE), enrol("Synthetic-password-48!")))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=ROOT, model=model, store=FileMatterStore(tmp_path, key=KEY), directory=directory,
                      legal_search=searcher(), audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                          **gmail_settings(secret, NM_PUBLIC_URL="https://nyaymalaw.example",
                                           NM_PUBLIC_REGISTRATION="enabled")})
    monkeypatch.setattr(api, "_application", app)
    client = TestClient(create_app(app), headers={"origin": "http://testserver"})
    yield app, client, smtp[0], smtp[1]
    client.close()


def logged(app):
    return "".join(path.read_text(encoding="utf8") for path in sorted(Path(app.audit_root).glob("egress*.log")))


def test_the_served_application_sends_a_reset_link_through_gmail_and_opens_public_sign_up(served_with_gmail):
    app, client, observed, _ = served_with_gmail
    assert app.mail.delivers_to_mailbox is True
    capabilities = client.get("/api/account-capabilities").json()
    assert capabilities["public_registration"] is True and capabilities["mail_delivery"] == "mailbox"
    assert client.post("/api/password/forgot", json={"email": ADVOCATE}).status_code == 202
    assert ("login", SENDER, SIGNED_IN_WITH) in observed
    (_, message, _, to), = [event for event in observed if event[0] == "send"]
    assert to == [ADVOCATE] and "https://nyaymalaw.example/app#reset=" in message.get_content()
    log = logged(app)
    assert "egress permitted sink=mail processor=gmail-account-mail purpose=mail" in log
    assert SIGNED_IN_WITH not in log and ADVOCATE not in log and "#reset=" not in log


def test_a_send_gmail_did_not_confirm_is_said_as_not_delivered_and_never_as_a_programming_error(served_with_gmail, monkeypatch,
                                                                                             caplog):
    from nm.app import api

    app, client, observed, smtp = served_with_gmail

    def refused(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(smtp, "login", refused)
    with caplog.at_level(logging.ERROR, logger="nm.account_mail"):
        assert client.post("/api/password/forgot", json={"email": ADVOCATE}).status_code == 202
    assert "password reset link not delivered: MailNotConfirmed" in caplog.text
    assert "programming error" not in caplog.text and SIGNED_IN_WITH not in caplog.text
    # The admin's "send a reset link" says the same, rather than failing (plan AN.46).
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b"",
                       "scheme": "https", "server": ("nyaymalaw.example", 443), "root_path": ""})
    assert api._send_reset_link_for_an_admin(ADVOCATE, request, datetime.now(timezone.utc)) == "not-delivered"
    assert not [event for event in observed if event[0] == "send"]
