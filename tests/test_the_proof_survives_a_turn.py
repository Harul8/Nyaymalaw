"""A proof position does not vanish because a read forgot to mention it.

THE MEASURED DEFECT
---------------------
Driven, 6 September 2026, because a live read cannot be made to forget on
demand — the same way the issue flicker had to be reproduced:

    turn 1  held          ('we hold the original',)
    turn 2  held          ('we hold the original',)
    turn 3  NOT_ASSESSED  ()          <- the read did not mention it
    turn 4  held          ('we hold the original',)

The material never moved. An advocate told on turn 2 that an element is
established, and on turn 3 that nobody worked it out, is watching the product
lose its place — and it is the issue count going 1, 1, 1, 0, 2 with a
different type on it.

THE ASYMMETRY IS THE RULE, AND IT RUNS AGAINST COMFORT
--------------------------------------------------------
SILENCE never overwrites: a read that did not mention an element has said
nothing about it, and nothing is not a finding.

A POSITIVE STATEMENT ALWAYS WINS, including a regression from HELD to ABSENT.
D5.1 warns that a model being careful with a client drifts toward the
comfortable answer, so a product that could not LOWER its own confidence would
have a proof section that only ever improved. That is the failure that loses
cases, and it is the more likely one.

AND THE FILE OVERRULES BOTH. A HELD position rests on material; material the
advocate has corrected takes the position with it, checked against the file
rather than against the read. `chart` already drops a superseded fact for
exactly this reason, and B-086 was the correction that was applied and had no
visible effect.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.knowledge.elements import CuratedElements
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core import proof_read
from nm.core.turn import TurnEngine, TurnInput, TurnMetrics
from nm.domain import proof as domain_proof
from nm.domain.matter import Basis, CauseOfAction, Posture, Role, Side, Thread
from nm.domain.proof import Burden, ProofPosition, ProofStatus, Standard
from nm.domain.quotable import Quotable
from nm.knowledge.elements import elements_for
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 6)
ACCOUNT = ("We act for the plaintiff. The agreement to sell is dated "
           "15-4-2024 and we hold the original.")

ELEMENTS = elements_for(CauseOfAction.SPECIFIC_PERFORMANCE)
FIRST = ELEMENTS.ingredients[0].element
SECOND = ELEMENTS.ingredients[1].element


def _pos(element=FIRST, status=ProofStatus.NOT_ASSESSED, **kw):
    return ProofPosition(element=element, burden=Burden(on=Side.MOVING),
                         status=status,
                         standard=(Standard.BALANCE_OF_PROBABILITIES
                                   if status is not ProofStatus.NOT_ASSESSED
                                   else Standard.NOT_ESTABLISHED),
                         **kw)


def _held(element=FIRST, on=("we hold the original",)):
    return _pos(element, ProofStatus.HELD, material=on)


# ================================ the merge =================================

def test_a_position_survives_a_read_that_forgets_it():
    """THE DEFECT, AS A RULE. Not "positions are stored" — storing them and
    replacing the list from each read would pass that and change nothing."""
    merged = domain_proof.merge((_held(),), (_pos(),))
    assert len(merged) == 1
    assert merged[0].status is ProofStatus.HELD
    assert merged[0].material == ("we hold the original",)


def test_a_positive_statement_wins_even_when_it_is_worse_news():
    """THE BOUND THAT MATTERS MOST.

    D5.1: the drift runs toward the comfortable answer, so a merge that only
    ever let a position improve would build the drift into the mechanism. A
    read that has looked again and says the element is not made out must be
    able to say so.
    """
    merged = domain_proof.merge(
        (_held(),),
        (_pos(FIRST, ProofStatus.ABSENT,
              dead_end="the original was never executed"),))
    assert merged[0].status is ProofStatus.ABSENT
    assert merged[0].material == ()


def test_a_gap_that_closes_is_taken():
    """The other direction, and it is the ordinary one: material arrives."""
    merged = domain_proof.merge(
        (_pos(FIRST, ProofStatus.OBTAINABLE,
              closing_material="the original agreement"),),
        (_held(),))
    assert merged[0].status is ProofStatus.HELD


def test_a_fresh_element_is_added_and_a_dropped_one_is_kept():
    """An element that has left the curated list is one the advocate was
    already told about. Losing it silently is the defect this exists for."""
    merged = domain_proof.merge((_held(),), (_pos(SECOND),))
    assert {p.element for p in merged} == {FIRST, SECOND}
    assert merged[0].element == SECOND, (
        "the fresh list's order is the curated order for the cause this turn "
        "established, and it comes first")


def test_silence_against_silence_changes_nothing():
    merged = domain_proof.merge((_pos(),), (_pos(),))
    assert len(merged) == 1 and merged[0].status is ProofStatus.NOT_ASSESSED


def test_nothing_matches_two_elements_by_resembling_them():
    """CLAUDE.md §5. The element text comes from the curated table on BOTH
    sides, so it is a key and not a resemblance — and two elements of one
    cause can read very alike."""
    a = _held("A concluded and enforceable agreement, and its terms")
    b = _pos("A concluded and enforceable agreement and its terms")
    assert len(domain_proof.merge((a,), (b,))) == 2


# ============================ the file overrules ============================

def test_a_position_held_on_withdrawn_material_falls():
    """B-086 IN D5'S CLOTHES. The advocate corrects the date, the fact leaves
    the chart, and a position resting on it would go on reading as HELD."""
    on_file = Quotable(file="We act for the plaintiff.")
    position = _held()
    assert not domain_proof.still_supported(position, on_file)

    fallen = domain_proof.withdrawn(position, "the fact was corrected")
    assert fallen.status is ProofStatus.NOT_ASSESSED
    assert fallen.material == ()
    assert fallen.withdrawn_because == "the fact was corrected"


def test_it_falls_to_not_assessed_and_never_to_absent():
    """ABSENT means nothing identified would establish it, which is a finding
    nobody made. The material was withdrawn; whether something else would
    establish the element has not been looked at since."""
    fallen = domain_proof.withdrawn(_held(), "corrected")
    assert fallen.status is not ProofStatus.ABSENT
    assert fallen.dead_end == "", (
        "a withdrawn position carries a dead end, which is a claim that "
        "nothing would establish the element — and nobody checked")


def test_a_position_still_on_the_file_is_left_alone():
    """THE BOUND. A check that failed everything would pass the test above
    and delete every HELD position on every turn."""
    assert domain_proof.still_supported(_held(), Quotable(file=ACCOUNT))


def test_a_position_that_is_not_held_has_no_material_to_withdraw():
    obtainable = _pos(FIRST, ProofStatus.OBTAINABLE,
                      closing_material="the original agreement")
    assert domain_proof.still_supported(obtainable, Quotable(file=""))


# =============================== the store ==================================

def test_positions_come_back_from_the_store_typed(tmp_path):
    """`Thread.proof` is untyped because `nm.domain.proof` would be a cycle,
    so the store returns plain dicts. Left implicit, the next turn would merge
    dicts against positions, match nothing, and every element would look
    freshly unassessed every turn — this defect arriving through its repair,
    which is what happened to the issues."""
    store = FileMatterStore(tmp_path, key=KEY)
    from nm.domain.matter import Matter

    matter = Matter.create(advocate_id="adv_1", title="t")
    thread = replace(Thread.create(label="t"),
                     proof=(_held(), _pos(SECOND, ProofStatus.OBTAINABLE,
                                          closing_material="the ledger")))
    store.commit(matter.with_thread(thread),
                 expected_version=matter.version)

    raw = store.load(matter.id).threads[0].proof
    assert raw, "nothing was persisted"
    live = domain_proof.from_stored(raw)
    assert len(live) == 2
    assert all(isinstance(p, ProofPosition) for p in live)
    assert live[0].status is ProofStatus.HELD
    assert live[0].material == ("we hold the original",)
    assert live[1].closing_material == "the ledger"


def test_a_stored_row_that_cannot_be_rebuilt_is_dropped_and_the_rest_kept():
    """Losing one position to a record written before a field existed is bad.
    Losing the whole list to it is worse."""
    good = {"element": FIRST, "burden": {"on": "moving"},
            "standard": "balance_of_probabilities", "status": "held",
            "material": ["we hold the original"]}
    rebuilt = domain_proof.from_stored(
        [good, {"element": FIRST, "burden": {"on": "sideways"}},
         "not a position", 7])
    assert len(rebuilt) == 1
    assert rebuilt[0].element == FIRST


# ============================== on the wire =================================

class _Forgetful(ScriptedModelAdapter):
    """Answers the proof read ONCE and says nothing afterwards.

    GS-15 turn 4 in the shape D5 would meet it. Driven, because the live read
    forgot on one turn of five and could not be made to do it on demand.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.reads = 0

    def structured(self, prompt, schema, tier, **kw):
        result = super().structured(prompt, schema, tier, **kw)
        if schema.get("x-nm-read") == "proof" and result.data is not None:
            self.reads += 1
            if self.reads > 1:
                import json
                said = {"positions": []}
                return replace(result, data=said, text=json.dumps(said))
        return result


