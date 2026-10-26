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


# --- the resident engine and the definitions (open items round, 15 Oct 2026) ---------

class FakeClamd:
    """clamd's stream protocol on this computer: PING, INSTREAM and RELOAD."""

    def __init__(self, reply=b"stream: OK\0"):
        import socket
        import threading
        self.reply, self.seen = reply, []
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        import struct
        while True:
            try:
                link, _ = self.server.accept()
            except OSError:
                return
            with link:
                command = b""
                while not command.endswith(b"\0"):
                    command += link.recv(1)
                self.seen.append(command)
                if command == b"zINSTREAM\0":
                    data = b""
                    while True:
                        size = struct.unpack("!L", self._exact(link, 4))[0]
                        if not size:
                            break
                        data += self._exact(link, size)
                    self.seen.append(data)
                    link.sendall(self.reply)
                else:
                    link.sendall(b"PONG\0" if command == b"zPING\0" else b"RELOADING\0")

    @staticmethod
    def _exact(link, size):
        out = b""
        while len(out) < size:
            out += link.recv(size - len(out))
        return out


@pytest.mark.parametrize("reply,verdict", [
    (b"stream: OK\0", ("clear", "no threat found by ClamAV")),
    (b"stream: Eicar-Test-Signature FOUND\0", ("held", "ClamAV reported a threat in this file (Eicar-Test-Signature)")),
    (b"stream: Heuristics.Limits.Exceeded.MaxScanSize FOUND\0",
     ("unavailable", "the malware check could not look at the whole file")),
    (b"INSTREAM size limit exceeded. ERROR\0", ("unavailable", "the malware check could not look at the whole file")),
])
def test_a_ready_resident_engine_scans_the_streamed_bytes(installed, monkeypatch, reply, verdict):
    calls = scanner(monkeypatch, 0)
    clamd = FakeClamd(reply)
    installed._port, installed._ready = clamd.port, True
    data = b"words " * 400_000  # more than one streamed piece
    assert installed.check(data) == verdict
    assert clamd.seen == [b"zINSTREAM\0", data] and calls == []  # no command-line scan


def test_a_resident_engine_that_stops_hands_the_scan_back_to_the_command_line(installed, monkeypatch):
    calls = scanner(monkeypatch, 0)
    clamd = FakeClamd()
    clamd.server.close()
    installed._port, installed._ready = clamd.port, True
    assert installed.check(b"x") == ("clear", "no threat found by ClamAV")
    assert len(calls) == 1 and installed._ready is False


def test_without_a_scanner_nothing_is_started_at_start(tmp_path, monkeypatch):
    monkeypatch.setattr(clamav_check.subprocess, "Popen", lambda *a, **k: pytest.fail("started"))
    ClamAVCheck(None, None, tmp_path).warm()


def test_the_resident_engine_is_started_beside_the_scanner_and_listens_only_here(installed, monkeypatch, tmp_path):
    started = []

    class Process:
        def poll(self):
            return 0  # ends the readiness wait at once

    monkeypatch.setattr(clamav_check.subprocess, "Popen", lambda command, **kwargs: started.append(command) or Process())
    scanner(monkeypatch, 0)
    (tmp_path / "clamd.exe").write_bytes(b"")
    installed.check(b"x")
    command, = started
    assert command[0] == str(tmp_path / "clamd.exe")
    config = (installed.workdir / "clamd.conf").read_text(encoding="utf-8")
    assert "TCPAddr 127.0.0.1" in config and f"DatabaseDirectory {installed.database}" in config


def test_a_relative_store_folder_gives_every_clamav_program_absolute_paths_only(tmp_path, monkeypatch):
    """Measured 26 Oct 2026 (plan AN.25): with the live NM_MATTER_STORE=.nm/matters the engine's configuration held relative
    paths and clamd refused to start ("ERROR: LogFile requires full path"), so every upload reloaded all the definitions."""
    from pathlib import Path
    (tmp_path / "tools" / "database").mkdir(parents=True)
    for name in ("clamscan.exe", "clamd.exe"):
        (tmp_path / "tools" / name).write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    started = []

    class Process:
        def poll(self):
            return 0  # ends the readiness wait at once

    monkeypatch.setattr(clamav_check.subprocess, "Popen", lambda command, **kwargs: started.append(command) or Process())
    calls = scanner(monkeypatch, 0)
    checker = ClamAVCheck("tools/clamscan.exe", "tools/database", Path("matters") / "scan",
                          freshclam_config="tools/freshclam.conf")
    checker.check(b"x")
    config = dict(line.split(" ", 1) for line in (tmp_path / "matters" / "scan" / "clamd.conf").read_text("utf-8").splitlines()
                  if line)
    for key in ("DatabaseDirectory", "TemporaryDirectory", "LogFile"):
        assert Path(config[key]).is_absolute(), f"{key} is {config[key]}"
    (clamd, option), = started
    assert Path(clamd).is_absolute() and Path(option.split("=", 1)[1]).is_absolute()
    (command, _), = calls
    assert Path(command[0]).is_absolute()
    for part in command:
        if part.startswith(("--database=", "--tempdir=")):
            assert Path(part.split("=", 1)[1]).is_absolute(), part
    assert checker.freshclam_config.is_absolute() and checker.freshclam.is_absolute()


def test_definitions_are_refreshed_only_when_a_day_old_and_the_engine_reloads(installed, tmp_path):
    import os
    import time
    runs = []
    signatures = installed.database / "daily.cvd"
    signatures.write_bytes(b"")
    assert installed.refresh(run=lambda *a, **k: runs.append(a)) == "current" and runs == []
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(signatures, (old, old))
    assert installed.refresh(run=lambda *a, **k: runs.append(a)) == "not set up" and runs == []
    (tmp_path / "freshclam.exe").write_bytes(b"")
    (tmp_path / "freshclam.conf").write_text("DatabaseMirror database.clamav.net\n")
    clamd = FakeClamd()
    installed._port, installed._ready = clamd.port, True
    done = lambda command, **kwargs: runs.append(command) or subprocess.CompletedProcess(command, 0)  # noqa: E731
    assert installed.refresh(run=done) == "refreshed"
    command, = runs
    assert command == [str(tmp_path / "freshclam.exe"), f"--config-file={tmp_path / 'freshclam.conf'}",
                       f"--datadir={installed.database}"]
    assert clamd.seen == [b"zRELOAD\0"]
