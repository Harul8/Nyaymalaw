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
from nm.domain.restore import (
    EGRESS_KINDS,
    FAULT_KINDS,
    PHASE_ROLE,
    Compatibility,
    Fault,
    Isolation,
    Measured,
    Restore,
    RestoreRefused,
    Role,
    SinceSnapshot,
    Snapshot,
    compatibility,
    open_for_service,
    projection,
    refuse_open,
    refuse_role,
    sealed_from,
)

pytestmark = pytest.mark.class_a

TAKEN = "2026-09-14T09:00:00+00:00"
STARTED = "2026-09-14T09:05:00+00:00"
OPENED = "2026-09-14T09:12:00+00:00"


def _snapshot(**kw) -> Snapshot:
    base = dict(
        snapshot_id="snap_1", taken_at=TAKEN, schema=3,
        manifest_digest="d" * 64,
        matters=({"matter_id": "mat_a", "version": 4, "key_ref": "k_a"},),
        objects=({"asset_id": "as_1", "sha256": "a" * 64},),
        sessions=({"session_id": "ses_1", "advocate_id": "adv_1"},),
        jobs=({"job_id": "job_1", "outcome": "unknown"},))
    base.update(kw)
    return Snapshot(**base)


def _restore(**kw) -> Restore:
    snapshot = kw.pop("snapshot", None) or _snapshot()
    since = kw.pop("since", None) or SinceSnapshot(recorded_at=STARTED)
    base = dict(
        restore_id="rs_1", snapshot=snapshot, since=since,
        isolation=sealed_from(EGRESS_KINDS), build_schema=3,
        observed_manifest_digest=snapshot.manifest_digest,
        reconciled_jobs=tuple(str(j["job_id"]) for j in snapshot.jobs),
        measured=Measured(environment="local_rehearsal", started_at=STARTED,
                          opened_at=OPENED, snapshot_taken_at=TAKEN))
    base.update(kw)
    return Restore(**base)


# ================= 1. nothing leaves the building during one ================

def test_a_sealed_restore_opens():
    """THE POSITIVE CONTROL. A harness that refused every restore would prove
    nothing about the thirteen refusals below."""
    assert refuse_open(_restore()) == ()
    assert open_for_service(_restore()).opened is True


def test_all_four_egresses_must_be_off_and_three_is_not_enough():
    """PARTIAL is the state an operator reaches by turning three things off
    and believing they turned off four."""
    assert sealed_from(EGRESS_KINDS) is Isolation.SEALED
    assert sealed_from(EGRESS_KINDS[:3]) is Isolation.PARTIAL
    assert sealed_from(()) is Isolation.NOT_ASSERTED
    assert Isolation.not_established() is Isolation.NOT_ASSERTED
    for state in (Isolation.PARTIAL, Isolation.OPEN, Isolation.NOT_ASSERTED):
        assert state.safe_to_restore is False


def test_a_restore_that_could_dispatch_is_refused():
    why = refuse_open(_restore(isolation=sealed_from(EGRESS_KINDS[:2])))
    assert any("a restore that can send is a restore that will" in w
               for w in why)


def test_isolation_is_derived_from_what_is_off_not_handed_in():
    """A boolean an operator sets is a boolean an operator sets while looking
    at a different environment."""
    assert sealed_from(("external_egress", "notifications", "model_calls",
                        "job_dispatch")) is Isolation.SEALED
    assert sealed_from(("external_egress", "", "  ")) is Isolation.PARTIAL


# ==================== 2. least privilege, not one big role ==================

def test_the_reading_role_cannot_write():
    """THE ASSERTION THE WHOLE REHEARSAL RESTS ON. If the reader can write,
    the rehearsal was run by one identity wearing three hats."""
    assert refuse_role("write_records", Role.RESTORE_READER)
    assert refuse_role("write_records", Role.RESTORE_WRITER) == ""


def test_each_declared_phase_names_the_role_it_needs():
    for phase, role in PHASE_ROLE.items():
        assert refuse_role(phase, role) == "", phase
        assert refuse_role(phase, Role.NOT_ASSERTED)


def test_a_phase_nobody_declared_has_no_authority():
    why = refuse_role("do_whatever_is_needed", Role.RESTORE_WRITER)
    assert "not a restore phase this product declares" in why


