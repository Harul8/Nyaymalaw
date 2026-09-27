"""Current v7 wording and working/scope children share the actual saved parent."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from nm.legal_brain.evaluate.brain_evaluation import EvaluationService
from nm.legal_brain.verify.brain_finalization import SavedCheckReader
from nm.legal_brain.verify.interaction_review import InteractionReviewService
from nm.legal_brain.verify.interaction_subject import InteractionSubjectOwner
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits
from nm.legal_brain.reason.working_record import area_id
from nm.legal_brain.reason.working_record_contracts import AnalysisArea
from nm.shared.budget_contracts import Budget
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_communication_premises_require_their_own_assessment import PremiseJudge
from tests.test_working_record_is_source_owned_and_independently_scoped import _case

pytestmark = pytest.mark.class_a


def composed_working_case(tmp_path, *, annotate=False, source=False, needed=(), covered=()):
    store, outcome, owner, working, scope, scope_judge, verifier, brain = _case(
        tmp_path, annotate=annotate, source=source, return_brain=True
    )
    scope_judge.needed, scope_judge.covered = needed, covered
    interaction_owner = InteractionSubjectOwner(
        principles=brain.principles, source_current=lambda *_: True
    )
    interaction_model = PremiseJudge()
    reader = SavedCheckReader(
        store=store,
        log=MatterLoopLog(store, advocate_id=outcome.record.identity.advocate_id),
        model=interaction_model,
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
        subject_packages=interaction_owner.packages,
        max_tokens=4096,
    )
    brain.interaction_review = InteractionReviewService(
        reader=reader, owner=interaction_owner, protocol_version=7
    )
    brain.working_review, brain.working_scope = working, scope
    assessment = Mock()
    evaluator = EvaluationService(brain, assessment, monotonic=lambda: 100.0)
    return (
        store,
        outcome,
        owner,
        working,
        scope,
        scope_judge,
        verifier,
        interaction_model,
        evaluator,
    )


def run_composed_working(evaluator):
    return evaluator.run(
        matter_id="mat_loop",
        turn_id="work-parent",
        message="Which rule was read?",
        limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=30), 30, 400
        ),
        max_repairs=0,
    )


def test_serial_candidate_wording_and_scope_reviews_use_actual_shared_journal_and_budget(tmp_path):
    values = composed_working_case(tmp_path, annotate=True, source=True)
    store, parent, owner, _working, _scope, scope_judge, _verifier, _interaction, evaluator = values
    _inventory, annotations, _packages = owner.candidates(parent, store.load("mat_loop"))
    area = area_id("thread_one", AnalysisArea.ACT_PASSAGES)
    scope_judge.needed = scope_judge.covered = (area, annotations[0].need_ids[0])
    result = run_composed_working(evaluator)
    assert result.stop == "interaction_checks_complete_private_candidate"
    assert len(result.working_reviews) == len(result.interaction_reviews) == 1
    assert len(result.working_scope_reviews) == len(result.working_completeness) == 1
    assert result.working_completeness[0].complete
    children = store.load("mat_loop").loop_records[1:]
    assert len(children) == 3
    assert ":verify:" in children[0].identity.turn_id
    assert children[1].identity.turn_id.endswith(":check:communication_premises")
    assert children[2].identity.turn_id.endswith(":check:working_scope_v1")
    assert children[0].events[0].payload["parent"] == parent.record.identity.fingerprint
    assert all(
        child.events[0].payload["parent"] == parent.record.events[-1].fingerprint
        for child in children[1:]
    )
    costs = [child.events[-1].payload["spend"]["cost_usd"] for child in children]
    assert result.budget.spend.cost_usd == pytest.approx(parent.budget.spend.cost_usd + sum(costs))
    assert result.budget.spend.children == parent.budget.spend.children + 3
    assert children[-1].events[0].payload["budget"]["spend"]["cost_usd"] == pytest.approx(
        parent.budget.spend.cost_usd + sum(costs[:-1])
    )
    assert result.budget.max_cost_usd == parent.budget.max_cost_usd
    assert not result.client_ready and not store.load("mat_loop").turn_receipts
    assert not store.transcripts_for("mat_loop")


@pytest.mark.parametrize("source", [False, True])
def test_absent_or_input_only_work_cannot_complete_needed_analysis_after_checked_question(
    tmp_path, source
):
    needed = (area_id("thread_one", AnalysisArea.CASE_TO_PREPARE),)
    store, _parent, *_owners, evaluator = composed_working_case(
        tmp_path, annotate=False, source=source, needed=needed
    )
    result = run_composed_working(evaluator)
    assert result.interaction_reviews[0].checked
    assert not result.working_reviews[0].checked_annotations
    complete = result.working_completeness[0]
    assert not complete.complete
    assert next(row for row in complete.items if row.id == needed[0]).state == "not_assessed"
    assert not store.load("mat_loop").turn_receipts and not result.client_ready


def test_narrow_question_can_be_checked_without_seven_forced_analysis_headings(tmp_path):
    _store, _parent, *_owners, evaluator = composed_working_case(tmp_path)
    result = run_composed_working(evaluator)
    assert result.interaction_reviews[0].checked
    assert result.working_completeness[0].complete
    assert all(row.state == "inapplicable" for row in result.working_completeness[0].items)
    assert result.working_reviews[0].annotations == ()
    assert not result.client_ready