def _engine(tmp_path, inner=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=inner or ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=_Evidence(), model=model,
                      elements=CuratedElements()), store


class _Memory:
    account = ACCOUNT
    advocate_words = ACCOUNT
    notes = ""


def _thread():
    return replace(Thread.create(label="t"),
                   posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED))


def test_a_held_position_does_not_flicker_across_turns(tmp_path):
    """THE DEFECT, END TO END, and the count must never fall while nothing
    has withdrawn anything."""
    engine, _ = _engine(tmp_path, inner=_Forgetful(
        _model_config(), responses={"__default__": "Issue the notice."}))
    thread = _thread()
    turn = TurnInput(advocate_id="adv_1", today=TODAY, message="where now?")

    assessed = []
    for _ in range(4):
        concluded: dict = {}
        engine._proof(turn, thread, _Memory(),
                      TurnMetrics(turn_id="turn_1", matter_id="mat_1"),
                      "specific_performance", concluded)
        live = concluded["proof"]
        thread = replace(thread, proof=live)
        assessed.append(sum(1 for p in live
                            if p.status is not ProofStatus.NOT_ASSESSED))

    assert assessed[0] > 0, (
        "the first turn established nothing, so this is not exercising the "
        "case it was written for")
    assert all(b >= a for a, b in zip(assessed, assessed[1:], strict=False)), (
        f"the number of established elements fell while nothing withdrew "
        f"anything: {assessed}. The read went silent and the position went "
        f"with it, which is the issue count going 1, 1, 1, 0, 2.")


