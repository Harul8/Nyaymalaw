"""Saved actual wording/scope work cannot be refunded by a later source review."""
from dataclasses import replace

import pytest

from nm.legal_brain.brain_release import ReviewRefused, shared_review_budget
from tests.test_working_evaluation_uses_one_actual_check_budget import (
    composed_working_case,
    run_composed_working,
)

pytestmark = pytest.mark.class_a


def test_repeated_working_review_after_actual_wording_and_scope_children_spends_once(tmp_path):
    store, parent, _owner, working, _scope, _judge, verifier, _wording, evaluator = (
        composed_working_case(tmp_path, annotate=True, source=True))
    result = run_composed_working(evaluator)
    assert result.interaction_reviews[0].checked
    actual_calls = len(verifier.prompts)
    previous_records = store.load("mat_loop").loop_records
    reviewed = working.review(parent, budget=result.budget)
    assert reviewed.checked_annotations
    assert len(verifier.prompts) == actual_calls
    assert store.load("mat_loop").loop_records == previous_records
    assert reviewed.review.budget.spend.cost_usd == pytest.approx(result.budget.spend.cost_usd)
    assert reviewed.review.budget.spend.tokens == result.budget.spend.tokens
    assert reviewed.review.budget.spend.children == result.budget.spend.children
    assert evaluator.brain.log.read(parent.record.identity) == parent.record
    assert parent.budget.as_dict() == parent.record.events[-1].payload["budget"]


def test_actual_wording_and_scope_spend_is_a_hard_floor_for_later_verification(tmp_path):
    store, parent, owner, working, _scope, _judge, _verifier, _wording, evaluator = (
        composed_working_case(tmp_path, annotate=True, source=True))
    result = run_composed_working(evaluator)
    packages = owner.packages(parent, store.load("mat_loop"))
    actual = working.reviewer.log
    for field in ("tokens", "cost_usd", "children"):
        restored = replace(result.budget, spend=replace(result.budget.spend,
            **{field: getattr(parent.budget.spend, field)}))
        with pytest.raises(ReviewRefused):
            shared_review_budget(parent, packages, store.load("mat_loop"), actual, restored)
    enlarged = replace(result.budget, max_cost_usd=result.budget.max_cost_usd + 1)
    with pytest.raises(ReviewRefused):
        shared_review_budget(parent, packages, store.load("mat_loop"), actual, enlarged)
    cancelled = replace(result.budget, cancelled_at="2026-09-27T00:00:00+00:00")
    assert shared_review_budget(parent, packages, store.load("mat_loop"), actual,
                               cancelled).cancelled_at == cancelled.cancelled_at
