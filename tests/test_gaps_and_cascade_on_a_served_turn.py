"""A3 — the gap queue and the correction cascade, REACHED. §5.1–5.4.

Both modules were complete and called by nothing (B-079). The queue ranked
gaps nobody produced; the cascade compared a `before` no turn recorded.

WHY THE CASCADE SAT UNWIRED LONGEST
-------------------------------------
`changes(before, after)` needs a BEFORE, and a turn only ever has an after. It
has to come from the PREVIOUS turn, so each turn now records what it derived
and the next reads it back through the transcript store.

Re-deriving the previous position from today's facts would not do: the matter
holds facts, not derivations, so it would be computed FROM the corrected fact
and would always agree with itself.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import cascade
from nm.core import gaps as gap_queue
from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

AT_RISK = ("We act for the plaintiff at Hyderabad. The original agreement is "
           "with the opponent brother. Goods were supplied against invoices "
           "on 14 March 2023 and were never paid for.")


def _text(out):
    return " ".join(e.text for e in out.answer.elements)


def _questions(out):
    return " ".join(e.text for e in out.answer.elements
                    if e.kind is ElementKind.QUESTION)


# ======================= §5.1–5.2: the queue, ranked =======================

@pytest.mark.eval_id("E-090")
def test_the_questions_come_out_of_the_queue_as_one_batched_ask(tmp_path):
    """*Serial single questions make the advocate do the scheduling.*

    Batching by thread is what lets them answer a dispute in one go instead of
    ping-ponging across five.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=AT_RISK,
                               today=date(2026, 9, 4)))
    asks = [e for e in out.answer.elements
            if e.kind is ElementKind.QUESTION and e.gate == "G-GAP"]
    assert len(asks) == 1, (
        f"expected ONE batched ask from the queue, got {len(asks)}")
    assert "preserv" in asks[0].text.lower()


@pytest.mark.eval_id("E-090")
def test_the_answer_closes_with_what_is_still_missing(tmp_path):
    """§5.2's closing line. It is what stops an assessment reading as more
    settled than it is — a recorded gap is a first-class output."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=AT_RISK,
                               today=date(2026, 9, 4)))
    assert "Still missing:" in _text(out)
    assert "needed for:" in _text(out), (
        "a gap listed without what it blocks is a curiosity")


@pytest.mark.eval_id("E-090")
def test_a_question_cannot_exist_without_the_gap_it_fills():
    """E-090's counterexample — *a question asked to keep the conversation
    moving* — is UNWRITABLE rather than caught. There is nowhere for such a
    question to get a `Gap` from."""
    with pytest.raises(TypeError):
        gap_queue.Question(text="so, how are we feeling about this?")


def test_a_gap_that_blocks_nothing_cannot_be_built():
    with pytest.raises(ValueError):
        gap_queue.Gap(what="something", blocks="   ", thread="th_1",
                      kind=gap_queue.GapKind.DEADLINE)


def test_a_gap_has_no_default_kind():
    """The kind IS the rank, so a default is a rank nobody chose. An
    unclassified blocking gate would queue below every deadline — precisely
    the burial this queue exists to prevent."""
    with pytest.raises(TypeError):
        gap_queue.Gap(what="something", blocks="an action", thread="th_1")


def test_the_ranking_is_the_prds_order():
    made = [gap_queue.Gap(what=k.value, blocks="an action", thread="th_1",
                          kind=k)
            for k in (gap_queue.GapKind.CONSEQUENCE,
                      gap_queue.GapKind.BLOCKING_GATE,
                      gap_queue.GapKind.INFORMATION_VALUE,
                      gap_queue.GapKind.DEADLINE)]
    assert [g.kind for g in gap_queue.rank(tuple(made))] == list(
        gap_queue.RANK)


def test_nothing_is_owed_when_nothing_is_blocked():
    """*There is no obligation to ask something in order to advance, because
    there is nothing to advance.* A queue that always yields something is the
    manufactured question with a data structure behind it."""
    assert gap_queue.leads(()) is None


# ============================ §5.3: not a rail =============================

@pytest.mark.eval_id("E-090")
def test_the_queues_preference_is_carried_and_not_obeyed():
    """*If the advocate asks about another thread, NM answers on that thread.*

    A build that passes its stages by railroading the advocate through them
    has failed, so `follows` returns the thread they asked about — always —
    and the queue's own preference alongside it.
    """
    elsewhere = gap_queue.Gap(what="a more urgent thing", blocks="an action",
                              thread="th_2",
                              kind=gap_queue.GapKind.BLOCKING_GATE)
    answer_on, preference = gap_queue.follows((elsewhere,), "th_1")
    assert answer_on == "th_1", "the queue redirected the advocate"
    assert preference is elsewhere, "the preference was dropped, not carried"


# ========================= §5.4: the cascade ===============================

@pytest.mark.eval_id("E-092")
def test_a_first_turn_reports_no_cascade(tmp_path):
    """Nothing has moved because there was nothing to move FROM — which is not
    the same as "re-derived and nothing changed", and saying the second would
    be a claim about a comparison nobody made."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=AT_RISK,
                               today=date(2026, 9, 4)))
    assert "has MOVED since the last turn" not in _text(out)


