"""Terminal holds use intact reviewed evidence, not the offered catalogue."""
from copy import deepcopy

import pytest

from nm.brain import turn
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import addressed_sources
from nm.shared.model_port import SchemaViolation
from tests.test_brain_dispute_conflict_review_mechanics import (
    Model,
    candidate,
    decision,
    treatments,
)

FIRST = "The custodian did not return the inventory."
SECOND = "The client does not know who collected it."
LATEST = FIRST + " " + SECOND


def prepared():
    proposed = candidate(FIRST)
    rows = treatments((), LATEST, roles={"L2": "examination_material"})
    state = {}
    model = Model({"verdicts": [decision("C1", "independent_dispute", accept=True,
                                        source="L1", words=FIRST)]})
    accepted = verify_disputes(model, candidates=(proposed,), earlier=(), latest=LATEST,
                               active_disputes=(), source_treatments=rows, review_state=state)
    assert accepted == (proposed,)
    _, latest, prior = addressed_sources((), LATEST)
    return proposed, state, latest, prior


def offered_catalogue(monkeypatch):
    """Simulate the planned expansion without changing checked proof."""
    monkeypatch.setattr(turn, "candidate_account_ids", lambda candidate, latest, prior: set(latest))


def test_unselected_changed_source_preserves_checked_peer_without_recovery_call(monkeypatch):
    proposed, state, latest, prior = prepared()
    before = deepcopy(state)
    offered_catalogue(monkeypatch)

    affected = turn._affected_proposals((proposed,), ("L2",), latest, prior, review_state=state)

    assert affected == set() and state == before


def test_selected_source_change_still_holds_dependent_proposal(monkeypatch):
    proposed, state, latest, prior = prepared()
    offered_catalogue(monkeypatch)

    assert turn._affected_proposals((proposed,), ("L1",), latest, prior,
                                   review_state=state) == {proposed}


def test_unreviewed_proposal_cannot_borrow_another_proofs_dependencies(monkeypatch):
    proposed, state, latest, prior = prepared()
    new = candidate(SECOND)
    offered_catalogue(monkeypatch)

    assert turn._affected_proposals((proposed, new), ("L2",), latest, prior,
                                   review_state=state) == {new}


def test_tampered_review_cache_is_not_used_to_preserve_work():
    proposed, state, latest, prior = prepared()
    state["cache"].decisions["C1"]["account_check"]["source_ids"] = []

    with pytest.raises(SchemaViolation, match="intact code-issued cache"):
        turn._affected_proposals((proposed,), ("L2",), latest, prior, review_state=state)


def test_changed_proposal_cannot_inherit_original_review():
    proposed, state, latest, prior = prepared()
    rewritten = candidate(FIRST, statement="The client admitted taking the inventory.")

    with pytest.raises(SchemaViolation, match="changed an original reviewed proposal"):
        turn._affected_proposals((rewritten,), ("L2",), latest, prior, review_state=state)


def test_unavailable_assignment_still_holds_otherwise_independent_source():
    from dataclasses import replace
    proposed, _, latest, prior = prepared()
    linked = replace(proposed, dispute_ids=("removed-issue",))

    assert turn._affected_proposals((linked,), (), latest, prior, ("removed-issue",)) == {linked}
