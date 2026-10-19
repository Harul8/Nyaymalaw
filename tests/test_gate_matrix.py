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

from nm.shared.gates_contracts import (
    GATES,
    Gate,
    Persistence,
    Recovery,
    Response,
    Scope,
    gate,
    withholding,
)
from nm.shared.traceability_contracts import refuses

pytestmark = pytest.mark.class_a


def test_turn_and_need_withholding_have_explicit_distinct_owners():
    turn_withholding = {g.id for g in withholding() if g.scope is Scope.TURN}
    assert turn_withholding == {
        "G-GROUND", "G-ATTRIB", "G-QUOTE", "G-STALE", "G-CORE", "G-COMMIT"}
    assert gate("G-EFFECT").response is Response.WITHHOLD
    assert gate("G-EFFECT").scope is Scope.NEED
    assert gate("G-INCOMPLETE").response is Response.DISCLOSE
    assert gate("G-INCOMPLETE").scope is Scope.NEED
    # 17 Oct 2026: a section still flagged after the rewrites is held back alone.
    held = gate("G-SECTION")
    assert (held.response, held.scope, held.recovery) == (Response.WITHHOLD, Scope.NEED, Recovery.ADVOCATE)


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


def test_every_gate_names_a_feature_and_a_visible_response():
    for g in GATES:
        assert g.feature.strip(), f"{g.id} owns no feature"
        assert len(g.visible.strip()) > 20, (
            f"{g.id} does not say what the advocate sees. A gate whose visible "
            f"response is unspecified will be implemented as silence.")


def test_unbuilt_gates_are_declared_unbuilt():
    """The remaining unbuilt population must be an explicit, current decision.

    THE FIVE SCREEN GATES LANDED ON 8 SEPTEMBER 2026 (BK-34). Until then
    `_run_screens` built five NOT_ASSESSED rows, watched `may_admit_substance`
    refuse them, and admitted substance anyway under a general "slice 10"
    exception — on every matter, while registration told the advocate the
    firm's conflict registry governed the session. Both statements were false.
    Each now has a producer and fires its own gate, so listing them unbuilt
    would be the specification a release behind the code, which `trace` T9
    refuses in as many words.

    G-LIMITATION remained unbuilt until 22 September: date computation alone
    could not establish whether a proposed step depended on that date. DG-02
    now binds a dependency assessment to the exact step and refuses dependent
    or ambiguous steps while leaving independent work available. The served
    tests demonstrate enforcement; live-model classification quality remains
    a separate obligation. A whole-thread block would still be incorrect.
    """
    unbuilt = {g.id for g in GATES if not g.built}
    # DG-02 and the 6 October NMBrain writer/turn wiring cover this inventory.
    # Paired controls in test_limitation_step_gate,
    # test_brain_continuation_record_outcome and
    # test_brain_turn_execution_consumer establish exercised enforcement.
    # Neither this inventory nor those scripted tests certify semantic quality.
    assert unbuilt == set(), (
        "the unbuilt set changed — either something landed, or something "
        "regressed, and both need a deliberate edit here")


