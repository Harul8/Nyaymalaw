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

from dataclasses import replace

import pytest

from nm.core.worker import (
    AmbiguousEffect,
    JobResult,
    JobRunner,
)
from nm.domain.matter import Matter
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
        self.matters: dict[str, Matter] = {}
        self.reads: list[str] = []
        self.outcomes: list[tuple[str, Outcome, str]] = []
        self.now = 1000.0

    def add(self, entry: OutboxEntry, operation: Operation) -> None:
        self.rows[entry.entry_id] = entry
        self.operations[operation.idempotency_key] = operation
        matter_id = entry.matter_id or operation.matter_id
        if matter_id not in self.matters:
            self.matters[matter_id] = Matter(
                id=matter_id, advocate_id=operation.advocate_id,
                title="Synthetic accepted matter", version=entry.matter_version)

    def load(self, matter_id):
        self.reads.append(str(matter_id))
        return self.matters.get(str(matter_id))

    def claim_outbox(self, workspace_id, *, worker, lease_seconds, limit=1, reconcile=False):
        out = []
        for entry_id, entry in sorted(self.rows.items()):
            previous = next((state for done, state, _ in reversed(self.outcomes)
                             if entry_id == done), None)
            if previous is not None and previous is not Outcome.UNKNOWN:
                continue
            if reconcile != (previous is Outcome.UNKNOWN):
                continue
            if self.leases.get(entry_id, 0.0) > self.now:
                continue
            self.leases[entry_id] = self.now + lease_seconds
            bumped = OutboxEntry(
                entry_id=entry.entry_id, workspace_id=entry.workspace_id,
                operation_key=entry.operation_key, kind=entry.kind,
                matter_id=entry.matter_id, payload=entry.payload,
                matter_version=entry.matter_version,
                attempts=entry.attempts + 1, at=entry.at, lease_owner=worker)
            self.rows[entry_id] = bumped
            out.append(bumped)
            if len(out) >= limit:
                break
        return tuple(out)

    def operation(self, workspace_id, idempotency_key):
        return self.operations.get(idempotency_key)

    def renew_outbox(self, workspace_id, entry, *, lease_seconds):
        from nm.ports.transactional import LeaseLost

        held = self.rows.get(entry.entry_id)
        if (workspace_id != entry.workspace_id or held is None
                or held.lease_owner != entry.lease_owner or held.attempts != entry.attempts
                or self.leases.get(entry.entry_id, 0) <= self.now):
            raise LeaseLost("the claim is no longer current")
        self.leases[entry.entry_id] = self.now + lease_seconds

    def record_job_outcome(self, workspace_id, entry, *, outcome, detail):
        self.renew_outbox(workspace_id, entry, lease_seconds=1)
        self.outcomes.append((entry.entry_id, outcome, detail))
        self.leases[entry.entry_id] = 0

    def request_cancellation(self, workspace_id, idempotency_key):
        from dataclasses import replace

        operation = self.operations.get(idempotency_key)
        if operation is not None:
            self.operations[idempotency_key] = replace(
                operation, cancel_requested_at="2026-09-12T00:00:00+00:00",
                outcome=Outcome.CANCEL_REQUESTED if operation.outcome in (
                    Outcome.ACCEPTED, Outcome.RUNNING) else operation.outcome)
        return self.operations.get(idempotency_key)


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


def test_unknown_survives_a_new_runner_and_requires_explicit_reconciliation():
    runner, store, sink, permits = _fixture()
    sink.fail_with = AmbiguousEffect("synthetic lost acknowledgement")
    assert runner.run_once(WS, worker="first")[0].outcome is Outcome.UNKNOWN
    store.now += 100
    restarted = JobRunner(store=store, effects=sink, permits=permits)
    assert restarted.run_once(WS, worker="second") == ()
    sink.fail_with = None
    sink.delivered.append("ws_a:e-1")
    assert restarted.reconcile_once(WS, worker="review")[0].outcome is Outcome.COMPLETED
    assert sink.delivered == ["ws_a:e-1"]


def test_a_missing_outcome_writer_refuses_before_an_effect():
    runner, store, sink, _ = _fixture()
    store.record_job_outcome = None
    with pytest.raises(TypeError, match="record_job_outcome"):
        runner.run_once(WS, worker="first")
    assert sink.delivered == []


def test_an_expired_claim_cannot_settle_after_another_worker_claims():
    from nm.ports.transactional import LeaseLost

    runner, store, _, _ = _fixture()
    old = store.claim_outbox(WS, worker="old", lease_seconds=30)[0]
    store.now += 31
    new = store.claim_outbox(WS, worker="new", lease_seconds=30)[0]
    with pytest.raises(LeaseLost):
        store.record_job_outcome(WS, old, outcome=Outcome.COMPLETED, detail="stale")
    store.record_job_outcome(WS, new, outcome=Outcome.COMPLETED, detail="current")
    assert len(store.outcomes) == 1


