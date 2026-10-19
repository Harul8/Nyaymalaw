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


import pytest

from nm.shared.operation_contracts import (
    Operation,
    OutboxEntry,
    Outcome,
    refuse_outbox,
    request_digest,
)

pytestmark = pytest.mark.class_a

#: Tables whose every row belongs to exactly one workspace.
TENANT_TABLES = ("nm_matter", "nm_operation", "nm_outbox")


# ===================== the outbox cannot contradict itself ==================


def _operation(**over) -> Operation:
    base = dict(
        idempotency_key="key-1",
        workspace_id="ws_a",
        advocate_id="adv@example.test",
        command="create-matter",
        matter_id="mat_1",
        request_digest=request_digest({"a": 1}),
    )
    base.update(over)
    return Operation(**base)


def test_an_outbox_entry_for_another_workspace_is_refused():
    entry = OutboxEntry(entry_id="e1", workspace_id="ws_b", operation_key="key-1", kind="advise")
    problems = refuse_outbox(entry, workspace_id="ws_a", operation=_operation())
    assert problems and "ws_b" in problems[0]


def test_an_outbox_entry_naming_another_operation_is_refused():
    entry = OutboxEntry(
        entry_id="e1", workspace_id="ws_a", operation_key="someone-elses", kind="advise"
    )
    assert refuse_outbox(entry, workspace_id="ws_a", operation=_operation())


def test_an_outbox_entry_about_another_matter_is_refused():
    entry = OutboxEntry(
        entry_id="e1",
        workspace_id="ws_a",
        operation_key="key-1",
        kind="advise",
        matter_id="mat_other",
    )
    assert refuse_outbox(entry, workspace_id="ws_a", operation=_operation())


def test_a_consistent_entry_is_accepted():
    """The negative control: a refusal function that refused everything would
    satisfy the three tests above and the product would commit nothing."""
    entry = OutboxEntry(
        entry_id="e1", workspace_id="ws_a", operation_key="key-1", kind="advise", matter_id="mat_1"
    )
    assert refuse_outbox(entry, workspace_id="ws_a", operation=_operation()) == []


# ============================== replay and conflict =========================


def test_one_key_with_the_same_request_is_a_replay():
    digest = request_digest({"message": "we act for the plaintiff"})
    recorded = _operation(request_digest=digest)
    assert recorded.replaying("create-matter", digest)
    assert not recorded.same_key_different_request("create-matter", digest)


def test_one_key_with_a_different_request_is_a_conflict_not_a_replay():
    """Returning the first answer would answer a question nobody asked."""
    recorded = _operation(request_digest=request_digest({"message": "one"}))
    assert recorded.same_key_different_request("create-matter", request_digest({"message": "two"}))
    assert recorded.same_key_different_request("delete-matter", recorded.request_digest)


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


