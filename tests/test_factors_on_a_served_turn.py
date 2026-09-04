"""B-073, THROUGH THE ENGINE — not through the module.

WHY A SEPARATE FILE FROM `test_factors.py`
--------------------------------------------
That file proves `nm/core/factors.py` is right. This proves the TURN reaches
it, retrieves the section, applies the factor, and puts a moved date in front
of the advocate.

Those are different claims and this project has paid for confusing them.
`limitation`, `thresholds` and `deadlines` were built, unit-tested,
mutation-covered and called by nothing — four defects (B-057 to B-060) sat in
the wiring, invisible to a green suite, until a turn was actually driven. Ten
more modules were found in the same state on 31 August 2026 (B-079). A module
with a perfect unit suite and no served path is the default failure here, not
the exotic one.

THE EVIDENCE STUB ANSWERS BY QUESTION, DELIBERATELY
-----------------------------------------------------
The shared `_Evidence` returns one result for every need. That is fine for
tests about one retrieval and useless here: the whole mechanism turns on the
turn making a SECOND, different fetch for s.18, and a stub that cannot tell
the two needs apart would pass whether or not that fetch happened.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.turn import TurnInput
from nm.domain.matter import Provenance
from nm.ports.evidence import Coverage, EvidenceResult
from tests.test_turn_contract import build, finding

pytestmark = pytest.mark.class_a

S18_SPAN = ("18. Effect of acknowledgment in writing.—(1) Where, before the "
            "expiration of the prescribed period for a suit, an acknowledgment "
            "of liability has been made in writing signed by the party against "
            "whom such right is claimed, a fresh period of limitation shall be "
            "computed from the time when the acknowledgment was so signed.")

ARTICLE_19 = ("For the price of goods sold and delivered where no fixed period "
              "of credit is agreed upon... three years.")

PROV = Provenance(kind="advocate_statement", turn="t1")


class _Corpus:
    """Answers the ARTICLE need and the SECTION need differently.

    A stub returning one result for both would satisfy this test while the
    turn made only one fetch — which is the wiring defect it exists to catch.
    """

    def __init__(self, *, serve_s18: bool = True):
        self.serve_s18 = serve_s18
        self.asked: list[str] = []

    def fetch(self, need):
        self.asked.append(need.question)
        if "section 18" in need.question:
            if not self.serve_s18:
                return EvidenceResult(coverage=Coverage.NOT_HELD,
                                      missing="Limitation Act section 18")
            return EvidenceResult(
                coverage=Coverage.ANSWERED,
                findings=(finding(proposition="Limitation Act, 1963 s.18",
                                  ref="Limitation Act, 1963 s.18",
                                  span=S18_SPAN,
                                  locator="the_limitation_act_1963::s_18"),),
                searched_stores=("the_limitation_act_1963",))
        if "section 19" in need.question:
            return EvidenceResult(coverage=Coverage.NOT_HELD,
                                  missing="Limitation Act section 19")
        return EvidenceResult(
            coverage=Coverage.ANSWERED,
            findings=(finding(proposition="Limitation Act, 1963 Article 19",
                              ref="Limitation Act, 1963 Article 19",
                              span=ARTICLE_19,
                              locator="the_limitation_act_1963::Article_19"),),
            searched_stores=("the_limitation_act_1963",))


BRIEF = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
         "supplied against invoices on 14 March 2023 and were never paid for. "
         "The defendant wrote to us on 12 June 2024 admitting the amount was "
         "outstanding.")


def _run(tmp_path, corpus):
    engine, store = build(tmp_path, evidence=corpus)
    return engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                                today=date(2026, 9, 4)))


def test_the_turn_asks_for_the_section_and_not_only_the_article(tmp_path):
    """THE SECOND FETCH HAPPENS. Everything below rests on it, and a test that
    only checked the final date would pass on a lucky arithmetic coincidence."""
    corpus = _Corpus()
    _run(tmp_path, corpus)
    assert any("section 18" in q for q in corpus.asked), (
        f"the turn never asked for s.18. It asked: {corpus.asked}")


def test_an_acknowledgment_moves_the_date_the_advocate_is_shown(tmp_path):
    """THE MEASURED DEFECT, END TO END.

    GS-14 served: the acknowledgment of 12 June 2024 was on the file, was
    repeated back, and never reached the arithmetic — the claim was reported
    dead at 2026-03-14 when it is alive to 2027-06-12.
    """
    out = _run(tmp_path, _Corpus())
    text = " ".join(e.text for e in out.answer.elements)
    assert "2027-06-12" in text or "2027" in text, (
        "the served answer does not carry the restarted date. The "
        "acknowledgment is on the chronology and the section was retrieved, "
        "so the period runs from 12 June 2024.\n\n" + text[:900])


def test_the_unretrieved_section_is_disclosed_and_never_silently_none(tmp_path):
    """WHEN s.18 IS NOT HELD, the advocate is told nothing was weighed against
    it — not shown a clean date computed as though nothing restarts.

    This is the branch that would rot silently: a corpus that stops serving
    s.18 would leave every answer looking exactly as correct as before.
    """
    out = _run(tmp_path, _Corpus(serve_s18=False))
    text = " ".join(e.text for e in out.answer.elements)
    assert "2027-06-12" not in text, (
        "a restart was applied with no section retrieved to support it")
    assert any(word in text.lower() for word in
               ("not been weighed", "not assessed", "not retrieved",
                "never weighed")), (
        "the answer computed a period without saying that nothing had been "
        "weighed against sections 18 or 19:\n\n" + text[:900])
