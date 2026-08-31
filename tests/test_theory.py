"""S8 — theory, the adversarial pass, salvage. D6, D7, D8.

Each of the three is a rule about what the product must NOT quietly omit, and
each counterexample is a document that read perfectly:

    D6  a theory that works only if three documents are forgotten
    D7  a file where the client's own recovery suit undermines his defence in
        the cheque matter, and no single thread reveals it
    D8  advice that a claim was dead where a different framing on the same
        facts was available

None of the three is wrong on its face. All three are short.
"""
from __future__ import annotations

import pytest

from nm.core.adversarial import (
    Attack,
    Coordinate,
    Exposure,
    ExposureReport,
    ExposureState,
    Salvage,
    Strength,
    cross_thread,
    unanswered,
    unvaried,
)
from nm.core.theory import (
    Argument,
    Stance,
    Theory,
    for_thread,
    inconsistent,
    unaccounted,
    undeclared,
)
from nm.domain.matter import Side
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

ADVERSE = ("fact_receipt", "fact_letter", "fact_ledger")


# ================= D6.0 — one theory, and the menu refused =================


@refuses("D6", 0)
@pytest.mark.eval_id("E-080")
def test_exactly_one_theory_per_thread():
    """D6: *never offer two theories in parallel. A menu is the survey this
    document already rejects.*

    An advocate handed three theories has been handed the work back. Ranking
    them would be the menu wearing an ordering, and they would still choose.
    """
    one = Theory(thread="thr_1", theme="the goods were delivered and unpaid",
                 stance=Stance.AFFIRMATIVE, relief="a decree for the price",
                 for_side=Side.MOVING)
    assert for_thread((one,), "thr_1") is one
    assert for_thread((one,), "thr_2") is None, "a thread with no theory yet"

    other = Theory(thread="thr_1", theme="the contract was frustrated",
                   stance=Stance.AFFIRMATIVE, relief="rescission")
    with pytest.raises(ValueError) as exc:
        for_thread((one, other), "thr_1")
    assert "menu" in str(exc.value)


@refuses("D6", 0)
@pytest.mark.eval_id("E-080")
def test_every_adverse_fact_is_explained_or_expressly_conceded():
    """E-080's counterexample: *a theory that works only if three documents are
    forgotten.*

    It reads perfectly. The three are simply not mentioned, and absence is
    invisible — so this makes it a list.
    """
    forgetful = Theory(
        thread="thr_1", theme="the goods were delivered and unpaid",
        stance=Stance.AFFIRMATIVE, relief="a decree for the price",
        explains=("fact_receipt",))

    left = unaccounted(ADVERSE, forgetful)
    assert set(left) == {"fact_letter", "fact_ledger"}

    # CONCEDING IS AN ANSWER. Ignoring is not.
    honest = Theory(
        thread="thr_1", theme="the goods were delivered and unpaid",
        stance=Stance.AFFIRMATIVE, relief="a decree for the price",
        explains=("fact_receipt",), concedes=("fact_letter", "fact_ledger"))
    assert unaccounted(ADVERSE, honest) == ()

    # NO THEORY LEAVES EVERY ADVERSE FACT UNACCOUNTED, not none. A thread has
    # not disposed of its adverse facts by having no theory.
    assert unaccounted(ADVERSE, None) == ADVERSE

    # AND A FACT CANNOT BE BOTH. Which one it is decides what is pleaded.
    with pytest.raises(ValueError):
        Theory(thread="thr_1", theme="t", stance=Stance.AFFIRMATIVE,
               relief="r", explains=("fact_x",), concedes=("fact_x",))


@refuses("D6", 1)
@pytest.mark.eval_id("E-080")
def test_a_bare_denial_is_a_chosen_strategy_and_never_a_default():
    """D6: *a defending party's theory is not "we deny". "The cheque was
    security for a loan that was repaid" is a theory; "the complainant has not
    proved his case" is a hope that the other side fails.*

    A denial is sometimes right. When it is, it says why — so the default is
    unreachable without a reason.
    """
    with pytest.raises(ValueError) as exc:
        Theory(thread="thr_1", theme="the complainant has not proved his case",
               stance=Stance.DENIAL, for_side=Side.DEFENDING)
    assert "arrived at by default" in str(exc.value)

    chosen = Theory(
        thread="thr_1", theme="the complainant has not proved his case",
        stance=Stance.DENIAL, for_side=Side.DEFENDING,
        chosen_because=("the cheque is not in his name and he has produced no "
                        "ledger; putting a positive case would concede "
                        "possession we do not need to concede"))
    assert chosen.chosen_because

    # AND AN AFFIRMATIVE THEORY WITH NOTHING TO ASK FOR is a story.
    with pytest.raises(ValueError) as exc2:
        Theory(thread="thr_1", theme="the goods were delivered",
               stance=Stance.AFFIRMATIVE)
    assert "names no relief" in str(exc2.value)


