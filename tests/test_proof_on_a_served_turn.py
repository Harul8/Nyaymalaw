"""D5 — what has to be proved, produced on a turn an advocate can reach.

WHAT WAS MISSING, AND FOR HOW LONG
------------------------------------
`nm/domain/proof.py` has carried D5's whole contract since slice 7. A position
cannot be HELD without material, cannot be OBTAINABLE without saying what would
obtain it, cannot be ABSENT without naming the dead end, and `uncovered` draws
its population from the ELEMENTS so the coverage gate cannot certify itself.

Every one of those refusals was correct, and NOTHING EVER BUILT A
`ProofPosition`. None of it ran. It is B-079 exactly — D9's issue register was
complete and unreachable in the same way, one feature along — and the reason
both were invisible is that the unit tests pass beautifully on a type nobody
constructs in production.

THE DIVISION OF LABOUR IS THE DESIGN, AND THESE TEST IT SEPARATELY
--------------------------------------------------------------------
    the LAW    what a cause requires   `nm/knowledge/elements.py`, curated
    the FILE   what is held for each   `nm/core/proof_read.py`, read + guarded

A model asked "what are the elements of specific performance" answers
plausibly and differently every call. If the element list came back from the
model, `uncovered` would report complete coverage of whatever it produced and
D5's third NEVER would be defeated one layer above where it looks.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.knowledge.elements import CuratedElements
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core import proof, proof_read
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.matter import Basis, CauseOfAction, Posture, Role, Side
from nm.domain.proof import ProofPosition, ProofStatus, Standard
from nm.domain.quotable import Quotable
from nm.knowledge.elements import ELEMENTS, WITHHELD, elements_for, why_not
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 6)

ACCOUNT = ("We act for the plaintiff. The agreement to sell is dated "
           "15-4-2024 and we hold the original. The defendant refused to "
           "execute the sale deed on 2-1-2025.")


def _elements(cause=CauseOfAction.SPECIFIC_PERFORMANCE):
    got = elements_for(cause)
    assert got is not None, f"{cause} is not curated"
    return got


def _quotable(text=ACCOUNT):
    return Quotable(turn="where do we stand?", file=text)


# ======================== the law is curated, not read ======================

def test_no_element_list_comes_from_the_model():
    """THE RULE THE WHOLE FEATURE RESTS ON.

    The schema has no field in which a model could return an element, and the
    reader matches every reported position against the curated list by name.
    That is CLAUDE.md §5 reaching somewhere it does not obviously go: fuzzy
    matching may rank, never identify, and what is being identified here is
    what the advocate has to prove.
    """
    props = proof_read.PROOF_SCHEMA["properties"]["positions"]["items"]
    assert set(props["required"]) == {
        "element", "status", "material", "closing_material", "dead_end"}
    assert props["additionalProperties"] is False, (
        "the model can return a field nobody declared, which is where an "
        "invented element gets in")


def test_an_element_the_model_invents_is_dropped_and_disclosed():
    """It would arrive in front of the advocate with the authority of the
    curated ones behind it."""
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": "A sixth thing I made up", "status": "held",
         "material": ["we hold the original"], "closing_material": "",
         "dead_end": ""},
    ]}, elements, _quotable())

    assert all(p.element != "A sixth thing I made up" for p in read.positions)
    assert any("not an element of this cause" in r for r in read.refused)


def test_every_curated_element_gets_a_position_even_when_unmentioned():
    """E-070'S COUNTEREXAMPLE, refused by construction.

    Its shape is a conclusion where two of five elements have NO proof
    position at all. A list that shrinks to whatever the read mentioned looks
    complete; NOT_ASSESSED in the gap is what the advocate actually needs.
    """
    elements = _elements()
    read = proof_read.read({"positions": []}, elements, _quotable())

    assert len(read.positions) == len(elements.ingredients)
    assert all(p.status is ProofStatus.NOT_ASSESSED for p in read.positions)
    assert not proof.uncovered(
        tuple(i.element for i in elements.ingredients), read.positions)


def test_the_curated_order_is_the_order_the_advocate_reads():
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[2].element, "status": "not_assessed",
         "material": [], "closing_material": "", "dead_end": ""}]},
        elements, _quotable())
    assert [p.element for p in read.positions] \
        == [i.element for i in elements.ingredients]


# ===================== the drift, which runs one way ========================

def test_obtainable_with_nothing_named_is_refused():
    """D5.1's MEASURED DIRECTION. A model being careful reaches for OBTAINABLE
    where the honest answer is ABSENT, because obtainable sounds like progress.

    D5's second NEVER: *never report a proof gap as a verdict. "You cannot
    prove the loan" fails. "The loan needs the bank statement for that month
    and the ledger entry; both are ordinarily with the client" is the
    requirement.* Both halves are enforced — the vague answer is refused, and
    the refusal is what makes ABSENT the cheaper honest route.
    """
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[1].element, "status": "obtainable",
         "material": [], "closing_material": "   ", "dead_end": ""}]},
        elements, _quotable())

    assert any("nothing named that would obtain it" in r for r in read.refused)
    assert read.positions[1].status is ProofStatus.NOT_ASSESSED, (
        "a refused position left a status behind it, so the advocate reads a "
        "gap that was never assessed as one that was")


def test_obtainable_that_names_the_material_is_taken():
    """THE BOUND. A rule that refused every OBTAINABLE would pass the test
    above and delete the status D5 asks for."""
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[1].element, "status": "obtainable",
         "material": [],
         "closing_material": "the bank statements for April 2024 to the date "
                             "of the suit, ordinarily with the client",
         "dead_end": ""}]}, elements, _quotable())

    assert read.positions[1].status is ProofStatus.OBTAINABLE
    assert "bank statements" in read.positions[1].closing_material


def test_absent_with_no_dead_end_is_refused():
    """An advocate told a thing cannot be proved, with no reason, cannot tell
    whether to look harder or to change the case."""
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[3].element, "status": "absent",
         "material": [], "closing_material": "", "dead_end": ""}]},
        elements, _quotable())
    assert any("no express dead end" in r for r in read.refused)


def test_held_must_be_held_on_the_advocates_own_words():
    """The same verbatim guard every other read applies, through the same
    value the prompt was built from. HELD is the one status that claims
    something about the file, so it is the one whose material has to be in it.
    """
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[0].element, "status": "held",
         "material": ["a document nobody ever mentioned"],
         "closing_material": "", "dead_end": ""}]}, elements, _quotable())

    assert read.positions[0].status is ProofStatus.NOT_ASSESSED
    assert any("HELD" in r for r in read.refused)


def test_held_on_what_the_advocate_did_write_is_taken():
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[0].element, "status": "held",
         "material": ["we hold the original"],
         "closing_material": "", "dead_end": ""}]}, elements, _quotable())

    assert read.positions[0].status is ProofStatus.HELD
    assert read.positions[0].material == ("we hold the original",)


def test_one_refused_position_does_not_discard_the_others():
    """A filter with a good excuse is still a filter."""
    elements = _elements()
    read = proof_read.read({"positions": [
        {"element": elements.ingredients[0].element, "status": "held",
         "material": ["we hold the original"], "closing_material": "",
         "dead_end": ""},
        {"element": elements.ingredients[1].element, "status": "obtainable",
         "material": [], "closing_material": "", "dead_end": ""},
        {"element": elements.ingredients[3].element, "status": "absent",
         "material": [], "closing_material": "",
         "dead_end": "the defendant has never denied performing"},
    ]}, elements, _quotable())

    assert read.positions[0].status is ProofStatus.HELD
    assert read.positions[3].status is ProofStatus.ABSENT
    assert len(read.refused) == 1


# ============================== the burden ==================================

def test_the_burden_knows_the_side_and_not_whether_it_is_ours():
    """D9's rule about `effect`, in a second place. Baking "this is a problem
    for us" into the table would be wrong for half the advocates who read it —
    the s.19(b) defence is the defendant's burden whoever we act for."""
    elements = _elements()
    defence = elements.ingredients[-1]
    assert defence.on is Side.DEFENDING

    for_plaintiff = Posture(role=Role.PLAINTIFF, basis=Basis.STATED)
    for_defendant = Posture(role=Role.DEFENDANT, basis=Basis.STATED)
    burden = elements.burden(defence)
    assert burden.falls_on_us(for_plaintiff) is False
    assert burden.falls_on_us(for_defendant) is True


