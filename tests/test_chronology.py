"""C5, the date chart — and its three NEVER clauses, written with the feature.

WHY THESE EXIST BEFORE THE ENGINE WIRING
------------------------------------------
Seventeen NEVER clauses sat untested across five features in slices already
marked DONE, because tests were derived from the DOES half — the happy path —
and NEVER was treated as prose. Writing them afterwards found an anonymous
session able to open a matter within the hour.

So C5's refusals are written here, with the module, before anything calls it.

THE COUNTEREXAMPLE C5 RECORDS is two defects in one sentence: *a client who
said "yesterday" being asked for the date twice, and a chart completed by
guessing.* The first is the repeat-question failure the matter memory refuses.
The second is this file's subject, and it is the more expensive of the two: a
guessed date produces a limitation calculation the advocate acts on, and
nothing downstream can tell it from a computed one.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.chronology import (
    DateState,
    build_prompt,
    chart,
    conflicts,
    interpret,
)
from nm.domain.matter import Certainty, Fact, Provenance
from nm.domain.quotable import Quotable
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)


def _fact(statement: str, on: date | None = None, **kw) -> Fact:
    return Fact.create(
        statement=statement,
        provenance=Provenance(kind="advocate_statement", turn="t1"),
        date=on, **kw)


def _model_said(**kw) -> dict:
    base = {"event": "an event", "date_expression": "", "resolved": "",
            "documented": False}
    base.update(kw)
    return {"events": [base]}


# ============================================ C5.0 — never estimate ==========


@refuses("C5", 0)
@pytest.mark.eval_id("E-040")
def test_a_date_the_words_do_not_fix_is_recorded_as_undated():
    """C5: *Never estimate an undated event.*

    An undated event is an ordinary thing on a real file. Filling the gap
    produces arithmetic the advocate will rely on, and a chart with no holes in
    it reads as complete — so the hole is exactly what they need to see.
    """
    message = "the notice went some time last year and he never replied"

    # The model declines to fix a date. That is the ORDINARY answer.
    rows = interpret(Quotable(turn=message), TODAY, _model_said(
        event="the notice went", date_expression="some time last year",
        resolved=""))
    assert len(rows) == 1
    assert rows[0].state is DateState.UNDATED
    assert rows[0].on is None
    assert not rows[0].dated

    # And the event is STILL ON THE CHART. Dropping what could not be dated is
    # the same defect arriving as an absence instead of a wrong number.
    assert rows[0].event == "the notice went"


@refuses("C5", 0)
@pytest.mark.eval_id("E-040")
def test_a_date_read_from_words_the_advocate_never_wrote_is_refused():
    """THE SPAN GUARD, and it is the same one the posture read needed.

    A resolved date must come with the advocate's own words. Checked against
    what they WROTE, never against the prompt — the prompt carries the file and
    this product's own questions, and a span lifted from there would let the
    product date an event out of its own text (B-035).
    """
    message = "he was arrested and produced the next morning"

    rows = interpret(Quotable(turn=message), TODAY, _model_said(
        event="the arrest",
        date_expression="on 14 March 2026",   # nowhere in the message
        resolved="2026-03-14"))
    assert rows[0].state is DateState.UNDATED, (
        "a date was accepted from words the advocate never wrote")
    assert rows[0].on is None
    assert "not in what the advocate wrote" in rows[0].refused

    # A date is also refused when NO span supports it at all.
    bare = interpret(Quotable(turn=message), TODAY, _model_said(
        event="the arrest", date_expression="", resolved="2026-03-14"))
    assert bare[0].state is DateState.UNDATED
    assert "no words to support it" in bare[0].refused

    # THE POSITIVE CONTROL. The guard must not be a blanket refusal: a span the
    # advocate DID write resolves normally, or this test proves only that
    # nothing ever works.
    good = interpret(Quotable(turn="the cheque bounced on 3 March 2026"), TODAY, _model_said(
        event="the cheque bounced", date_expression="3 March 2026",
        resolved="2026-03-03"))
    assert good[0].dated and good[0].on == date(2026, 3, 3)


@refuses("C5", 0)
@pytest.mark.eval_id("E-040")
def test_a_resolved_date_names_what_it_was_counted_from():
    """"Yesterday" is meaningless without a reference, and a resolution that
    cannot say what it counted from is a guess with a date's confidence.

    `EvidenceNeed` refuses a query with no governing date for the same reason:
    a query built from a text string with no date silently degrades the whole
    design back to search-first, and nothing downstream notices.
    """
    rows = interpret(Quotable(turn="the quit notice was served yesterday"), TODAY, _model_said(
        event="the quit notice was served", date_expression="yesterday",
        resolved="2026-08-30"))
    assert rows[0].dated
    assert rows[0].reference == TODAY.isoformat(), (
        "the row does not record what 'yesterday' was counted from")
    assert rows[0].date_expression == "yesterday"

    # And the reference reaches the model, rather than being assumed by it.
    prompt = build_prompt(Quotable(turn="served yesterday"), TODAY)
    assert TODAY.isoformat() in prompt.user
    assert "NEVER ESTIMATE" in prompt.system


def test_a_malformed_date_is_undated_and_never_partially_parsed():
    """Lenient parsing is how an invented vocabulary once emptied a charge map.
    A date that will not parse is not a date."""
    for bad in ("2026-13-45", "next Tuesday", "15/04/2026", ""):
        rows = interpret(Quotable(turn="it happened then"), TODAY, _model_said(
            event="it happened", date_expression="then", resolved=bad))
        assert rows[0].state is DateState.UNDATED, f"{bad!r} was accepted"


# ============================================ C5.1 — never resolve silently ==


@refuses("C5", 1)
@pytest.mark.eval_id("E-040")
def test_two_dates_for_one_event_are_surfaced_and_both_kept():
    """C5: *Never resolve conflicting dates silently.* C1 says it twice over —
    never resolve a contradiction inside the account; KEEP BOTH.

    A conflict is not a data problem to tidy before the advocate sees it. It is
    frequently the most important thing on the file, because whichever date is
    right decides whether the claim is alive.
    """
    facts = (
        _fact("the sale deed was executed", date(2019, 4, 15)),
        _fact("the sale deed was executed", date(2019, 6, 2)),
    )
    found = conflicts(facts)
    assert len(found) == 1, "two dates for one event were not surfaced"
    c = found[0]
    assert {c.left, c.right} == {date(2019, 4, 15), date(2019, 6, 2)}
    assert c.left_fact != c.right_fact
    assert "kept both" in c.as_text()
    assert "not mine to pick" in c.as_text()

    # NOTHING IS RESOLVED. Both facts survive, with their own dates.
    assert facts[0].date == date(2019, 4, 15)
    assert facts[1].date == date(2019, 6, 2)


def test_the_same_event_on_the_same_date_is_not_a_conflict():
    """THE OTHER HALF OF FLAG CALIBRATION. A conflict detector that fires on
    agreement teaches the advocate to ignore it, and then it protects nothing."""
    facts = (_fact("the notice was served", date(2025, 1, 9)),
             _fact("the notice was served", date(2025, 1, 9)))
    assert conflicts(facts) == ()

    # And an undated account of the same event is not a conflict either — it is
    # simply less information, which is C5.0's whole subject.
    assert conflicts((_fact("the notice was served", date(2025, 1, 9)),
                      _fact("the notice was served"))) == ()


def test_different_events_on_different_dates_are_not_a_conflict():
    facts = (_fact("the cheque bounced", date(2026, 3, 3)),
             _fact("the statutory notice went", date(2026, 4, 15)))
    assert conflicts(facts) == ()


# ============================================ C5.2 — asserted stays asserted ==


@refuses("C5", 2)
@pytest.mark.eval_id("E-041")
def test_a_documented_date_and_an_asserted_one_are_not_the_same_thing():
    """C5: *Never let a computation resting on an asserted date present as
    settled.* It says so at the POINT OF THE CONCLUSION, not in a footnote.

    The distinction has to survive the read to be carried anywhere, so this is
    where it starts: what the advocate remembers is asserted, however
    confidently they say it.
    """
    documented = interpret(Quotable(turn="the notice is dated 15 April 2026"), TODAY,
                           _model_said(event="the notice",
                                       date_expression="15 April 2026",
                                       resolved="2026-04-15", documented=True))
    assert documented[0].certainty is Certainty.DOCUMENTED

    remembered = interpret(Quotable(turn="I think it went out on 15 April 2026"), TODAY,
                           _model_said(event="the notice",
                                       date_expression="15 April 2026",
                                       resolved="2026-04-15", documented=False))
    assert remembered[0].certainty is Certainty.ASSERTED, (
        "a recollection was recorded as documented. Every limitation position "
        "resting on it would then present as settled.")

    # AND AN UNDATED EVENT KEEPS ITS CERTAINTY TOO. Losing the label on the
    # rows that have no date is how it goes missing from the ones that do.
    undated = interpret(Quotable(turn="the deed was registered, I don't recall when"), TODAY,
                        _model_said(event="the deed was registered",
                                    resolved="", documented=True))
    assert undated[0].state is DateState.UNDATED
    assert undated[0].certainty is Certainty.DOCUMENTED


# ================================================= the chart itself ==========


def test_the_chart_is_ordered_and_keeps_what_it_could_not_date():
    """Dated first, in order; undated last, and PRESENT.

    A chart that silently omits what it could not date is the same defect as
    one that guesses — arriving as an absence rather than as a wrong number,
    and absence is the harder of the two to notice.
    """
    a = _fact("the agreement", date(2019, 4, 15))
    b = _fact("the notice", date(2026, 4, 15))
    c = _fact("a payment, date unknown")
    other = _fact("something on another thread", date(2020, 1, 1))

    rows = chart((other, b, c, a), (a.id, b.id, c.id))
    assert [f.id for f in rows] == [a.id, b.id, c.id], (
        "the chart is not ordered by date with the undated last")
    assert other.id not in {f.id for f in rows}, (
        "a fact from another thread reached this thread's chart — that is the "
        "wrong-merge defect arriving through the chronology")
    assert c in rows, "the undated event was dropped from the chart"


def test_an_empty_thread_has_an_empty_chart_and_not_an_error():
    assert chart((), ()) == ()
