"""Case theory. D6.

ONE THEORY PER THREAD, AND A MENU IS NOT A THEORY
---------------------------------------------------
D6's first NEVER: *never offer two theories in parallel. A menu is the survey
this document already rejects.* An advocate handed three theories has been
handed the work back, so `for_thread` refuses a second one on the same thread
rather than ranking them.

A DEFENDING PARTY'S THEORY IS NOT "WE DENY"
---------------------------------------------
*"The cheque was security for a loan that was repaid" is a theory; "the
complainant has not proved his case" is a hope that the other side fails.*

A bare denial is sometimes right, and when it is it is a CHOSEN STRATEGY with
reasons — never arrived at by default. `Theory` therefore requires
`chosen_because` when it is a denial, so the default is impossible to reach
without saying why.

WHY E-081 DOES NOT READ ENGLISH
---------------------------------
*"I never signed it"* and *"I signed it under a misrepresentation"* are
inconsistent, and no amount of string comparison shows it. Pleading in the
ALTERNATIVE is permitted and routine; what destroys credibility is two
inconsistent FACTUAL accounts, and the difference is not in the words.

So an argument declares the factual account it NEEDS: which facts it requires
to be true and which it requires to be untrue. Two arguments that need opposite
values of the same fact are inconsistent, exactly, by set arithmetic — and an
argument that declares nothing cannot be silently consistent with everything,
because `unaccounted` reports it.

That is the same move as every other check in this build: make the question
structural so the answer does not depend on reading prose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.matter import FactId, Side, ThreadId
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class Stance(str, Enum):
    """How the theory stands to the claim."""

    AFFIRMATIVE = "affirmative"
    """A positive account: what happened and why we win."""

    DENIAL = "denial"
    """A bare denial. Permitted, and only as a CHOSEN strategy with reasons."""

    NOT_ESTABLISHED = "not_established"
    """No theory has been formed yet. NOT "there is no theory to form"."""


@refuses_blank_text("chosen_because", "relief")
@dataclass(frozen=True)
class Theory:
    """One sentence: what happened and why we win. D6's PRODUCES."""

    thread: ThreadId
    theme: str
    """The sentence a judge could repeat back."""
    account: str = ""
    """The factual account, consistent with the record."""
    legal_theory: str = ""
    """What converts the account into relief."""
    relief: str = ""
    stance: Stance = Stance.NOT_ESTABLISHED
    for_side: Side = Side.UNKNOWN
    explains: tuple[FactId, ...] = ()
    """Adverse facts this theory EXPLAINS."""
    concedes: tuple[FactId, ...] = ()
    """Adverse facts EXPRESSLY CONCEDED. Conceding is an answer; ignoring is not."""
    chosen_because: str = ""
    """Required for a DENIAL. See the module docstring."""

    def __post_init__(self) -> None:
        if self.stance is Stance.DENIAL and blank(self.chosen_because):
            raise ValueError(
                f"a bare denial on thread {self.thread!r} with no reasons. "
                f"'The complainant has not proved his case' is a hope that the "
                f"other side fails, not a theory — where a denial is genuinely "
                f"right it is a CHOSEN strategy and says why, never one arrived "
                f"at by default.")
        if self.stance is Stance.AFFIRMATIVE and blank(self.relief):
            raise ValueError(
                f"an affirmative theory on thread {self.thread!r} names no "
                f"relief. A theme with nothing to ask for is a story.")
        if set(self.explains) & set(self.concedes):
            raise ValueError(
                "a fact cannot be both explained and conceded. Which one it is "
                "decides what is pleaded.")


@implements("D6")
def for_thread(theories: tuple[Theory, ...], thread: ThreadId) -> Theory | None:
    """The one theory on this thread, or `None`.

    RAISES on a second one rather than picking. D6: *never offer two theories
    in parallel.* Ranking them here would be the menu wearing an ordering, and
    the advocate would still have to choose.
    """
    mine = [t for t in theories if t.thread == thread]
    if len(mine) > 1:
        raise ValueError(
            f"{len(mine)} theories on thread {thread!r}: "
            f"{[t.theme[:40] for t in mine]}. Exactly one per thread — a menu "
            f"is the survey D6 rejects, and offering two is handing the work "
            f"back to the advocate.")
    return mine[0] if mine else None


@implements("D6")
def unaccounted(adverse: tuple[FactId, ...], theory: Theory | None,
                ) -> tuple[FactId, ...]:
    """E-080'S INVARIANT. Adverse facts the theory neither explains nor concedes.

    E-080's counterexample is *a theory that works only if three documents are
    forgotten* — and it reads perfectly, because the three are simply not
    mentioned. Absence is invisible; this makes it a list.

    THE POPULATION IS THE ADVERSE FACTS, drawn from the file rather than from
    the theory's own two tuples. Asked the other way it would confirm that
    everything the theory mentioned was mentioned, which cannot fail.

    With no theory at all, EVERY adverse fact is unaccounted — not none. A
    thread with no theory has not disposed of its adverse facts by not having
    one.
    """
    if theory is None:
        return tuple(adverse)
    handled = set(theory.explains) | set(theory.concedes)
    return tuple(f for f in adverse if f not in handled)


# ------------------------------------------------ E-081, structurally ------


@refuses_blank_text()
@dataclass(frozen=True)
class Argument:
    """One argument, AND THE FACTUAL ACCOUNT IT REQUIRES.

    `requires` maps a fact to what this argument needs it to be: `True` for
    "this happened", `False` for "this did not". That is what makes
    inconsistency computable without reading the sentences.

    An argument that declares nothing is not silently compatible with
    everything -- `undeclared` reports it, because an argument whose factual
    commitments nobody wrote down is one nothing can check.
    """

    statement: str
    thread: ThreadId
    requires: dict[FactId, bool] = field(default_factory=dict)
    in_the_alternative: bool = False
    """Pleading in the ALTERNATIVE is permitted and routine.

    It does not license an inconsistent FACTUAL account, and this flag
    deliberately does not suppress the check -- *"I never borrowed the money,
    and in any event I repaid it"* loses whether or not it is labelled
    alternative. The flag is carried so the answer can say which arguments are
    pleaded that way, never so one can opt out."""


@implements("D6")
def inconsistent(arguments: tuple[Argument, ...],
                 ) -> tuple[tuple[str, str, FactId], ...]:
    """D6: *never run two arguments requiring inconsistent factual accounts.*

    Returns the pairs and the fact they disagree about, so the advocate can see
    which two and on what -- a boolean would tell them their case is
    contradictory and leave them to find it.

    *"I never signed it"* needs `signed: False`; *"I signed it under a
    misrepresentation"* needs `signed: True`. No string comparison shows that;
    the arithmetic does.
    """
    out: list[tuple[str, str, FactId]] = []
    for i, a in enumerate(arguments):
        for b in arguments[i + 1:]:
            if a.thread != b.thread:
                continue
            for fact, needed in a.requires.items():
                if fact in b.requires and b.requires[fact] != needed:
                    out.append((a.statement[:60], b.statement[:60], fact))
    return tuple(out)


@implements("D6")
def undeclared(arguments: tuple[Argument, ...]) -> tuple[str, ...]:
    """Arguments that declare no factual commitments at all.

    The positive control for `inconsistent` in production: an argument
    declaring nothing can never contradict anything, so a file of them would
    report a clean bill of health forever. That is the shape B-049 was, and it
    is why this is computed rather than assumed away.
    """
    return tuple(a.statement[:60] for a in arguments if not a.requires)
