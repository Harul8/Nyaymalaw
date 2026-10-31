"""The research check is told that counting extents is code's work (plan AN.27, P24; invariants I6 and S13).

In both replays of the reviewed bundle's first turn it was NM's own check that first said a purchase "does not reconcile" with two
passbooks - its own sum was wrong, since 40 guntas make an acre - and the revising step adopted it; the second replay's answer carried
it. The writer's prompt already says that counting is code's work for extents as it is for days; the check's did not. The check now has
the same sentence, with its point for a check: it does not report figures as disagreeing because they do not seem to add up, it says so
where two papers give different figures for the same land, and it says that figures have not been added up where they might or might
not. A prompt is pinned here, not proved: what the model does with it is measured by a bounded replay. From research v13 and the writer
v14 the rule is said of figures of any kind - areas, sums of money and any other (plan AN.28, D7).
"""
import pytest

from nm.core_engine import research, response_writer
from nm.core_engine.research import plan
from tests.test_core_research import Model
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a

COUNTING = ("Counting is code's work for figures as it is for days: do not add, subtract or convert areas, sums of money or any other "
            "figures yourself")


def words(prompt):
    return " ".join(prompt.split())


def test_the_check_is_told_what_the_writer_is_told_about_counting_extents():
    assert COUNTING in words(research.CHECK)
    assert COUNTING in words(response_writer.SYSTEM_V14), "one rule, said the same way to the step that writes and the step that checks"


def test_the_check_says_what_it_does_and_does_not_do_with_figures():
    check = words(research.CHECK)
    assert COUNTING + ", and do not report that figures disagree because they do not seem to add up." in check
    assert "Where two papers give different figures for the same thing, say so with each figure as it is given;" in check
    assert "where figures might or might not add up, say that they have not been added up." in check


def test_it_is_among_the_instructions_before_the_check_says_what_to_report():
    check = words(research.CHECK)
    assert check.index("Is research being started when the advocate has ruled it out") < check.index(COUNTING) < check.index(
        "Report only problems that matter")


def test_the_call_that_checks_the_understanding_is_given_it_as_its_system_prompt():
    model = Model()
    plan(model, context("Find the applicable law."))
    checks = [prompt for prompt in model.calls if prompt.operation == "core_research_check"]
    assert checks and all(prompt.system == research.CHECK and COUNTING in words(prompt.system) for prompt in checks)


def test_the_purpose_the_check_already_had_is_unchanged():
    check = research.CHECK
    assert "Our purpose with every matter is to find where the law stands for each dispute in it" in check
    assert "Do not report research as a problem because the advocate's words did not literally ask for advice" in check
    assert "Do not invent problems to have something to say." in check
