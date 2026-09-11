"""What this advocate was actually instructed to do. BK-62-AC1. P13.

    from nm.domain.commission import Commission, Deadline, WorkProduct

WHY THIS IS NOT PART OF `Engagement`
--------------------------------------
`nm/domain/engagement.py` records WHO THE CLIENT IS AND WHAT THIS FILE COVERS,
built from what the product already read -- the client description and the
thread labels. It is a disclosure assembled from existing facts, and it names
the five things it does not hold.

A commission is a different kind of record: it is AUTHORED, it is VERSIONED,
and changing it invalidates work. Folding it into `Engagement` would make a
derived summary and an authored instruction one type, and the derived half
would start carrying things nobody derived.

What the two share is a promise made in `engagement.py`: *"The day one of
these is recorded, it comes off this list and the diff says so."* This module
records three of the five, and `NOT_RECORDED` shrinks accordingly.

THE FIELDS ARE THE CONTRACT'S, NOT MINE
-----------------------------------------
`docs/blueprint/contracts/commands.json` `$defs.Commission` already specifies
objective, work product, scope, exclusions, instructing party, decision maker,
authority record, jurisdiction, deadline and constraints. That contract is
`design_only` -- the live routes keep their shapes until an authorised cutover
-- but its FIELD SET is an authored decision, and inventing a different one
here would be a second contract for one concept.

WHO INSTRUCTS AND WHO DECIDES ARE TWO FIELDS
----------------------------------------------
Not one field called "client". An instructing solicitor relays what the client
wants and cannot concede the client's case; a client decides and may not know
what has been filed. Collapsing them is how a concession gets taken from
somebody who could not give it, which is the exact attempt P13 is required to
refuse.

UNKNOWN IS A VALUE
--------------------
`Deadline.unknown(reason)` is a deadline that has not been established, and it
is not an empty string, not `None`, and not today's date. The contract models
it as a `oneOf` with a required reason for exactly this purpose: an advocate
reading the cover must be able to tell "no deadline applies" from "nobody has
worked out what the deadline is", because the second is work and the first is
not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.authority import ActingAs
from nm.domain.text import refuses_blank_text


class WorkProduct(str, Enum):
    """What the advocate was asked to produce. The contract's enum."""

    ADVICE = "advice"
    RESEARCH = "research"
    DRAFT = "draft"
    HEARING = "hearing"
    NEGOTIATION = "negotiation"
    PROTECTIVE_TRIAGE = "protective_triage"
    """P14's emergency route produces this and only this."""
    UNSTATED = "unstated"
    """Nobody has said what is wanted. Not in the wire contract, which
    requires the field -- but a matter exists before its instruction does, and
    a domain type that could not represent that would force a caller to guess
    one of the six."""

    @classmethod
    def not_established(cls) -> "WorkProduct":
        return cls.UNSTATED


class DeadlineKind(str, Enum):
    UNKNOWN = "unknown"
    DATE = "date"
    NONE_APPLIES = "none_applies"
    """POSITIVELY ASSESSED AS HAVING NO DEADLINE, which is a finding somebody
    made and not the absence of one. `UNKNOWN` is the absence."""

    @classmethod
    def not_established(cls) -> "DeadlineKind":
        return cls.UNKNOWN


