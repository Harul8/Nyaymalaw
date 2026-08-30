"""The golden set, checked as a SET rather than as prose.

These three evals are what S0's exit criterion actually asks for — *the golden
scenarios load and their authority reads back from the corpus* — and until
`tools/run_goldens.py` existed there was no way to run any of them, so no slice
could close. `tools/slicegate.py` reported that same blocker ten times in a row.

The structural pair are class A: no corpus, no model, every commit. The
authority check is class C, because it reads 43 provisions out of the real
corpus.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.run_goldens import (  # noqa: E402
    SUITES,
    check_authority,
    check_structure,
    expand,
    load_provisions,
    load_scenarios,
)


@pytest.fixture(scope="module")
def scenarios():
    return load_scenarios()


# ==================================================== structure (class A) ====

@pytest.mark.class_a
@pytest.mark.eval_id("E-002c")
def test_every_scenario_is_reachable_from_a_suite(scenarios):
    """A SUITE IS A FILTER OVER THE SET, NEVER A DIFFERENT SET.

    Two failures this catches, and the second is the quiet one:

      * a suite naming a scenario that does not exist — which happened, when a
        parser that knew only the first table shape saw five scenarios in a set
        of twenty-five and reported every later suite as broken;
      * a scenario reachable from no suite at all, which is how coverage rots
        while the count still says 25.
    """
    assert len(scenarios) == 25, (
        f"{len(scenarios)} scenarios parsed; the document declares 25. A "
        f"scenario the parser cannot read silently leaves the set.")
    failures = check_structure(scenarios)
    assert not failures, "\n  ".join(failures)


@pytest.mark.class_a
@pytest.mark.eval_id("E-002d")
def test_slice_n_selects_exactly_the_scenarios_runnable_by_then(scenarios):
    """`slice-N` is the suite run at a slice close, so selecting one scenario
    too many fails the close for the wrong reason — a theory scenario run
    before S8 fails because the feature is not built, which teaches nothing."""
    for n in range(1, 10):
        picked = {s.id for s in expand(f"slice-{n}", scenarios)}
        expected = {s.id for s in scenarios if s.slice <= n}
        assert picked == expected, (
            f"slice-{n}: {sorted(picked ^ expected)} differ")

    # And it is cumulative: every suite is a subset of the next.
    for n in range(1, 9):
        assert ({s.id for s in expand(f"slice-{n}", scenarios)}
                <= {s.id for s in expand(f"slice-{n + 1}", scenarios)})


@pytest.mark.class_a
def test_every_named_suite_resolves_and_is_non_empty(scenarios):
    for name in SUITES:
        picked = expand(name, scenarios)
        assert picked, f"suite {name!r} selected nothing"
        assert len({s.id for s in picked}) == len(picked), (
            f"suite {name!r} names a scenario twice")


# ==================================================== authority (class C) ====

@pytest.mark.class_c
@pytest.mark.eval_id("E-002")
def test_every_golden_provision_reads_back_from_the_corpus():
    """S0'S EXIT CRITERION.

    43 provisions across 16 Acts, each retrieved through the union lookup at a
    date the Act was in force. A scenario resting on authority that will not
    read back is a scenario that will fail for a reason having nothing to do
    with the product — which is exactly what happened in the previous build,
    where three scenarios were STRUCK for a defect that was in the lookup.

    Two harness defects were found writing this, and both would have produced
    a false result rather than a false failure:

      * checking BNSS at a 2019 date reported `not_held` for provisions the
        corpus holds — the era rule working correctly against a question that
        was wrong;
      * a fuzzy Act-name match resolved "Indian Easements Act 1882" first to
        "Indian Evidence Act, 1872" on the shared word `Indian`, then to
        "Transfer of Property Act, 1882" on the shared year. Both verified a
        DIFFERENT Act's s.15 and would have reported the golden set's
        authority as held. A verification tool certifying authority it never
        checked is the defect this product exists to refuse.
    """
    if not (ROOT / "legal_database" / "vector_store" / "chunks.db").exists():
        pytest.skip("the corpus is not attached")

    failures, ok, total = check_authority()
    assert total >= 40, f"only {total} provisions parsed from §6"
    assert not failures, (
        f"{ok}/{total} read back. Failures:\n  " + "\n  ".join(failures))


@pytest.mark.class_a
def test_the_authority_table_covers_every_act_the_scenarios_name():
    """§6 is the set's own claim about what it rests on. An empty or shrunken
    table would make the authority check vacuous while it still passed."""
    rows = load_provisions()
    assert len(rows) >= 15, f"only {len(rows)} Act groups parsed from §6"
    for act, provs in rows:
        assert provs.strip(), f"{act} lists no provisions"
