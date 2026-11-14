"""Content-free durable ownership of one request and its correction allowance."""
from typing import Protocol, runtime_checkable


class AttemptRefused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@runtime_checkable
class TurnAttemptPort(Protocol):
    def claim(self, identity: str, request_digest: str, *, unsaved: bool = False) -> dict:
        """Return token/corrections_used (a count), or refuse ambiguous or terminal ownership. unsaved (plan AN.50, D188): the
        caller has read the conversation and found no answer saved for this request, so an attempt left unconfirmed is settled
        as retryable and claimed."""
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


class TurnAttemptSweepPort(Protocol):
    """The attempts' retention (plan AN.53, D241: 90 days after a turn finished or stopped), a narrow port of its own that only
    the daily sweep is given: the turn path's port claims, corrects and finishes, and removes nothing."""

    def sweep(self, before) -> int:
        """Remove the attempts that ended before `before`, never one still running; how many."""
        ...
