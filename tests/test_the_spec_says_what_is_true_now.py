"""THE GENERATED SPEC STATES PRESENT TRUTH, AND ITS IDENTITY COVERS THE PROMISE.

BK-80-AC3, BK-80-AC5, BK-48-AC1, BK-48-AC2.

WHAT WAS WRONG, MEASURED 10 SEPTEMBER 2026
--------------------------------------------
`tools/export_spec.py` read each feature's status out of the Feature Map sheet
of `docs/Nyaymalaw_Project_Plan.xlsx` -- the August vertical-slice plan.
Eighteen features exported as `tested`. Not one of them had a delivering row at
`implementation: complete` with currently passing evidence; A1 exported as
`tested` while its own rows were `in_progress` and every criterion reachable
from it read `NOT_RUN`.

And `verification_fingerprint` covered `nm`, `tests`, `tools`, `web` and the
plan contracts -- not the PRD, not the generated specification, not the release
thresholds, not the playbooks. So a promise could change and every recorded
PASS still read as current.

THE TWO HALVES ARE OPPOSITE AND BOTH ARE TESTED HERE
------------------------------------------------------
    a promise changes  -> the fingerprint MOVES and prior proof goes stale
    a verdict changes  -> the fingerprint HOLDS

The second is not a relaxation. Folding a verdict into the identity of the
thing it judges makes recording evidence invalidate that same evidence, so the
check could never be satisfied by anything -- and a check nothing can satisfy
gets switched off, which is how this repository lost `pytest.xfail` strictness
and its `derive_done` sign-off.
"""
from __future__ import annotations

import pathlib
import shutil
import tempfile
from collections.abc import Callable, Iterator

import pytest
import yaml

from tools import evidence as ev
from tools.export_spec import ExportRefused, build, publish
from tools.feature_state import project, reconcile

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEATURES = ROOT / "spec" / "features.yaml"
STATUS = ROOT / "docs" / "backlog" / "status.yaml"
STEPS = ROOT / "docs" / "backlog" / "steps.yaml"

#: Copied rather than pointed at. A fingerprint test that edited the real tree
#: would leave every other test in the session measuring a mutated repository,
#: and the failure would surface somewhere else entirely.
_SKIP = shutil.ignore_patterns(
    "legal_database", ".git", "node_modules", "__pycache__", "outputs",
    ".nm", ".code-review-graph", "*.xlsx", ".venv", "venv")


@pytest.fixture
def tree() -> Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as td:
        copy = pathlib.Path(td) / "tree"
        shutil.copytree(ROOT, copy, symlinks=True, ignore=_SKIP)
        yield copy


def _features(path: pathlib.Path = FEATURES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf8"))["features"]


def _rewrite(root: pathlib.Path, mutate: Callable[[dict], None]) -> None:
    path = root / "spec" / "features.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf8"))
    mutate(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                    encoding="utf8")


# =================== the workbook is history, not present state ==============

def test_no_feature_carries_a_tested_label_it_did_not_currently_earn():
    """BK-80-AC5. THE FINDING THIS WHOLE PACKET EXISTS FOR.

    `tested` is derivable only from a delivering row at `implementation:
    complete` whose acceptance evidence is currently PASSING. Eighteen features
    claimed it from a spreadsheet cell.
    """
    for f in _features():
        if f["status"] != "tested":
            continue
        assert f["implementation"] == "complete" and f["proof"] == "PASS", (
            f"{f['id']} exports as tested with implementation="
            f"{f['implementation']!r} proof={f['proof']!r}")


def test_the_historical_verdict_survives_and_cannot_be_read_as_current():
    """Losing the plan of record would lose the slice frontier. Keeping it
    under the same key would keep every existing call site's old meaning while
    the value underneath changed, which is worse than either."""
    rows = _features()
    assert any(f["historical_status"] == "tested" for f in rows), (
        "the August plan of record has been dropped, not renamed")
    for f in rows:
        assert "slice" not in f and "eval_ids" not in f, (
            f"{f['id']} still carries an unqualified {sorted(set(f) & {'slice', 'eval_ids'})}"
            f" -- a consumer reading it cannot tell which plan it belongs to")
        assert "historical_slice" in f and "historical_eval_ids" in f