def test_a_slow_effect_renews_its_lease_without_holding_a_transaction():
    import threading

    runner, store, sink, _ = _fixture()
    runner.lease_seconds = 0.06
    heartbeat_observed = threading.Event()
    original = store.renew_outbox
    calls = []
    def renew(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(threading.current_thread().name)
        if threading.current_thread().name == "nm-job-lease":
            heartbeat_observed.set()
    store.renew_outbox = renew
    def slow(entry, *, idempotency_key):
        assert heartbeat_observed.wait(1), "the effect outlived an unrenewed lease"
        sink.delivered.append(idempotency_key)
    sink.deliver = slow
    assert runner.run_once(WS, worker="w1")[0].outcome is Outcome.COMPLETED
    assert "nm-job-lease" in calls


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


@pytest.mark.parametrize("cancel", [False, True])
def test_recovery_reconciles_a_prior_effect_before_budget_or_cancellation(cancel):
    runner, store, sink, _ = _fixture(attempts=99)
    sink.delivered.append("ws_a:e-1")
    if cancel:
        store.request_cancellation(WS, "op-1")
    result = runner.run_once(WS, worker="recovery")[0]
    assert result.outcome is Outcome.COMPLETED
    assert "reconciled by key" in result.detail
    assert "cancelled before" not in result.detail
    assert sink.delivered == ["ws_a:e-1"]
    if cancel:
        assert store.operation(WS, "op-1").cancel_requested_at


def test_unknown_aggregate_does_not_hide_cancellation_from_an_undispatched_sibling():
    from dataclasses import replace
    runner, store, sink, _ = _fixture()
    operation = replace(store.operations["op-1"], outcome=Outcome.UNKNOWN)
    store.operations["op-1"] = operation
    store.outcomes.append(("e-1", Outcome.UNKNOWN, "unacknowledged first effect"))
    store.add(OutboxEntry(entry_id="e-2", workspace_id=WS, operation_key="op-1",
                         kind="advise", matter_id="mat_1"), operation)
    requested = store.request_cancellation(WS, "op-1")
    assert requested.outcome is Outcome.UNKNOWN and requested.cancel_requested_at
    result = runner.run_once(WS, worker="sibling")[0]
    assert result.entry_id == "e-2" and result.outcome is Outcome.FAILED
    assert "cancelled before the effect" in result.detail
    assert sink.delivered == []


def test_unanswerable_prior_effect_is_unknown_even_after_cancellation_and_budget():
    runner, store, sink, _ = _fixture(attempts=99)
    store.request_cancellation(WS, "op-1")
    sink.answerable = False
    result = runner.run_once(WS, worker="recovery")[0]
    assert result.outcome is Outcome.UNKNOWN and sink.delivered == []


def test_permission_is_rechecked_after_a_positive_reconciliation_lookup():
    runner, _, sink, permits = _fixture(attempts=1)
    sink.delivered.append("ws_a:e-1")
    def revoke_during_read(key):
        permits.allowed = False
        return True
    sink.already_delivered = revoke_during_read
    result = runner.run_once(WS, worker="recovery")[0]
    assert result.outcome is Outcome.FAILED
    assert "already delivered" in result.detail and "no result is authorised" in result.detail
    assert sink.delivered == ["ws_a:e-1"] and permits.asked == 2


@pytest.mark.parametrize("uncertain", [None, "false", {}, 0])
def test_a_non_boolean_sink_status_is_unknown_and_never_a_no_effect_claim(uncertain):
    runner, _, sink, _ = _fixture()
    sink.already_delivered = lambda key: uncertain
    result = runner.run_once(WS, worker="recovery")[0]
    assert result.outcome is Outcome.UNKNOWN and sink.delivered == []


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
            return not sink.delivered  # revoke at the effect, not at an arbitrary read count

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

    assert permits.asked == 3, "read, dispatch and publication checks must all happen"
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


@pytest.mark.parametrize("answer", [None, 1, "true", {"allowed": True}, [True]])
def test_only_explicit_boolean_permission_may_read_or_deliver(answer):
    runner, store, sink, permits = _fixture()
    permits.allowed = answer
    result = runner.run_once(WS, worker="first")[0]
    assert result.outcome is Outcome.FAILED
    assert store.reads == [] and sink.delivered == []


@pytest.mark.parametrize("change", ["newer", "older", "absent", "wrong_id", "boolean",
                                    "string", "unavailable", "missing_reader"])
def test_current_canonical_identity_and_version_are_required_before_any_sink_read(change):
    runner, store, sink, _ = _fixture()
    matter = replace(store.matters["mat_1"], version=7)
    store.matters["mat_1"] = matter
    store.rows["e-1"] = replace(store.rows["e-1"], matter_version=7)
    if change == "absent":
        store.matters.clear()
    elif change == "unavailable":
        def unavailable(matter_id):
            raise OSError("synthetic canonical store unavailable")
        store.load = unavailable
    elif change == "missing_reader":
        store.load = None
    else:
        changes = {"newer": {"version": 8}, "older": {"version": 6},
                   "wrong_id": {"id": "mat_other"}, "boolean": {"version": True},
                   "string": {"version": "7"}}
        store.matters["mat_1"] = replace(matter, **changes[change])
    status_reads = []
    sink.already_delivered = lambda key: status_reads.append(key) or False
    result = runner.run_once(WS, worker="first")[0]
    assert result.outcome is Outcome.FAILED
    assert status_reads == [] and sink.delivered == []


def test_permission_evaluation_cannot_hide_a_concurrent_matter_change():
    runner, store, sink, permits = _fixture()
    def changes_matter(*args):
        store.matters["mat_1"] = replace(store.matters["mat_1"], version=1)
        return True
    permits.may_publish = changes_matter
    result = runner.run_once(WS, worker="first")[0]
    assert result.outcome is Outcome.FAILED and sink.delivered == []
    assert store.reads == ["mat_1"]


@pytest.mark.parametrize("point", ["negative_status", "positive_status", "delivery"])
@pytest.mark.parametrize("change", ["stale", "unavailable"])
def test_the_matter_is_rechecked_after_slow_work_without_erasing_sink_facts(point, change):
    runner, store, sink, _ = _fixture()
    def invalidate():
        if change == "stale":
            store.matters["mat_1"] = replace(store.matters["mat_1"], version=1)
        else:
            def unavailable(matter_id):
                raise OSError("synthetic canonical store unavailable")
            store.load = unavailable
    if point == "delivery":
        def deliver(entry, *, idempotency_key):
            sink.delivered.append(idempotency_key)
            invalidate()
        sink.deliver = deliver
    else:
        def status(key):
            if point == "positive_status":
                sink.delivered.append(key)
            invalidate()
            return point == "positive_status"
        sink.already_delivered = status
    result = runner.run_once(WS, worker="first")[0]
    assert result.outcome is Outcome.FAILED
    if point == "negative_status":
        assert sink.delivered == [] and "nothing was sent" in result.detail
    else:
        assert sink.delivered == ["ws_a:e-1"]
        assert "no result is authorised" in result.detail
        assert "delivered" in result.detail or "confirmed delivery" in result.detail


@pytest.mark.parametrize("reconciling", [False, True])
def test_a_stale_recovery_never_relabels_a_possible_prior_effect_as_no_effect(reconciling):
    runner, store, sink, _ = _fixture(attempts=1)
    sink.delivered.append("ws_a:e-1")
    store.matters["mat_1"] = replace(store.matters["mat_1"], version=1)
    if reconciling:
        store.outcomes.append(("e-1", Outcome.UNKNOWN, "prior ambiguous effect"))
    method = runner.reconcile_once if reconciling else runner.run_once
    result = method(WS, worker="recovery")[0]
    assert result.outcome is Outcome.UNKNOWN
    assert sink.delivered == ["ws_a:e-1"]
    assert "prior effect" in result.detail


def test_current_nonzero_version_retains_the_three_canonical_checks():
    runner, store, sink, _ = _fixture()
    store.rows["e-1"] = replace(store.rows["e-1"], matter_version=17)
    store.matters["mat_1"] = replace(store.matters["mat_1"], version=17)
    assert runner.run_once(WS, worker="first")[0].outcome is Outcome.COMPLETED
    assert sink.delivered == ["ws_a:e-1"] and store.reads == ["mat_1"] * 3


@pytest.mark.parametrize("expected", [None, False, "0", -1])
def test_an_unestablished_expected_version_never_defaults_to_the_current_matter(expected):
    runner, store, sink, _ = _fixture()
    store.rows["e-1"] = replace(store.rows["e-1"], matter_version=expected)
    result = runner.run_once(WS, worker="first")[0]
    assert result.outcome is Outcome.FAILED
    assert store.reads == [] and sink.delivered == []


@pytest.mark.parametrize("reconciling", [False, True])
def test_a_missing_operation_during_recovery_retains_the_uncertain_prior_effect(reconciling):
    runner, store, sink, _ = _fixture(attempts=1)
    sink.delivered.append("ws_a:e-1")
    store.operations.clear()
    if reconciling:
        store.outcomes.append(("e-1", Outcome.UNKNOWN, "prior ambiguous effect"))
    method = runner.reconcile_once if reconciling else runner.run_once
    result = method(WS, worker="recovery")[0]
    assert result.outcome is Outcome.UNKNOWN
    assert sink.delivered == ["ws_a:e-1"] and store.reads == []