def test_an_unresolved_posture_claims_nothing_about_whose_burden_it_is():
    """`None`, never `False`. `False` reads as "the opponent must prove it",
    which is the more comfortable answer and is not one anybody established."""
    elements = _elements()
    burden = elements.burden(elements.ingredients[0])
    assert burden.falls_on_us(Posture()) is None

    positions = tuple(
        ProofPosition(element=i.element, burden=elements.burden(i))
        for i in elements.ingredients)
    assert proof_read.against_us(positions, Posture()) == ()


def test_against_us_returns_only_our_gaps():
    elements = _elements()
    positions = tuple(
        ProofPosition(element=i.element, burden=elements.burden(i))
        for i in elements.ingredients)
    ours = proof_read.against_us(
        positions, Posture(role=Role.PLAINTIFF, basis=Basis.STATED))
    assert ours and all(p.burden.on is Side.MOVING for p in ours)


# ===================== the table, and what it withholds =====================

def test_every_cause_is_either_curated_or_withheld_with_a_reason():
    """POPULATION FROM THE ENUM. A cause added tomorrow fails this on the day
    it is added, rather than silently producing no proof section."""
    unaccounted = [c for c in CauseOfAction
                   if c is not CauseOfAction.NOT_ESTABLISHED
                   and c not in ELEMENTS and c not in WITHHELD]
    assert not unaccounted, (
        f"these causes have neither curated elements nor a recorded reason "
        f"for not having them: {unaccounted}. Silence here produces a "
        f"conclusion with no proof section, which reads as though nothing "
        f"had to be proved.")


