"""A RESTORE THAT CANNOT REVIVE WHAT WAS TAKEN AWAY. BK-42-AC4, BK-88-AC1. P38.

    from nm.domain.restore import Restore, Isolation, plan, refuse_open

WHAT A RESTORE IS FOR, AND WHAT IT MUST NOT BRING BACK
--------------------------------------------------------
A restore puts back the state of a file as it stood. Four things must NOT come
back with it, and each of them came back on somebody's system before it was
written down:

    A REVOKED SESSION. The snapshot predates the revocation, so the token in it
    is live again. An advocate who ended a session on a borrowed laptop, and a
    restore that hands it back, is the whole of what that control was for.

    AN ERASED ASSET. The snapshot predates the erasure. Restoring it is not a
    mistake about a file, it is undoing a decision somebody made about a
    person's material -- and nothing downstream will notice, because the asset
    looks exactly like every other asset.

    A RELEASED HOLD, or worse a hold that was placed after the snapshot and is
    now missing. A held asset restored without its hold is available.

    A JOB'S UNCERTAINTY. An operation that was UNKNOWN at snapshot time is
    still unknown; restoring it as ACCEPTED makes it retryable, and the retry
    is a duplicate of something that may already have happened.

So the restore is not a copy. It is a copy PLUS a replay of every tombstone,
hold and revocation recorded after the snapshot, and it refuses to open until
that replay is complete.

NOTHING LEAVES THE BUILDING DURING ONE
----------------------------------------
`Isolation` is not a setting on the restore, it is a precondition of it. A
restore that can send is a restore that will: the job queue it just rebuilt is
full of work that was already owed, and the first thing a worker does with a
restored outbox is deliver it. Every egress is off, and `refuse_open` will not
let a restored matter be served until they are.

LEAST PRIVILEGE IS THE POINT OF THE REHEARSAL
-----------------------------------------------
A restore run by an identity that can do everything proves that a restore is
possible, not that THIS deployment can perform one. `Role` is checked against
what each phase actually needs, and the reading role cannot write.

WHAT THIS MODULE CANNOT ESTABLISH
-----------------------------------
That any of it works on a deployment. There is no deployment. Every timestamp
here is observed from a local rehearsal, so `Measured.rto_seconds` is a real
measurement OF A REHEARSAL and is never a recovery objective met in an
operated environment. `production_measure` stays NOT RUN, and
`Measured.environment` says which it was.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Isolation(str, Enum):
    """Whether anything can leave while this runs.

    `NOT_ASSERTED` is the default and is refused: a restore whose isolation
    nobody stated is a restore that might dispatch, and the cost of being
    wrong is a real notification about a real matter sent from a rehearsal.
    """

    SEALED = "sealed"
    """Egress, notifications, model calls and job dispatch are all off."""

    PARTIAL = "partial"
    """Some are off. Named separately because it is the state an operator
    reaches by turning three of four things off and believing they turned off
    four."""

    OPEN = "open"
    NOT_ASSERTED = "not_asserted"

    @classmethod
    def not_established(cls) -> "Isolation":
        return cls.NOT_ASSERTED

    @property
    def safe_to_restore(self) -> bool:
        return self is Isolation.SEALED


#: THE FOUR THINGS THAT MUST BE OFF, named so a caller cannot turn off three
#: and report isolation. Read by `sealed_from` and by the served projection.
EGRESS_KINDS: tuple[str, ...] = (
    "external_egress", "notifications", "model_calls", "job_dispatch",
)


def sealed_from(disabled: tuple[str, ...]) -> Isolation:
    """DERIVED from what is actually off, never handed in.

    A boolean an operator sets is a boolean an operator sets while looking at
    a different environment.
    """
    off = {str(k).strip() for k in disabled if str(k).strip()}
    if not off:
        return Isolation.NOT_ASSERTED
    if off >= set(EGRESS_KINDS):
        return Isolation.SEALED
    return Isolation.PARTIAL


class Role(str, Enum):
    """The identity a restore phase runs as. NOT an all-powerful test user.

    A rehearsal run as root proves a restore is possible. It does not prove
    that the roles this deployment actually has can perform one, which is the
    only question BK-42-AC4 is asking.
    """

    RESTORE_READER = "restore_reader"
    """May read the snapshot and the manifest. MAY NOT WRITE."""

    RESTORE_WRITER = "restore_writer"
    """May write the restored records. May not release a hold."""

    RETENTION_OFFICER = "retention_officer"
    """May replay tombstones and holds. May not read matter content."""

    NOT_ASSERTED = "not_asserted"

    @classmethod
    def not_established(cls) -> "Role":
        return cls.NOT_ASSERTED


#: WHAT EACH PHASE NEEDS, declared once. A phase whose role is not listed is a
#: phase nobody decided the authority for, and `refuse_role` says so rather
#: than allowing it.
PHASE_ROLE: dict[str, Role] = {
    "read_snapshot": Role.RESTORE_READER,
    "verify_manifest": Role.RESTORE_READER,
    "write_records": Role.RESTORE_WRITER,
    "replay_tombstones": Role.RETENTION_OFFICER,
    "replay_revocations": Role.RETENTION_OFFICER,
}


def refuse_role(phase: str, acting: Role) -> str:
    """Why this identity may not perform this phase, or "".

    THE READER CANNOT WRITE, and that is the assertion the whole least-
    privilege rehearsal rests on: if the reading role can write, the rehearsal
    was run by one identity wearing three hats.
    """
    needed = PHASE_ROLE.get(phase)
    if needed is None:
        return (f"{phase!r} is not a restore phase this product declares, so "
                f"no authority for it has been decided")
    if acting is Role.NOT_ASSERTED:
        return (f"no role is recorded for {phase!r}; a restore run as an "
                f"unnamed identity proves a restore is possible and not that "
                f"this deployment can perform one")
    if acting is not needed:
        return (f"{phase!r} needs {needed.value} and is being attempted as "
                f"{acting.value}")
    return ""


class Compatibility(str, Enum):
    """Whether the snapshot's schema can be read by this build.

    BACKWARD and FORWARD are separate because they fail differently: an older
    snapshot may be readable and incomplete, and a newer one is unreadable in
    a way that looks like corruption.
    """

    SAME = "same"
    BACKWARD_READABLE = "backward_readable"
    FORWARD_UNREADABLE = "forward_unreadable"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Compatibility":
        return cls.NOT_ASSESSED

    @property
    def may_restore(self) -> bool:
        return self in (Compatibility.SAME, Compatibility.BACKWARD_READABLE)


def compatibility(snapshot_schema: int, build_schema: int) -> Compatibility:
    if snapshot_schema <= 0 or build_schema <= 0:
        return Compatibility.NOT_ASSESSED
    if snapshot_schema == build_schema:
        return Compatibility.SAME
    if snapshot_schema < build_schema:
        return Compatibility.BACKWARD_READABLE
    return Compatibility.FORWARD_UNREADABLE


#: THE THIRTEEN INJECTIONS, declared so the harness cannot quietly test twelve.
#: Each is a real way a restore goes wrong and each fails differently.
FAULT_KINDS: tuple[str, ...] = (
    "missing_data_key", "wrong_data_key", "missing_object", "corrupted_object",
    "stale_manifest", "stale_schema", "database_object_disagreement",
    "revoked_account", "erased_matter", "incomplete_job", "unknown_delivery",
    "failed_rollback", "cross_tenant",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Fault:
    """One thing wrong with a snapshot, named. BK-42-AC4's injections.

    A POPULATION AND NOT A BOOLEAN. "This restore failed" sends an operator
    looking; "the data key for mat_x is missing" tells them which of thirteen
    things happened.
    """

    kind: str
    subject: str
    why: str = ""

    def __post_init__(self) -> None:
        # `why` CARRIES A DEFAULT SO THE FIELD ORDER READS, and the blank rule
        # only reaches required fields -- so it is checked here. A fault with
        # no account of itself is a red light with no label, which sends an
        # operator to read the harness instead of the snapshot.
        if blank(self.why):
            raise ValueError(
                f"the {self.kind!r} fault on {self.subject!r} records no "
                f"reason; an operator cannot act on a named failure with no "
                f"account of what was wrong")
        if self.kind not in FAULT_KINDS:
            raise ValueError(
                f"{self.kind!r} is not a declared restore fault; the thirteen "
                f"are " + ", ".join(FAULT_KINDS))


@refuses_blank_text()
@dataclass(frozen=True)
class Snapshot:
    """What a backup holds, as the restore reads it."""

    snapshot_id: str
    taken_at: str
    schema: int = 0
    manifest_digest: str = ""
    matters: tuple[dict, ...] = ()
    objects: tuple[dict, ...] = ()
    sessions: tuple[dict, ...] = ()
    jobs: tuple[dict, ...] = ()


@dataclass(frozen=True)
class SinceSnapshot:
    """What happened AFTER the snapshot and must be replayed onto it.

    This is the half a copy does not have. Everything here is a decision
    somebody made that the snapshot predates, and a restore that omits it is
    a restore that undoes the decision.
    """

    revoked_sessions: tuple[str, ...] = ()
    revoked_accounts: tuple[str, ...] = ()
    tombstones: tuple[dict, ...] = ()
    holds: tuple[dict, ...] = ()
    recorded_at: str = ""


@refuses_blank_text()
@dataclass(frozen=True)
class Measured:
    """RTO and RPO FROM OBSERVED TIMESTAMPS, and where they were observed.

    `environment` is required and is the whole honesty of this record: a
    rehearsal's numbers are real measurements of a rehearsal. Reporting them
    against a recovery objective for a deployment that does not exist is the
    substitution this packet is written to refuse.
    """

    environment: str
    started_at: str = ""
    opened_at: str = ""
    snapshot_taken_at: str = ""

    def rto_seconds(self) -> float | None:
        return _elapsed(self.started_at, self.opened_at)

    def rpo_seconds(self) -> float | None:
        return _elapsed(self.snapshot_taken_at, self.started_at)

    @property
    def is_a_deployment(self) -> bool:
        """Whether these numbers are about an operated environment. FALSE for
        every environment this build can create."""
        return self.environment not in ("", "local_rehearsal", "synthetic")

    def said(self) -> str:
        rto, rpo = self.rto_seconds(), self.rpo_seconds()
        if rto is None or rpo is None:
            return ("Nothing was timed, so no recovery objective was measured "
                    "-- which is not the same as one that was met.")
        where = ("an operated deployment" if self.is_a_deployment
                 else f"a {self.environment or 'local'} rehearsal, NOT a "
                      f"deployment")
        return (f"Recovery took {rto:.0f}s and lost at most {rpo:.0f}s of "
                f"writes, measured on {where}.")


def _elapsed(start: str, end: str) -> float | None:
    from datetime import datetime

    if blank(start) or blank(end):
        return None
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except ValueError:
        return None
    return max(0.0, (b - a).total_seconds())


@refuses_blank_text()
@dataclass(frozen=True)
class Restore:
    """One rehearsed restoration, and everything that must be true to open it."""

    restore_id: str
    snapshot: Snapshot
    since: SinceSnapshot = field(default_factory=SinceSnapshot)
    isolation: Isolation = Isolation.NOT_ASSERTED
    build_schema: int = 0
    observed_manifest_digest: str = ""
    faults: tuple[Fault, ...] = ()
    replayed_tombstones: tuple[str, ...] = ()
    replayed_revocations: tuple[str, ...] = ()
    reconciled_jobs: tuple[str, ...] = ()
    measured: Measured | None = None
    opened: bool = False

    @property
    def schema_state(self) -> Compatibility:
        return compatibility(self.snapshot.schema, self.build_schema)


def refuse_open(r: Restore) -> tuple[str, ...]:
    """EVERY REASON THIS RESTORE MAY NOT BE SERVED. BK-42-AC4, BK-88-AC1.

    A population rather than a boolean: an operator told "the restore failed"
    goes looking, and what they find is whichever of thirteen things they
    thought of first.
    """
    out: list[str] = []

    if not r.isolation.safe_to_restore:
        out.append(
            f"isolation is {r.isolation.value}: a restore that can send is a "
            f"restore that will, because the queue it just rebuilt is full of "
            f"work that was already owed. Required off: "
            + ", ".join(EGRESS_KINDS))

    state = r.schema_state
    if not state.may_restore:
        out.append(
            f"the snapshot's schema is {state.value.replace('_', ' ')} "
            f"(snapshot {r.snapshot.schema}, this build {r.build_schema}); a "
            f"forward-incompatible snapshot reads as corruption rather than "
            f"as a version")

    if blank(r.observed_manifest_digest):
        out.append("the manifest was not verified, so what is in this "
                   "snapshot is not established")
    elif r.observed_manifest_digest != r.snapshot.manifest_digest:
        out.append(
            f"the manifest does not describe these bytes "
            f"({r.snapshot.manifest_digest[:12]}... recorded, "
            f"{r.observed_manifest_digest[:12]}... observed)")

    for fault in r.faults:
        out.append(f"{fault.kind}: {fault.subject} -- {fault.why}")

    # THE REPLAY. Everything decided after the snapshot must be back on before
    # anything is served, and an omission here is the restore undoing somebody
    # else's decision rather than failing.
    owed_tombs = {str(t.get("asset_id")) for t in r.since.tombstones}
    missing_tombs = sorted(owed_tombs - set(r.replayed_tombstones))
    if missing_tombs:
        out.append(
            "these assets were erased after the snapshot and the erasure has "
            "not been replayed, so restoring would bring them back: "
            + "; ".join(missing_tombs))

    owed_revs = set(r.since.revoked_sessions) | set(r.since.revoked_accounts)
    missing_revs = sorted(owed_revs - set(r.replayed_revocations))
    if missing_revs:
        out.append(
            "these sessions or accounts were revoked after the snapshot and "
            "the revocation has not been replayed, so the restore would hand "
            "the access back: " + "; ".join(missing_revs))

    held = {str(h.get("asset_id")) for h in r.since.holds
            if not h.get("released_at")}
    unheld = sorted(held - set(r.replayed_tombstones) - _held_now(r))
    if unheld:
        out.append(
            "these assets are under a hold that the restored state does not "
            "carry: " + "; ".join(unheld))

    unsettled = [j for j in r.snapshot.jobs
                 if str(j.get("job_id")) not in set(r.reconciled_jobs)]
    if unsettled:
        out.append(
            f"{len(unsettled)} job(s) in the snapshot have not been "
            f"reconciled. A job that was UNKNOWN when the snapshot was taken "
            f"is still unknown, and restoring it as retryable is a duplicate "
            f"of something that may already have happened")

    if r.measured is None:
        out.append("nothing was timed, so no recovery objective was measured")
    return tuple(out)


def _held_now(r: Restore) -> set[str]:
    return {str(h.get("asset_id")) for h in r.since.holds
            if h.get("replayed")}


def open_for_service(r: Restore) -> Restore:
    """Serve it, or refuse. THE REFUSAL IS THE ORDINARY OUTCOME.

    A restore that opens is one where every tombstone, hold and revocation
    recorded after the snapshot has been replayed and nothing can leave the
    building. Anything less is a restore that looks finished.
    """
    problems = refuse_open(r)
    if problems:
        raise RestoreRefused("; ".join(problems))
    return replace(r, opened=True)


class RestoreRefused(Exception):
    """A restored state that will not be served."""


def projection(r: Restore) -> dict:
    """What an operator is shown. THE REFUSALS TRAVEL WITH IT."""
    problems = refuse_open(r)
    measured = r.measured
    return {
        "restore_id": r.restore_id,
        "snapshot": r.snapshot.snapshot_id,
        "isolation": r.isolation.value,
        "sealed": r.isolation.safe_to_restore,
        "schema": r.schema_state.value,
        "faults": [f"{f.kind}: {f.subject}" for f in r.faults],
        "replayed_tombstones": len(r.replayed_tombstones),
        "replayed_revocations": len(r.replayed_revocations),
        "reconciled_jobs": len(r.reconciled_jobs),
        "openable": not problems,
        "blockers": list(problems),
        "measured": (measured.said() if measured else
                     "Nothing was timed, so no recovery objective was "
                     "measured."),
        "is_a_deployment": bool(measured and measured.is_a_deployment),
        "said": ("This is a rehearsal record. A restore that opens here has "
                 "been proved against synthetic infrastructure and says "
                 "nothing about an operated deployment."),
    }
