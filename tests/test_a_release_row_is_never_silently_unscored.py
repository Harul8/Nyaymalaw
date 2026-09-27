"""AN AUTHORED RELEASE ROW IS SCORED, OR REPORTED NOT MEASURED -- NEVER DROPPED.

THE MEASURED GAP, 27 September 2026, adding the LB-40 quality bar as release
rows RG-30 to RG-38. `releasegate.score` reported the rows it had code for and
nothing else: a threshold authored in release.yaml with no measurement behind
it did not appear in the scorecard at all, and a scorecard missing a row reads
exactly like one where every row was looked at (S1).

THE RULE: every row release.yaml authors appears in the score. A row with no
measurement is NOT MEASURED with the reason, and keeps its blocking flag, so
it fails the release exactly as the file says NOT MEASURED must. The
population is release.yaml itself, read when the test runs.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "pipeline" / "quality" / "releasegate.py"
RELEASE = ROOT / "assurance" / "specification" / "release.yaml"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("releasegate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))["scorecard"]


def test_every_authored_row_appears_in_the_score(gate):
    rows = _rows()
    assert len(rows) > 1
    score = gate.Score()
    added = gate.unscored(rows, score)
    assert [r["id"] for r in score.rows] == [r["id"] for r in rows] == added
    for row, scored in zip(rows, score.rows):
        assert scored["state"] == gate.UNMEASURED and scored["blocking"] == bool(row.get("blocking"))


def test_a_row_already_scored_is_left_as_scored(gate):
    rows = _rows()
    score = gate.Score()
    score.add(rows[0]["id"], gate.PASS, "measured", True)
    gate.unscored(rows, score)
    assert score.get(rows[0]["id"])["state"] == gate.PASS
    assert len(score.rows) == len(rows)


def test_a_planted_row_with_no_measurement_is_not_measured_and_blocks(gate):
    score = gate.Score()
    gate.unscored([{"id": "RG-PLANTED", "blocking": True}], score)
    assert score.get("RG-PLANTED")["state"] == gate.UNMEASURED
    assert score.get("RG-PLANTED")["blocking"] is True


def test_the_scorer_completes_the_scorecard_before_returning():
    """Judged on the code: `score` calls `unscored` on its rows before it returns."""
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    score = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "score")
    calls = [n for n in ast.walk(score) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "unscored"]
    assert calls, "score() no longer completes the scorecard with the rows it did not measure"
    assert isinstance(score.body[-1], ast.Return) and isinstance(score.body[-2], ast.Expr) \
        and score.body[-2].value in calls, "unscored() must run last, after every measurement"
