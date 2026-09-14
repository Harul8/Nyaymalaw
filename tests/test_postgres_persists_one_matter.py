"""THE REAL THING, AGAINST A REAL SERVER. BK-83-AC1, BK-36. P10.

    NM_POSTGRES_DSN=postgresql://... python -m pytest -m postgres

WHY THIS IS SKIPPED AND WHY THAT IS NOT A PASS
------------------------------------------------
Measured on 11 September 2026: no PostgreSQL server, client library, container
runtime or WSL package is present on this machine, so a disposable cluster
cannot be started from tooling already here. The adapter is therefore built and
unproven, and the honest record of that is a SKIP plus a control that refuses
to let BK-83-AC1 carry evidence -- `tests/test_no_database_means_no_evidence.py`.

A skip that nobody counts is how an unproven adapter becomes a claimed one.

WHAT WOULD MAKE THIS RUN
--------------------------
A PostgreSQL instance the runner owns, and `pip install psycopg[binary]`.
The suite creates its own tables, uses two synthetic workspaces and drops
nothing it did not create. It must never be pointed at a database holding real
matters: `test_the_target_database_is_disposable` refuses a DSN that does not
say so in its name.

WHAT IS ASSERTED
------------------
    one accepted command produces one version, one operation and one outbox row
    the three are committed together or not at all
    a stale writer is refused and the winner's version stands
    a replayed idempotency key returns the original result and does no work
    the same key with a different request is a conflict
    workspace B cannot see, list or update workspace A's matter
    a pooled connection carries no tenant context between transactions
    every persisted field survives a round trip
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from nm.adapters.store.postgres import PostgresMatterStore
from nm.adapters.store.sealing import MatterSealer
from nm.domain.matter import Matter
from nm.domain.operation import (
    Operation,
    OutboxEntry,
    OutboxRefused,
    request_digest,
)
from nm.ports.store import StaleWrite
from nm.ports.transactional import OperationConflict, TenantMismatch

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("NM_POSTGRES_DSN"),
        reason="NM_POSTGRES_DSN is not set, so no PostgreSQL server is "
        "available. BK-83-AC1 stays NOT_RUN; a skip is not a pass.",
    ),
]

DSN = os.environ.get("NM_POSTGRES_DSN", "")
SEAL = "integration-seal-" + "k" * 24
WS_A, WS_B = "ws_synthetic_a", "ws_synthetic_b"


def _driver():
    try:
        import psycopg

        return psycopg
    except ImportError:
        try:
            import psycopg2

            return psycopg2
        except ImportError:
            pytest.skip("no psycopg/psycopg2 is installed")


@pytest.fixture
def store(tmp_path):
    """A store on a schema this test owns, dropped when it is done."""
    driver = _driver()
    sealer = MatterSealer(SEAL, tmp_path / "keys")

    def connect():
        return driver.connect(DSN)

    made = PostgresMatterStore(connect=connect, sealer=sealer, workspace_id=WS_A)
    made.create_schema()
    yield made
    with made._tx() as cur:
        for table in ("nm_outbox", "nm_operation", "nm_matter"):
            cur.execute(f"DELETE FROM {table} WHERE workspace_id IN (%s, %s)", (WS_A, WS_B))


@pytest.fixture
def other(store, tmp_path):
    return PostgresMatterStore(
        connect=store.connect, sealer=MatterSealer(SEAL, tmp_path / "keys"), workspace_id=WS_B
    )


def _matter(advocate: str = "adv@example.test") -> Matter:
    return Matter(
        id=f"mat_{uuid.uuid4().hex[:12]}", advocate_id=advocate, title="Kukatpally possession"
    )


def _operation(matter: Matter, key: str, workspace: str = WS_A) -> Operation:
    return Operation(
        idempotency_key=key,
        workspace_id=workspace,
        advocate_id=matter.advocate_id,
        command="create-matter",
        matter_id=str(matter.id),
        request_digest=request_digest({"title": matter.title}),
    )


# =========================== the target is disposable =======================


def test_the_target_database_is_disposable():
    """REFUSES A DSN THAT DOES NOT SAY SO. This suite deletes rows, and a
    database whose name does not announce that it is scratch is one somebody
    may be keeping real matters in."""
    name = DSN.rsplit("/", 1)[-1].split("?")[0].lower()
    assert any(
        word in name for word in ("test", "scratch", "tmp", "disposable", "synthetic", "nm_dev")
    ), (
        f"the DSN names database {name!r}, which does not announce itself as "
        f"disposable. Point NM_POSTGRES_DSN at a database you own and can lose."
    )


def test_the_schema_is_applied_and_says_its_version(store):
    assert store.schema_version() == 2


# ======================== one command, three records ========================


def test_one_accepted_command_writes_the_matter_the_operation_and_the_outbox(store):
    matter = _matter()
    entry = OutboxEntry(
        entry_id=f"e_{uuid.uuid4().hex[:8]}",
        workspace_id=WS_A,
        operation_key="key-1",
        kind="advise",
        matter_id=str(matter.id),
    )

    saved = store.commit_accepted(
        matter, expected_version=0, operation=_operation(matter, "key-1"), outbox=(entry,)
    )

    assert saved.version == 1
    assert store.load(matter.id) is not None
    recorded = store.operation(WS_A, "key-1")
    assert recorded is not None and recorded.matter_id == str(matter.id)
    claimed = store.claim_outbox(WS_A, worker="w1", lease_seconds=30)
    assert [c.entry_id for c in claimed] == [entry.entry_id]


def test_a_refused_outbox_entry_leaves_no_matter_behind(store):
    """ALL OR NONE. A matter version written beside a rejected entry is work
    owed that nobody recorded."""
    matter = _matter()
    bad = OutboxEntry(entry_id="e-bad", workspace_id=WS_B, operation_key="key-2", kind="advise")
    with pytest.raises(OutboxRefused):
        store.commit_accepted(
            matter, expected_version=0, operation=_operation(matter, "key-2"), outbox=(bad,)
        )
    assert store.load(matter.id) is None
    assert store.operation(WS_A, "key-2") is None


# ============================== versions ====================================


def test_a_stale_writer_is_refused_and_the_winner_stands(store):
    matter = _matter()
    first = store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "k-a"))
    store.commit_accepted(first, expected_version=1, operation=_operation(matter, "k-b"))

    with pytest.raises(StaleWrite) as refused:
        store.commit_accepted(first, expected_version=1, operation=_operation(matter, "k-c"))
    assert "version 2" in str(refused.value)
    assert store.load(matter.id).version == 2


# ============================== idempotency =================================


def test_a_replayed_key_returns_the_original_and_does_no_second_work(store):
    """The advocate's connection dropped and they pressed the button again."""
    matter = _matter()
    store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "same-key"))

    again = store.commit_accepted(
        matter, expected_version=0, operation=_operation(matter, "same-key")
    )
    assert again.id == matter.id
    assert store.load(matter.id).version == 1, "the replay did the work twice"

    with store._tx() as cur:
        cur.execute("SELECT count(*) FROM nm_matter WHERE workspace_id = %s", (WS_A,))
        assert cur.fetchone()[0] == 1


