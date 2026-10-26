"""ClamAV as the trusted malware checker for uploaded documents (owner decisions,
15 Oct 2026: Windows Defender is switched off on this PC by another antivirus).

A document is read only after this check clears it. A file ClamAV flags is held. A
scan that cannot run, does not finish or could not look at the whole file is
'unavailable', and the file is held too, never read on trust. The installation names
the scanner and its definitions folder (NM_CLAMSCAN, NM_CLAMAV_DATABASE); without them
nothing is read.

Resident scanning (open items round, 15 Oct 2026): the command-line scanner reloads
every definition on each scan (about 11 seconds), so on first use ClamAV's own
resident engine (clamd, beside the scanner) is started as a child of this process,
listening only on this computer, and the bytes are streamed to it; no copy is written
here. While it loads, or if it stops, the command-line scanner is used as before.

Image fingerprinting (owner decision, 26 Oct 2026, plan AN.25): ClamAV 1.2 and later hash every
page image of a file to match fingerprints of known-bad images, a phishing-lookalike defence. On a
scanned 20-page PDF that took 38 s of a scan that takes 3 s without it, so it is switched off, in
the resident engine and in the command-line scan alike. Every other check of a file is unchanged,
and a file is still read only after the check clears it.

Definitions (owner decision, 15 Oct 2026): the app refreshes them itself with ClamAV's
freshclam (beside the scanner, using the configuration beside the definitions folder)
when they are more than a day old, at start and then daily while it runs, and the
resident engine reloads them. No Windows setting is changed.
"""
from __future__ import annotations

import atexit
import re
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

NAME = "clamav"
_FOUND = re.compile(r"^stdin: (.+) FOUND$", re.MULTILINE)
_STREAM_FOUND = re.compile(r"^stream: (.+) FOUND$")
_CHUNK = 1 << 20
#: Definitions older than this are refreshed.
REFRESH_AFTER = 24 * 60 * 60
_QUIET = getattr(subprocess, "CREATE_NO_WINDOW", 0)
#: The option that switches image fingerprinting, as the scanner's own help names it. An older ClamAV has no such
#: option and refuses one it does not know, which would hold every document, so it is passed only where the help lists it.
_FINGERPRINT_OPTION = "--scan-image-fuzzy-hash"


def _signature(found):
    return re.sub(r"[^A-Za-z0-9._-]", "", found)[:100]


def _verdict(signature):
    if signature.startswith("Heuristics.Limits.Exceeded"):
        return "unavailable", "the malware check could not look at the whole file"
    return "held", "ClamAV reported a threat in this file" + (f" ({signature})" if signature else "")


