"""The adversarial pass, and salvage. D7 and D8.

D7 RUNS ACROSS THE WHOLE FILE, AFTER THE THREADS
--------------------------------------------------
Not as a step inside each thread, and the counterexample says why: *a file where
the client's own recovery suit undermines his defence in the cheque matter, and
NO SINGLE THREAD REVEALS IT.* A per-thread pass cannot see it however carefully
each thread is worked, because the exposure exists only in the pair.

EXACTLY ONCE, EMPTY OR NOT
----------------------------
E-082 is precise: cross-thread exposure is produced *exactly once on every
multi-thread file, empty or not*, and its counterexample is *emitted twice, or
silently omitted*. Both halves are defects and they fail in opposite
directions — twice is noise the advocate learns to skip, and omitted reads as
"nothing found" when nobody looked.

So `ExposureReport` has three states and one of them is NOT_RUN. An empty
report and an absent one are different facts and this type refuses to let them
render alike.

D8: ALMOST EVERY "YOU LOSE" IS ONE COORDINATE FAILING
-------------------------------------------------------
*Treat a claim as a set of coordinates — party, cause, relief, forum, timing,
procedure, burden — and ask which coordinate can move.* The measured original
error was advice that a claim was dead where a different framing on the same
facts was available.

Hence `failure_scope`: **we lose** and **we lose on this framing** are different
answers, and the overwhelming majority of weak-case reports are the second.

AND THE BOUND, WHICH IS THE HARDER HALF
-----------------------------------------
*Never manufacture a route. A system rewarded for always finding a way out will
invent one, and a hopeless alternative cause costs the client money and the
advocate credibility.*

So `route=None` is a first-class outcome: a coordinate can be varied, the result
stated, and no route found. What the type refuses is the OPPOSITE — a route
with no strength and no citation, which is how a manufactured one arrives.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import ThreadId
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements

# ============================================================ D7 ==========


@refuses_blank_text("no_answer_because")
@dataclass(frozen=True)
class Attack:
    """The case the other side will run, on the grounds they will run it."""

    thread: ThreadId
    ground: str
    their_case: str
    our_answer: str = ""
    no_answer: bool = False
    no_answer_because: str = ""
    """What we DO about it, where there is no good answer.

    D7: *where an attack has no good answer, say so plainly and resolve it into
    what we do about it.* An unanswerable attack reported and left there is
    half a finding."""

    def __post_init__(self) -> None:
        if not self.no_answer and blank(self.our_answer):
            raise ValueError(
                f"the attack on {self.ground!r} carries no answer and does not "
                f"say it has none. Those are different findings: one is work "
                f"not done, the other is a fact about the case.")
        if self.no_answer and blank(self.no_answer_because):
            raise ValueError(
                f"the attack on {self.ground!r} is marked unanswerable and "
                f"stops there. D7 requires it resolved into what we do about "
                f"it — a problem stated and abandoned is half a finding.")


@refuses_blank_text()
@dataclass(frozen=True)
class Exposure:
    """Something on one thread that damages another."""

    from_thread: ThreadId
    to_thread: ThreadId
    what: str
    consequence: str

    def __post_init__(self) -> None:
        if self.from_thread == self.to_thread:
            raise ValueError(
                "cross-thread exposure between a thread and itself is a "
                "per-thread finding wearing the wrong name, and it would make "
                "the file-level pass look like it had found something.")


class ExposureState(str, Enum):
    FOUND = "found"
    NONE_FOUND = "none_found"
    """Looked, and there is none. AN ANSWER, and D7 requires it expressly."""
    NOT_RUN = "not_run"
    """Nobody looked. The state E-082's 'silently omitted' half produces."""


@dataclass(frozen=True)
class ExposureReport:
    """Produced EXACTLY ONCE per file. Empty is not absent."""

    state: ExposureState
    exposures: tuple[Exposure, ...] = ()
    not_run_because: str = ""

    def __post_init__(self) -> None:
        if self.state is ExposureState.FOUND and not self.exposures:
            raise ValueError(
                "an exposure report claiming findings and carrying none. "
                "NONE_FOUND is the state for 'we looked and there is nothing'.")
        if self.state is ExposureState.NONE_FOUND and self.exposures:
            raise ValueError("NONE_FOUND with exposures in it")
        if self.state is ExposureState.NOT_RUN and blank(self.not_run_because):
            raise ValueError(
                "a pass that did not run must say why. Without it, NOT_RUN and "
                "NONE_FOUND are the same sentence to the advocate, and they are "
                "opposite facts.")


