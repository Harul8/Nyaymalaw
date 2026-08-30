"""The coverage position -- a value, so both layers can speak it.

The MEASUREMENT lives in `nm/knowledge/coverage.py` (it reads a file) and the
GATE lives in `nm/core/turn.py` (it must stay pure). Neither may import the
other, so the thing they exchange lives here, in the layer that imports
nothing.

That is not architectural tidiness. `core/` having no I/O is what buys the
class-A cadence -- the invariants that run every commit in seconds with no
corpus and no model -- and a knowledge import in the engine would end it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.text import refuses_blank_text


class CoverageState(str, Enum):
    """THREE states. `NOT_MEASURED` is the one that earns its keep.

    If coverage has never been measured -- a fresh clone, a corpus not
    attached, a measurement that failed -- then `MET` claims coverage nobody
    established and `UNMET` claims a gap nobody established. Both are
    assertions. Only the third is true.
    """

    MET = "met"
    UNMET = "unmet"
    NOT_MEASURED = "not_measured"


@refuses_blank_text()
@dataclass(frozen=True)
class CoveragePosition:
    state: CoverageState
    jurisdiction: str
    detail: str
    measured_at: str | None = None
    corpus_version: str | None = None

    @property
    def discloses(self) -> bool:
        """Anything but MET is said out loud. A gap nobody measured is
        disclosed exactly like a measured one -- the advocate's exposure is
        identical, and only one of the two is easier to admit."""
        return self.state is not CoverageState.MET
