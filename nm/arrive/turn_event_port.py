"""One content-free line when a turn ends (plan AN.46, piece 46h; owner decision D120, 7 Nov 2026: "Yes add it").

WHAT THE LINE HOLDS. Which account (by the digest the usage store names it by), when the turn started and ended, how many seconds it
took, how it ended, the model and the effort the advocate chose for it, how many model calls it made, what they cost, and how many
documents were sent with it - a number. NO conversation or matter identity, no turn identity, no word of the message, the answer or
a file: the line cannot say what a turn was about, only that one happened and how it went. Nothing but the Admin area reads it.

HOW IT ENDED. `answered`: an answer was saved. `stopped`: the advocate stopped it. `refused`: it was refused before it could be
answered (a sign-in that ended, AI sharing off, an earlier answer still being worked on, a document it could not use). `failed`: it
stopped for a reason on NM's side or the AI service's. Reopening a saved answer is not a turn and leaves no line.

WRITING IT MUST NEVER COST A TURN. The caller catches `TurnEventRefused`, logs a diagnosis without private data, and goes on: an
unwritable record loses one line, and never fails, delays or changes an answer.
"""
from __future__ import annotations

from typing import Protocol

#: What a record is given, in this order (the seconds a turn took are worked out from its two times); `calls` and `micro_usd` may be
#: None where the turn did not establish them.
EVENT_FIELDS = ("started_at", "ended_at", "outcome", "model", "effort", "calls", "micro_usd", "documents")
OUTCOMES = ("answered", "stopped", "refused", "failed")


class TurnEventRefused(Exception):
    """The turn record could not be read or written. Never a reason to fail the turn it describes."""


class TurnEventPort(Protocol):
    def record(self, account_id: str, event: dict) -> None:
        """Keep one line, with exactly EVENT_FIELDS."""
        ...


class TurnRecordSweepPort(Protocol):
    """The turn record's retention (plan AN.53, D241: the counts and timings of turns are kept two years), a narrow port of its own
    that only the daily sweep is given: the turn path's port can still only add a line."""

    def sweep(self, before) -> int:
        """Remove the lines of turns that ended before `before`; how many."""
        ...