class Review(str, Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"

    @classmethod
    def not_established(cls) -> "Review":
        return cls.UNREVIEWED


@refuses_blank_text()
@dataclass(frozen=True)
class Deadline:
    """A date, no date, or nobody knows -- and which of the three it is.

    THE REASON IS REQUIRED ON THE UNKNOWN. A file saying "deadline: unknown"
    with no reason is a field nobody filled in; one saying "unknown: the date
    of service has not been confirmed" is a piece of work with a next step.
    """

    kind: DeadlineKind = DeadlineKind.UNKNOWN
    on: str = ""
    basis: str = ""
    review: Review = Review.UNREVIEWED
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind is DeadlineKind.DATE:
            if not (self.on or "").strip():
                raise ValueError("a dated deadline needs a date")
            if not (self.basis or "").strip():
                raise ValueError(
                    "a dated deadline needs its basis -- which provision or "
                    "event produced it. A date with no basis cannot be "
                    "checked and cannot be corrected.")
        elif not (self.reason or "").strip():
            raise ValueError(
                f"a {self.kind.value} deadline needs a reason, or the cover "
                f"shows a blank field where a finding should be")

    @staticmethod
    def unknown(reason: str) -> "Deadline":
        return Deadline(kind=DeadlineKind.UNKNOWN, reason=reason)

    @staticmethod
    def none_applies(reason: str) -> "Deadline":
        return Deadline(kind=DeadlineKind.NONE_APPLIES, reason=reason)

    @staticmethod
    def on_date(on: str, basis: str,
                review: Review = Review.UNREVIEWED) -> "Deadline":
        return Deadline(kind=DeadlineKind.DATE, on=on, basis=basis,
                        review=review)

    @property
    def assessed(self) -> bool:
        """Whether anybody has worked this out. The cover shows this."""
        return self.kind is not DeadlineKind.UNKNOWN

    def said(self) -> str:
        """What the advocate reads. Never a bare date and never blank."""
        if self.kind is DeadlineKind.DATE:
            mark = "" if self.review is Review.REVIEWED else " (unreviewed)"
            return f"{self.on} — {self.basis}{mark}"
        if self.kind is DeadlineKind.NONE_APPLIES:
            return f"no deadline applies — {self.reason}"
        return f"not established — {self.reason}"

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "on": self.on, "basis": self.basis,
                "review": self.review.value, "reason": self.reason,
                "assessed": self.assessed, "said": self.said()}

    @staticmethod
    def from_stored(value) -> "Deadline":
        if isinstance(value, Deadline):
            return value
        if not isinstance(value, dict):
            return Deadline.unknown("nothing was recorded")
        try:
            return Deadline(
                kind=DeadlineKind(value.get("kind", "unknown")),
                on=value.get("on", ""), basis=value.get("basis", ""),
                review=Review(value.get("review", "unreviewed")),
                reason=value.get("reason", "") or "nothing was recorded")
        except (ValueError, TypeError):
            return Deadline.unknown("the stored deadline could not be read")


@refuses_blank_text()
@dataclass(frozen=True)
class Party:
    """One person, and what they are TO THIS INSTRUCTION.

    The capacity lives here rather than on the account because it is a fact
    about this matter: the same solicitor instructs on one file and decides on
    another, and an account cannot say which.
    """

    party_id: str
    described_as: str
    capacity: ActingAs = ActingAs.UNKNOWN

    def as_dict(self) -> dict:
        return {"party_id": self.party_id, "described_as": self.described_as,
                "capacity": self.capacity.value}

    @staticmethod
    def from_stored(value) -> "Party | None":
        if isinstance(value, Party):
            return value
        if not isinstance(value, dict) or not value.get("party_id"):
            return None
        try:
            capacity = ActingAs(value.get("capacity", "unknown"))
        except ValueError:
            capacity = ActingAs.UNKNOWN
        return Party(party_id=value["party_id"],
                     described_as=value.get("described_as") or "(not described)",
                     capacity=capacity)


