"""A BROWSER REPORT PROVES THE RUN HAPPENED, NOT THAT ITS ROWS ARE GREEN.

BK-80-AC2 (the reader) and BK-51-AC1 (the runner's reconciliation).

`bind_execution_evidence` checked two things: the report's fingerprint, and the
state of one named row. Every report below satisfies both and proves nothing —
and every one of them has rows that are entirely `PASS`:

    the run crashed at phase 3      three green rows, then nothing
    a phase was renamed away        nothing asks for it, so nothing is missing
    a row appears twice             the count says 24, the population is 23
    the tree moved mid-run          half the rows describe different code
    last week's screenshots         artifacts from a product that is not this one

THE CRITERION'S OWN MUTATION is *supply an unfinished report, duplicate a row
or omit one expected scenario while retaining a matching fingerprint* — the
last clause being the point: the fingerprint check was the only thing there,
and all three mutations keep it valid.
"""
from __future__ import annotations

import copy

import pytest

from tools.browser_evidence import SCHEMA, manifest_problems, problems, row_for

pytestmark = pytest.mark.class_a

TREE = "0123456789abcdef0123"
EXPECTED = ("phase_one", "phase_two", "phase_three")


def _report(**overrides) -> dict:
    base = {
        "schema": SCHEMA,
        "ran_at": "2026-09-11T09:00:00+00:00",
        "commit": "abc1234",
        "fingerprint": TREE,
        "finished_fingerprint": TREE,
        "argv": ["pytest"],
        "pytest_returncode": 0,
        "expected": len(EXPECTED),
        "rows": [{"nodeid": f"tests/journey.py::{name}", "state": "PASS",
                  "phase": name, "note": ""} for name in EXPECTED],
        "artifacts": {"phase_one.png": TREE},
    }
    base.update(overrides)
    return base


def _check(report, **kwargs):
    return problems(report, expected=EXPECTED, fingerprint=TREE, **kwargs)


# ============================ the negative control ==========================

def test_a_complete_run_reconciles():
    """Without this, a reader that refused everything would satisfy the whole
    file and stop every release for a reason nobody could find."""
    assert _check(_report()) == []
    assert row_for(_report(), "tests/journey.py::phase_one") == "PASS"


# ======================= the criterion's own mutations ======================

def test_an_unfinished_run_cannot_prove_the_phases_it_never_reached():
    """A crash at phase 3 leaves three green rows behind it, and a reader that
    looks only at rows sees three passes."""
    found = _check(_report(pytest_returncode=2))
    assert any("did not complete" in p for p in found), found


def test_a_duplicated_row_is_reported_rather_than_counted_twice():
    report = _report()
    report["rows"].append(copy.deepcopy(report["rows"][0]))
    found = _check(report)
    assert any("appears 2 times" in p for p in found), found


def test_a_scenario_that_produced_no_row_is_not_a_scenario_that_passed():
    """§9 on the browser surface. The omitted phase's silence is indistinguish-
    able from success unless something holds the expected population."""
    report = _report()
    report["rows"] = [r for r in report["rows"] if "phase_two" not in r["nodeid"]]
    found = _check(report)
    assert any("phase_two produced no row" in p for p in found), found


def test_all_three_mutations_keep_the_fingerprint_valid():
    """THE MEASUREMENT BEHIND THE CRITERION'S LAST CLAUSE. The fingerprint
    check was the only thing there, and it survives every one of them."""
    unfinished = _report(pytest_returncode=2)
    duplicated = _report()
    duplicated["rows"].append(copy.deepcopy(duplicated["rows"][0]))
    omitted = _report()
    omitted["rows"] = omitted["rows"][:-1]
    for mutated in (unfinished, duplicated, omitted):
        assert mutated["fingerprint"] == TREE, "the mutation moved the fingerprint"
        assert all(row["state"] == "PASS" for row in mutated["rows"])
        assert _check(mutated), "a mutation with a valid fingerprint reconciled"


# ========================== identity across the run =========================

def test_a_tree_that_moved_during_the_run_is_two_products():
    found = _check(_report(finished_fingerprint="ffffffffffffffffffff"))
    assert any("moved during the run" in p for p in found), found


def test_a_report_about_another_tree_is_stale():
    found = _check(_report(fingerprint="ffffffffffffffffffff",
                           finished_fingerprint="ffffffffffffffffffff"))
    assert any("stale" in p for p in found), found


def test_a_narrower_question_can_be_asked_without_a_tree():
    """The runner asks *is my own output complete* before printing a verdict,
    which is a different question from *is it about this tree*."""
    # THE ARTIFACTS ARE RETAGGED TOO, and the first version of this test forgot
    # to: it moved the fingerprint and left `phase_one.png` tagged with the old
    # one, so the artifact check fired and the test failed for a reason it was
    # not about. The check was right -- artifacts are anchored to the report's
    # OWN run identity, which is what makes a retained one visible.
    report = _report(fingerprint="somewhere-else",
                     finished_fingerprint="somewhere-else",
                     artifacts={"phase_one.png": "somewhere-else"})
    assert problems(report, expected=EXPECTED) == []
    assert problems(report, expected=EXPECTED, fingerprint=TREE)


# ============================== absent inputs ===============================

@pytest.mark.parametrize("report,expected", [
    (None, "absent or unreadable"),
    ({}, "unsupported schema"),
    ({"schema": 99}, "unsupported schema"),
])
def test_an_absent_report_never_reads_as_a_failed_run(report, expected):
    found = problems(report, expected=EXPECTED)
    assert any(expected in p for p in found), found


def test_an_empty_row_population_is_refused():
    found = _check(_report(rows=[]))
    assert any("empty row population" in p for p in found), found


@pytest.mark.parametrize("field", [
    "ran_at", "commit", "fingerprint", "finished_fingerprint", "artifacts",
])
def test_every_binding_field_is_required(field):
    found = _check(_report(**{field: None}))
    assert any(field in p for p in found), (field, found)


def test_a_retained_artifact_from_another_run_is_named():
    """A screenshot from last week is a picture of a product that is not this
    one, and a reader cannot tell by looking at the file."""
    found = _check(_report(artifacts={"phase_one.png": TREE,
                                      "old_failure.png": "an-earlier-run"}))
    assert any("old_failure.png" in p for p in found), found


# ===================== the manifest the runner declares =====================

def test_a_duplicated_expectation_makes_a_complete_run_report_short():
    """BK-51-AC1. `expected: len(EXPECTED)` is the declared population size, so
    a duplicate makes a perfect run look one phase short forever -- and the
    obvious fix is to relax the completeness check."""
    found = manifest_problems(("a", "b", "a"))
    assert any("names a 2 times" in p for p in found), found


def test_an_empty_manifest_would_reconcile_a_run_that_did_nothing():
    found = manifest_problems(())
    assert any("empty" in p for p in found), found


def test_the_real_manifest_is_unique_and_nonempty():
    """The population this repository actually declares, not a fixture."""
    from tools.journey import EXPECTED as REAL

    assert manifest_problems(REAL) == []
    assert len(REAL) == len(set(REAL)) >= 20


def test_the_runner_writes_what_the_reader_requires():
    """THE TWO HALVES, CHECKED AGAINST EACH OTHER. A writer that emits less
    than the reader demands produces evidence nobody can use, and the drift
    would only appear the first time a browser PASS was recorded."""
    import inspect

    from tools import journey
    from tools.browser_evidence import REQUIRED_FIELDS

    written = inspect.getsource(journey.run)
    for field in REQUIRED_FIELDS:
        assert f'"{field}"' in written, (
            f"the reader requires {field!r} and tools/journey.py never writes it")