# ============ D6.2 — inconsistent factual accounts, structurally ===========


@refuses("D6", 2)
@pytest.mark.eval_id("E-081")
def test_two_arguments_needing_opposite_facts_are_flagged():
    """E-081's counterexample: *"I never signed it" run alongside "I signed it
    under a misrepresentation".*

    No string comparison shows that, and D6 is explicit that pleading in the
    ALTERNATIVE is permitted — what destroys credibility is two inconsistent
    FACTUAL accounts. So an argument declares which facts it needs true and
    which untrue, and the arithmetic does the rest.
    """
    never = Argument(statement="I never signed it", thread="thr_1",
                     requires={"fact_signature": False})
    under = Argument(statement="I signed it under a misrepresentation",
                     thread="thr_1", requires={"fact_signature": True},
                     in_the_alternative=True)

    clash = inconsistent((never, under))
    assert len(clash) == 1
    assert clash[0][2] == "fact_signature"

    # THE ALTERNATIVE FLAG DOES NOT SUPPRESS IT. "I never borrowed the money,
    # and in any event I repaid it" loses whether or not it is so labelled.
    assert under.in_the_alternative and clash

    # PLEADING IN THE ALTERNATIVE ON COMPATIBLE FACTS IS FINE, so the check is
    # not simply refusing alternatives.
    limitation = Argument(statement="and in any event the claim is out of time",
                          thread="thr_1", requires={"fact_accrual_2019": True},
                          in_the_alternative=True)
    assert inconsistent((never, limitation)) == ()

    # AND ARGUMENTS ON DIFFERENT THREADS ARE DIFFERENT CASES.
    other = Argument(statement="I signed it", thread="thr_2",
                     requires={"fact_signature": True})
    assert inconsistent((never, other)) == ()


@refuses("D6", 2)
@pytest.mark.eval_id("E-081")
def test_an_argument_declaring_no_facts_cannot_be_silently_consistent():
    """THE POSITIVE CONTROL, in production.

    An argument that commits to nothing can never contradict anything, so a
    file of them reports a clean bill of health forever — the shape B-049 was.
    """
    vague = Argument(statement="the claim is misconceived", thread="thr_1")
    assert inconsistent((vague, vague)) == ()
    assert undeclared((vague,)) == ("the claim is misconceived",)

    declared = Argument(statement="the claim is misconceived", thread="thr_1",
                        requires={"fact_privity": False})
    assert undeclared((declared,)) == ()


# ============ D7 — exactly once, empty or not =============================


@refuses("D7", 2)
@pytest.mark.eval_id("E-082")
def test_cross_thread_exposure_is_produced_exactly_once_empty_or_not():
    """E-082's counterexample: *exposure emitted twice, or silently omitted.*

    Both are defects and they fail in opposite directions — twice is noise the
    advocate learns to skip, omitted reads as "nothing found" when nobody
    looked. So there are three states and one of them is NOT_RUN.
    """
    threads = ("thr_cheque", "thr_recovery")
    exposure = Exposure(
        from_thread="thr_recovery", to_thread="thr_cheque",
        what="the plaint asserts he was solvent throughout 2024",
        consequence="it contradicts the no-funds defence on the cheque")

    found = cross_thread(threads, (exposure,))
    assert found.state is ExposureState.FOUND and len(found.exposures) == 1

    # LOOKED AND FOUND NOTHING is an ANSWER, expressly returned.
    assert cross_thread(threads, ()).state is ExposureState.NONE_FOUND

    # NOBODY LOOKED is a different fact and says why.
    not_run = cross_thread(threads, None)
    assert not_run.state is ExposureState.NOT_RUN
    assert not_run.not_run_because

    # A SINGLE-THREAD FILE STILL GETS A REPORT. A section that appears only
    # sometimes is one the advocate cannot rely on being there.
    assert cross_thread(("thr_only",), ()).state is ExposureState.NONE_FOUND