def test_the_same_key_with_a_different_request_is_a_conflict(store):
    matter = _matter()
    store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "reused"))
    changed = Operation(
        idempotency_key="reused",
        workspace_id=WS_A,
        advocate_id=matter.advocate_id,
        command="delete-matter",
        matter_id=str(matter.id),
        request_digest="a different request",
    )
    with pytest.raises(OperationConflict):
        store.commit_accepted(matter, expected_version=1, operation=changed)


# ============================== tenant isolation ============================


def test_workspace_b_cannot_read_or_list_workspace_as_matter(store, other):
    matter = _matter()
    store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "k-iso"))

    with pytest.raises(TenantMismatch):
        other.load(matter.id)
    assert other.list_for(matter.advocate_id).matters == ()
    assert other.list_for(matter.advocate_id).unreadable == ()


def test_workspace_b_cannot_update_workspace_as_matter(store, other):
    matter = _matter()
    saved = store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "k-upd"))
    with pytest.raises(StaleWrite):
        other.commit(saved, expected_version=1)
    assert store.load(matter.id).version == 1


def test_one_key_in_two_workspaces_are_two_operations(store, other):
    """An idempotency key is chosen by a client, and two firms may choose the
    same one. A global lookup would hand one firm the other's result."""
    mine, theirs = _matter(), _matter()
    store.commit_accepted(mine, expected_version=0, operation=_operation(mine, "collide"))
    other.commit_accepted(theirs, expected_version=0, operation=_operation(theirs, "collide", WS_B))

    assert store.operation(WS_A, "collide").matter_id == str(mine.id)
    assert other.operation(WS_B, "collide").matter_id == str(theirs.id)


def test_a_reused_connection_carries_no_tenant_context_between_transactions(store, other):
    """`SET LOCAL` is transaction-scoped, which is the property that matters
    for a pool: the setting cannot survive into the next caller's use of the
    same physical connection."""
    matter = _matter()
    store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "k-pool"))
    for _ in range(3):
        assert other.operation(WS_B, "k-pool") is None
        assert store.operation(WS_A, "k-pool") is not None


# ============================ nothing is lost ===============================


def test_every_persisted_field_survives_a_round_trip(store):
    """Compared against the file store's own encoder, so the two adapters
    cannot disagree about the shape of one matter."""
    from nm.adapters.store.file_store import _enc

    matter = _matter()
    store.commit_accepted(matter, expected_version=0, operation=_operation(matter, "k-fields"))
    back = store.load(matter.id)
    before = _enc(matter)
    after = _enc(back)
    before.pop("version", None)
    after.pop("version", None)
    assert json.loads(json.dumps(after, default=str)) == json.loads(json.dumps(before, default=str))


