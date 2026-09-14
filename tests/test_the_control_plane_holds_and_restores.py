"""THE CONTROL PLANE, PROVED RATHER THAN ASSUMED. BK-44-AC1, BK-60-AC6. P42.

WHAT THIS PACKET IS AND IS NOT
--------------------------------
P42 is a VERIFICATION packet over twenty-eight criteria, and twenty-six of them
already carry passing evidence produced by suites that are not touched here.
Rewriting a working control for uniformity is how a working control stops
working, so nothing in this file replaces one.

Two criteria carried no evidence, and in both cases the MECHANISM already
existed while nothing could exercise it:

    BK-44-AC1  `tools/journey.py` already refuses an undeclared reproduction
               and a declaration that has outlived its defect. The decision
               sat inside `run()` between a pytest subprocess and a print, so
               the only way to exercise it was to break a browser suite on
               purpose. A control nobody can test is a control nobody has
               tested.

    BK-60-AC6  `tools/backlog.py` already declares `CONTRACT_FIELDS` and the
               lint already reads them. Nothing planted a step with half a
               contract and required the refusal.

AND ONE DEFECT THE FRESH WORKTREE FOUND, which is the reason a packet like
this exists at all: three criteria bound their browser evidence to
`.nm/journey/report.json` -- a GITIGNORED runtime path. On the machine that
last ran the journey they resolve; in any fresh checkout the lint reports the
report as absent. Evidence that exists on one machine is not evidence.
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from tools.backlog import CONTRACT_FIELDS
from tools.journey import EXPECTED, REPRODUCING, regressions

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _row(name: str, state: str = "PASS", note: str = "") -> dict:
    return {"nodeid": f"tests/test_the_journey_login_to_logout.py::{name}",
            "state": state, "phase": name.replace("_", " "), "note": note}


# ============ 1. BK-44-AC1 -- a regression cannot pass as a defect ==========

def test_a_clean_run_is_clean():
    """THE POSITIVE CONTROL. A verdict that refused every run would be
    switched off, and the three refusals below would go with it."""
    verdict = regressions([_row("test_one"), _row("test_two")],
                          expected=("test_one", "test_two"), declared={})
    assert verdict.clean is True
    assert verdict.undeclared == () and verdict.closed == ()


def test_a_closed_scenario_that_starts_reproducing_is_a_regression():
    """BK-44-AC1'S NEGATIVE CONTROL: *turn a closed passing scenario into a
    conditional expected failure* -> *the journey verdict rejects the
    regression*.

    This is the case the runner could not previously tell apart: a phase
    reporting REPRODUCED looks identical whether somebody wrote the defect
    down or it just came back.
    """
    verdict = regressions([_row("test_one", "REPRODUCED", "BK-32 again")],
                          expected=("test_one",), declared={})
    assert verdict.clean is False
    assert [r["nodeid"] for r in verdict.undeclared] == [
        "tests/test_the_journey_login_to_logout.py::test_one"]


def test_a_declared_reproduction_is_permitted():
    """A wave-0 suite that exited non-zero on every documented defect is a
    command nobody runs, which is the reason the allow-list exists at all."""
    verdict = regressions([_row("test_one", "REPRODUCED")],
                          expected=("test_one",),
                          declared={"test_one": "BK-99: documented, open"})
    assert verdict.undeclared == ()
    assert verdict.clean is True


def test_a_declaration_that_outlived_its_defect_blocks():
    """A declaration left standing after the phase starts passing covers the
    next regression on that phase silently -- the same third outcome the build
    gate keeps."""
    verdict = regressions([_row("test_one", "PASS")],
                          expected=("test_one",),
                          declared={"test_one": "BK-99: documented, open"})
    assert verdict.closed == ("test_one",)
    assert verdict.clean is False


def test_a_declaration_for_a_phase_that_did_not_run_is_not_stale():
    """It cannot be known to have started passing if it did not report. The
    absent check owns that case, and reporting it twice would send whoever
    reads it to remove a declaration for a phase nobody ran."""
    verdict = regressions([], expected=("test_one",),
                          declared={"test_one": "BK-99: documented, open"})
    assert verdict.closed == ()
    assert verdict.absent == ("test_one",)
    assert verdict.clean is False


def test_a_declared_phase_that_produced_no_row_is_not_a_pass():
    verdict = regressions([_row("test_one")],
                          expected=("test_one", "test_two"), declared={})
    assert verdict.absent == ("test_two",)
    assert verdict.clean is False


def test_a_phase_nobody_declared_is_reported_rather_than_counted():
    """An unexpected row is a phase the manifest does not know about, and
    counting it as a pass is how the manifest stops being the population."""
    verdict = regressions([_row("test_one"), _row("test_surprise")],
                          expected=("test_one",), declared={})
    assert verdict.unexpected == ("test_surprise",)
    assert verdict.clean is False


@pytest.mark.parametrize("state", ["FAILED", "NOT RUN"])
def test_a_failure_and_a_phase_that_could_not_run_are_both_unexplained(state):
    """NOT RUN IS NOT A PASS. A browser that never started produces no rows
    and no failures, which is the shape that reads greenest."""
    verdict = regressions([_row("test_one", state)],
                          expected=("test_one",), declared={})
    assert verdict.failed and verdict.clean is False


def test_the_declaration_is_keyed_on_the_test_function_name():
    """Keying it on the human-readable label was tried: no declaration could
    ever match, so every reproduction read as undeclared -- a permission that
    can never be granted."""
    verdict = regressions([_row("test_one", "REPRODUCED")],
                          expected=("test_one",),
                          declared={"one": "the readable label, not the name"})
    assert verdict.undeclared, "a label-keyed declaration must not match"


def test_the_live_allow_list_is_empty_and_the_manifest_is_not():
    """THE POPULATION THIS RUNS AGAINST, asserted so the tests above are not
    proving something about a fixture alone."""
    assert REPRODUCING == {}, sorted(REPRODUCING)
    assert len(EXPECTED) > 40
    assert len(set(EXPECTED)) == len(EXPECTED), "a duplicated phase"


def test_the_runner_reads_the_verdict_rather_than_deciding_again():
    """STRUCTURAL. The extraction is worth nothing if `run()` kept its own
    copy: two answers to "was this a regression" is exactly the second owner
    this build refuses."""
    import inspect

    from tools import journey

    source = inspect.getsource(journey.run)
    assert "regressions(rows" in source
    for recomputed in ('r["state"] == "REPRODUCED"',
                       'not in REPRODUCING',
                       'sorted(seen - set(EXPECTED))'):
        assert recomputed not in source, recomputed


# ============ 2. BK-60-AC6 -- a step states do, refuse and recover =========

def _steps() -> list[dict]:
    loaded = yaml.safe_load((ROOT / "docs" / "backlog" / "steps.yaml")
                            .read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, list) else loaded["steps"]


def test_every_journey_step_states_what_it_does_refuses_and_recovers():
    """BK-60-AC6, over the whole registry rather than a sample."""
    rows = _steps()
    assert len(rows) == 47, len(rows)
    thin = []
    for step in rows:
        for field in ("expected_visible_result", "failure_behaviour",
                      "recovery_behaviour"):
            value = step.get(field)
            if not value or not all(str(v).strip() for v in value):
                thin.append(f"{step['id']}: {field}")
    assert not thin, (
        "these steps do not say what they must do, refuse or recover from, "
        "and a step that says only what it does is a heading: " + "; ".join(thin))


def test_the_contract_is_all_eight_fields_and_they_are_declared_once():
    """The lint reads `CONTRACT_FIELDS`; this asserts the three the criterion
    names are in it rather than keeping a second list beside it."""
    for field in ("expected_visible_result", "failure_behaviour",
                  "recovery_behaviour"):
        assert field in CONTRACT_FIELDS, field
    assert len(CONTRACT_FIELDS) == 8


def test_the_lint_refuses_a_step_given_half_a_contract(tmp_path):
    """BK-60-AC6'S NEGATIVE CONTROL: *give a step half a contract* -> *lint
    refuses it; a partial contract is not a contract*.

    THE MUTATION IS ASSERTED TO HAVE LANDED before the refusal is required.
    A probe that silently edited nothing would report the check working on a
    file it never changed.
    """
    from tools import backlog

    rows = _steps()
    original = json.dumps(rows[0], sort_keys=True)
    maimed = json.loads(original)
    maimed.pop("recovery_behaviour")
    assert json.dumps(maimed, sort_keys=True) != original, (
        "the mutation changed nothing, so the refusal below would prove "
        "nothing")

    # THE REAL LINT FUNCTION, driven with the real registry's items and
    # features so the only thing wrong with this run is the maimed step.
    doc = yaml.safe_load((ROOT / "docs" / "backlog" / "status.yaml")
                         .read_text(encoding="utf-8"))
    items = {i["id"] for i in doc["items"]}
    features = {f["id"]: f for f in doc["features"]}

    whole = backlog._steps({"steps": [json.loads(original)]}, items, features)
    assert not [p for p in whole if "partial contract" in p], (
        "the unmutated step is already reported, so the refusal below would "
        "not be about the mutation")

    problems = backlog._steps({"steps": [maimed]}, items, features)
    assert any("a partial contract is not a contract" in p
               and "recovery_behaviour" in p for p in problems), problems


# ===== 3. evidence must resolve in a fresh checkout, not on one machine ====

IGNORED_EVIDENCE_ROOTS = (".nm/", ".nm-artefacts/", "outputs/")


def test_no_evidence_ref_points_at_a_path_a_fresh_checkout_does_not_have():
    """FOUND BY CHECKING OUT A FRESH WORKTREE, which is the only way it shows.

    Three criteria bound their browser evidence to `.nm/journey/report.json`.
    On the machine that last ran the journey they resolve; anywhere else the
    lint reports the report absent -- and "absent" is not "failed", so the
    rows read as unproven rather than as wrong, which is worse than either.

    THE POPULATION IS EVERY REF, not the three that were found: a fourth
    written next month into `outputs/` fails here the day it is written.
    """
    doc = yaml.safe_load((ROOT / "docs" / "backlog" / "status.yaml")
                         .read_text(encoding="utf-8"))
    stranded = []
    for item in doc["items"]:
        for ac in item.get("acceptance") or ():
            for kind, row in (ac.get("evidence") or {}).items():
                ref = str(row.get("ref") or "")
                path = ref.split("#", 1)[0]
                if path.startswith(IGNORED_EVIDENCE_ROOTS):
                    stranded.append(f"{ac['id']}/{kind}: {ref}")
    assert not stranded, (
        "these evidence rows name a path that is not in the repository, so "
        "they resolve only on the machine that last produced it:\n  "
        + "\n  ".join(stranded))


def test_every_committed_evidence_path_exists():
    """The other half. A ref into the repository that names nothing is the
    same defect wearing a tracked path."""
    doc = yaml.safe_load((ROOT / "docs" / "backlog" / "status.yaml")
                         .read_text(encoding="utf-8"))
    missing = []
    for item in doc["items"]:
        for ac in item.get("acceptance") or ():
            for kind, row in (ac.get("evidence") or {}).items():
                ref = str(row.get("ref") or "")
                path = ref.split("#", 1)[0]
                if not path.endswith(".json"):
                    continue
                if not (ROOT / path).exists():
                    missing.append(f"{ac['id']}/{kind}: {path}")
    assert not missing, (
        "these evidence rows name a file that is not there:\n  "
        + "\n  ".join(missing))


def test_the_stranded_ref_check_can_see_a_planted_one():
    """A POSITIVE CONTROL. The check above passes trivially once the three are
    fixed, and would go on passing if the prefix tuple were emptied."""
    planted = ".nm/journey/report.json#tests/x.py::test_y"
    assert planted.split("#", 1)[0].startswith(IGNORED_EVIDENCE_ROOTS)
    assert not "docs/backlog/evidence/x.json".startswith(IGNORED_EVIDENCE_ROOTS)
