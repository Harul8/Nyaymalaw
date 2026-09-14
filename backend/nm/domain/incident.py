"""A REHEARSAL IS EVIDENCE ABOUT PEOPLE, NOT ABOUT A POLICY DOCUMENT. P40.
BK-85-AC5, BK-88-AC3.

    from nm.domain.incident import Exercise, refuse_close

WHAT THIS IS FOR
------------------
An incident policy is a document. What BK-85-AC5 asks for is a REHEARSAL: the
named on-call and legal owners actually reached, the detection time actually
recorded, the reviewed clock actually run, containment actually authorised and
evidence actually taken into custody. P40's own declared expected failure says
it in one line -- *evidence includes people/contact results, not just an
incident-policy document* -- so this module is built so that a record with no
people in it cannot read as a completed exercise.

THE CLOCKS ARE NOT IN THIS FILE
---------------------------------
`docs/blueprint/evaluations.json` holds `incident_response`, which carries the
reporting clocks from the dated India applicability review in
`docs/blueprint/SECURITY_PRIVACY.md` §§1, 10 -- their hours, what starts them,
whether anybody has determined they apply, and the instrument each comes from.
This module READS them. Writing "six hours" into Python would be inventing a
legal notification period the moment the review is superseded, and the copy
that drifts is whichever is read less.

    AND THEY ARE NOT INTERCHANGEABLE. The CERT-In initial report and the DPDP
    Board update are different duties on different triggers with different
    scopes, and a single "breach deadline" that averaged them would be wrong
    in both directions. Each is its own row and each is decided separately.

APPLICABILITY IS A THIRD STATE, AND IT IS THE DEFAULT
-------------------------------------------------------
Whether either regime covers this deployment is a determination somebody with
standing has to make. Nobody has. So `Applicability.NOT_DETERMINED` is what a
clock carries until then, and it is neither "applies" nor "does not apply":

    a clock that is NOT DETERMINED still runs the internal escalation, and it
    may never be recorded as satisfied.

Both halves matter. Treating undetermined as "does not apply" is how a
reportable incident goes unreported; treating it as "applies" would let this
build assert a legal duty nobody has established.

WHAT AN EXERCISE MAY NOT CONTAIN
----------------------------------
Client content. Not in a finding, not in a custody row, not in a decision
basis. There is no field that takes it: custody rows carry a digest, an id and
a holder, findings carry a step id and an owner, and `CustodyItem` has no
member for bytes. That is deliberate rather than a rule in a comment -- *never
log client content merely to prove the exercise occurred* is unenforceable as
a habit and trivial as a type.

WHAT A TEST MAY NEVER DO
--------------------------
Send anything. `Decision` has no SENT member. The furthest a rehearsal goes is
`PREPARED_FOR_HUMAN_AUTHORISATION`, because an actual notification is an
operational act by an accountable person and a suite that could perform one
would eventually perform one by accident.

WHAT THIS MODULE CANNOT ESTABLISH
-----------------------------------
That the exercise happened. `conducted_by_people` is derived from named
participants who recorded their own reachability, and no fixture supplies
them, so `human_execution` stays NOT RUN. BK-88-AC3 is refused separately and
for its own reason: an exercise bound to a different configuration digest is
proof about that configuration, and inheriting it as pilot proof is precisely
the mutation the criterion names.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from nm.domain.text import blank, refuses_blank_text

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = pathlib.Path("docs") / "blueprint" / "evaluations.json"


class IncidentContractUnreadable(RuntimeError):
    """The incident contract could not be read. NEVER an empty policy.

    An unreadable clock registry that produced no clocks would let a rehearsal
    complete having reported to nobody, which is the absent-input defect
    holding the statutory timer.
    """


class Applicability(str, Enum):
    """Whether a reporting duty has been determined to cover this deployment.

    `NOT_DETERMINED` is the default and it is a distinct answer. See the
    module docstring: it still runs the internal escalation and it may never
    be recorded as satisfied.
    """

    APPLIES = "applies"
    DOES_NOT_APPLY = "does_not_apply"
    NOT_DETERMINED = "not_determined"

    @classmethod
    def not_established(cls) -> "Applicability":
        return cls.NOT_DETERMINED

    @property
    def is_settled(self) -> bool:
        return self is not Applicability.NOT_DETERMINED


@refuses_blank_text()
@dataclass(frozen=True)
class ReportingClock:
    """One external reporting duty, AS THE REVIEW RECORDED IT.

    `starts_from` is a field rather than an assumption because the two clocks
    this product faces start from different events, and a timer started at
    assessment when the duty runs from notice is late before anybody looks.
    """

    clock_id: str
    hours: int
    starts_from: str
    instrument: str
    applicability: Applicability = Applicability.NOT_DETERMINED
    note: str = ""


def load_clocks(root: pathlib.Path | None = None) -> tuple[ReportingClock, ...]:
    """The reviewed clocks, or a refusal. NEVER an empty tuple."""
    path = (root or ROOT) / CONTRACT
    try:
        document = json.loads(path.read_text(encoding="utf8"))
    except Exception as exc:  # noqa: BLE001 -- unreadable is not empty
        raise IncidentContractUnreadable(
            f"the incident contract at {CONTRACT.as_posix()} could not be "
            f"read ({exc}). A rehearsal cannot run a clock nobody reviewed, "
            f"and an unreadable registry is a refusal rather than a set of "
            f"zero duties.") from exc
    block = document.get("incident_response")
    if not isinstance(block, dict):
        raise IncidentContractUnreadable(
            "the evaluations document declares no incident_response block")
    rows = block.get("reporting_clocks") or []
    if not rows:
        raise IncidentContractUnreadable(
            "the incident contract names no reporting clock, so a rehearsal "
            "against it would report to nobody and complete")
    out = []
    for row in rows:
        out.append(ReportingClock(
            clock_id=str(row.get("clock_id", "")),
            hours=int(row.get("hours", 0)),
            starts_from=str(row.get("starts_from", "")),
            instrument=str(row.get("instrument", "")),
            applicability=Applicability(
                str(row.get("applicability", "not_determined"))),
            note=str(row.get("note", ""))))
    return tuple(out)


# ------------------------------------------------------------- the people ---

class Reached(str, Enum):
    """What happened when somebody was paged.

    `NOT_PAGED` is separate from `NO_ANSWER` because a rota that was never
    tried and a rota that was tried and failed are opposite findings, and both
    render as "nobody came" in a summary that stores only the outcome.
    """

    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    NOT_PAGED = "not_paged"

    @classmethod
    def not_established(cls) -> "Reached":
        return cls.NOT_PAGED


@refuses_blank_text()
@dataclass(frozen=True)
class Contact:
    """One named person in the rota, and what happened when they were paged.

    `person_id` is an identifier and not a name, for the same reason every
    other record in this product carries ids: the tabletop record is kept, and
    a kept record naming who was asleep at 03:00 is an HR document nobody
    intended to write.
    """

    role: str
    person_id: str
    order: int
    reached: Reached = Reached.NOT_PAGED
    responded_at: str = ""


@refuses_blank_text()
@dataclass(frozen=True)
class Rota:
    """Who is paged for one role, in order."""

    role: str
    contacts: tuple[Contact, ...] = ()

    @property
    def in_order(self) -> tuple[Contact, ...]:
        return tuple(sorted(self.contacts, key=lambda c: c.order))

    @property
    def answered(self) -> Contact | None:
        for contact in self.in_order:
            if contact.reached is Reached.ANSWERED:
                return contact
        return None

    def refuse(self) -> tuple[str, ...]:
        """Why this role's escalation did not execute.

        THE POINT OF THE CRITERION. An absent primary contact must not
        silently stop the response, so a rota whose primary did not answer and
        whose secondary was never paged is a FAILED escalation and not a
        reachability note.
        """
        order = self.in_order
        if not order:
            return (f"no contact is listed for {self.role!r}, and a role with "
                    f"an empty rota cannot be escalated to",)
        if self.answered is not None:
            return ()
        untried = [c for c in order if c.reached is Reached.NOT_PAGED]
        if untried:
            return (f"{self.role!r} did not answer and "
                    f"{', '.join(repr(c.person_id) for c in untried)} "
                    f"{'was' if len(untried) == 1 else 'were'} never paged: an "
                    f"absent primary contact must not silently stop the "
                    f"required response",)
        return (f"every contact for {self.role!r} was paged and none "
                f"answered, so this role has no accountable owner during an "
                f"incident",)


# --------------------------------------------------------------- the clock ---

@refuses_blank_text()
@dataclass(frozen=True)
class Timeline:
    """The separate timestamps §10 requires, kept apart deliberately.

    Occurrence, detection and notice are three different moments and every
    external clock runs from exactly one of them. Collapsing them into "when
    it happened" is how a six-hour duty is discovered to have started four
    hours ago.

    `assessed_at` and `contained_at` are exempt from the blank rule because
    their emptiness is this record's live state: an incident under way has
    neither, and requiring them would make an open incident unrepresentable.
    """

    occurred_at: str
    detected_at: str
    noticed_at: str
    assessed_at: str = ""
    contained_at: str = ""

    def moment(self, name: str) -> str:
        return str(getattr(self, name, "") or "")

    def hours_from(self, starts_from: str, until: str) -> float | None:
        """Elapsed hours, or None when either end is missing or unreadable."""
        start, end = self.moment(starts_from), until
        try:
            return (datetime.fromisoformat(end)
                    - datetime.fromisoformat(start)).total_seconds() / 3600.0
        except (ValueError, TypeError):
            return None


class Decision(str, Enum):
    """What a rehearsal concluded about one reporting clock.

    THERE IS NO `SENT`. An actual notification is a human-authorised
    operational act; a rehearsal that could perform one would eventually
    perform one by accident, and the regulator would receive a drill.
    """

    PREPARED_FOR_HUMAN_AUTHORISATION = "prepared_for_human_authorisation"
    NOT_APPLICABLE_ON_REVIEWED_SCOPE = "not_applicable_on_reviewed_scope"
    UNDETERMINED = "undetermined"

    @classmethod
    def not_established(cls) -> "Decision":
        return cls.UNDETERMINED


@refuses_blank_text()
@dataclass(frozen=True)
class NotificationDecision:
    """One clock, one decision, one accountable person, one moment.

    `on_available_information` is the CERT-In FAQ's own allowance and it is
    recorded rather than assumed: an initial report may go with what is known
    and be supplemented, so "we did not have the full picture" is not a reason
    the rehearsal may record for having prepared nothing.
    """

    clock_id: str
    decision: Decision
    decided_by: str
    decided_at: str
    basis: str
    on_available_information: bool = False


# -------------------------------------------------------------- the custody --

@refuses_blank_text()
@dataclass(frozen=True)
class CustodyItem:
    """One piece of preserved evidence: WHAT, WHOSE HASH, WHO HOLDS IT.

    THERE IS NO CONTENT FIELD, and that is the mechanism rather than a rule in
    a comment. *Never log client content merely to prove the exercise
    occurred* is a habit if it is a sentence and a type error if it is a
    schema, so this record can hold a digest and cannot hold the bytes.
    """

    item_id: str
    sha256: str
    held_by: str
    held_at: str
    privileged: bool = False

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(
                c not in "0123456789abcdef" for c in self.sha256.lower()):
            raise ValueError(
                f"custody item {self.item_id!r} carries {self.sha256!r} where "
                f"a SHA-256 digest belongs; an item nobody hashed cannot be "
                f"shown to be the item that was taken")


class Authority(str, Enum):
    """Who authorised a containment action that interrupted service."""

    INCIDENT_COMMANDER = "incident_commander"
    OPERATIONS_OWNER = "operations_owner"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Authority":
        return cls.NOT_RECORDED


@refuses_blank_text()
@dataclass(frozen=True)
class Containment:
    """One action taken to stop the harm, and who said so."""

    action_id: str
    taken_at: str
    authorised_by: Authority = Authority.NOT_RECORDED
    reverses_client_access: bool = False


class Step(str, Enum):
    """Whether one rehearsed step actually executed."""

    EXECUTED = "executed"
    MISSED = "missed"
    NOT_REACHED = "not_reached"

    @classmethod
    def not_established(cls) -> "Step":
        return cls.NOT_REACHED


@refuses_blank_text()
@dataclass(frozen=True)
class Finding:
    """One rehearsed step and its owner. NO PROSE ABOUT THE MATTER.

    A missed step is registered WITH AN OWNER, because a list of things that
    went wrong and nobody's name against them is a document that changes
    nothing before the next exercise.
    """

    step_id: str
    owner: str
    state: Step = Step.NOT_REACHED


# -------------------------------------------------------------- the exercise --

@refuses_blank_text()
@dataclass(frozen=True)
class Exercise:
    """One rehearsal, bound to the scenario and the configuration it exercised.

    `configuration_digest` is empty for a synthetic foundation run and that is
    the honest reading, not a gap to fill: BK-88-AC3 refuses an exercise whose
    digest is not the pilot's, so a foundation record cannot be inherited as
    pilot proof by leaving the field blank either.
    """

    exercise_id: str
    scenario_id: str
    scenario_version: int
    conducted_at: str
    timeline: Timeline
    configuration_digest: str = ""
    rotas: tuple[Rota, ...] = ()
    decisions: tuple[NotificationDecision, ...] = ()
    custody: tuple[CustodyItem, ...] = ()
    containment: tuple[Containment, ...] = ()
    findings: tuple[Finding, ...] = ()
    participants: tuple[str, ...] = ()

    @property
    def conducted_by_people(self) -> bool:
        """DERIVED. Named participants who each answered a page.

        Not a flag: a boolean somebody sets is a boolean somebody sets while
        reading a policy document, which is exactly the substitution P40's
        second expected failure names.
        """
        answered = {c.person_id for rota in self.rotas
                    for c in rota.contacts if c.reached is Reached.ANSWERED}
        return bool(self.participants) and all(
            person in answered for person in self.participants)


def refuse_close(exercise: Exercise, *,
                 clocks: tuple[ReportingClock, ...] | None = None,
                 pilot_digest: str = "") -> tuple[str, ...]:
    """Why this rehearsal may not be recorded as a completed exercise.

    Empty means it may. The population is returned rather than a boolean for
    the reason `refuse_transition` returns one: an operator told only "not
    complete" cannot tell which of eleven things to repeat.
    """
    clocks = load_clocks() if clocks is None else clocks
    out: list[str] = []

    if not exercise.participants:
        out.append("no participant is named, so this is an incident policy "
                   "and not a rehearsal of one: evidence includes people and "
                   "contact results, not a document")
    elif not exercise.conducted_by_people:
        missing = [p for p in exercise.participants
                   if p not in {c.person_id for rota in exercise.rotas
                                for c in rota.contacts
                                if c.reached is Reached.ANSWERED}]
        out.append(f"{', '.join(repr(p) for p in missing)} are named as "
                   f"participants and no rota records them answering a page")

    for rota in exercise.rotas:
        out.extend(rota.refuse())

    if blank(exercise.timeline.noticed_at):
        out.append("no notice time is recorded, and every external clock here "
                   "runs from a moment: an incident record is opened at first "
                   "suspicion rather than after root cause")

    decided = {d.clock_id: d for d in exercise.decisions}
    for clock in clocks:
        decision = decided.get(clock.clock_id)
        if decision is None:
            out.append(
                f"the {clock.clock_id!r} clock ({clock.hours}h from "
                f"{clock.starts_from}, {clock.instrument}) has no recorded "
                f"decision; a clock nobody decided about is not a clock that "
                f"did not apply")
            continue
        if (decision.decision is Decision.NOT_APPLICABLE_ON_REVIEWED_SCOPE
                and not clock.applicability.is_settled):
            out.append(
                f"{clock.clock_id!r} is recorded as not applicable while its "
                f"applicability is {clock.applicability.value}: nobody with "
                f"standing has determined the scope, and undetermined is not "
                f"a finding of no duty")
        if (decision.decision is Decision.UNDETERMINED
                and not decision.on_available_information):
            out.append(
                f"{clock.clock_id!r} was left undetermined and no report was "
                f"prepared on available information; incomplete initial "
                f"information is expressly not a reason to prepare nothing")
        elapsed = exercise.timeline.hours_from(
            clock.starts_from, decision.decided_at)
        if elapsed is None:
            out.append(
                f"{clock.clock_id!r} cannot be timed: the timeline has no "
                f"readable {clock.starts_from!r} moment or the decision has "
                f"no readable time, and an untimed clock is not a met one")
        elif elapsed > clock.hours:
            out.append(
                f"{clock.clock_id!r} was decided {elapsed:.1f}h after "
                f"{clock.starts_from} against a {clock.hours}h duty")

    for action in exercise.containment:
        if action.authorised_by is Authority.NOT_RECORDED:
            out.append(
                f"containment {action.action_id!r} records no authority, and "
                f"an action that interrupts a client's access to their own "
                f"matter is a decision somebody has to own")

    if not exercise.custody:
        out.append("no evidence was taken into custody, so nothing preserved "
                   "during this exercise can be shown to be what was taken")

    for finding in exercise.findings:
        if finding.state is Step.NOT_REACHED:
            out.append(f"step {finding.step_id!r} was never reached and is "
                       f"owned by {finding.owner!r}; an unreached step is not "
                       f"a passed one")

    if pilot_digest:
        if not exercise.configuration_digest:
            out.append(
                "this exercise names no configuration, so it cannot be the "
                "rehearsal of the enabled confidential path: a synthetic "
                "foundation run is proof about the foundation")
        elif exercise.configuration_digest != pilot_digest:
            out.append(
                f"this exercise rehearsed configuration "
                f"{exercise.configuration_digest!r} and the pilot is "
                f"{pilot_digest!r}; incident, recovery and least-privilege "
                f"evidence is revalidated for the enabled path rather than "
                f"inherited from another one")
    return tuple(out)


def projection(exercise: Exercise,
               clocks: tuple[ReportingClock, ...] | None = None) -> dict:
    """What a reviewer is shown. IDENTIFIERS, TIMES AND DIGESTS ONLY."""
    clocks = load_clocks() if clocks is None else clocks
    refused = refuse_close(exercise, clocks=clocks)
    return {
        "exercise": exercise.exercise_id,
        "scenario": f"{exercise.scenario_id}@v{exercise.scenario_version}",
        "configuration": exercise.configuration_digest or "not bound",
        "conducted_by_people": exercise.conducted_by_people,
        "participants": list(exercise.participants),
        "roles": {rota.role: (rota.answered.person_id if rota.answered
                              else "nobody answered")
                  for rota in exercise.rotas},
        "clocks": {clock.clock_id: clock.applicability.value
                   for clock in clocks},
        "custody": [item.sha256[:12] for item in exercise.custody],
        "open_findings": [f.step_id for f in exercise.findings
                          if f.state is not Step.EXECUTED],
        "closed": not refused,
        "refused_because": list(refused),
        "said": ("A rehearsal record is evidence about people. Nothing here "
                 "was notified to anybody: a notification is a human-"
                 "authorised operational act and this record has no state "
                 "for having sent one."),
    }
