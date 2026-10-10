"""Content-free durable ownership of one request and its correction allowance."""
from typing import Protocol, runtime_checkable


class AttemptRefused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@runtime_checkable
class TurnAttemptPort(Protocol):
    def claim(self, identity: str, request_digest: str) -> dict:
        """Return token/correction_used, or refuse ambiguous or terminal ownership."""
        ...

    def consume_correction(self, identity: str, token: str) -> None:
        """Persist the one allowance before any corrective provider dispatch."""
        ...

    def finish(self, identity: str, token: str, state: str, code: str | None = None) -> None:
        """Monotonic terminal/finished/unconfirmed, or retryable with allowance retained."""
        ...