def test_replaying_a_tombstone_is_not_the_writers_authority():
    """The retention officer replays erasures and holds; the writer restores
    records. Collapsing them is how a restore releases a hold on its way past."""
    assert refuse_role("replay_tombstones", Role.RESTORE_WRITER)
    assert refuse_role("replay_tombstones", Role.RETENTION_OFFICER) == ""


# ================== 3. the thirteen injections, one by one ==================

def test_the_declared_injections_are_thirteen_and_distinct():
    """Declared so the harness cannot quietly exercise twelve."""
    assert len(FAULT_KINDS) == 13 == len(set(FAULT_KINDS))


@pytest.mark.parametrize("kind", FAULT_KINDS)
def test_every_injected_fault_refuses_the_restore_and_names_itself(kind):
    """Each is a different way a restore goes wrong, and an operator told
    only "the restore failed" goes looking for whichever they thought of
    first."""
    hurt = _restore(faults=(Fault(kind=kind, subject="mat_a",
                                  why="injected by the rehearsal harness"),))
    why = refuse_open(hurt)
    assert any(w.startswith(f"{kind}:") for w in why), why
    with pytest.raises(RestoreRefused, match=kind):
        open_for_service(hurt)


def test_a_fault_records_why_rather_than_just_naming_itself():
    """A red light with no label sends an operator to read the harness
    instead of the snapshot."""
    with pytest.raises(ValueError, match="records no reason"):
        Fault(kind="missing_object", subject="as_1", why="   ")


def test_a_fault_nobody_declared_cannot_be_injected():
    """The thirteen are declared so the harness cannot quietly invent a
    fourteenth and report thirteen."""
    with pytest.raises(ValueError, match="not a declared restore fault"):
        Fault(kind="something_new", subject="as_1", why="invented")


# ============ 4. what was decided after the snapshot comes back on ==========

def test_an_erased_asset_cannot_reappear():
    """BK-88-AC1'S NEGATIVE CONTROL: *restore a snapshot predating erasure and
    revocation*. Restoring it is not a mistake about a file; it undoes a
    decision somebody made about a person's material."""
    since = SinceSnapshot(recorded_at=STARTED,
                          tombstones=({"asset_id": "as_1",
                                       "erased_at": "2026-09-14T09:02:00Z"},))
    why = refuse_open(_restore(since=since))
    assert any("would bring them back" in w and "as_1" in w for w in why)


def test_replaying_the_erasure_lets_it_open():
    since = SinceSnapshot(recorded_at=STARTED,
                          tombstones=({"asset_id": "as_1"},))
    assert refuse_open(_restore(since=since,
                                replayed_tombstones=("as_1",))) == ()


def test_a_revoked_session_is_not_handed_back():
    """An advocate who ended a session on a borrowed laptop, and a restore
    that hands the token back, is the whole of what that control was for."""
    since = SinceSnapshot(recorded_at=STARTED, revoked_sessions=("ses_1",))
    why = refuse_open(_restore(since=since))
    assert any("hand the access back" in w and "ses_1" in w for w in why)


def test_a_revoked_account_is_the_same_rule():
    since = SinceSnapshot(recorded_at=STARTED, revoked_accounts=("adv_9",))
    assert any("adv_9" in w for w in refuse_open(_restore(since=since)))


def test_a_hold_placed_after_the_snapshot_must_travel_with_the_restore():
    since = SinceSnapshot(recorded_at=STARTED,
                          holds=({"asset_id": "as_2", "reason": "legal hold"},))
    why = refuse_open(_restore(since=since))
    assert any("under a hold that the restored state does not carry" in w
               for w in why)


def test_a_released_hold_does_not_block():
    """THE POSITIVE CONTROL on the hold rule. A check that blocked on released
    holds would make every restore impossible after the first release."""
    since = SinceSnapshot(recorded_at=STARTED,
                          holds=({"asset_id": "as_2",
                                  "released_at": "2026-09-13"},))
    assert refuse_open(_restore(since=since)) == ()


def test_an_unreconciled_job_blocks_because_unknown_is_still_unknown():
    """A job that was UNKNOWN when the snapshot was taken is still unknown.
    Restoring it as retryable is a duplicate of something that may already
    have happened."""
    why = refuse_open(_restore(reconciled_jobs=()))
    assert any("still unknown" in w for w in why)


# ================== 5. schema compatibility, both directions ================

