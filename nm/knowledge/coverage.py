"""What the corpus holds for a jurisdiction -- read at turn time.

THE FINDING THIS EXISTS TO ANSWER
----------------------------------
An external review's first stop-ship was that the product claims Telangana
coverage it has not measured. The figures were already written down in
`docs/BASELINE.md`. They changed nothing, because a measured fact in a document
is not a gate.

THE FIRST VERSION OF THE MEASUREMENT WAS ITSELF WRONG, and this module is what
served it. It counted the `hc_telangana` court LABEL, which no record in the
corpus carries, and so reported that no High Court output was held for the
jurisdiction. There are 4,280 Andhra Pradesh judgments held and every one of
them BINDS Telangana under the standing decision in BASELINE.md 1.1. Binding is
a RELATIONSHIP; a zero from the wrong index reads exactly like absence.

So the measurement now has one home and two consumers:

    tools/releasegate.py  measures ------> spec/coverage.yaml
                                              |
                    the release decision <----+----> THIS MODULE, at turn time
                                                     (gate G-COVERAGE)

The advocate is told BEFORE they rely on an answer, not after, and the release
gate and the disclosure cannot disagree because there is nothing for them to
disagree about.

WHY THE ANSWER HAS THREE STATES
--------------------------------
`MET` and `UNMET` are not enough. If `spec/coverage.yaml` has never been
written -- a fresh clone, a corpus not attached, a measurement that failed --
then returning `MET` claims coverage nobody measured, and returning `UNMET`
claims a gap nobody measured. Both are assertions. `NOT_MEASURED` is the truth,
and it is disclosed in the same breath as a real gap would be.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from nm.domain.coverage import CoveragePosition, CoverageState


@dataclass(frozen=True)
class CoverageProfile:
    measured_at: str | None
    corpus_version: str | None
    jurisdictions: dict

    @staticmethod
    def load(path: str | Path) -> "CoverageProfile":
        p = Path(path)
        if not p.exists():
            return CoverageProfile(None, None, {})
        doc = yaml.safe_load(p.read_text(encoding="utf8")) or {}
        return CoverageProfile(
            measured_at=doc.get("measured_at"),
            corpus_version=doc.get("corpus_version"),
            jurisdictions=doc.get("jurisdictions") or {},
        )

    @property
    def measured(self) -> bool:
        return bool(self.jurisdictions)

    def position(self, jurisdiction: str) -> CoveragePosition:
        """The coverage position for a matter's jurisdiction."""
        if not self.measured:
            return CoveragePosition(
                CoverageState.NOT_MEASURED, jurisdiction,
                "corpus coverage has never been measured on this installation. "
                "Run `python tools/releasegate.py --write`. Until then I cannot "
                "tell you whether the binding court's output is held, and I am "
                "not going to imply that it is.")

        entry = self.jurisdictions.get(jurisdiction)
        if entry is None:
            return CoveragePosition(
                CoverageState.NOT_MEASURED, jurisdiction,
                f"coverage for {jurisdiction!r} has not been measured. This "
                f"corpus is scoped to Telangana and the Union of India, and an "
                f"answer about another State's law out of it would be "
                f"confidently wrong.",
                self.measured_at, self.corpus_version)

        gap = (entry.get("gap") or "").strip()
        if gap:
            held = entry.get("held") or {}
            return CoveragePosition(
                CoverageState.UNMET, jurisdiction,
                f"{gap} What is held: "
                + ", ".join(f"{k} {v:,}" for k, v in sorted(held.items()))
                + ".",
                self.measured_at, self.corpus_version)

        return CoveragePosition(
            CoverageState.MET, jurisdiction,
            "the binding courts for this jurisdiction have output held",
            self.measured_at, self.corpus_version)
