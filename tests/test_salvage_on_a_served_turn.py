"""D8 — salvage, REACHED. E-084 on a served turn.

*Treat a claim as a set of coordinates — party, cause, relief, forum, timing,
procedure, burden — and ask which coordinate can move. Almost every "you lose"
is the failure of one of them, not of the case.*

The measured original error was advice that a claim was dead where a different
framing on the same facts was available.

AND THE BOUND, WHICH IS THE HARDER HALF
-----------------------------------------
*Never manufacture a route. A system rewarded for always finding a way out
will invent one, and a hopeless alternative cause costs the client money and
the advocate credibility.*

Half the tests here are about the product REFUSING to help — which is the half
a feature like this fails at, because every incentive runs the other way.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import adversarial as adv
from nm.core.turn import TurnInput
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

HELD = ("Limitation Act, 1963 Article 19",)

#: THE FIXTURE RETRIEVES ARTICLE 65 — TWELVE YEARS, not three.
#:
#: This said 2019 and asserted the period had run, which is true under Article
#: 19's three years and false under the twelve the stub actually returns. The
#: test's own guard caught it: a brief chosen for the period the AUTHOR had in
#: mind rather than the one the turn computes proves nothing about salvage.
EXPIRED = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
           "supplied against invoices on 14 March 2010 and were never paid "
           "for.")


def _run(tmp_path, message=EXPIRED):
    engine, _ = build(tmp_path)
    return engine.run(TurnInput(advocate_id="adv_1", message=message,
                                today=date(2026, 9, 4)))


def _text(out):
    return " ".join(e.text for e in out.answer.elements)


# ============================== the bound =================================

def test_a_route_citing_nothing_retrieved_is_dropped_and_the_route_goes():
    """THE ROUTE GOES, THE VARIATION STAYS.

    What changes when a coordinate moves is still worth saying; what is not
    worth saying is a way out resting on nothing. `Salvage` refuses a route
    with no findings, so dropping the citation necessarily drops the route —
    that is the design, not a limitation of the reader.
    """
    read = adv.read_salvage({"failure_scope": "framing", "varied": [{
        "coordinate": "forum",
        "varied_result": "a commercial court has pecuniary jurisdiction",
        "route": "file in the commercial court",
        "strength": "arguable",
        "citations": ["a half-remembered Act"]}]}, HELD)

    (only,) = read.considered
    assert only.route == "", "a route rested on nothing retrieved"
    assert only.varied_result, "the variation was discarded with the route"
    assert read.refused and "citing nothing retrieved" in read.refused[0]


def test_a_route_with_no_strength_cannot_be_constructed():
    """*Never present a route NM would not itself run as though it would.* An
    unmarked route reads as a recommendation."""
    with pytest.raises(ValueError, match="carries no strength"):
        adv.Salvage(coordinate=adv.Coordinate.FORUM, varied_result="x",
                    route="file elsewhere", findings=("a ref",))


def test_a_route_with_no_citation_cannot_be_constructed():
    """*'Consider a different forum', with no forum named* is E-084's
    counterexample, and this is the type that refuses it."""
    with pytest.raises(ValueError, match="rests on nothing retrieved"):
        adv.Salvage(coordinate=adv.Coordinate.FORUM, varied_result="x",
                    route="file elsewhere", strength=adv.Strength.ARGUABLE)


def test_a_route_that_cites_what_was_actually_retrieved_survives():
    """The rule is not "no routes". A route grounded in retrieved text is the
    whole point of the feature."""
    read = adv.read_salvage({"failure_scope": "framing", "varied": [{
        "coordinate": "timing",
        "varied_result": "an acknowledgment restarts the period",
        "route": "sue on the restarted period",
        "strength": "would_run",
        "citations": list(HELD)}]}, HELD)
    (only,) = read.considered
    assert only.route and only.findings == HELD
    assert only.strength is adv.Strength.WOULD_RUN


# ==================== the coordinates nobody moved ========================

@pytest.mark.eval_id("E-084")
def test_the_population_is_the_seven_and_not_what_was_tried():
    """A report that varied two coordinates and concluded the case is dead has
    not done the work — and the two it DID vary make it look as though it
    had."""
    read = adv.read_salvage({"failure_scope": "framing", "varied": [
        {"coordinate": "timing", "varied_result": "a", "route": "",
         "strength": "not_assessed", "citations": []},
        {"coordinate": "forum", "varied_result": "b", "route": "",
         "strength": "not_assessed", "citations": []}]}, HELD)

    assert set(adv.unvaried(read.considered)) == {
        "party", "cause", "relief", "procedure", "burden"}


@pytest.mark.eval_id("E-084")
def test_a_coordinate_outside_the_seven_is_refused():
    read = adv.read_salvage({"failure_scope": "case", "varied": [{
        "coordinate": "vibes", "varied_result": "x", "route": "",
        "strength": "not_assessed", "citations": []}]}, HELD)
    assert read.considered == ()
    assert read.refused and "outside the seven" in read.refused[0]


# ============================== on the wire ===============================

@pytest.mark.eval_id("E-084")
def test_salvage_runs_where_the_claim_is_reported_as_failing(tmp_path):
    """The line the turn already prints ends *"that is not the end of the file
    — what else it offers is a separate question"*. This is what makes good on
    it."""
    text = _text(_run(tmp_path))
    assert "period has run" in text, (
        "the fixture no longer produces a failing claim, so this proves "
        "nothing:\n" + text[:400])
    assert "coordinates were not moved" in text or "timing:" in text, (
        "the claim was reported as failing and no coordinate was varied:\n"
        + text[:800])


@pytest.mark.eval_id("E-084")
def test_salvage_does_not_run_on_a_claim_that_is_fine(tmp_path):
    """Seven paragraphs of hypothetical restructuring attached to a healthy
    claim is the survey this product rejects."""
    # Well inside twelve years, so nothing is reported as failing.
    fine = ("We act for the plaintiff at Hyderabad. Goods were supplied "
            "against invoices on 14 March 2024 and were never paid for.")
    text = _text(_run(tmp_path, fine))
    assert "coordinates were not moved" not in text
    assert "We lose on THIS FRAMING" not in text


@pytest.mark.eval_id("E-084")
def test_we_lose_and_we_lose_on_this_framing_are_different_answers(tmp_path):
    """*Distinguish "we lose" from "we lose on this framing".* The measured
    original error was advice that a claim was dead where a different framing
    on the same facts was available — and the overwhelming majority of
    weak-case reports are the second."""
    assert "framing" in _text(_run(tmp_path)).lower()

    case = adv.read_salvage({"failure_scope": "case", "varied": []}, HELD)
    assert case.failure_scope is adv.FailureScope.CASE


def test_three_states_on_the_salvage_read():
    """`not_assessed` on a weak case must not read as "nothing could be
    done"."""
    assert adv.UNREAD_SALVAGE.state == "not_assessed"
    assert adv.salvage_not_assessed("the model was unavailable").state == \
        "not_assessed"
    assert adv.read_salvage({"failure_scope": "case", "varied": []},
                            HELD).state == "none_varied"


def test_a_variation_with_no_route_is_ordinary_and_not_a_failure():
    """`route=None` is a FIRST-CLASS OUTCOME and the common one. A reader that
    treated it as a failure would push the model toward inventing one."""
    read = adv.read_salvage({"failure_scope": "case", "varied": [{
        "coordinate": "cause",
        "varied_result": "no other cause is available on these facts",
        "route": "", "strength": "not_assessed", "citations": []}]}, HELD)
    assert len(read.considered) == 1
    assert read.refused == ()
