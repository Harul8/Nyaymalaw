"""THE LAYOUT CHECK MUST BE ABLE TO FAIL. BK-43-AC1, BK-47-AC1. P36.

WHAT THESE DEFEND
-------------------
Two checks that were unable to fail, and both reported green for a week.

    `body { overflow-x: hidden }` made `scrollWidth == clientWidth` whatever
    the content did. The rule is gone; the QUESTION was still wrong, because
    an `overflow: hidden` on any inner container clips a control while the
    document measures exactly its viewport.

    `if page.is_visible("#rail"): return` made the desktop width assert
    nothing past sign-in, and the report showed three green rows for three
    widths, one of which had done no work.

Every test here is paired: the thing that must fail, and the thing that must
NOT -- because a check that refuses everything is turned off within a week and
the population grows behind it.
"""
from __future__ import annotations

import pytest

from tools.layout import (
    MEASURE_JS,
    REQUIRED_ACTIONS,
    WIDTHS,
    Box,
    Control,
    Did,
    clipped,
    from_measurement,
    measured,
    population_problems,
    unexecuted,
)

pytestmark = pytest.mark.class_a

VIEWPORT = Box(left=0, top=0, right=390, bottom=844)


def _control(name="sign out", left=10, right=120, top=10, bottom=44,
             clips=(VIEWPORT,), scrollable=(False,), hidden=False) -> Control:
    return Control(name=name, rect=Box(left=left, top=top, right=right,
                                       bottom=bottom),
                   clips=tuple(clips), scrollable=tuple(scrollable),
                   hidden=hidden)


# ============ 1. BK-43-AC1 -- clipped content, with overflow hidden =========

def test_a_control_inside_every_clip_is_reachable():
    """THE POSITIVE CONTROL. Without it this file proves only that something
    can be reported, not that ordinary layout passes."""
    assert clipped((_control(),)) == ()


def test_a_control_outside_a_clipping_container_is_unreachable():
    """THE DEFECT BK-43 NAMES, and the document does not scroll sideways here.

    The rail is 260px wide and clips its overflow. The control sits at x=300,
    inside the 390px viewport and outside the rail. `scrollWidth` equals
    `clientWidth`; the advocate cannot reach the control.
    """
    rail = Box(left=0, top=0, right=260, bottom=844)
    why = clipped((_control(left=300, right=380, clips=(rail, VIEWPORT),
                            scrollable=(False, False)),))
    assert why, "a control outside an overflow:hidden container was not named"
    assert "clips its overflow" in why[0]
    assert "does not scroll sideways" in why[0]


def test_the_same_control_inside_a_scrolling_container_is_reachable():
    """A scrolling rail is ordinary, correct layout. Refusing it would fail
    every long list in the product, and the check would be switched off."""
    rail = Box(left=0, top=0, right=260, bottom=844)
    assert clipped((_control(left=300, right=380, clips=(rail, VIEWPORT),
                             scrollable=(True, False)),)) == ()


def test_an_inner_scroller_cannot_undo_an_outer_clip():
    """The chain is walked outermost-last and every non-scrolling ancestor
    intersects. An inner scroller bringing a control into ITS box says nothing
    about the fixed box outside it."""
    inner = Box(left=0, top=0, right=900, bottom=844)      # scrolls
    outer = Box(left=0, top=0, right=260, bottom=844)      # clips
    assert clipped((_control(left=300, right=380,
                             clips=(inner, outer, VIEWPORT),
                             scrollable=(True, False, False)),))


def test_a_control_off_the_right_edge_of_the_viewport_is_unreachable():
    """The viewport is the outermost clip, and it is not scrollable for this
    purpose: a control at x=800 on a 390px phone is off the screen."""
    assert clipped((_control(left=800, right=900),))


def test_a_control_that_was_never_rendered_is_a_different_answer():
    """Hidden and clipped are different defects with different fixes, and
    reporting geometry for something nobody rendered sends the reader looking
    at a layout problem that is not there."""
    why = clipped((_control(hidden=True),))
    assert why and "not rendered at all" in why[0]


def test_a_zero_sized_control_is_named():
    why = clipped((_control(left=10, right=10),))
    assert why and "nothing to click" in why[0]


def test_an_empty_measurement_proves_nothing_and_says_so():
    """§9. `clipped(())` is empty and that must never read as a clean page.
    `measured` is what the browser phase asserts before believing the result."""
    assert clipped(()) == ()
    assert measured(()) == 0
    assert measured((_control(),)) == 1


def test_the_measurement_reads_every_ancestor_and_not_a_guessed_container():
    """STRUCTURAL, over the snippet itself. The rule that produced BK-43 sat
    518 lines from the comment explaining its own removal; a check that looked
    at one container would have missed it there too."""
    assert "parentElement" in MEASURE_JS
    assert "getComputedStyle" in MEASURE_JS
    assert "overflowX" in MEASURE_JS and "overflowY" in MEASURE_JS
    # AND IT DOES NOT ASK THE DOCUMENT FOR ITS SCROLL WIDTH. That question is
    # the one a style rule can answer for it.
    assert "scrollWidth" not in MEASURE_JS


