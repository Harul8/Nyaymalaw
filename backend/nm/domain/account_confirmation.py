"""Mailbox proof is bounded account activation, never professional approval."""
from dataclasses import dataclass

CODE_MINUTES = 15
CODE_ATTEMPTS = 5
RESEND_SECONDS = 60
REQUESTS_PER_HOUR = 5
PENDING_HOURS = 24


@dataclass
class ConfirmationRefused(ValueError):
    message: str
    retry_after: int = 0

    def __str__(self) -> str:
        return self.message


REFUSED = 'That confirmation is not valid or has expired. Request a code or register again.'
