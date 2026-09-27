"""Bounded local owner file; no cache, model writes or source acquisition."""
from __future__ import annotations

import json
from pathlib import Path

from nm.legal_brain.practice_playbooks_port import PlaybooksSnapshot, PlaybooksUnavailable

DEFAULT_PLAYBOOKS = Path(__file__).resolve().parents[2] / "docs/blueprint/PRACTICE_PLAYBOOKS.json"
MAX_BYTES = 128000


class FilePracticePlaybooks:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_PLAYBOOKS

    def load(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("The owner playbooks exceed their byte bound")
            def no_duplicates(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate playbook field")
                    result[key] = value
                return result
            body = json.loads(raw.decode("utf8"), object_pairs_hook=no_duplicates)
            return PlaybooksSnapshot(json.dumps(body, sort_keys=True,
                                                ensure_ascii=False, allow_nan=False))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise PlaybooksUnavailable(
                "The current owner playbooks cannot be established.") from exc
