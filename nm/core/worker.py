"""Doing owed work exactly once, or saying you cannot tell. BK-83-AC2. P11.

    runner = JobRunner(store=..., effects=..., permits=..., clock=...)
    runner.run_once(workspace_id="ws_a", worker="w1")

WHAT A WORKER OWES
--------------------
An outbox entry is a promise the product made inside a transaction: *this
matter moved, and something outside owes work because of it*. The worker's job
is to keep that promise once -- and, where it cannot know whether it kept it,
to say so rather than guess.

THE FOUR THINGS THAT MAKE THIS HARD, EACH WITH ITS ANSWER
-----------------------------------------------------------
1. TWO WORKERS TAKE THE SAME JOB. Answered by the lease: a claim is a write,
   and a claim nobody else holds is the only kind there is. `claim_outbox`
   owns that; this module never decides it is allowed to run something.

2. THE WORKER DIES MID-JOB. Answered by lease EXPIRY -- the job becomes
   claimable again -- and by where it died. Before the effect, a retry is
   free. After the effect and before recording it, a retry is a DUPLICATE, so
   the effect record is written with an idempotency key the sink honours and
   the outcome of an unacknowledged effect is `UNKNOWN`.

3. THE ANSWER IS AMBIGUOUS. Answered by refusing to answer: `Outcome.UNKNOWN`
   is not a failure and not a success, and `Outcome.retryable()` returns False
   for it by construction. Reconciliation asks the SINK what it already has;
   only then does the job move.

4. PERMISSION CHANGED WHILE THE JOB WAITED. Answered by rechecking before
   reading and again before publishing. A job accepted while an advocate was a
   member of the workspace must not publish after they were removed, and the
   gap between claim and publish is exactly where that happens.

WHAT IS NOT CLAIMED
---------------------
EXACTLY-ONCE EXTERNAL DELIVERY. It does not exist over a network nobody
controls. What is claimed is: at-least-once delivery, an idempotency key the
sink can use to collapse duplicates, and an explicit `UNKNOWN` whenever this
process cannot establish which happened. Anything stronger would be a promise
about somebody else's system.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from nm.domain.operation import OutboxEntry, Outcome
from nm.domain.text import refuses_blank_text

#: How many times a job may be attempted before it stops being retried and
#: starts being a thing somebody looks at. A budget rather than forever: a job
#: that fails identically two hundred times is not going to succeed on the
#: two hundred and first, and the retries hide it.
DEFAULT_RETRY_BUDGET = 5


class EffectSink(Protocol):
    """Something outside this process that the work is owed to.

    `deliver` MUST take the idempotency key and MUST be able to answer
    `already_delivered`. A sink that cannot say what it already has turns
    every ambiguous outcome into a permanent UNKNOWN, which is honest and
    useless -- so the port requires it and a sink that cannot is a sink this
    product does not use.
    """

    def deliver(self, entry: OutboxEntry, *, idempotency_key: str) -> dict: ...

    def already_delivered(self, idempotency_key: str) -> bool: ...


class Permits(Protocol):
    """Whether this advocate may still act on this matter, ASKED NOW."""

    def may_publish(self, workspace_id: str, advocate_id: str,
                    matter_id: str) -> bool: ...


@refuses_blank_text()
@dataclass(frozen=True)
class JobResult:
    """What happened to one job. THE OUTCOME IS NEVER GUESSED."""

    entry_id: str
    outcome: Outcome
    detail: str = ""
    attempts: int = 0

    def reconcilable(self) -> bool:
        return self.outcome is Outcome.UNKNOWN


class Cancelled(RuntimeError):
    """A cancellation was requested before the effect happened.

    NOT an erasure. Work already done is not undone by asking, and a
    cancellation that arrives after the effect is recorded as a cancellation
    REQUEST against a completed job rather than as a completed cancellation.
    """


@dataclass
class JobRunner:
    """One pass over the owed work. Stateless between runs, deliberately.

    Every fact it needs is in the store, so a restarted worker is
    indistinguishable from a running one -- which is the property that makes
    "crash and restart" a test rather than a hope.
    """

    store: Any
    effects: EffectSink
    permits: Permits
    #: Asked, never taken from a clock inside a branch. CLAUDE.md's rule about
    #: the machine's idea of the date applies to lease arithmetic too.
    clock: Callable[[], float] = time.monotonic
    retry_budget: int = DEFAULT_RETRY_BUDGET
    lease_seconds: int = 30
    #: Entries whose effect is in doubt. Read by an operator, not retried.
    reconcile: list[JobResult] = field(default_factory=list)

    # ------------------------------------------------------------- one job --

    def run_once(self, workspace_id: str, *, worker: str) -> tuple[JobResult, ...]:
        claimed = self.store.claim_outbox(
            workspace_id, worker=worker, lease_seconds=self.lease_seconds)
        return tuple(self._run(workspace_id, entry) for entry in claimed)

    def _run(self, workspace_id: str, entry: OutboxEntry) -> JobResult:
        """One entry, from claim to outcome."""
        key = self.idempotency_key(entry)

        if entry.attempts > self.retry_budget:
            # THE BUDGET IS SPENT AND THE JOB IS NOT ABANDONED. It stops being
            # retried and starts being visible; a job retried forever is one
            # nobody ever looks at.
            return self._settle(workspace_id, entry, Outcome.FAILED,
                                f"retry budget of {self.retry_budget} spent")

        operation = self.store.operation(workspace_id, entry.operation_key)
        if operation is None:
            return self._settle(
                workspace_id, entry, Outcome.FAILED,
                "the operation this entry was committed with is gone, so "
                "there is nothing to publish against")
        if operation.outcome is Outcome.CANCEL_REQUESTED:
            # BEFORE THE EFFECT, so cancelling is still free.
            return self._settle(workspace_id, entry, Outcome.FAILED,
                                "cancelled before the effect")

        if not self._permitted(workspace_id, operation, entry):
            return self._settle(
                workspace_id, entry, Outcome.FAILED,
                "the advocate may no longer act on this matter, so the result "
                "is not published")

        # AN EFFECT ALREADY AT THE SINK IS NOT DONE AGAIN. This is the answer
        # to dying after the effect and before recording it: ask.
        try:
            if self.effects.already_delivered(key):
                return self._settle(workspace_id, entry, Outcome.COMPLETED,
                                    "already delivered; reconciled by key")
        except Exception as exc:  # noqa: BLE001 -- a sink that cannot answer
            return self._unknown(workspace_id, entry,
                                 f"the sink could not be asked: {exc}")

        try:
            self.effects.deliver(entry, idempotency_key=key)
        except AmbiguousEffect as exc:
            return self._unknown(workspace_id, entry, str(exc))
        except Exception as exc:  # noqa: BLE001 -- a named failure is a retry
            return JobResult(entry.entry_id, Outcome.RUNNING,
                             f"attempt failed and will be retried: {exc}",
                             entry.attempts)

        # THE SECOND PERMISSION CHECK, and it is not redundant. The first
        # decided whether to do the work; this decides whether to publish it,
        # and membership can be revoked in between.
        if not self._permitted(workspace_id, operation, entry):
            return self._settle(
                workspace_id, entry, Outcome.FAILED,
                "access was revoked while the job ran, so the effect is not "
                "published to the matter")
        return self._settle(workspace_id, entry, Outcome.COMPLETED, "delivered")

    # ----------------------------------------------------------- the parts --

    @staticmethod
    def idempotency_key(entry: OutboxEntry) -> str:
        """STABLE ACROSS RETRIES AND UNIQUE ACROSS ENTRIES.

        Derived from the entry rather than generated, because a key minted per
        attempt is a key that identifies nothing: the retry would present a
        different one and the sink would deliver twice.
        """
        return f"{entry.workspace_id}:{entry.entry_id}"

    def _permitted(self, workspace_id: str, operation, entry: OutboxEntry) -> bool:
        try:
            return bool(self.permits.may_publish(
                workspace_id, operation.advocate_id,
                entry.matter_id or operation.matter_id))
        except Exception:  # noqa: BLE001 -- an unanswerable permission is a no
            # FAIL CLOSED. A permission check that could not run must not read
            # as permission granted; that is the absent-input defect holding a
            # publication decision.
            return False

    def _settle(self, workspace_id: str, entry: OutboxEntry, outcome: Outcome,
                detail: str) -> JobResult:
        self._record(workspace_id, entry, outcome, detail)
        return JobResult(entry.entry_id, outcome, detail, entry.attempts)

    def _unknown(self, workspace_id: str, entry: OutboxEntry,
                 detail: str) -> JobResult:
        """AMBIGUOUS. Recorded, surfaced, and never retried from here."""
        result = JobResult(entry.entry_id, Outcome.UNKNOWN, detail,
                           entry.attempts)
        self._record(workspace_id, entry, Outcome.UNKNOWN, detail)
        self.reconcile.append(result)
        return result

    def _record(self, workspace_id: str, entry: OutboxEntry, outcome: Outcome,
                detail: str) -> None:
        recorder = getattr(self.store, "record_job_outcome", None)
        if recorder is None:
            return
        recorder(workspace_id, entry.entry_id, outcome=outcome, detail=detail)


class AmbiguousEffect(RuntimeError):
    """The sink was called and the answer never arrived.

    RAISED BY A SINK, deliberately, rather than inferred here from an
    exception type. Only the adapter talking to the destination knows whether
    a timeout means *not sent* or *sent and unacknowledged*, and guessing that
    from a socket error is how a charge gets duplicated.
    """