@implements("D7")
def cross_thread(threads: tuple[ThreadId, ...],
                 found: tuple[Exposure, ...] | None) -> ExposureReport:
    """E-082. One report per file, whatever the answer.

    `found is None` means the pass did not run and produces NOT_RUN with the
    reason — never an empty FOUND, and never silence.

    A SINGLE-THREAD FILE STILL GETS A REPORT. It says NONE_FOUND, because there
    is no pair for an exposure to exist in, and that is a finding rather than a
    reason to skip the section. A section that appears only sometimes is one
    the advocate cannot rely on being there.
    """
    if found is None:
        return ExposureReport(
            ExposureState.NOT_RUN,
            not_run_because="the cross-file pass did not run on this turn")
    if len(threads) < 2:
        return ExposureReport(ExposureState.NONE_FOUND)
    real = tuple(e for e in found
                 if e.from_thread in threads and e.to_thread in threads)
    return (ExposureReport(ExposureState.FOUND, real) if real
            else ExposureReport(ExposureState.NONE_FOUND))


@implements("D7")
def unanswered(attacks: tuple[Attack, ...]) -> tuple[str, ...]:
    """E-083. Attacks with no answer and no express statement that there is none.

    Should be empty, because `Attack` refuses one at construction. Computed
    anyway: a type guard says nothing about objects decoded from an older
    store, and this is the check a recommendation is measured against.
    """
    return tuple(a.ground for a in attacks
                 if not a.no_answer and blank(a.our_answer))


# ============================================================ D8 ==========


class Coordinate(str, Enum):
    """D8's seven. *Almost every "you lose" is the failure of one of them.*"""

    PARTY = "party"
    CAUSE = "cause"
    RELIEF = "relief"
    FORUM = "forum"
    TIMING = "timing"
    PROCEDURE = "procedure"
    BURDEN = "burden"


class Strength(str, Enum):
    """*Never present a route NM would not itself run as though it would.*"""

    WOULD_RUN = "would_run"
    ARGUABLE = "arguable"
    WOULD_NOT_RUN = "would_not_run"
    NOT_ASSESSED = "not_assessed"


class FailureScope(str, Enum):
    """*Distinguish "we lose" from "we lose on this framing".*"""

    CASE = "case"
    FRAMING = "framing"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text("route")
@dataclass(frozen=True)
class Salvage:
    """One coordinate, varied. D8's PRODUCES."""

    coordinate: Coordinate
    varied_result: str
    """What changes when this dimension moves. REQUIRED whether or not a route
    was found -- D8 says state it BEFORE reporting that the claim fails."""
    route: str = ""
    strength: Strength = Strength.NOT_ASSESSED
    findings: tuple[str, ...] = ()
    """The retrieved provisions or authorities the route rests on."""

    def __post_init__(self) -> None:
        if self.route and self.strength is Strength.NOT_ASSESSED:
            raise ValueError(
                f"the route on {self.coordinate.value} carries no strength. "
                f"D8: never present a route NM would not itself run as though "
                f"it would — an unmarked route reads as a recommendation.")
        if self.route and not self.findings:
            raise ValueError(
                f"the route on {self.coordinate.value} rests on nothing "
                f"retrieved: {self.route[:60]!r}. D8 forbids grounding a route "
                f"on a plausible recollection that such a claim exists, and a "
                f"route with no citation is exactly a category-level "
                f"suggestion — 'consider a different forum' with no forum "
                f"named.")


@implements("D8")
def unvaried(considered: tuple[Salvage, ...]) -> tuple[str, ...]:
    """Coordinates nobody moved.

    THE POPULATION IS THE SEVEN, not what was tried. D8 requires the variation
    stated BEFORE reporting failure, so a report that varied two coordinates
    and concluded the case is dead has not done the work — and the two it did
    vary would make it look as though it had.
    """
    done = {s.coordinate for s in considered}
    return tuple(c.value for c in Coordinate if c not in done)
