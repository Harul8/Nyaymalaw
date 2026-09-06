"""B-107 — a sentence recorded twice, once by each of two paths.

THE MEASURED DEFECT
---------------------
GS-15's second served run, 5 September 2026. Eight facts on a five-turn
matter, and two of the duplications were visible in the cause read's own
prompt bytes:

    "the agreement is dated 15-4-1984"        undated AND dated, one turn
    "Corrected: the agreement is dated 15-4-2024"   TWICE, same date

Two paths create facts from one turn and neither knew about the other. The
account is recorded WHOLE before anything is clarified — that is C1 and it
stays — and the date read then produces a dated fact from the same sentence.
`Matter.with_fact` refused a duplicate ID and nothing refused duplicate
CONTENT.

IT COST THREE WAYS. The account budget paid for the same words twice; the
model read a file that looked like it said something twice; and the limitation
read a chronology with two entries where the advocate described one event.

WHAT THE FIX IS NOT
---------------------
It is not "refuse the second copy", because the right outcome is better than
refusal. A dated reading of a sentence already on the file is THE SAME FACT,
NOW DATED — so the held one is amended and the advocate sees one entry
carrying its date, instead of two entries carrying half the information each.

THE CASE THAT MUST NOT BE COLLAPSED is the same statement with a DIFFERENT
date. That is a date conflict, `chronology.conflicts` exists to surface it,
and resolving it here would be the silent resolution C5 forbids. It has its
own test below, and it is the one that makes this fix safe rather than merely
tidy.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.domain.matter import (
    Certainty,
    Fact,
    Matter,
    Provenance,
)

pytestmark = pytest.mark.class_a

TURN = "turn_1"
LATER = "turn_2"
SENTENCE = "the agreement is dated 15-4-1984"


def _matter() -> Matter:
    return Matter.create(advocate_id="adv_1", title="t")


def _fact(statement=SENTENCE, *, turn=TURN, on=None, span=None):
    return Fact.create(
        statement=statement,
        provenance=Provenance(kind="advocate_statement", turn=turn, span=span),
        certainty=Certainty.ASSERTED, date=on)


# ============================== the four cases ==============================

def test_a_dated_reading_of_the_account_sentence_amends_it():
    """THE DEFECT, AS A RULE. One sentence, one fact — and it ends up DATED,
    which neither of the two facts was on its own."""
    m, account = _matter().recording(_fact())
    m, held = m.recording(_fact(on=date(1984, 4, 15), span="15-4-1984"))

    assert len(m.facts) == 1, (
        f"one sentence became {len(m.facts)} facts. GS-15 left 8 on a 5-turn "
        f"matter this way")
    assert held.id == account.id, (
        "the caller was handed a fact that is not the one on the file, so "
        "the chronology would carry an id nothing can look up")
    assert m.facts[0].date == date(1984, 4, 15)
    assert m.facts[0].provenance.span == "15-4-1984", (
        "the words the date was read from were dropped, so nothing can walk "
        "the date back to what the advocate wrote")


def test_the_statement_is_untouched_by_the_amendment():
    """C1 TAKES THE ACCOUNT WHOLE. The date read is authoritative about dates
    and about nothing else — a fix that let it rewrite the advocate's sentence
    would be a worse defect than the one it closes."""
    m, _ = _matter().recording(_fact())
    m, _ = m.recording(_fact(statement=SENTENCE, on=date(1984, 4, 15)))
    assert m.facts[0].statement == SENTENCE


def test_the_identical_fact_twice_is_recorded_once():
    """The second duplication GS-15 showed: same statement, same date."""
    m, first = _matter().recording(_fact(on=date(2024, 4, 15)))
    m, again = m.recording(_fact(on=date(2024, 4, 15)))
    assert len(m.facts) == 1
    assert again.id == first.id


def test_two_dates_for_one_sentence_are_both_kept():
    """THE BOUND, and the reason this fix is safe.

    A sentence held with two different dates is a CONFLICT. Collapsing it here
    would resolve it silently and pick a date by arrival order — the failure
    `chronology.conflicts` was written to prevent, arriving one layer below
    where it looks for it.
    """
    from nm.core import chronology

    m, _ = _matter().recording(_fact(on=date(1984, 4, 15)))
    m, _ = m.recording(_fact(on=date(2024, 4, 15)))
    assert len(m.facts) == 2, "a date conflict was resolved by deduplication"
    assert len(chronology.conflicts(m.facts)) == 1, (
        "both dates are on the file and the conflict is no longer visible")


def test_an_undated_repeat_of_a_dated_fact_adds_nothing():
    m, first = _matter().recording(_fact(on=date(1984, 4, 15)))
    m, again = m.recording(_fact())
    assert len(m.facts) == 1
    assert again.id == first.id
    assert m.facts[0].date == date(1984, 4, 15), (
        "an undated repeat erased the date that was already established")


# ============================== the scoping =================================

def test_the_same_sentence_on_a_later_turn_is_a_new_fact():
    """SAME TURN ONLY. The defect is two extractions of ONE sentence, and that
    is what a turn is. An advocate who says the same thing again on turn 4 has
    said it again — and where they say it with a different date, that is the
    conflict path above, which only works if both are on the file."""
    m, _ = _matter().recording(_fact())
    m, _ = m.recording(_fact(turn=LATER))
    assert len(m.facts) == 2


def test_a_superseded_fact_does_not_absorb_a_new_reading():
    """It has left the chart. Amending it would put a date on a record the
    advocate has withdrawn, and `chart` would then not show the date at all —
    the correction applied and having no effect, which is B-086 exactly."""
    from dataclasses import replace

    m, first = _matter().recording(_fact())
    m = m.amending(replace(first, superseded_by="fact_whatever"))
    m, fresh = m.recording(_fact(on=date(2024, 4, 15)))

    assert len(m.facts) == 2
    assert fresh.id != first.id
    assert m.fact(first.id).date is None


def test_a_different_sentence_is_a_different_fact():
    """THE OTHER BOUND. A rule that merged everything would pass every test
    above and lose the file."""
    m, _ = _matter().recording(_fact())
    m, _ = m.recording(_fact(statement="the notice was served on 2-1-2020"))
    assert len(m.facts) == 2


def test_typography_does_not_make_a_second_fact():
    """The one fold, applied here. `15-4-1984` and `15/4/1984` are the same
    date written by two readers of the same sentence."""
    m, _ = _matter().recording(_fact(statement="The agreement is dated 15-4-1984."))
    m, _ = m.recording(_fact(statement="the agreement is dated 15/4/1984",
                             on=date(1984, 4, 15)))
    assert len(m.facts) == 1


# =========================== nobody can bypass it ===========================

def test_with_fact_goes_through_the_same_rule():
    """WHAT REFUSES THE SECOND COPY (CLAUDE.md §4). `with_fact` is the older
    door and every existing caller uses it; if it kept its own append, the
    rule would hold only for callers who knew to use the new one."""
    m = _matter().with_fact(_fact()).with_fact(_fact(on=date(1984, 4, 15)))
    assert len(m.facts) == 1
    assert m.facts[0].date == date(1984, 4, 15)


def test_a_duplicate_id_is_still_refused():
    """B-086's guard, unchanged. A matter holding two facts with one id is a
    matter where every lookup wins by accident of order."""
    f = _fact()
    m = _matter().with_fact(f)
    with pytest.raises(ValueError, match="already on this matter"):
        m.with_fact(f)


def test_a_blank_statement_cannot_match_everything():
    """`fold("")` is `""`, and an equality test on it would match every other
    blank — so the empty key must not be a key at all. `Fact` refuses a blank
    statement outright, which is where this is actually enforced; asserted
    here because the fold made a new way for it to matter."""
    with pytest.raises(ValueError):
        _fact(statement="   ")
