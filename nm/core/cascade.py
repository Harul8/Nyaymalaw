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

from nm.domain.matter import FactId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


@refuses_blank_text()
@dataclass(frozen=True)
class Derived:
    """One value computed from facts, and WHICH facts.

    `from_facts` is what makes the cascade possible at all: without it, a
    correction has to re-run everything and cannot say what it touched.
    """

    name: str
    value: str
    from_facts: tuple[FactId, ...]


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
        if d.name not in old:
            out.append(Change(name=d.name, was="not computed before",
                              now=d.value))
        elif old[d.name] != d.value:
            out.append(Change(name=d.name, was=old[d.name], now=d.value))
    return tuple(out)


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
