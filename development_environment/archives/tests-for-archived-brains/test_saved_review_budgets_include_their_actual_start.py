"""Admission checkpoints retain real elapsed work without replay refunds."""
from dataclasses import replace

import pytest

from nm.Archives.legal_brain.verify.brain_assessment import _saved_review, saved_package_reviews
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, prepare_claims
from nm.shared.budget_contracts import Spend
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import finding, response
from tests.test_reviewed_private_preview_checks_saved_words import (
    changed_payload,
    ready,
    replace_record,
)

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("positive", [True, False])
def test_actual_start_elapsed_is_part_of_live_replay_and_exact_assessment(tmp_path, positive):
    store, brain, parent, judge, _ = _case(tmp_path, judged=response(inference=positive))
    admitted = replace(parent.budget, spend=replace(parent.budget.spend,
        elapsed_ms=parent.budget.spend.elapsed_ms + 937))
    checked = brain.reviewer.review(parent, budget=admitted)
    child = store.load("mat_loop").loop_records[-1]
    assert child.events[0].payload["budget"]["spend"]["elapsed_ms"] == admitted.spend.elapsed_ms
    assert checked.budget.spend.elapsed_ms == (
        admitted.spend.elapsed_ms + child.events[-1].payload["spend"]["elapsed_ms"])
    packages = prepare_claims(parent, store.load("mat_loop"))
    assert saved_package_reviews(parent, packages, store.load("mat_loop"), brain.log) == checked
    assert brain.review(parent) == checked
    assert _saved_review(parent, checked, store.load("mat_loop"), brain.log) == checked
    wrong = replace(checked, budget=replace(checked.budget,
        spend=replace(checked.budget.spend, elapsed_ms=parent.budget.spend.elapsed_ms)))
    with pytest.raises(ReviewRefused, match="budgets differ"):
        _saved_review(parent, wrong, store.load("mat_loop"), brain.log)
    assert len(judge.prompts) == 1
    assert parent.budget.as_dict() == parent.record.events[-1].payload["budget"]


def test_later_actual_checks_do_not_rewrite_a_historical_review_but_default_replay_keeps_them(
    tmp_path,
):
    store, brain, parent, assessment, _preview, _checks, judge = ready(tmp_path, publish=False)
    historical = assessment.review
    assert _saved_review(parent, historical, store.load("mat_loop"), brain.log) == historical
    children = store.load("mat_loop").loop_records[1:]
    assert sum(":check:" in child.identity.turn_id for child in children) == 2
    current = brain.review(parent)
    assert current.records == historical.records
    assert current.budget.spend.children == parent.budget.spend.children + len(children)
    assert current.budget.spend.tokens == parent.budget.spend.tokens + sum(
        child.events[-1].payload["spend"]["tokens"] for child in children)
    assert current.budget.spend.cost_usd == pytest.approx(parent.budget.spend.cost_usd + sum(
        child.events[-1].payload["spend"]["cost_usd"] for child in children))
    assert len(judge.prompts) == 1
    assert _saved_review(parent, historical, store.load("mat_loop"), brain.log) == historical