def test_a_currently_reopened_feature_is_not_overwritten_by_a_tested_history():
    """The packet's own negative control: historical `tested` must not restore
    a feature the current registry has reopened."""
    rows = {f["id"]: f for f in _features()}
    reopened = [f for f in rows.values()
                if f["historical_status"] == "tested" and f["status"] != "tested"]
    assert reopened, (
        "nothing in the spec exercises this today, so the check proves "
        "nothing -- it needs a feature whose history and present disagree")
    for f in reopened:
        assert f["status"] in ("decided", "built")


# ========================= where the answer came from ========================

def test_every_feature_says_which_source_answered_for_it():
    """A registry answer and a decorator answer are different facts. Collapsing
    them into one word is the three-stores defect in a fourth place."""
    for f in _features():
        basis, rows = f["implementation_basis"], f["delivered_by"]
        assert basis in ("registry", "trace", "contradicted", "absent")
        if basis == "registry":
            assert rows, f"{f['id']} claims a registry basis with no delivering row"
        if basis == "trace":
            assert not rows, (
                f"{f['id']} has a delivering row and reports a trace basis -- "
                f"a row that says `none` while code claims the feature is a "
                f"contradiction, and saying `trace` would hide which it is")
        if basis == "contradicted":
            assert rows, f"{f['id']} contradicts a row it does not have"
        if basis == "absent":
            assert not rows and f["implementation"] == "not_recorded"


def test_a_decorator_alone_can_reach_built_and_never_tested():
    """BK-48-AC1, stated as a rule rather than as today's counts."""
    ids = [f["id"] for f in _features()]
    state = project(ids)
    by_trace = [s for s in state.values() if s.implementation_basis == "trace"]
    assert by_trace, "no feature rests on the trace basis, so this proves nothing"
    for s in by_trace:
        assert s.status == "built", (
            f"{s.feature} reached {s.status!r} on a decorator alone")


def test_the_registry_and_the_code_are_reconciled_in_both_directions():
    """BK-48-AC2. `recorded_only_in_code` is the direction T3 cannot look."""
    ids = [f["id"] for f in _features()]
    state = project(ids)
    unrecorded = {f for f, s in state.items() if s.recorded_only_in_code}
    declared = {f["id"] for f in _features()
                if f["implementation_basis"] in ("trace", "contradicted")}
    assert unrecorded == declared, (
        "the exported spec and the projection disagree about which features "
        "the registry does not record")


# ============================ what the export refuses ========================

@pytest.mark.parametrize("mutation,expected", [
    ("unknown_step_feature", "is not a PRD feature"),
    ("unknown_delivers", "which is not a PRD feature"),
    ("duplicate_feature", "is defined 2 times"),
    ("unreached_feature", "no journey step reaches"),
])
def test_reconcile_refuses_a_population_that_does_not_line_up(mutation, expected):
    """Compared over all 44 features rather than a sample, because the failure
    shape is not a wrong value -- it is a row that silently is not there."""
    ids = [f["id"] for f in _features()]
    steps = yaml.safe_load(STEPS.read_text(encoding="utf8"))["steps"]
    items = yaml.safe_load(STATUS.read_text(encoding="utf8"))["items"]

    assert reconcile(ids, steps, items) == [], "the real sources already disagree"

    if mutation == "unknown_step_feature":
        steps = [*steps, {"id": "STEP-X", "features": ["ZZ9"], "items": []}]
    elif mutation == "unknown_delivers":
        items = [*items, {"id": "BK-999", "delivers": ["ZZ9"]}]
    elif mutation == "duplicate_feature":
        ids = [*ids, ids[0]]
    elif mutation == "unreached_feature":
        ids = [*ids, "ZZ9"]
        items = [*items, {"id": "BK-999", "delivers": ["ZZ9"]}]

    problems = reconcile(ids, steps, items)
    assert any(expected in p for p in problems), problems


