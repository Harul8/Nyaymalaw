"""B-086 — a correction replaces the fact it corrects. GS-15's spine.

THE MEASURED DEFECT
--------------------
GS-15, served, 4 September 2026. The advocate said the agreement is dated
15-4-1984, then *"sorry, that is wrong. It is dated 15-4-2024"* — and BOTH
dates sat on the chronology as separate events. The limitation runs from the
earliest dated fact, so turn 5 reported a period that expired on 1987-04-15
for an agreement the advocate had corrected to 2024.

Every citation on that turn was verbatim and correct. The arithmetic was
correct. The answer was about a date the advocate had withdrawn.

`Fact.superseded_by` had existed since slice 1 and nothing ever set it — the
same shape as B-073, and the second time that shape has cost a whole scenario.

NOTHING IS DELETED
-------------------
The superseded fact stays on the matter and on the thread's chronology. It
leaves the CHART, which is the one place the arithmetic reads. §5.4 needs the
prior value to still exist so a change can be reported with what it was
before, and an advocate needs to see what they said as well as what replaced
it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.core import chronology, correction
from nm.core.turn import TurnInput
from nm.domain.matter import Fact, Provenance
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

PROV = Provenance(kind="advocate_statement", turn="t1")


def _fact(fid, statement, on=None):
    return Fact(id=fid, statement=statement, provenance=PROV, date=on)


OLD = _fact("f1", "the agreement is dated 15-4-1984", date(1984, 4, 15))
NEW = _fact("f2", "It is dated 15-4-2024", date(2024, 4, 15))


# ========================= the chart, which is the fix =====================

def test_a_superseded_fact_leaves_the_chart():
    """THE ONE PLACE THE ARITHMETIC STOPS READING IT.

    One place on purpose: the limitation, the coverage record, the
    adverse-fact read and the theory all take their facts from `chart`, so a
    correction applied in four places is one that will be applied in three of
    them next month.
    """
    superseded = replace(OLD, superseded_by="f2")
    got = chronology.chart((superseded, NEW), ("f1", "f2"))
    assert [f.id for f in got] == ["f2"]


def test_the_superseded_fact_is_still_on_the_file():
    """Marked, not removed. An advocate needs to see what they said as well as
    what replaced it, and §5.4 needs the prior value to report a change WITH
    what it was before."""
    superseded = replace(OLD, superseded_by="f2")
    assert superseded.date == date(1984, 4, 15)
    assert superseded.statement == OLD.statement


def test_the_chart_is_unchanged_where_nothing_was_superseded():
    """A guard on the fix: if this filtered anything else, every chart in the
    product would quietly lose entries."""
    assert [f.id for f in chronology.chart((OLD, NEW), ("f1", "f2"))] == \
        ["f1", "f2"]


# ============================ what may be paired ===========================

def test_a_correction_pairs_an_earlier_entry_with_one_from_this_turn():
    read = correction.read(
        {"corrections": [{"supersedes": "f1", "replaced_by": "f2",
                          "why": "the advocate says the date was wrong"}]},
        existing=(OLD,), added=(NEW,))
    assert read.state == "corrected"
    (c,) = read.corrections
    assert (c.supersedes, c.replaced_by) == ("f1", "f2")


def test_an_entry_the_file_does_not_hold_cannot_be_superseded():
    read = correction.read(
        {"corrections": [{"supersedes": "f_nowhere", "replaced_by": "f2",
                          "why": "x"}]}, existing=(OLD,), added=(NEW,))
    assert read.corrections == ()
    assert "not on this file" in read.refused[0]


def test_a_correction_must_come_from_this_turn():
    """Pairing two entries that were BOTH already on the file is a re-reading
    of history, not a correction — and the advocate said nothing to license
    it."""
    other = _fact("f3", "an unrelated earlier event", date(2000, 1, 1))
    read = correction.read(
        {"corrections": [{"supersedes": "f1", "replaced_by": "f3",
                          "why": "x"}]}, existing=(OLD, other), added=(NEW,))
    assert read.corrections == ()
    assert "not a correction" in read.refused[0]


def test_an_entry_cannot_supersede_itself():
    read = correction.read(
        {"corrections": [{"supersedes": "f2", "replaced_by": "f2",
                          "why": "x"}]}, existing=(NEW,), added=(NEW,))
    assert read.corrections == ()


def test_an_already_superseded_entry_is_not_superseded_twice():
    already = replace(OLD, superseded_by="f9")
    read = correction.read(
        {"corrections": [{"supersedes": "f1", "replaced_by": "f2",
                          "why": "x"}]}, existing=(already,), added=(NEW,))
    assert read.corrections == ()
    assert "already superseded" in read.refused[0]


def test_nothing_corrected_is_a_different_state_from_nothing_read():
    assert correction.read({"corrections": []}, (OLD,), (NEW,)).state == \
        "none_found"
    assert correction.UNREAD.state == "not_assessed"


# ============================== on the wire ================================

def test_a_corrected_date_replaces_the_old_one_on_a_served_turn(tmp_path):
    """GS-15'S SPINE, END TO END.

    Two turns: a date, then a correction of it. The chart must hold ONE dated
    agreement afterwards, and it must be the corrected one.
    """
    engine, store = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv_1", today=date(2026, 9, 5),
        message=("We act for the plaintiff on an agreement of sale at "
                 "Hyderabad. The agreement is dated 15 April 1984.")))
    engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id, today=date(2026, 9, 5),
        message="sorry, that is wrong. It is dated 15 April 2024."))

    matter = store.load(first.matter.id)
    thread = matter.threads[0]
    chart = chronology.chart(matter.facts, thread.chronology)
    years = {f.date.year for f in chart if f.date}

    assert 1984 not in years, (
        f"the withdrawn date is still on the chart: "
        f"{[(f.id, f.date, f.statement[:40]) for f in chart if f.date]}")
    assert 2024 in years, "the corrected date never reached the chart"

    # AND IT IS STILL ON THE FILE, marked rather than deleted.
    superseded = [f for f in matter.facts if f.superseded_by is not None]
    assert superseded, "nothing was marked superseded; it was just dropped"
    assert superseded[0].date.year == 1984
