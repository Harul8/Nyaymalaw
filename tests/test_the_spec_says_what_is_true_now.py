"""THE GENERATED SPEC STATES PRESENT TRUTH, AND ITS IDENTITY COVERS THE PROMISE.

BK-80-AC3, BK-80-AC5, BK-48-AC1, BK-48-AC2.

WHAT WAS WRONG, MEASURED 10 SEPTEMBER 2026
--------------------------------------------
`assurance/gate/export_spec.py` read each feature's status out of the Feature Map sheet
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
from openpyxl import load_workbook

from assurance.control_plane import evidence as ev
from assurance.control_plane.feature_state import implements_map, project, reconcile
from assurance.gate.export_spec import (
    ExportRefused,
    build,
    compare_payloads,
    generated_paths,
    historical_feature_ids,
    plan_tables,
    publish,
)
from assurance.gate.export_spec import main as export_main
from assurance.gate.trace import (
    AssessmentState,
    AwaitingRef,
    assess_population,
    assess_status_support,
    awaiting_problems,
    expired_awaiting,
    implementation_discrepancies,
)
from pipeline.quality import releasegate

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEATURES = ROOT / "assurance" / "specification" / "features.yaml"
STATUS = ROOT / "docs" / "backlog" / "status.yaml"
STEPS = ROOT / "docs" / "backlog" / "steps.yaml"

#: Copied rather than pointed at. A fingerprint test that edited the real tree
#: would leave every other test in the session measuring a mutated repository,
#: and the failure would surface somewhere else entirely.
_SKIP = shutil.ignore_patterns(
    "legal_database", ".git", "node_modules", "__pycache__", "outputs",
    ".nm", ".code-review-graph", ".venv", "venv")


@pytest.fixture
def tree() -> Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as td:
        copy = pathlib.Path(td) / "tree"
        shutil.copytree(ROOT, copy, symlinks=True, ignore=_SKIP)
        yield copy


def _features(path: pathlib.Path = FEATURES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf8"))["features"]


def _rewrite(root: pathlib.Path, mutate: Callable[[dict], None]) -> None:
    path = root / "assurance" / "specification" / "features.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf8"))
    mutate(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                    encoding="utf8")


def _rewrite_status(root: pathlib.Path, mutate: Callable[[dict], None]) -> None:
    path = root / "docs" / "backlog" / "status.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf8"))
    mutate(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                    encoding="utf8")


def _reconcile_sources(root: pathlib.Path = ROOT) -> dict:
    status = yaml.safe_load(
        (root / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8"))
    steps = yaml.safe_load(
        (root / "docs" / "backlog" / "steps.yaml").read_text(encoding="utf8"))["steps"]
    workbook_rows, _evals, _tasks = plan_tables(root)
    anchors = yaml.safe_load(
        (root / "assurance" / "specification" / "anchors.yaml").read_text(encoding="utf8")
    )["anchors"]
    ids = [feature["id"] for feature in yaml.safe_load(
        (root / "assurance" / "specification" / "features.yaml").read_text(encoding="utf8")
    )["features"]]
    return {
        "feature_ids": ids,
        "authored_features": status["features"],
        "steps": steps,
        "items": status["items"],
        "workbook_rows": workbook_rows,
        "declared_ids": implements_map(root),
        "anchor_ids": [anchor["id"] for anchor in anchors],
        "historical_ids": historical_feature_ids(root),
    }


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
    """The registry answers implementation; observations retain their own keys."""
    authored = {row["id"]: row for row in yaml.safe_load(
        STATUS.read_text(encoding="utf8"))["features"]}
    for feature in _features():
        assert feature["implementation_basis"] == "registry"
        assert feature["implementation"] == authored[feature["id"]]["implementation"]
        assert isinstance(feature["delivered_by"], list)
        assert isinstance(feature["declared_in"], list)


def _plant_authored_denial(root: pathlib.Path, feature_id: str = "C6") -> None:
    """A code-declared, delivered feature explicitly denied in this copied tree."""
    before = project([feature_id], root=root, bind_execution=False)[feature_id]
    assert before.declared_in and before.delivered_by, "the counterexample needs both observations"

    def deny(document: dict) -> None:
        rows = [row for row in document["features"] if row["id"] == feature_id]
        assert len(rows) == 1
        rows[0]["implementation"] = "none"

    _rewrite_status(root, deny)


def test_code_and_delivery_cannot_overwrite_authored_implementation(tree):
    """Plant the old C6 denial; a healthier live registry must not remove this control."""
    _plant_authored_denial(tree)
    state = project(["C6"], root=tree, bind_execution=False)["C6"]
    assert state.declared_in and state.delivered_by, "the negative control is vacuous"
    assert state.implementation == "none"
    assert state.implementation_basis == "registry"
    assert state.status == "decided"
    assert state.implementation_contradicted


def test_a_reconciliation_control_row_cannot_supply_feature_proof(tree):
    """A control may inspect delivery reconciliation; it cannot prove A2 itself."""
    def make_control_deliver(document: dict) -> None:
        feature = next(row for row in document["features"] if row["id"] == "A2")
        feature["implementation"] = "complete"
        # Establish a control-only delivery population explicitly. Real A2
        # delivery can grow without supplying this test's counterexample.
        for item in document["items"]:
            if "A2" in (item.get("delivers") or []):
                item["delivers"].remove("A2")
        control = next(item for item in document["items"] if item["id"] == "BK-48")
        assert control["kind"] != "journey"
        control["delivers"] = ["A2"]
        assert [item["id"] for item in document["items"]
                if "A2" in (item.get("delivers") or [])] == ["BK-48"]
        for criterion in control["acceptance"]:
            criterion["required_evidence"] = []

    _rewrite_status(tree, make_control_deliver)
    state = project(["A2"], root=tree, bind_execution=False)["A2"]
    assert state.implementation == "complete"
    assert state.delivered_by == () and state.proof == "NOT_RUN"
    assert state.status == "built"


def test_the_registry_and_the_code_are_reconciled_in_both_directions():
    """Delivery gaps and implementation contradictions remain separate sets."""
    ids = [f["id"] for f in _features()]
    assert ids and len(set(ids)) == len(ids)
    state = project(ids)
    assert set(state) == set(ids)
    exported = _features()
    observed = {fid: list(value.declared_in) for fid, value in state.items()}
    assert {feature["id"]: feature["declared_in"] for feature in exported} == observed
    trace_only, contradicted = implementation_discrepancies(
        exported, {fid: sites for fid, sites in observed.items() if sites})
    assert set(trace_only) == {fid for fid, value in state.items() if value.delivery_gap}
    assert set(contradicted) == {
        fid for fid, value in state.items() if value.implementation_contradicted}
    # The separate planted denial/delivery-removal controls below require
    # both failures. This live reconciliation must also permit their repair.


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
    sources = _reconcile_sources()
    assert reconcile(**sources) == [], "the real sources already disagree"

    if mutation == "unknown_step_feature":
        sources["steps"] = [*sources["steps"],
                            {"id": "STEP-X", "features": ["ZZ9"], "items": []}]
    elif mutation == "unknown_delivers":
        sources["items"] = [*sources["items"],
                            {"id": "BK-999", "kind": "journey", "delivers": ["ZZ9"]}]
    elif mutation == "duplicate_feature":
        sources["feature_ids"] = [*sources["feature_ids"], sources["feature_ids"][0]]
    elif mutation == "unreached_feature":
        sources["feature_ids"] = [*sources["feature_ids"], "ZZ9"]
        sources["authored_features"] = [
            *sources["authored_features"],
            {"id": "ZZ9", "phase": "Z", "implementation": "none"},
        ]
        sources["workbook_rows"] = [
            *sources["workbook_rows"], {"Feature": "ZZ9", "Phase": "Z"}]

    problems = reconcile(**sources)
    assert any(expected in p for p in problems), problems


def test_a_refused_export_writes_nothing_at_all(tree, monkeypatch):
    """TRANSACTIONAL, AND PROVEN ON THE BYTES.

    Five generated files describe one state. Publishing three and failing on
    the fourth leaves a spec that is internally inconsistent in a way that
    reads as ordinary generator drift -- so T1 would send the reader to the
    generator rather than to the failure.
    """
    targets = sorted((tree / "assurance" / "specification").glob("*.yaml"))
    before = {p: p.read_bytes() for p in targets}

    payloads = {p: "MUTILATED\n" for p in targets}
    boom = targets[-1]

    import assurance.gate.export_spec as export_spec

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
    assert not list((tree / "assurance" / "specification").glob("*.tmp"))


def test_the_exporter_refuses_a_feature_with_no_feature_map_row(monkeypatch):
    """An orphan used to WARN and still publish, so the spec shipped with a
    feature carrying `phase: None` and a defaulted status."""
    import assurance.gate.export_spec as export_spec

    real = export_spec.features_from_prd

    def with_orphan(root=ROOT, *, gates_json=None):
        contracts, anchors, schemas = real(root, gates_json=gates_json)
        ghost = dict(contracts[0])
        ghost["id"] = "ZZ9"
        return [*contracts, ghost], anchors, schemas

    monkeypatch.setattr(export_spec, "features_from_prd", with_orphan)
    with pytest.raises(ExportRefused) as refused:
        build(bind_execution=False)
    assert "ZZ9" in str(refused.value)


def _mutate_feature_map(root: pathlib.Path, mutation: str) -> str:
    """Make one raw-row identity defect without passing through a dictionary."""
    path = root / "docs" / "Nyaymalaw_Project_Plan.xlsx"
    workbook = load_workbook(path)
    sheet = workbook["Feature Map"]
    header = next(row for row in range(1, 6) if sheet.cell(row, 1).value == "Feature")
    first = header + 1
    feature_id = str(sheet.cell(first, 1).value)
    if mutation == "duplicate":
        sheet.append([sheet.cell(first, column).value
                      for column in range(1, sheet.max_column + 1)])
    elif mutation == "unknown":
        values = [sheet.cell(first, column).value
                  for column in range(1, sheet.max_column + 1)]
        values[0], values[1] = "ZZ9", "Z"
        sheet.append(values)
    elif mutation == "missing":
        sheet.delete_rows(first)
    elif mutation == "blank_id":
        sheet.cell(first, 1).value = None
    else:  # pragma: no cover - test helper guard
        raise AssertionError(mutation)
    workbook.save(path)
    workbook.close()
    return feature_id


@pytest.mark.parametrize("mutation,expected", [
    ("duplicate", "Feature Map id"),
    ("unknown", "Feature Map names unknown feature 'ZZ9'"),
    ("missing", "is a PRD feature with no Feature Map row"),
    ("blank_id", "Feature Map data row 1 has no feature id"),
])
def test_raw_workbook_identity_defects_refuse_prepublication(tree, mutation, expected):
    """The restored workbook is mutated before the real exporter reads it."""
    _mutate_feature_map(tree, mutation)
    with pytest.raises(ExportRefused) as refused:
        build(root=tree, bind_execution=False)
    assert expected in str(refused.value)


def test_historical_workbook_state_cannot_overwrite_current_authored_state(tree):
    """Change current A2 only; its August tested verdict remains audit history."""
    def reopen_a2(document: dict) -> None:
        feature = next(row for row in document["features"] if row["id"] == "A2")
        feature["implementation"] = "none"

    _rewrite_status(tree, reopen_a2)
    _payloads, built = build(root=tree, bind_execution=False)
    a2 = next(row for row in built["features"] if row["id"] == "A2")
    assert a2["implementation"] == "none" and a2["status"] == "decided"
    assert a2["historical_status"] == "tested"


def test_delivery_and_contradiction_signatures_move_independently(tree):
    """Removing C6's delivery link cannot make its authored denial disappear."""
    _plant_authored_denial(tree)
    _payloads, baseline = build(root=tree, bind_execution=False)
    before_features = baseline["features"]
    implementation_sites = {
        row["id"]: row["declared_in"] for row in before_features if row["declared_in"]}
    before_trace, before_contradicted = implementation_discrepancies(
        before_features, implementation_sites)
    assert "C6" not in before_trace and "C6" in before_contradicted

    def remove_delivery(document: dict) -> None:
        rows = [item for item in document["items"]
                if item.get("kind") == "journey" and "C6" in (item.get("delivers") or [])]
        assert rows, "a deletion that changes no delivery relation proves nothing"
        for row in rows:
            row["delivers"].remove("C6")
        assert not any(item.get("kind") == "journey" and "C6" in (item.get("delivers") or [])
                       for item in document["items"])

    _rewrite_status(tree, remove_delivery)
    _payloads, changed = build(root=tree, bind_execution=False)
    after_trace, after_contradicted = implementation_discrepancies(
        changed["features"], implementation_sites)
    assert set(after_trace) == set(before_trace) | {"C6"}
    assert after_contradicted == before_contradicted