@refuses("D7", 3)
@pytest.mark.eval_id("E-082")
def test_an_empty_report_and_an_absent_one_cannot_render_alike():
    """The type refuses the confusion rather than a reader catching it."""
    with pytest.raises(ValueError) as exc:
        ExposureReport(ExposureState.FOUND)
    assert "NONE_FOUND is the state" in str(exc.value)

    with pytest.raises(ValueError) as exc2:
        ExposureReport(ExposureState.NOT_RUN)
    assert "must say why" in str(exc2.value)

    # AND AN EXPOSURE FROM A THREAD TO ITSELF is a per-thread finding wearing
    # the wrong name -- it would make the file-level pass look productive.
    with pytest.raises(ValueError):
        Exposure(from_thread="t", to_thread="t", what="x", consequence="y")


@refuses("D7", 0)
@pytest.mark.eval_id("E-083")
def test_every_attack_carries_our_answer_or_says_there_is_none():
    """D7: *where an attack has no good answer, say so plainly and resolve it
    into what we do about it.*

    An attack with no answer and an attack expressly unanswerable are different
    findings: one is work not done, the other is a fact about the case.
    """
    with pytest.raises(ValueError) as exc:
        Attack(thread="t", ground="limitation",
               their_case="the claim accrued in 2019 and is out of time")
    assert "work not done" in str(exc.value)

    # UNANSWERABLE AND ABANDONED is half a finding.
    with pytest.raises(ValueError) as exc2:
        Attack(thread="t", ground="limitation",
               their_case="the claim accrued in 2019", no_answer=True)
    assert "what we do about it" in str(exc2.value)

    ok = Attack(thread="t", ground="limitation",
                their_case="the claim accrued in 2019 and is out of time",
                no_answer=True,
                no_answer_because=("we concede the point and move to the s.18 "
                                   "acknowledgment, which is the whole case"))
    assert unanswered((ok,)) == ()


# ============ D8 — we lose, or we lose on this framing =====================


@refuses("D8", 1)
@refuses("D8", 2)
@refuses("D8", 3)
@pytest.mark.eval_id("E-084")
def test_no_salvage_route_is_stated_at_category_level():
    """E-084's counterexample: *"Consider a different forum", with no forum
    named.*

    D8: *"consider a different relief" is boilerplate; "declaration plus
    possession on the same facts" is a route.* A route resting on nothing
    retrieved IS the category-level suggestion, so the citation requirement and
    the specificity requirement are the same requirement.
    """
    with pytest.raises(ValueError) as exc:
        Salvage(coordinate=Coordinate.FORUM,
                varied_result="a different forum might take it",
                route="consider a different forum",
                strength=Strength.ARGUABLE)
    assert "category-level" in str(exc.value)

    # AND AN UNMARKED ROUTE READS AS A RECOMMENDATION.
    with pytest.raises(ValueError) as exc2:
        Salvage(coordinate=Coordinate.RELIEF,
                varied_result="declaration is available on the same facts",
                route="declaration plus possession",
                findings=("Specific Relief Act, 1963 s.34",))
    assert "no strength" in str(exc2.value)

    real = Salvage(
        coordinate=Coordinate.RELIEF,
        varied_result="the same facts support a declaration",
        route="declaration plus possession on the same facts",
        strength=Strength.WOULD_RUN,
        findings=("Specific Relief Act, 1963 s.34",))
    assert real.route


@refuses("D8", 0)
@pytest.mark.eval_id("E-084")
def test_a_coordinate_can_be_varied_and_yield_no_route():
    """D8: *never manufacture a route. A system rewarded for always finding a
    way out will invent one, and a hopeless alternative cause costs the client
    money and the advocate credibility.*

    So no route is a first-class outcome — what is required is that the
    variation was STATED, which D8 says must happen before reporting failure.
    """
    dead = Salvage(coordinate=Coordinate.PARTY,
                   varied_result=("joining the guarantor does not help: the "
                                  "guarantee was discharged by the novation"))
    assert dead.route == ""
    assert dead.strength is Strength.NOT_ASSESSED
    assert dead.varied_result


@refuses("D8", 0)
@pytest.mark.eval_id("E-084")
def test_coordinates_nobody_moved_are_named():
    """THE POPULATION IS THE SEVEN, not what was tried.

    D8's measured error was advice that a claim was dead where a different
    framing on the same facts was available. A report that varied two
    coordinates and concluded the case is dead has not done the work — and the
    two it did vary would make it look as though it had.
    """
    tried = (Salvage(coordinate=Coordinate.RELIEF, varied_result="x"),
             Salvage(coordinate=Coordinate.FORUM, varied_result="y"))
    left = unvaried(tried)
    assert set(left) == {"party", "cause", "timing", "procedure", "burden"}
    assert unvaried(tuple(Salvage(coordinate=c, varied_result="z")
                          for c in Coordinate)) == ()
