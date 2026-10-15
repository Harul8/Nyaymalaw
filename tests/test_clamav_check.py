"""ClamAV as the malware checker for uploaded documents (owner decisions, 15 Oct 2026).

The scanner is replaced by recorded outcomes here: these prove how each outcome is
read, not ClamAV's detection, which the scratch trial measured with EICAR.
"""
import subprocess

import pytest

from nm.open_matter import clamav_check
from nm.open_matter.clamav_check import ClamAVCheck

pytestmark = pytest.mark.class_a


@pytest.fixture
def installed(tmp_path):
    executable, database = tmp_path / "clamscan.exe", tmp_path / "database"
    executable.write_bytes(b"")
    database.mkdir()
    return ClamAVCheck(executable, database, tmp_path / "scan")


def scanner(monkeypatch, returncode=0, stdout=b"", raises=None):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(command, returncode, stdout, b"")

    monkeypatch.setattr(clamav_check.subprocess, "run", run)
    return calls


def test_the_bytes_go_through_standard_input_and_a_clean_file_is_cleared(installed, monkeypatch):
    calls = scanner(monkeypatch, 0, b"stdin: OK\r\n")
    assert installed.check(b"some words") == ("clear", "no threat found by ClamAV")
    (command, kwargs), = calls
    assert command[-1] == "-" and kwargs["input"] == b"some words"
    assert "--alert-exceeds-max=yes" in command and not any((installed.workdir).iterdir())


def test_a_flagged_file_is_held_with_the_signature_clamav_named(installed, monkeypatch):
    scanner(monkeypatch, 1, b"stdin: Eicar-Test-Signature FOUND\r\n")
    assert installed.check(b"x") == ("held", "ClamAV reported a threat in this file (Eicar-Test-Signature)")


@pytest.mark.parametrize("outcome", [
    {"returncode": 1, "stdout": b"stdin: Heuristics.Limits.Exceeded.MaxFileSize FOUND\r\n"},
    {"returncode": 2, "stdout": b"stdin: Can't open file ERROR\r\n"},
    {"raises": subprocess.TimeoutExpired("clamscan", 180)},
    {"raises": OSError("cannot start")},
])
def test_a_check_that_did_not_look_at_the_whole_file_is_unavailable_never_clear(installed, monkeypatch, outcome):
    scanner(monkeypatch, **outcome)
    state, reason = installed.check(b"x")
    assert state == "unavailable" and reason


def test_without_a_configured_scanner_nothing_runs_and_nothing_is_cleared(tmp_path, monkeypatch):
    calls = scanner(monkeypatch, 0)
    for checker in (ClamAVCheck(None, None, tmp_path), ClamAVCheck(tmp_path / "missing.exe", tmp_path, tmp_path)):
        assert checker.check(b"x") == ("unavailable", "no malware checker is set up on this installation")
    assert calls == []
