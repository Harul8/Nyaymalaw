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

import json
from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.core import cascade
from nm.core import evidence_item as inventory
from nm.core import gaps as gap_queue
from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from tests.test_turn_contract import _model_config, build

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

    # TIED TO THE MATRIX ROW, not only to the wording. G-CASCADE's
    # `visible` clause is the promise this asserts, and without the id
    # here nothing connects the two: the gate could be withdrawn, or its
    # response changed from `disclose`, and this test would stay green.
    # B-128 is what that gap becomes when it is left alone.
    assert "G-CASCADE" in {g.gate_id for g in second.metrics.gates_fired}, (
        "the advocate was told the value moved and the gate that owes "
        "them that did not fire -- the disclosure and the matrix disagree "
        "about whether it happened")
    assert [e for e in second.answer.elements
            if "has MOVED since the last turn" in e.text], (
        "G-CASCADE fired into the metrics and the answer's elements "
        "carry nothing")


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


# ============ the conservation invariant: nothing is silently lost =========

@pytest.mark.eval_id("E-092")
def test_a_derivation_that_stopped_being_computed_is_reported():
    """THE DIRECTION `changes` CANNOT SEE.

    `changes` walks `after` and asks what moved, so a value present BEFORE and
    absent now produces nothing from it — the function's own docstring reasons
    carefully about a value that appears and never about one that vanishes.
    Asked in that direction it cannot find forgetting, which is the one thing
    it is for.

    This matters most because nearly everything the product derives is
    re-derived from scratch by a model read every turn. A read that found
    three issues on turn 2 and nothing on turn 9 does not fail — it succeeds,
    quietly, with less, and nothing else in the build could tell.
    """
    before = (cascade.Derived(name="issues on th_1", value="3",
                              from_facts=("f1",)),
              cascade.Derived(name="limitation on th_1", value="2027-06-12",
                              from_facts=("f1",)))
    after = (cascade.Derived(name="limitation on th_1", value="2027-06-12",
                             from_facts=("f1",)),)

    assert cascade.changes(before, after) == (), (
        "if this ever reports something, the test below is measuring the "
        "wrong thing")
    (vanished,) = cascade.lost(before, after)
    assert vanished.name == "issues on th_1"
    assert vanished.value == "3", (
        "the prior value must survive: 'issues on th_1, which was 3' is "
        "actionable and '1 derivation lost' is not")


@pytest.mark.eval_id("E-092")
def test_nothing_lost_reports_nothing():
    """A guard on the guard. If this fired on every turn the advocate would
    learn to skip the line, and the real one would arrive in a place they had
    stopped reading."""
    same = (cascade.Derived(name="issues on th_1", value="3",
                            from_facts=("f1",)),)
    assert cascade.lost(same, same) == ()


@pytest.mark.eval_id("E-092")
def test_a_derivation_that_produced_nothing_records_no_row():
    """THE ABSENCE IS THE SIGNAL.

    Recording a row with a count of zero would make "this read found nothing
    this turn" look like an ordinary value that happens to be small, and
    `lost` would never see it.
    """
    from nm.core.turn import _record
    from nm.domain.matter import Thread

    thread = Thread.create(label="a thread")
    rows: list = []
    _record(rows, "issues", thread, ("f1",), 0)
    assert rows == []
    _record(rows, "issues", thread, ("f1",), 3)
    assert len(rows) == 1 and rows[0].value == "3"


