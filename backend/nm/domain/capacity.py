"""Human capacity assessment on the record, not inferred from account or role.

P14 consumes this position at actual admission. A later informed decision
must carry its own applicable position; this matter-level foundation is not
the complete E4 DecisionRecord and grants no action authority.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from nm.domain.traceability import implements


class Capacity(str, Enum):
    """B6's existing vocabulary, shared with Engagement and the live screen."""

    NOT_IN_DOUBT = "not_in_doubt"
    IN_DOUBT = "in_doubt"
    NOT_ASSESSED = "not_assessed"


def record_on(matter, position):
    """One assessment history for intake, later correction and turn input."""
    answers = dict(matter.intake_answers or {})
    previous = answers.get("capacity")
    history = tuple(answers.get("capacity_history") or ())
    if previous is not None:
        history = (*history, previous)
    answers.update(capacity=position.as_dict(), capacity_history=history)
    return replace(matter, intake_answers=answers)


@dataclass(frozen=True)
class CapacityPosition:
    state: Capacity = Capacity.NOT_ASSESSED
    basis: str = "No explicit capacity assessment is recorded."
    raised_at: datetime | None = None
    resolved_by: str = ""
    raised_by: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, Capacity):
            raise ValueError("capacity state must be explicit")
        if not isinstance(self.basis, str) or not self.basis.strip():
            raise ValueError("capacity needs a recorded basis")
        if not isinstance(self.raised_by, str) or not isinstance(self.resolved_by, str):
            raise ValueError("capacity source and resolver must be named text")
        if self.raised_at is not None and (
            not isinstance(self.raised_at, datetime)
            or self.raised_at.tzinfo is None
            or self.raised_at.utcoffset() is None
        ):
            raise ValueError("capacity assessment needs an aware timestamp")
        if self.state is not Capacity.NOT_ASSESSED and (
            self.raised_at is None or not self.raised_by.strip()
        ):
            raise ValueError("capacity assessment needs its source and time")
        if self.state is Capacity.NOT_IN_DOUBT:
            if not self.resolved_by.strip() or self.resolved_by != self.raised_by:
                raise ValueError("a capacity clearance needs its named assessor")
        elif self.resolved_by:
            raise ValueError("unresolved capacity cannot name a resolver")

    @staticmethod
    def record(value: dict, *, actor: str, now: datetime) -> "CapacityPosition":
        """Record a deliberate human state; no NLP or phrase-list inference."""
        if not isinstance(value, dict) or set(value) != {"state", "basis"}:
            raise ValueError("capacity assessment accepts exactly state and basis")
        if not isinstance(value["state"], str) or not isinstance(value["basis"], str):
            raise ValueError("capacity state and basis must be text")
        state = Capacity(value["state"])
        basis = value["basis"].strip()
        if state is Capacity.NOT_ASSESSED and not basis:
            basis = "The advocate has not assessed capacity to instruct."
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("capacity assessment needs an authenticated source")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("capacity assessment needs the server's aware timestamp")
        return CapacityPosition(
            state=state, basis=basis, raised_at=now, raised_by=actor,
            resolved_by=actor if state is Capacity.NOT_IN_DOUBT else "")

    @implements("B6")
    def authorises_at(self, now: datetime) -> bool:
        """Only a current explicit assessment clears this one admission check."""
        if self.state is not Capacity.NOT_IN_DOUBT or self.raised_at is None:
            return False
        try:
            return self.raised_at <= now
        except TypeError:
            return False

    @property
    def next_step(self) -> str:
        if self.state is Capacity.IN_DOUBT:
            return ("Obtain and record a human resolution of capacity "
                    "before relying on instructions.")
        if self.state is Capacity.NOT_ASSESSED:
            return "Record an explicit capacity assessment and its basis before substantive work."
        return "Reassess if the basis or the instruction materially changes."

    def said(self) -> str:
        # Identity and timestamps remain in the attributable record; conversation
        # carries the human assessment and action, not status codes or account IDs.
        assessment = {
            Capacity.NOT_ASSESSED: "Capacity to give these instructions has not yet been assessed.",
            Capacity.IN_DOUBT: "Capacity to give these instructions remains in doubt.",
            Capacity.NOT_IN_DOUBT: (
                "The recorded assessment finds capacity to give these instructions "
                "is not in doubt."),
        }[self.state]
        return f"{assessment} {self.basis} {self.next_step}"

    def as_dict(self) -> dict:
        return {
            "state": self.state.value, "basis": self.basis,
            "raised_at": self.raised_at.isoformat() if self.raised_at else None,
            "resolved_by": self.resolved_by, "raised_by": self.raised_by,
            "next_step": self.next_step,
        }

    @staticmethod
    def from_stored(value) -> "CapacityPosition":
        if isinstance(value, CapacityPosition):
            return value
        if not isinstance(value, dict) or "state" not in value:
            return CapacityPosition(basis=(
                "A legacy or missing answer is not an explicit capacity assessment; "
                "reassessment is required."))
        try:
            stamp = value.get("raised_at")
            return CapacityPosition(
                state=Capacity(value["state"]), basis=value.get("basis", ""),
                raised_at=datetime.fromisoformat(stamp) if isinstance(stamp, str) else None,
                raised_by=value.get("raised_by", ""), resolved_by=value.get("resolved_by", ""))
        except (ValueError, TypeError, AttributeError):
            return CapacityPosition(basis="The recorded capacity assessment could not be verified.")
