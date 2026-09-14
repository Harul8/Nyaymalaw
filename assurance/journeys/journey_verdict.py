"""WAS THIS RUN A PASS? One decision, over the rows. BK-44-AC1. P42.

    from assurance.journeys.journey_verdict import regressions

WHY THIS IS ITS OWN MODULE
----------------------------
Two reasons, and the second is the one that decided it.

FIRST, the decision needs to be provable without a browser. It sat inside
`journey.run()` between a pytest subprocess and a print, so the only way to
exercise "a closed scenario that starts reproducing must fail the command" was
to break a browser suite on purpose -- which is why BK-44-AC1 carried no
evidence at all. A control nobody can test is a control nobody has tested.

SECOND, IT CANNOT LIVE IN `assurance/journeys/journey.py`. That file is loaded standalone by
`tests/test_tooling_bites.py::test_the_journey_manifest_matches_what_the_suite_
collects`, through `spec_from_file_location` without registering the module in
`sys.modules`. A `@dataclass` there raises `AttributeError` inside
`dataclasses._is_type`, which looks the module up by name and finds nothing.
Moving the record here keeps that check working untouched -- the alternative
was editing a working control to accommodate a new one, which is the wrong way
round.

NOTHING ABOUT WHICH RUNS FAIL CHANGES. The four outcomes, and the reasons each
exists, are carried over exactly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    """WHAT THE ROWS SAY ABOUT THE RUN, decided in one place. BK-44-AC1.

    Four ways a journey run is not a pass, and they are separate because the
    next step differs for each:

        `failed`      a phase said so.
        `absent`      a declared phase produced no row. A question nobody
                      asked is not a question answered.
        `undeclared`  a phase reproduced a defect nobody wrote down. THIS IS
                      THE REGRESSION CASE: a closed scenario that starts
                      reproducing looks exactly like a documented one.
        `closed`      a declaration outlived its defect. Left standing, it
                      covers the next regression on the same phase silently.
    """

    rows: tuple[dict, ...]
    seen: frozenset[str]
    failed: tuple[dict, ...]
    reproduced: tuple[dict, ...]
    absent: tuple[str, ...]
    undeclared: tuple[dict, ...]
    closed: tuple[str, ...]
    unexpected: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """Whether the ROWS are a pass. The command also weighs pytest's own
        return code and the report's own integrity, which are not facts about
        the rows and are not decided here."""
        return not (self.failed or self.absent or self.undeclared
                    or self.closed or self.unexpected)


def regressions(rows, *, expected, declared) -> Verdict:
    """Read a run's rows against the declared manifest and allow-list.

    A PURE FUNCTION OVER ROWS, so the decision can be exercised without a
    browser. It was inline in `run()` between a pytest subprocess and a print,
    which is why BK-44-AC1 had no evidence: the only way to test "a closed
    scenario that starts reproducing must fail the command" was to break a
    browser suite on purpose.

    `declared` is keyed on the TEST FUNCTION NAME, which is what `expected`
    and the rows hold. Keying it on the human-readable label was tried and no
    declaration could ever match -- a permission that can never be granted.
    """
    rows = tuple(rows)
    seen = frozenset(r["nodeid"].split("::")[-1] for r in rows)
    reproduced = tuple(r for r in rows if r["state"] == "REPRODUCED")
    reproducing = {r["nodeid"].split("::")[-1] for r in reproduced}
    return Verdict(
        rows=rows,
        seen=seen,
        failed=tuple(r for r in rows if r["state"] in ("FAILED", "NOT RUN")),
        reproduced=reproduced,
        absent=tuple(p for p in expected if p not in seen),
        undeclared=tuple(r for r in reproduced
                         if r["nodeid"].split("::")[-1] not in declared),
        closed=tuple(sorted(name for name in declared
                            if name in seen and name not in reproducing)),
        unexpected=tuple(sorted(seen - set(expected))),
    )
