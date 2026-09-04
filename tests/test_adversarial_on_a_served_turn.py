"""D7 — the adversarial pass, REACHED. E-082 and E-083 on a served turn.

D7's counterexample is a FILE-level fact:

    *a file where the client's own recovery suit undermines his defence in the
    cheque matter, and NO SINGLE THREAD REVEALS IT.*

A per-thread pass cannot find it however carefully each thread is worked,
because the exposure exists only in the pair. So the pass is a phase of its
own, after the threads, and it runs EXACTLY ONCE — empty or not.

E-082's counterexample is *emitted twice, or silently omitted*, and the two
fail in opposite directions: twice is noise the advocate learns to skip, and
omitted reads as "nothing found" when nobody looked.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import adversarial as adv
from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

BRIEF = ("We act for the defendant at Hyderabad in a cheque matter. The loan "
         "was repaid in cash with no receipt and the complainant says it was "
         "never paid.")


def _run(tmp_path, *messages):
    engine, _ = build(tmp_path)
    out = None
    for message in messages or (BRIEF,):
        out = engine.run(TurnInput(
            advocate_id="adv_1", message=message,
            matter_id=out.matter.id if out else None,
            today=date(2026, 9, 4)))
    return out


def _cross_file(out):
    return [e.text for e in out.answer.elements
            if e.text.startswith("Across this file")
            or "CROSS-FILE PASS DID NOT RUN" in e.text]


# ============== E-082: exactly once, empty or not, every file ==============

@pytest.mark.eval_id("E-082")
def test_a_single_thread_file_still_gets_the_cross_file_line(tmp_path):
    """A SECTION THAT APPEARS ONLY SOMETIMES is one the advocate cannot rely
    on being there — and cannot tell from one that found nothing.

    A single-thread file has no pair for an exposure to exist in. That is a
    FINDING, not a reason to skip the section.
    """
    lines = _cross_file(_run(tmp_path))
    assert len(lines) == 1, f"expected exactly one cross-file line, got {lines}"
    assert "found none" in lines[0]


@pytest.mark.eval_id("E-082")
def test_the_cross_file_line_appears_exactly_once_on_a_multi_thread_file(
        tmp_path):
    """TWICE IS NOISE THE ADVOCATE LEARNS TO SKIP, which is why E-082 names it
    as a defect alongside omission rather than as a cosmetic problem."""
    out = _run(tmp_path, BRIEF,
               "Separately, we have a recovery suit for the same client "
               "against a supplier at Secunderabad.")
    assert len(out.matter.threads) >= 2, "the second dispute did not open"
    assert len(_cross_file(out)) == 1


# ============== the pass that did not run is not an empty pass =============

@pytest.mark.eval_id("E-082")
def test_a_pass_that_did_not_run_says_so_rather_than_reading_as_empty():
    """`NOT_RUN` and `NONE_FOUND` are OPPOSITE FACTS and the type refuses to
    let them render alike — a report that did not run must carry why."""
    not_run = adv.cross_thread(("th_1", "th_2"), None)
    assert not_run.state is adv.ExposureState.NOT_RUN
    assert not_run.not_run_because

    with pytest.raises(ValueError, match="must say why"):
        adv.ExposureReport(adv.ExposureState.NOT_RUN)


def test_a_report_claiming_findings_and_carrying_none_is_refused():
    with pytest.raises(ValueError, match="NONE_FOUND is the state"):
        adv.ExposureReport(adv.ExposureState.FOUND)


def test_an_exposure_between_a_thread_and_itself_is_refused():
    """It would be a per-thread finding wearing the wrong name, and it would
    make the file-level pass look as though it had found something."""
    with pytest.raises(ValueError, match="wearing the wrong name"):
        adv.Exposure(from_thread="th_1", to_thread="th_1", what="x",
                     consequence="y")


def test_an_exposure_naming_a_thread_the_file_does_not_hold_is_dropped():
    kept = adv.read_exposures({"exposures": [
        {"from_thread": "th_1", "to_thread": "th_2", "what": "a",
         "consequence": "b"},
        {"from_thread": "th_1", "to_thread": "th_9", "what": "c",
         "consequence": "d"}]}, ("th_1", "th_2"))
    assert len(kept) == 1


# ================= E-083: an attack is answered or resolved ================

@pytest.mark.eval_id("E-083")
def test_the_other_sides_case_reaches_the_advocate(tmp_path):
    grounds = [e.text for e in _run(tmp_path).answer.elements
               if e.kind is ElementKind.GROUND
               and e.text.startswith("They will say")]
    assert grounds, "the other side's case was never put"


@pytest.mark.eval_id("E-083")
def test_an_attack_with_no_answer_that_does_not_say_so_is_refused():
    """TWO DIFFERENT FINDINGS. An attack with no answer is work not done; one
    expressly unanswerable is a fact about the case. Letting the first pass as
    the second is how a gap becomes a conclusion."""
    read = adv.read_attacks({"attacks": [{
        "ground": "limitation", "their_case": "out of time",
        "our_answer": "", "no_answer": False, "no_answer_because": ""}]},
        "th_1")
    assert read.attacks == ()
    assert read.refused and "does not say it has none" in read.refused[0]


@pytest.mark.eval_id("E-083")
def test_an_unanswerable_attack_that_stops_there_is_refused():
    """*Where an attack has no good answer, say so plainly and RESOLVE IT into
    what we do about it.* A problem stated and abandoned is half a finding."""
    read = adv.read_attacks({"attacks": [{
        "ground": "no receipt", "their_case": "repayment is unproved",
        "our_answer": "", "no_answer": True, "no_answer_because": ""}]},
        "th_1")
    assert read.attacks == ()
    assert read.refused and "stops there" in read.refused[0]


@pytest.mark.eval_id("E-083")
def test_an_unanswerable_attack_with_a_plan_is_accepted_and_rendered(tmp_path):
    """The rule is not "every attack must have an answer". It is that an
    unanswerable one must resolve into what we DO."""
    read = adv.read_attacks({"attacks": [{
        "ground": "no receipt", "their_case": "repayment is unproved",
        "our_answer": "", "no_answer": True,
        "no_answer_because": "concede it early and prepare the client"}]},
        "th_1")
    assert len(read.attacks) == 1
    assert adv.unanswered(read.attacks) == ()

    text = " ".join(e.text for e in _run(tmp_path).answer.elements)
    assert "No good answer" in text, (
        "an unanswerable attack was not rendered as one:\n" + text[:600])


def test_the_thread_comes_from_the_caller_and_not_from_the_model():
    """An attack landing on a thread it was not made about would be a finding
    attached to the wrong dispute — and the turn already knows which thread it
    is deriving."""
    read = adv.read_attacks({"attacks": [{
        "thread": "th_somewhere_else", "ground": "g", "their_case": "c",
        "our_answer": "a", "no_answer": False, "no_answer_because": ""}]},
        "th_1")
    assert read.attacks[0].thread == "th_1"


def test_three_states_on_the_attack_read():
    assert adv.UNREAD_ATTACKS.state == "not_assessed"
    assert adv.read_attacks({"attacks": []}, "th_1").state == "none_put"
    assert adv.attacks_not_assessed("no account").state == "not_assessed"


@pytest.mark.eval_id("E-082")
def test_a_blocked_turn_does_not_pay_for_the_cross_file_pass(tmp_path):
    """"EXACTLY ONCE" IS ABOUT A TURN THAT PRODUCES ANALYSIS.

    The exposure line belongs to an ANSWER, and a blocked turn has none — it
    asked a question and stopped. Running the pass anyway cost a model call on
    every blocked turn, which a slice-1 invariant already refused: a turn that
    blocks because the thread binding is ambiguous must be CHEAP, or the
    product charges the advocate for its own uncertainty.

    Caught by that invariant on the first full run after D7 was wired.
    """
    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv_1",
        message="we act for the plaintiff in O.S. 442/2023, a possession suit"))
    second = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id,
        message="in C.C. 77/2025 our client is the accused on a cheque complaint"))
    out = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=second.matter.id,
        message="the hearing yesterday went badly, what now"))

    assert out.answer.blocked, "the fixture no longer blocks, so this proves nothing"
    assert _cross_file(out) == [], (
        "a blocked turn emitted the cross-file line, which means it paid for "
        "the pass that produces it")
