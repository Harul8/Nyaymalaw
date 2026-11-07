"""Acts staged for the library by an admin, read and checked before anything is appended (plan AN.46, pieces 46m and 46o; owner decisions D122 and
D125, 7 Nov 2026).

WHAT THIS DOES AND WHAT IT LEAVES TO THE OWNER. An admin chooses Act text files and a jurisdiction; they are copied into a folder of their own
(never into the library), and the free reading job (`pipeline/check_bare_acts.py`: the append job's own reading of an Act, without its encoder)
is run on them in a separate process with a time limit. The batch then says, for each Act, how many sections and passages it would make, where
its numbering was read as something other than sections, and whether the library already holds it (the append refuses an Act already held).
An admin who has looked at that approves the batch, and the batch then shows the exact commands for the owner's terminal. THE APPEND ITSELF IS
NOT RUN FROM HERE: it replaces the index files, which a running server holds open, and the owner runs it with the server stopped (the append
job's own rule). When it has been run the library page shows the new counts, and a batch whose Acts are all held reads "in the library".

A BATCH IS ONE FOLDER, batch.json AND ITS FILES. Nothing is shared between batches; discarding one removes its folder. The folder name is made
here and never from what the admin typed, a file name must be `<year>_<number>_<title>.txt` with no path in it, and the limits (twenty files,
eight megabytes each, forty in all) are checked before anything is written.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from nm.arrive.admin_port import AdminChangeRefused, AdminUnavailable

_log = logging.getLogger("nm.admin")
MAX_FILES = 20
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
CHECK_SECONDS = 180
_FILE = re.compile(r"\d{4}_\d{1,5}_[^\\/:*?\"<>|\x00-\x1f]{1,150}\.txt\Z")
_JURISDICTION = re.compile(r"[A-Za-z][A-Za-z .'-]{0,59}\Z")
_BATCH = re.compile(r"[0-9a-f]{12}\Z")
_STATES = ("checked", "needs attention", "approved")


class AdminStaging:
    """The staged batches of one installation. See the module's note."""

    def __init__(self, folder: Path, *, root: Path, held: Callable[[], set | None], python: str | None = None,
                 timeout: int = CHECK_SECONDS):
        self.folder, self.root, self.held = Path(folder), Path(root), held
        self.python, self.timeout = python or sys.executable, timeout

    # ------------------------------------------------------------------------- reading ---

    def _path(self, batch_id: str) -> Path:
        if not isinstance(batch_id, str) or not _BATCH.fullmatch(batch_id):
            raise AdminChangeRefused(404, "There is no such batch.")
        return self.folder / f"batch-{batch_id}"

    def _load(self, batch_id: str) -> dict:
        try:
            return json.loads((self._path(batch_id) / "batch.json").read_text(encoding="utf8"))
        except FileNotFoundError:
            raise AdminChangeRefused(404, "There is no such batch.") from None
        except (OSError, ValueError) as exc:
            raise AdminUnavailable("a batch could not be read") from exc

    def _save(self, batch: dict) -> None:
        path = self._path(batch["id"]) / "batch.json"
        temporary = path.with_name(f".batch.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(batch, indent=1), encoding="utf8")
            os.replace(temporary, path)
        except OSError as exc:
            raise AdminUnavailable("a batch could not be written") from exc

    def batches(self) -> list[dict]:
        """Every batch, newest first, each with its state recomputed against what the library holds now."""
        found = []
        try:
            folders = sorted(p for p in self.folder.glob("batch-*") if p.is_dir()) if self.folder.exists() else []
        except OSError as exc:
            raise AdminUnavailable("the batches could not be listed") from exc
        held = self.held()
        for path in folders:
            try:
                batch = json.loads((path / "batch.json").read_text(encoding="utf8"))
            except (OSError, ValueError):
                found.append({"id": path.name[6:], "unreadable": True})
                continue
            found.append(self._described(batch, held))
        return sorted(found, key=lambda b: b.get("created_at") or "", reverse=True)

    def _described(self, batch: dict, held: set | None) -> dict:
        acts = batch.get("acts", [])
        in_library = bool(acts) and held is not None and all(a.get("act_id") in held for a in acts if a.get("act_id"))
        shown = {**batch, "acts": [{**a, "already_held": (a.get("act_id") in held) if held is not None and a.get("act_id") else None}
                                   for a in acts]}
        shown["in_library"] = in_library
        shown["commands"] = self.commands(batch) if batch.get("state") == "approved" else []
        return shown

    def commands(self, batch: dict) -> list[str]:
        """The two commands the owner runs, in order, with the server stopped: read first, append second."""
        files = " ".join(f'"{self._path(batch["id"]) / "files" / f["name"]}"' for f in batch["staged"])
        base = f'.venv-arrive\\Scripts\\python.exe pipeline\\append_bare_acts.py {files} --jurisdiction "{batch["jurisdiction"]}"'
        return [base + " --dry-run", base]

    # ------------------------------------------------------------------------- staging ---

    def stage(self, jurisdiction: str, files: list[tuple[str, str]], now: datetime) -> dict:
        """Copy the files into a new batch folder, run the free reading on them and keep what it says. Nothing reaches the library."""
        if not isinstance(jurisdiction, str) or not _JURISDICTION.fullmatch(jurisdiction.strip()):
            raise AdminChangeRefused(422, "Name the jurisdiction as the library does, such as Union of India or Telangana.")
        if not files or len(files) > MAX_FILES:
            raise AdminChangeRefused(422, f"Choose between one and {MAX_FILES} Act files.")
        names, total = set(), 0
        for name, text in files:
            if not isinstance(name, str) or not _FILE.fullmatch(name) or name in names:
                raise AdminChangeRefused(422, "Each file is named <year>_<number>_<title>.txt, once, with no folder in it.")
            names.add(name)
            size = len(text.encode("utf8"))
            total += size
            if size == 0 or size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise AdminChangeRefused(422, "A file is empty, or the files are larger than a batch may be "
                                              "(8 MB each, 40 MB together).")
        batch_id = uuid.uuid4().hex[:12]
        base = self._path(batch_id)
        try:
            (base / "files").mkdir(parents=True)
            for name, text in files:
                (base / "files" / name).write_text(text, encoding="utf8", newline="\n")
        except OSError as exc:
            shutil.rmtree(base, ignore_errors=True)
            raise AdminUnavailable("the files could not be staged") from exc
        batch = {"id": batch_id, "created_at": now.isoformat(timespec="seconds"), "jurisdiction": " ".join(jurisdiction.split()),
                 "staged": [{"name": name, "bytes": len(text.encode("utf8"))} for name, text in files], "acts": [], "state": "needs attention",
                 "problem": ""}
        try:
            result = subprocess.run(
                [self.python, str(self.root / "pipeline" / "check_bare_acts.py"), "--jurisdiction", batch["jurisdiction"],
                 *[str(base / "files" / name) for name, _ in files]],
                capture_output=True, text=True, encoding="utf8", timeout=self.timeout, cwd=self.root,
                env={k: v for k, v in os.environ.items() if k != "SSLKEYLOGFILE"})
            if result.returncode != 0:
                raise ValueError("the reading job stopped")
            acts = json.loads(result.stdout.strip().splitlines()[-1])["acts"]
        except (subprocess.TimeoutExpired, ValueError, KeyError, IndexError, OSError) as exc:
            _log.warning("The staged Acts could not be read (%s).", type(exc).__name__)
            batch["problem"] = "The files could not be read just now, so nothing was checked."
            self._save(batch)
            return self._described(batch, self.held())
        batch["acts"] = acts
        held = self.held()
        clean = all("error" not in a and a["sections"] > 0 and not (held is not None and a["act_id"] in held) for a in acts)
        batch["state"] = "checked" if clean else "needs attention"
        self._save(batch)
        return self._described(batch, held)

    # --------------------------------------------------------------------- approving ---

    def approve(self, batch_id: str, actor: str, now: datetime) -> dict:
        batch = self._load(batch_id)
        held = self.held()
        if batch.get("state") == "approved":
            return self._described(batch, held)
        if batch.get("state") != "checked":
            raise AdminChangeRefused(409, "This batch needs attention before it can be approved: an Act did not read, or the library "
                                          "already holds it.")
        batch.update(state="approved", approved_by=actor, approved_at=now.isoformat(timespec="seconds"))
        self._save(batch)
        return self._described(batch, held)

    def discard(self, batch_id: str) -> bool:
        base = self._path(batch_id)
        if not base.exists():
            raise AdminChangeRefused(404, "There is no such batch.")
        try:
            shutil.rmtree(base)
        except OSError as exc:
            raise AdminUnavailable("the batch could not be removed") from exc
        return True
