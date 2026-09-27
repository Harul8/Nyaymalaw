"""Installed explanation ownership, not a claim of live semantic quality."""

import pytest

from nm.legal_brain.brain_release import ReviewService
from nm.legal_brain.verifier import IndependentVerifier
from nm.legal_brain.working_explanation import WorkingExplanationService
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope
from tests.test_independent_claim_verifier import Judge

pytestmark = pytest.mark.class_a


def test_actual_composition_uses_one_source_scope_and_final_boundary_population(client):
    app, _matter, scope = _scope(client)
    verifier = IndependentVerifier(Judge())
    reviewer = ReviewService(
        store=app.store, log=MatterLoopLog(app.store, advocate_id=scope.advocate_id),
        verifier=verifier, session_current=lambda: True, cost_ceiling=lambda *_: 0.03)
    brain = app.controlled_brain_for(
        scope, session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        source_version=app.source_generation_guard().version,
        table_version="actual-test-tables", reviewer=reviewer)
    service = brain.working_explanations
    assert type(service) is WorkingExplanationService
    assert service.working is brain.working_review
    assert service.scope is brain.working_scope
    assert service.finalizer is brain.finalizer
    assert service.reader.model is verifier.model
    assert service.reader.store is app.store
    assert service.reader.log is brain.log
    assert service.reader.subject_packages == brain.working_review.owner.packages
    assert brain.early_review.verifier is verifier
    assert brain.early_review.log is brain.log
    assert "check_candidate_independently" in brain.registry._tools
    assert brain.input_continuations.reviewer is reviewer
    assert set(brain.input_continuations.binding_owners) == {"limitation", "interest", "fee"}
    assert brain.fee_selection_review.owner.source_owner is brain.working_review.owner
    assert brain.registry._tools["court_fee"].handler.__module__ == "nm.legal_brain.reviewed_fee_selection"
    assert not app.store.load(_matter.id).loop_records
    assert not app.store.load(_matter.id).turn_receipts


def test_no_independent_owner_does_not_install_a_source_only_explanation_fallback(client):
    app, _matter, scope = _scope(client)
    brain = _compose(app, scope)
    assert brain.working_explanations is None
    assert brain.working_review is None and brain.working_scope is None
    assert brain.early_review is None and brain.input_continuations is None
    assert "check_candidate_independently" not in brain.registry._tools
    assert brain.fee_selection_review is None
