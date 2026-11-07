"""What the library holds, as the Admin area reads it (plan AN.46, piece 46l; owner decisions D119, D122 and D125, 7 Nov 2026).

READ-ONLY AND CONTENT-FREE. The held law is public law, not an advocate's work, and this reads only its descriptions: each store's lineage
record (how many passages and vectors, which model, when it was recorded, how it was checked), the Acts catalogue the Acts store was built
from (how many Acts, by jurisdiction and by their standing), the earlier copies kept beside a store when it was last replaced, and any
candidate store built beside it that is not yet the one searched (the judgments' read stage). It opens no passage, no judgment's text, no
index; nothing here is changed, and a source that cannot be read says so for itself and leaves the others standing (D128).

THE ACTS CATALOGUE IS READ ONCE PER CHANGE OF THE FILE (its size and time), not on every page view; it is a fourteen-megabyte list.

Adding documents is not done from here (D122, and the append job's own rule that the owner runs it with the server stopped): this shows
what is held, so that an addition can be seen to have arrived.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Mapping

from nm.arrive.admin_port import AdminChecksPort

_log = logging.getLogger("nm.admin")
#: The most jurisdictions and standings listed; the rest are one line, "others".
SHOWN = 40
_COPY_MARK = ".before-"
#: What a candidate store's summary may say, by name: counts and a time, nothing else is passed on.
_CANDIDATE_NUMBERS = ("judgments", "passages", "problems", "notes", "printed", "unnumbered", "not in the earlier store")


def _size(path: Path) -> int | None:
    try:
        if path.is_dir():
            return sum(p.stat().st_size for p in path.iterdir() if p.is_file())
        return path.stat().st_size
    except OSError:
        return None


class AdminLibrary:
    """The held-law stores of one installation, described. See the module's note."""

    def __init__(self, *, checks: AdminChecksPort, root: Path, corpus_dir: Path):
        self.checks, self.root, self.corpus = checks, Path(root), Path(corpus_dir)
        self._catalogues: dict[Path, tuple[tuple[int, int], dict]] = {}

    # ----------------------------------------------------------------- the Acts catalogue ---

    def _catalogue(self, folder: Path) -> dict | None:
        """The Acts the store was built from: how many, by jurisdiction and by standing. None when it cannot be read."""
        path = folder / "acts.json"
        try:
            info = path.stat()
            key = (info.st_size, info.st_mtime_ns)
            cached = self._catalogues.get(path)
            if cached and cached[0] == key:
                return cached[1]
            rows = json.loads(path.read_text(encoding="utf8"))
            if not isinstance(rows, list):
                return None
            by_jurisdiction = Counter(str(r.get("jurisdiction") or "not stated") for r in rows if isinstance(r, dict))
            by_standing = Counter(str(r.get("standing") or "not stated") for r in rows if isinstance(r, dict))
            found = {"acts": len(rows), "by_jurisdiction": self._top(by_jurisdiction), "by_standing": self._top(by_standing)}
            self._catalogues[path] = (key, found)
            return found
        except (OSError, ValueError):
            return None

    @staticmethod
    def _top(counts: Counter) -> list[dict]:
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        shown = [{"name": name, "acts": n} for name, n in ordered[:SHOWN]]
        rest = sum(n for _, n in ordered[SHOWN:])
        return shown + ([{"name": "others", "acts": rest}] if rest else [])

    # ----------------------------------------------------------------- earlier copies ---

    def _earlier_copies(self) -> list[dict]:
        """What was set aside when a store was last replaced: files and folders named with `.before-` beside the stores and beside
        their lineage records. Name and size only."""
        found = []
        for base in (self.corpus, self.root / ".nm" / "retrieval"):
            try:
                candidates = [*base.glob(f"*{_COPY_MARK}*"), *base.glob(f"*/*{_COPY_MARK}*")]
            except OSError:
                continue
            for path in sorted(candidates):
                found.append({"name": path.relative_to(base).as_posix(), "bytes": _size(path), "folder": path.is_dir()})
        return found

    # ------------------------------------------------------------ candidates built beside ---

    def _candidates(self) -> list[dict]:
        """Stores built beside the live ones and not yet searched: a folder with a summary and a passages file (a read stage's output)."""
        found = []
        try:
            folders = sorted(p for p in self.corpus.iterdir() if p.is_dir())
        except OSError:
            return found
        for folder in folders:
            summary = folder / "summary.json"
            if not summary.is_file() or not (folder / "passages.jsonl").is_file():
                continue
            entry: dict = {"name": folder.name, "readable": False}
            try:
                said = json.loads(summary.read_text(encoding="utf8"))
                entry.update(readable=True, built_at=str(said.get("built_at", "")),
                             passages_file_bytes=_size(folder / "passages.jsonl"),
                             has_index=any(folder.glob("*.index")),
                             **{name.replace(" ", "_"): int(said[name]) for name in _CANDIDATE_NUMBERS
                                if isinstance(said.get(name), int) and not isinstance(said.get(name), bool)})
            except (OSError, ValueError):
                pass
            found.append(entry)
        return found

    # ------------------------------------------------------------------------ the page ---

    def library(self) -> Mapping[str, object]:
        stores = []
        for store in self.checks.law():
            entry = dict(store)
            if entry.get("readable"):
                try:
                    record = json.loads((self.root / ".nm" / "retrieval" / (
                        "bare_acts.lineage.json" if entry["collection"] == "acts" else "judgments.lineage.json")).read_text(encoding="utf8"))
                    vector, passages = record["vector_index"]["path"], record["passage_store"]["path"]
                    entry.update(index_bytes=_size(self.corpus / vector), passage_store_bytes=_size(self.corpus / passages))
                    if entry["collection"] == "acts":
                        entry["catalogue"] = self._catalogue((self.corpus / passages).parent)
                except (OSError, ValueError, KeyError, TypeError):
                    entry.update(index_bytes=None, passage_store_bytes=None)
            stores.append(entry)
        return {"stores": stores, "earlier_copies": self._earlier_copies(), "candidates": self._candidates(),
                "disk": self.checks.disk()}