def test_every_generated_output_is_compared_before_explicit_publication(tree, capsys):
    # Use the same real evidence-binding mode as the CLI. An unbound authored
    # PASS and a bound STALE verdict are legitimately different candidates;
    # comparing those was not a publication-integrity check.
    payloads, _built = build(root=tree)
    assert set(payloads) == set(generated_paths(tree))
    publish(payloads)
    assert compare_payloads(payloads) == []

    for path in generated_paths(tree):
        original = path.read_bytes()
        path.write_bytes(original + b"\nSTALE\n")
        assert compare_payloads(payloads) == [(path, "stale")]
        before = path.read_bytes()
        assert export_main([], root=tree) == 1
        assert path.read_bytes() == before, f"check mode silently repaired {path.name}"
        path.write_bytes(original)

    # AND `--write` REPAIRS IT -- asked of the exporter itself, not answered by
    # comparing against `payloads`.
    #
    # WHY THAT DISTINCTION IS THE POINT. `payloads` was built with
    # `bind_execution=False`; `export_main` builds WITH binding, which is the
    # projection this repository actually publishes. The two agree only while
    # no delivering item carries any machine evidence at all -- the wart
    # `export_spec.build` records in as many words -- and that stopped being
    # hypothetical the day BK-54 gained a recorded automated result. Bound, C2
    # and C6 read `proof: STALE`, because the recorded pass was measured
    # against a tree that has since moved; unbound they read `NOT_RUN`,
    # because the authored row on its own says nothing ran.
    #
    # BOTH ARE RIGHT: they answer different questions, and a fresh gate run
    # does not converge them -- it turns the bound answer into PASS while the
    # unbound one stays NOT_RUN. So comparing a bound regeneration against
    # unbound payloads asserted that evidence binding never changes anything,
    # which is the opposite of what binding is for. What this step is actually
    # for is that an explicit write leaves the tree CURRENT, and check mode is
    # the thing that decides what current means.
    regenerated = generated_paths(tree)[0]
    regenerated.write_bytes(regenerated.read_bytes() + b"\nSTALE\n")
    assert export_main(["--write"], root=tree) == 0
    assert export_main([], root=tree) == 0, (
        "check mode still reports the tree stale after an explicit write, so "
        "`--write` did not publish what the next reader compares against")
    capsys.readouterr()


