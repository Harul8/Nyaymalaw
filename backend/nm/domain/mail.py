"""Account mail: what the product writes to an advocate's email address.
Implementation Plan F-A-03.

    from nm.domain.mail import MailMessage, password_reset_mail

ONE OWNER FOR THE WORDS
-------------------------
Account confirmation and password-reset messages have their subject and text
composed here, once, and the edge hands the result to the mail port. A
route that wrote its own sentence would be a second owner of the promise the
message makes -- how long the link lasts and what using it does -- and the two
would drift the first time the lifetime changed.

WHAT A MESSAGE MAY CARRY
--------------------------
An email address, a subject and plain text. Never client matter material: the
mail sink is admitted for operational and restricted data only, and a reset
message has no reason to name a matter. `purpose` is a short content-free label
for the audit line, so an operator can see that a reset message was queued
without the log ever holding the link.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.advocate import PASSWORD_RESET_MINUTES, registration_email
from nm.domain.text import blank


@dataclass(frozen=True)
class MailMessage:
    """One message for one address. Plain text; no attachments, no HTML."""

    to: str
    subject: str
    text: str
    purpose: str

    def __post_init__(self) -> None:
        if registration_email(self.to) != self.to:
            raise ValueError("account mail needs one canonical email address")
        for name in ("subject", "text", "purpose"):
            if blank(getattr(self, name)):
                raise ValueError(f"account mail with no {name} says nothing")
        if any(mark in self.subject for mark in ("\r", "\n")):
            raise ValueError("a mail subject must fit on one header line")


PASSWORD_RESET_PURPOSE = "password-reset"


def confirmation_mail(to: str, code: str) -> MailMessage:
    from nm.domain.account_confirmation import CODE_MINUTES
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ValueError('confirmation needs six digits')
    return MailMessage(to=to, subject='Confirm your Nyaymalaw email',
                       text=f'Your Nyaymalaw confirmation code is {code}. '
                            f'It expires after {CODE_MINUTES} minutes and works once. '
                            'If you did not begin registration, do not share this code. '
                            'Confirm only after choosing your own password.',
                       purpose='email-confirmation')


def password_reset_mail(to: str, link: str,
                        minutes: int = PASSWORD_RESET_MINUTES) -> MailMessage:
    """The reset message. States the lifetime, the single use and the effect."""
    if blank(link) or any(mark in link for mark in ("\r", "\n", " ")):
        raise ValueError("a reset link must be one unbroken URL")
    return MailMessage(
        to=to,
        subject="Reset your Nyaymalaw password",
        text=(
            f"Someone asked to reset the password for the Nyaymalaw account "
            f"{to}.\n\n"
            f"To choose a new password, open this link within {minutes} minutes:\n\n"
            f"{link}\n\n"
            "The link works once. Setting a new password signs this account out "
            "on every device.\n\n"
            "If you did not ask for this, ignore this email. Your password has "
            "not changed.\n"),
        purpose=PASSWORD_RESET_PURPOSE,
    )
