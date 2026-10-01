"""The P51 bridge consumes real loop receipts, not author's evidence assertions."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService, prepare_claims
from nm.Archives.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode
from nm.Archives.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.Archives.legal_brain.orchestrate.tools import Boundary, foundation_tools
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import SchemaViolation, Tier, ToolCall
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_independent_claim_verifier import Judge, finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a


def _case(tmp_path, *, claims=None, judged=None, budget=1.0, children=0, max_steps=10,
          threads=()):
    store, identity, _, author, _ = _setup(tmp_path)
    saved = store.load(identity.matter_id)
    store.commit(replace(saved, facts=(premise(),), threads=threads, version=saved.version + 1),
                 expected_version=saved.version)
    held = finding()
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (held,), searched_stores=("held",))
    registry = foundation_tools(store, evidence, manifest=Mock(), source_version="generation-1",
                                before=lambda *_: Boundary(True, "Controlled admission."),
                                after=lambda *_: Boundary(True, "Controlled result check."))
    author.provider = "scripted"
    author.resolved_model.return_value = "scripted:author"
    author.context_budget.return_value = 100_000
    original = {"id": "p1", "text": "The benefit depends on notice.",
                "sources": [{"locator": held.locator, "quote": held.span}],
                "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    author.tool_call.side_effect = [
        replace(_response(ToolCall("source1", "read_provision", {
            "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})),
            provider="scripted", model="scripted:author"),
        replace(_response(ToolCall("answer1", "submit_answer", {
            "claims": claims if claims is not None else [original]})),
            provider="scripted", model="scripted:author")]
    judge = Judge(answer=judged or response())
    log = MatterLoopLog(store, advocate_id=identity.advocate_id)
    reviewer = ReviewService(store=store, log=log, verifier=IndependentVerifier(judge),
                             session_current=lambda: True, cost_ceiling=lambda *_: 0.03)
    brain = ControlledBrain(store=store, model=author, principles=FilePrinciples(), log=log,
                            registry=registry, scope=EvaluationScope(
                                "OWNER-CONTROLLED", identity.advocate_id,
                                frozenset({identity.matter_id}), LoopMode.SYNTHETIC),
                            cost_ceiling=lambda *_: 0.03, session_current=lambda: True,
                            reviewer=reviewer)
    output = brain.run(matter_id=identity.matter_id, turn_id="package-turn",
                       message="Assess the notice requirement.",
                       limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000,
                                                max_cost_usd=budget,
                                                max_children=children), max_steps, 500))
    return store, brain, output, judge, original


def test_actual_saved_sources_reach_a_distinct_judge_and_final_words_remain_exact(tmp_path):
    store, brain, outcome, judge, _ = _case(tmp_path)
    checked = brain.review(outcome)
    assert checked.candidate_text == outcome.proposal["claims"][0]["text"]
    assert checked.result.released and checked.records[0].releasable
    assert not checked.client_ready and not store.load("mat_loop").turn_receipts
    assert len(judge.prompts) == 1
    logs = store.load("mat_loop").loop_records
    assert len(logs) == 2 and logs[-1].terminal
    assert logs[-1].events[1].payload["model"] == judge.resolved_model(Tier.JUDGE)
    assert logs[-1].events[-1].payload["released"] is False
    repeated = brain.review(outcome)
    assert repeated == checked and len(judge.prompts) == 1


@pytest.mark.parametrize("mutation", ["quote", "locator", "foreign_fact", "extra_answer", "empty"])
def test_authored_evidence_or_unchecked_extra_words_cannot_reach_the_judge(tmp_path, mutation):
    _, brain, outcome, judge, _ = _case(tmp_path)
    proposal = {"claims": [dict(outcome.proposal["claims"][0])]}
    if mutation in {"quote", "locator"}:
        proposal["claims"][0]["sources"] = [{
            "locator": "other:matter:source" if mutation == "locator" else "held:rule:1",
            "quote": ("A certificate establishes service." if mutation == "quote"
                      else finding().span)}]
    elif mutation == "foreign_fact":
        proposal["claims"][0]["premise_ids"] = ["foreign_fact"]
    elif mutation == "extra_answer":
        proposal["answer"] = "Do whatever the unchecked prose recommends."
    else:
        proposal["claims"] = []
    # The terminal saved proposal does not change with the caller's copy.
    with pytest.raises((ReviewRefused, SchemaViolation)):
        brain.review(replace(outcome, proposal=proposal))
    assert not judge.prompts


@pytest.mark.parametrize("mutation", ["quote", "locator", "foreign_fact", "empty"])
def test_a_saved_bad_package_is_refused_not_just_a_changed_callers_copy(tmp_path, mutation):
    source = finding()
    row = {"id": "p1", "text": "The benefit depends on notice.",
           "sources": [{"locator": source.locator, "quote": source.span}],
           "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    if mutation == "quote":
        row["sources"][0]["quote"] = "Words not present in the captured primary source."
    elif mutation == "locator":
        row["sources"][0]["locator"] = "a:source:from:another:file"
    elif mutation == "foreign_fact":
        row["premise_ids"] = ["fact_from_another_file"]
    claims = [] if mutation == "empty" else [row]
    store, brain, outcome, judge, _ = _case(tmp_path, claims=claims)
    assert outcome.record.events[-1].payload["proposal"] == {"claims": claims}
    with pytest.raises(ReviewRefused):
        brain.review(outcome)
    assert not judge.prompts and len(store.load("mat_loop").loop_records) == 1


def test_caller_cannot_reset_the_budget_by_replacing_a_saved_outcomes_limits(tmp_path):
    _, brain, outcome, judge, _ = _case(tmp_path)
    inflated = replace(outcome, budget=replace(outcome.budget, max_cost_usd=100))
    with pytest.raises(ReviewRefused, match="saved whole-task"):
        brain.review(inflated)
    assert not judge.prompts


def test_a_paid_review_over_its_reservation_is_saved_but_never_credited(tmp_path):
    from nm.shared.model_port import Usage

    store, brain, outcome, judge, _ = _case(tmp_path)
    original_call = judge.structured

    def oversized(*args, **kwargs):
        result = original_call(*args, **kwargs)
        return replace(result, usage=Usage(tokens_in=10, tokens_out=10, cost_usd=0.9))

    judge.structured = oversized
    checked = brain.review(outcome)
    assert not checked.result.released and not checked.candidate_text
    assert checked.records[0].usage.cost_usd == 0.9
    assert checked.budget.spend.cost_usd == pytest.approx(0.92)
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.terminal and saved.events[-1].payload["spend"]["cost_usd"] == 0.9
    assert not saved.events[-1].payload["verification"]["textual_support"]["assessed"]


def test_correcting_the_file_or_ending_the_session_refuses_review_before_spending(tmp_path):
    store, brain, outcome, judge, _ = _case(tmp_path)
    matter = store.load("mat_loop")
    store.commit(replace(matter, facts=(replace(matter.facts[0], statement="No certificate."),),
                         version=matter.version + 1), expected_version=matter.version)
    with pytest.raises(ReviewRefused, match="changed"):
        brain.review(outcome)
    assert not judge.prompts
    brain._session_current = lambda: False
    with pytest.raises(PermissionError):
        brain.review(outcome)
    assert not judge.prompts


def test_false_final_inference_withholds_the_actual_paragraph_and_is_saved(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path, judged=response(inference=False))
    checked = brain.review(outcome)
    assert not checked.candidate_text and checked.result.withheld
    assert not checked.records[0].inference.assessed
    assert store.load("mat_loop").loop_records[-1].terminal
    assert not checked.client_ready


def test_a_review_cannot_reset_the_whole_task_money_limit(tmp_path):
    _, brain, outcome, judge, _ = _case(tmp_path, budget=0.04)
    assert outcome.budget.spend.cost_usd == 0.02
    with pytest.raises(ReviewRefused, match="whole-task"):
        brain.review(outcome)
    assert not judge.prompts


def test_package_premises_remain_asserted_even_when_the_advocate_confirmed_the_account(tmp_path):
    store, _, outcome, _, _ = _case(tmp_path)
    packages = prepare_claims(outcome, store.load("mat_loop"))
    assert packages[0].premises[0].certainty.value == "asserted"
    assert packages[0].premises[0].confirmed is True


def test_independent_reviews_share_the_parent_child_allowance_and_retries_do_not_reset_it(tmp_path):
    claim = {"text": "The benefit depends on notice.",
             "sources": [{"locator": finding().locator, "quote": finding().span}],
             "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    store, brain, outcome, judge, _ = _case(tmp_path, children=1,
        claims=[{"id": "first", **claim}, {"id": "second", **claim}])
    checked = brain.review(outcome)
    assert checked.budget.spend.children == 1 and len(judge.prompts) == 1
    assert len(checked.records) == 1 and len(checked.result.withheld) == 1
    assert checked.result.released[0].id == "first"
    assert len(store.load("mat_loop").loop_records) == 2
    assert brain.review(outcome) == checked
    assert len(judge.prompts) == 1