def test_the_measurement_takes_the_candidate_that_actually_renders():
    """"However this width offers it" is BK-32's rule, and it is why a
    selector may name several controls.

    `querySelector` alone returns the first match in DOCUMENT order, which at
    1280px is a drawer toggle that is correctly hidden there -- and the check
    then reported the navigator unreachable on a page showing it the whole
    time. The browser caught that; this keeps it caught.
    """
    assert "split(','" in MEASURE_JS
    assert "candidates.find(renders)" in MEASURE_JS
    # AND WHEN NONE RENDERS THE ROW IS STILL EMITTED, hidden. An omitted row
    # is a control nobody checked wearing the appearance of one that passed.
    assert "candidates.find(Boolean)" in MEASURE_JS


def test_a_measurement_round_trips_into_controls():
    rows = [{"name": "sign out", "hidden": False,
             "rect": {"left": 300, "top": 10, "right": 380, "bottom": 44},
             "clips": [{"left": 0, "top": 0, "right": 260, "bottom": 844},
                       {"left": 0, "top": 0, "right": 390, "bottom": 844}],
             "scrollable": [False, False]}]
    controls = from_measurement(rows)
    assert measured(controls) == 1
    assert clipped(controls)


def test_a_missing_element_measures_as_hidden_rather_than_as_absent():
    """`querySelector` returning null is a control that is not on the page,
    and the snippet says so rather than omitting the row -- an omitted row is
    a control nobody checked wearing the appearance of one that passed."""
    controls = from_measurement([{"name": "sign out", "hidden": True,
                                  "rect": {}, "clips": [], "scrollable": []}])
    assert measured(controls) == 1
    assert clipped(controls)


# =========== 2. BK-47-AC1 -- every width executes every action =============

def _all_ran() -> dict[str, Did]:
    return {action: Did.RAN for action in REQUIRED_ACTIONS}


def test_a_width_that_ran_everything_has_no_problems():
    """THE POSITIVE CONTROL."""
    assert unexecuted(_all_ran()) == ()
    assert population_problems({w: _all_ran() for w, _ in WIDTHS}) == ()


def test_visible_is_not_reached():
    """THE DEFECT BK-47 NAMES, in one line: `if page.is_visible("#rail"):
    return`. The control was on screen and was never used."""
    ran = _all_ran()
    ran["find another matter in the navigator"] = Did.SEEN
    why = unexecuted(ran)
    assert why and "was visible and was never used" in why[0]


def test_an_action_absent_from_the_mapping_is_not_permitted():
    """The default that lets a phase omit a key and pass is the whole defect."""
    ran = _all_ran()
    del ran["sign out"]
    assert any("not attempted" in why for why in unexecuted(ran))


def test_a_width_that_recorded_nothing_is_the_loudest_failure():
    """THE BACKLOG'S NEGATIVE CONTROL: *skip desktop navigation because the
    rail is visible* -> the population control rejects the unexecuted route.

    An early return leaves NO ROW, not a red one, and a runner counting green
    rows sees three of three.
    """
    partial = {w: _all_ran() for w, _ in WIDTHS}
    del partial[1280]
    why = population_problems(partial)
    assert why and "1280px executed no required action at all" in why[0]


def test_the_population_is_every_declared_width_times_every_action():
    """Read from `WIDTHS` and `REQUIRED_ACTIONS`, so a width or an action
    added tomorrow is required by this test without anybody editing it."""
    why = population_problems({})
    assert len(why) == len(WIDTHS)
    why = population_problems({w: {} for w, _ in WIDTHS})
    assert len(why) == len(WIDTHS) * len(REQUIRED_ACTIONS)


def test_390_is_a_supported_width():
    """The one the product kept failing at, named rather than assumed."""
    assert 390 in {w for w, _ in WIDTHS}
    assert {w for w, _ in WIDTHS} == {390, 768, 1280}


def test_only_ran_proves_reachability_and_it_is_written_once():
    """No width decides for itself what counts as having done the work."""
    assert Did.RAN.proves_reachable is True
    assert Did.SEEN.proves_reachable is False
    assert Did.NOT_ATTEMPTED.proves_reachable is False
    assert Did.not_established() is Did.NOT_ATTEMPTED


def test_the_required_actions_cover_the_criterion_and_the_new_flows():
    """BK-32-AC1 names start, find, switch, research, History, identity and
    sign-out; P29 to P32 added preparation, which must be reachable too or the
    flows this release built are desktop-only."""
    joined = " | ".join(REQUIRED_ACTIONS)
    for needed in ("start", "find", "switch", "research", "history",
                   "identity", "sign out", "preparation", "case file"):
        assert needed in joined.lower(), needed
