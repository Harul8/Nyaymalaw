"""THE JOB LIFECYCLE. BK-83-AC2. P11.

WHAT IS PROVEN HERE AND WHAT IS NOT
-------------------------------------
PROVEN: the lifecycle. Leases, bounded retries, cancellation, idempotent
effects, permission rechecks, and -- the one that matters most -- that an
ambiguous external effect becomes `UNKNOWN` and is reconciled rather than
retried blind.

NOT PROVEN: durability. The store here is a reference implementation that
keeps its rows in memory, so "the worker restarted" means a new `JobRunner`
against the same rows, which is exactly what restart means to the lease logic
-- every fact a worker needs is in the store and none is in the worker. What
it does NOT establish is that a real substrate keeps those rows across a
process death. That is BK-83-AC1's integration evidence, it needs a
PostgreSQL server, and there is none on this machine.

Saying which of the two this file is buys the right to have it at all. A
memory store presented as durability proof would be the three-stores defect
with a queue.

EXACTLY-ONCE IS NOT CLAIMED ANYWHERE, and `test_the_runner_never_promises_
exactly_once` holds that line in the source itself.
"""
from __future__ import annotations

import pytest

from nm.core.worker import (
    AmbiguousEffect,
    JobResult,
    JobRunner,
)
from nm.domain.operation import Operation, OutboxEntry, Outcome, request_digest

pytestmark = pytest.mark.class_a

WS = "ws_a"
ADVOCATE = "adv@example.test"


# ============================ the reference store ===========================

class _Store:
    """A reference `TransactionalStorePort`. IN MEMORY, NOT DURABLE.

    It exists so the lifecycle can be exercised end to end without a database.
    It is not evidence that anything survives a process death.
    """

    def __init__(self) -> None:
        self.rows: dict[str, OutboxEntry] = {}
        self.leases: dict[str, float] = {}
        self.operations: dict[str, Operation] = {}
        self.outcomes: list[tuple[str, Outcome, str]] = []
        self.now = 1000.0

    def add(self, entry: OutboxEntry, operation: Operation) -> None:
        self.rows[entry.entry_id] = entry
        self.operations[operation.idempotency_key] = operation

    def claim_outbox(self, workspace_id, *, worker, lease_seconds, limit=1):
        out = []
        for entry_id, entry in sorted(self.rows.items()):
            if any(entry_id == done for done, _, _ in self.outcomes):
                continue
            if self.leases.get(entry_id, 0.0) > self.now:
                continue
            self.leases[entry_id] = self.now + lease_seconds
            bumped = OutboxEntry(
                entry_id=entry.entry_id, workspace_id=entry.workspace_id,
                operation_key=entry.operation_key, kind=entry.kind,
                matter_id=entry.matter_id, payload=entry.payload,
                matter_version=entry.matter_version,
                attempts=entry.attempts + 1, at=entry.at)
            self.rows[entry_id] = bumped
            out.append(bumped)
            if len(out) >= limit:
                break
        return tuple(out)

    def operation(self, workspace_id, idempotency_key):
        return self.operations.get(idempotency_key)

    def record_job_outcome(self, workspace_id, entry_id, *, outcome, detail):
        self.outcomes.append((entry_id, outcome, detail))


class _Sink:
    """A local synthetic destination that records what reached it."""

    def __init__(self) -> None:
        self.delivered: list[str] = []
        self.fail_with: Exception | None = None
        self.answerable = True

    def deliver(self, entry, *, idempotency_key):
        if self.fail_with is not None:
            raise self.fail_with
        self.delivered.append(idempotency_key)
        return {"ok": True}

    def already_delivered(self, idempotency_key):
        if not self.answerable:
            raise RuntimeError("the sink is unreachable")
        return idempotency_key in self.delivered


class _Permits:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.asked = 0

    def may_publish(self, workspace_id, advocate_id, matter_id):
        self.asked += 1
        return self.allowed


def _fixture(*, allowed: bool = True, attempts: int = 0):
    store, sink, permits = _Store(), _Sink(), _Permits(allowed)
    operation = Operation(
        idempotency_key="op-1", workspace_id=WS, advocate_id=ADVOCATE,
        command="advise", matter_id="mat_1",
        request_digest=request_digest({"m": 1}))
    entry = OutboxEntry(entry_id="e-1", workspace_id=WS, operation_key="op-1",
                        kind="advise", matter_id="mat_1", attempts=attempts)
    store.add(entry, operation)
    runner = JobRunner(store=store, effects=sink, permits=permits)
    return runner, store, sink, permits


