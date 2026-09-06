"""B-078 — what the answer SHOWS, and what the step is ABOUT.

E-102's judge, on the first judged run: the register is instructional rather
than peer-to-peer. Two things earned that verdict and they are different
defects with the same symptom.

ONE — THE WHOLE BARE ACT IN THE ADVOCATE'S FACE
-------------------------------------------------
*Earlier turns reproduced the full bare-act text of Article 14 as the ground.*
The register row names the conflation exactly: how much of a retrieved span
the ANSWER renders is a presentation question, and the verbatim requirement is
about what can be READ BACK. The gate reads `findings[].span` and never the
element text, so a shorter rendering cannot weaken it.

TWO — A STEP WITH NOTHING SPECIFIC TO BE ABOUT
------------------------------------------------
*"Ensure the letter explicitly acknowledges the debt and contains a promise to
pay or a request for a specific payment plan"* — read as guiding a lay client
on drafting, rather than analysing with a peer whether the 12 June letter they
ALREADY HOLD satisfies s.18.

That is not a tone failure, and D5.1 says in as many words that this family of
problem needs A RULE AND NOT A TONE INSTRUCTION. The step described what a
compliant document would contain, which is the section restated and the
advocate can read the section. What they cannot read off the section is
whether the thing in their file does the job.

The frame carries it. `ProofPosition` says exactly that — HELD on named
material, OBTAINABLE with the material named, ABSENT with the dead end — it
was computed earlier in the turn and persisted on the thread, and the one read
whose whole job is to say what to do next was not being shown it.

WHAT THESE TESTS DO NOT DECIDE
--------------------------------
Whether the register READS as peer-to-peer. That is E-102, it is judged, and a
judged run needs explicit per-run approval. These assert the two structural
properties the verdict rested on; the verdict itself is re-run by a person.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.core.turn import EXCERPT, _excerpt, _positions_note, _shortened
from nm.domain.matter import Side, Thread
from nm.domain.proof import Burden, ProofPosition, ProofStatus, Standard

pytestmark = pytest.mark.class_a

ARTICLE_14 = (
    "For the price of goods sold and delivered where no fixed period of "
    "credit was agreed. Three years. The date of the delivery of the goods, "
    "and a further clause carrying the text well past the cap so the "
    "behaviour on a long span is exercised rather than assumed.")


def _pos(element, status, **kw):
    return ProofPosition(
        element=element, burden=Burden(on=Side.MOVING), status=status,
        standard=(Standard.BALANCE_OF_PROBABILITIES
                  if status is not ProofStatus.NOT_ASSESSED
                  else Standard.NOT_ESTABLISHED), **kw)


# ===================== one: shown is not the same as verified ===============

def test_a_ground_does_not_reproduce_the_whole_provision():
    """THE DEFECT, AS A RULE. An advocate knows what the Article says; what
    they need from a ground is WHICH provision was read and a handle to read
    the rest, which is the locator beside it."""
    assert len(_excerpt(ARTICLE_14)) <= EXCERPT + 1
    assert len(ARTICLE_14) > EXCERPT, (
        "the fixture is shorter than the cap, so this asserts nothing")
    assert _shortened(ARTICLE_14)


def test_the_excerpt_ends_on_a_sentence_and_not_mid_word():
    """`[:400]` cuts mid-word, and text that reads as broken is text an
    advocate discounts — the opposite of what a ground is for."""
    out = _excerpt(ARTICLE_14)
    assert out.endswith("."), out
    assert ARTICLE_14.startswith(out), (
        "the excerpt is not a prefix of the span, so the grounding gate "
        "cannot find the product's own quotation in what was retrieved")


def test_a_span_short_enough_is_left_whole_and_not_flagged():
    """THE BOUND. A rule that truncated everything would pass the test above
    and turn every short provision into an excerpt of itself."""
    short = "Three years from the date of delivery."
    assert _excerpt(short) == short
    assert not _shortened(short)


def test_the_ellipsis_is_never_inside_the_quotation_marks():
    """LOAD-BEARING, NOT TYPOGRAPHIC.

    `nm.core.grounding` pulls quoted runs out of an element and looks for them
    in the retrieved text. An ellipsis inside the quotes would make the
    product fail to find its OWN excerpt and withhold the turn on its own
    rendering — the grounding gate firing on the product's own prose, which is
    the shape B-019 already was.
    """
    import pathlib as _p

    body = (_p.Path(__file__).resolve().parents[1]
            / "nm" / "core" / "turn.py").read_text(encoding="utf-8")
    assert '"{_excerpt(f.span)}"' in body, (
        "the ground no longer renders an excerpt inside quotes; if that "
        "changed deliberately, the gate interaction has to be re-reasoned")
    assert '" [...]" if _shortened' in body, (
        "the shortening marker moved inside the quotation, so the grounding "
        "gate will look for an ellipsis in the bare Act and not find it")


def test_the_gate_still_verifies_the_shortened_ground():
    """THE SAFETY PROPERTY, checked rather than reasoned about. The whole
    point is that rendering less does not verify less."""
    from nm.core.grounding import verify_quotes
    from nm.domain.answer import Element, ElementKind
    from tests.test_turn_contract import finding as _finding

    span = ARTICLE_14
    element = Element(
        kind=ElementKind.GROUND, thread="t",
        text=f'Article 14 — "{_excerpt(span)}" [...] (Schedule I)')
    found = _finding(ref="Article 14", span=span, locator="Schedule I")

    violations = verify_quotes((element,), (found,))
    assert not violations, (
        f"the gate refused the product's own excerpt: {violations}")


# ================ two: the step is about what the file holds ================

def test_the_recommendation_is_shown_what_the_file_establishes():
    """B-078's second half. The step had nothing specific to be about, so it
    described the general case — what a compliant letter would contain rather
    than what the letter on the file does."""
    thread = replace(Thread.create(label="t"), proof=(
        _pos("An acknowledgment in writing signed by the party",
             ProofStatus.HELD, material=("the letter of 12 June 2024",)),
        _pos("That it was made before the period expired",
             ProofStatus.OBTAINABLE,
             closing_material="the postal receipt, ordinarily with the client"),
    ))
    note = _positions_note(thread)

    assert "the letter of 12 June 2024" in note, (
        "the step is not told what the file holds, so it can only describe "
        "what such a document should contain — which is E-102's verdict")
    assert "the postal receipt" in note
    assert "not about what such material should look like" in note


def test_a_position_nobody_assessed_is_not_offered_as_a_step():
    """NOT_ASSESSED says nobody worked it out. Handing that to a read whose
    output is an imperative invites a step recommended on an element nobody
    examined, which is worse than saying nothing."""
    thread = replace(Thread.create(label="t"), proof=(
        _pos("The terms of repayment", ProofStatus.NOT_ASSESSED),))
    assert _positions_note(thread) == ""


def test_a_thread_with_no_positions_adds_nothing():
    """A heading with nothing under it is prompt budget spent on a heading."""
    assert _positions_note(Thread.create(label="t")) == ""


def test_an_absent_element_reaches_the_step_with_its_dead_end():
    """D5.1's direction, carried through. A step that never hears "nothing
    would establish this" recommends looking for it."""
    thread = replace(Thread.create(label="t"), proof=(
        _pos("A registered instrument", ProofStatus.ABSENT,
             dead_end="the transaction was never reduced to writing"),))
    note = _positions_note(thread)
    assert "NOTHING WOULD ESTABLISH" in note
    assert "never reduced to writing" in note


def test_the_rule_is_about_subject_matter_and_not_about_tone():
    """D5.1: *it needs a RULE, NOT A TONE INSTRUCTION.* A prompt that said
    "sound like a peer" would be the politeness layer that document forbids;
    this says what the step must be ABOUT.
    """
    import inspect

    from nm.core.turn import TurnEngine
    from nm.domain.register import PEER

    body = inspect.getsource(TurnEngine._recommend)

    # THE WORDS MOVED, AND THAT IS THE POINT. This rule got its own wording
    # here first, because the recommendation was the only prompt E-102 had
    # caught. Re-judged on 6 September the judge quoted the theory and the
    # adversarial reads instead -- five more prompts with no register rule at
    # all -- so the clause moved to `nm.domain.register` and this reaches it.
    # Six copies of a sentence drift within a slice.
    assert "+ PEER +" in body
    assert "Where the file already holds the material" in PEER
    assert "the section restated" in PEER

    assert "_positions_note(thread)" in body, (
        "the rule is in the prompt and the material it needs is not, which "
        "makes it exactly the tone instruction D5.1 says will not work")
