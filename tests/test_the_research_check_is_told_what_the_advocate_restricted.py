"""The research check is told what the advocate restricted, and the purpose (plan AN.27, P4; invariant I2).

The check of the matter's understanding cut a research agenda because the latest message "does not ask for advice or research", and
the correction obeyed. The check now has the purpose in plain words - every matter is researched for each dispute unless the
advocate said not to - and what the interpretation step found the advocate restricted in their latest message, as their exact words
or "none". The first understanding call runs beside the interpretation and is never held up for it.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import plan
from tests.test_core_research import Model, operations, understanding
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a

NONE = ("\n\nInstructions from the advocate limiting our work, as our reading of their latest message found them: none.")


def revising():
    problem = {"verdict": "revise", "problems": [{"problem": "A point is missing.", "fix": "Add it."}]}
    return Model(understanding(1), checks=[problem, {"verdict": "sound", "problems": []}], revisions=[understanding(1)])


def inputs(model, operation):
    return [prompt.user for prompt in model.calls if prompt.operation == operation]


def test_the_check_and_the_correction_are_told_the_advocate_restricted_nothing():
    model = revising()
    plan(model, context("Find the applicable law."), restrictions=lambda: [])
    checks, revisions = inputs(model, "core_research_check"), inputs(model, "core_research_revise")
    assert len(checks) == 2 and len(revisions) == 1
    for seen in checks + revisions:
        assert seen.count(NONE) == 1, "told once, after the conversation and before the understanding"
        assert seen.index(NONE) < seen.index("understanding:\n")
    (first,) = inputs(model, "core_research_understand")
    assert "limiting our work" not in first, "the first call runs beside the interpretation and cannot wait for it"


def test_what_the_advocate_restricted_is_given_in_their_exact_words():
    model = revising()
    plan(model, context("Find the applicable law."), restrictions=lambda: ["Do not research the law yet.", "Leave the notice alone."])
    for seen in inputs(model, "core_research_check") + inputs(model, "core_research_revise"):
        assert "found them: \n- Do not research the law yet.\n- Leave the notice alone.\n" in seen + "\n"
        assert "none." not in seen.split("found them:")[1].split("Your")[0]


@pytest.mark.parametrize("asked", [{}, {"restrictions": lambda: None}])
def test_where_it_is_not_known_what_was_restricted_nothing_is_said_not_none(asked):
    model = revising()
    plan(model, context("Find the applicable law."), **asked)
    for seen in inputs(model, "core_research_check") + inputs(model, "core_research_revise"):
        assert "limiting our work" not in seen


def test_the_restrictions_are_asked_once_and_only_after_the_loop_is_let_go_on():
    order = []
    model = revising()
    plan(model, context("Find the applicable law."), wanted=lambda: order.append("wanted") or True,
         restrictions=lambda: order.append("restrictions") or [])
    assert order[:2] == ["wanted", "restrictions"] and order.count("restrictions") == 1


def test_a_loop_that_is_not_wanted_never_asks_what_was_restricted():
    asked = []
    model = Model()
    plan(model, context("Thank you."), wanted=lambda: False, restrictions=lambda: asked.append(1) or [])
    assert operations(model) == ["core_research_understand"] and asked == []


def test_the_check_states_the_purpose_of_research_in_plain_words():
    purpose = research.CHECK
    assert "Our purpose with every matter is to find where the law stands for each dispute in it" in purpose
    assert "They do not have to ask for that" in purpose
    assert "Do not report research as a problem because the advocate's words did not literally ask for advice" in purpose
    assert "listed after the conversation" in purpose
