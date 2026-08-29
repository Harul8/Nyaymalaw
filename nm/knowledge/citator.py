"""Subsequent treatment, and an honest account of how little it covers.

WHAT IS ACTUALLY THERE, MEASURED 30 AUGUST 2026
------------------------------------------------
`legal_database/vector_store/citator.json` holds 4,894 entries against 33,791
judgments. 1,317 are negative. The treatment verbs are FOLLOWED 3,111,
AFFIRMED 1,153, REVERSED 946, OVERRULED 283, DISTINGUISHED 279, DOUBTED 77,
PER_INCURIAM 76, DISAPPROVED 44.

So roughly ONE JUDGMENT IN SEVEN has any citator entry, and the key is the case
NAME as written by the citing judgment -- not an id. Name matching across
Indian case-name conventions is lossy in both directions.

WHY THAT MAKES THE THIRD STATE THE ENTIRE DESIGN
-------------------------------------------------
A lookup miss here means "the citator has nothing to say". Reported as `clean`,
it becomes "this case is good law" -- a claim about the whole body of Indian
case law derived from a 14% index. That is defect shape S3 (an empty result
from the wrong index, indistinguishable from absence) pointed at the single
most damaging thing this product could get wrong.

So a miss is `NOT_CHECKED`, a Finding whose treatment is `NOT_CHECKED` cannot
carry a proposition alone, and the advocate is told which of the two it is.

A hit is not `clean` either, unless the entry is non-negative AND names what it
was treated on. Treatment without scope cannot distinguish "overruled" from
"overruled on a point we are not relying on".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nm.ports.evidence import Treatment, TreatmentState

_NEGATIVE_VERBS = {"REVERSED", "OVERRULED", "DOUBTED", "DISAPPROVED", "PER_INCURIAM"}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def normalise_case_name(name: str) -> str:
    """Fold a case name onto the citator's key convention.

    Deliberately conservative. A looser fold would raise the hit rate and lower
    the precision, and a WRONG treatment record is worse than a missing one:
    `NOT_CHECKED` blocks, while a mismatched `clean` clears.
    """
    text = (name or "").lower()
    text = text.replace(" versus ", " v ").replace(" vs. ", " v ").replace(" vs ", " v ")
    text = text.replace("&", " and ")
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


class Citator:
    """Read-only. Built offline, consulted at turn time."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._index: dict[str, dict] | None = None

    @property
    def available(self) -> bool:
        return self._path.exists()

    def _load(self) -> dict[str, dict]:
        if self._index is None:
            if not self.available:
                self._index = {}
            else:
                raw = json.loads(self._path.read_text(encoding="utf8", errors="replace"))
                self._index = {normalise_case_name(k): v for k, v in raw.items()}
        return self._index

    @property
    def entries(self) -> int:
        return len(self._load())

    def treatment(self, case_name: str) -> Treatment:
        """Three states, always. THE MISS IS THE IMPORTANT ONE."""
        if not self.available:
            return Treatment.not_checked(
                f"the citator is not readable at {self._path}; subsequent "
                f"treatment is UNKNOWN, not clear")

        key = normalise_case_name(case_name)
        entry = self._load().get(key)
        if entry is None:
            return Treatment.not_checked(
                f"no citator entry for {case_name!r}. The citator holds "
                f"{self.entries} named cases against 33,791 judgments, so a miss "
                f"means the index is silent -- NOT that the judgment is undoubted")

        counts: dict[str, int] = entry.get("counts") or {}
        verbs = tuple(sorted(counts))
        by = tuple(entry.get("by") or ())
        negative = bool(entry.get("negative")) or bool(_NEGATIVE_VERBS & set(counts))

        if negative:
            return Treatment(
                state=TreatmentState.NEGATIVE,
                scope=("the citator does not record WHICH proposition was treated, "
                       "so this is negative treatment of the judgment at large"),
                verbs=verbs, by=by)

        return Treatment(
            state=TreatmentState.CLEAN,
            scope=(f"checked against {self.entries} citator entries: "
                   f"{', '.join(verbs) or 'no verbs recorded'}, none negative. "
                   f"The scope of each treatment is not recorded"),
            verbs=verbs, by=by)
