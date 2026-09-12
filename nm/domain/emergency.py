"""Liberty does not wait for a registry. BK-78-AC1, BK-78-AC2, BK-53-AC1. P14.

    from nm.domain.emergency import Declaration, Protective

WHY THIS IS A RECORD AND NOT A BOOLEAN
----------------------------------------
`nm/core/screens.may_admit_substance` already takes `emergency: bool`, and a
boolean is exactly enough to admit substance and nothing like enough to answer
the questions asked afterwards: WHO declared it, on what basis, what it
permitted, which screens were still outstanding, and WHEN IT STOPPED.

BK-78-AC2 requires the declaration and any expiry to survive retry and
re-entry. A flag survives nothing -- it is recomputed on each turn from
whatever the caller passed -- so an emergency declared on Tuesday is
indistinguishable on Thursday from one declared five seconds ago.

WHAT AN EMERGENCY BUYS, AND WHAT IT DOES NOT
----------------------------------------------
It buys PROTECTIVE OR REFERRAL guidance: the narrow thing that stops harm
now. It does not buy substantive analysis, and it does not make a closed
screen open. The exception is recorded AS AN EXCEPTION so the file never reads
as though the screens had passed -- which is the sentence
`nm/core/screens.py` already uses, kept deliberately because this module is
its record and not a second rule.

`permits(work)` therefore answers False for every work product except
`PROTECTIVE_TRIAGE`, by construction rather than by a caller remembering, and
there is no parameter that widens it.

EXPIRY IS NOT DELETION
------------------------
An expired declaration stays on the file. The urgency it recorded was real and
remains evidence of why the file was handled as it was; what lapses is the
PERMISSION, not the history. So `active_at` is a question about a moment and
`Declaration` is immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from nm.domain.text import refuses_blank_text

#: How long a declaration permits anything before somebody has to look again.
#:
#: SHORT ON PURPOSE. An emergency that lasts a week is not an emergency, it is
#: an unexamined file -- and the whole risk of this route is that it becomes
#: the comfortable one. Re-declaring is cheap and leaves a second record;
#: a long window leaves none.
DEFAULT_HOURS = 24


#: THE ONLY WORK PRODUCT AN EMERGENCY ADMITS. Named against the commission's
#: own enum so the two cannot drift: if `WorkProduct` gains a value, this stays
#: exactly as narrow as it was, which is the correct default for a permission.
PERMITTED_WORK = "protective_triage"


@refuses_blank_text("revoked_by")
@dataclass(frozen=True)
class Declaration:
    """One emergency, declared by somebody, for a reason, with an end."""

    actor_id: str
    basis: str
    """WHAT THE DANGER IS, in the declarer's words. Required: a declaration
    with no basis is a switch, and a switch is what this record exists to stop
    the emergency route from being."""

    declared_at: datetime
    expires_at: datetime
    #: The screens that were outstanding WHEN IT WAS DECLARED. Frozen at that
    #: moment on purpose -- it is the justification, and a list recomputed
    #: later would silently rewrite why the exception was taken.
    outstanding: tuple[str, ...] = ()
    permitted_scope: str = (
        "immediate protective or referral guidance only; no substantive "
        "analysis and no step that assumes the screens have passed")
    revoked_at: datetime | None = None
    revoked_by: str = ""

    @staticmethod
    def declare(actor_id: str, basis: str, outstanding: tuple[str, ...],
                now: datetime, hours: int = DEFAULT_HOURS) -> "Declaration":
        if (not isinstance(hours, int) or isinstance(hours, bool)
                or not 1 <= hours <= DEFAULT_HOURS):
            raise ValueError(f"an emergency must expire within 1–{DEFAULT_HOURS} hours")
        return Declaration(
            actor_id=actor_id, basis=basis, declared_at=now,
            expires_at=now + timedelta(hours=hours),
            outstanding=tuple(outstanding))

    # ------------------------------------------------------------- state ---

    def active_at(self, now: datetime) -> bool:
        """Whether this permits anything AT THIS MOMENT.

        A QUESTION ABOUT A MOMENT, not a stored flag, so re-entry two days
        later gets the true answer rather than the one that was true when
        somebody last wrote a field.
        """
        try:
            if self.revoked_at is not None and now >= self.revoked_at:
                return False
            return self.declared_at <= now < self.expires_at
        except TypeError:
            return False  # incompatible historic timestamps grant nothing

    def state_at(self, now: datetime) -> str:
        """`live`, `expired` or `revoked`. THREE, because the advocate does
        different things about each: a live one is working, an expired one is
        re-declared if the danger persists, and a revoked one was ended by a
        person who should be asked why."""
        try:
            if self.revoked_at is not None and now >= self.revoked_at:
                return "revoked"
            if now >= self.expires_at:
                return "expired"
            return "live" if self.declared_at <= now else "not_assessed"
        except TypeError:
            return "not_assessed"

    def permits(self, work_product: str) -> bool:
        """Whether this declaration admits that work. PROTECTIVE ONLY.

        No parameter widens this and no caller may pass one. An emergency that
        could be made to admit substantive work would be a way of turning the
        screens off, which is the one thing it must never be.
        """
        return str(work_product) == PERMITTED_WORK

    def revoke(self, by: str, now: datetime) -> "Declaration":
        """End it early. A NEW RECORD, never an erasure."""
        from dataclasses import replace

        return replace(self, revoked_at=now, revoked_by=by)

    # ------------------------------------------------------- what is said ---

    def said(self, now: datetime) -> str:
        """What the advocate reads. NAMES THE EXCEPTION AS AN EXCEPTION."""
        state = self.state_at(now)
        if state == "not_assessed":
            return "the emergency validity cannot be established; no exception is granted"
        if state == "live":
            return (f"EMERGENCY EXCEPTION, live until "
                    f"{self.expires_at.isoformat(timespec='minutes')}: "
                    f"{self.permitted_scope}. Screens still outstanding: "
                    f"{'; '.join(self.outstanding) or 'none recorded'}.")
        if state == "revoked":
            return (f"the emergency exception was revoked by "
                    f"{self.revoked_by or 'somebody unnamed'}; ordinary "
                    f"screens apply and the urgency recorded on "
                    f"{self.declared_at.date().isoformat()} stands on the file")
        return (f"the emergency exception lapsed at "
                f"{self.expires_at.isoformat(timespec='minutes')}. The urgency "
                f"recorded on {self.declared_at.date().isoformat()} stands on "
                f"the file; ordinary screens are required before substantive "
                f"work resumes.")

    def as_dict(self) -> dict:
        return {
            "actor_id": self.actor_id, "basis": self.basis,
            "declared_at": self.declared_at.isoformat(timespec="seconds"),
            "expires_at": self.expires_at.isoformat(timespec="seconds"),
            "outstanding": list(self.outstanding),
            "permitted_scope": self.permitted_scope,
            "revoked_at": (self.revoked_at.isoformat(timespec="seconds")
                           if self.revoked_at else None),
            "revoked_by": self.revoked_by,
        }

    @staticmethod
    def from_stored(value) -> "Declaration | None":
        if isinstance(value, Declaration):
            return value
        if (not isinstance(value, dict) or not value.get("actor_id")
                or not isinstance(value.get("basis"), str) or not value["basis"].strip()):
            return None

        def when(key):
            raw = value.get(key)
            try:
                return datetime.fromisoformat(raw) if raw else None
            except (TypeError, ValueError):
                return None

        declared, expires = when("declared_at"), when("expires_at")
        if declared is None or expires is None:
            return None
        revoked = when("revoked_at")
        # Malformed is not absent. Collapsing a damaged revocation into None
        # would recreate a live exception nobody currently authorised.
        if value.get("revoked_at") is not None and revoked is None:
            return None
        return Declaration(
            actor_id=value["actor_id"],
            basis=value["basis"],
            declared_at=declared, expires_at=expires,
            outstanding=tuple(value.get("outstanding") or ()),
            permitted_scope=value.get("permitted_scope")
            or "immediate protective or referral guidance only",
            revoked_at=revoked,
            revoked_by=value.get("revoked_by", ""))


def latest(declarations: tuple, now: datetime) -> "Declaration | None":
    """The one that governs NOW, or None. History is kept; only one governs.

    A file may carry several declarations -- an emergency re-declared after
    expiry is a second record, deliberately, because two separate moments of
    danger are two facts. The governing one is the live one; if none is live,
    NOTHING is, and an expired declaration must not be returned as though it
    still permitted anything.
    """
    candidates = []
    for index, row in enumerate(declarations or ()):
        declaration = Declaration.from_stored(row)
        if declaration is None:
            return None  # damaged history cannot silently revive an older grant
        try:
            if declaration.declared_at <= now:
                candidates.append((declaration.declared_at, index, declaration))
        except TypeError:
            return None
    if not candidates:
        return None
    # Stored timestamps historically have second precision. Later append order
    # decides a tie, so a restrictive replacement in that second wins.
    governing = max(candidates, key=lambda candidate: candidate[:2])[2]
    return governing if governing.active_at(now) else None