@pytest.mark.eval_id("E-092")
def test_a_count_that_grew_is_not_announced_as_a_correction():
    """§5.4'S BOUND, WHICH THE PASSING RUN BROKE.

    GS-15 finally passed its spine on 5 September 2026 — and the cascade
    fired on all five turns. Evidence appeared on turn 2, the issues went 1 to
    2 on turn 4, the opponent's case changed on turn 5, each announced as "a
    value has MOVED" and each raising a blocking question about what needed
    undoing.

    A limitation date moving from 1987 to 2027 is a CORRECTION. An issue count
    moving from 1 to 2 is the file growing, which is what a conversation does.
    §5.4 says why the difference matters: a product that announces a cascade
    every turn trains the advocate to skip the section, and the real one then
    arrives in a place they have learned to ignore.
    """
    grew = (cascade.Derived(name="issues on th_1", value="1",
                            from_facts=("f1",), kind=cascade.Kind.MEASUREMENT),)
    more = (cascade.Derived(name="issues on th_1", value="2",
                            from_facts=("f1",), kind=cascade.Kind.MEASUREMENT),)
    assert cascade.changes(grew, more) == (), (
        "a count that grew was reported as a correction")


@pytest.mark.eval_id("E-092")
def test_a_position_that_moved_is_still_announced():
    """The bound must not silence the thing it bounds."""
    before = (cascade.Derived(name="limitation on th_1", value="1987-04-15",
                              from_facts=("f1",)),)
    after = (cascade.Derived(name="limitation on th_1", value="2027-04-15",
                             from_facts=("f1",)),)
    (moved,) = cascade.changes(before, after)
    assert moved.was == "1987-04-15" and moved.now == "2027-04-15"


@pytest.mark.eval_id("E-092")
def test_a_measurement_that_vanishes_is_still_reported_lost():
    """BOTH KINDS ARE WATCHED FOR LOSS. Quieting the growth of a count must
    not quiet its disappearance — that is the forgetting the whole mechanism
    exists to find, and it is the more dangerous direction."""
    had = (cascade.Derived(name="issues on th_1", value="3",
                           from_facts=("f1",), kind=cascade.Kind.MEASUREMENT),)
    assert cascade.lost(had, ()) == had


def test_an_unclassified_derivation_is_treated_as_a_position():
    """The safe direction. A value nobody classified is announced when it
    moves, rather than silently filed as accumulation."""
    assert cascade.Derived(name="x", value="1", from_facts=()).kind \
        is cascade.Kind.POSITION


# ================= BK-5 — held, not rendered ================================

def test_the_cascade_counts_what_the_thread_holds_not_what_the_turn_showed():
    """BK-5. MEASURED ON GS-14, 6 September 2026, turns 3 and 4:

        "This turn derived LESS than the last one. evidence on
         thr_787d62dd3826 was 2 and is not computed now."

    The inventory HELD two items. It RENDERED zero findings, because B-120
    made it render only what changed -- and the same answer said so one line
    down: "2 item(s) already on the file are unchanged and not repeated here."

    `_record` counted FINDING elements. It was written when rendering and
    holding were the same thing and B-120 separated them hours earlier, so the
    cascade was measuring the rendering and reporting it as the derivation.
    """
    import inspect

    from nm.core.turn import TurnEngine

    body = inspect.getsource(TurnEngine._derive)
    for what, held in (("issues", 'concluded.get("issues"'),
                       ("proof", 'concluded.get("proof"'),
                       ("evidence", 'concluded.get("evidence"'),
                       ("theory", 'concluded.get("theory"')):
        assert held in body, (
            f"the {what} derivation is not counted from what the thread "
            f"holds, so a turn that renders nothing new reports it lost")
    assert "if e.kind is ElementKind.FINDING))" not in body.split(
        "the opponent")[0], (
        "a derivation before the adversarial read still counts rendered "
        "elements")


def test_a_derivation_that_really_vanishes_is_still_reported():
    """THE BOUND, and it is the one that matters. Persistence does not remove
    the failure the cascade catches: a merge can return an empty list, and
    `proof.still_supported` can withdraw every position on the file.

    A fix that made the check quiet on a real loss would be worse than the
    false alarm it replaced -- the alarm was noise, and silence here is the
    forgetting this whole mechanism exists to find.
    """
    from nm.core import cascade

    before = (cascade.Derived(name="evidence on thr_1", shown="evidence",
                              value="2", from_facts=(),
                              kind=cascade.Kind.MEASUREMENT),)
    assert cascade.lost(before, ()) == before
    assert cascade.lost(before, before) == ()