# ============================= the ordinary path ============================

def test_a_claimed_job_is_delivered_once():
    """The negative control. Without it, a runner that refused everything
    satisfies every refusal test below."""
    runner, _, sink, _ = _fixture()
    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.COMPLETED]
    assert sink.delivered == ["ws_a:e-1"]


def test_a_second_pass_does_not_deliver_it_again():
    runner, _, sink, _ = _fixture()
    runner.run_once(WS, worker="w1")
    runner.run_once(WS, worker="w1")
    assert sink.delivered == ["ws_a:e-1"]


def test_two_workers_do_not_both_hold_one_job():
    """The lease is a write, and a claim nobody else holds is the only kind."""
    runner, store, sink, _ = _fixture()
    first = store.claim_outbox(WS, worker="w1", lease_seconds=30)
    second = store.claim_outbox(WS, worker="w2", lease_seconds=30)
    assert [e.entry_id for e in first] == ["e-1"]
    assert second == ()


def test_an_expired_lease_makes_the_job_claimable_again():
    """A worker that died holding a lease must not park the work forever."""
    runner, store, _, _ = _fixture()
    store.claim_outbox(WS, worker="w1", lease_seconds=30)
    assert store.claim_outbox(WS, worker="w2", lease_seconds=30) == ()
    store.now += 31
    assert [e.entry_id for e in
            store.claim_outbox(WS, worker="w2", lease_seconds=30)] == ["e-1"]


# ============================ dying, and where =============================

def test_a_crash_before_the_effect_costs_nothing():
    """The job is simply claimed again and delivered once."""
    runner, store, sink, _ = _fixture()
    store.claim_outbox(WS, worker="dead", lease_seconds=30)   # then died
    store.now += 31

    fresh = JobRunner(store=store, effects=sink, permits=_Permits())
    results = fresh.run_once(WS, worker="w2")
    assert [r.outcome for r in results] == [Outcome.COMPLETED]
    assert sink.delivered == ["ws_a:e-1"]


def test_a_crash_after_the_effect_does_not_deliver_twice():
    """THE CASE THE KEY EXISTS FOR. The effect happened and the worker died
    before recording it, so the next attempt must ask the sink rather than
    assume."""
    runner, store, sink, _ = _fixture()
    sink.delivered.append("ws_a:e-1")            # it happened; nobody wrote it down
    store.now += 31

    results = JobRunner(store=store, effects=sink,
                        permits=_Permits()).run_once(WS, worker="w2")
    assert [r.outcome for r in results] == [Outcome.COMPLETED]
    assert sink.delivered == ["ws_a:e-1"], "the effect happened twice"
    assert "reconciled by key" in results[0].detail


def test_the_idempotency_key_is_stable_across_attempts():
    """A key minted per attempt identifies nothing: the retry presents a
    different one and the sink delivers twice."""
    entry = OutboxEntry(entry_id="e-1", workspace_id=WS, operation_key="op-1",
                        kind="advise", attempts=1)
    again = OutboxEntry(entry_id="e-1", workspace_id=WS, operation_key="op-1",
                        kind="advise", attempts=7)
    assert JobRunner.idempotency_key(entry) == JobRunner.idempotency_key(again)


# ========================= the ambiguous outcome ===========================

def test_an_ambiguous_effect_becomes_unknown_and_is_not_retried():
    """THE POINT OF THE FILE. Neither done nor undone, and both of the other
    two answers cost money or lose work."""
    runner, _, sink, _ = _fixture()
    sink.fail_with = AmbiguousEffect("the call timed out after the request left")

    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.UNKNOWN]
    assert results[0].reconcilable()
    assert runner.reconcile and runner.reconcile[0].entry_id == "e-1"
    assert Outcome.UNKNOWN.retryable() is False


def test_a_sink_that_cannot_be_asked_is_also_unknown():
    """Not knowing whether it was delivered and not being able to find out are
    the same state, and it is not failure."""
    runner, _, sink, _ = _fixture()
    sink.answerable = False
    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.UNKNOWN]
    assert sink.delivered == [], "it delivered without knowing what was there"


def test_a_named_failure_is_retried_and_an_ambiguous_one_is_not():
    """The difference is whether anything may have happened at the far end."""
    runner, _, sink, _ = _fixture()
    sink.fail_with = ConnectionRefusedError("nothing was listening")
    assert [r.outcome for r in runner.run_once(WS, worker="w1")] == \
        [Outcome.RUNNING]
    assert runner.reconcile == []


