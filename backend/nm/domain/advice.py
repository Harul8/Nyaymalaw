"""ADVICE AT THE MATURITY IT ACTUALLY HAS. BK-50-AC1, BK-96-AC2, BK-96-AC3. P26.

    from nm.domain.advice import Maturity, Recommendation, releasable

WHAT THIS IS FOR
------------------
An advocate reads the top of an answer and decides whether to act on it. The
product therefore has to be able to say *how far this has actually got* --
and to be unable to say more than that.

Two failures, and the second is the one that looks like diligence:

* advice released as though it were settled when a prerequisite is missing;
* advice buried under background, so the reader reconstructs the position
  from the working instead of being told it.

`nm.domain.brief` already owns WHERE things appear -- `Section`, `ORDER`,
`HEADINGS`, with POSITION first because "counsel opens an advice looking for
the position and the step". This module owns WHETHER there is a position to
put there, and what a recommendation must carry before it may be one.

MATURITY IS DERIVED, NEVER DECLARED
-------------------------------------
`maturity_of` reads the prerequisites and the support. Nothing accepts a
maturity as an argument, for the same reason `retention.request` does not
accept a state: a value a caller can pass is a value a caller can get wrong,
and the wrong answer here is *this is settled*.

    A missing prerequisite lowers the maturity. It never disappears, and it is
    never replaced by a confident sentence about something else -- which is
    CLAUDE.md's "a right answer to a question nobody asked".

WHAT A RECOMMENDATION MUST CARRY
----------------------------------
BK-96-AC2 names seven things: the position, why the alternatives lose, the
next action, the responsible owner, the attributed by-when, the fallback, and
the fact that would change the view. Each is a FIELD, and each may be empty --
but an empty one is rendered as *not established* rather than dropped, because
a template silently filled with a plausible owner and a plausible date is the
defect this criterion exists to refuse. `absent()` names them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Maturity(str, Enum):
    """How far the advice has actually got. Ordered, worst first.

    NOT a confidence score. Each value is a statement about what EXISTS --
    which prerequisites are met and what supports the position -- so it can be
    checked against the file rather than felt.
    """

    NOT_ASSESSED = "not_assessed"
    """Nothing has been worked out yet. The third state, and the default:
    a turn that could not run says so rather than releasing an empty shape."""

    BLOCKED = "blocked"
    """A controlling question is outstanding and the answer turns on it. What
    the reader gets is the question, not a position hedged around it."""

    PROVISIONAL = "provisional"
    """A position exists and rests on something inferred or unverified. It may
    be acted on with the reservation attached, and the reservation travels."""

    SUPPORTED = "supported"
    """The position rests on attributed material and every prerequisite the
    task declares is met. This is as far as this product goes on its own."""

    @classmethod
    def not_established(cls) -> "Maturity":
        return cls.NOT_ASSESSED

    @property
    def may_be_released(self) -> bool:
        """NOT_ASSESSED never reaches the advocate as advice. It reaches them
        as a statement that nothing was worked out, which is a different
        sentence and is rendered by a different owner."""
        return self is not Maturity.NOT_ASSESSED


#: WHAT THE PRD'S E2 DECLARES, field for field:
#:
#:     Recommendation { position, why_alternatives_lose[], next_step{action,
#:                      owner, by_when}, fallback, changing_fact }
#:
#: The names are the PRD's, not this module's preference. `Recommendation` was
#: carried in `test_reached_from_production.UNTYPED` as *"E2. BUILT AS A
#: STRING. `turn._recommend` composes prose; the PRD declares a record. B-074
#: is what an untyped recommendation costs -- nothing could ask it what it was
#: based on, so it contradicted the finding printed beneath it."* Typing it is
#: this packet's job, and typing it under different names would leave the
#: declaration true in substance while the checker went quiet.
#:
#: Each maps to one of BK-96-AC2's seven, and the label is how an absent one is
#: reported. Named ONCE: the renderer, the served projection and the test that
#: counts them all read this rather than keeping three lists that drift.
REQUIRED_FIELDS: dict[str, str] = {
    "position": "the supported position",
    "why_alternatives_lose": "why the alternatives lose",
    "fallback": "the fallback if it does not hold",
    "changing_fact": "the fact that would change this view",
}

#: The same, for the nested step. Separate because `next_step` is one field of
#: the record and three obligations of the criterion.
REQUIRED_STEP_FIELDS: dict[str, str] = {
    "action": "the next action",
    "owner": "who is responsible for it",
    "by_when": "by when",
}


@refuses_blank_text(*REQUIRED_STEP_FIELDS, "by_when_basis")
@dataclass(frozen=True)
class NextStep:
    """`next_step{action, owner, by_when}` from E2, plus who says so.

    `by_when_basis` is not in the PRD's field list and is required by
    BK-96-AC2, which asks for an ATTRIBUTED by-when. A date with no basis is a
    guess wearing a deadline's clothes -- the product has already been measured
    telling an advocate to file "within the limitation period" while the period
    had run (B-074) -- so a by-when whose basis is empty is reported absent
    even though it carries text.

    Every field is exempt from the blank rule because emptiness is the state
    this type exists to express. Refusing construction would push callers into
    inventing an owner and a date to obtain an object, which is the fabrication
    BK-96-AC2 forbids in as many words.
    """

    action: str = ""
    owner: str = ""
    by_when: str = ""
    by_when_basis: str = ""

    def absent(self) -> tuple[str, ...]:
        missing = [label for name, label in REQUIRED_STEP_FIELDS.items()
                   if blank(getattr(self, name, ""))]
        if not blank(self.by_when) and blank(self.by_when_basis):
            missing.append("on whose authority the by-when rests")
        return tuple(missing)


@refuses_blank_text(*REQUIRED_FIELDS)
@dataclass(frozen=True)
class Recommendation:
    """E2's record, typed at last. BK-96-AC2.

    EVERY REQUIRED FIELD IS EXEMPT FROM THE BLANK RULE, deliberately rather
    than laxly: their emptiness is the state this type exists to express, so
    that `absent()` can report it and the renderer can print *not established*
    instead of a plausible invention.

    `maturity` is not a field. It is derived by `maturity_of` from the
    prerequisites and the support, for the same reason `retention.request`
    takes no state: a value a caller can pass is a value a caller can get
    wrong, and the wrong answer here is *this is settled*.
    """

    position: str = ""
    why_alternatives_lose: tuple[str, ...] = ()
    next_step: NextStep = field(default_factory=NextStep)
    fallback: str = ""
    changing_fact: str = ""
    reservations: tuple[str, ...] = ()
    """MATERIAL RESERVATIONS, which survive the concise view. A reservation
    that appears only in the expanded rendering is one the reader who acted on
    the summary never saw."""

    def absent(self) -> tuple[str, ...]:
        """Every required thing this recommendation does not carry, by name.

        The population comes from `REQUIRED_FIELDS` and `REQUIRED_STEP_FIELDS`,
        so a field added there is counted here the same day rather than on the
        day somebody remembers to extend a second list.
        """
        missing = [label for name, label in REQUIRED_FIELDS.items()
                   if blank(getattr(self, name, ""))]
        return tuple(missing) + self.next_step.absent()


def maturity_of(*, has_position: bool, controlling_question: str = "",
                unmet_prerequisites: tuple[str, ...] = (),
                inferred_support: bool = False,
                withheld: bool = False) -> Maturity:
    """Derive maturity from what EXISTS. The one owner, and it takes no
    maturity argument.

    THE ORDER OF THESE TESTS IS THE RULE. Withholding outranks everything: a
    turn whose analysis was withheld has no maturity to report, and letting it
    fall through to PROVISIONAL is how a gated answer reaches the ordinary
    renderer looking like ordinary advice (BK-96-AC3's last clause).

    A controlling question outranks a position, because a position that turns
    on an unanswered question is not a position the reader may act on -- they
    may act on the question.
    """
    if withheld or not has_position:
        return Maturity.NOT_ASSESSED if withheld else (
            Maturity.BLOCKED if controlling_question else Maturity.NOT_ASSESSED)
    if controlling_question:
        return Maturity.BLOCKED
    if unmet_prerequisites or inferred_support:
        return Maturity.PROVISIONAL
    return Maturity.SUPPORTED


def refuse_release(recommendation: Recommendation, maturity: Maturity,
                   *, withheld: bool = False, stale: bool = False,
                   truncated: bool = False) -> str:
    """Why this may not be rendered as ordinary advice, or "".

    BK-96-AC3: *failed or withheld analysis cannot enter the ordinary
    recommendation renderer.* Three ways an answer can be unfit and they are
    reported separately, because they need different things from the reader:
    a withheld turn needs the gate cleared, a stale one needs re-deriving, and
    a truncated one needs the run repeating.

    ONE OWNER FOR THE QUESTION, called by the renderer and by the served
    projection, on the rule §4 states: a check with one caller is a check
    until somebody adds a second path.
    """
    if withheld:
        return ("the analysis was withheld by a gate; a withheld turn is "
                "reported as withheld and never rendered as advice")
    if stale:
        return ("the analysis rests on material that has since moved; it is "
                "reopened rather than served as current")
    if truncated:
        return ("the analysis did not finish; a partial derivation rendered as "
                "advice reads as a complete answer that happens to be short")
    if not maturity.may_be_released:
        return ("nothing was worked out on this thread, which is said plainly "
                "rather than shaped into a recommendation")
    if maturity is not Maturity.BLOCKED and blank(recommendation.position):
        return ("the recommendation carries no position; an answer with no "
                "position is background, and background is not the top of an "
                "advice")
    return ""
