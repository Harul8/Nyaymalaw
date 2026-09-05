"""THE READS. Every structured model call the product makes, and what it costs
to get one wrong.

WHY THIS TABLE EXISTS
----------------------
Eleven reads were added across ten slices, each with its own schema, its own
guards and its own tests. Nothing anywhere said which of them CHANGE A NUMBER
THE ADVOCATE ACTS ON and which enrich an answer — so all eleven ran on the
cheap tier, including the one that decides what a limitation period runs from.

Measured on GS-15 (B-088): the correction read fired on one run and returned
nothing on the next, on identical input. The scenario reported a claim as
expired in 1987 for an agreement dated 2024, and every citation on the turn was
verbatim and correct.

DECISIVE IS NOT "IMPORTANT"
-----------------------------
It is a narrow test and the narrowness is the point: does the read's output
change a DATE, an AMOUNT, or WHICH LAW IS READ? If it does, being wrong is not
a worse answer — it is a right-looking answer about something else, and no
downstream check can catch it because everything downstream is derived from it.

The issue read is not decisive and it matters enormously; a missed issue makes
the answer thinner, and the advocate can see it is thinner. A missed correction
makes the answer confident and wrong about the one number they will act on.

WHAT ESCALATION IS AND IS NOT
-------------------------------
PRD §7.4.1: a step moves to `hard` only with a recorded measurement showing the
quality it bought. B-088 is that measurement for the decisive reads. It is not
a measurement for the rest, and they stay where they are.

AND WHEN `hard` IS NOT CONFIGURED, THE DEGRADATION IS SAID OUT LOUD. A decisive
read that quietly falls back to the cheap tier is the same defect as a screen
that could not run returning a clean result — the answer looks identical and is
worth less.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.text import refuses_blank_text


@refuses_blank_text()
@dataclass(frozen=True)
class Read:
    """One structured model call, and whether being wrong changes a number."""

    key: str
    """The schema's `x-nm-read` value. THE EXACT KEY the adapter dispatches on."""

    decisive: bool
    why: str
    """Why it is decisive, or why it is not. Both are worth writing down: the
    second is what stops the list growing until every read is decisive and the
    distinction stops meaning anything."""


#: EVERY read the product makes. `tests/test_reads_registry.py` fails the build
#: on a schema in `nm/` that is not here, so a twelfth read cannot be added
#: without someone deciding which kind it is.
READS: tuple[Read, ...] = (
    # ---- decisive: the output IS a date, an amount, or which law is read ----
    Read("dates", True,
         "Every date on the chronology comes from here, and the accrual is one "
         "of them. A missed or misread date moves the limitation period and "
         "every deadline derived from it."),
    Read("correction", True,
         "It decides which of two contradictory facts the arithmetic reads. "
         "B-088: it returned nothing on one run and the answer computed from a "
         "date the advocate had withdrawn — correctly, from the wrong fact."),
    Read("cause", True,
         "It decides WHICH ACT is looked up. CLAUDE.md §5 measures what a wrong "
         "one costs: an exact section lookup sent into the wrong statute, "
         "returning a confident period that governs a different suit."),
    Read("factors", True,
         "An acknowledgment under s.18 restarts the period. Missing it reports "
         "a live claim as dead (B-073); inventing one reports a dead claim as "
         "live."),
    Read("posture", True,
         "Which side we are on. Nothing side-dependent can be computed without "
         "it, and a wrong one advises the opponent's case."),
    Read("role", True,
         "The procedural role, which resolves the posture. Same consequence, "
         "one step earlier."),

    # ---- not decisive: being wrong makes the answer thinner, not false ------
    Read("dispute", False,
         "Whether a message opens a new thread. Wrong, it puts the right "
         "analysis on the wrong thread — visible to the advocate immediately, "
         "and correctable in a sentence."),
    Read("issues", False,
         "A missed issue makes the answer thinner and the advocate can SEE it "
         "is thinner. It changes no number."),
    Read("inventory", False,
         "What evidence is mentioned and who holds it. A missed item costs a "
         "preservation question; it moves no date."),
    Read("adverse", False,
         "Which facts hurt us. Feeds the theory's completeness check, which "
         "reports what is unaccounted rather than computing anything."),
    Read("theory", False,
         "The spine. Wrong, it is an argument the advocate rejects — which is "
         "the ordinary way an advocate uses a draft."),
    Read("attacks", False,
         "The opponent's case. A weak one is a preparation gap, not a false "
         "statement about the file."),
    Read("exposure", False,
         "Cross-thread contradiction. Reports a relationship; computes nothing."),
    Read("salvage", False,
         "Coordinate variation. Its routes are already bound to retrieved "
         "citations by the type, so the read cannot manufacture one."),
)

BY_KEY: dict[str, Read] = {r.key: r for r in READS}

#: A FUNCTION WRITTEN FOR FUTURE USE IS FUTURE USE. `decisive_keys()` and
#: `is_decisive()` were both here and neither had a caller — M2 caught them
#: within the hour. They belong with the tier escalation that will call them,
#: not ahead of it, so what this module offers today is the TABLE: a place
#: where a twelfth read cannot be added without someone deciding which kind
#: it is.
