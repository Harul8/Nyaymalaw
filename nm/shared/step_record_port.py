"""Content-free records of the steps a server has taken, for its next start (plan AN.48, piece 48f3; owner decision D167)."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class StepRecordPort(Protocol):
    def taken(self, advocate_id: str, turn_id: str, *, route: str, chat_id: str | None = None, choice: str | None = None,
              disputes: list | None = None, session: str | None = None) -> None:
        """A step taken by the server, not yet begun: whose, which turn and conversation, which route, a go-ahead's choice and
        disputes, and the sign-in it was asked under by its fingerprint. Never fails its step."""
        ...

    def begun(self, advocate_id: str, turn_id: str) -> None:
        """The step has begun."""
        ...

    def ended(self, advocate_id: str, turn_id: str) -> None:
        """The step has ended, or was stopped before it began: its record goes."""
        ...

    def left(self) -> list:
        """At the server's start: every step an earlier run of it took and did not end, with when each was taken."""
        ...


@runtime_checkable
class StepRecordSweepPort(Protocol):
    """The step records' retention (plan AN.53, D241: 90 days, with the turns' attempts), a narrow port of its own that only the
    daily sweep is given."""

    def sweep(self, before) -> int:
        """Remove the records of steps taken before `before`; how many."""
        ...
