"""Offline SMTP contract tests; every socket is replaced, never a real send."""

import smtplib
import ssl

import pytest
from nm.adapters.mail.gmail import GMAIL_PROCESSOR, GmailMail
from nm.bootstrap.composition import build_mail
from nm.bootstrap.egress_policy import egress_policy
from nm.domain.egress import Gatekeeper
from nm.domain.mail import confirmation_mail

pytestmark = pytest.mark.class_a


class PermittedFixture:
    def __init__(self):
        self.calls = []

    def permit(self, *args):
        self.calls.append(args)


@pytest.fixture
def transport(tmp_path, monkeypatch):
    token = tmp_path / "synthetic-token"
    token.write_text("synthetic-AccessToken", encoding="utf8")
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

        def send_message(self, message, *, from_addr, to_addrs):
            observed.append(("send", message, from_addr, to_addrs))
            return {}

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    gate = PermittedFixture()
    adapter = GmailMail("sender@example.test", token, gate, enabled=True)
    return adapter, gate, observed, FakeSMTP


def test_gmail_is_disabled_before_secret_access_or_network(transport):
    adapter, gate, observed, _ = transport
    adapter.token_file.unlink()
    disabled = GmailMail(adapter.sender, adapter.token_file, gate)
    with pytest.raises(RuntimeError, match="disabled"):
        disabled.send(confirmation_mail("recipient@example.test", "123456"))
    assert not observed and not gate.calls
    assert disabled.delivers_to_mailbox is False


def test_account_mail_uses_verified_tls_single_recipient_and_oauth(transport):
    adapter, gate, observed, _ = transport
    adapter.send(confirmation_mail("recipient@example.test", "123456"))
    assert len(gate.calls) == 1 and gate.calls[0][1] == GMAIL_PROCESSOR
    _, host, port, timeout, context = observed[0]
    assert (host, port, timeout) == ("smtp.gmail.com", 465, 10)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert observed[2][1] == "XOAUTH2"
    assert observed[2][2] == "user=sender@example.test\x01auth=Bearer synthetic-AccessToken\x01\x01"
    assert observed[2][3] == ""
    assert observed[3][3] == ["recipient@example.test"]
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
        return {"recipient@example.test": (550, b"synthetic-AccessToken")}

    monkeypatch.setattr(smtp, "auth" if failure == "authentication" else "send_message", fail)
    with pytest.raises(RuntimeError) as raised:
        adapter.send(confirmation_mail("recipient@example.test", "123456"))
    assert "could not be confirmed" in str(raised.value)
    assert "synthetic-AccessToken" not in str(raised.value)
    assert "recipient@example.test" not in str(raised.value)
    assert sum(event[0] == "connect" for event in observed) == 1


def test_replacing_local_access_token_is_used_on_next_send(transport):
    adapter, _, observed, _ = transport
    adapter.send(confirmation_mail("recipient@example.test", "123456"))
    adapter.token_file.write_text("replacement-AccessToken", encoding="utf8")
    adapter.send(confirmation_mail("recipient@example.test", "654321"))
    assert "replacement-AccessToken" in [event for event in observed if event[0] == "auth"][-1][2]


def test_composition_does_not_treat_configuration_as_processor_approval(tmp_path, transport):
    from pathlib import Path

    from nm.domain.egress import EgressRefused

    _, _, observed, _ = transport
    gate = Gatekeeper(
        policy=egress_policy(Path(__file__).resolve().parents[1]), audit=lambda _: None
    )
    adapter, _ = build_mail({"NM_MAIL_PROVIDER": "gmail"}, tmp_path, "unused", gate)
    assert adapter.delivers_to_mailbox is False
    with pytest.raises(RuntimeError, match="disabled"):
        adapter.send(confirmation_mail("recipient@example.test", "123456"))
    with pytest.raises(EgressRefused):
        build_mail(
            {"NM_MAIL_PROVIDER": "gmail", "NM_MAIL_DELIVERY": "enabled"}, tmp_path, "unused", gate
        )
    assert not observed