def test_zero_population_and_tested_without_evals_are_never_pass():
    empty = assess_population("T4", 0, "tested features")
    assert empty.state == AssessmentState.NOT_ASSESSED

    feature = {"id": "A1", "status": "tested", "historical_eval_ids": []}
    _t3, t4 = assess_status_support([feature], {"A1": ["backend/nm/example.py"]}, set())
    assert t4.state == AssessmentState.FAIL
    assert t4.issues == ("A1 is marked 'tested' but declares no eval ids",)


def test_release_rg12_uses_the_same_not_assessed_result(monkeypatch):
    from assurance.gate import trace

    monkeypatch.setattr(trace, "load_spec", lambda: ([], []))
    monkeypatch.setattr(trace, "load_gates", lambda: [])
    monkeypatch.setattr(trace, "gate_consultations", lambda: {})
    monkeypatch.setattr(trace, "scan_tree", lambda *_args, **_kwargs: {})
    measured = releasegate.measure_trace()
    assert measured["tested_population"] == 0
    assert measured["status_assessment"].state == AssessmentState.NOT_ASSESSED


def test_every_awaiting_declaration_is_structured_and_resolvable():
    features = _features()
    items = yaml.safe_load(STATUS.read_text(encoding="utf8"))["items"]
    assert awaiting_problems(features, items) == []
    assert expired_awaiting(features, items) == ()
    unresolved = {
        ("A3", 0): AwaitingRef("feature", "ZZ9", "a missing blocker")}
    assert "does not resolve" in awaiting_problems(features, items, unresolved)[0]


# ====================== the fingerprint covers the promise ===================

@pytest.mark.parametrize("what,mutate", [
    ("a PRD requirement", lambda t: _append(t / "assurance" / "specification" / "prd" / "part_b.js",
                                            "\n// a further requirement\n")),
    ("a release gate threshold",
     lambda t: _append(t / "assurance" / "specification" / "release.yaml",
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
        t / "assurance" / "specification" / "coverage.yaml", "\n# remeasured today\n")),
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
