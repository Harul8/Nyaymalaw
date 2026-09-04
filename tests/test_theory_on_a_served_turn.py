"""D6 — the case theory, REACHED. E-080 and E-081 on a served turn.

E-080's counterexample is *a theory that works only if three documents are
forgotten*, and the reason it is dangerous is that it READS PERFECTLY: the
three are simply not mentioned. Absence is invisible. `unaccounted` makes it a
list, by name, because which one it is decides what is pleaded.

THE ORDER OF THE TWO READS IS THE MECHANISM
---------------------------------------------
The adverse facts are read FIRST, without the model knowing what theory will
be built on them. If one read produced both, the theory would choose its own
population — three adverse facts named, three accounted for, every time — and
`unaccounted` could not fail. That is S11 wearing a plausible face, and the
test below plants exactly that failure to show the check survives it.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import theory as th
from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from nm.domain.matter import Fact, Provenance, Side
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

PROV = Provenance(kind="advocate_statement", turn="t1")

BRIEF = ("We act for the defendant at Hyderabad in a cheque matter. The "
         "cheque was signed on 4 January 2024. The loan was repaid in cash on "
         "9 February 2024 with no receipt.")


def _fact(fid, statement):
    return Fact(id=fid, statement=statement, provenance=PROV)


def _run(tmp_path, message=BRIEF):
    engine, _ = build(tmp_path)
    return engine.run(TurnInput(advocate_id="adv_1", message=message,
                                today=date(2026, 9, 4)))


def _text(out):
    return " ".join(e.text for e in out.answer.elements)


# ============================ the wiring itself ============================

@pytest.mark.eval_id("E-080")
def test_a_theory_reaches_the_advocate(tmp_path):
    """`nm/core/theory.py` had a complete unit suite and no production caller
    for a slice (B-079). Everything below is meaningless without this."""
    findings = [e.text for e in _run(tmp_path).answer.elements
                if e.kind is ElementKind.FINDING and e.text.startswith("Theory:")]
    assert findings, "no theory reached the answer"


# ====================== E-080, and the check that can fail =================

@pytest.mark.eval_id("E-080")
def test_a_theory_that_forgets_the_adverse_facts_names_every_one_of_them():
    """THE COUNTEREXAMPLE, PLANTED.

    Driven through the reader rather than the engine, because the scripted
    double deliberately accounts for everything it is given — a test that
    waited for the double to forget would be waiting on a coincidence.
    """
    chart = tuple(_fact(f"f{i}", f"an adverse document {i}") for i in (1, 2, 3))
    adverse, _ = th.read_adverse(
        {"adverse": [{"fact_id": f.id, "why": "the other side relies on it"}
                     for f in chart]}, chart)

    forgetful = th.read_theory({
        "theme": "A theory that works only if three documents are forgotten",
        "account": "a", "legal_theory": "b", "relief": "dismissal",
        "stance": "affirmative", "chosen_because": "",
        "explains": [], "concedes": []}, "th_1", Side.DEFENDING, adverse)

    assert th.unaccounted(adverse, forgetful.theory) == ("f1", "f2", "f3"), (
        "the theory accounted for nothing and the check said nothing")


@pytest.mark.eval_id("E-080")
def test_no_theory_at_all_leaves_every_adverse_fact_unaccounted():
    """A thread with no theory has not disposed of its adverse facts by not
    having one. `None` must not read as `nothing outstanding`."""
    chart = (_fact("f1", "an admission"), _fact("f2", "a delay"))
    adverse, _ = th.read_adverse(
        {"adverse": [{"fact_id": "f1", "why": "x"},
                     {"fact_id": "f2", "why": "y"}]}, chart)
    assert th.unaccounted(adverse, None) == ("f1", "f2")


@pytest.mark.eval_id("E-080")
def test_a_theory_cannot_shrink_the_check_by_naming_facts_nobody_called_adverse():
    """S11, CLOSED FROM THE OTHER SIDE.

    A theory claiming to explain `f9` — which nothing called adverse — would
    make `unaccounted` smaller without answering anything. The claim is
    dropped, so the check measures what it says it measures.
    """
    chart = (_fact("f1", "an admission"),)
    adverse, _ = th.read_adverse({"adverse": [{"fact_id": "f1", "why": "x"}]},
                                 chart)
    read = th.read_theory({
        "theme": "X", "account": "a", "legal_theory": "b", "relief": "r",
        "stance": "affirmative", "chosen_because": "",
        "explains": ["f9"], "concedes": []}, "th_1", Side.DEFENDING, adverse)

    assert read.theory.explains == ()
    assert th.unaccounted(adverse, read.theory) == ("f1",)


def test_an_adverse_id_the_file_does_not_hold_is_dropped():
    """It would ENLARGE the population, so the theory would be reported as
    failing to account for a fact that does not exist."""
    chart = (_fact("f1", "an admission"),)
    adverse, _ = th.read_adverse({"adverse": [
        {"fact_id": "f1", "why": "x"}, {"fact_id": "f9", "why": "y"}]}, chart)
    assert adverse == ("f1",)


# ============================ a denial is chosen ===========================

@pytest.mark.eval_id("E-080")
def test_a_bare_denial_with_no_reasons_is_refused_and_the_advocate_is_told():
    """*"The complainant has not proved his case" is a hope that the other
    side fails.* Where a denial is genuinely right it is a CHOSEN strategy and
    says why — never one arrived at by default."""
    read = th.read_theory({
        "theme": "The complainant has not proved his case",
        "account": "", "legal_theory": "", "relief": "",
        "stance": "denial", "chosen_because": "",
        "explains": [], "concedes": []}, "th_1", Side.DEFENDING, ())

    assert read.state == "refused"
    assert "hope that the other side fails" in read.refused


def test_a_denial_with_reasons_is_accepted():
    """The rule is not "no denials". A denial that says why is a theory."""
    read = th.read_theory({
        "theme": "The complainant cannot prove the debt existed",
        "account": "no writing, no witness, and the ledger is theirs",
        "legal_theory": "the burden is on the complainant",
        "relief": "", "stance": "denial",
        "chosen_because": "there is no document to explain and inventing an "
                          "account would be worse than making them prove it",
        "explains": [], "concedes": []}, "th_1", Side.DEFENDING, ())
    assert read.state == "formed"


# =========================== one theory, not a menu ========================

@pytest.mark.eval_id("E-080")
def test_two_theories_on_one_thread_raise_rather_than_being_ranked():
    """*Never offer two theories in parallel.* Ranking them would be the menu
    wearing an ordering, and the advocate would still have to choose."""
    a = th.Theory(thread="th_1", theme="One", stance=th.Stance.AFFIRMATIVE,
                  relief="r")
    b = th.Theory(thread="th_1", theme="Two", stance=th.Stance.AFFIRMATIVE,
                  relief="r")
    with pytest.raises(ValueError, match="menu"):
        th.for_thread((a, b), "th_1")


def test_a_fact_cannot_be_both_explained_and_conceded():
    """Which one it is decides what is pleaded."""
    with pytest.raises(ValueError, match="explained and conceded"):
        th.Theory(thread="th_1", theme="X", stance=th.Stance.AFFIRMATIVE,
                  relief="r", explains=("f1",), concedes=("f1",))


# ============================ E-081, structurally ==========================

@pytest.mark.eval_id("E-081")
def test_two_arguments_needing_opposite_values_of_one_fact_are_inconsistent():
    """*"I never signed it"* and *"I signed it under a misrepresentation"* are
    inconsistent, and no amount of string comparison shows it.

    Pleading in the ALTERNATIVE is permitted and routine; what destroys
    credibility is two inconsistent FACTUAL accounts — so an argument declares
    the account it NEEDS, and the answer is set arithmetic.
    """
    # `requires` MAPS A FACT TO WHAT THE ARGUMENT NEEDS IT TO BE — `True` for
    # "this happened", `False` for "this did not". Two arguments needing
    # opposite values of one fact are inconsistent by set arithmetic, with no
    # sentence read.
    never = th.Argument(statement="I never signed it", thread="th_1",
                        requires={"f_signature": False})
    duress = th.Argument(statement="I signed under misrepresentation",
                         thread="th_1", requires={"f_signature": True})
    assert th.inconsistent((never, duress))


def test_an_argument_that_declares_nothing_is_reported_not_silently_consistent():
    """It would otherwise be consistent with everything, which is how a
    contradiction survives a check designed to find one."""
    silent = th.Argument(statement="we should win", thread="th_1")
    assert th.undeclared((silent,))


def test_three_states_on_the_read():
    assert th.UNREAD_THEORY.state == "not_assessed"
    assert th.theory_not_assessed("no chart").state == "not_assessed"
    assert th.read_theory({"theme": ""}, "th_1", Side.UNKNOWN, ()).state == \
        "none_formed"
