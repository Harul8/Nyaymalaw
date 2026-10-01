"""Each dispute is searched by its own sentences, never by the background it shares.

LB-76 change 3 (owner, 30 September 2026). On the Farah Begum brief every
dispute's words began with the shared background -- "We act for Farah Begum as a
prospective claimant. No suit or criminal proceeding has yet been filed." -- and
the judgment search for a boundary wall looked for "prospective, claimant, suit,
criminal, proceeding, filed, owns, house". The background is still charted on every
dispute; it is only left out of what each dispute is SEARCHED by.
"""
from __future__ import annotations

import pytest

from nm.Archives.legal_brain.orchestrate import turn as turn_module
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.understand.threading import SourceAllocation
from tests.test_every_dispute_is_cleanly_identified import _Model, listed
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

BRIEF = ("We act for Asha Rao as a prospective claimant. No suit has been filed.\n\n"
         "First, her neighbour Mohan built a wall across her boundary strip on "
         "3 September 2026.\n\n"
         "Second, a buyer, Kiran, has not paid Rs 5 lakh for goods delivered in March "
         "2026.")


def test_a_disputes_own_words_leave_out_what_every_dispute_shares():
    spans = ("We act for Asha Rao.", "Mohan built a wall.")
    assert turn_module._own_words(spans, ("We act for Asha Rao.",)) == "Mohan built a wall."
    assert turn_module._own_words(spans, ()) == "We act for Asha Rao.\nMohan built a wall."
    assert turn_module._own_words(("We act for Asha Rao.",), ("We act for Asha Rao.",)) == ""


def test_identical_background_words_do_not_remove_the_disputes_own_occurrence():
    sentence = "The eastern gate is locked."
    sources = (SourceAllocation("S1", sentence, "turn_1"),
               SourceAllocation("S2", sentence, "turn_1"))
    assert turn_module._own_words((sentence,), (sentence,), sources=sources,
                                  shared_unit_ids=("S1",)) == sentence


def test_the_served_turn_searches_an_own_sentence_identical_to_background(tmp_path):
    text = ("We act for Asha Rao. The eastern gate was locked. "
            "The eastern gate was locked.")
    reading = listed(text, [("", "the eastern gate", "use_or_access", [])],
                     client="Asha Rao")
    reading["disputes"][0]["sentences"] = ["S3"]
    reading["background"] = ["S1", "S2"]
    engine, _ = build(tmp_path, model=_Model(reading))
    asked = []
    fetch = engine._fetch

    def recording(need, *args, **kwargs):
        asked.append(need.question)
        return fetch(need, *args, **kwargs)

    engine._fetch = recording
    out = engine.run(TurnInput(advocate_id="adv", message=text))
    assert len(out.matter.threads) == 1
    assert asked and any("eastern gate" in q for q in asked)
    assert all("We act for Asha Rao" not in q for q in asked), (
        "an identical shared sentence emptied the own search and used the whole brief")


def test_every_dispute_is_searched_without_the_shared_background(tmp_path):
    reading = listed(BRIEF, [
        ("Mohan", "the boundary strip", "possession_of_property", ["First,"]),
        ("Kiran", "the price of goods", "money_owed", ["Second,"])],
        background=["We act", "No suit"], client="Asha Rao")
    engine, _ = build(tmp_path, model=_Model(reading))
    asked = []
    fetch = engine._fetch

    def recording(need, *args, **kwargs):
        asked.append(need.question)
        return fetch(need, *args, **kwargs)

    engine._fetch = recording
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert len(out.matter.threads) == 2
    assert any("wall" in q for q in asked), "the dispute in focus was not searched"
    for question in asked:
        assert "prospective claimant" not in question and "No suit" not in question, (
            f"a dispute was searched by the background every dispute shares: {question!r}")
    # The background is still charted on each dispute: only the search leaves it out.
    facts = {f.id: f.statement for f in out.matter.facts}
    for thread in out.matter.threads:
        assert any("We act for Asha Rao" in facts[i] for i in thread.chronology)
