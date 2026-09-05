"""The correction cascade. PRD §5.4, eval E-092.

*"Actually the notice was served on 12 August, not 10."*

That touches the chronology, the limitation date, the proof position, the
recommendation, and possibly ADVICE FROM AN EARLIER TURN THE ADVOCATE HAS
ALREADY ACTED ON.

THE RULE, IN THREE PARTS
--------------------------
When a material fact changes:

  1. every item derived from it is recomputed;
  2. each recomputed item WHOSE VALUE CHANGED is reported WITH WHAT IT WAS;
  3. where earlier advice is affected, that is said in terms — INCLUDING
     WHETHER ANYTHING ALREADY DONE NEEDS UNDOING.

The third is the one a silent recompute loses, and it is the one that matters:
an advocate who filed on Tuesday against a date that moved on Thursday needs to
be told, not to be shown a corrected number.

E-092's counterexample is *a limitation date silently recomputed with no note
that it moved.* Both halves of that are defects. Recomputing is right;
recomputing SILENTLY is the failure — a value that changes with no history is
one the advocate cannot reconcile against what they remember, and they will
assume they misread it.

THE BOUND
-----------
*Only MATERIAL facts trigger the cascade, and where re-derivation changes
nothing the answer is one line.* A product that announced a cascade on every
turn would train the advocate to skip the section where the real one appears.
So `report` returns one line for an empty change set rather than a heading with
nothing under it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import FactId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


@refuses_blank_text()
class Kind(str, Enum):
    """What sort of derived value this is. See `Derived.kind`."""

    POSITION = "position"
    """A value the advocate acts on: a date, an amount, a holding."""

    MEASUREMENT = "measurement"
    """A count of what the file now contains. Grows as the matter does."""


@dataclass(frozen=True)
class Derived:
    """One value computed from facts, and WHICH facts.

    `from_facts` is what makes the cascade possible at all: without it, a
    correction has to re-run everything and cannot say what it touched.
    """

    name: str
    value: str
    from_facts: tuple[FactId, ...]
    kind: Kind = Kind.POSITION
    """POSITION or MEASUREMENT, and the difference decides what is news.

    A limitation date moving from 1987 to 2027 is a CORRECTION: something the
    advocate relied on is now different and §5.4 requires it reported with its
    prior. An issue count moving from 1 to 2 is ACCUMULATION: the file grew,
    which is what a conversation does.

    Measured on GS-15, 5 September 2026 — the run where the spine finally
    passed. The cascade fired on all five turns, because evidence appeared on
    turn 2, the issues went 1 to 2 on turn 4 and the opponent's case changed
    on turn 5. Every one raised a blocking "does anything need undoing" gap.
    §5.4's own bound says why that is a defect: a product that announces a
    cascade every turn trains the advocate to skip the section, and the real
    one then arrives in a place they have learned to ignore.

    BOTH KINDS ARE STILL WATCHED FOR LOSS. A measurement that stops being
    computed is exactly the forgetting `lost` exists to find; what changes is
    that its GROWTH is not announced as a correction."""


@refuses_blank_text("undo")
@dataclass(frozen=True)
class Change:
    """A derived value that MOVED, and what it was before.

    `was` is required. A change reported without its prior value is a number
    the advocate cannot reconcile against what they remember, and the honest
    reading of that is that they misread it the first time.
    """

    name: str
    was: str
    now: str
    undo: str = ""
    """What already done needs undoing, where anything does.

    Empty means NOT THAT NOTHING DOES -- it means nothing was identified, and
    `advice_at_risk` is what reports the ones nobody answered that question
    for."""


@refuses_blank_text()
@dataclass(frozen=True)
class PriorAdvice:
    """Something already said, and what it rested on.

    Carried so §5.4's third part is answerable. Advice with no record of what
    it depended on cannot be revisited when the dependency moves, and the
    advocate has already acted on it.
    """

    what: str
    given_at_turn: str
    rested_on: tuple[str, ...]
    """The names of the derived values it relied on."""


@implements("A3")
def dependents(items: tuple[Derived, ...],
               changed: tuple[FactId, ...]) -> tuple[Derived, ...]:
    """Everything derived from a fact that moved.

    THE POPULATION IS THE DERIVED ITEMS, asked which of them touch a changed
    fact. Asked the other way -- which changed facts appear in the items --
    it would confirm that the facts it knew about were known about, which
    cannot fail.
    """
    moved = set(changed)
    return tuple(d for d in items if moved & set(d.from_facts))


@implements("A3")
def changes(before: tuple[Derived, ...],
            after: tuple[Derived, ...]) -> tuple[Change, ...]:
    """Recomputed values that actually MOVED, each with its prior.

    Only the ones that changed. §5.4's bound is explicit that where
    re-derivation changes nothing the answer is one line, and a list of
    unchanged values is the noise that hides the changed one.

    A value that APPEARS -- computed now and not before -- is a change with no
    prior, and it is reported as such rather than skipped: "this was not
    computed before" is information, and silently adding a limitation date is
    the same defect as silently moving one.
    """
    old = {d.name: d.value for d in before}
    out: list[Change] = []
    for d in after:
        # ACCUMULATION IS NOT A CORRECTION. A measurement that grew is the
        # file growing, which is what a conversation does; announcing it as a
        # cascade spends the signal that a real correction needs.
        if d.kind is Kind.MEASUREMENT:
            continue
        if d.name not in old:
            out.append(Change(name=d.name, was="not computed before",
                              now=d.value))
        elif old[d.name] != d.value:
            out.append(Change(name=d.name, was=old[d.name], now=d.value))
    return tuple(out)


@implements("A3")
def lost(before: tuple[Derived, ...],
         after: tuple[Derived, ...]) -> tuple[Derived, ...]:
    """Derivations that were computed BEFORE and are not computed now.

    THE POPULATION IS `before`, AND THAT IS THE WHOLE POINT. `changes` walks
    `after` and asks what moved, so a value that simply STOPPED BEING
    COMPUTED produces nothing from it — the docstring above reasons carefully
    about a value that appears and never about one that vanishes. Asked in
    that direction the check cannot find forgetting, which is the one thing it
    is for.

    This is why it matters here more than anywhere else. Most of what the
    product derives is re-derived from scratch every turn by a model read: the
    issues, the theory, the opponent's case, the evidence inventory. A read
    that returns nothing on turn 9 having returned three issues on turn 2 does
    not fail — it succeeds, quietly, with less. The answer is thinner and
    nothing in the product could tell.

    Returns the PRIOR rows rather than their names, because what the advocate
    needs is what was lost, not a count of it: "the limitation position on
    thread 2, which was 2027-06-12" is actionable and "1 derivation lost" is
    not.
    """
    now = {d.name for d in after}
    return tuple(d for d in before if d.name not in now)


@implements("A3")
def advice_at_risk(prior: tuple[PriorAdvice, ...],
                   moved: tuple[Change, ...]) -> tuple[PriorAdvice, ...]:
    """§5.4's THIRD PART, and the one a silent recompute loses.

    *Where earlier advice is affected, that is said in terms, including whether
    anything already done needs undoing.*

    An advocate who filed on Tuesday against a date that moved on Thursday
    needs to be told. Showing them a corrected number is not telling them.
    """
    names = {c.name for c in moved}
    return tuple(a for a in prior if names & set(a.rested_on))


@implements("A3")
def unresolved_undo(moved: tuple[Change, ...]) -> tuple[str, ...]:
    """Changes where nobody said whether anything needs undoing.

    Empty `undo` is not "nothing needs undoing" -- it is a question nobody
    answered, and the two must not read alike. This is the third state, made
    into a list so it cannot be silent.
    """
    return tuple(c.name for c in moved if not c.undo.strip())


@implements("A3")
def report(moved: tuple[Change, ...],
           affected: tuple[PriorAdvice, ...] = ()) -> tuple[str, ...]:
    """What the advocate reads. ONE LINE where nothing moved.

    §5.4's bound. A product that announced a cascade every turn would train
    them to skip the section, and the real one would arrive in a place they had
    learned to ignore.
    """
    if not moved:
        return ("Re-derived everything that rested on the corrected fact; "
                "nothing changed.",)
    lines = [f"{c.name}: was {c.was}, now {c.now}"
             + (f" — {c.undo}" if c.undo else "")
             for c in moved]
    lines.extend(
        f"Advice given at turn {a.given_at_turn} rested on this and is "
        f"superseded: {a.what}" for a in affected)
    return tuple(lines)