def test_worker_outcomes_and_unknown_reconciliation_survive_adapter_restart(store):
    from nm.core.worker import AmbiguousEffect, JobRunner
    from nm.domain.operation import Outcome

    from tests.test_owed_work_happens_once_or_says_it_cannot_tell import _Permits, _Sink

    matter = _matter()
    operation = _operation(matter, "durable-job")
    entry = OutboxEntry(
        entry_id="durable-entry",
        workspace_id=WS_A,
        operation_key=operation.idempotency_key,
        kind="synthetic",
        matter_id=matter.id,
    )
    store.commit_accepted(matter, expected_version=0, operation=operation, outbox=(entry,))
    sink = _Sink()
    sink.fail_with = AmbiguousEffect("synthetic unacknowledged effect")
    runner = JobRunner(store=store, effects=sink, permits=_Permits())
    assert runner.run_once(WS_A, worker="first")[0].outcome is Outcome.UNKNOWN
    fresh = PostgresMatterStore(connect=store.connect, sealer=store.sealer, workspace_id=WS_A)
    assert fresh.operation(WS_A, operation.idempotency_key).outcome is Outcome.UNKNOWN
    assert fresh.claim_outbox(WS_A, worker="ordinary", lease_seconds=30) == ()
    sink.delivered.append(f"{WS_A}:durable-entry")
    restarted = JobRunner(store=fresh, effects=sink, permits=_Permits())
    assert restarted.reconcile_once(WS_A, worker="review")[0].outcome is Outcome.COMPLETED
    assert fresh.operation(WS_A, operation.idempotency_key).outcome is Outcome.COMPLETED
    assert fresh.claim_outbox(WS_A, worker="again", lease_seconds=30) == ()
    assert sink.delivered == [f"{WS_A}:durable-entry"]


def test_database_cancellation_and_fencing_are_durable(store):
    from nm.core.worker import JobRunner
    from nm.domain.operation import Outcome
    from nm.ports.transactional import LeaseLost

    from tests.test_owed_work_happens_once_or_says_it_cannot_tell import _Permits, _Sink

    matter = _matter()
    operation = _operation(matter, "cancel-job")
    entry = OutboxEntry(
        entry_id="cancel-entry",
        workspace_id=WS_A,
        operation_key=operation.idempotency_key,
        kind="synthetic",
        matter_id=matter.id,
    )
    store.commit_accepted(matter, expected_version=0, operation=operation, outbox=(entry,))
    old = store.claim_outbox(WS_A, worker="old", lease_seconds=30)[0]
    with store._tx() as cur:
        cur.execute(
            "UPDATE nm_outbox SET leased_until = 0 WHERE workspace_id = %s AND entry_id = %s",
            (WS_A, entry.entry_id),
        )
    store.request_cancellation(WS_A, operation.idempotency_key)
    assert store.operation(WS_A, operation.idempotency_key).outcome is Outcome.CANCEL_REQUESTED
    sink = _Sink()
    assert (
        JobRunner(store=store, effects=sink, permits=_Permits())
        .run_once(WS_A, worker="current")[0]
        .outcome
        is Outcome.FAILED
    )
    with pytest.raises(LeaseLost):
        store.record_job_outcome(WS_A, old, outcome=Outcome.COMPLETED, detail="stale completion")
    assert sink.delivered == []
    with store._tx() as cur:
        cur.execute(
            "SELECT cancel_requested_at FROM nm_operation "
            "WHERE workspace_id = %s AND idempotency_key = %s",
            (WS_A, operation.idempotency_key),
        )
        assert cur.fetchone()[0]


def test_database_unknown_aggregate_keeps_cancellation_visible_to_sibling_jobs(store):
    from nm.core.worker import JobRunner
    from nm.domain.operation import Outcome

    from tests.test_owed_work_happens_once_or_says_it_cannot_tell import _Permits, _Sink

    matter = _matter()
    operation = _operation(matter, "cancel-unknown-sibling")
    entries = tuple(
        OutboxEntry(
            entry_id=f"sibling-{index}",
            workspace_id=WS_A,
            operation_key=operation.idempotency_key,
            kind="synthetic",
            matter_id=matter.id,
        )
        for index in (1, 2)
    )
    store.commit_accepted(matter, expected_version=0, operation=operation, outbox=entries)
    first = store.claim_outbox(WS_A, worker="first", lease_seconds=30, limit=1)[0]
    store.record_job_outcome(
        WS_A, first, outcome=Outcome.UNKNOWN, detail="synthetic unacknowledged effect"
    )
    requested = store.request_cancellation(WS_A, operation.idempotency_key)
    assert requested.outcome is Outcome.UNKNOWN and requested.cancel_requested_at
    fresh = PostgresMatterStore(connect=store.connect, sealer=store.sealer, workspace_id=WS_A)
    assert fresh.operation(WS_A, operation.idempotency_key).cancel_requested_at
    sink = _Sink()
    result = JobRunner(store=fresh, effects=sink, permits=_Permits()).run_once(WS_A, worker="next")
    assert len(result) == 1 and result[0].outcome is Outcome.FAILED
    assert result[0].entry_id != first.entry_id and sink.delivered == []
    assert fresh.operation(WS_A, operation.idempotency_key).outcome is Outcome.UNKNOWN