@pytest.mark.eval_id("E-092")
def test_a_corrected_date_moves_the_value_and_says_what_it_was(tmp_path):
    """THE TRIGGER, END TO END.

    Turn one supplies goods in 2023; turn two corrects it to 2019. The
    limitation date must move, and the advocate must be told WITH THE PRIOR —
    a number they cannot reconcile against what they remember reads as though
    they misread it the first time.
    """
    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", message=AT_RISK,
                                 today=date(2026, 9, 4)))
    second = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id,
        message=("Correction: the goods were supplied on 14 March 2019, not "
                 "2023. What now?"),
        today=date(2026, 9, 4)))

    text = _text(second)
    assert "has MOVED since the last turn" in text, (
        "a corrected date did not re-derive anything:\n" + text[:900])
    assert "was " in text, "the change was reported without its prior value"


@pytest.mark.eval_id("E-092")
def test_a_change_reported_without_its_prior_cannot_be_built():
    with pytest.raises((ValueError, TypeError)):
        cascade.Change(name="limitation", now="2027-01-01")


@pytest.mark.eval_id("E-092")
def test_a_value_that_appears_is_a_change_with_no_prior():
    """*Silently adding a limitation date is the same defect as silently
    moving one.*"""
    (only,) = cascade.changes(
        (), (cascade.Derived(name="limitation", value="2027-01-01",
                             from_facts=("f1",)),))
    assert only.was == "not computed before"


@pytest.mark.eval_id("E-092")
def test_nothing_moving_is_one_line_and_not_a_section():
    """§5.4's bound. A product that announced a cascade every turn would train
    the advocate to skip the section, and the real one would arrive in a place
    they had learned to ignore."""
    assert cascade.report(()) == (
        "Re-derived everything that rested on the corrected fact; "
        "nothing changed.",)


@pytest.mark.eval_id("E-092")
def test_an_unanswered_undo_becomes_a_blocking_gap(tmp_path):
    """*Where earlier advice is affected, that is said in terms, INCLUDING
    whether anything already done needs undoing.*

    Empty `undo` is not "nothing needs undoing" — it is a question nobody
    answered, and it outranks everything else in the queue: an advocate who
    filed on Tuesday against a date that moved on Thursday needs telling.
    """
    moved = (cascade.Change(name="limitation on th_1", was="2026-03-14",
                            now="2022-03-14"),)
    assert cascade.unresolved_undo(moved) == ("limitation on th_1",)

    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", message=AT_RISK,
                                 today=date(2026, 9, 4)))
    second = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id,
        message="Correction: the goods were supplied on 14 March 2019.",
        today=date(2026, 9, 4)))
    assert "needs undoing" in _questions(second), (
        "a moved value left no question about what had already been done:\n"
        + _questions(second)[:600])


@pytest.mark.eval_id("E-092")
def test_advice_that_rested_on_a_moved_value_is_named():
    """An advocate who acted on it needs to be told. Showing them a corrected
    number is not telling them."""
    moved = (cascade.Change(name="limitation on th_1", was="a", now="b"),)
    prior = (cascade.PriorAdvice(what="file the recovery suit this week",
                                 given_at_turn="turn_1",
                                 rested_on=("limitation on th_1",)),)
    (at_risk,) = cascade.advice_at_risk(prior, moved)
    assert at_risk.what.startswith("file the recovery suit")
    assert any("superseded" in line for line in cascade.report(moved, (at_risk,)))