def test_a_withheld_cause_says_why_and_does_not_guess():
    """THREE STATES, AND THE THIRD SAID OUT LOUD. A cause deliberately
    withheld and a cause nobody has curated are different facts: the first is
    a decision with a reason, the second is a gap in the product."""
    assert elements_for(CauseOfAction.CHEQUE_DISHONOUR) is None
    reason = why_not(CauseOfAction.CHEQUE_DISHONOUR)
    assert "CRIMINAL" in reason and "beyond reasonable doubt" in reason

    assert elements_for(CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION) is None
    assert "s.6" in why_not(CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION)


def test_an_unestablished_cause_is_not_a_missing_table_entry():
    assert elements_for(CauseOfAction.NOT_ESTABLISHED) is None
    assert "not been established" in why_not(CauseOfAction.NOT_ESTABLISHED)


def test_every_curated_entry_says_where_it_came_from():
    """`curated_from` is required by the type, and this asserts it carries a
    SOURCE rather than a sentence. A legal decision that cannot say where it
    came from is one somebody remembered, and this table is exactly where
    remembering would be invisible."""
    for cause, entry in ELEMENTS.items():
        assert entry.cause is cause, f"{cause}: the entry names another cause"
        assert entry.ingredients, f"{cause}: curated with no ingredients"
        assert entry.standard is not Standard.NOT_ESTABLISHED, (
            f"{cause}: no standard, so no position on it can carry one")
        assert any(ch.isdigit() for ch in entry.curated_from), (
            f"{cause}: `curated_from` names no section, Article or year: "
            f"{entry.curated_from!r}")


def test_the_prompt_carries_the_elements_and_the_standard():
    elements = _elements()
    prompt = proof_read.build_prompt(_quotable(), elements)
    for ing in elements.ingredients:
        assert ing.element in prompt.user
    assert "balance of probabilities" in prompt.user
    assert "obtainable" in prompt.system.lower()


def test_the_prompt_forbids_a_character_finding():
    """D5.1. NM speaks to the ADVOCATE, and holds nothing on which a
    credibility finding could rest — it has not met the client."""
    prompt = proof_read.build_prompt(_quotable(), _elements())
    assert "honesty" in prompt.system and "have not met them" in prompt.system


