"""The gate matrix. Slice 2 — one authoritative table, and it must stay one.

WHAT THIS FILE IS DEFENDING
---------------------------
An external review found §7.1 promising that the product "fails closed only on
grounding" while nine conditions elsewhere in the specification blocked
something. Both statements were written in good faith. Prose about failure
handling drifts from the handler within one slice, every time.

So these tests do not check that the document says the right thing. They check
that the table the document renders is the table the code obeys, and that its
own construction rules cannot be broken by the next person to add a gate.
"""
from __future__ import annotations

import pytest

from nm.domain.gates import (
    GATES,
    Gate,
    Persistence,
    Recovery,
    Response,
    Scope,
    gate,
    withholding,
)
from nm.domain.metrics import TurnMetrics
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


def test_the_turn_is_withheld_by_the_grounding_family_and_nothing_else():
    """THE ANSWER TO THE REVIEW'S STOP-SHIP #3, made checkable.

    "Fails closed only on grounding" was wrong as written and right in spirit.
    Precisely: exactly three gates withhold a TURN on quality grounds, and they
    are the grounding family. G-STALE also withholds a turn and is not a
    quality gate at all — it is a concurrency re-derive, and calling that
    "failing closed" is what made the original sentence unfalsifiable.
    """
    turn_withholding = {g.id for g in withholding() if g.scope is Scope.TURN}
    assert turn_withholding == {"G-GROUND", "G-ATTRIB", "G-QUOTE", "G-STALE"}

    quality = turn_withholding - {"G-STALE"}
    assert quality == {"G-GROUND", "G-ATTRIB", "G-QUOTE"}, (
        "if this set grows, §7.1's claim has changed and the document must say so")


def test_a_gate_cleared_by_a_person_carries_a_could_not_evaluate_state():
    """Defect shape S8, refused at construction.

    A screen an actor must clear can always fail to run. Without a third state
    it comes back looking exactly like one that passed — the single most
    repeated defect in the previous build, and the reason twelve mechanical
    checks all went green on a transcript that was wrong throughout.
    """
    for g in GATES:
        if g.recovery in (Recovery.ADVOCATE, Recovery.HUMAN):
            assert len(g.states) >= 3, (
                f"{g.id} is cleared by {g.recovery.value} and has only "
                f"{list(g.states)} — no state for 'could not be evaluated'")


@refuses("P5", 0)
def test_a_two_state_human_cleared_gate_cannot_be_constructed():
    """THE COUNTEREXAMPLE. The rule above is enforced by the type, not by
    review — so adding a bad gate fails at import, not at inspection."""
    with pytest.raises(ValueError, match="could-not-evaluate"):
        Gate(id="G-BAD", condition="something", states=("yes", "no"),
             response=Response.BLOCK, scope=Scope.TURN,
             persistence=Persistence.STICKY, recovery=Recovery.HUMAN,
             visible="x", feature="B3", built=False)


def test_gate_ids_are_unique():
    ids = [g.id for g in GATES]
    assert len(ids) == len(set(ids))


def test_an_unknown_gate_id_raises_rather_than_becoming_a_label():
    """A typo'd gate id must not degrade into free text.

    That is how a gating condition becomes a log line nobody reads: it still
    "fires", it just fires into nothing.
    """
    with pytest.raises(KeyError, match="is not a gate"):
        gate("G-TYPO")


def test_the_response_is_read_from_the_matrix_not_passed_in():
    """The call site reports the condition. The TABLE decides what happens.

    Before this, each site decided for itself — which is exactly how the
    specification came to claim one failure policy while nine sites implemented
    others.
    """
    m = TurnMetrics(turn_id="t")
    assert m.fire("G-POSTURE", "unresolved", "x") is Response.BLOCK
    assert m.fire("G-GROUND", "unsupported", "y") is Response.WITHHOLD
    assert m.fire("G-NOTHELD", "not_held", "z") is Response.DISCLOSE

    # Only the WITHHOLD one becomes a gating violation, and the caller never
    # said so.
    assert [v.rule for v in m.gating_violations] == ["G-GROUND"]


@refuses("D9", 3)
def test_an_out_of_vocabulary_state_is_refused():
    """PRD D9: an out-of-vocabulary facet value is blanked and re-derived,
    never accepted. A gate that accepts any state string cannot be reported
    on — every dashboard over it silently invents categories."""
    m = TurnMetrics(turn_id="t")
    with pytest.raises(ValueError, match="vocabulary"):
        m.fire("G-POSTURE", "probably_fine", "x")


def test_every_gate_names_a_feature_and_a_visible_response():
    for g in GATES:
        assert g.feature.strip(), f"{g.id} owns no feature"
        assert len(g.visible.strip()) > 20, (
            f"{g.id} does not say what the advocate sees. A gate whose visible "
            f"response is unspecified will be implemented as silence.")


def test_unbuilt_gates_are_declared_unbuilt():
    """The screens are slice 10. Listing them as built would be the
    specification describing a product that screens matters when it does not.

    `G-LIMITATION` is the odd one and it is deliberate. D2 computes the
    position and D1 renders it BLOCKED with the reason where it could not be
    computed — so the *state* is built. What is not built is the other half of
    the condition the PRD states: whether the step being recommended is merits
    work that DEPENDS on limitation. "Obtain the sale deed" does not; "file the
    suit" does, and nothing before D5 can tell them apart. Firing on the whole
    set would repeat G-POSTURE's recorded defect — a gate applied to a case it
    was not written for.
    """
    unbuilt = {g.id for g in GATES if not g.built}
    assert unbuilt == {"G-EMERGENCY", "G-CONFLICT", "G-COMPETENCE", "G-SCOPE",
                       "G-CAPACITY", "G-LIMITATION"}, (
        "the unbuilt set changed — either something landed, or something "
        "regressed, and both need a deliberate edit here")
