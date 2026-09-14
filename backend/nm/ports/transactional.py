"""Persisting the matter, the accepted command and the owed work TOGETHER.

    from nm.ports.transactional import TransactionalStorePort

WHY THIS IS A SEPARATE PORT
-----------------------------
`StorePort` says how a matter is loaded and committed, and every adapter and
test in the product satisfies it. Adding three methods there would change what
thirty-one call sites are required to provide, for a capability only two
adapters have -- and `backend/nm/adapters/policed_port.py` derives its gated
population from the Protocol, so a method added to `StorePort` also becomes a
new policed route for every store.

So this is the narrower contract that a TRANSACTIONAL store satisfies as well.
The file store does not, and says so by not declaring it, which is the honest
answer: it can write a matter atomically and it cannot write three records
atomically.

THE ONE PROMISE
-----------------
`commit_accepted` either persists ALL of the matter version, the operation and
the outbox entries, or none of them. There is no partial application, and no
ordering in which a caller can observe one without the others. An outbox row
without its matter version is work owed for a state that does not exist; a
matter version without its outbox row is work silently dropped.

WHY THE VERSION IS STILL CONDITIONAL
--------------------------------------
For the reason `StorePort.commit` already gives: two turns interleaving on one
derivation graph would compute both answers from a state neither of them saw.
A transaction makes the write atomic; it does not make it correct.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from nm.domain.matter import Matter
from nm.domain.operation import Operation, OutboxEntry, Outcome


class TenantMismatch(Exception):
    """A read or write crossed a workspace boundary.

    DISTINCT FROM AN EMPTY RESULT, deliberately. A query that returns nothing
    because the row belongs to another tenant and a query that returns nothing
    because there is no such row are different facts, and reporting the first
    as the second is the absent-reads-as-success shape holding another firm's
    matter.
    """


class OperationConflict(Exception):
    """One idempotency key was used for two different requests.

    Not a replay. A replay returns the original answer; this is a caller
    asking a new question under an old name, and answering it with the old
    result would answer a question nobody asked.
    """


class LeaseLost(Exception):
    """This claim no longer owns the work; it cannot renew or settle it."""


@runtime_checkable
class TransactionalStorePort(Protocol):
    """A store that can commit state, acceptance and owed work at once."""

    def commit_accepted(self, matter: Matter, *, expected_version: int,
                        operation: Operation,
                        outbox: tuple[OutboxEntry, ...] = ()) -> Matter:
        """All three, or none. Raises `StaleWrite` if the matter moved."""
        ...

    def operation(self, workspace_id: str,
                  idempotency_key: str) -> Operation | None:
        """The accepted command under this key, for THIS workspace.

        Scoped by workspace because an idempotency key is chosen by a client
        and two firms may choose the same one. A global lookup would hand one
        firm the other's result.
        """
        ...

    def claim_outbox(self, workspace_id: str, *, worker: str,
                     lease_seconds: int,
                     limit: int = 1, reconcile: bool = False) -> tuple[OutboxEntry, ...]:
        """Take a lease on work nobody else holds. P11 drives this."""
        ...

    def renew_outbox(self, workspace_id: str, entry: OutboxEntry,
                     *, lease_seconds: int) -> None:
        """Renew the current unexpired fenced claim, or raise LeaseLost."""
        ...

    def record_job_outcome(self, workspace_id: str, entry: OutboxEntry,
                           *, outcome: Outcome, detail: str) -> None:
        """Durably settle this fenced claim and derive its operation's outcome."""
        ...

    def request_cancellation(self, workspace_id: str, idempotency_key: str) -> Operation | None:
        """Retain the cancellation request; accepted work and results are not erased."""
        ...
