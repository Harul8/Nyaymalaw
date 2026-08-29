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
    jurisdiction: str = "Union of India"

    def covers(self, section: str) -> bool:
        return section in self.intended_sections

    def in_force_on(self, day: date) -> bool:
        """Was this instrument in force on the governing date?

        The 2024 codes make this load-bearing rather than pedantic: the CrPC
        and the BNSS both match "criminal procedure", and serving the
        superseded one for a 2025 offence is a wrong answer that reads exactly
        like a right one.
        """
        if self.in_force_from and day < self.in_force_from:
            return False
        if self.in_force_to and day > self.in_force_to:
            return False
        return True


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
                jurisdiction=e.get("jurisdiction", "Union of India"),
            )
            for e in doc["acts"]
        )
        return Manifest(
            entries=entries,
            corpus_version=doc.get("corpus_version", "unreconciled"),
            reconciled_at=(date.fromisoformat(doc["reconciled_at"])
                           if doc.get("reconciled_at") else None),
        )

    def resolve(self, question: str,
                on: date | None = None) -> tuple[ManifestEntry | None, ManifestEntry | None]:
        """Which Act governs the question ON THE GOVERNING DATE.

        Returns `(entry, superseded)`. `superseded` is the best keyword match
        that was EXCLUDED because it was not in force on that date, and it is
        returned rather than dropped so the caller can say *"the Act you are
        describing existed, on a different date"* instead of the flat and false
        *"not held"*.

        Dropping it silently is the failure this signature exists to prevent:
        a 2025 criminal matter matches the CrPC on keywords, the CrPC is out of
        force, and a bare `None` would report a corpus gap where the truth is a
        code transition.

        Keyword-scored and deliberately simple. This is the resolution layer at
        its thinnest; the cause-of-action graph that replaces it is slice 5.
        """
        low = question.lower()
        best: ManifestEntry | None = None
        superseded: ManifestEntry | None = None
        best_score = superseded_score = 0
        for e in self.entries:
            hits = sum(1 for k in e.keywords if k.lower() in low)
            if not hits:
                continue
            if on is not None and not e.in_force_on(on):
                if hits > superseded_score:
                    superseded, superseded_score = e, hits
                continue
            if hits > best_score:
                best, best_score = e, hits
        return best, superseded

    def intends(self, entry: ManifestEntry, section: str) -> bool:
        return entry.covers(section)

    def act(self, name: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.act_name == name), None)
