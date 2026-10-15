"""ClamAV as the trusted malware checker for uploaded documents (owner decisions,
15 Oct 2026: Windows Defender is switched off on this PC by another antivirus).

A document is read only after this check clears it. The bytes reach ClamAV's
command-line scanner through standard input, so this code writes no copy; ClamAV
keeps its own working copy in a private folder. A file ClamAV flags is held. A scan
that cannot run, does not finish or could not look at the whole file is
'unavailable', and the file is held too, never read on trust. The installation names
the scanner and its definitions folder (NM_CLAMSCAN, NM_CLAMAV_DATABASE); without
them nothing is read.
"""
from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path

NAME = "clamav"
_FOUND = re.compile(r"^stdin: (.+) FOUND$", re.MULTILINE)


class ClamAVCheck:
    name = NAME

    def __init__(self, executable, database, workdir, *, timeout: float = 180.0):
        self.executable = Path(executable) if executable else None
        self.database = Path(database) if database else None
        self.workdir, self.timeout = Path(workdir), timeout
        # Each scan loads the full definitions (about a gigabyte of memory); one at a time.
        self._one_at_a_time = threading.Lock()

    def available(self) -> bool:
        return bool(self.executable and self.executable.is_file()
                    and self.database and self.database.is_dir())

    def check(self, data: bytes) -> tuple[str, str]:
        """'clear', 'held' or 'unavailable', with the reason the advocate is shown."""
        if not self.available():
            return "unavailable", "no malware checker is set up on this installation"
        command = [str(self.executable), "--no-summary", "--stdout", f"--database={self.database}",
                   f"--tempdir={self.workdir}", "--alert-exceeds-max=yes", "-"]
        try:
            self.workdir.mkdir(parents=True, exist_ok=True)
            with self._one_at_a_time:
                done = subprocess.run(command, input=data, capture_output=True,
                                      timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            return "unavailable", "the malware check did not finish in time"
        except OSError:
            return "unavailable", "the malware checker could not be started"
        said = (done.stdout or b"").decode("utf-8", "replace").replace("\r", "")
        if done.returncode == 0:
            return "clear", "no threat found by ClamAV"
        if done.returncode == 1:
            found = _FOUND.search(said)
            signature = re.sub(r"[^A-Za-z0-9._-]", "", found.group(1))[:100] if found else ""
            if signature.startswith("Heuristics.Limits.Exceeded"):
                return "unavailable", "the malware check could not look at the whole file"
            return "held", ("ClamAV reported a threat in this file"
                            + (f" ({signature})" if signature else ""))
        return "unavailable", f"the malware check could not complete (code {done.returncode})"
