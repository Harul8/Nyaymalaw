"""Quarantine. B4 and PRD §7.6, eval E-089.

*Where substance arrives before clearance: think, answer within the permitted
pre-clearance scope, and RETAIN NOTHING — quarantine it. On human clearance:
record who cleared it, when, and against what; release the quarantine EXACTLY
ONCE.*

E-089's counterexample is *substance merged onto a file no conflict check had
cleared*, and the eval has two halves: quarantined substance is unreachable
from analysis, AND it releases exactly once.

UNREACHABLE IS A PROPERTY OF THE TYPE, NOT A CONVENTION
---------------------------------------------------------
The substance is held in a private attribute and there is no accessor for it.
The ONLY way out is `release`, which requires a clearance, and a caller that
has not cleared the matter has nothing to pass. A public field with a comment
saying "do not read this before clearance" is a comment.

RELEASES EXACTLY ONCE, AND THE SECOND CALL RAISES
---------------------------------------------------
Not "returns nothing", not "is ignored". A second release is a caller that
believes it is clearing something, and telling it nothing happened would leave
that belief in place. The failure is loud because the thing it protects — a
conflict check that actually ran — is the one nobody notices the absence of.

THE SCREEN THAT TRIGGERS THIS IS SLICE 10
-------------------------------------------
The conflict screen is declared in the matrix as not built. This is the
mechanism it will use, built now because E-089 is class A and runs every
commit, and because a mechanism built alongside its consumer tends to acquire
the consumer's assumptions.

THIS MODULE DELIBERATELY DOES NOT NAME THAT GATE'S ID. `tools/trace.py` T9
fails the build when a gate declared unbuilt is consulted anywhere in `nm/`,
and it reads the source for the id -- which is right, because an id appearing
in code is indistinguishable from a consultation. Naming it here would make the
matrix say nothing evaluates the condition while something appeared to. The
screen will name it, in slice 10, when it is built.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class AlreadyReleased(Exception):
    """A second release. Raised rather than ignored -- see the module docstring."""


@refuses_blank_text()
@dataclass(frozen=True)
class Clearance:
    """WHO cleared it, WHEN, and AGAINST WHAT. All three, or it is not a
    clearance.

    B4 names the three, and `against` is the one that gets dropped: "cleared by
    Priya on Tuesday" records that somebody said yes and not what they looked
    at, which is unauditable the moment anyone asks.
    """

    by: str
    against: str
    at: datetime = field(default_factory=datetime.now)


@implements("B4")
class Quarantined:
    """Substance held out of reach until a human clears it.

    NOT a dataclass, deliberately. A frozen dataclass would put the substance
    in `__repr__`, in `asdict`, in equality, and in every log line that touched
    it -- so the thing that must be unreachable would be reachable from five
    directions nobody had thought about.
    """

    __slots__ = ("_substance", "_released", "_clearance", "held_because")

    def __init__(self, substance: str, held_because: str) -> None:
        if blank(substance):
            raise ValueError("nothing to quarantine")
        if blank(held_because):
            raise ValueError(
                "quarantine with no reason. The reason is what a human clears "
                "AGAINST, and without it the clearance has nothing to be a "
                "clearance of.")
        self._substance = substance
        self.held_because = held_because
        self._released = False
        self._clearance: Clearance | None = None

    @property
    def reachable(self) -> bool:
        """False until released. THE HALF E-089 ASKS ABOUT FIRST."""
        return self._released

    @property
    def clearance(self) -> Clearance | None:
        """Who cleared it, or `None`. Reading this does not release anything."""
        return self._clearance

    @implements("B4")
    def release(self, clearance: Clearance) -> str:
        """Hand the substance over, ONCE.

        A second call raises. It is a caller that believes it is clearing
        something, and returning nothing would leave that belief in place --
        while the thing being protected is a conflict check that actually ran,
        which is exactly the absence nobody notices.
        """
        if self._released:
            raise AlreadyReleased(
                f"this substance was already released to "
                f"{self._clearance.by if self._clearance else 'unknown'} "
                f"against {self._clearance.against if self._clearance else '?'}. "
                f"B4 requires release EXACTLY ONCE — a second release is a "
                f"second clearance nobody performed.")
        self._released = True
        self._clearance = clearance
        return self._substance

    def __repr__(self) -> str:
        """NEVER the substance. A repr is a log line waiting to happen."""
        state = "released" if self._released else "held"
        return f"<Quarantined {state}: {self.held_because[:50]!r}>"


@implements("B4")
def reachable_substance(items: tuple[Quarantined, ...]) -> tuple[str, ...]:
    """Everything analysis could currently read. E-089's first half.

    Returns what IS reachable rather than asserting that nothing is, so the
    check has something to be wrong about: a version that always returned `()`
    would satisfy an "assert nothing reachable" test identically, which is the
    B-049 shape.
    """
    return tuple(q.held_because for q in items if q.reachable)