# ============================ on a served turn ==============================

def _engine(tmp_path, inner=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=inner or ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=_Evidence(), model=model,
                      elements=CuratedElements()), store


def test_an_unwired_element_table_says_so_rather_than_saying_nothing(tmp_path):
    """S1, ON THE FEATURE'S OWN FRONT DOOR. A conclusion with no proof section
    reads as a claim with nothing to prove. With no port the turn discloses
    that nothing decomposed the claim, which is what G-PROOF's `not_assessed`
    state exists to carry."""
    store = FileMatterStore(tmp_path, key=KEY)
    engine = TurnEngine(store=store, evidence=_Evidence(),
                        model=TracedModel(inner=ScriptedModelAdapter(
                            _model_config(),
                            responses={"__default__": "Issue the notice."})),
                        elements=None)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=ACCOUNT))
    text = " ".join(e.text for e in out.answer.elements)
    assert "no element table is configured" in text or out.blocked, (
        "the turn produced no proof section and said nothing about why")


def test_a_cause_with_no_curated_elements_names_the_reason(tmp_path):
    """A refusal that says only "not assessed" leaves the advocate unable to
    tell a decision from a gap."""
    engine, _ = _engine(tmp_path)
    from nm.domain.matter import Thread

    thread = replace(Thread.create(label="t"),
                     posture=Posture(role=Role.COMPLAINANT, basis=Basis.STATED))

    class _M:
        account = ACCOUNT
        advocate_words = ACCOUNT
        notes = ""

    out = engine._proof(
        TurnInput(advocate_id="adv_1", today=TODAY, message="where now?"),
        thread, _M(), _metrics(), "cheque_dishonour", {})
    text = " ".join(e.text for e in out)
    assert "CRIMINAL" in text, text


def _metrics():
    from nm.core.turn import TurnMetrics
    return TurnMetrics(turn_id="turn_1", matter_id="mat_1")


def test_the_positions_reach_the_answer_on_a_served_turn(tmp_path):
    """THE WHOLE POINT. Every refusal in `nm/domain/proof.py` was correct for
    a slice and none of it ran, because nothing constructed a position."""
    engine, _ = _engine(tmp_path)
    from nm.domain.matter import Thread

    thread = replace(Thread.create(label="t"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED))

    class _M:
        account = ACCOUNT
        advocate_words = ACCOUNT
        notes = ""

    out = engine._proof(
        TurnInput(advocate_id="adv_1", today=TODAY, message="where now?"),
        thread, _M(), _metrics(), "specific_performance", {})
    text = " ".join(e.text for e in out)

    assert "concluded and enforceable agreement" in text, text
    assert "burden ours" in text, "the burden was not resolved against the posture"
    assert "balance of probabilities" in text
    held = [e.text for e in out if "; held on " in e.text]
    assert held, "no element came back HELD, so the guard is not exercised"
    span = held[0].split("; held on ", 1)[1].rstrip("]")
    assert Quotable(file=ACCOUNT).accepts(span), (
        f"a HELD position cites {span!r}, which is not in what the advocate "
        f"wrote. The material behind a status is the one thing that must be "
        f"theirs.")
    assert "not assessed" in text, (
        "every element came back with a status, so the read is not being "
        "exercised on the case E-070 is about")


def test_a_gap_on_our_side_is_named(tmp_path):
    engine, _ = _engine(tmp_path)
    from nm.domain.matter import Thread

    thread = replace(Thread.create(label="t"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED))

    class _M:
        account = ACCOUNT
        advocate_words = ACCOUNT
        notes = ""

    out = engine._proof(
        TurnInput(advocate_id="adv_1", today=TODAY, message="where now?"),
        thread, _M(), _metrics(), "specific_performance", {})
    ours = [e for e in out if "OURS to establish" in e.text]
    assert ours, "no line told the advocate which gaps are theirs to close"
    assert "subsequent transferee" not in ours[0].text, (
        "the s.19(b) defence is the DEFENDANT'S burden and was listed as ours")
