"""A RESTORE CANNOT REVIVE WHAT WAS TAKEN AWAY. BK-42-AC3/AC4/AC6, BK-83-AC3,
BK-85-AC2, BK-88-AC1. P38.

WHAT THESE DEFEND
-------------------
A restore is not a copy. Four things must not come back with it, and each one
looks exactly like ordinary restored state once it has:

    a revoked session, live again because the snapshot predates the revocation;
    an erased asset, back because the snapshot predates the erasure;
    a held asset, available because the hold was placed afterwards;
    a job that was UNKNOWN, retryable again -- and the retry is a duplicate of
    something that may already have happened.

Nothing downstream notices any of them, which is why the refusal has to be at
the point the restored state is opened rather than anywhere later.

WHAT THIS SUITE CANNOT ESTABLISH, AND SAYS SO IN ITS OWN ASSERTIONS
----------------------------------------------------------------------
That any of it works on a deployment. There is no deployment, no PostgreSQL
service and no KMS. Every fixture here is synthetic, `Measured.environment` is
`local_rehearsal`, and `test_a_rehearsal_never_reports_itself_as_a_deployment`
is the assertion that stops this file being read as production evidence.
`production_measure` stays NOT RUN on all six criteria.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a

TAKEN = "2026-09-14T09:00:00+00:00"
STARTED = "2026-09-14T09:05:00+00:00"
OPENED = "2026-09-14T09:12:00+00:00"


# ================= 1. nothing leaves the building during one ================


# ==================== 2. least privilege, not one big role ==================


# ================== 3. the thirteen injections, one by one ==================


# ============ 4. what was decided after the snapshot comes back on ==========


# ================== 5. schema compatibility, both directions ================


# ======================= 6. the manifest describes it =======================


# ============ 7. RTO and RPO are measurements OF A REHEARSAL ================


# ================== 8. rollback after target-only writes ====================

def test_an_unreconcilable_pair_refuses_rollback_rather_than_permitting_it():
    """*we could not check* is the worst possible reason to proceed with an
    irreversible step, and the existing owner already answers it."""
    from operations.migrate_store import Inventory, reconcile, refuse_rollback

    unreadable = Inventory(root="tgt", assessed=False,
                           why="the target store could not be read")
    source = Inventory(root="src", assessed=True, matters={})
    reasons = refuse_rollback(source, unreadable,
                              reconcile(source, unreadable))
    assert any("cannot be shown that rolling back would lose nothing" in r
               for r in reasons), reasons


def test_rollback_is_refused_when_the_target_holds_an_acknowledged_write():
    """BK-83-AC3'S NEGATIVE CONTROL: *abort a cutover or roll back after
    target-only writes*. The existing migration owner answers this; the
    rehearsal drives it rather than reimplementing it."""
    from operations.migrate_store import (
        Inventory,
        MatterRecord,
        reconcile,
        refuse_rollback,
        target_only,
    )

    kept = MatterRecord(matter_id="mat_a", version=4, content_digest="a",
                        key_ref="k", readable=True)
    added = MatterRecord(matter_id="mat_b", version=1, content_digest="b",
                         key_ref="k", readable=True)
    source = Inventory(root="src", assessed=True, matters={"mat_a": kept})
    target = Inventory(root="tgt", assessed=True,
                       matters={"mat_a": kept, "mat_b": added})
    assert list(target_only(source, target)) == ["mat_b"]
    # A POPULATION OF REASONS, not an exception: the operator needs to know
    # WHICH matters would be lost, and an exception carries one sentence.
    reasons = refuse_rollback(source, target, reconcile(source, target))
    assert any("accepted work" in r and "mat_b" in r for r in reasons), reasons


def test_rollback_is_permitted_when_the_target_added_nothing():
    """THE POSITIVE CONTROL. A refusal that fired on every rollback would stop
    the only safe recovery there is."""
    from operations.migrate_store import (
        Inventory,
        MatterRecord,
        reconcile,
        refuse_rollback,
        target_only,
    )

    rows = {"mat_a": MatterRecord(matter_id="mat_a", version=4,
                                  content_digest="a", key_ref="k",
                                  readable=True)}
    source = Inventory(root="src", assessed=True, matters=dict(rows))
    target = Inventory(root="tgt", assessed=True, matters=dict(rows))
    assert list(target_only(source, target)) == []
    assert refuse_rollback(source, target, reconcile(source, target)) == []


# ======= 9. the projection says what a rehearsal record actually is ========


