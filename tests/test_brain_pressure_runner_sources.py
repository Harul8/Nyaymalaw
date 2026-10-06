"""Evidence input ownership guards for the offline pressure runner."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nm_pressure_runner",
    ROOT / "development_environment/one_off_tools/brain_pressure_test_20261006.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_additional_sources_are_deduplicated_and_resolved_to_the_repository(tmp_path, monkeypatch):
    packet = tmp_path / "input.json"
    packet.write_text("{}")
    monkeypatch.setattr(RUNNER, "ROOT", tmp_path)
    assert RUNNER.selected_source_files(["input.json", packet]) == ["input.json"]


@pytest.mark.parametrize("kind", ["missing", "directory", "outside", "outside_symlink"])
def test_additional_sources_reject_missing_or_unowned_files(tmp_path, monkeypatch, kind):
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    monkeypatch.setattr(RUNNER, "ROOT", root)
    if kind == "outside_symlink":
        supplied = root / "linked.json"
        supplied.symlink_to(outside)
    elif kind == "outside":
        supplied = outside
    elif kind == "directory":
        supplied = root
    else:
        supplied = root / "missing.json"
    with pytest.raises(ValueError, match="existing repository files"):
        RUNNER.selected_source_files([supplied])


def test_input_byte_change_changes_the_evidence_snapshot(tmp_path, monkeypatch):
    tests = tmp_path / "tests"
    tests.mkdir()
    for filename in ("brain_pressure_support.py", "conftest.py", "test_brain_material.py",
                     "brain_reader_fixture.py", "brain_continuation_fixture.py"):
        (tests / filename).write_text("")
    packet = tmp_path / "input.json"
    packet.write_text('{"original": true}')
    monkeypatch.setattr(RUNNER, "ROOT", tmp_path)
    before = RUNNER.test_source_hashes([], ["input.json"])
    packet.write_text('{"original": false}')
    after = RUNNER.test_source_hashes([], ["input.json"])
    assert before.keys() == after.keys()
    assert before["input.json"] != after["input.json"]
    assert all(before[key] == after[key] for key in before if key != "input.json")
