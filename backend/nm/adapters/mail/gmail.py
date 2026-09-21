"""Gmail account-mail transport, disabled until separately authorised.

SMTP over certificate-verified TLS; OAuth access tokens are supplied through a
local secret file and re-read for each send (never copied to the project or log).
No automatic retries: a lost SMTP acknowledgement is an uncertain send.
Provider acceptance is not proof of inbox delivery.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

from nm.domain.advocate import registration_email
from nm.domain.egress import DataClass, Gatekeeper, Sink
from nm.domain.mail import MailMessage

GMAIL_PROCESSOR = 'gmail-account-mail'
MAIL_CLASSES = (DataClass.OPERATIONAL, DataClass.RESTRICTED)


@dataclass(frozen=True)
class GmailMail:
    sender: str
    token_file: Path = field(repr=False)
    gate: Gatekeeper = field(repr=False)
    enabled: bool = False

    def __post_init__(self):
        if registration_email(self.sender) != self.sender:
            raise ValueError('Gmail needs one canonical sender address.')
        if not isinstance(self.token_file, Path) or not self.token_file.is_absolute():
            raise ValueError('Gmail needs an absolute local credential-file path.')

    @property
    def delivers_to_mailbox(self) -> bool:
        return self.enabled

    def send(self, message: MailMessage) -> None:
        if not self.enabled:
            raise RuntimeError('Real email delivery is disabled. No message was sent.')
        # The same policy decision used elsewhere in NM, before even reading
        # credentials. Direct use of this adapter cannot evade the boundary.
        self.gate.permit(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)
        if not isinstance(message, MailMessage) or message.purpose not in {
                'password-reset', 'email-confirmation'}:
            raise ValueError('This channel accepts account confirmation and reset messages only.')
        try:
            # Bound input; a mistaken path must not load an arbitrary large file.
            with self.token_file.open('r', encoding='utf8') as source:
                token = source.read(8193).strip()
            if not token or len(token) > 8192 or any(c.isspace() or ord(c) < 32 for c in token):
                raise ValueError('invalid credential')
            message_body = EmailMessage()
            message_body['From'] = self.sender
            message_body['To'] = message.to
            message_body['Subject'] = message.subject
            message_body.set_content(message.text)
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10, context=context) as smtp:
                smtp.ehlo()
                response = f'user={self.sender}\x01auth=Bearer {token}\x01\x01'
                smtp.auth('XOAUTH2', lambda challenge=None: response if challenge is None else '')
                refused = smtp.send_message(message_body, from_addr=self.sender,
                                            to_addrs=[message.to])
                if refused:
                    raise RuntimeError('recipient was refused')
        except (OSError, UnicodeError, ValueError, smtplib.SMTPException, RuntimeError):
            # Provider exceptions can contain addresses, tokens and response
            # bodies. None belongs in the served error or chained traceback.
            raise RuntimeError('Email acceptance could not be confirmed. '
                               'No automatic retry was sent.') from None


class DisabledMail:
    delivers_to_mailbox = False
    delivery_mode = 'disabled'

    def send(self, message: MailMessage) -> None:
        raise RuntimeError('Real email delivery is disabled. No message was queued.')
