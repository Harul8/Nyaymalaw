"""The gate, its evidence and its stamp name exactly one checked tree.

These are planted failures, not inventory assertions. Each input class that
used to fall outside the digest is changed in isolation, and the old framing
collision is constructed in both directions.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import zipfile

import pytest
import yaml

from assurance.control_plane import evidence
from assurance.gate import check, gatestamp, known_failures

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("relative", [
    "pipeline/manifest.yaml",                 # non-Python generated spec
    "assurance/specification/prd/gates.json",                # authoritative PRD, non-JavaScript
    "docs/Nyaymalaw_PRD.docx",            # authoritative rendered PRD
    "docs/backlog/known_failures.yaml",   # control registry
    "docs/backlog/steps.yaml",            # journey registry
    "frontend/app.js",                         # served product
    ".github/workflows/class-a.yml",       # CI workflow/configuration
    "pyproject.toml",                     # Python/gate configuration
    "tests/js/render_turn_partition.mjs", # Class-A JavaScript helper
    "development_environment/developer_tooling/crg_serve.ps1",                # PowerShell helper
    "assurance/hooks/pre-commit",              # extensionless gate hook
    "pytest.ini",                          # root test-discovery configuration
], ids=lambda path: path.replace("/", "-"))
def test_every_effective_input_class_moves_the_checked_tree_identity(
        tmp_path: pathlib.Path, relative: str):
    planted = tmp_path / relative
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_bytes(b"before\n")
    before = evidence.verification_fingerprint(tmp_path)

    planted.write_bytes(b"after\n")

    assert evidence.verification_fingerprint(tmp_path) != before, (
        f"the canonical identity omitted {relative}")


def test_a_new_suffix_does_not_fall_out_of_a_covered_tree(tmp_path):
    (tmp_path / "tools").mkdir()
    before = evidence.verification_fingerprint(tmp_path)
    (tmp_path / "tools" / "future.runner").write_bytes(b"new input")
    assert evidence.verification_fingerprint(tmp_path) != before


def _unframed_python_digest(root: pathlib.Path) -> str:
    """The replaced path+content construction, retained only as the control."""
    digest = hashlib.sha256()
    for path in sorted((root / "backend" / "nm").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_path_and_content_boundaries_are_collision_safe(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    for root in (left, right):
        (root / "backend" / "nm").mkdir(parents=True)

    (left / "backend" / "nm" / "a.py").write_bytes(b"")
    (left / "backend" / "nm" / "b.py").write_bytes(b"backend/nm/b.py\n")
    (right / "backend" / "nm" / "a.py").write_bytes(b"backend/nm/b.py")
    (right / "backend" / "nm" / "b.py").write_bytes(b"\n")

    assert _unframed_python_digest(left) == _unframed_python_digest(right), (
        "the control no longer constructs the old boundary collision")
    assert (evidence.verification_fingerprint(left)
            != evidence.verification_fingerprint(right)), (
        "path/content framing still admits the constructive collision")


def _write_yaml(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def test_delivery_and_evidence_binding_relations_are_claim_identity(tmp_path):
    status = {
        "schema": 1,
        "features": [{
            "id": "A1", "implementation": "complete",
            "disposition": "delivered", "delivery_items": ["BK-1"],
        }],
        "items": [{
            "id": "BK-1", "delivery_status": "verifying",
            "implementation": "complete", "verification": "passing",
            "delivers": ["A1"],
            "stage_records": {
                "test": {"result": "VERIFIED", "ref": "tests/test_one.py"},
            },
            "acceptance": [{
                "id": "BK-1-AC1", "requirement": "the claim",
                "required_evidence": ["domain_test"],
                "evidence": {"domain_test": {
                    "result": "PASS", "ref": "tests/test_one.py::test_one",
                }},
            }],
        }],
    }
    path = tmp_path / "docs" / "backlog" / "status.yaml"
    _write_yaml(path, status)
    before = evidence.verification_fingerprint(tmp_path)

    status["items"][0]["delivers"] = ["B2"]
    _write_yaml(path, status)
    after_delivery_move = evidence.verification_fingerprint(tmp_path)
    assert after_delivery_move != before

    status["items"][0]["acceptance"][0]["evidence"]["domain_test"][
        "ref"] = "tests/test_two.py::test_two"
    _write_yaml(path, status)
    after_evidence_move = evidence.verification_fingerprint(tmp_path)
    assert after_evidence_move != after_delivery_move

    status["items"][0]["stage_records"]["test"]["ref"] = "tests/test_two.py"
    _write_yaml(path, status)
    assert evidence.verification_fingerprint(tmp_path) != after_evidence_move


def test_recording_generated_verdicts_reaches_a_fixed_point(tmp_path):
    status_path = tmp_path / "docs" / "backlog" / "status.yaml"
    status = {
        "schema": 1,
        "events": [{"type": "old verdict"}],
        "features": [{
            "id": "A1", "implementation": "none", "disposition": "planned",
            "delivery_items": ["BK-1"],
        }],
        "items": [{
            "id": "BK-1", "delivery_status": "in_progress",
            "implementation": "partial", "verification": "partial",
            "delivers": ["A1"], "stage_records": {"test": {"result": "OPEN"}},
            "acceptance": [{
                "id": "BK-1-AC1", "requirement": "the claim",
                "required_evidence": ["domain_test"],
                "evidence": {"domain_test": {
                    "result": "NOT_RUN", "note": "not measured",
                    "ref": "tests/test_one.py::test_one",
                }},
            }],
        }],
    }
    _write_yaml(status_path, status)
    feature_path = tmp_path / "assurance" / "specification" / "features.yaml"
    _write_yaml(feature_path, {"features": [{
        "id": "A1", "does": ["the claim"], "status": "decided",
        "implementation": "none", "implementation_basis": "registry",
        "proof": "NOT_RUN", "delivered_by": ["BK-1"],
    }]})
    coverage_path = tmp_path / "assurance" / "specification" / "coverage.yaml"
    _write_yaml(coverage_path, {"verdict": "NOT_RUN"})
    evidence_path = tmp_path / "docs" / "backlog" / "evidence" / "class_a.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text('{"result":"NOT_RUN"}\n', encoding="utf-8")
    before = evidence.verification_fingerprint(tmp_path)

    status["events"] = [{"type": "new verdict"}]
    status["features"][0].update(
        implementation="complete", disposition="delivered")
    status["items"][0].update(
        delivery_status="verifying", implementation="complete",
        verification="passing", stage_records={"test": {"result": "VERIFIED"}})
    proof = status["items"][0]["acceptance"][0]["evidence"]["domain_test"]
    proof.update(result="PASS", note="measured")
    _write_yaml(status_path, status)
    _write_yaml(feature_path, {"features": [{
        "id": "A1", "does": ["the claim"], "status": "tested",
        "implementation": "complete", "implementation_basis": "trace",
        "proof": "PASS", "delivered_by": ["BK-1"],
    }]})
    _write_yaml(coverage_path, {"verdict": "PASS"})
    evidence_path.write_text('{"result":"PASS"}\n', encoding="utf-8")

    assert evidence.verification_fingerprint(tmp_path) == before, (
        "recording a verdict invalidated the claim that verdict judges")


def test_rendering_the_backlog_board_does_not_restate_its_verdict_as_a_claim(
        tmp_path):
    backlog = tmp_path / "docs" / "BACKLOG.md"
    backlog.parent.mkdir(parents=True)
    backlog.write_text(
        "Authored reason.\n<!-- BACKLOG_STATUS:START -->\nold board\n"
        "<!-- BACKLOG_STATUS:END -->\nAuthored limit.\n",
        encoding="utf-8",
    )
    before = evidence.verification_fingerprint(tmp_path)

    backlog.write_text(
        "Authored reason.\n<!-- BACKLOG_STATUS:START -->\nnew generated board\n"
        "<!-- BACKLOG_STATUS:END -->\nAuthored limit.\n",
        encoding="utf-8",
    )
    assert evidence.verification_fingerprint(tmp_path) == before

    backlog.write_text(
        "Changed authored reason.\n<!-- BACKLOG_STATUS:START -->\nnew generated board\n"
        "<!-- BACKLOG_STATUS:END -->\nAuthored limit.\n",
        encoding="utf-8",
    )
    assert evidence.verification_fingerprint(tmp_path) != before


def test_generated_current_plan_can_record_identity_without_becoming_identity(
        tmp_path):
    workbook = tmp_path / "docs" / "Nyaymalaw_End_to_End_Project_Plan.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"workbook containing fingerprint one")
    before = evidence.verification_fingerprint(tmp_path)

    workbook.write_bytes(b"workbook containing fingerprint two")

    assert evidence.verification_fingerprint(tmp_path) == before, (
        "a generated reader view made the checked-tree identity recursive")
    generator = tmp_path / "assurance" / "specification" / "plan" / "build_current_plan.mjs"
    generator.parent.mkdir(parents=True)
    generator.write_text("generator version one\n", encoding="utf-8")
    generated_from = evidence.verification_fingerprint(tmp_path)
    generator.write_text("generator version two\n", encoding="utf-8")
    assert evidence.verification_fingerprint(tmp_path) != generated_from


def _write_prd_docx(path: pathlib.Path, *, created: str, document: str,
                    zip_year: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    core = (
        '<cp:coreProperties xmlns:cp="urn:core" '
        'xmlns:dcterms="urn:terms"><dcterms:created>'
        f"{created}</dcterms:created><cp:title>Nyaymalaw PRD</cp:title>"
        "</cp:coreProperties>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in (
            ("docProps/core.xml", core),
            ("word/document.xml", document),
        ):
            info = zipfile.ZipInfo(name, date_time=(zip_year, 1, 1, 0, 0, 0))
            archive.writestr(info, body)


def test_prd_identity_is_semantic_not_a_zip_timestamp(tmp_path):
    path = tmp_path / "docs" / "Nyaymalaw_PRD.docx"
    _write_prd_docx(
        path, created="2026-09-10T00:00:00Z",
        document="<document><p>same promise</p></document>", zip_year=2025,
    )
    before = evidence.verification_fingerprint(tmp_path)

    _write_prd_docx(
        path, created="2027-01-01T00:00:00Z",
        document="<document><p>same promise</p></document>", zip_year=2026,
    )
    assert evidence.verification_fingerprint(tmp_path) == before

    _write_prd_docx(
        path, created="2027-01-01T00:00:00Z",
        document="<document><p>changed promise</p></document>", zip_year=2026,
    )
    assert evidence.verification_fingerprint(tmp_path) != before


def test_real_repository_identity_uses_the_portable_index_population(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.local\nweb/dist/\n", encoding="utf-8")
    runner = tmp_path / "tools" / "runner.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("answer = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".gitignore", "tools/runner.py"],
        check=True,
    )
    before = evidence.verification_fingerprint(tmp_path)

    ignored = tmp_path / "tools" / "machine.local"
    ignored.write_text("machine-specific\n", encoding="utf-8")
    untracked = tmp_path / "tools" / "not-yet-a-candidate.py"
    untracked.write_text("candidate = 1\n", encoding="utf-8")
    assert evidence.verification_fingerprint(tmp_path) == before

    runner.write_text("answer = 2\n", encoding="utf-8")
    assert evidence.verification_fingerprint(tmp_path) != before
    runner.write_text("answer = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "tools/not-yet-a-candidate.py"],
        check=True,
    )
    assert evidence.verification_fingerprint(tmp_path) != before


def test_gate_stamp_uses_the_canonical_checked_tree_identity(tmp_path):
    assert gatestamp.tree_digest(tmp_path) == evidence.verification_fingerprint(
        tmp_path)


def test_staged_candidate_must_be_the_exact_tree_the_gate_checked(
        tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "tools" / "runner.py"
    source.parent.mkdir(parents=True)
    source.write_text("answer = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "tools/runner.py"], check=True)
    monkeypatch.setattr(gatestamp, "ROOT", tmp_path)
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / ".nm" / "last_green.json")

    checked = evidence.verification_fingerprint(tmp_path)
    assert gatestamp.staged_tree_digest(tmp_path) == checked
    gatestamp.record(checked)
    assert gatestamp.state(require_index=True)[0] == "current"

    source.write_text("answer = 2\n", encoding="utf-8")
    gatestamp.record(evidence.verification_fingerprint(tmp_path))
    verdict, sentence = gatestamp.state(require_index=True)
    assert verdict == "stale"
    assert "staged commit candidate" in sentence


def test_two_unchanged_scoped_runs_remain_valid_but_never_become_full(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gatestamp, "ROOT", tmp_path)
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / ".nm" / "last_green.json")
    baseline = "a" * 64
    monkeypatch.setattr(known_failures, "registry_digest", lambda: baseline)
    monkeypatch.setattr(
        known_failures, "load",
        lambda: [known_failures.Known(
            "KF-1", ("trace",),
            known_failures.FailureFact("trace", "T1", "planted"),
            ("BK-1-AC1",), "planted",
        )],
    )
    (tmp_path / "backend" / "nm").mkdir(parents=True)
    (tmp_path / "backend" / "nm" / "a.py").write_text("x = 1\n", encoding="utf-8")

    for _ in range(2):
        gatestamp.record(kind="scoped", waived=["KF-1"], baseline=baseline)
        assert gatestamp.state()[0] == "current_scoped"

    monkeypatch.setattr(sys, "argv", ["gatestamp.py", "--quiet"])
    assert gatestamp.main() == 0
    assert "SCOPED BUILD PASS -- FULL GATE RED" in capsys.readouterr().out

    monkeypatch.setattr(
        sys, "argv", ["gatestamp.py", "--quiet", "--require-full"])
    assert gatestamp.main() == 1
    assert "CURRENT_SCOPED" in capsys.readouterr().out


def test_stamp_reader_fails_closed_on_a_legacy_or_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(gatestamp, "ROOT", tmp_path)
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / ".nm" / "last_green.json")
    gatestamp.STAMP.parent.mkdir(parents=True)
    current = gatestamp.tree_digest(tmp_path)
    gatestamp.STAMP.write_text(json.dumps({"tree": current, "kind": "maybe"}),
                               encoding="utf-8")
    assert gatestamp.state()[0] == "not_assessed"


@pytest.mark.parametrize("kind,waived,baseline", [
    ("full", ["KF-1"], "a" * 64),
    ("scoped", ["KF-1"], "short"),
    ("scoped", ["KF-1", "KF-1"], "a" * 64),
])
def test_stamp_writer_rejects_incompatible_payloads(
        tmp_path, monkeypatch, kind, waived, baseline):
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / "last_green.json")
    with pytest.raises(ValueError):
        gatestamp.record("b" * 64, kind=kind, waived=waived, baseline=baseline)


def test_scoped_stamp_waivers_must_equal_the_registered_population(
        tmp_path, monkeypatch):
    monkeypatch.setattr(gatestamp, "ROOT", tmp_path)
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / ".nm" / "last_green.json")
    monkeypatch.setattr(known_failures, "registry_digest", lambda: "a" * 64)
    monkeypatch.setattr(
        known_failures, "load",
        lambda: [known_failures.Known(
            "KF-2", ("trace",),
            known_failures.FailureFact("trace", "T2", "different"),
            ("BK-1-AC1",), "different",
        )],
    )
    (tmp_path / "backend" / "nm").mkdir(parents=True)
    gatestamp.record(
        evidence.verification_fingerprint(tmp_path), kind="scoped",
        waived=["KF-1"], baseline="a" * 64,
    )
    assert gatestamp.state()[0] == "not_assessed"


def test_stamp_reader_cannot_self_certify_from_its_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(gatestamp, "ROOT", tmp_path)
    monkeypatch.setattr(gatestamp, "STAMP", tmp_path / ".nm" / "last_green.json")
    monkeypatch.setattr(sys, "argv", ["gatestamp.py", "--write"])
    with pytest.raises(SystemExit):
        gatestamp.main()
    assert not gatestamp.STAMP.exists()


def test_the_running_gate_voids_a_non_python_input_mutation(
        tmp_path, monkeypatch, capsys):
    planted = tmp_path / "frontend" / "app.js"
    planted.parent.mkdir(parents=True)
    planted.write_text("before\n", encoding="utf-8")
    calls = 0

    def fake_step(_label, _cmd, allow_warn=False):
        nonlocal calls
        if calls == 0:
            planted.write_text("after\n", encoding="utf-8")
        calls += 1
        return True, ""

    monkeypatch.setattr(check, "step", fake_step)
    monkeypatch.setattr(
        check, "verification_fingerprint",
        lambda: evidence.verification_fingerprint(tmp_path))
    monkeypatch.setattr(sys, "argv", ["check.py"])

    assert check.main() == 1
    assert "CHECK VOID" in capsys.readouterr().out


def test_the_running_gate_stamps_the_digest_it_actually_verified(
        monkeypatch, capsys):
    checked = "c" * 64
    recorded: list[str] = []

    monkeypatch.setattr(check, "step", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(check, "verification_fingerprint", lambda: checked)
    monkeypatch.setattr(gatestamp, "record", lambda digest: recorded.append(digest))
    monkeypatch.setattr(sys, "argv", ["check.py"])

    assert check.main() == 0
    assert recorded == [checked]
    assert "CHECK OK" in capsys.readouterr().out


def test_a_new_preflight_failure_does_not_run_the_expensive_populations(
        monkeypatch, capsys):
    labels: list[str] = []

    def fake_step(label, _cmd, allow_warn=False):
        labels.append(label)
        return label != "ruff", "planted ruff failure"

    monkeypatch.setattr(check, "step", fake_step)
    monkeypatch.setattr(check, "verification_fingerprint", lambda: "d" * 64)
    monkeypatch.setattr(check, "_known_failure_registry_is_empty", lambda: True)
    monkeypatch.setattr(sys, "argv", ["check.py"])

    assert check.main() == 1
    # THE LAST PREFLIGHT STEP, which since 14 September 2026 is the evidence
    # population check rather than pylint. It is preflight because it reads
    # files and takes about a second; the property this test holds -- every
    # cheap step still runs, and no expensive population does -- is unchanged.
    assert labels[-1] == "backlog population"
    assert "pylint E0601,E0606" in labels
    assert not any(label.startswith("pytest") for label in labels)
    assert "NOT RUN -- preflight is already red" in capsys.readouterr().out


def test_declared_failures_still_require_every_population(
        monkeypatch):
    labels: list[str] = []

    def fake_step(label, _cmd, allow_warn=False):
        labels.append(label)
        return label != "ruff", "planted declared failure"

    monkeypatch.setattr(check, "step", fake_step)
    monkeypatch.setattr(check, "verification_fingerprint", lambda: "e" * 64)
    monkeypatch.setattr(check, "_known_failure_registry_is_empty", lambda: False)
    monkeypatch.setattr(check, "_scoped_verdict", lambda *_args: 0)
    monkeypatch.setattr(sys, "argv", ["check.py"])

    assert check.main() == 0
    assert "pytest Class-A (offline every-commit)" in labels
    assert "pytest (ordinary local)" in labels


def _complete_class_a_result(tmp_path: pathlib.Path) -> dict:
    fingerprint = evidence.verification_fingerprint(tmp_path)
    return {
        "schema": 1,
        "kind": "class_a",
        "source_fingerprint": fingerprint,
        "finished_fingerprint": fingerprint,
        "started_at": "2026-09-10T00:00:00+00:00",
        "finished_at": "2026-09-10T00:01:00+00:00",
        "runner": "pytest test fixture",
        "command": evidence.CLASS_A_COMMAND,
        "exit_code": 0,
        "selection": "full_class_a",
        "complete": True,
        "tests": {"tests/test_one.py::test_one": {"outcome": "passed"}},
    }


@pytest.mark.parametrize("outcome", ["failed", "skipped", "not_run"])
def test_publishable_class_a_population_contains_only_passes(tmp_path, outcome):
    result = _complete_class_a_result(tmp_path)
    result["tests"]["tests/test_one.py::test_one"]["outcome"] = outcome
    problems = evidence.validate_class_a(result, root=tmp_path)
    assert any("did not pass" in problem for problem in problems)


@pytest.mark.parametrize("nodeid,row", [
    ("", {"outcome": "passed"}),
    ("not-a-pytest-node", {"outcome": "passed"}),
    ("tests/test_one.py::test_one", "passed"),
])
def test_publishable_class_a_population_rejects_malformed_rows(
        tmp_path, nodeid, row):
    result = _complete_class_a_result(tmp_path)
    result["tests"] = {nodeid: row}
    assert evidence.validate_class_a(result, root=tmp_path)


def test_duplicate_json_keys_cannot_shrink_an_evidence_population(tmp_path):
    artifact = tmp_path / "class_a.json"
    artifact.write_text(
        '{"tests":{"tests/a.py::test_a":{"outcome":"passed"},'
        '"tests/a.py::test_a":{"outcome":"skipped"}}}', encoding="utf-8")
    assert evidence.load_result(artifact) == {}
