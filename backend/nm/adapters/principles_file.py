"""Read-only local owner guidance; snapshots do not change during a turn."""

from __future__ import annotations

import hashlib
from pathlib import Path

from nm.ports.principles import PrinciplesSnapshot, PrinciplesUnavailable

DEFAULT_PRINCIPLES = (
    Path(__file__).resolve().parents[3] / "docs" / "blueprint" / "LEGAL_BRAIN_PRINCIPLES.md"
)
MAX_PRINCIPLES_BYTES = 64_000


class FilePrinciples:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else DEFAULT_PRINCIPLES

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
            return PrinciplesSnapshot(text, hashlib.sha256(raw).hexdigest())
        except ValueError as exc:
            raise PrinciplesUnavailable("The reasoning principles are not usable.") from exc


def load_principles(path: Path | str | None = None) -> PrinciplesSnapshot:
    return FilePrinciples(path).load()