def test_an_older_snapshot_is_readable_and_a_newer_one_is_not():
    assert compatibility(2, 3) is Compatibility.BACKWARD_READABLE
    assert compatibility(3, 3) is Compatibility.SAME
    assert compatibility(4, 3) is Compatibility.FORWARD_UNREADABLE
    assert compatibility(0, 3) is Compatibility.NOT_ASSESSED
    assert Compatibility.not_established() is Compatibility.NOT_ASSESSED


def test_a_forward_incompatible_snapshot_is_refused_rather_than_read():
    """It reads as corruption rather than as a version, which is the worst
    available failure: an operator debugging bytes instead of a number."""
    why = refuse_open(_restore(snapshot=_snapshot(schema=9)))
    assert any("forward unreadable" in w for w in why)


def test_a_backward_readable_snapshot_opens():
    assert refuse_open(_restore(snapshot=_snapshot(schema=2))) == ()


def test_an_unassessed_schema_does_not_open():
    assert any("not assessed" in w
               for w in refuse_open(_restore(build_schema=0)))


# ======================= 6. the manifest describes it =======================

def test_a_manifest_that_does_not_describe_these_bytes_is_refused():
    why = refuse_open(_restore(observed_manifest_digest="e" * 64))
    assert any("does not describe these bytes" in w for w in why)


def test_an_unverified_manifest_is_not_a_verified_one():
    why = refuse_open(_restore(observed_manifest_digest=""))
    assert any("what is in this snapshot is not established" in w for w in why)


# ============ 7. RTO and RPO are measurements OF A REHEARSAL ================

def test_recovery_objectives_are_computed_from_observed_timestamps():
    m = Measured(environment="local_rehearsal", started_at=STARTED,
                 opened_at=OPENED, snapshot_taken_at=TAKEN)
    assert m.rto_seconds() == 7 * 60
    assert m.rpo_seconds() == 5 * 60


def test_a_rehearsal_never_reports_itself_as_a_deployment():
    """THE ASSERTION THAT STOPS THIS FILE BEING READ AS PRODUCTION EVIDENCE."""
    for env in ("local_rehearsal", "synthetic"):
        assert Measured(environment=env).is_a_deployment is False
        assert "NOT a deployment" in Measured(
            environment=env, started_at=STARTED, opened_at=OPENED,
            snapshot_taken_at=TAKEN).said()

    # AND AN UNNAMED ENVIRONMENT IS NOT A RECORD. A measurement whose
    # environment nobody stated is the one that gets read as production.
    with pytest.raises(ValueError, match="environment"):
        Measured(environment="   ")


def test_nothing_timed_is_not_an_objective_met():
    m = Measured(environment="local_rehearsal")
    assert m.rto_seconds() is None and m.rpo_seconds() is None
    assert "not the same as one that was met" in m.said()
    assert any("no recovery objective was measured" in w
               for w in refuse_open(_restore(measured=None)))


def test_an_unparseable_timestamp_measures_nothing_rather_than_zero():
    """Zero seconds is the best possible recovery objective and would be
    reported by a clock nobody could read."""
    m = Measured(environment="local_rehearsal", started_at="not a time",
                 opened_at=OPENED, snapshot_taken_at=TAKEN)
    assert m.rto_seconds() is None


# ================== 8. rollback after target-only writes ====================

def test_an_unreconcilable_pair_refuses_rollback_rather_than_permitting_it():
    """*we could not check* is the worst possible reason to proceed with an
    irreversible step, and the existing owner already answers it."""
    from backend.operations.migrate_store import Inventory, reconcile, refuse_rollback

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
    from backend.operations.migrate_store import (
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
    from backend.operations.migrate_store import (
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

def test_the_projection_carries_the_blockers_and_names_itself_a_rehearsal():
    shown = projection(_restore(isolation=Isolation.OPEN))
    assert shown["openable"] is False and shown["blockers"]
    assert shown["is_a_deployment"] is False
    assert "says nothing about an operated deployment" in shown["said"]


def test_a_successful_backup_is_not_restore_proof():
    """The packet's own sentence. A snapshot that exists says nothing about
    whether it can be read back, and this record only ever describes a read
    that was actually attempted."""
    never_read = _restore(observed_manifest_digest="")
    assert refuse_open(never_read)
    assert projection(never_read)["openable"] is False
