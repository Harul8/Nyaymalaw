"""Gmail account-mail transport (plan AN.48, owner decision D168, 10 Nov 2026: Gmail sends NM's account mail).

SMTP over certificate-verified TLS to smtp.gmail.com. The sender signs in with a Google app password, or with an OAuth access token
for a setup that keeps one fresh; either is supplied through a local secret file, re-read for each send and never copied to the
project, a log or an error. Whether Gmail may be sent anything at all is the gate's to say, before any secret is read; the owner's
exception that admits it for account mail is built at the composition root (nm/app/composition.py, gmail_policy).
No automatic retries: a lost SMTP acknowledgement is an uncertain send. Provider acceptance is not proof of inbox delivery.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

from nm.arrive.advocate_contracts import registration_email
from nm.arrive.mail_contracts import MailMessage
from nm.arrive.mail_port import MailNotConfirmed
from nm.shared.egress_contracts import DataClass, Gatekeeper, Sink

GMAIL_PROCESSOR = 'gmail-account-mail'
MAIL_CLASSES = (DataClass.OPERATIONAL, DataClass.RESTRICTED)


@dataclass(frozen=True)
class GmailMail:
    sender: str
    #: An OAuth access token's file: the sender signs in with XOAUTH2. Nothing here refreshes the token.
    token_file: Path | None = field(repr=False)
    gate: Gatekeeper = field(repr=False)
    enabled: bool = False
    #: A Google app password's file (D168): the sender signs in with its address and the app password instead.
    password_file: Path | None = field(default=None, repr=False)

    def __post_init__(self):
        if registration_email(self.sender) != self.sender:
            raise ValueError('Gmail needs one canonical sender address.')
        given = [path for path in (self.token_file, self.password_file) if path is not None]
        if len(given) != 1 or not isinstance(given[0], Path) or not given[0].is_absolute():
            raise ValueError('Gmail needs one absolute local credential-file path: an app password or an access token.')

    @property
    def delivers_to_mailbox(self) -> bool:
        return self.enabled

    def send(self, message: MailMessage) -> None:
        if not self.enabled:
            raise MailNotConfirmed('Real email delivery is disabled. No message was sent.')
        # The same policy decision used elsewhere in NM, before even reading
        # credentials. Direct use of this adapter cannot evade the boundary.
        self.gate.permit(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)
        if not isinstance(message, MailMessage) or message.purpose not in {
                'password-reset', 'email-confirmation'}:
            raise ValueError('This channel accepts account confirmation and reset messages only.')
        try:
            secret = self._secret()
            message_body = EmailMessage()
            message_body['From'] = self.sender
            message_body['To'] = message.to
            message_body['Subject'] = message.subject
            message_body.set_content(message.text)
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10, context=context) as smtp:
                smtp.ehlo()
                if self.password_file is not None:
                    smtp.login(self.sender, secret)
                else:
                    response = f'user={self.sender}\x01auth=Bearer {secret}\x01\x01'
                    smtp.auth('XOAUTH2', lambda challenge=None: response if challenge is None else '')
                refused = smtp.send_message(message_body, from_addr=self.sender,
                                            to_addrs=[message.to])
                if refused:
                    raise RuntimeError('recipient was refused')
        except (OSError, UnicodeError, ValueError, smtplib.SMTPException, RuntimeError):
            # Provider exceptions can contain addresses, tokens and response
            # bodies. None belongs in the served error or chained traceback.
            raise MailNotConfirmed('Email acceptance could not be confirmed. '
                                   'No automatic retry was sent.') from None

    def _secret(self) -> str:
        """The secret as its file holds it now. Bounded, so a mistaken path cannot load a large file."""
        if self.password_file is not None:
            with self.password_file.open('r', encoding='utf8') as source:
                text = source.read(257)
            # Google shows an app password in groups of four letters; the spaces between them are not part of it.
            password = ''.join(text.split())
            if not password or len(text) > 256 or any(not 33 <= ord(c) <= 126 for c in password):
                raise ValueError('invalid credential')
            return password
        with self.token_file.open('r', encoding='utf8') as source:
            token = source.read(8193).strip()
        if not token or len(token) > 8192 or any(c.isspace() or ord(c) < 32 for c in token):
            raise ValueError('invalid credential')
        return token


class DisabledMail:
    delivers_to_mailbox = False
    delivery_mode = 'disabled'

    def send(self, message: MailMessage) -> None:
        raise MailNotConfirmed('Real email delivery is disabled. No message was queued.')
