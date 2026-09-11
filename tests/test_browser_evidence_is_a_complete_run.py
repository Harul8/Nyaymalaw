"""A browser report proves one complete, byte-bound run or proves nothing."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from tools import browser_evidence, journey
from tools.browser_evidence import (
    SCHEMA,
    artifact_inventory,
    execution_identity,
    manifest_problems,
    problems,
    publish,
    row_for,
)

pytestmark = pytest.mark.class_a

TREE = "0123456789abcdef0123"
RUN = "12345678-1234-4234-9234-123456789abc"
EXPECTED = ("phase_one", "phase_two", "phase_three")
ARGV = ["pytest", "tests/journey.py", "-m", "journey"]
PYTHON = {"implementation": "cpython", "version": [3, 11, 9],
          "executable": "python.exe"}


def _rows(names=EXPECTED) -> list[dict]:
    return [{"nodeid": f"tests/journey.py::{name}", "scenario": name,
             "state": "PASS", "phase": name, "note": ""} for name in names]


def _counts(rows: list[dict]) -> dict:
    scenarios = {row["scenario"] for row in rows}
    return {
        "pass": sum(row["state"] == "PASS" for row in rows),
        "reproduced": sum(row["state"] == "REPRODUCED" for row in rows),
        "unexplained": sum(row["state"] in ("FAILED", "NOT RUN") for row in rows),
        "missing": len(set(EXPECTED) - scenarios),
        "unexpected": len(scenarios - set(EXPECTED)),
    }


def _report(**overrides) -> dict:
    rows = overrides.pop("rows", _rows())
    expected = overrides.pop("expected", list(EXPECTED))
    argv = overrides.pop("argv", list(ARGV))
    python = overrides.pop("python", copy.deepcopy(PYTHON))
    base = {
        "schema": SCHEMA,
        "run_id": RUN,
        "ran_at": "2026-09-11T09:00:00+00:00",
        "commit": "abc1234",
        "fingerprint": TREE,
        "finished_fingerprint": TREE,
        "argv": argv,
        "python": python,
        "configuration_identity": execution_identity(
            argv=argv, expected=expected, python=python),
        "pytest_returncode": 0,
        "expected": expected,
        "rows": rows,
        "counts": _counts(rows),
        "artifacts": [],
    }
    base.update(overrides)
    return base


def _check(report, *, root=None, **kwargs):
    return problems(report, expected=EXPECTED, fingerprint=TREE,
                    artifact_root=root, **kwargs)


def test_a_complete_run_reconciles():
    assert _check(_report()) == []
    assert row_for(_report(), "tests/journey.py::phase_one") == "PASS"


def test_an_unfinished_run_cannot_prove_green_rows():
    found = _check(_report(pytest_returncode=2))
    assert any("did not complete" in problem for problem in found), found


def test_population_process_and_artifact_mutations_are_each_refused(tmp_path):
    duplicate = _rows()
    duplicate.append(copy.deepcopy(duplicate[0]))
    assert any("appears 2 times" in p for p in _check(_report(rows=duplicate)))

    missing = _rows(("phase_one", "phase_three"))
    assert any("phase_two produced no row" in p
               for p in _check(_report(rows=missing)))

    unexpected = _rows((*EXPECTED, "phase_four"))
    assert any("phase_four is an unexpected row" in p
               for p in _check(_report(rows=unexpected)))

    assert any("did not complete" in problem
               for problem in _check(_report(pytest_returncode=2)))

    retained = tmp_path / "last-weeks-failure.png"
    retained.write_bytes(b"old")
    inventory = artifact_inventory([retained], root=tmp_path, run_id=RUN)
    inventory[0]["run_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert any("different run" in problem
               for problem in _check(_report(artifacts=inventory), root=tmp_path))


def test_suffix_similarity_cannot_replace_an_exact_scenario():
    rows = _rows(("phase_one", "phase_two", "renamed_phase_three"))
    found = _check(_report(rows=rows))
    assert any("phase_three produced no row" in problem for problem in found)
    assert any("renamed_phase_three is an unexpected" in problem for problem in found)


def test_row_identity_and_summary_counts_are_reconciled():
    report = _report()
    report["rows"][0]["scenario"] = "not-phase-one"
    report["counts"]["pass"] = 99
    found = _check(report)
    assert any("exact scenario identity" in problem for problem in found)
    assert any("counts do not reconcile" in problem for problem in found)


def test_start_end_tree_and_execution_configuration_are_bound():
    moved = _check(_report(finished_fingerprint="f" * 20))
    assert any("moved during the run" in problem for problem in moved)

    report = _report()
    report["argv"].append("-k")
    found = _check(report)
    assert any("configuration identity" in problem for problem in found)


def test_report_retains_the_exact_expected_manifest():
    report = _report(expected=["phase_one", "phase_two"])
    found = _check(report)
    assert any("expected manifest differs" in problem for problem in found)


def test_artifact_bytes_are_bound_to_the_run(tmp_path):
    screenshot = tmp_path / "phase_one.png"
    screenshot.write_bytes(b"actual screenshot bytes")
    report = _report(artifacts=artifact_inventory(
        [screenshot], root=tmp_path, run_id=RUN))
    assert _check(report, root=tmp_path) == []

    screenshot.write_bytes(b"changed later")
    found = _check(report, root=tmp_path)
    assert any("bytes changed" in problem or "byte count changed" in problem
               for problem in found), found


def test_retained_or_unavailable_artifacts_are_not_accepted(tmp_path):
    screenshot = tmp_path / "failure.png"
    screenshot.write_bytes(b"old")
    inventory = artifact_inventory([screenshot], root=tmp_path, run_id=RUN)
    inventory[0]["run_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    report = _report(artifacts=inventory)
    assert any("different run" in problem
               for problem in _check(report, root=tmp_path))
    assert any("not available" in problem for problem in _check(report))


def test_atomic_publish_leaves_neither_partial_report_nor_temp_file(tmp_path,
                                                                    monkeypatch):
    target = tmp_path / "report.json"
    target.write_text('{"old": true}', encoding="utf-8")

    def refuse_replace(source, destination):
        raise OSError("planted publication failure")

    monkeypatch.setattr(browser_evidence.os, "replace", refuse_replace)
    with pytest.raises(OSError, match="planted publication failure"):
        publish(target, _report())
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("report,expected", [
    (None, "absent or unreadable"),
    ({}, "unsupported schema"),
    ({"schema": 99}, "unsupported schema"),
])
def test_absent_or_incompatible_reports_never_pass(report, expected):
    assert any(expected in problem for problem in problems(report, expected=EXPECTED))


def test_manifest_is_nonempty_unique_and_the_real_one_is_populated():
    assert any("empty" in problem for problem in manifest_problems(()))
    assert any("names a 2 times" in problem
               for problem in manifest_problems(("a", "b", "a")))
    from tools.journey import EXPECTED as REAL
    assert manifest_problems(REAL) == []
    assert len(REAL) == len(set(REAL)) >= 20


def test_the_runner_writes_every_reader_field():
    import inspect

    from tools import journey
    written = inspect.getsource(journey.run)
    for field in browser_evidence.REQUIRED_FIELDS:
        assert f'"{field}"' in written, field


def _drive_runner(monkeypatch, tmp_path, *, returncode=0,
                  reported=("phase_one", "phase_two")):
    artifacts = tmp_path / "journey"
    report_path = artifacts / "report.json"
    artifacts.mkdir()
    stale = artifacts / "last-weeks-failure.png"
    stale.write_bytes(b"old screenshot")
    monkeypatch.setattr(journey, "ARTIFACTS", artifacts)
    monkeypatch.setattr(journey, "REPORT", report_path)
    monkeypatch.setattr(journey, "EXPECTED", ("phase_one", "phase_two"))
    monkeypatch.setattr(journey, "_fingerprint", lambda: TREE)

    def controlled_process(argv, **_kwargs):
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="abc1234\n", stderr="")
        if argv[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        (artifacts / "phase_one.png").write_bytes(b"current screenshot")
        stdout = "\n".join(
            f"PASSED tests/test_the_journey_login_to_logout.py::{name}"
            for name in reported
        )
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(journey.subprocess, "run", controlled_process)
    result = journey.run([])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return result, report, artifacts, stale


def test_real_runner_publishes_one_complete_byte_bound_execution(monkeypatch,
                                                                  tmp_path):
    result, report, artifacts, stale = _drive_runner(monkeypatch, tmp_path)
    assert result == 0
    assert not stale.exists()
    assert {row["scenario"] for row in report["rows"]} == {
        "phase_one", "phase_two",
    }
    assert [row["path"] for row in report["artifacts"]] == ["phase_one.png"]
    assert problems(
        report, expected=("phase_one", "phase_two"), fingerprint=TREE,
        configuration_identity=report["configuration_identity"],
        artifact_root=artifacts,
    ) == []


def test_real_runner_retains_partial_teardown_failure_as_a_refusal(monkeypatch,
                                                                   tmp_path):
    result, report, artifacts, _ = _drive_runner(
        monkeypatch, tmp_path, returncode=2, reported=("phase_one",))
    assert result == 1
    assert report["pytest_returncode"] == 2
    found = problems(
        report, expected=("phase_one", "phase_two"), fingerprint=TREE,
        configuration_identity=report["configuration_identity"],
        artifact_root=artifacts,
    )
    assert any("did not complete" in problem for problem in found), found
    assert any("phase_two produced no row" in problem for problem in found), found


def test_real_runner_records_an_interruption_that_produces_no_rows(monkeypatch,
                                                                   tmp_path):
    result, report, artifacts, _ = _drive_runner(
        monkeypatch, tmp_path, returncode=4, reported=())
    assert result == 2
    assert report["rows"] == []
    found = problems(
        report, expected=("phase_one", "phase_two"), fingerprint=TREE,
        configuration_identity=report["configuration_identity"],
        artifact_root=artifacts,
    )
    assert any("empty row population" in problem for problem in found), found
    assert all(any(name in problem for problem in found)
               for name in ("phase_one", "phase_two"))
