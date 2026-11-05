"""Content-free durable ownership of one request and its correction allowance."""
from typing import Protocol, runtime_checkable


class AttemptRefused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@runtime_checkable
class TurnAttemptPort(Protocol):
    def claim(self, identity: str, request_digest: str) -> dict:
        """Return token/corrections_used (a count), or refuse ambiguous or terminal ownership."""
        ...

    def consume_correction(self, identity: str, token: str) -> None:
        """Persist one correction of the allowance before any corrective provider dispatch;
        refused once the allowance is spent."""
        ...

    def finish(self, identity: str, token: str, state: str, code: str | None = None) -> None:
        """Monotonic terminal/finished/unconfirmed, or retryable with allowance retained."""
        ...

    def release_ended(self, code: str = "interrupted") -> int:
        """At the server's start (plan AN.41, D73): each claim still running, left by an earlier run of the server, made
        retryable with its allowance retained. Returns how many."""
        ...
