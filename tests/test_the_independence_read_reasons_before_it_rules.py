"""THE STEP-INDEPENDENCE READ REASONS BEFORE IT RULES, AND IS GIVEN THE TEST.

`nm.core.step_dependency` decides whether a proposed step may pass G-LIMITATION
while the limitation position is unresolved. A model sits inside that gate
boundary -- R2, "the open hole" -- and until 23 September 2026 nobody had
measured how it behaves.

MEASURED, on eighteen labelled steps, through the same adapter, the same
`guided` composition and the same ledger the live matters use:

    as shipped          10/18 correct   unsafe clear 0/10   safe block 8/8
    the test alone      11/18           0/10                7/8
    reason first alone  11/18           0/10                7/8
    BOTH, run 1         16/18           0/10                2/8
    BOTH, run 2         15/18           0/10                3/8

As shipped it answered `dependent` for every step -- a constant, not a
classifier -- so G-LIMITATION withheld every recommended step on any matter
whose limitation was unresolved. Live matter 4 lost exactly the step the
advocate asked for: "Obtain a copy of the charge sheet ... since the case is
listed for hearing on 6 October 2026", judged dependent because a hearing date
"necessitates the assumption of legal timelines".

Neither change works alone. These tests hold BOTH, because removing either one
puts the classifier back at 7 of 8 refused -- and a test that held only one
would pass while the product went back to refusing almost everything.

WHAT THESE TESTS DO NOT CLAIM. They are structural: the order and the test are
present. Whether the model then classifies well is a MEASUREMENT, re-run by
the harness above through the ledger, and it is not a unit test's to assert.
"""
from __future__ import annotations

import pytest

from nm.core import step_dependency

pytestmark = pytest.mark.class_a


def test_the_reason_is_emitted_before_the_verdict():
    """Strict structured output generates properties in schema order. With the
    verdict first, the model commits before it has reasoned."""
    order = list(step_dependency.schema_for("any step")["properties"])
    assert order.index("reason") < order.index("dependence"), (
        f"the schema emits {order}: the verdict comes before the reason, which "
        f"measured at 8 of 8 independent steps refused")


def test_the_prompt_gives_the_definition_as_a_test():
    """Independence of the limitation position means: right whichever way that
    position is settled. The model is told to apply exactly that."""
    system = step_dependency.build_prompt("any step", "context").system
    assert "EITHER way" in system and "BOTH answers" in system, (
        "the counterfactual test is gone from the prompt")


def test_a_scheduled_date_is_named_as_urgency_not_limitation():
    """The live failure's own shape: a hearing date read as a time-bar."""
    system = step_dependency.build_prompt("any step", "context").system
    assert "scheduled against" in system and "says when to act" in system


def test_the_unknown_state_and_the_fail_closed_binding_survive():
    """The repair must not loosen the part that makes the gate safe: an answer
    not bound to the exact step, or with no reason, is UNKNOWN -- and UNKNOWN
    is treated as dependent by the engine."""
    step = "Ask the client for the bank statements."
    bad = step_dependency.assess({"reason": "x", "step": "another step",
                                  "dependence": "independent"}, step, "ctx")
    assert bad.dependence is step_dependency.Dependence.UNKNOWN
    empty = step_dependency.assess({"reason": " ", "step": step,
                                    "dependence": "independent"}, step, "ctx")
    assert empty.dependence is step_dependency.Dependence.UNKNOWN


# ------------------------------------------------ the verdict is derived ---
#
# Live matter 4, after everything above: told the reason first, given the
# either-way test, AND told exactly which position was unresolved, the read
# still called "Request a copy of the charge sheet from the police" dependent.
# The abstract test is the part the model cannot hold, so it now answers the
# two halves and CODE derives the verdict. These state the derivation.

STEP = "Request a copy of the charge sheet from the police."


def _answer(in_time, out_of_time, said="dependent"):
    return {"reason": "r", "step": STEP, "right_if_in_time": in_time,
            "right_if_out_of_time": out_of_time, "dependence": said}


@pytest.mark.parametrize("in_time,out_of_time,said,expected", [
    ("yes", "yes", "independent", "independent"),
    ("yes", "no", "dependent", "dependent"),
    ("no", "yes", "dependent", "dependent"),
    ("no", "no", "dependent", "dependent"),
    ("yes", "unknown", "independent", "unknown"),
    ("unknown", "unknown", "unknown", "unknown"),
])
def test_released_only_when_right_on_both_answers_and_the_verdict_agrees(
        in_time, out_of_time, said, expected):
    got = step_dependency.assess(_answer(in_time, out_of_time, said), STEP, "ctx").dependence
    assert got.value == expected


def test_any_no_is_dependent_whatever_the_label_says():
    """The safe direction needs no agreement: a step wrong on either answer
    depends on which answer it is, even if the model wrote `independent`."""
    assert step_dependency.assess(_answer("no", "yes", said="independent"), STEP,
                                  "ctx").dependence is step_dependency.Dependence.DEPENDENT


def test_halves_that_contradict_the_verdict_release_nothing():
    """THE MEASURED UNSAFE CASE. On the labelled set the model reasoned that
    condonation "hinges on the limitation position", said dependent, and
    answered yes/yes to the halves. The first derivation trusted the halves and
    RELEASED it. An answer that disagrees with itself is not an answer: it is
    UNKNOWN, which the gate treats as dependent."""
    got = step_dependency.assess(_answer("yes", "yes", said="dependent"), STEP, "ctx")
    assert got.dependence is step_dependency.Dependence.UNKNOWN


def test_the_read_is_told_whose_position_is_unresolved():
    """Given only the file note, the read invented a limitation period on
    requesting a document. It is told the position, whose it is, and that it is
    the only limitation question in issue."""
    theirs = step_dependency.position_context(False, "which provision governs", "FILE")
    assert "OPPOSING party's claim" in theirs
    assert "ONLY limitation question" in theirs
    assert "which provision governs" in theirs
    assert "OUR CLIENT's own claim" in step_dependency.position_context(True, "x")
