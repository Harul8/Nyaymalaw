"""What has been DECIDED on a matter, and by whom. The `decisions` section.

WHY THIS EXISTS
-----------------
NM makes decisions on every turn and records none of them. It routes a cause to
an Act, settles a posture, takes a theory, and picks an action — and each one
is disclosed as a sentence that vanishes when the turn ends.

    "You named no provision, so I resolved one: the cause reads as specific
     performance, which the graph routes to Limitation Act, 1963 Article 54"

That is a decision with a reason and, where the graph offers them,
alternatives. It was made on turn 1 of GS-15 and made again on turns 2, 3, 4
and 5, from scratch, with nothing checking that the answer was the same.

WHAT A DECISION BUYS, AND IT IS THE ADVOCATE-SHAPED PART
----------------------------------------------------------
An advocate does not re-decide a settled question every time they are asked
something. They decided to proceed under s.53A; that stands until a reason to
revisit it appears, and if it changes they say so and say why.

So a decision RECORDED is a decision that can be:

  * held stable — the same choice is not silently made differently next turn;
  * shown to change — a routing that moves between turns is a cascade event
    and not a fresh sentence in the same place as last time;
  * REVERSED BY THE ADVOCATE, which is the whole point of naming alternatives.
    A product decision the advocate can overturn in four words is a
    collaboration; one they cannot see is a guess they will discover in court.

WHO DECIDED IS A FIELD, NOT A CONVENTION
------------------------------------------
`by` separates a choice the PRODUCT made from one the ADVOCATE made, because
the two have opposite defaults. A product decision is provisional and invites
correction; an advocate decision is instruction and must not be quietly
re-derived. Collapsing them would let the product overwrite its instructions
with its own inferences — which is the posture defect (C3) in a different
place.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import ThreadId, TurnId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


class DecidedBy(str, Enum):
    """Whose choice this was. THREE STATES, and the third is not decoration."""

    ADVOCATE = "advocate"
    """They said so. Instruction, never re-derived."""

    PRODUCT = "product"
    """We inferred it. Provisional, and it says so."""

    NOT_RECORDED = "not_recorded"
    """A decision read back from a record that did not say who made it.

    A record written before this field existed cannot be assigned to either
    side, and guessing would turn our own inference into the advocate's
    instruction — which is the one direction that must never happen silently.
    """


@refuses_blank_text()
@dataclass(frozen=True)
class Decision:
    """One settled question, with its reason and what else it could have been."""

    what: str
    """The choice, in the terms an advocate would use."""
    because: str
    """Why. A decision with no reason cannot be argued with, and a decision
    the advocate cannot argue with is one they have to take on trust."""
    at_turn: TurnId
    thread: ThreadId = ""
    by: DecidedBy = DecidedBy.NOT_RECORDED
    alternatives: tuple[str, ...] = ()
    """What else it could have been. Named where the choice had a rival.

    An advocate reading "we are proceeding under Article 54" learns what we
    did; one reading "also arguable: Article 65" learns what we did NOT do,
    which is the half they can correct.
    """

    @property
    def provisional(self) -> bool:
        """A product decision invites correction. An advocate's does not."""
        return self.by is not DecidedBy.ADVOCATE


def _fold(text: str) -> str:
    return " ".join((text or "").lower().split())


@implements("A3")
def merge(standing: tuple[Decision, ...], made: tuple[Decision, ...],
          ) -> tuple[Decision, ...]:
    """The decisions on the thread after this turn. THE LIST IS NOT REPLACED.

    IDENTITY IS THE QUESTION, NOT THE ANSWER. Two decisions about the same
    thing are one decision that may have changed, and keying on `what` alone
    would file "route to Article 54" and "route to Article 65" as two settled
    questions rather than one that moved. So the key is the question --
    everything before the first colon -- and `moved` reports the rest.

    AN ADVOCATE'S DECISION IS NOT OVERWRITTEN BY THE PRODUCT'S. They said so;
    inferring otherwise later is the product overruling its instructions,
    which is C3 in a different place. The reverse IS permitted: an advocate
    may overrule us, and that is the point of showing them the alternatives.
    """
    out = list(standing)
    index = {_question(d.what): i for i, d in enumerate(out)}
    for decision in made:
        key = _question(decision.what)
        if key not in index:
            index[key] = len(out)
            out.append(decision)
            continue
        was = out[index[key]]
        if was.by is DecidedBy.ADVOCATE and decision.by is not DecidedBy.ADVOCATE:
            continue
        out[index[key]] = decision
    return tuple(out)


@implements("A3")
def moved(standing: tuple[Decision, ...], made: tuple[Decision, ...],
          ) -> tuple[tuple[Decision, Decision], ...]:
    """Settled questions this turn answered DIFFERENTLY, as (was, now) pairs.

    The pair, not the new value alone. §5.4's rule everywhere else in this
    build: a changed value is reported WITH its prior, because an advocate who
    is shown only the new answer cannot tell whether it moved.
    """
    index = {_question(d.what): d for d in standing}
    out = []
    for decision in made:
        was = index.get(_question(decision.what))
        if was is not None and _fold(was.what) != _fold(decision.what):
            out.append((was, decision))
    return tuple(out)


def _question(what: str) -> str:
    """The QUESTION a decision answers, which is what makes two of them one.

    Everything before the first colon. The product writes its decisions as
    "<question>: <answer>" precisely so this is possible without parsing
    prose — and a decision with no colon is its own question, which is the
    honest reading of a sentence that does not separate the two.
    """
    head = (what or "").split(":", 1)[0]
    return _fold(head)


@implements("A3")
def from_stored(values) -> tuple[Decision, ...]:
    """Decisions read back off a thread, whatever shape the store returned.

    `Thread.decisions` is untyped for the reason `theory` and `issues` are:
    this module imports `nm.domain.matter`, so `matter` cannot name `Decision`
    without a cycle, and the generic decoder hands back plain dicts.

    A row that cannot be rebuilt is DROPPED AND THE REST KEPT, and one that
    does not say who decided becomes NOT_RECORDED rather than being guessed
    at. Guessing would promote our own inference to the advocate's
    instruction, which the merge then refuses to overwrite — a wrong guess
    here becomes permanent.
    """
    if not values:
        return ()
    out: list[Decision] = []
    for v in values:
        if isinstance(v, Decision):
            out.append(v)
            continue
        if not isinstance(v, dict):
            continue
        try:
            out.append(Decision(
                what=str(v["what"]),
                because=str(v["because"]),
                at_turn=TurnId(str(v.get("at_turn") or "")),
                thread=ThreadId(str(v.get("thread") or "")),
                by=DecidedBy(v.get("by") or DecidedBy.NOT_RECORDED),
                alternatives=tuple(str(a) for a in v.get("alternatives") or ()),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return tuple(out)
