"""NOTHING RUNS IN THE BACKGROUND WITHOUT SOMEBODY HAVING ASKED. BK-58-AC1. P45.

    from nm.domain.service import ServiceAuthority, Trigger, refuse_service

WHAT THIS IS FOR
------------------
Proactive work is the one capability that acts when nobody is watching. A
deadline reminder, a conflict re-check, a hearing alert -- each is useful, and
each is a message that leaves the building on an advocate's behalf without them
in the room. Two things therefore have to be true before any of it happens:

    SOMEBODY AUTHORISED IT, specifically, for a stated purpose, with a named
    responsible actor -- and that authority is still current at the moment the
    work is scheduled, at the moment it runs, and at the moment its result is
    accepted. Three checks, because the gap between them is where a revoked
    authority still sends.

    AND IT IS NOT SILENT. An advocate who was told "I will watch this" and was
    not watched is worse off than one who was told nothing, because they
    stopped watching too.

PERMISSION TO READ IS NOT PERMISSION TO ACT
---------------------------------------------
This record is separate from `Engagement` and from the workspace membership
that lets an advocate open the file. Authority to READ a matter is answered by
`nm/domain/authority.py`; authority to ACT ON IT UNPROMPTED is answered here,
and folding the two would make opening a file an instruction to monitor it.

NO CONTINUOUS MONITORING IS CLAIMED, EVER
-------------------------------------------
`said()` states what is actually true: work happens when a recorded trigger
fires and this product is running. A claim of continuous watching is a promise
about uptime nobody in this build has measured, and an advocate who believes it
has delegated a limitation period to a cron job.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class AuthorityState(str, Enum):
    """Whether proactive work is authorised RIGHT NOW.

    `NOT_RECORDED` is the default and it is not a refusal -- it is the absence
    of a decision, which reads differently to an advocate and is fixed by a
    different act. `REVOKED` and `EXPIRED` are both "not now" and they are kept
    apart because one was somebody's decision and the other was a date.
    """

    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "AuthorityState":
        return cls.NOT_RECORDED

    @property
    def permits_work(self) -> bool:
        """ONLY `GRANTED`. Written once so no scheduler, worker or result
        handler decides for itself -- the three of them deciding separately is
        how a revoked authority keeps sending."""
        return self is AuthorityState.GRANTED


class Trigger(str, Enum):
    """What makes the work due.

    An EVENT trigger fires when something is recorded on the file; a CADENCE
    trigger fires on a stated interval. They are separated because they fail
    differently: an event that never arrives is silence, and a cadence that
    stops is a service that looks alive.
    """

    EVENT = "event"
    CADENCE = "cadence"
    NOT_STATED = "not_stated"

    @classmethod
    def not_established(cls) -> "Trigger":
        return cls.NOT_STATED


class Notify(str, Enum):
    """How the advocate asked to be told. THE PREFERENCE IS PART OF THE
    AUTHORITY, not a setting beside it: consent to be watched is not consent
    to be telephoned."""

    IN_PRODUCT = "in_product"
    EMAIL = "email"
    NONE = "none"
    """Do the work, record it, tell nobody until they look. A real choice, and
    the only one that sends nothing."""

    NOT_STATED = "not_stated"

    @classmethod
    def not_established(cls) -> "Notify":
        return cls.NOT_STATED


#: What a service authority must record before any work may be scheduled.
#: Named once; `absent()` and the served projection both read this.
REQUIRED_BEFORE_SERVICE: dict[str, str] = {
    "responsible_actor": "who is responsible for what this produces",
    "purpose": "what the work is for",
    "granted_by": "who authorised it",
    "granted_at": "when they authorised it",
}


@refuses_blank_text("revoked_at", "revoked_by", "expires_on", "cadence",
                    "responsible_actor", "purpose", "granted_by", "granted_at")
@dataclass(frozen=True)
class ServiceAuthority:
    """One recorded permission to work on a matter unprompted, VERSIONED.

    Every field in `REQUIRED_BEFORE_SERVICE` is exempt from the blank rule
    because an incomplete authority must be REPRESENTABLE -- `absent()` reports
    it, and refusing construction would push a caller into inventing a purpose
    to obtain an object. The same argument P30's `ActionProposal` makes.

    CHANGING IT MAKES A NEW VERSION. A revoked authority is not deleted: work
    done under version 2 was authorised work, and erasing version 2 makes it
    look like it never was.
    """

    authority_id: str
    matter_id: str
    responsible_actor: str = ""
    purpose: str = ""
    trigger: Trigger = Trigger.NOT_STATED
    cadence: str = ""
    notify: Notify = Notify.NOT_STATED
    granted_by: str = ""
    granted_at: str = ""
    expires_on: str = ""
    revoked_at: str = ""
    revoked_by: str = ""
    version: int = 1

    def absent(self) -> tuple[str, ...]:
        out = [label for name, label in REQUIRED_BEFORE_SERVICE.items()
               if blank(getattr(self, name, ""))]
        if self.trigger is Trigger.NOT_STATED:
            out.append("what makes the work due")
        elif self.trigger is Trigger.CADENCE and blank(self.cadence):
            out.append("how often it runs")
        if self.notify is Notify.NOT_STATED:
            out.append("how the advocate asked to be told")
        return tuple(out)

    def state_on(self, today: str) -> AuthorityState:
        """DERIVED, never stored. A stored state is one somebody can set to
        `granted` without granting anything -- the rule P26 keeps for advice
        maturity and P33 for retention, at the point where getting it wrong
        sends a message on somebody's behalf.
        """
        if not blank(self.revoked_at):
            return AuthorityState.REVOKED
        if self.absent():
            return AuthorityState.NOT_RECORDED
        if not blank(self.expires_on) and today and today > self.expires_on:
            return AuthorityState.EXPIRED
        return AuthorityState.GRANTED

    def said(self, today: str = "") -> str:
        """WHAT THE ADVOCATE READS, and it never claims continuous watching."""
        state = self.state_on(today)
        if state is AuthorityState.NOT_RECORDED:
            return ("No proactive work is authorised on this matter, so "
                    "nothing runs on it unless you are here. "
                    + ("Still needed: " + "; ".join(self.absent())
                       if self.absent() else ""))
        if state is AuthorityState.REVOKED:
            return (f"Authorised work on this matter was withdrawn on "
                    f"{self.revoked_at}. Nothing further is scheduled and "
                    f"anything already running is being stopped.")
        if state is AuthorityState.EXPIRED:
            return (f"This authority ran out on {self.expires_on}. Nothing "
                    f"further is scheduled; it has not been renewed.")
        return (f"{self.responsible_actor} is responsible for this. Work "
                f"happens when the recorded trigger fires and this product is "
                f"running -- it is NOT continuous monitoring, and a period "
                f"you are relying on is still yours to watch.")


def grant(*, authority_id: str, matter_id: str, responsible_actor: str,
          purpose: str, trigger: Trigger, notify: Notify, granted_by: str,
          granted_at: str, cadence: str = "",
          expires_on: str = "") -> ServiceAuthority:
    """Record an authority. IT CANNOT BE CREATED ALREADY REVOKED, and it
    cannot be created incomplete.

    The state is not a parameter -- the discipline `retention.request`,
    `advice.maturity_of` and `handover.offer` all keep. A caller that could
    construct a granted authority with nothing in it could start work nobody
    asked for and point at a record saying they had.
    """
    made = ServiceAuthority(
        authority_id=authority_id, matter_id=matter_id,
        responsible_actor=responsible_actor.strip(), purpose=purpose.strip(),
        trigger=trigger, cadence=cadence.strip(), notify=notify,
        granted_by=granted_by.strip(), granted_at=granted_at.strip(),
        expires_on=expires_on.strip())
    missing = made.absent()
    if missing:
        raise ValueError(
            "a service authority records: " + "; ".join(missing)
            + ". Work that runs on a partial authority is work nobody agreed "
              "to in the terms it actually happens in")
    return made


def revoke(authority: ServiceAuthority, *, by: str, at: str) -> ServiceAuthority:
    """Withdraw it. THE RECORD IS KEPT and the version moves.

    Revocation is a new version rather than a deletion because work done under
    the previous one was authorised work, and a file that cannot show the
    authority under which a message went out cannot answer for the message.
    """
    if blank(by) or blank(at):
        raise ValueError("a revocation records who withdrew it and when")
    if not blank(authority.revoked_at):
        # IDEMPOTENT BY CONSTRUCTION. Revoking twice is what a retried click
        # does, and the second one must not rewrite the first one's record.
        return authority
    return replace(authority, revoked_at=at, revoked_by=by,
                   version=authority.version + 1)


def refuse_service(authority: ServiceAuthority | None, *, today: str,
                   doing: str) -> str:
    """Why this proactive work may not happen, or "". BK-58-AC1.

    ASKED AT ALL THREE MOMENTS -- scheduling, running, accepting the result --
    by the one caller shape, because an authority checked only at scheduling
    is an authority that keeps sending for as long as the queue is deep.
    """
    if authority is None:
        return (f"nothing authorises {doing} on this matter. Proactive work "
                f"needs a recorded authority naming who is responsible, what "
                f"it is for and what makes it due")
    state = authority.state_on(today)
    if state.permits_work:
        return ""
    if state is AuthorityState.NOT_RECORDED:
        return ("the service authority on this matter does not record: "
                + "; ".join(authority.absent())
                + f", so {doing} is not authorised")
    return (f"the service authority on this matter is {state.value}, so "
            f"{doing} is not authorised")
