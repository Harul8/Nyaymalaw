"""The corpus manifest. PRD §4.5 / D5A.

M1 IS THE WHOLE DESIGN, AND GETTING IT BACKWARDS MAKES THIS USELESS
-------------------------------------------------------------------
The manifest states INTENDED coverage and is therefore CURATED. A manifest
generated from what the index contains can only tell you what is there. It can
never tell you what is MISSING, because absence leaves no trace to enumerate.

To detect a gap you need an independent assertion -- "the Limitation Act 1963,
all sections and the whole Schedule" -- against which absence becomes visible.

That assertion is what makes the three-state answer computable:

    zero hits + manifest says we hold it   -> HELD_NOT_FOUND, a DEFECT
    zero hits + manifest says we do not    -> NOT_HELD, an honest refusal

Without it, both look identical and the refusal rule is unfalsifiable.

Each entry carries the identifier PATTERNS the Act is held under, because the
corpus holds the same Act under more than one convention at different degrees
of completeness -- and a coverage figure from one store is refused, not
reported (check `act-1`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


def _expand(spec: list) -> tuple[str, ...]:
    """Expand "1-44" into every section in the range.

    Ranges are a WRITING convenience only. What is stored is the explicit set,
    because the manifest has to answer "should we hold s.6?" for one section at
    a time, and a range that is never expanded cannot answer it.
    """
    out: list[str] = []
    for item in spec:
        text = str(item)
        if "-" in text and text.replace("-", "").isdigit():
            lo, hi = text.split("-", 1)
            out.extend(str(n) for n in range(int(lo), int(hi) + 1))
        elif text.lower().startswith("article_") and "-" in text:
            _, rng = text.split("_", 1)
            lo, hi = rng.split("-", 1)
            out.extend(f"Article_{n}" for n in range(int(lo), int(hi) + 1))
        else:
            out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class ManifestEntry:
    act_name: str
    act_patterns: tuple[str, ...]
    intended_sections: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    in_force_from: date | None = None
    in_force_to: date | None = None

    def covers(self, section: str) -> bool:
        return section in self.intended_sections


@dataclass(frozen=True)
class Manifest:
    entries: tuple[ManifestEntry, ...]
    corpus_version: str = "unreconciled"
    reconciled_at: date | None = None

    @staticmethod
    def load(path: str | Path) -> "Manifest":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf8"))
        entries = tuple(
            ManifestEntry(
                act_name=e["act_name"],
                act_patterns=tuple(e["act_patterns"]),
                intended_sections=_expand(e["intended_sections"]),
                keywords=tuple(e.get("keywords", ())),
                in_force_from=(date.fromisoformat(e["in_force_from"])
                               if e.get("in_force_from") else None),
                in_force_to=(date.fromisoformat(e["in_force_to"])
                             if e.get("in_force_to") else None),
            )
            for e in doc["acts"]
        )
        return Manifest(
            entries=entries,
            corpus_version=doc.get("corpus_version", "unreconciled"),
            reconciled_at=(date.fromisoformat(doc["reconciled_at"])
                           if doc.get("reconciled_at") else None),
        )

    def resolve(self, question: str) -> ManifestEntry | None:
        """Which Act governs the question. Keyword-scored, deliberately simple.

        This is the resolution layer at its thinnest -- enough to make the
        three-state answer real in slice 1. The cause-of-action graph that
        replaces it is slice 5.
        """
        low = question.lower()
        best, score = None, 0
        for e in self.entries:
            hits = sum(1 for k in e.keywords if k.lower() in low)
            if hits > score:
                best, score = e, hits
        return best

    def intends(self, entry: ManifestEntry, section: str) -> bool:
        return entry.covers(section)

    def act(self, name: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.act_name == name), None)
