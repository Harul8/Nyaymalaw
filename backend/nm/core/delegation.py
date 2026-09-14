"""Admission and acceptance for bounded delegation. P47. BK-92-AC1/AC2.

    from nm.core.delegation import Ledger, admit, accept

THE APPLICATION OWNS THESE TWO DECISIONS, NOT THE AGENT
--------------------------------------------------------
autonomy.json `control_boundary` puts `admission`, `budget_reservations`,
`version_checks`, `job_lifecycle` and `publication` under `application_owned`.
So these are deterministic functions over typed state, not something a model
proposes: a specialist may ASK to be dispatched and may RETURN a result, but
whether it is admitted, and whether its result is accepted, is decided here.

    A prompt is not a guard. The mechanism that refuses an over-budget
    dispatch, a stale result, a forged result or a source that tries to grant
    a processor is code the agent cannot talk its way past.

TWO ENTRY POINTS, AND WHY THEY FAIL IN OPPOSITE DIRECTIONS
------------------------------------------------------------
`admit` fails CLOSED: an expansion, an over-cap reservation, a too-deep or
too-concurrent dispatch is refused before any protected work runs (BK-92-AC1).
`accept` fails CLOSED too, but on the other side of the work: a stale, revoked,
cancelled or forged result is refused before it can be published, and a result
that is merely PARTIAL or FAILED is accepted only as visibly INCOMPLETE, never
as clean (BK-92-AC2). Findings are taken as CANDIDATES for the one canonical
version-checked writer, and a conflict between two candidates stays CONTESTED
rather than being voted into truth.

THE BUDGET IS ONE SHARED LEDGER, ATOMIC, AND NEVER RESET PER CHILD
-------------------------------------------------------------------
`Ledger` reserves across every dimension at once: if any dimension would go
over its cap the whole reservation is refused and nothing is taken (so two
children admitted concurrently cannot each pass a check the pair fails). Spend
accumulates across children and retries; only the concurrency SLOT is released
when a child finishes, because a finished child still spent what it spent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nm.domain.delegation import (
    Finding,
    Mandate,
    Result,
    Task,
)


class Ledger:
    """The shared, atomic, task-wide budget. autonomy.json
    `budget_accounting: atomic_task_wide_reservation_includes_retries_and_children`.

    Caps are per dimension (BUDGET_DIMENSIONS). `concurrency` is the live count
    of admitted-and-unfinished specialists; every other dimension is cumulative
    SPEND that a retry or a child adds to and nothing subtracts from -- resetting
    it per child is the exact defect BK-92-AC1's negative control plants.
    """

    def __init__(self, caps: dict):
        self._caps = {str(k): float(v) for k, v in (caps or {}).items()}
        self._reserved: dict[str, float] = {}
        self._active = 0
        self._accepted: set[str] = set()

    @property
    def active(self) -> int:
        return self._active

    def reserve(self, task: Task) -> list[str]:
        """Reserve this task's budget atomically. Returns refusal reasons; on
        any reason NOTHING is taken. One caller admits at a time, so the
        check-and-take is not interleaved -- the atomicity that matters is that
        a partial reservation never lands."""
        req = {str(k): float(v) for k, v in (task.requested_budget or {}).items()}
        bad: list[str] = []

        conc_cap = self._caps.get("concurrency")
        if conc_cap is not None and self._active + 1 > conc_cap:
            bad.append(f"admitting this specialist would run {self._active + 1} "
                       f"concurrently, over the shared cap of {int(conc_cap)}")
        for dim, amount in req.items():
            cap = self._caps.get(dim)
            if cap is None:
                continue
            already = self._reserved.get(dim, 0.0)
            if already + amount > cap:
                bad.append(f"{dim}: reserving {amount} on top of {already} "
                           f"exceeds the shared cap {cap}")
        if bad:
            return bad

        for dim, amount in req.items():
            self._reserved[dim] = self._reserved.get(dim, 0.0) + amount
        self._active += 1
        return []

    def release_slot(self) -> None:
        """A specialist finished. Free its CONCURRENCY slot -- but keep every
        other reservation, because the spend is real whether or not the child
        succeeded (retries included)."""
        self._active = max(0, self._active - 1)

    def already_accepted(self, attempt_id: str) -> bool:
        return attempt_id in self._accepted

    def mark_accepted(self, attempt_id: str) -> None:
        self._accepted.add(attempt_id)

    def receipt(self) -> dict:
        return {"reserved": dict(self._reserved), "active": self._active}


@dataclass(frozen=True)
class Admission:
    """Whether a delegated task may run. `task` carries the NARROWED mandate
    when admitted -- never more than parent and server both allow."""

    admitted: bool
    reasons: tuple[str, ...] = ()
    task: Task | None = None


def admit(parent: Mandate, request: Task, server: Mandate, ledger: Ledger,
          *, specialists_may_delegate: bool = False) -> Admission:
    """The one admission boundary. BK-92-AC1.

    Refuses, before any protected processing and with the actual reason, a task
    whose mandate expands beyond the parent OR the server, that would exceed the
    depth or concurrency profile, that a specialist is not permitted to spawn,
    or whose budget will not fit the shared ledger. Only when nothing refuses is
    the budget reserved and the narrowed task returned.
    """
    reasons: list[str] = []
    reasons += [f"beyond the parent's authority: {r}"
                for r in request.mandate.expansions_over(parent)]
    reasons += [f"beyond server policy: {r}"
                for r in request.mandate.expansions_over(server)]

    if request.depth > parent.max_depth:
        reasons.append(f"delegation depth {request.depth} exceeds the profile "
                       f"cap of {parent.max_depth}")
    # A SPECIALIST MAY NOT DELEGATE (initial profile). A child dispatched by a
    # specialist is at depth >= 2, which the cap of 1 already refuses; this names
    # the reason directly rather than leaving it to read as a bare depth error.
    if not specialists_may_delegate and request.depth > 1:
        reasons.append("a specialist may not itself delegate; only the lead "
                       "dispatches specialists in this profile")

    if not reasons and ledger.active >= parent.max_concurrent:
        reasons.append(f"{ledger.active} specialists already run, at the "
                       f"concurrency cap of {parent.max_concurrent}")

    if reasons:
        return Admission(False, tuple(reasons), None)

    narrowed = request.mandate.intersect(parent).intersect(server)
    from dataclasses import replace
    admitted_task = replace(request, mandate=narrowed)
    budget_reasons = ledger.reserve(admitted_task)
    if budget_reasons:
        return Admission(False, tuple(budget_reasons), None)
    return Admission(True, (), admitted_task)


@dataclass(frozen=True)
class Acceptance:
    """What the one acceptance path did with a result. BK-92-AC2.

    `candidates` are findings offered to the canonical writer -- never accepted
    truth here. `contested` are pairs that disagree on the same subject and are
    KEPT, not voted. `incomplete` is set for any non-COMPLETED status so a
    failed specialist cannot report a clean whole. `duplicate` means the attempt
    was already accepted and no effect is applied twice.
    """

    accepted: bool
    incomplete: bool = False
    duplicate: bool = False
    candidates: tuple[Finding, ...] = ()
    contested: tuple[tuple[Finding, Finding], ...] = ()
    refused_deltas: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    receipt: dict = field(default_factory=dict)


def accept(result: Result, task: Task, *, current_mandate_version: int,
           revoked_epochs: frozenset[int] = frozenset(),
           cancelled: bool = False, ledger: Ledger | None = None,
           prior_findings: tuple[Finding, ...] = ()) -> Acceptance:
    """The sole version-checked acceptance path. BK-92-AC2.

    Order matters and every branch fails toward NOT publishing:

      1. FORGED -- no producer, no attempt id, or a task id that is not this
         task's. A result that cannot be authenticated is refused outright.
      2. DUPLICATE -- an attempt already accepted returns the prior outcome and
         applies nothing again (idempotent delivery, retry, worker restart).
      3. STALE -- the result rests on a mandate version that has moved.
      4. REVOKED / CANCELLED -- the permission epoch was revoked, or the task
         was cancelled; a late result is not published.
      5. EXPANDING DELTA -- a proposed change that would add a tool, processor
         or matter is refused; source text and model proposals grant no
         authority.
      6. INCOMPLETE -- a PARTIAL/FAILED/UNAVAILABLE result is accepted only as
         visibly incomplete; findings still become candidates.
      7. CONTESTED -- a candidate that disagrees with a prior finding on the
         same subject is kept beside it, never merged or voted.
    """
    forged = result.forged_against or (
        "" if result.task_id == task.task_id else
        f"result task id {result.task_id!r} does not match {task.task_id!r}")
    if forged:
        return Acceptance(False, incomplete=True, reasons=(forged,))

    if ledger is not None and ledger.already_accepted(result.attempt_id):
        return Acceptance(True, incomplete=not result.status.is_clean(),
                          duplicate=True,
                          reasons=("this attempt was already accepted; the "
                                   "prior outcome stands and nothing is applied "
                                   "twice",),
                          receipt=dict(result.budget_used))

    reasons: list[str] = []
    if result.mandate_version != current_mandate_version:
        reasons.append(f"the result rests on mandate version "
                       f"{result.mandate_version}, and the mandate is now at "
                       f"{current_mandate_version}; it is stale")
    if cancelled or result.cancellation_epoch != task.cancellation_epoch:
        reasons.append("the task was cancelled; a result arriving after "
                       "cancellation is not published")
    if result.permission_epoch in revoked_epochs:
        reasons.append("the permission that authorised this result has since "
                       "been revoked; it is not published")
    if reasons:
        return Acceptance(False, incomplete=True, reasons=tuple(reasons))

    refused = tuple(
        "a proposed change would expand the mandate (add a tool, processor or "
        "matter); source text and model proposals confer no authority"
        for delta in result.proposed_deltas if delta.expands())

    prior_by_subject = {f.subject: f for f in prior_findings if f.subject}
    candidates: list[Finding] = []
    contested: list[tuple[Finding, Finding]] = []
    for finding in result.findings:
        if (finding.subject and finding.subject in prior_by_subject
                and prior_by_subject[finding.subject].claim != finding.claim):
            contested.append((prior_by_subject[finding.subject], finding))
        candidates.append(finding)

    if ledger is not None:
        ledger.mark_accepted(result.attempt_id)

    return Acceptance(
        accepted=True,
        incomplete=not result.status.is_clean(),
        candidates=tuple(candidates),
        contested=tuple(contested),
        refused_deltas=refused,
        receipt=(ledger.receipt() if ledger is not None
                 else dict(result.budget_used)))


def whole_task_clean(outcomes: tuple[tuple, ...],
                     required_roles: tuple = ()) -> bool:
    """A parent's whole task is clean only if every specialist it relied on
    returned a COMPLETED result -- one failed or missing required child makes
    the whole incomplete (`specialist_failure: visible_incomplete_not_clean`).

    `outcomes` is (Role, ResultStatus) pairs -- role lives on the Task, not the
    Result, so the caller pairs them. A parent that ran NO specialists (ordinary
    work) is clean: the population is the REQUIRED roles, so an empty requirement
    with no outcomes is clean, while a required role with no COMPLETED outcome
    never is."""
    if not all(status.is_clean() for _role, status in outcomes):
        return False
    completed_roles = {role for role, status in outcomes if status.is_clean()}
    return all(role in completed_roles for role in required_roles)
