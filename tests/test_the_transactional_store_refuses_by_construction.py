"""WHAT THE ADAPTER REFUSES WITHOUT A SERVER. BK-83-AC1. P10.

THIS FILE IS NOT INTEGRATION EVIDENCE AND MUST NEVER BE RECORDED AS ANY
------------------------------------------------------------------------
BK-83-AC1 requires `integration_test` proof against a real PostgreSQL server.
Nothing here talks to one. A recording double proves that THIS MODULE asks the
right questions; it proves nothing about whether PostgreSQL answers them, and
the two are different claims. `tests/test_postgres_persists_one_matter.py`
holds the real proof and is skipped until a server exists.

The distinction matters because the easy mistake is to build a convincing
double, watch it go green, and record the criterion as met -- which is the
three-stores defect with a schema: one store answering for another.

WHAT THIS DOES ESTABLISH, and it is worth having on every commit
-----------------------------------------------------------------
    every statement that touches a tenant table is scoped to a workspace
    a row that belongs to another workspace RAISES and never reads as absent
    an outbox entry that contradicts its operation is refused before any write
    a replayed key returns the original, and a reused key with a new request
        is a conflict rather than an answer to a question nobody asked
    the schema names its version, and an unmigrated database is None not zero

The first is a static scan of the SQL, which is the highest-value check here:
a missing `WHERE workspace_id` is a cross-tenant read that looks exactly like
a successful one, and no amount of local testing with one tenant finds it.
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest

from nm.adapters.store import postgres as pg
from nm.domain.operation import (
    Operation,
    OutboxEntry,
    OutboxRefused,
    Outcome,
    refuse_outbox,
    request_digest,
)
from nm.ports.transactional import TenantMismatch, TransactionalStorePort

pytestmark = pytest.mark.class_a

#: Tables whose every row belongs to exactly one workspace.
TENANT_TABLES = ("nm_matter", "nm_operation", "nm_outbox")


def _statements() -> list[str]:
    """Every SQL string literal in the adapter, joined per call site.

    Taken from the AST rather than by reading the file as text, so a statement
    split across implicitly-concatenated lines is one statement here -- which
    is how they are written, and a line-based scan would see a `SELECT` with
    no `WHERE` on it and be satisfied by the wrong half.
    """
    tree = ast.parse(inspect.getsource(pg))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = " ".join(node.value.split())
            if re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b", text):
                out.append(text)
    return out


def test_the_scan_can_see_the_adapters_statements():
    """A scan that found nothing would pass the tenant check silently."""
    found = _statements()
    assert len(found) >= 8, found
    assert any("UPDATE nm_matter" in s for s in found)
    assert any("INSERT INTO nm_operation" in s for s in found)


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_every_statement_against_a_tenant_table_is_scoped(table):
    """A MISSING `WHERE workspace_id` IS A CROSS-TENANT READ THAT LOOKS LIKE A
    SUCCESSFUL ONE, and testing with one tenant never finds it.

    `nm_matter`'s bare `SELECT ... WHERE matter_id` is deliberately exempt and
    is the ONE place a row is fetched without the filter -- because it exists
    to tell *absent* from *not yours*, and it compares the workspace itself.
    That exemption is named here rather than left as a hole the scan happens
    not to notice.
    """
    unscoped = []
    for statement in _statements():
        if table not in statement:
            continue
        if "workspace_id" in statement:
            continue
        if statement.startswith("CREATE") or "nm_schema" in statement:
            continue
        unscoped.append(statement)

    allowed = [
        "SELECT workspace_id, sealed FROM nm_matter WHERE matter_id = %s",
    ]
    surprising = [s for s in unscoped if s not in allowed]
    assert not surprising, (
        f"these touch {table} without naming a workspace: {surprising}")


def test_the_one_unscoped_read_exists_to_tell_absent_from_not_yours():
    """The exemption above is only safe because of what `load` does with it.
    If that changed, the exemption would become the hole."""
    source = inspect.getsource(pg.PostgresMatterStore.load)
    assert "TenantMismatch" in source
    assert "return None" in source, "an absent matter must still read as absent"


def test_a_foreign_row_raises_rather_than_reading_as_absent():
    """*No rows* and *not yours* are different facts, and reporting the second
    as the first is the absent-reads-as-success shape holding another firm's
    matter -- a caller that sees None decides it may create one."""

    class _Foreign:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, args=()):
            self._sql = sql

        def fetchall(self):
            if "FROM nm_matter" in getattr(self, "_sql", ""):
                return [("ws_other", b"{}")]
            return []

        def fetchone(self):
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    store = pg.PostgresMatterStore(connect=lambda: _Foreign(), sealer=None,
                                   workspace_id="ws_mine")
    with pytest.raises(TenantMismatch):
        store.load("mat_1")


def test_asking_this_store_for_another_workspaces_operation_is_refused():
    store = pg.PostgresMatterStore(connect=lambda: None, sealer=None,
                                   workspace_id="ws_mine")
    with pytest.raises(TenantMismatch):
        store.operation("ws_other", "key-1")
    with pytest.raises(TenantMismatch):
        store.claim_outbox("ws_other", worker="w1", lease_seconds=30)


# ===================== the outbox cannot contradict itself ==================

def _operation(**over) -> Operation:
    base = dict(idempotency_key="key-1", workspace_id="ws_a",
                advocate_id="adv@example.test", command="create-matter",
                matter_id="mat_1", request_digest=request_digest({"a": 1}))
    base.update(over)
    return Operation(**base)


def test_an_outbox_entry_for_another_workspace_is_refused():
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_b",
                        operation_key="key-1", kind="advise")
    problems = refuse_outbox(entry, workspace_id="ws_a",
                             operation=_operation())
    assert problems and "ws_b" in problems[0]


def test_an_outbox_entry_naming_another_operation_is_refused():
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_a",
                        operation_key="someone-elses", kind="advise")
    assert refuse_outbox(entry, workspace_id="ws_a", operation=_operation())


def test_an_outbox_entry_about_another_matter_is_refused():
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_a",
                        operation_key="key-1", kind="advise",
                        matter_id="mat_other")
    assert refuse_outbox(entry, workspace_id="ws_a", operation=_operation())


def test_a_consistent_entry_is_accepted():
    """The negative control: a refusal function that refused everything would
    satisfy the three tests above and the product would commit nothing."""
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_a",
                        operation_key="key-1", kind="advise",
                        matter_id="mat_1")
    assert refuse_outbox(entry, workspace_id="ws_a",
                         operation=_operation()) == []


def test_the_adapter_refuses_a_contradictory_entry_before_touching_the_database():
    """Refused BEFORE the transaction opens, so a bad entry cannot leave a
    half-written state behind."""
    store = pg.PostgresMatterStore(
        connect=lambda: pytest.fail("the database was opened"),
        sealer=None, workspace_id="ws_a")
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_b",
                        operation_key="key-1", kind="advise")
    with pytest.raises(OutboxRefused):
        store.commit_accepted(object(), expected_version=0,
                              operation=_operation(), outbox=(entry,))


# ============================== replay and conflict =========================

def test_one_key_with_the_same_request_is_a_replay():
    digest = request_digest({"message": "we act for the plaintiff"})
    recorded = _operation(request_digest=digest)
    assert recorded.replaying("create-matter", digest)
    assert not recorded.same_key_different_request("create-matter", digest)


def test_one_key_with_a_different_request_is_a_conflict_not_a_replay():
    """Returning the first answer would answer a question nobody asked."""
    recorded = _operation(request_digest=request_digest({"message": "one"}))
    assert recorded.same_key_different_request(
        "create-matter", request_digest({"message": "two"}))
    assert recorded.same_key_different_request(
        "delete-matter", recorded.request_digest)


def test_an_opening_command_carries_no_matter_and_that_is_the_hard_case():
    """BK-36's own next_action: idempotency must cover the OPENING turn, where
    there is no matter yet and a replay that mints a second one is invisible
    until somebody counts."""
    opening = _operation(matter_id="")
    assert opening.matter_id == ""
    assert opening.outcome is Outcome.ACCEPTED


# ================================ the states ================================

def test_an_ambiguous_outcome_is_never_retryable():
    """*Ambiguous external effects reconcile before retry* is a rule a call
    site can forget. A method that answers False cannot be forgotten."""
    assert Outcome.UNKNOWN.retryable() is False
    assert Outcome.UNKNOWN.settled() is False
    assert Outcome.not_established() is Outcome.UNKNOWN


def test_the_retryable_set_is_exactly_the_unfinished_ones():
    retryable = {o for o in Outcome if o.retryable()}
    assert retryable == {Outcome.ACCEPTED, Outcome.RUNNING}


def test_the_adapter_satisfies_the_transactional_port():
    for name in ("commit_accepted", "operation", "claim_outbox"):
        assert hasattr(pg.PostgresMatterStore, name)
    assert isinstance(TransactionalStorePort, type)


def test_the_schema_says_which_version_it_is():
    assert pg.SCHEMA_VERSION == 1
    assert any("nm_schema" in statement for statement in pg.DDL)
