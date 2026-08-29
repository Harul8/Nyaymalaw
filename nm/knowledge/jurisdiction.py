"""Binding status, computed. Never asserted, never defaulted.

THE DECISION THIS ENCODES
-------------------------
Every Andhra Pradesh High Court judgment held in the corpus is treated as
BINDING on a Telangana matter, not persuasive. That is a product decision taken
on 29 August 2026 and recorded in `docs/BASELINE.md` §1.1, and it is what the
measurement supports rather than a concession:

  * The Telangana High Court was constituted on the bifurcation of
    1 January 2019, and a successor court is bound by the decisions of the
    predecessor court for its territory.
  * Every AP judgment held predates it. The range is 1954-2018 and the
    post-2018 count is EXACTLY ZERO, measured across all 4,280 records.

So "AP before bifurcation binds Telangana" and "all held AP judgments bind
Telangana" currently select the same 4,280 rows. The rules agree today.

THE TRIPWIRE, AND WHY IT IS A THIRD STATE RATHER THAN A DEFAULT
---------------------------------------------------------------
Those two rules stop agreeing the instant ONE post-2018 AP judgment is ingested,
and on that day silence becomes a wrong answer: an advocate told that a 2022
Andhra judgment binds a Telangana court has been misled about the weight of
their own authority, and nothing downstream would catch it.

The alternative -- quietly extending "all AP is binding" to material the
decision was never taken against -- is exactly defect shape S8. So a post-2018
AP judgment returns `NOT_ASSESSED` naming check `bind-1`, which makes the
authority quotable with its status disclosed and unable to carry a proposition
alone. It does not guess, and it does not fail silently.

`tools/releasegate.py` runs `bind-1` over the corpus and FAILS THE BUILD if any
post-2018 AP judgment has been ingested, so this branch is a guard against a
future corpus, not a condition that is expected to be hit in service.

COURT NAMES ARE NORMALISED ON READ, NEVER TRUSTED AS STORED
------------------------------------------------------------
One judgment in 33,791 carries `court = "Supreme Court"` where every other
carries `"Supreme Court of India"`. Any code that groups or filters on the
stored string silently drops it -- a one-row defect today and an unbounded one
after the next ingest.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.ports.evidence import Binding

# The bifurcation of the composite High Court of Judicature at Hyderabad.
BIFURCATION = date(2019, 1, 1)


class Court(str, Enum):
    SUPREME_COURT = "supreme_court"
    HC_TELANGANA = "hc_telangana"
    HC_ANDHRA_PRADESH = "hc_andhra_pradesh"
    HC_OTHER = "hc_other"
    SUBORDINATE = "subordinate"
    UNKNOWN = "unknown"


_NORMALISE: tuple[tuple[re.Pattern, Court], ...] = (
    (re.compile(r"supreme\s+court", re.I), Court.SUPREME_COURT),
    (re.compile(r"telangana", re.I), Court.HC_TELANGANA),
    (re.compile(r"andhra", re.I), Court.HC_ANDHRA_PRADESH),
    (re.compile(r"hyderabad", re.I), Court.HC_ANDHRA_PRADESH),
    (re.compile(r"high\s+court", re.I), Court.HC_OTHER),
    (re.compile(r"district|sessions|magistrate|tribunal", re.I), Court.SUBORDINATE),
)


def normalise_court(raw: str | None) -> Court:
    """Map a stored court string onto the closed vocabulary.

    An unrecognised string returns UNKNOWN, which is a VALUE. It is never
    coerced to the commonest court, because a mis-attributed authority is worse
    than an unattributed one.
    """
    if not raw or not raw.strip():
        return Court.UNKNOWN
    for pattern, court in _NORMALISE:
        if pattern.search(raw):
            return court
    return Court.UNKNOWN


@dataclass(frozen=True)
class BindingRuling:
    """The answer, with the rule that produced it attached.

    `rule` is not decoration. An advocate who cannot see WHY an authority was
    called binding has to take it on trust, and binding status is the single
    field most likely to be wrong in a way that changes what they file.
    """

    status: Binding
    reason: str
    rule: str
    court: Court

    @property
    def assessed(self) -> bool:
        return self.status is not Binding.NOT_ASSESSED


def binding_status(raw_court: str | None, year: int | None,
                   jurisdiction: str = "Telangana") -> BindingRuling:
    """Binding status for an authority, against the matter's jurisdiction.

    Three outcomes, always. `NOT_ASSESSED` is returned wherever the inputs do
    not let the rule run -- an unknown court, a missing year, or a jurisdiction
    this product has not measured coverage for. It is never the case that a
    missing input produces `PERSUASIVE`, because "persuasive" is a finding and
    "I could not tell" is not.
    """
    court = normalise_court(raw_court)
    place = (jurisdiction or "").strip().lower()

    if court is Court.SUPREME_COURT:
        return BindingRuling(
            Binding.BINDING,
            "the Supreme Court binds every court in India (Constitution, Art. 141)",
            "art-141", court)

    if place not in ("telangana", "union of india", "india"):
        # The corpus is scoped to Telangana and the Union. An answer about
        # Kerala law out of it is confidently wrong and nothing downstream
        # catches that, so the rule refuses rather than generalising.
        return BindingRuling(
            Binding.NOT_ASSESSED,
            f"binding status for {jurisdiction!r} is outside the measured scope of "
            f"this corpus (Telangana and the Union of India)",
            "scope-1", court)

    if court is Court.HC_TELANGANA:
        return BindingRuling(
            Binding.BINDING, "the High Court for the State of Telangana",
            "hc-own", court)

    if court is Court.HC_ANDHRA_PRADESH:
        if year is None:
            return BindingRuling(
                Binding.NOT_ASSESSED,
                "an Andhra Pradesh High Court judgment with no year cannot be "
                "placed against the bifurcation of 1 January 2019",
                "bind-1", court)
        if year < BIFURCATION.year:
            return BindingRuling(
                Binding.BINDING,
                f"decided in {year}, before the bifurcation of "
                f"{BIFURCATION.isoformat()}: a decision of the predecessor High "
                f"Court binds its successor's territory",
                "bind-1", court)
        return BindingRuling(
            Binding.NOT_ASSESSED,
            f"decided in {year}, AFTER the bifurcation of {BIFURCATION.isoformat()}. "
            f"The standing decision that Andhra Pradesh judgments bind Telangana "
            f"was taken against a corpus holding NO post-2018 Andhra judgment, so "
            f"it does not reach this one. Check `bind-1` fails the build on ingest "
            f"of such a judgment; the decision is re-taken, not extended",
            "bind-1", court)

    if court is Court.HC_OTHER:
        return BindingRuling(
            Binding.PERSUASIVE,
            "a High Court of another State: persuasive, not binding",
            "hc-other", court)

    if court is Court.SUBORDINATE:
        return BindingRuling(
            Binding.PERSUASIVE,
            "a subordinate court or tribunal: persuasive at most",
            "subordinate", court)

    return BindingRuling(
        Binding.NOT_ASSESSED,
        f"the court {raw_court!r} could not be normalised, so binding status "
        f"cannot be computed. It is not assumed",
        "court-unknown", court)