# ============================ budget and cancel ============================

def test_the_retry_budget_stops_a_job_that_will_never_succeed():
    """A job retried forever is a job nobody ever looks at."""
    runner, _, sink, _ = _fixture(attempts=99)
    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "retry budget" in results[0].detail
    assert sink.delivered == []


def test_a_cancellation_before_the_effect_stops_the_job():
    runner, store, sink, _ = _fixture()
    store.operations["op-1"] = Operation(
        idempotency_key="op-1", workspace_id=WS, advocate_id=ADVOCATE,
        command="advise", matter_id="mat_1",
        outcome=Outcome.CANCEL_REQUESTED, request_digest="d")
    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert sink.delivered == []
    assert "cancelled" in results[0].detail


def test_a_cancellation_request_is_not_an_erasure():
    """Work already accepted is not undone by asking, and the vocabulary has
    to keep *asked* and *happened* apart."""
    assert Outcome.CANCEL_REQUESTED.value == "cancel_requested"
    assert Outcome.CANCEL_REQUESTED.settled() is False


# =========================== permission, twice =============================

def test_a_revoked_advocate_never_reaches_the_sink():
    runner, _, sink, permits = _fixture(allowed=False)
    results = runner.run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert sink.delivered == []
    assert permits.asked >= 1


def test_permission_is_rechecked_after_the_effect_before_publishing():
    """NOT REDUNDANT. The first check decides whether to do the work; the
    second decides whether to publish it, and membership can be revoked in
    between."""

    class _Revoking(_Permits):
        def may_publish(self, workspace_id, advocate_id, matter_id):
            self.asked += 1
            return self.asked == 1          # revoked immediately after

    store, sink = _Store(), _Sink()
    operation = Operation(idempotency_key="op-1", workspace_id=WS,
                          advocate_id=ADVOCATE, command="advise",
                          matter_id="mat_1", request_digest="d")
    store.add(OutboxEntry(entry_id="e-1", workspace_id=WS,
                          operation_key="op-1", kind="advise",
                          matter_id="mat_1"), operation)
    permits = _Revoking()
    results = JobRunner(store=store, effects=sink,
                        permits=permits).run_once(WS, worker="w1")

    assert permits.asked == 2, "the second check never happened"
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "revoked while the job ran" in results[0].detail


def test_a_permission_check_that_cannot_run_refuses():
    """An unanswerable permission must not read as permission granted."""

    class _Broken:
        def may_publish(self, *a):
            raise RuntimeError("the directory is unreachable")

    store, sink = _Store(), _Sink()
    operation = Operation(idempotency_key="op-1", workspace_id=WS,
                          advocate_id=ADVOCATE, command="advise",
                          matter_id="mat_1", request_digest="d")
    store.add(OutboxEntry(entry_id="e-1", workspace_id=WS,
                          operation_key="op-1", kind="advise"), operation)
    results = JobRunner(store=store, effects=sink,
                        permits=_Broken()).run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert sink.delivered == []


# ============================== what is claimed ============================

def test_the_runner_never_promises_exactly_once():
    """Exactly-once external delivery does not exist over a network nobody
    controls, and a docstring that implied it would be the claim somebody
    quotes in a design review."""
    import inspect

    import nm.core.worker as worker

    source = inspect.getsource(worker)
    assert "EXACTLY-ONCE EXTERNAL DELIVERY. It does not exist" in source
    lowered = source.lower()
    for phrase in ("guarantees exactly once", "exactly-once delivery is",
                   "delivered exactly once"):
        assert phrase not in lowered, phrase


def test_a_missing_operation_is_a_failure_and_not_a_silent_skip():
    """An entry whose operation is gone has nothing to publish against, and
    dropping it quietly would lose owed work with no record."""
    store, sink = _Store(), _Sink()
    store.rows["e-1"] = OutboxEntry(entry_id="e-1", workspace_id=WS,
                                    operation_key="vanished", kind="advise")
    results = JobRunner(store=store, effects=sink,
                        permits=_Permits()).run_once(WS, worker="w1")
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "is gone" in results[0].detail


def test_a_job_result_is_a_value_and_not_a_boolean():
    """A worker that answered True/False could not express UNKNOWN at all."""
    result = JobResult("e-1", Outcome.UNKNOWN, "timed out")
    assert result.reconcilable()
    assert not JobResult("e-1", Outcome.COMPLETED, "").reconcilable()
