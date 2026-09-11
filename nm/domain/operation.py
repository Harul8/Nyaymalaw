"""An accepted command, and the work it owes. BK-36-AC1, BK-83-AC1. P10.

    from nm.domain.operation import Operation, Outcome, OutboxEntry

WHY AN OPERATION EXISTS AT ALL
--------------------------------
Because the advocate's client dropped the connection and they pressed the
button again. Without a record of what was accepted, the second press is a
second matter, a second turn and a second charge, and nothing in the product
can tell that it was the same intention arriving twice.

So an accepted command is a RECORD, keyed by something the caller chose before
it sent anything -- an idempotency key -- and replaying that key returns the
ORIGINAL result rather than doing the work again.

THE STATES ARE FIVE AND THE FIFTH IS THE POINT
------------------------------------------------
`UNKNOWN` is not a failure and it is not a success: it is what an operation is
when an external effect may or may not have happened -- the worker died
between calling out and writing down that it had. A model that has only
`succeeded` and `failed` forces that case into one of them, and both answers
are wrong in a way that costs money or duplicates an effect.

An `UNKNOWN` operation is RECONCILED, never retried. That is the whole reason
the value exists, so `retryable()` refuses it by construction rather than by a
caller remembering.

WHAT IS NOT HERE
------------------
Any notion of WHERE this is stored. An operation is a fact about a command, and
the same fact holds whether it lands in a file, in PostgreSQL or in a test
double. `nm/ports/transactional.py` says how it is persisted.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from nm.domain.advocate import utcnow
from nm.domain.text import refuses_blank_text


class Outcome(str, Enum):
    """What became of an accepted command."""

    ACCEPTED = "accepted"
    """Recorded and owed. Nothing has been attempted yet."""
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    """A cancellation was asked for. NOT a cancellation: work already accepted
    is not erased by asking, and the request is recorded so the difference
    between *asked* and *happened* survives."""
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    """AN EXTERNAL EFFECT MAY OR MAY NOT HAVE HAPPENED.

    The third state, at the one place it is most expensive to collapse. A
    worker that called a provider and died before recording the answer is
    neither done nor undone, and treating it as either duplicates a charge or
    loses the work. It is reconciled against the destination and never retried
    blind."""

    @classmethod
    def not_established(cls) -> "Outcome":
        return cls.UNKNOWN

    def settled(self) -> bool:
        """Whether anything more is owed. UNKNOWN is NOT settled."""
        return self in (Outcome.COMPLETED, Outcome.FAILED)

    def retryable(self) -> bool:
        """Whether a worker may simply run this again.

        UNKNOWN IS REFUSED HERE, BY CONSTRUCTION. *Ambiguous external-effect
        outcomes must reconcile before retry* is a rule that a call site can
        forget; a method that answers False cannot be forgotten.
        """
        return self in (Outcome.ACCEPTED, Outcome.RUNNING)


@refuses_blank_text()
@dataclass(frozen=True)
class Operation:
    """One accepted command, by the key its caller chose."""

    #: CHOSEN BY THE CALLER, BEFORE IT SENT ANYTHING. A key the server mints
    #: cannot identify a retry, because the retry never saw it.
    idempotency_key: str
    workspace_id: str
    advocate_id: str
    command: str
    outcome: Outcome = Outcome.ACCEPTED
    matter_id: str = ""
    """Empty on an OPENING command, where no matter exists yet. That case is
    exactly the one idempotency has to cover and the one it usually misses:
    replaying it must return the matter that was minted, not mint a second."""
    matter_version: int = 0
    #: The answer the first attempt produced, returned verbatim on replay so a
    #: lost response cannot become a second unit of work.
    result: dict = field(default_factory=dict)
    request_digest: str = ""
    at: str = ""

    def replaying(self, command: str, request_digest: str) -> bool:
        """Whether a new arrival is this same operation coming back.

        THE DIGEST IS PART OF THE ANSWER. A caller that reuses one key for a
        DIFFERENT request has made a mistake, and returning the first result
        would answer a question it never asked. That is a conflict, not a
        replay, and `same_key_different_request` names it.
        """
        return (self.command == command
                and self.request_digest == request_digest)

    def same_key_different_request(self, command: str,
                                   request_digest: str) -> bool:
        return not self.replaying(command, request_digest)


def request_digest(payload: object) -> str:
    """A stable fingerprint of what was asked, never the content itself.

    Stored beside the key so a reused key carrying a different request is
    caught. It is a digest rather than the payload because an operation record
    is read by operators and must not hold the advocate's words.
    """
    return hashlib.sha256(repr(payload).encode("utf8")).hexdigest()


@refuses_blank_text()
@dataclass(frozen=True)
class OutboxEntry:
    """Work owed to something outside this transaction.

    WHY AN OUTBOX AND NOT A CALL. Because a provider call inside a database
    transaction holds the row locks for the length of a network round trip,
    and because a call that succeeds while the transaction rolls back has
    happened in the world and not in the record. So the intention is COMMITTED
    WITH the state change, atomically, and a worker publishes it afterwards.
    """

    entry_id: str
    workspace_id: str
    operation_key: str
    kind: str
    matter_id: str = ""
    #: What the worker needs, carrying no client words. The turn's material
    #: stays in the sealed matter; this says which matter and which version.
    payload: dict = field(default_factory=dict)
    matter_version: int = 0
    attempts: int = 0
    at: str = ""


class OutboxRefused(RuntimeError):
    """The entry contradicts the state it was committed with."""


def refuse_outbox(entry: OutboxEntry, *, workspace_id: str,
                  operation: Operation) -> list[str]:
    """Why this entry must not be committed with this operation.

    ONE FUNCTION, EVERY ADAPTER. The file store and the PostgreSQL adapter
    must not each decide what a consistent outbox row is, or the two stores
    disagree about the same record -- which is the three-stores defect with a
    schema.
    """
    bad: list[str] = []
    if entry.workspace_id != workspace_id:
        bad.append(
            f"outbox entry {entry.entry_id!r} is for workspace "
            f"{entry.workspace_id!r} and the operation is in {workspace_id!r}")
    if entry.operation_key != operation.idempotency_key:
        bad.append(
            f"outbox entry {entry.entry_id!r} names operation "
            f"{entry.operation_key!r} and is being committed with "
            f"{operation.idempotency_key!r}")
    if entry.matter_id and operation.matter_id and \
            entry.matter_id != operation.matter_id:
        bad.append(
            f"outbox entry {entry.entry_id!r} is about matter "
            f"{entry.matter_id!r} and the operation is about "
            f"{operation.matter_id!r}")
    return bad


def now_text(at: datetime | None = None) -> str:
    return (at or utcnow()).isoformat(timespec="seconds")
