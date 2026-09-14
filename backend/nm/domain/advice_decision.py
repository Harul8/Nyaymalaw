"""A DISPOSITION OF ADVICE, WHICH IS NOT AUTHORITY TO ACT. BK-55-AC3. P27.

    from nm.domain.advice_decision import AdviceDecision, Disposition, authorises

THREE THINGS IN THIS PRODUCT ARE CALLED A DECISION, AND THEY ARE NOT ONE THING
--------------------------------------------------------------------------------
Getting this wrong is the §4 defect -- a second copy of a notion -- and getting
it wrong in the OTHER direction is worse: one type serving two notions means
neither is checkable. So, explicitly:

`nm.domain.decision.Decision`
    A SETTLED QUESTION on the matter: which Act the cause routes to, which
    posture was read. It carries `what`, `because`, `alternatives` and `by`
    (product or advocate), and its point is that the same question is not
    silently re-decided next turn. A routing decision has no owner and no
    review trigger, and giving it some to reuse the type would put two empty
    fields on every routing this product makes.

Appendix E's `DecisionRecord`
    THE CLIENT'S INSTRUCTION, with capacity, voluntariness, understanding
    confirmed, scope, effective dates and confirmation evidence -- seventeen
    required fields. It is what turns advice into authority for an external
    act. It is NOT implemented; `backend/nm/domain/capacity.py` says so, and this
    module does not implement it either. Naming this type `DecisionRecord`
    would let a five-field record read as a seventeen-field obligation met.

`AdviceDecision`, here
    WHAT THE ADVOCATE DECIDED TO DO ABOUT A PIECE OF ADVICE -- accept, reject,
    narrow or defer it -- with the authorised actor, the advice version, the
    scope, the owner and what brings it back. BK-55-AC3, and nothing else.

THE CLAUSE THIS MODULE TURNS ON
---------------------------------
*never turns a recommendation into action authority.* `authorises()` is the
whole answer. It exists as a function rather than a comment so the question has
somewhere to be asked, and so the answer arrives as a sentence the advocate can
be shown rather than as an absence a caller fills in for itself.

A RECOMMENDATION, SILENCE, AND A DECISION ARE THREE STATES. `NOT_DECIDED` is
the third, and it is the default: advice sitting unread must never read as
advice adopted.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Disposition(str, Enum):
    """What was decided about a piece of advice."""

    ACCEPT = "accept"
    REJECT = "reject"
    NARROW = "narrow"
    DEFER = "defer"
    NOT_DECIDED = "not_decided"
    """NOBODY HAS DECIDED. Silence is not acceptance."""

    @classmethod
    def not_established(cls) -> "Disposition":
        return cls.NOT_DECIDED

    @property
    def is_decided(self) -> bool:
        return self is not Disposition.NOT_DECIDED


#: What BK-55-AC3 requires a decision to record, and how an absent one reads.
#: Named once; `absent()` and the served projection both read this rather than
#: keeping their own lists.
REQUIRED: dict[str, str] = {
    "decided_by": "the authorised actor who decided",
    "advice_version": "the version of the advice decided on",
    "scope": "the scope the decision covers",
    "owner": "who owns the decision",
    "review_trigger": "what brings it back for review",
}


@refuses_blank_text(*REQUIRED, "narrowed_to", "because", "decided_at",
                    "superseded_by")
@dataclass(frozen=True)
class AdviceDecision:
    """One disposition of one version of one piece of advice.

    `advice_version` is not decoration. A decision taken against version 3 and
    read after version 4 was derived is a decision about something the advocate
    can no longer see -- and P28 turns on being able to tell.

    Every field is exempt from the blank rule because emptiness is a state this
    type must express: `absent()` reports it, and the alternative is callers
    inventing an owner and a trigger in order to construct an object at all.
    """

    decision_id: str
    disposition: Disposition = Disposition.NOT_DECIDED
    decided_by: str = ""
    decided_at: str = ""
    advice_version: str = ""
    scope: str = ""
    owner: str = ""
    review_trigger: str = ""
    narrowed_to: str = ""
    """What survived the narrowing. Required when the disposition is NARROW: a
    narrowing that does not say what remains is a rejection nobody called
    one."""

    because: str = ""
    superseded_by: str = ""
    """Withdrawn by a later record, never by deletion -- the rule Appendix E
    states for its own record, and it applies here for the same reason."""

    def absent(self) -> tuple[str, ...]:
        """Everything BK-55-AC3 requires that this does not carry.

        An undecided record is not incomplete -- there is nothing yet to
        record -- so it reports nothing absent. Reporting five gaps against
        advice nobody has looked at would make the real gaps unreadable.
        """
        if not self.disposition.is_decided:
            return ()
        missing = [label for name, label in REQUIRED.items()
                   if blank(getattr(self, name, ""))]
        if self.disposition is Disposition.NARROW and blank(self.narrowed_to):
            missing.append("what the advice was narrowed to")
        return tuple(missing)

    @property
    def is_current(self) -> bool:
        return blank(self.superseded_by)


def authorises(decision: AdviceDecision) -> tuple[bool, str]:
    """MAY THIS AUTHORISE AN EXTERNAL ACT? No, and here is the sentence.

    It always answers no, and that is the rule rather than a check that cannot
    fail. S11 is a condition that can never be true; this is a QUESTION whose
    true answer happens to be constant, and having it answered in one place
    beats every caller deciding for itself what a recorded acceptance permits.

    Filing, sending, settling or conceding needs Appendix E's `DecisionRecord`
    -- the client's instruction with capacity and voluntariness recorded --
    and that record is not implemented. So nothing in this product authorises
    an external act today, which is the honest state and is said as one.
    """
    if not decision.disposition.is_decided:
        return False, ("nobody has decided on this advice; silence is not "
                       "acceptance and it is certainly not authority")
    return False, (
        f"this records that the advice was {decision.disposition.value}ed by "
        f"{decision.decided_by or 'an unnamed actor'}. It is not authority to "
        f"file, send, settle or concede: that needs the client's instruction "
        f"on Appendix E's DecisionRecord, with capacity and voluntariness "
        f"recorded, and no such record exists on this matter")


def supersede(previous: AdviceDecision, by: str) -> AdviceDecision:
    """Withdraw a decision by naming its replacement, never by deleting it.

    The history is what lets an advocate answer *when did we decide that, and
    against which advice*, which is the question a decision record exists for.
    """
    if blank(by):
        raise ValueError(
            "a decision is superseded BY something; withdrawing it with no "
            "replacement named is deletion with extra steps")
    return replace(previous, superseded_by=by)
