"""HANDOVER DOES NOT MOVE RESPONSIBILITY BY ITSELF. BK-39-AC2, BK-58-AC3. P32.

    from nm.domain.handover import CaseSummary, Handover, HandoverState

WHAT THIS IS FOR
------------------
An advocate hands a matter to someone else -- going on leave, leaving the
chambers, briefing a junior. The dangerous half is not the file, which is on
disk. It is the RESPONSIBILITY, which is not:

    A handover that completes because it was SENT leaves a deadline with
    nobody watching it, and both people believe the other has it.

So `HandoverState` has an OFFERED state and an ACCEPTED state and they are not
the same, acceptance is by the named recipient and nobody else, and
`unowned_after` reports every outstanding obligation that would land on no one.

THE SNAPSHOT IS APPENDIX E'S `CaseSummary`
--------------------------------------------
Sixteen required fields, including `handover_complete` and
`handover_blockers` -- the contract already knew a summary has to be able to
say it is NOT ready to hand over. BK-39-AC2 asks for instruction, material
facts, authorities, decisions, reservations and next responsibility *with
unassessed sections explicit*, and that last clause is why every section is
`Section`, not a bare list: a section nobody assessed reads as UNASSESSED, and
an empty list reads as "there are none". Those are different sentences and the
receiving advocate acts differently on each.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Assessed(str, Enum):
    """Whether anybody looked. THE DISTINCTION BK-39-AC2 TURNS ON.

    `EMPTY` means somebody looked and there is nothing. `NOT_ASSESSED` means
    nobody looked. A handover that renders both as an empty list tells the
    receiving advocate there are no authorities when the truth may be that no
    one has searched for any.
    """

    ASSESSED = "assessed"
    EMPTY = "empty"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Assessed":
        return cls.NOT_ASSESSED


@dataclass(frozen=True)
class Section:
    """One part of the snapshot, and whether anybody assessed it."""

    items: tuple[str, ...] = ()
    state: Assessed = Assessed.NOT_ASSESSED

    def __post_init__(self) -> None:
        # A SECTION CANNOT CARRY ITEMS AND CLAIM NOBODY LOOKED. That shape
        # would let a populated section render as unassessed and be skipped.
        if self.items and self.state is Assessed.NOT_ASSESSED:
            object.__setattr__(self, "state", Assessed.ASSESSED)
        if not self.items and self.state is Assessed.ASSESSED:
            object.__setattr__(self, "state", Assessed.EMPTY)

    def render(self) -> str:
        if self.state is Assessed.NOT_ASSESSED:
            return "not assessed -- nobody has looked at this"
        if self.state is Assessed.EMPTY:
            return "none, and that was checked"
        return "; ".join(self.items)


class HandoverState(str, Enum):
    """OFFERED IS NOT ACCEPTED, and that is the whole packet.

    There is no `SENT`. Sending is not a state of the responsibility; it is a
    thing that happened to a message.
    """

    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    NOT_OFFERED = "not_offered"

    @classmethod
    def not_established(cls) -> "HandoverState":
        return cls.NOT_OFFERED

    @property
    def responsibility_moved(self) -> bool:
        """ONLY acceptance moves it. Everything else leaves it where it was,
        which is the answer that keeps a deadline watched."""
        return self is HandoverState.ACCEPTED


#: Appendix E's `CaseSummary`, required fields. Asserted against
#: `assurance/specification/schemas.yaml` by the test rather than trusted as a copy.
SUMMARY_FIELDS: tuple[str, ...] = (
    "matter", "engagement", "screens", "threads", "posture", "chronology",
    "issues", "theory", "proof", "authorities", "deadlines", "decisions",
    "reservations", "gaps", "handover_complete", "handover_blockers",
)


@refuses_blank_text()
@dataclass(frozen=True)
class CaseSummary:
    """The handover snapshot. Appendix E's record, implemented.

    `handover_complete` is DERIVED by `blockers()` rather than stored as a
    claim: a summary that could assert its own completeness is a summary that
    will, and the receiving advocate reads that as a checked statement.
    """

    matter: str
    engagement: Section = field(default_factory=Section)
    screens: Section = field(default_factory=Section)
    threads: Section = field(default_factory=Section)
    posture: Section = field(default_factory=Section)
    chronology: Section = field(default_factory=Section)
    issues: Section = field(default_factory=Section)
    theory: Section = field(default_factory=Section)
    proof: Section = field(default_factory=Section)
    authorities: Section = field(default_factory=Section)
    deadlines: Section = field(default_factory=Section)
    decisions: Section = field(default_factory=Section)
    reservations: Section = field(default_factory=Section)
    gaps: Section = field(default_factory=Section)
    instruction: str = ""
    next_responsibility: str = ""
    version: int = 1

    @property
    def sections(self) -> dict[str, Section]:
        return {name: getattr(self, name) for name in (
            "engagement", "screens", "threads", "posture", "chronology",
            "issues", "theory", "proof", "authorities", "deadlines",
            "decisions", "reservations", "gaps")}

    def unassessed(self) -> tuple[str, ...]:
        """Every section nobody has looked at, BY NAME. BK-39-AC2's
        *unassessed sections explicit*."""
        return tuple(name for name, s in self.sections.items()
                     if s.state is Assessed.NOT_ASSESSED)

    def blockers(self) -> tuple[str, ...]:
        """Why this snapshot is not fit to hand over."""
        out: list[str] = []
        if blank(self.instruction):
            out.append("the current instruction is not recorded, so the "
                       "receiving advocate does not know what they are asked "
                       "to do")
        if blank(self.next_responsibility):
            out.append("nothing says what the next responsibility is or whose "
                       "it becomes")
        return tuple(out)

    # UNASSESSED SECTIONS ARE DISCLOSED, NOT BLOCKING -- and a first version of
    # this had it wrong.
    #
    # BK-39-AC2 asks for a snapshot "with unassessed sections explicit"; it does
    # not ask for one where nothing is unassessed, and BK-58-AC3's blocking
    # condition is the recipient's ACKNOWLEDGEMENT. Treating "nobody has
    # searched for authorities yet" as a bar to handing over would refuse
    # almost every real matter -- and the pressure that creates is to mark
    # sections assessed to get the handover through, which destroys the very
    # distinction the criterion is about. So `unassessed()` travels with the
    # offer and the receiving advocate decides what to do about it.

    @property
    def handover_complete(self) -> bool:
        return not self.blockers()

    @property
    def handover_blockers(self) -> tuple[str, ...]:
        return self.blockers()


@refuses_blank_text("accepted_at", "declined_because", "withdrawn_at")
@dataclass(frozen=True)
class Handover:
    """One offer of a matter to a named recipient, and what became of it.

    `to_actor` is named at the OFFER. A handover to whoever happens to open it
    next is not a handover; it is an abandonment with a covering note.
    """

    handover_id: str
    matter_id: str
    from_actor: str
    to_actor: str
    offered_at: str
    summary_version: int
    state: HandoverState = HandoverState.OFFERED
    accepted_at: str = ""
    declined_because: str = ""
    withdrawn_at: str = ""
    outstanding: tuple[str, ...] = ()
    """Obligations that are live at the moment of the offer. They do not move
    until the offer is accepted."""

    def owner_of_outstanding(self) -> str:
        """WHO OWNS THE UNRESOLVED WORK RIGHT NOW. BK-58-AC3.

        Not a question about the offer -- a question about who is accountable
        this minute, which is the one a deadline needs answered.
        """
        return self.to_actor if self.state.responsibility_moved else self.from_actor

    def unowned_after(self) -> tuple[str, ...]:
        """Outstanding work that would land on nobody. Empty is the good case.

        A declined or withdrawn handover leaves everything with the offeror,
        which is correct and is not a gap; what this catches is an accepted
        handover with no recipient recorded, which the constructor should have
        refused and which would otherwise silently orphan the work.
        """
        if self.state.responsibility_moved and blank(self.to_actor):
            return self.outstanding
        return ()


def offer(*, handover_id: str, matter_id: str, from_actor: str,
          to_actor: str, offered_at: str, summary: CaseSummary,
          outstanding: tuple[str, ...] = ()) -> Handover:
    """Offer a matter. IT CANNOT BE CREATED ALREADY ACCEPTED.

    The state is not a parameter -- the same discipline `retention.request`
    and `advice.maturity_of` keep. Acceptance is an act by the recipient, and
    a caller that could construct an accepted handover could move
    responsibility onto somebody who never agreed to take it.
    """
    if blank(to_actor):
        raise ValueError(
            "a handover names its recipient. A matter handed to whoever opens "
            "it next is not a handover, it is an abandonment with a note")
    if from_actor == to_actor:
        raise ValueError(
            "the handover is from and to the same actor; nothing moves and "
            "the record would suggest something did")
    blockers = summary.blockers()
    if blockers:
        raise ValueError(
            "this snapshot is not fit to hand over: " + "; ".join(blockers))
    return Handover(
        handover_id=handover_id, matter_id=matter_id, from_actor=from_actor,
        to_actor=to_actor, offered_at=offered_at,
        summary_version=summary.version, state=HandoverState.OFFERED,
        outstanding=outstanding)


def accept(handover: Handover, *, by: str, at: str) -> Handover:
    """The recipient takes it. BY THE NAMED RECIPIENT AND NOBODY ELSE.

    BK-58-AC3 asks for an *authorised recipient acknowledgement*. Accepting on
    somebody's behalf is how responsibility arrives with a person who does not
    know they have it -- which is indistinguishable, afterwards, from a
    handover that worked.
    """
    from dataclasses import replace

    if handover.state is not HandoverState.OFFERED:
        raise ValueError(
            f"this handover is {handover.state.value} and only an offered one "
            f"can be accepted")
    if by != handover.to_actor:
        raise ValueError(
            f"{by!r} is not the recipient this handover names "
            f"({handover.to_actor!r}); acceptance on somebody's behalf leaves "
            f"them responsible for work they have not seen")
    return replace(handover, state=HandoverState.ACCEPTED, accepted_at=at)


def decline(handover: Handover, *, by: str, because: str) -> Handover:
    """Refuse it. The work stays with the offeror, and the reason is kept."""
    from dataclasses import replace

    if by != handover.to_actor:
        raise ValueError(
            f"{by!r} is not the recipient and cannot decline for them")
    if blank(because):
        raise ValueError(
            "a declined handover records why; the offeror has to know what to "
            "fix before offering it again")
    return replace(handover, state=HandoverState.DECLINED,
                   declined_because=because)