def test_a_refused_export_writes_nothing_at_all(tree, monkeypatch):
    """TRANSACTIONAL, AND PROVEN ON THE BYTES.

    Five generated files describe one state. Publishing three and failing on
    the fourth leaves a spec that is internally inconsistent in a way that
    reads as ordinary generator drift -- so T1 would send the reader to the
    generator rather than to the failure.
    """
    targets = sorted((tree / "spec").glob("*.yaml"))
    before = {p: p.read_bytes() for p in targets}

    payloads = {p: "MUTILATED\n" for p in targets}
    boom = targets[-1]

    import tools.export_spec as export_spec

    # THE REAL RENAME IS CAPTURED BEFORE IT IS REPLACED. `export_spec.os` IS
    # the `os` module, so patching an attribute on it rebinds the name the
    # replacement itself would call -- the first version recursed until the
    # stack ran out, which is fault injection replacing the behaviour under
    # test rather than perturbing it.
    real_replace = export_spec.os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        calls["n"] += 1
        if pathlib.Path(dst) == boom:
            raise OSError("injected fault at the last rename")
        return real_replace(src, dst)

    monkeypatch.setattr(export_spec.os, "replace", failing_replace)

    with pytest.raises(OSError):
        publish(payloads)

    assert calls["n"] > 1, "the fault fired before anything had been written"
    for path, original in before.items():
        assert path.read_bytes() == original, (
            f"{path.name} was left rewritten after a refused publication")
    assert not list((tree / "spec").glob("*.tmp"))


def test_the_exporter_refuses_a_feature_with_no_feature_map_row(monkeypatch):
    """An orphan used to WARN and still publish, so the spec shipped with a
    feature carrying `phase: None` and a defaulted status."""
    import tools.export_spec as export_spec

    real = export_spec.features_from_prd

    def with_orphan():
        contracts, anchors, schemas = real()
        ghost = dict(contracts[0])
        ghost["id"] = "ZZ9"
        return [*contracts, ghost], anchors, schemas

    monkeypatch.setattr(export_spec, "features_from_prd", with_orphan)
    with pytest.raises(ExportRefused) as refused:
        build(bind_execution=False)
    assert "ZZ9" in str(refused.value)


# ====================== the fingerprint covers the promise ===================

@pytest.mark.parametrize("what,mutate", [
    ("a PRD requirement", lambda t: _append(t / "spec" / "prd" / "part_b.js",
                                            "\n// a further requirement\n")),
    ("a release gate threshold", lambda t: _append(t / "spec" / "release.yaml",
                                                   "\n# a revised threshold\n")),
    ("a playbook obligation", lambda t: _append(
        t / "docs" / "playbooks" / "TEST_A_CHANGE.md", "\nA further step.\n")),
    ("a build-guide rule", lambda t: _append(t / "docs" / "BUILD_GUIDE.md",
                                             "\nA further rule.\n")),
    ("a generated NEVER clause", lambda t: _rewrite(
        t, lambda d: d["features"][0]["never"].append("a further NEVER clause"))),
    ("a generated PRODUCES contract", lambda t: _rewrite(
        t, lambda d: d["features"][0]["produces"].append("`Ghost { }`"))),
])
def test_changing_a_promise_makes_prior_proof_stale(tree, what, mutate):
    """BK-80-AC3's negative control, run: change a promise WITHOUT changing any
    product code, and prior conformance evidence must stop reading as current."""
    before = ev.verification_fingerprint(tree)
    mutate(tree)
    assert ev.verification_fingerprint(tree) != before, (
        f"{what} changed and the evidence identity did not move")


@pytest.mark.parametrize("what,mutate", [
    ("the derived status of every feature", lambda t: _rewrite(t, _all_tested)),
    ("a remeasured coverage verdict", lambda t: _append(
        t / "spec" / "coverage.yaml", "\n# remeasured today\n")),
])
def test_recording_a_verdict_does_not_invalidate_the_evidence_recording_it(
        tree, what, mutate):
    """THE OPPOSITE HALF, AND IT IS NOT A RELAXATION.

    If a verdict were part of the identity of the claim it judges, then
    recording a PASS would move the fingerprint and immediately restale the
    PASS. Nothing could ever be proven, and a check nothing can satisfy is a
    check somebody switches off.
    """
    before = ev.verification_fingerprint(tree)
    mutate(tree)
    assert ev.verification_fingerprint(tree) == before, (
        f"{what} moved the evidence identity, so proof invalidates itself")


def test_the_fingerprint_reports_an_absent_promise_tree_rather_than_ignoring_it(
        tree):
    """An absent input must never read as unchanged. §9."""
    before = ev.verification_fingerprint(tree)
    shutil.rmtree(tree / "docs" / "playbooks")
    assert ev.verification_fingerprint(tree) != before


def _append(path: pathlib.Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf8") + text, encoding="utf8")


def _all_tested(doc: dict) -> None:
    for f in doc["features"]:
        f["status"] = "tested"
        f["proof"] = "PASS"
        f["implementation"] = "complete"
        f["implementation_basis"] = "registry"
        f["delivered_by"] = ["BK-999"]
