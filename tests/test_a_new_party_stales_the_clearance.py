"""ADDING A PARTY MAKES AN EARLIER CONFLICT CLEARANCE STALE. BK-34, B3.

THE MECHANISM EXISTED AND NOTHING CALLED IT
---------------------------------------------
`Screen.stale_for` has answered this since B3 landed. Asked on 10 September
2026 which functions call it, the code graph returned exactly one -- a unit
test in `test_screens.py`. No production caller anywhere.

So an advocate who named a guarantor on turn six was shown the conflict
clearance from turn one, which had never seen that name, and nothing said so.
The rule was written, tested in isolation, and unwired: a hundred good rules
with no runner is the failure this repository opens by describing.

WHAT IS AND IS NOT THE DEFECT
-------------------------------
The screen genuinely cannot run on the turn that names the party. It sits in
ADMIT-A, before this turn's words are read by anything, so screening a name
given today would mean admitting the brief first -- which is exactly what B3
forbids. `turn.py` says so in terms: *"a party named today is screened from
tomorrow."*

That sequencing is correct and this test does not challenge it. What was
missing is that the advocate was never TOLD the clearance in front of them did
not cover the name they had just given. A recorded assurance nobody gave is
worse than no assurance, which is what `Screen.covers` was built to prevent.
"""
from __future__ import annotations

import pytest

from nm.core.screens import Screen, ScreenKind, ScreenState

pytestmark = pytest.mark.class_a


def _cleared(*covers: str) -> Screen:
    return Screen(kind=ScreenKind.CONFLICT, state=ScreenState.CLEAR,
                  detail="checked against your other files",
                  covers=frozenset(covers))


def test_a_clearance_names_the_parties_it_never_saw():
    """THE RULE. `stale_for` says THAT; `uncovered` says WHICH.

    A disclosure that cannot name the party is one the advocate cannot act
    on. "The check may not cover everyone" is a worry; "it did not cover the
    guarantor you just named" is a next step.
    """
    screened = _cleared("acme", "beta")

    assert screened.uncovered(frozenset({"acme"})) == ()
    assert screened.uncovered(frozenset({"acme", "beta"})) == ()
    assert screened.uncovered(frozenset({"acme", "gamma"})) == ("gamma",)
    assert screened.uncovered(frozenset({"delta", "gamma"})) == (
        "delta", "gamma"), "every uncovered name is reported, not just one"


def test_which_and_whether_agree():
    """They are one rule and must not be able to disagree.

    `stale_for` true with `uncovered` empty would be a disclosure with nothing
    to say; `stale_for` false with names in `uncovered` would be a clearance
    quietly covering someone it never screened.
    """
    screened = _cleared("acme", "beta")
    for parties in (frozenset({"acme"}), frozenset({"acme", "beta"}),
                    frozenset({"acme", "gamma"}), frozenset({"delta"}),
                    frozenset()):
        assert screened.stale_for(parties) == bool(screened.uncovered(parties)), (
            f"stale_for and uncovered disagree about {sorted(parties)}")


def test_the_turn_engine_asks_rather_than_computing_it():
    """THE WIRING, which is the half that was missing.

    `stale_for` was correct and unreachable. Asserting the rule alone would
    have passed on 9 September, when no production code called it at all, so
    this asserts the CALL -- and asserts the engine asks the screen rather
    than recomputing `parties - covers` for itself, because that copy is where
    a normalisation drifts and the check silently stops matching.
    """
    import inspect

    from nm.core.turn import TurnEngine

    body = inspect.getsource(TurnEngine._read_parties)
    assert "stale_for" in body, (
        "the party read no longer consults the clearance, so a party named "
        "this turn is silently covered by a screen that never saw it")
    assert "uncovered(" in body, (
        "the party read no longer asks WHICH parties are uncovered")
    assert "- conflict.covers" not in body, (
        "the engine recomputes the set difference instead of asking the "
        "screen -- a second copy of a rule that has an owner")
    assert ".clears" in body, (
        "the engine tests the screen state itself instead of asking "
        "`Screen.clears`, which is the second copy that property exists to "
        "refuse")


def test_an_unassessed_screen_is_not_a_stale_clearance():
    """A screen that never ran is not a clearance that stopped applying.

    Without this the disclosure would fire on every turn that names anybody,
    while the screens are all NOT_ASSESSED -- saying "the check did not cover
    X" about a check that has not run at all. The screen row already says it
    has not run, and two messages about one fact is how an advocate learns to
    read neither.
    """
    never_ran = Screen(kind=ScreenKind.CONFLICT,
                       state=ScreenState.NOT_ASSESSED,
                       not_assessed_because="B3 is not built on this slice")
    assert not never_ran.clears, (
        "a NOT_ASSESSED screen reported itself as a clearance")

    import inspect

    from nm.core.turn import TurnEngine
    body = inspect.getsource(TurnEngine._read_parties)
    assert "conflict.clears" in body, (
        "the disclosure is not guarded by the screen having actually cleared, "
        "so it would fire about a check that never ran")
