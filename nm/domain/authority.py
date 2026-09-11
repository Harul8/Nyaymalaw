"""Who may do what, asked once. BK-63-AC1. P13.

    from nm.domain.authority import Act, Standing, permits

WHY THIS IS ITS OWN MODULE AND NOT A METHOD ON THE COMMISSION
---------------------------------------------------------------
Because four callers ask the same question: the API before it accepts a
command, a background job before it publishes, `nm/domain/decision.py` before
it records a decision, and any future action path before it acts. The moment
two of them decide it for themselves there are two answers to one question --
CLAUDE.md section 4 -- and the one that drifts is whichever is read least. So
the policy is here, once, and every caller consults it.

`ROLE` IS ALREADY TAKEN, AND DELIBERATELY NOT REUSED
------------------------------------------------------
`nm/domain/matter.Role` is the LITIGATION POSTURE -- plaintiff, defendant,
petitioner. This is a different thing entirely: who a person is to the
instruction, not which side the client is on. Naming both `Role` would collapse
two legal states into one word, which is the fifth rule in CLAUDE.md and the
kind of collision that reads fine until somebody passes the wrong one.

THE THIRD STATE IS THE WHOLE POINT
------------------------------------
`Standing.NOT_ESTABLISHED` is what the file holds before anybody has recorded
who this person is. A two-valued answer forces that into "permitted" or
"refused", and both are wrong: refusing blocks an advocate whose own authority
was simply never written down, and permitting lets an unrecorded person concede
a case. So the answer is a `Ruling` with three states and a reason, and only
`PERMITTED` authorises.

A REFUSAL IS A RECORD, NOT A RETURN VALUE
-------------------------------------------
BK-63-AC1 requires that unauthorised operations are "refused AND RECORDED".
A boolean that the caller drops on the floor satisfies the first half and
none of the second, so `Ruling` carries who attempted it, what they attempted
and why it was refused -- everything an audit line needs -- and the caller
writes it down.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.text import refuses_blank_text


class ActingAs(str, Enum):
    """WHAT PART A PERSON PLAYS in this instruction.

    NOT `Capacity`, AND THE NAME MATTERS. `nm/core/screens.Capacity` already
    means something else entirely -- whether the client's capacity TO INSTRUCT
    is in doubt, which is B6's question about a person's legal capacity. Two
    enums called `Capacity` meaning "is this person of sound mind" and "is this
    person the decision maker" is CLAUDE.md's fifth rule broken in one word,
    and it reads fine right up until somebody passes the wrong one.

    ALSO NOT `nm/domain/matter.Role`, which is the litigation posture.

    Not their job title and not their side. A solicitor who instructs and a
    client who decides are two capacities, and the same human can hold both --
    which is why this is recorded per person per matter rather than inferred
    from an account.
    """

    INSTRUCTING = "instructing"
    """Gives instructions. Does NOT thereby decide: an instructing solicitor
    relays what the client wants and cannot concede the client's case."""

    DECIDING = "deciding"
    """Owns the decision -- the client, or somebody holding their written
    authority. The only capacity that may concede, settle or waive."""

    ADVISING = "advising"
    """The advocate. Recommends; does not decide, and a recommendation is not
    an authority to act on it."""

    ASSISTING = "assisting"
    """A colleague, junior or clerk. Reads and drafts; binds nobody."""

    UNKNOWN = "unknown"
    """Nobody has recorded what this person is to this matter.

    A real and common state -- a file exists before its paperwork does -- and
    the reason `permits` answers NOT_ESTABLISHED rather than guessing.
    """

    @classmethod
    def not_established(cls) -> "ActingAs":
        return cls.UNKNOWN


class Act(str, Enum):
    """Something a person may attempt. Named exhaustively, so a new one is a
    change to this enum and not an unlisted default that falls through."""

    READ = "read"
    RECORD = "record"
    """WRITE DOWN WHAT SOMEBODY ELSE INSTRUCTED. Not the same as instructing.

    The advocate keeps the file, so recording the commission is their ordinary
    work -- and the first draft of this module conflated it with `INSTRUCT`,
    which made the advocate unable to write down their own instructions. The
    authority question about an instruction is whether it is ATTRIBUTABLE to
    somebody who could give it, which is a question about the NAMED PARTY and
    not about the person typing.
    """
    INSTRUCT = "instruct"
    """BE THE SOURCE of a material instruction -- objective, scope, deadline,
    work product. Checked against the party the commission names, never
    against the advocate recording it."""
    ADVISE = "advise"
    """Run a substantive turn and produce advice."""
    DECIDE = "decide"
    """Record a decision that binds the conduct of the matter."""
    CONCEDE = "concede"
    """Give up a point, settle, or waive a right. THE ONE THAT LOSES CASES,
    and the reason this module exists."""
    ACT_EXTERNALLY = "act_externally"
    """File, serve, or send something outside the firm."""