@pytest.mark.parametrize("children", [2, 3])
def test_new_paid_subject_without_explicit_budget_uses_actual_prior_check_allowance(
    tmp_path, children,
):
    from nm.Archives.legal_brain.verify.brain_finalization import SavedCheckReader
    from nm.shared.model_config import ModelConfig, TierConfig
    from nm.shared.model_port import Prompt, Tier
    from nm.shared.model_scripted import ScriptedModelAdapter

    claim = {"text": "The benefit depends on notice.",
        "sources": [{"locator": finding().locator, "quote": finding().span}],
        "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    store, brain, parent, judge, _ = _case(tmp_path, children=children,
        claims=[{"id": "first", **claim}, {"id": "second", **claim}])
    packages = prepare_claims(parent, store.load("mat_loop"))

    def owner(outcome, matter, selected):
        if not selected or any(row not in prepare_claims(outcome, matter) for row in selected):
            raise ReviewRefused("Only exact saved claim subjects are admitted")

    first = brain.reviewer.review_packages(parent, packages[:1], current_owner=owner)
    model = ScriptedModelAdapter(ModelConfig({Tier.ROUTINE: TierConfig(
        Tier.ROUTINE, "scripted", "budget-check", None, None)}),
        structured_responses={"budget_checkpoint": {"ready": True}})
    reader = SavedCheckReader(store=store, log=brain.log, model=model,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    read = reader.read(parent, "budget_checkpoint", Prompt("Recorded budget checkpoint."),
        {"type": "object", "properties": {"ready": {"type": "boolean"}},
         "required": ["ready"], "additionalProperties": False}, Tier.ROUTINE, first.budget)
    after_check = first.budget.spend_on(read.spend)
    second = brain.reviewer.review_packages(parent, packages[1:], current_owner=owner)
    if children == 2:
        assert second.records == ()
        assert second.budget.spend.children == after_check.spend.children == 2
        assert len(judge.prompts) == 1
    else:
        assert second.records[0].releasable and len(judge.prompts) == 2
        saved = store.load("mat_loop").loop_records[-1]
        assert saved.events[0].payload["budget"]["spend"]["children"] == 2
        assert second.budget.spend.children == 3
    assert saved_package_reviews(parent, packages[:1], store.load("mat_loop"), brain.log) == first


@pytest.mark.parametrize("positive", [True, False])
@pytest.mark.parametrize("mutation", ["boolean_counter", "negative_counter", "nan_cost",
                                      "missing_field", "extra_field", "larger_grant"])
def test_unknown_and_positive_receipts_have_the_same_strict_start_contract(
    tmp_path, positive, mutation,
):
    store, brain, parent, _, _ = _case(tmp_path, judged=response(inference=positive))
    brain.review(parent)

    def alter(saved):
        budget = saved.events[0].payload["budget"]
        if mutation == "boolean_counter":
            budget["spend"]["children"] = False
        elif mutation == "negative_counter":
            budget["spend"]["elapsed_ms"] = -1
        elif mutation == "nan_cost":
            # A nonfinite value is not even admissible to the sealed JSON owner.
            budget["spend"]["cost_usd"] = "NaN"
        elif mutation == "missing_field":
            del budget["spend"]["discarded_results"]
        elif mutation == "extra_field":
            budget["extra_authorized_money"] = 100
        else:
            budget["max_cost_usd"] += 1
        return changed_payload(saved, 0, budget=budget)

    replace_record(store, "package-turn:verify:p1", alter)
    with pytest.raises(ReviewRefused):
        brain.review(parent)
    with pytest.raises(ReviewRefused):
        saved_package_reviews(parent, prepare_claims(parent, store.load("mat_loop")),
            store.load("mat_loop"), brain.log)


def test_start_keeps_full_measured_cost_not_its_display_rounding(tmp_path):
    store, brain, parent, _, _ = _case(tmp_path)
    extra = Spend(cost_usd=0.000000123456789, elapsed_ms=811)
    admitted = parent.budget.spend_on(extra)
    checked = brain.reviewer.review(parent, budget=admitted)
    start = store.load("mat_loop").loop_records[-1].events[0].payload["budget"]
    assert start["spend"]["cost_usd"] == admitted.spend.cost_usd
    assert start["spend"]["cost_usd"] != admitted.as_dict()["spend"]["cost_usd"]
    assert saved_package_reviews(parent, checked.packages, store.load("mat_loop"),
        brain.log) == checked


@pytest.mark.parametrize("stop", ["cancelled", "zero_calls", "time_exhausted"])
def test_a_stopped_replay_cannot_refund_selected_completed_children(tmp_path, stop):
    store, brain, parent, judge, _ = _case(tmp_path)
    checked = brain.review(parent)
    budget, maximum = checked.budget, None
    if stop == "cancelled":
        budget = replace(budget, cancelled_at="2026-09-27T00:00:00+00:00")
    elif stop == "zero_calls":
        maximum = 0
    else:
        budget = replace(budget, spend=replace(budget.spend, elapsed_ms=budget.max_ms + 1))
    replayed = brain.reviewer.review(parent, budget=budget, max_model_calls=maximum)
    assert replayed.records == () and len(judge.prompts) == 1
    assert replayed.budget.spend.children == checked.budget.spend.children
    assert replayed.budget.spend.tokens == checked.budget.spend.tokens
    assert replayed.budget.spend.cost_usd == pytest.approx(checked.budget.spend.cost_usd)
    assert replayed.budget.spend.elapsed_ms >= budget.spend.elapsed_ms
    assert saved_package_reviews(parent, checked.packages, store.load("mat_loop"),
        brain.log) == checked


@pytest.mark.parametrize("positive", [True, False])
def test_a_later_start_cannot_restore_an_actual_earlier_admission(tmp_path, positive):
    claim = {"text": "The benefit depends on notice.",
        "sources": [{"locator": finding().locator, "quote": finding().span}],
        "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    store, brain, parent, _, _ = _case(tmp_path, judged=response(inference=positive),
        claims=[{"id": "first", **claim}, {"id": "second", **claim}])
    start = replace(parent.budget, spend=replace(parent.budget.spend,
        elapsed_ms=parent.budget.spend.elapsed_ms + 937))
    checked = brain.reviewer.review(parent, budget=start)
    assert len(checked.records) == 2
    replace_record(store, "package-turn:verify:second", lambda saved:
        changed_payload(saved, 0, budget=parent.budget.as_dict()))
    with pytest.raises(ReviewRefused, match="restored"):
        brain.review(parent)
    with pytest.raises(ReviewRefused, match="restored"):
        saved_package_reviews(parent, checked.packages, store.load("mat_loop"), brain.log)
