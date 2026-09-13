"""SCHEDULING PROACTIVE WORK, AND THE CONFLICT WATCH. BK-58-AC1/AC2. P45.

    from nm.core.service import due, schedule, cancel, watch_report

WHAT THIS OWNS AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------
It owns the DECISION to create work and the propagation of a cancellation. It
owns neither running the work nor delivering its result, because both already
have an owner:

    the durable job, its lease, its retries      nm/core/worker.py (P11)
    what became of it, including UNKNOWN         nm/domain/operation.py
    who may act at all                           nm/domain/authority.py
    the conflict screen itself                   nm/core/conflict.py
    what a change reaches                        nm/core/dependency.py (P18)

A second runner here would be a second answer to "did this send?", and the two
disagreeing is a duplicate notification -- which is the exact thing BK-58-AC1
names. So `schedule` returns a `ServiceJob` and stops.

AND THE BRIDGE TO P11's RUNNER IS NOT BUILT, which is a real gap and is stated
rather than papered over. A function composing an `OutboxEntry` from a job was
written here and deleted: nothing called it, because dispatch is CHOICE-09's
and CHOICE-09's connectors are disabled. A helper with no caller whose
docstring claims to bridge two systems is the shape B-050 records -- a contract
satisfied on paper while the work happened somewhere else, or nowhere.

THE AUTHORITY IS CHECKED THREE TIMES AND THAT IS NOT REDUNDANT
----------------------------------------------------------------
At scheduling, at dispatch, and before a result is accepted. The gaps between
them are real: an advocate revokes at 09:00, a job claimed at 08:59 runs at
09:01, and its result lands at 09:02. Checking once at the front means all
three of those happen under an authority that no longer exists.

THE IDEMPOTENCY KEY IS DERIVED FROM WHAT THE WORK IS ABOUT
------------------------------------------------------------
Not from a clock and not from a counter. Two triggers of the same cadence for
the same matter on the same due date ARE the same work, and a key that included
the attempt time would make them two -- which is a duplicate consequential
notification produced by the deduplication mechanism itself.

WHAT THE CONFLICT WATCH MAY SAY. BK-58-AC2
--------------------------------------------
`nm/core/conflict.py` finds the clash. What it may TELL the advocate about
another client's file is a different question, and this module answers it: the
party, the sides, and that it is on another of their files -- never that file's
name. An advocate holding both can look it up; a delegate, a locum or anyone
reading over a shoulder cannot, and "which other client is X suing" is exactly
the fact the screen must not hand out to establish that a clash exists.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from nm.domain.operation import Outcome, request_digest
from nm.domain.service import (
    AuthorityState,
    Notify,
    ServiceAuthority,
    Trigger,
    refuse_service,
)
from nm.domain.text import blank, clean, refuses_blank_text

#: The kinds of proactive work this product will schedule. DECLARED, so a
#: caller cannot invent one: an unknown kind is work nobody wrote a purpose
#: for, and the authority names a purpose.
SERVICE_KINDS: tuple[str, ...] = (
    "deadline_reminder",
    "conflict_recheck",
    "hearing_alert",
)


class ServiceRefused(Exception):
    """Proactive work that will not be scheduled, run or accepted."""


@refuses_blank_text()
@dataclass(frozen=True)
class ServiceJob:
    """One unit of authorised proactive work, and what became of it.

    `outcome` IS `nm.domain.operation.Outcome` AND NOT A NEW ENUM. It already
    carries accepted, running, cancel-requested, completed, failed and the
    UNKNOWN that a lost acknowledgement produces -- and `settled()` already
    answers that UNKNOWN is not settled. A second enum beside it would be two
    answers to "did this send?", which is the duplicate this packet exists to
    refuse.
    """

    job_id: str
    matter_id: str
    authority_id: str
    kind: str
    due_on: str
    idempotency_key: str
    outcome: Outcome = Outcome.ACCEPTED
    notified: Notify = Notify.NOT_STATED
    receipt: str = ""
    because: str = ""
    attempts: int = 0
    version: int = 1

    @property
    def claims_delivery(self) -> bool:
        """Only a COMPLETED job with a receipt claims the advocate was told.
        A completed job with nothing behind it is the shape that stops
        somebody watching a live period."""
        return self.outcome is Outcome.COMPLETED and not blank(self.receipt)

    def said(self) -> str:
        if self.outcome is Outcome.UNKNOWN:
            return ("This may or may not have reached you. It has not been "
                    "sent again, and nothing here treats it as delivered.")
        if self.outcome is Outcome.CANCEL_REQUESTED:
            return ("Cancellation was asked for. Work already running is not "
                    "erased by asking, and this says which it was.")
        if self.claims_delivery:
            return f"Sent, and the receipt says so: {self.receipt}."
        if self.outcome is Outcome.COMPLETED:
            return ("This ran and produced no receipt, so whether it reached "
                    "you is not established.")
        return f"This is {self.outcome.value}."


def idempotency_key(*, matter_id: str, kind: str, due_on: str,
                    authority_id: str) -> str:
    """WHAT THE WORK IS ABOUT, never when it was attempted. BK-58-AC1.

    Two triggers of the same cadence for the same matter on the same due date
    are the same work. A key carrying the attempt time would make them two,
    and the deduplication mechanism would be the thing producing the duplicate.
    """
    # A TUPLE, NOT A DICT. `request_digest` hashes `repr`, and a dict's repr
    # carries insertion order -- so two call sites building the same four
    # values in a different order would produce two keys for one unit of work,
    # which is the duplicate this function exists to prevent.
    return request_digest((
        "service-job", clean(matter_id), clean(kind), clean(due_on),
        clean(authority_id)))


def schedule(authority: ServiceAuthority | None, *, job_id: str, kind: str,
             due_on: str, today: str, existing: tuple[ServiceJob, ...] = (),
             ) -> ServiceJob:
    """Create one job, ONCE, and only under a current authority. BK-58-AC1.

    THE BACKLOG'S NEGATIVE CONTROL, both halves: *schedule monitoring without
    authority* is refused, and *replay the same due event* returns the job
    that already exists rather than a second one.
    """
    if kind not in SERVICE_KINDS:
        raise ServiceRefused(
            f"{kind!r} is not a kind of work this product schedules; the "
            f"declared kinds are {', '.join(SERVICE_KINDS)}")
    why = refuse_service(authority, today=today, doing=f"scheduling {kind}")
    if why:
        raise ServiceRefused(why)
    if authority is None:
        # NOT AN `assert`. `python -O` removes those, and a guard the
        # interpreter can be asked to skip is a guard that is not there --
        # which is defect shape S11 with a flag on it. `refuse_service`
        # returning "" for None would be a bug in it, and this is what would
        # notice rather than what would proceed.
        raise ServiceRefused(
            "no service authority was supplied and the refusal check did not "
            "catch it; nothing is scheduled")

    key = idempotency_key(matter_id=authority.matter_id, kind=kind,
                          due_on=due_on, authority_id=authority.authority_id)
    already = next((j for j in existing if j.idempotency_key == key), None)
    if already is not None:
        # NOT AN ERROR AND NOT A SECOND JOB. A replayed due event is the
        # ordinary case -- two schedulers, a restart, a retried click -- and
        # the honest answer is the job that already covers it.
        return already
    return ServiceJob(
        job_id=job_id, matter_id=authority.matter_id,
        authority_id=authority.authority_id, kind=kind, due_on=due_on,
        idempotency_key=key, notified=authority.notify)


def may_dispatch(authority: ServiceAuthority | None, job: ServiceJob, *,
                 today: str) -> str:
    """Checked again AT DISPATCH. Why not, or "".

    An authority revoked while this job sat in a queue must stop it here. The
    check at scheduling proves what was true then, and a queue is exactly the
    place where then and now are different.
    """
    if job.outcome is Outcome.CANCEL_REQUESTED:
        return "cancellation was requested for this job before it dispatched"
    if job.outcome.settled():
        return f"this job is already {job.outcome.value}"
    return refuse_service(authority, today=today,
                          doing=f"sending {job.kind}")


def may_accept(authority: ServiceAuthority | None, job: ServiceJob, *,
               today: str) -> str:
    """Checked a THIRD time, before a result is recorded on the file.

    The result of work done under an authority that has since been withdrawn
    is still a fact about what happened -- it is recorded -- but it must not
    be presented as current service. This is what says so.
    """
    if authority is None:
        return ("this result has no authority behind it and is recorded as "
                "an orphaned attempt rather than as service")
    if authority.state_on(today) is AuthorityState.REVOKED:
        return ("the authority was withdrawn while this ran; the attempt is "
                "recorded and no further work follows from it")
    return ""


def cancel(job: ServiceJob, *, at: str, because: str) -> ServiceJob:
    """Ask for a stop. ASKING IS NOT STOPPING, and the record says which.

    A job already running is not erased by a cancellation arriving; the
    request is recorded, the runner sees it before the effect, and a job that
    had already produced an effect resolves to UNKNOWN rather than to
    cancelled. Collapsing the two would let a cancelled-looking job have
    already sent.
    """
    if job.outcome.settled():
        return job
    if job.outcome is Outcome.UNKNOWN:
        # AN UNKNOWN JOB CANNOT BE CANCELLED INTO CERTAINTY. It may have
        # already reached somebody, and marking it cancelled would say it did
        # not.
        return replace(job, because=(
            f"{because}; the outcome was already unknown, so cancellation "
            f"stops anything further and settles nothing about what happened"),
            version=job.version + 1)
    return replace(job, outcome=Outcome.CANCEL_REQUESTED, because=because,
                   version=job.version + 1)


def revoke_reaches(jobs: tuple[ServiceJob, ...], *, authority_id: str,
                   at: str) -> tuple[ServiceJob, ...]:
    """Every unsettled job a revocation stops. BK-58-AC1's cancellation
    propagation, as one pass rather than a loop at each call site."""
    return tuple(
        cancel(j, at=at, because="the service authority was withdrawn")
        if j.authority_id == authority_id and not j.outcome.settled() else j
        for j in jobs)


def record_outcome(job: ServiceJob, *, outcome: Outcome, receipt: str = "",
                   because: str = "") -> ServiceJob:
    """What became of it. COMPLETED WITHOUT A RECEIPT DOES NOT CLAIM DELIVERY.

    The rule P30 keeps for a filing, at the other end of the product: a job
    that ran is not a message that arrived, and the state that says "we do not
    know" is `Outcome.UNKNOWN`, which `settled()` already refuses to treat as
    finished.
    """
    if outcome is Outcome.UNKNOWN and blank(because):
        raise ServiceRefused(
            "an unknown outcome records what was attempted and what came "
            "back; an advocate cannot act on an unknown with no account of it")
    return replace(job, outcome=outcome, receipt=receipt.strip(),
                   because=because.strip() or job.because,
                   attempts=job.attempts + 1, version=job.version + 1)


# ------------------------------------------------- the continuing watch ---

@refuses_blank_text()
@dataclass(frozen=True)
class WatchFinding:
    """One clash, said in a way that does not name the other file. BK-58-AC2.

    `other_matter_id` IS DELIBERATELY ABSENT FROM THIS TYPE. A field that
    carried it would be rendered by somebody, and the criterion is not "do not
    usually show it" -- it is that another client's matter is not exposed. The
    advocate holds both files and can find the other one; what they get here is
    that there IS one, on which party, and on which side.
    """

    party: str
    side_here: str
    side_elsewhere: str
    reason: str

    def said(self) -> str:
        return (f"{self.party} is {self.side_here} on this matter and "
                f"{self.side_elsewhere} on another of your files. I am not "
                f"naming that file here; open your matter list to find it.")


def restricted_findings(screen_detail: str) -> tuple[str, ...]:
    """Every line of a conflict screen that names another matter.

    THE POPULATION IS THE SCREEN'S OWN OUTPUT rather than a fixture, so a
    future phrasing that reintroduces the name is caught by the same check.
    """
    return tuple(line.strip() for line in str(screen_detail).split(";")
                 if " on '" in line or ' on "' in line)


def watch_report(screen, authority: ServiceAuthority | None, *,
                 today: str) -> dict:
    """What the advocate is shown about the continuing watch. BK-58.

    IT NAMES THE OWNER AND THE NEXT ACTION, and it never claims the watch is
    continuous. Where no authority is recorded, the report says the screen
    stands as at the last time somebody looked -- which is the truth, and is
    what stops an advocate believing a clash found tomorrow will find them.
    """
    state = (authority.state_on(today) if authority is not None
             else AuthorityState.NOT_RECORDED)
    return {
        "screen_state": getattr(getattr(screen, "state", None), "value", "not_assessed"),
        "authority": state.value,
        "continuing": state.permits_work,
        "owner": (authority.responsible_actor if authority is not None
                  and authority.responsible_actor else "NOT RECORDED"),
        "next_action": (
            "nothing is scheduled; re-run the screen when you add a party"
            if not state.permits_work else
            "the screen is re-run when a party or a material circumstance "
            "changes on this file"),
        "said": (authority.said(today) if authority is not None else
                 "No proactive work is authorised on this matter. This screen "
                 "stands as at the last time it ran and nothing re-runs it on "
                 "your behalf."),
        "leaks_another_matter": list(
            restricted_findings(getattr(screen, "detail", "") or "")),
    }


# ------------------------------------------------------------ persistence ---

def authority_as_dict(a: ServiceAuthority) -> dict:
    return {"schema": 1, "authority_id": a.authority_id,
            "matter_id": a.matter_id,
            "responsible_actor": a.responsible_actor, "purpose": a.purpose,
            "trigger": a.trigger.value, "cadence": a.cadence,
            "notify": a.notify.value, "granted_by": a.granted_by,
            "granted_at": a.granted_at, "expires_on": a.expires_on,
            "revoked_at": a.revoked_at, "revoked_by": a.revoked_by,
            "version": a.version}


def authority_from_dict(value) -> ServiceAuthority | None:
    if not isinstance(value, dict) or not value.get("authority_id"):
        return None

    def _enum(kind, raw, fallback):
        try:
            return kind(str(raw or ""))
        except ValueError:
            # AN UNREADABLE TRIGGER OR PREFERENCE IS NOT STATED, never a
            # default that runs. The direction every `from_stored` in this
            # product takes: the reading that does less is the safe one.
            return fallback

    return ServiceAuthority(
        authority_id=str(value["authority_id"]),
        matter_id=str(value.get("matter_id") or ""),
        responsible_actor=str(value.get("responsible_actor") or ""),
        purpose=str(value.get("purpose") or ""),
        trigger=_enum(Trigger, value.get("trigger"), Trigger.NOT_STATED),
        cadence=str(value.get("cadence") or ""),
        notify=_enum(Notify, value.get("notify"), Notify.NOT_STATED),
        granted_by=str(value.get("granted_by") or ""),
        granted_at=str(value.get("granted_at") or ""),
        expires_on=str(value.get("expires_on") or ""),
        revoked_at=str(value.get("revoked_at") or ""),
        revoked_by=str(value.get("revoked_by") or ""),
        version=int(value.get("version") or 1))


def authorities(matter) -> tuple[ServiceAuthority, ...]:
    return tuple(a for a in (
        authority_from_dict(v)
        for v in getattr(matter, "service_authorities", ()) or ())
        if a is not None)


def put_authority(existing: tuple[ServiceAuthority, ...],
                  a: ServiceAuthority) -> tuple[ServiceAuthority, ...]:
    if any(x.authority_id == a.authority_id for x in existing):
        return tuple(a if x.authority_id == a.authority_id else x
                     for x in existing)
    return (*existing, a)


def current_authority(matter, today: str) -> ServiceAuthority | None:
    """The one authority that permits work right now, or None.

    A MATTER MAY HOLD SEVERAL and only a granted one counts. Returning a
    revoked authority "so the caller can check" is how a caller forgets to.
    """
    return next((a for a in authorities(matter)
                 if a.state_on(today) is AuthorityState.GRANTED), None)


def authority_projection(a: ServiceAuthority, today: str) -> dict:
    """What the advocate is shown. IT NEVER CLAIMS CONTINUOUS MONITORING."""
    state = a.state_on(today)
    return {"authority_id": a.authority_id, "state": state.value,
            "responsible_actor": a.responsible_actor, "purpose": a.purpose,
            "trigger": a.trigger.value, "cadence": a.cadence,
            "notify": a.notify.value, "granted_by": a.granted_by,
            "granted_at": a.granted_at, "expires_on": a.expires_on,
            "revoked_at": a.revoked_at,
            "permits_work": state.permits_work,
            "still_needed": list(a.absent()),
            "version": a.version,
            "said": a.said(today)}


def job_as_dict(j: ServiceJob) -> dict:
    return {"schema": 1, "job_id": j.job_id, "matter_id": j.matter_id,
            "authority_id": j.authority_id, "kind": j.kind,
            "due_on": j.due_on, "idempotency_key": j.idempotency_key,
            "outcome": j.outcome.value, "notified": j.notified.value,
            "receipt": j.receipt, "because": j.because,
            "attempts": j.attempts, "version": j.version}


def job_from_dict(value) -> ServiceJob | None:
    if not isinstance(value, dict) or not value.get("job_id"):
        return None
    try:
        outcome = Outcome(str(value.get("outcome") or ""))
    except ValueError:
        # AN UNREADABLE OUTCOME IS UNKNOWN, never completed. A job whose
        # record cannot be read is a job nobody can say reached anybody.
        outcome = Outcome.UNKNOWN
    try:
        notified = Notify(str(value.get("notified") or ""))
    except ValueError:
        notified = Notify.NOT_STATED
    return ServiceJob(
        job_id=str(value["job_id"]),
        matter_id=str(value.get("matter_id") or ""),
        authority_id=str(value.get("authority_id") or ""),
        kind=str(value.get("kind") or ""),
        due_on=str(value.get("due_on") or ""),
        idempotency_key=str(value.get("idempotency_key") or ""),
        outcome=outcome, notified=notified,
        receipt=str(value.get("receipt") or ""),
        because=str(value.get("because") or ""),
        attempts=int(value.get("attempts") or 0),
        version=int(value.get("version") or 1))


def jobs(matter) -> tuple[ServiceJob, ...]:
    return tuple(j for j in (job_from_dict(v)
                             for v in getattr(matter, "service_jobs", ()) or ())
                 if j is not None)


def put_job(existing: tuple[ServiceJob, ...],
            job: ServiceJob) -> tuple[ServiceJob, ...]:
    """Replace by IDEMPOTENCY KEY, not by job id.

    Two schedulers that both minted an id for the same work would otherwise
    store two rows for one unit of work, and the advocate would be told twice
    -- which is the duplicate consequential notification, arriving through the
    store rather than through the wire.
    """
    if any(x.idempotency_key == job.idempotency_key for x in existing):
        return tuple(job if x.idempotency_key == job.idempotency_key else x
                     for x in existing)
    return (*existing, job)


def job_projection(j: ServiceJob) -> dict:
    return {"job_id": j.job_id, "kind": j.kind, "due_on": j.due_on,
            "outcome": j.outcome.value, "settled": j.outcome.settled(),
            "claims_delivery": j.claims_delivery,
            "notified": j.notified.value, "attempts": j.attempts,
            "because": j.because, "version": j.version,
            "said": j.said()}


def conflict_screen_of(matter):
    """This matter's stored conflict screen, or None.

    READ FROM THE FILE rather than re-run, because re-running here would give
    the watch report a different answer from the one the advocate was shown on
    their last turn -- two screens disagreeing about the same file.
    """
    from nm.core.screens import ScreenKind, from_stored

    stored = getattr(matter, "screens", ()) or ()
    try:
        # THE WHOLE POPULATION, THROUGH ITS OWNER. `from_stored` raises on a
        # malformed record rather than dropping it, because a dropped screen
        # invents a clean one -- so a file whose screens cannot be read
        # produces no watch report rather than a reassuring empty one.
        screens = from_stored(tuple(stored))
    except ValueError:
        return None
    return next((s for s in screens if s.kind is ScreenKind.CONFLICT), None)