#: The fields whose change REOPENS work already done. BK-62-AC1.
#:
#: Not every edit is material. Fixing a typo in the objective does not
#: invalidate an advice; changing the work product from `advice` to
#: `negotiation` does, and so does moving the deadline or narrowing the scope.
#: Naming them here, once, means the API, the job path and any future action
#: path ask the same question -- and a field added to `Commission` tomorrow is
#: NOT material until somebody puts it in this tuple deliberately.
MATERIAL: tuple[str, ...] = (
    "objective", "work_product", "scope", "exclusions", "forum",
    "deadline", "constraints", "instructing", "deciding",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Commission:
    """One version of what this advocate was instructed to do."""

    version: int = 1
    objective: str = ""
    work_product: WorkProduct = WorkProduct.UNSTATED
    scope: str = ""
    exclusions: tuple[str, ...] = ()
    #: WHO INSTRUCTS and WHO DECIDES. Two fields, never one.
    instructing: Party | None = None
    deciding: Party | None = None
    forum: str = ""
    deadline: Deadline = field(
        default_factory=lambda: Deadline.unknown("no instruction recorded yet"))
    constraints: tuple[str, ...] = ()
    recorded_by: str = ""
    recorded_at: str = ""
    #: WHY THIS VERSION EXISTS. Empty on the first; on every later one it is
    #: the reason somebody changed the instruction, which is the thing a
    #: receiving advocate most needs and the thing a bare diff cannot say.
    because: str = ""

    # ------------------------------------------------------- what is missing

    def unknowns(self) -> tuple[str, ...]:
        """What this commission does NOT establish, named.

        A LIST AND NOT A FLAG. `complete: false` tells an advocate something
        is missing and not which thing, so they cannot act on it -- and the
        one they would have chased is whichever they happened to think of.
        """
        missing: list[str] = []
        if not self.objective.strip():
            missing.append("the objective — what the advocate is to achieve")
        if self.work_product is WorkProduct.UNSTATED:
            missing.append("the work product — what is to be produced")
        if not self.scope.strip():
            missing.append("the scope — what is and is not covered")
        if self.instructing is None:
            missing.append("who instructs")
        elif self.instructing.capacity is ActingAs.UNKNOWN:
            missing.append(
                f"the capacity of {self.instructing.described_as}, who is "
                f"named as instructing")
        if self.deciding is None:
            missing.append("who decides, as distinct from who instructs")
        elif self.deciding.capacity is not ActingAs.DECIDING:
            missing.append(
                f"{self.deciding.described_as} is named as the decision maker "
                f"and is recorded as {self.deciding.capacity.value}")
        if not self.forum.strip():
            missing.append("the forum")
        if not self.deadline.assessed:
            missing.append(f"the deadline — {self.deadline.reason}")
        return tuple(missing)

    @property
    def established(self) -> bool:
        """Whether this commission says enough to work from.

        NOT whether it is complete in the professional sense -- that is a
        judgement a person makes, and `docs/BACKLOG.md` requires a counsel
        review for it. This is the narrower mechanical question.
        """
        return not self.unknowns()

    # ------------------------------------------------------------ versioning

    def next_version(self, **changes) -> "Commission":
        """The next version. NEVER a mutation of this one.

        Corrections are versions because the previous instruction is evidence:
        an advice given under version 1 was correct work under version 1, and
        deleting version 1 makes it look like a mistake.
        """
        from dataclasses import replace

        return replace(self, version=self.version + 1, **changes)

    def as_dict(self) -> dict:
        return {
            "version": self.version, "objective": self.objective,
            "work_product": self.work_product.value, "scope": self.scope,
            "exclusions": list(self.exclusions),
            "instructing": self.instructing.as_dict() if self.instructing else None,
            "deciding": self.deciding.as_dict() if self.deciding else None,
            "forum": self.forum, "deadline": self.deadline.as_dict(),
            "constraints": list(self.constraints),
            "recorded_by": self.recorded_by, "recorded_at": self.recorded_at,
            "because": self.because, "unknowns": list(self.unknowns()),
            "established": self.established,
        }

    @staticmethod
    def from_stored(value) -> "Commission | None":
        if isinstance(value, Commission):
            return value
        if not isinstance(value, dict):
            return None
        try:
            work = WorkProduct(value.get("work_product", "unstated"))
        except ValueError:
            work = WorkProduct.UNSTATED
        return Commission(
            version=int(value.get("version") or 1),
            objective=value.get("objective", ""), work_product=work,
            scope=value.get("scope", ""),
            exclusions=tuple(value.get("exclusions") or ()),
            instructing=Party.from_stored(value.get("instructing")),
            deciding=Party.from_stored(value.get("deciding")),
            forum=value.get("forum", ""),
            deadline=Deadline.from_stored(value.get("deadline")),
            constraints=tuple(value.get("constraints") or ()),
            recorded_by=value.get("recorded_by", ""),
            recorded_at=value.get("recorded_at", ""),
            because=value.get("because", ""))


def material_changes(old: Commission | None,
                     new: Commission) -> tuple[str, ...]:
    """Which material fields moved. EMPTY MEANS NOTHING WAS REOPENED.

    THE POPULATION IS `MATERIAL`, read from it rather than restated, so a
    field added to the tuple is compared here without anybody editing this
    function -- and a field added to `Commission` and NOT to the tuple is
    deliberately immaterial rather than accidentally so.
    """
    if old is None:
        return ()
    moved: list[str] = []
    for name in MATERIAL:
        if getattr(old, name, None) != getattr(new, name, None):
            moved.append(name)
    return tuple(moved)