#: WHICH CAPACITIES MAY ATTEMPT WHICH ACTS. The whole policy, as data.
#:
#: Authored as a table rather than as branching code so it can be read in one
#: sitting by somebody deciding whether it is right -- which is a different
#: audience from the one that reads the call sites, and the audience that
#: matters for a professional-conduct rule.
#:
#: THE SHAPE OF THE MISTAKE THIS PREVENTS: a recommendation silently becoming
#: an authority. `ADVISING` may advise and may not decide, instruct or concede;
#: `ASSISTING` may only read. Neither is a matter of degree.
PERMITTED: dict[ActingAs, frozenset[Act]] = {
    ActingAs.INSTRUCTING: frozenset({
        Act.READ, Act.RECORD, Act.INSTRUCT, Act.ADVISE}),
    ActingAs.DECIDING: frozenset({
        Act.READ, Act.RECORD, Act.INSTRUCT, Act.ADVISE, Act.DECIDE,
        Act.CONCEDE, Act.ACT_EXTERNALLY}),
    ActingAs.ADVISING: frozenset({Act.READ, Act.RECORD, Act.ADVISE}),
    ActingAs.ASSISTING: frozenset({Act.READ}),
    # UNKNOWN IS NOT IN THIS TABLE. An absent entry is not an empty permission
    # set that happens to refuse -- it is a different answer, and `permits`
    # returns NOT_ESTABLISHED for it rather than REFUSED.
}


class Standing(str, Enum):
    """The answer. Three values, and only one of them authorises."""

    PERMITTED = "permitted"
    REFUSED = "refused"
    NOT_ESTABLISHED = "not_established"
    """Nobody has recorded this person's capacity, so the question cannot be
    answered. NOT a refusal: the fix is to record the capacity, and telling an
    advocate they are forbidden would send them looking for the wrong thing."""

    @classmethod
    def not_established(cls) -> "Standing":
        return cls.NOT_ESTABLISHED

    def authorises(self) -> bool:
        """The ONLY way to ask. A caller comparing to a string would pass on
        `NOT_ESTABLISHED` the day somebody adds a fourth value."""
        return self is Standing.PERMITTED


@refuses_blank_text()
@dataclass(frozen=True)
class Ruling:
    """One decision about one attempt, with everything an audit needs.

    Carries the ATTEMPT, not just the verdict, because BK-63-AC1 requires a
    refused operation to be recorded and a bare boolean records nothing.
    """

    standing: Standing
    actor_id: str
    act: Act
    capacity: ActingAs
    why: str

    def authorises(self) -> bool:
        return self.standing.authorises()

    def as_line(self) -> str:
        """One audit line. NAMES THE PERSON AND THE ATTEMPT, carries no
        client material -- an authority decision is about who, not about
        what the matter says."""
        return (f"authority {self.standing.value} actor={self.actor_id} "
                f"act={self.act.value} capacity={self.capacity.value} "
                f"because={self.why}")

    def as_dict(self) -> dict:
        return {"standing": self.standing.value, "actor_id": self.actor_id,
                "act": self.act.value, "capacity": self.capacity.value,
                "why": self.why}


def permits(actor_id: str, capacity: ActingAs, act: Act) -> Ruling:
    """May this person do this? ONE ANSWER, FOR EVERY CALLER.

    The API asks before accepting a command, a job asks before publishing,
    and `nm/domain/decision.py` asks before recording. None of them decides
    for itself, and `tests/test_one_policy_answers_who_may_act.py` fails the
    build on a second implementation.
    """
    if not (actor_id or "").strip():
        return Ruling(
            standing=Standing.NOT_ESTABLISHED, actor_id="(unnamed)", act=act,
            capacity=capacity,
            why="the attempt names no actor, and an unnamed person has no "
                "recorded capacity to check")
    allowed = PERMITTED.get(capacity)
    if allowed is None:
        return Ruling(
            standing=Standing.NOT_ESTABLISHED, actor_id=actor_id, act=act,
            capacity=capacity,
            why=f"no capacity is recorded for {actor_id} on this matter, so "
                f"whether they may {act.value} is not established. Record "
                f"their capacity on the commission; this is not a refusal.")
    if act in allowed:
        return Ruling(standing=Standing.PERMITTED, actor_id=actor_id, act=act,
                      capacity=capacity,
                      why=f"{capacity.value} may {act.value}")
    return Ruling(
        standing=Standing.REFUSED, actor_id=actor_id, act=act,
        capacity=capacity,
        why=f"{actor_id} is recorded as {capacity.value} on this matter and "
            f"{capacity.value} may {sorted(a.value for a in allowed)}; "
            f"{act.value} is not among them")
