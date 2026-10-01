"""Read-only local owner guidance; snapshots do not change during a turn."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nm.Archives.legal_brain.common.principles_port import PrinciplesSnapshot, PrinciplesUnavailable
from nm.Archives.legal_brain.retrieve.practice_playbooks_port import PlaybooksUnavailable

DEFAULT_PRINCIPLES = (
    Path(__file__).resolve().parents[4] / "docs" / "blueprint" / "LEGAL_BRAIN_PRINCIPLES.md"
)
MAX_PRINCIPLES_BYTES = 64_000


class FilePrinciples:
    def __init__(self, path: Path | str | None = None, *, playbooks=None):
        self.path = Path(path) if path is not None else DEFAULT_PRINCIPLES
        self.playbooks = playbooks

    def load(self) -> PrinciplesSnapshot:
        """Read the actual file now; no cache or silent old-copy fallback."""
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_PRINCIPLES_BYTES + 1)
        except OSError as exc:
            raise PrinciplesUnavailable("The reasoning principles could not be read.") from exc
        if len(raw) > MAX_PRINCIPLES_BYTES:
            raise PrinciplesUnavailable("The reasoning principles exceed their declared bound.")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise PrinciplesUnavailable("The reasoning principles are not valid UTF-8.") from exc
        try:
            if self.playbooks is not None:
                books = self.playbooks.load()
                text += ("\nOWNER-EDITED PRACTICE NAVIGATION CATALOGUE\n"
                    + json.dumps({"version": books.version, "catalogue": books.catalogue},
                                 sort_keys=True, ensure_ascii=False, allow_nan=False)
                    + "\nGuidance is navigation only, never a rule, evidence, permission, "
                      "or a fixed case route. Read an exact playbook on demand; retrieve "
                      "its sources and independently assess support and applicability.\n")
                raw = text.encode("utf8")
            return PrinciplesSnapshot(text, hashlib.sha256(raw).hexdigest())
        except (ValueError, PlaybooksUnavailable) as exc:
            raise PrinciplesUnavailable("The reasoning principles are not usable.") from exc


def load_principles(path: Path | str | None = None) -> PrinciplesSnapshot:
    return FilePrinciples(path).load()