def test_the_positions_are_written_to_the_thread(tmp_path):
    """A merge that never reaches the store is a merge against an empty list
    every turn, which passes every unit test above and changes nothing."""
    engine, _ = _engine(tmp_path)
    concluded: dict = {}
    engine._proof(TurnInput(advocate_id="adv_1", today=TODAY,
                            message="where now?"),
                  _thread(), _Memory(),
                  TurnMetrics(turn_id="turn_1", matter_id="mat_1"),
                  "specific_performance", concluded)
    assert concluded.get("proof"), (
        "`_proof` derived positions and put none on `concluded`, so the "
        "write-back at the end of the turn has nothing to persist")
    assert len(concluded["proof"]) == len(ELEMENTS.ingredients)


def test_the_read_is_still_what_moves_a_position(tmp_path):
    """THE OTHER BOUND. A merge that always kept the standing list would
    freeze the thread on turn one — the opposite failure and just as bad."""
    engine, _ = _engine(tmp_path)
    thread = replace(_thread(), proof=(
        _pos(FIRST, ProofStatus.OBTAINABLE,
             closing_material="the original agreement"),))
    concluded: dict = {}
    engine._proof(TurnInput(advocate_id="adv_1", today=TODAY,
                            message="where now?"),
                  thread, _Memory(),
                  TurnMetrics(turn_id="turn_1", matter_id="mat_1"),
                  "specific_performance", concluded)

    first = next(p for p in concluded["proof"] if p.element == FIRST)
    assert first.status is ProofStatus.HELD, (
        "the standing OBTAINABLE survived a read that said HELD, so a gap "
        "that closes never closes")


def test_a_position_on_material_no_longer_on_the_file_falls_on_the_turn(tmp_path):
    """The file overruling the read, on the served path rather than in a unit.
    An advocate who corrects a fact must not read an element as established
    on the version they withdrew."""
    engine, _ = _engine(tmp_path)

    class _Corrected:
        account = "We act for the plaintiff."
        advocate_words = "We act for the plaintiff."
        notes = ""

    thread = replace(_thread(), proof=(_held(),))
    concluded: dict = {}
    engine._proof(TurnInput(advocate_id="adv_1", today=TODAY, message="and?"),
                  thread, _Corrected(),
                  TurnMetrics(turn_id="turn_2", matter_id="mat_1"),
                  "specific_performance", concluded)

    first = next(p for p in concluded["proof"] if p.element == FIRST)
    assert first.status is ProofStatus.NOT_ASSESSED
    assert first.withdrawn_because, (
        "the position fell and said nothing about why, which is B-086 "
        "exactly: the correction applied and had no visible effect")


def test_against_us_reads_the_merged_list_not_the_fresh_one(tmp_path):
    """The gaps line is what the advocate acts on, so it has to be built from
    the list that survived the merge rather than from this turn's read."""
    engine, _ = _engine(tmp_path, inner=_Forgetful(
        _model_config(), responses={"__default__": "Issue the notice."}))
    thread = _thread()
    turn = TurnInput(advocate_id="adv_1", today=TODAY, message="where now?")

    concluded: dict = {}
    engine._proof(turn, thread, _Memory(),
                  TurnMetrics(turn_id="turn_1", matter_id="mat_1"),
                  "specific_performance", concluded)
    thread = replace(thread, proof=concluded["proof"])

    concluded = {}
    out = engine._proof(turn, thread, _Memory(),
                        TurnMetrics(turn_id="turn_2", matter_id="mat_1"),
                        "specific_performance", concluded)
    text = " ".join(e.text for e in out)
    assert "held on" in text, (
        "the second turn's answer lost the position the first established, "
        "so the merge reached the store and not the advocate")
    assert proof_read.against_us(concluded["proof"], thread.posture)
