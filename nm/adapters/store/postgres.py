"""The transactional matter store. BK-83-AC1, BK-36-AC1, BK-36-AC2. P10.

    store = PostgresMatterStore(connect, sealer=MatterSealer(...),
                                workspace_id="ws_a")

WHAT THIS IS FOR
------------------
One accepted command must produce exactly one matter version, one operation
record and the outbox rows it owes -- ALL OF THEM OR NONE. The file store can
write one file atomically; it cannot write three records atomically, and the
gap between them is where a turn gets charged for twice or a job is owed for a
state that does not exist.

IT IS NOT THE LIVE WRITE AUTHORITY AND MUST NOT BECOME ONE QUIETLY
--------------------------------------------------------------------
`nm/bootstrap/composition.py` wires the file store. This adapter is built,
tested against a real server, and shadow only, until BK-83-AC1 carries
integration evidence and a migration has been rehearsed and approved (P12).
Two live writers is the defect P12 exists to prevent, not a configuration
option.

WHY A CONNECTION FACTORY AND NOT A DSN
----------------------------------------
So the caller owns pooling, and so the tests can hand in a connection that is
already inside a transaction they will roll back. It takes a zero-argument
callable returning a DB-API 2.0 connection: `psycopg.connect`, `psycopg2`'s,
or a pool's `getconn`. Nothing here imports a driver, so the module is
importable on a machine with no PostgreSQL -- which matters, because the
control plane has to be able to say this exists and is unproven.

TENANT ISOLATION IS IN EVERY STATEMENT, NOT IN A SESSION VARIABLE
-------------------------------------------------------------------
`SET LOCAL` is set as well, so a future row-level policy has something to read
and so a pooled connection cannot carry one tenant's context into another
caller's transaction. But the WHERE clause is what actually refuses, because a
session variable is a thing somebody can forget to set and a missing WHERE is
a cross-tenant read that looks exactly like a successful one.

A row that exists but belongs to another workspace raises `TenantMismatch`.
It does not return None. *No rows* and *not yours* are different facts, and
reporting the second as the first is the absent-reads-as-success shape holding
another firm's matter.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from nm.adapters.store.sealing import MatterSealer
from nm.domain.matter import Matter, MatterId
from nm.domain.operation import (
    Operation,
    OutboxEntry,
    OutboxRefused,
    Outcome,
    now_text,
    refuse_outbox,
)
from nm.ports.store import MatterList, StaleWrite
from nm.ports.transactional import OperationConflict, TenantMismatch

#: The schema, versioned in one place. Applied by `create_schema`, which is
#: for disposable test databases -- a real deployment gets a migration with a
#: review, and P12 owns that.
SCHEMA_VERSION = 1

DDL = (
    """
    CREATE TABLE IF NOT EXISTS nm_schema (
        version      integer PRIMARY KEY,
        applied_at   text NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nm_matter (
        workspace_id text    NOT NULL,
        matter_id    text    NOT NULL,
        advocate_id  text    NOT NULL,
        version      integer NOT NULL,
        sealed       bytea   NOT NULL,
        updated_at   text    NOT NULL,
        PRIMARY KEY (workspace_id, matter_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nm_operation (
        workspace_id    text    NOT NULL,
        idempotency_key text    NOT NULL,
        advocate_id     text    NOT NULL,
        command         text    NOT NULL,
        outcome         text    NOT NULL,
        matter_id       text    NOT NULL DEFAULT '',
        matter_version  integer NOT NULL DEFAULT 0,
        request_digest  text    NOT NULL DEFAULT '',
        result          text    NOT NULL DEFAULT '{}',
        at              text    NOT NULL,
        PRIMARY KEY (workspace_id, idempotency_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nm_outbox (
        workspace_id   text    NOT NULL,
        entry_id       text    NOT NULL,
        operation_key  text    NOT NULL,
        kind           text    NOT NULL,
        matter_id      text    NOT NULL DEFAULT '',
        matter_version integer NOT NULL DEFAULT 0,
        payload        text    NOT NULL DEFAULT '{}',
        attempts       integer NOT NULL DEFAULT 0,
        at             text    NOT NULL,
        leased_by      text,
        leased_until   double precision,
        done_at        text,
        PRIMARY KEY (workspace_id, entry_id)
    )
    """,
    # THE INDEX THE CLAIM QUERY NEEDS. Without it `claim_outbox` degrades to a
    # sequential scan under a lock, which is a production incident wearing the
    # shape of slowness.
    """
    CREATE INDEX IF NOT EXISTS nm_outbox_claimable
        ON nm_outbox (workspace_id, done_at, leased_until)
    """,
)


class SchemaMissing(RuntimeError):
    """The database has no schema, or one this adapter does not know."""


@dataclass
class PostgresMatterStore:
    """A matter store that can commit state, acceptance and owed work at once."""

    connect: Callable[[], Any]
    sealer: MatterSealer
    #: EVERY STATEMENT IS SCOPED TO THIS. Fixed per store instance rather than
    #: passed per call, because a per-call tenant is a parameter somebody
    #: eventually forgets to pass and the default is catastrophic.
    workspace_id: str

    # ----------------------------------------------------------- plumbing ---

    @contextmanager
    def _tx(self):
        """One transaction. Committed on success, rolled back on anything.

        `SET LOCAL` IS TRANSACTION-SCOPED, which is the property that matters
        for a pool: the setting cannot survive into the next caller's use of
        the same physical connection, so there is no reset to remember.
        """
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.workspace_id = %s",
                            (self.workspace_id,))
                yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            close = getattr(conn, "close", None)
            if close is not None and getattr(conn, "_nm_pooled", False) is False:
                close()

    def create_schema(self) -> None:
        """FOR A DISPOSABLE TEST DATABASE. Not a migration.

        A real deployment gets a reviewed migration with a rollback, which is
        P12's work. This exists so an integration test can stand a schema up
        in a database it owns and drop it afterwards.
        """
        with self._tx() as cur:
            for statement in DDL:
                cur.execute(statement)
            cur.execute(
                "INSERT INTO nm_schema (version, applied_at) VALUES (%s, %s) "
                "ON CONFLICT (version) DO NOTHING",
                (SCHEMA_VERSION, now_text()))

    def schema_version(self) -> int | None:
        """The version applied, or None. NONE IS NOT ZERO -- an unmigrated
        database and one at version 0 are different facts."""
        with self._tx() as cur:
            cur.execute("SELECT max(version) FROM nm_schema")
            row = cur.fetchone()
        return None if row is None or row[0] is None else int(row[0])

    # ------------------------------------------------------------- reads ----

    def load(self, matter_id: MatterId) -> Matter | None:
        with self._tx() as cur:
            cur.execute(
                "SELECT workspace_id, sealed FROM nm_matter WHERE matter_id = %s",
                (str(matter_id),))
            rows = cur.fetchall()
        if not rows:
            return None
        mine = [r for r in rows if r[0] == self.workspace_id]
        if not mine:
            # NOT `return None`. The row exists and belongs to somebody else,
            # and an empty answer would say it does not exist -- which is the
            # same sentence a caller uses to decide it may create one.
            raise TenantMismatch(
                f"matter {matter_id!r} belongs to another workspace")
        return self._unseal(str(matter_id), mine[0][1])

    def list_for(self, advocate_id: str) -> MatterList:
        """The advocate's matters, AND what could not be read.

        Unreadable rows are NAMED rather than dropped, for the reason the port
        gives: a bare list cannot distinguish six matters from seven with one
        corrupt, and the seventh is the one with the deadline in it.
        """
        with self._tx() as cur:
            cur.execute(
                "SELECT matter_id, sealed FROM nm_matter "
                "WHERE workspace_id = %s AND advocate_id = %s "
                "ORDER BY matter_id",
                (self.workspace_id, advocate_id))
            rows = cur.fetchall()
        out, unreadable = [], []
        for matter_id, sealed in rows:
            try:
                out.append(self._unseal(str(matter_id), sealed))
            except Exception:  # noqa: BLE001 -- named, never swallowed
                unreadable.append(str(matter_id))
        return MatterList(tuple(out), tuple(unreadable))

    def operation(self, workspace_id: str,
                  idempotency_key: str) -> Operation | None:
        if workspace_id != self.workspace_id:
            raise TenantMismatch(
                f"this store serves {self.workspace_id!r} and was asked for "
                f"an operation in {workspace_id!r}")
        with self._tx() as cur:
            return self._operation(cur, idempotency_key)

    @staticmethod
    def _operation(cur, idempotency_key: str) -> Operation | None:
        cur.execute(
            "SELECT idempotency_key, workspace_id, advocate_id, command, "
            "outcome, matter_id, matter_version, result, request_digest, at "
            "FROM nm_operation "
            "WHERE workspace_id = current_setting('app.workspace_id') "
            "AND idempotency_key = %s",
            (idempotency_key,))
        row = cur.fetchone()
        if row is None:
            return None
        return Operation(
            idempotency_key=row[0], workspace_id=row[1], advocate_id=row[2],
            command=row[3], outcome=Outcome(row[4]), matter_id=row[5] or "",
            matter_version=int(row[6]), result=json.loads(row[7] or "{}"),
            request_digest=row[8] or "", at=row[9])

    # ------------------------------------------------------------ writes ----

    def commit_accepted(self, matter: Matter, *, expected_version: int,
                        operation: Operation,
                        outbox: tuple[OutboxEntry, ...] = ()) -> Matter:
        """The matter version, the operation and the owed work. ALL OR NONE.

        THE REPLAY IS ANSWERED BEFORE ANY WORK. If this key has been seen and
        carries the same request, the recorded operation comes back untouched
        -- that is the whole point of the key, and doing the work again to
        produce the same answer would be a second unit of work with a second
        cost.

        A key seen with a DIFFERENT request is a conflict and not a replay.
        Returning the first answer there would answer a question nobody asked.
        """
        if operation.workspace_id != self.workspace_id:
            raise TenantMismatch(
                f"this store serves {self.workspace_id!r} and the operation "
                f"is in {operation.workspace_id!r}")
        problems: list[str] = []
        for entry in outbox:
            problems.extend(refuse_outbox(
                entry, workspace_id=self.workspace_id, operation=operation))
        if problems:
            raise OutboxRefused("; ".join(problems))

        with self._tx() as cur:
            seen = self._operation(cur, operation.idempotency_key)
            if seen is not None:
                if seen.same_key_different_request(operation.command,
                                                   operation.request_digest):
                    raise OperationConflict(
                        f"idempotency key {operation.idempotency_key!r} was "
                        f"used for {seen.command!r} and is now offered for "
                        f"{operation.command!r}. One key means one request.")
                loaded = self._load_in(cur, seen.matter_id or str(matter.id))
                if loaded is not None:
                    return loaded

            saved = self._write_matter(cur, matter, expected_version)
            cur.execute(
                "INSERT INTO nm_operation (workspace_id, idempotency_key, "
                "advocate_id, command, outcome, matter_id, matter_version, "
                "request_digest, result, at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (self.workspace_id, operation.idempotency_key,
                 operation.advocate_id, operation.command,
                 operation.outcome.value, str(saved.id), saved.version,
                 operation.request_digest, json.dumps(operation.result),
                 operation.at or now_text()))
            for entry in outbox:
                cur.execute(
                    "INSERT INTO nm_outbox (workspace_id, entry_id, "
                    "operation_key, kind, matter_id, matter_version, payload, "
                    "attempts, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (self.workspace_id, entry.entry_id, entry.operation_key,
                     entry.kind, entry.matter_id or str(saved.id),
                     entry.matter_version or saved.version,
                     json.dumps(entry.payload), entry.attempts,
                     entry.at or now_text()))
            return saved

    def commit(self, matter: Matter, *, expected_version: int) -> Matter:
        """`StorePort`'s conditional write, with no operation attached."""
        with self._tx() as cur:
            return self._write_matter(cur, matter, expected_version)

    def _write_matter(self, cur, matter: Matter, expected_version: int) -> Matter:
        """Version-conditional, IN THE STATEMENT.

        `UPDATE ... WHERE version = %s` makes the check and the write one
        operation the database serialises. Reading the version and then
        writing would leave an interval, and the interval is where two turns
        interleaving on one derivation graph both win.
        """
        sealed = self.sealer.seal(str(matter.id),
                                  json.dumps(_encode(matter)).encode("utf8"))
        stamp = now_text()
        if expected_version == 0:
            cur.execute(
                "INSERT INTO nm_matter (workspace_id, matter_id, advocate_id, "
                "version, sealed, updated_at) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (workspace_id, matter_id) DO NOTHING",
                (self.workspace_id, str(matter.id), matter.advocate_id, 1,
                 sealed, stamp))
            if cur.rowcount == 0:
                raise StaleWrite(
                    f"matter {matter.id} already exists; this write expected "
                    f"to create it. Re-derive against the current state.")
            return _with_version(matter, 1)

        cur.execute(
            "UPDATE nm_matter SET version = version + 1, sealed = %s, "
            "updated_at = %s WHERE workspace_id = %s AND matter_id = %s "
            "AND version = %s",
            (sealed, stamp, self.workspace_id, str(matter.id),
             expected_version))
        if cur.rowcount == 0:
            cur.execute(
                "SELECT version FROM nm_matter WHERE workspace_id = %s "
                "AND matter_id = %s", (self.workspace_id, str(matter.id)))
            row = cur.fetchone()
            found = "absent" if row is None else f"version {row[0]}"
            raise StaleWrite(
                f"matter {matter.id} was expected at version "
                f"{expected_version} and is {found}. Re-derive against the "
                f"current state rather than overwriting it.")
        return _with_version(matter, expected_version + 1)

    # ------------------------------------------------------------ outbox ----

    def claim_outbox(self, workspace_id: str, *, worker: str,
                     lease_seconds: int,
                     limit: int = 1) -> tuple[OutboxEntry, ...]:
        """Take a lease nobody else holds. P11 drives this.

        `FOR UPDATE SKIP LOCKED` is what makes two workers safe without a
        queue: each takes rows the other is not holding, rather than blocking
        on them and serialising the whole pool behind the slowest job.
        """
        if workspace_id != self.workspace_id:
            raise TenantMismatch(
                f"this store serves {self.workspace_id!r}")
        with self._tx() as cur:
            cur.execute(
                "WITH claimable AS ("
                "  SELECT entry_id FROM nm_outbox "
                "  WHERE workspace_id = %s AND done_at IS NULL "
                "    AND (leased_until IS NULL "
                "         OR leased_until < extract(epoch from now())) "
                "  ORDER BY at LIMIT %s FOR UPDATE SKIP LOCKED) "
                "UPDATE nm_outbox o SET leased_by = %s, "
                "  leased_until = extract(epoch from now()) + %s, "
                "  attempts = o.attempts + 1 "
                "FROM claimable c WHERE o.workspace_id = %s "
                "  AND o.entry_id = c.entry_id "
                "RETURNING o.entry_id, o.operation_key, o.kind, o.matter_id, "
                "  o.matter_version, o.payload, o.attempts, o.at",
                (self.workspace_id, limit, worker, lease_seconds,
                 self.workspace_id))
            rows = cur.fetchall()
        return tuple(
            OutboxEntry(entry_id=r[0], workspace_id=self.workspace_id,
                        operation_key=r[1], kind=r[2], matter_id=r[3] or "",
                        matter_version=int(r[4]),
                        payload=json.loads(r[5] or "{}"),
                        attempts=int(r[6]), at=r[7])
            for r in rows)

    # ------------------------------------------------------------ sealing ---

    def _unseal(self, matter_id: str, sealed: Any) -> Matter:
        blob = bytes(sealed) if not isinstance(sealed, bytes) else sealed
        return _decode(json.loads(
            self.sealer.open(matter_id, blob).decode("utf8")))

    def _load_in(self, cur, matter_id: str) -> Matter | None:
        cur.execute(
            "SELECT sealed FROM nm_matter WHERE workspace_id = %s "
            "AND matter_id = %s", (self.workspace_id, matter_id))
        row = cur.fetchone()
        return None if row is None else self._unseal(matter_id, row[0])


def _encode(matter: Matter) -> dict:
    """THE SAME ENCODER THE FILE STORE USES. Two encoders is two shapes of the
    same matter, and the one that drifts is whichever is read less."""
    from nm.adapters.store.file_store import _enc

    return _enc(matter)


def _decode(blob: dict) -> Matter:
    from nm.adapters.store.file_store import _matter

    return _matter(blob)


def _with_version(matter: Matter, version: int) -> Matter:
    import dataclasses

    return dataclasses.replace(matter, version=version)