class ClamAVCheck:
    name = NAME

    def __init__(self, executable, database, workdir, *, timeout: float = 180.0, freshclam_config=None):
        # Every path a ClamAV program is given is absolute (plan AN.25): clamd refuses a configuration holding a relative
        # one ("LogFile requires full path"), and an installation's store folder can be relative (.nm/matters), which
        # left the resident engine unable to start and every scan reloading the definitions.
        self.executable = Path(executable).absolute() if executable else None
        self.database = Path(database).absolute() if database else None
        self.workdir, self.timeout = Path(workdir).absolute(), timeout
        suffix = self.executable.suffix if self.executable else ""
        self.clamd = self.executable.with_name("clamd" + suffix) if self.executable else None
        self.freshclam = self.executable.with_name("freshclam" + suffix) if self.executable else None
        self.freshclam_config = (Path(freshclam_config).absolute() if freshclam_config else
                                 self.database.parent / "freshclam.conf" if self.database else None)
        # The command-line scanner loads the full definitions (about a gigabyte); one at a time.
        self._one_at_a_time = threading.Lock()
        self._resident_lock = threading.Lock()
        self._process = None
        self._port = None
        self._ready = False
        self._refresher = None
        self._fingerprint_switch = None  # whether this ClamAV has the option; None until its help has been read
        self.refreshed = None  # what the last refresh did, for the installation's own view

    def available(self) -> bool:
        return bool(self.executable and self.executable.is_file()
                    and self.database and self.database.is_dir())

    def check(self, data: bytes) -> tuple[str, str]:
        """'clear', 'held' or 'unavailable', with the reason the advocate is shown."""
        if not self.available():
            return "unavailable", "no malware checker is set up on this installation"
        self._start_resident()
        if self._ready:
            verdict = self._stream(data)
            if verdict is not None:
                return verdict
        return self._scan_once(data)

    def _fingerprints_off(self) -> bool:
        """Whether this ClamAV can have image fingerprinting switched off, asked once of the scanner's own help. A help
        that could not be read is not remembered: that scan runs as ClamAV does by default, and the next one asks again."""
        if self._fingerprint_switch is None:
            try:
                helped = subprocess.run([str(self.executable), "--help"], capture_output=True, timeout=30,
                                        check=False, creationflags=_QUIET)
            except (OSError, subprocess.TimeoutExpired):
                return False
            self._fingerprint_switch = _FINGERPRINT_OPTION.encode() in (helped.stdout or b"") + (helped.stderr or b"")
        return self._fingerprint_switch

    # --- the resident engine -------------------------------------------------------

    def warm(self):
        """Start the resident engine when the app starts, so the first upload does not
        wait on two loads of the definitions at once (measured 15 Oct 2026: 30 s)."""
        if self.available():
            self._start_resident()

    def _start_resident(self):
        """Start clamd once, in the background; scans use the command line until it answers."""
        if not (self.clamd and self.clamd.is_file()):
            return
        with self._resident_lock:
            if self._process is not None and self._process.poll() is None:
                return
            self._ready = False
            try:
                self.workdir.mkdir(parents=True, exist_ok=True)
                (self.workdir / "tmp").mkdir(exist_ok=True)
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    self._port = probe.getsockname()[1]
                config = self.workdir / "clamd.conf"
                config.write_text("\n".join([
                    f"DatabaseDirectory {self.database}", f"TCPSocket {self._port}", "TCPAddr 127.0.0.1",
                    f"TemporaryDirectory {self.workdir / 'tmp'}", "StreamMaxLength 40M", "MaxFileSize 40M",
                    "MaxScanSize 160M", "AlertExceedsMax yes", "Foreground yes",
                    *(["ScanImageFuzzyHash no"] if self._fingerprints_off() else []),
                    f"LogFile {self.workdir / 'clamd.log'}", ""]), encoding="utf-8")
                self._process = subprocess.Popen([str(self.clamd), f"--config-file={config}"],
                                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL, creationflags=_QUIET)
            except OSError:
                self._process = None
                return
            atexit.register(self.close)
            threading.Thread(target=self._await_resident, name="clamd-start", daemon=True).start()

    def _await_resident(self, *, limit: float = 300.0):
        ends = time.monotonic() + limit
        while time.monotonic() < ends and self._process is not None and self._process.poll() is None:
            if self._command(b"zPING\0", timeout=5) == "PONG":
                self._ready = True
                return
            time.sleep(1)

    def _command(self, command: bytes, *, timeout: float):
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=timeout) as link:
                link.sendall(command)
                return self._reply(link)
        except OSError:
            return None

    @staticmethod
    def _reply(link):
        said = b""
        while not said.endswith(b"\0"):
            part = link.recv(4096)
            if not part:
                break
            said += part
        return said.rstrip(b"\0").decode("utf-8", "replace").strip()

    def _stream(self, data):
        """Scan through the resident engine; None hands the scan to the command line."""
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=self.timeout) as link:
                link.sendall(b"zINSTREAM\0")
                for start in range(0, len(data), _CHUNK):
                    piece = data[start:start + _CHUNK]
                    link.sendall(struct.pack("!L", len(piece)) + piece)
                link.sendall(struct.pack("!L", 0))
                said = self._reply(link)
        except OSError:
            self._ready = False
            return None
        if said == "stream: OK":
            return "clear", "no threat found by ClamAV"
        found = _STREAM_FOUND.match(said)
        if found:
            return _verdict(_signature(found.group(1)))
        if "size limit exceeded" in said:
            return "unavailable", "the malware check could not look at the whole file"
        return None

    def close(self):
        process, self._process, self._ready = self._process, None, False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    # --- the command-line scanner ----------------------------------------------------

    def _scan_once(self, data):
        command = [str(self.executable), "--no-summary", "--stdout", f"--database={self.database}",
                   f"--tempdir={self.workdir}", "--alert-exceeds-max=yes",
                   *([f"{_FINGERPRINT_OPTION}=no"] if self._fingerprints_off() else []), "-"]
        try:
            self.workdir.mkdir(parents=True, exist_ok=True)
            with self._one_at_a_time:
                done = subprocess.run(command, input=data, capture_output=True,
                                      timeout=self.timeout, check=False, creationflags=_QUIET)
        except subprocess.TimeoutExpired:
            return "unavailable", "the malware check did not finish in time"
        except OSError:
            return "unavailable", "the malware checker could not be started"
        said = (done.stdout or b"").decode("utf-8", "replace").replace("\r", "")
        if done.returncode == 0:
            return "clear", "no threat found by ClamAV"
        if done.returncode == 1:
            found = _FOUND.search(said)
            return _verdict(_signature(found.group(1)) if found else "")
        return "unavailable", f"the malware check could not complete (code {done.returncode})"

    # --- the definitions -------------------------------------------------------------

    def definitions_age(self, now=None):
        """Seconds since the newest definitions file was written, or None if there is none."""
        files = [path for pattern in ("*.cvd", "*.cld") for path in (self.database or Path()).glob(pattern)]
        if not self.database or not files:
            return None
        return (now if now is not None else time.time()) - max(path.stat().st_mtime for path in files)

    def refresh(self, *, now=None, run=subprocess.run):
        """Refresh the definitions when they are over a day old; reload the resident engine."""
        age = self.definitions_age(now)
        if age is not None and age < REFRESH_AFTER:
            self.refreshed = "current"
            return self.refreshed
        if not (self.freshclam and self.freshclam.is_file() and self.freshclam_config
                and self.freshclam_config.is_file()):
            self.refreshed = "not set up"
            return self.refreshed
        try:
            done = run([str(self.freshclam), f"--config-file={self.freshclam_config}",
                        f"--datadir={self.database}"], capture_output=True, timeout=1800, check=False,
                       creationflags=_QUIET)
        except (OSError, subprocess.TimeoutExpired):
            self.refreshed = "failed"
            return self.refreshed
        self.refreshed = "refreshed" if done.returncode == 0 else f"failed (code {done.returncode})"
        if done.returncode == 0 and self._ready:
            self._command(b"zRELOAD\0", timeout=30)
        return self.refreshed

    def keep_refreshed(self, *, every: float = 60 * 60):
        """Check at start and then hourly; freshclam runs only when the definitions are a day old."""
        if self._refresher is not None or not self.available():
            return

        def loop():
            while True:
                self.refresh()
                time.sleep(every)

        self._refresher = threading.Thread(target=loop, name="clamav-definitions", daemon=True)
        self._refresher.start()