class _Repeats(ScriptedModelAdapter):
    """Returns the SAME inventory every turn.

    The stock double finds a NEW item on each turn -- measured going 1, 2, 3,
    4 held with one finding rendered each time -- so it never produces the
    condition this is about: items HELD and nothing RENDERED. Driven, because
    a fixture that cannot reach the case is a fixture that tests the fixture.
    """

    ITEMS = {"items": [
        {"what": "the invoices", "holder": "client", "form": "original",
         "quoted": "invoices dated 14 March 2023", "already": ""},
        {"what": "the admission letter", "holder": "client",
         "form": "original", "quoted": "nothing was paid", "already": ""},
    ]}

    def structured(self, prompt, schema, tier, **kw):
        result = super().structured(prompt, schema, tier, **kw)
        if schema.get("x-nm-read") != "inventory":
            return result
        # THE IDS THE PROMPT SHOWS, so the second turn NAMES what is on the
        # file rather than describing it again -- which is what a real read
        # does once it is shown the standing list, and the only way the merge
        # can hold two items while the renderer emits none.
        rows = []
        for line in prompt.user.splitlines():
            if line.strip().startswith("evi_") and "\t" in line:
                ident, what = line.strip().split("\t", 1)
                rows.append({"what": what, "holder": "client",
                             "form": "original",
                             "quoted": "invoices dated 14 March 2023",
                             "already": ident})
        said = self.ITEMS if not rows else {"items": rows}
        return replace(result, data=said, text=json.dumps(said))


def test_an_unchanged_inventory_is_not_announced_as_a_loss(tmp_path):
    """BK-5 ON A SERVED TURN, driven.

    MEASURED ON GS-14, 6 September 2026, turns 3 and 4:

        "This turn derived LESS than the last one. evidence on
         thr_787d62dd3826 was 2 and is not computed now."

    The inventory HELD two items. It RENDERED zero findings, because B-120
    made it render only what changed -- and the same answer said so one line
    down: "2 item(s) already on the file are unchanged and not repeated here."

    `_record` counted FINDING elements. It was written when rendering and
    holding were the same thing, and B-120 separated them hours earlier.

    THE FIRST VERSION OF THIS TEST PASSED WITH THE DEFECT REVERTED, because
    the stock double finds a new item every turn and the condition never
    arose. That is the shape this file exists to refuse, arriving in a test
    written for it.
    """
    engine, store = build(tmp_path, model=_Repeats(
        _model_config(), responses={"__default__": "Issue the notice."}))

    first = engine.run(TurnInput(
        advocate_id="adv", today=date(2026, 8, 31),
        message=("we act for the plaintiff in a recovery matter. The goods "
                 "were supplied against invoices dated 14 March 2023 and "
                 "nothing was paid.")))
    second = engine.run(TurnInput(
        advocate_id="adv", matter_id=first.matter.id, today=date(2026, 8, 31),
        message="is the claim still in time"))

    held = inventory.from_stored(
        store.load(first.matter.id).threads[0].evidence)
    rendered = [e for e in second.answer.elements
                if e.kind is ElementKind.FINDING and " — held by " in e.text]
    assert len(held) >= 2, (
        f"the file holds {len(held)} item(s); this test needs the inventory "
        f"carried across a turn to be about anything")
    assert not rendered, (
        "the second turn re-rendered the inventory, so it is not exercising "
        "the case B-120 created")

    alarms = [e.text for e in second.answer.elements if "derived LESS" in e.text]
    assert not any("evidence" in a for a in alarms), (
        f"the evidence was held and not rendered, and the turn announced it "
        f"LOST: {alarms}. The count is coming from what the turn RENDERED "
        f"rather than from what the thread HOLDS.")
