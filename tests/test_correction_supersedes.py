"""B-086 / B-088 — a correction replaces the fact it corrects. GS-15's spine.

THE MEASURED DEFECT
--------------------
GS-15, served, 4 September 2026. The advocate said the agreement is dated
15-4-1984, then *"sorry, that is wrong. It is dated 15-4-2024"* — and BOTH
dates sat on the chronology. The limitation runs from the earliest dated fact,
so the answer reported a period that expired on 1987-04-15 for an agreement
the advocate had corrected to 2024.

Every citation on that turn was verbatim. The arithmetic was correct. The
answer was about a date the advocate had withdrawn.

WHY IT WAS FRAGILE, AND IT WAS THE DESIGN
-------------------------------------------
The first fix made "is this a correction?" a SECOND read. That read had to
reconstruct, from two fact ids, a relationship the FIRST read already knew:
the 2024 date was extracted from *"sorry, that is wrong. It is dated
15-4-2024"*, and that sentence was in front of the date reader when it produced
the event. Splitting them threw the evidence away and asked a harder question
without it — and on one run of GS-15 the second read returned nothing (B-088).

One read now. The read that creates the fact says what it replaces.

TWO LAYERS, AND ONLY ONE OF THEM IS A MODEL
---------------------------------------------
1. `corrects` on the date row, guarded: an id the file does not hold is
   dropped, an entry already superseded is not superseded twice.
2. THE SAFETY NET, which holds when every read fails: the limitation names the
   dated entry it ran from AND the ones it did not. An advocate who corrected
   a date sees their correction in the "not used" list.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.core import chronology
from nm.core.turn import TurnInput
from nm.domain.matter import Fact, Provenance
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

PROV = Provenance(kind="advocate_statement", turn="t1")


def _fact(fid, statement, on=None):
    return Fact(id=fid, statement=statement, provenance=PROV, date=on)


OLD = _fact("f1", "the agreement is dated 15-4-1984", date(1984, 4, 15))
NEW = _fact("f2", "It is dated 15-4-2024", date(2024, 4, 15))

MSG = "sorry, that is wrong. It is dated 15-4-2024"


def _row(**kw):
    base = {"event": "It is dated", "date_expression": "15-4-2024",
            "resolved": "2024-04-15", "documented": False, "corrects": ""}
    return {"events": [{**base, **kw}]}


# ===================== the read that creates the fact ======================

def test_the_date_row_says_what_it_replaces():
    """One read. The sentence that identifies a correction is the same
    sentence the date was read out of."""
    (row,) = chronology.interpret(MSG, date(2026, 9, 5), _row(corrects="f1"),
                                  known=frozenset({"f1"}))
    assert row.corrects == "f1"
    assert row.dated


def test_an_id_the_file_does_not_hold_is_dropped():
    """A correction pointing at nothing would supersede nothing and read as
    one that had — the silent direction."""
    (row,) = chronology.interpret(MSG, date(2026, 9, 5),
                                  _row(corrects="f_nowhere"),
                                  known=frozenset({"f1"}))
    assert row.corrects == ""


def test_an_ordinary_event_corrects_nothing():
    """Empty is the ordinary answer. A new event on a different day is not a
    correction, and treating it as one would erase a real part of the
    chronology."""
    (row,) = chronology.interpret(MSG, date(2026, 9, 5), _row(),
                                  known=frozenset({"f1"}))
    assert row.corrects == ""


def test_the_prompt_carries_the_ids_there_are_to_name():
    """Without them `corrects` cannot be filled and the read degrades to what
    it was before this change."""
    prompt = chronology.build_prompt(MSG, date(2026, 9, 5), "", (OLD,))
    assert "f1" in prompt.user
    assert "corrects" in prompt.user


# ========================= the chart, which is the fix =====================

def test_a_superseded_fact_leaves_the_chart():
    """THE ONE PLACE THE ARITHMETIC STOPS READING IT.

    One place on purpose: the limitation, the coverage record, the
    adverse-fact read and the theory all take their facts from `chart`, so a
    correction applied in four places is one that will be applied in three of
    them next month.
    """
    superseded = replace(OLD, superseded_by="f2")
    assert [f.id for f in chronology.chart((superseded, NEW), ("f1", "f2"))] \
        == ["f2"]


def test_the_superseded_fact_is_still_on_the_file():
    """Marked, not removed. §5.4 needs the prior value to report a change WITH
    what it was before, and an advocate needs to see what they said."""
    superseded = replace(OLD, superseded_by="f2")
    assert superseded.date == date(1984, 4, 15)
    assert superseded.statement == OLD.statement


def test_the_chart_is_unchanged_where_nothing_was_superseded():
    """A guard on the fix: if this filtered anything else, every chart in the
    product would quietly lose entries."""
    assert [f.id for f in chronology.chart((OLD, NEW), ("f1", "f2"))] == \
        ["f1", "f2"]


# ===================== a fact id names exactly one fact ====================

def test_adding_a_fact_that_is_already_on_the_file_is_refused():
    """A matter holding two facts with one id is a matter where every lookup
    is ambiguous and the FIRST wins by accident of order.

    It happened: marking a fact superseded went through `with_fact`, appended
    a second copy, and `chart` kept the un-superseded one — the fix defeated
    by its own write.
    """
    from nm.domain.matter import Matter

    m = Matter.create(advocate_id="adv_1", title="t").with_fact(OLD)
    with pytest.raises(ValueError, match="already on this matter"):
        m.with_fact(OLD)


def test_amending_replaces_in_place():
    """Position is kept, or an advocate reading their own chronology would
    find it had rearranged itself when something was corrected."""
    from nm.domain.matter import Matter

    m = (Matter.create(advocate_id="adv_1", title="t")
         .with_fact(OLD).with_fact(NEW))
    amended = m.amending(replace(OLD, superseded_by="f2"))
    assert [f.id for f in amended.facts] == ["f1", "f2"]
    assert amended.facts[0].superseded_by == "f2"


def test_amending_a_fact_the_matter_does_not_hold_is_refused():
    from nm.domain.matter import Matter

    with pytest.raises(ValueError, match="nothing.*to amend"):
        Matter.create(advocate_id="adv_1", title="t").amending(OLD)


# ============================== on the wire ================================

def test_a_corrected_date_replaces_the_old_one_on_a_served_turn(tmp_path):
    """GS-15'S SPINE, END TO END."""
    engine, store = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv_1", today=date(2026, 9, 5),
        message=("We act for the plaintiff on an agreement of sale at "
                 "Hyderabad. The agreement is dated 15 April 1984.")))
    engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id, today=date(2026, 9, 5),
        message="sorry, that is wrong. It is dated 15 April 2024."))

    matter = store.load(first.matter.id)
    chart = chronology.chart(matter.facts, matter.threads[0].chronology)
    years = {f.date.year for f in chart if f.date}

    assert 1984 not in years, (
        f"the withdrawn date is still on the chart: "
        f"{[(f.id, f.date) for f in chart if f.date]}")
    assert 2024 in years, "the corrected date never reached the chart"

    superseded = [f for f in matter.facts if f.superseded_by is not None]
    assert superseded, "nothing was marked superseded; it was just dropped"
    assert superseded[0].date.year == 1984


def test_the_limitation_names_the_entries_it_did_not_run_from(tmp_path):
    """THE SAFETY NET, and it does not depend on any read succeeding.

    The accrual is the earliest dated entry — right on most files and an
    arbitrary tiebreak on a file that holds two dates for one event. Naming
    the alternatives costs a clause and makes a wrong choice visible on the
    face of the answer, whatever the model did.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=date(2026, 9, 5),
        message=("We act for the plaintiff at Hyderabad. Goods were supplied "
                 "on 14 March 2019 and a demand notice went on 2 May 2021.")))

    text = " ".join(e.text for e in out.answer.elements)
    assert "not from:" in text, (
        "the answer did not say which dated entries the period was NOT "
        "computed from:\n" + text[:700])
    assert "say which" in text, (
        "the advocate is shown the alternatives and not told they can choose")
