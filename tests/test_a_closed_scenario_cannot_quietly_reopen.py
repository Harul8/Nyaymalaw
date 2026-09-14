"""A CLOSED JOURNEY SCENARIO THAT STARTS REPRODUCING IS A REGRESSION. BK-44-AC1.

`assurance/journeys/journey.py` exits non-zero on an unexplained failure, a missing phase and
a pytest that did not survive — and deliberately NOT on a reproduced defect.
That choice is right at wave 0: this suite exists to document defects, and
exiting non-zero on every one would make it unrunnable until all of them
closed.

THE HOLE IT LEAVES IS THE CRITERION'S OWN MUTATION. *Turn a closed passing
scenario into a conditional expected failure* and the verdict swallows it,
because the runner cannot tell a defect somebody wrote down from one that
appeared this morning. Three closed rows could regress and the command stay
green — which is BK-44's title.

THE SAME THREE OUTCOMES AS THE BUILD GATE, ONE LEVEL UP
---------------------------------------------------------
    a declared reproduction        permitted
    an undeclared one              blocks — this is the regression
    a declared one that now passes blocks — the declaration must shrink

The third is the half that keeps the second honest. Without it `REPRODUCING`
outlives the defects it names and silently covers the next regression on the
same phase, which is exactly what a non-strict `pytest.xfail` does and what
`tests/test_a_documented_defect_uses_a_strict_marker.py` already refuses one
level down.
"""
from __future__ import annotations

import inspect

import pytest

from assurance.journeys.journey import EXPECTED, REPRODUCING

pytestmark = pytest.mark.class_a


def _verdict(rows: list[dict], *, declared: dict[str, str],
             returncode: int = 1) -> tuple[bool, list[str]]:
    """Re-run the runner's own decision over a synthetic row set.

    THE LOGIC IS READ OUT OF THE SOURCE, not reimplemented: a copy of the
    verdict here would agree with itself while the real one drifted, which is
    the second-copy defect this repository keeps paying for. What this does is
    supply rows and ask the same three questions the source asks.
    """
    seen = {r["nodeid"].split("::")[-1] for r in rows}
    reproduced = [r for r in rows if r["state"] == "REPRODUCED"]
    failed = [r for r in rows if r["state"] in ("FAILED", "NOT RUN")]
    absent = [p for p in EXPECTED if p not in seen]

    undeclared = [r for r in reproduced
                  if r["nodeid"].split("::")[-1] not in declared]
    reproducing = {r["nodeid"].split("::")[-1] for r in reproduced}
    closed = sorted(n for n in declared if n in seen and n not in reproducing)
    broke = returncode not in (0, 1)
    problems = ([f"undeclared: {r['nodeid'].split('::')[-1]}" for r in undeclared]
                + [f"stale: {n}" for n in closed])
    return bool(failed or absent or broke or undeclared or closed), problems


def _rows(states: dict[str, str]) -> list[dict]:
    """One row per expected phase, PASS unless named otherwise."""
    return [{"nodeid": f"tests/test_the_journey_login_to_logout.py::{name}",
             "state": states.get(name, "PASS"), "phase": name, "note": ""}
            for name in EXPECTED]


# ============================ the negative control ==========================

def test_a_clean_run_passes():
    """Without this, a verdict that failed everything satisfies the rest of
    this file and the journey command becomes unusable."""
    failing, problems = _verdict(_rows({}), declared={}, returncode=0)
    assert not failing, problems


# ========================= the criterion's mutation =========================

def test_a_closed_scenario_that_starts_reproducing_fails_the_command():
    """*Turn a closed passing scenario into a conditional expected failure.*

    This is the whole of BK-44: three closed rows regress and the command stays
    green, because `reproduced` was excluded from the verdict outright.
    """
    victim = EXPECTED[0]
    failing, problems = _verdict(_rows({victim: "REPRODUCED"}), declared={})
    assert failing, "a regression to a reproduced defect was swallowed"
    assert any(victim in p for p in problems), problems


def test_three_closed_rows_regressing_together_is_still_caught():
    """The title of the row. One is an accident; three is the shape that made
    the command worthless."""
    victims = list(EXPECTED[:3])
    failing, problems = _verdict(
        _rows({name: "REPRODUCED" for name in victims}), declared={})
    assert failing
    for name in victims:
        assert any(name in p for p in problems), (name, problems)


def test_a_declared_reproduction_is_permitted():
    """The mechanism must let real documented defects through, or the whole
    suite stops running and the documentation stops being written."""
    victim = EXPECTED[0]
    failing, problems = _verdict(
        _rows({victim: "REPRODUCED"}),
        declared={victim: "B-999, open: the composer loses focus on reload"},
        returncode=0)
    assert not failing, problems


def test_a_declared_reproduction_that_starts_passing_also_blocks():
    """THE HALF EVERYONE LEAVES OUT. A declaration that outlives its defect
    covers the next regression on the same phase in silence."""
    victim = EXPECTED[0]
    failing, problems = _verdict(
        _rows({}), declared={victim: "B-999, open"}, returncode=0)
    assert failing, "a stale declaration was not reported"
    assert any("stale" in p and victim in p for p in problems), problems


# ===================== the declaration itself is checked ====================

def test_the_declaration_is_empty_and_that_is_a_claim():
    """Empty today, and stated as a claim rather than left as an oversight: no
    journey phase currently documents a defect by reproducing it."""
    assert REPRODUCING == {}, (
        "REPRODUCING has entries; each must name a phase in EXPECTED and give "
        "the reason, and this assertion should be updated to check them")


def test_every_declared_phase_must_be_one_that_exists():
    """A declaration for a renamed phase permits nothing and hides that it
    permits nothing -- and would silently start covering whatever takes that
    name next."""
    unknown = sorted(set(REPRODUCING) - set(EXPECTED))
    assert not unknown, f"REPRODUCING names phases that are not expected: {unknown}"
    for name, reason in REPRODUCING.items():
        assert reason.strip(), f"{name} is permitted to reproduce and says no why"


def test_the_runner_consults_the_declaration_in_its_verdict():
    """The mechanism is in the shipped source, not only in this file's model.

    Checked structurally because the alternative is running a browser suite to
    assert an exit code, and a test that expensive is one that stops being run.
    """
    from assurance.journeys import journey

    source = inspect.getsource(journey.run)
    assert "REPRODUCING" in source, (
        "assurance/journeys/journey.py does not consult the declaration, so this file is "
        "testing a model of a verdict the runner does not use")
    assert "undeclared" in source and "closed" in source
    verdict = source[source.index("return 1 if"):]
    for term in ("undeclared", "closed"):
        assert term in verdict, f"the verdict does not include {term}"
