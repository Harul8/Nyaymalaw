"""Saved proposal failures use the original bounded task, never a source waiver."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.legal_brain.verify.brain_assessment import AssessmentService
from nm.legal_brain.verify.brain_release import ProposalBindingRefused, ReviewRefused, prepare_claims
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_private_brain_transport_cannot_approve_or_release_itself import path, request
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def assessment(store, brain):
    brain.assessment = AssessmentService(store=store, log=brain.log,
        session_current=lambda: True, current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version)


def run(brain, **kwargs):
    return brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500),
        **kwargs)


def author_response(call):
    return replace(_response(call), provider="scripted", model="scripted:author")


@pytest.mark.parametrize("fault", ["quote", "locator", "premise", "empty"])
def test_authored_reference_failures_are_typed_after_the_saved_source_is_checked(tmp_path, fault):
    _, _, _, _, claim = _case(tmp_path / "seed")
    bad = deepcopy(claim)
    if fault == "quote":
        bad["sources"][0]["quote"] = "Words absent from every captured source."
    elif fault == "locator":
        bad["sources"][0]["locator"] = "not-a-captured-source"
    elif fault == "premise":
        bad["premise_ids"] = ["not-a-recorded-premise"]
    claims = [] if fault == "empty" else [bad]
    store, _, outcome, judge, _ = _case(tmp_path / "actual", claims=claims)
    with pytest.raises(ProposalBindingRefused):
        prepare_claims(outcome, store.load("mat_loop"))
    assert not judge.prompts and not store.load("mat_loop").turn_receipts


def test_false_citation_returns_to_the_shared_repair_tail_before_any_judge_dispatch(tmp_path):
    _, _, _, _, claim = _case(tmp_path / "seed")
    bad = deepcopy(claim)
    bad["sources"][0]["quote"] = "Words absent from every captured source."
    store, brain, first, judge, _ = _case(tmp_path / "actual", claims=[bad])
    assessment(store, brain)
    brain.model.tool_call.side_effect = [
        author_response(ToolCall("read-again", "read_provision", {
            "act": "Held act", "section": "1", "as_of": "2026-01-01"})),
        author_response(ToolCall("fixed", "submit_answer", {"claims": [claim]}))]
    result = run(brain)
    assert len(result.attempts) == 2 and len(judge.prompts) == 1
    assert len(result.assessments) == 1 and not result.client_ready
    assert result.stop == "required_checks_missing"
    assert result.attempts[0].record == first.record
    repair = result.attempts[1].record.events[0].payload
    assert repair["feedback_identity"] and result.budget.spend.discarded_results == 1
    assert "proposal_binding" in str(repair["context"])
    assert not store.load("mat_loop").turn_receipts


def test_old_held_source_is_not_a_read_receipt_for_a_new_unretrieved_proposal(tmp_path):
    store, brain, _, judge, claim = _case(tmp_path)
    assessment(store, brain)
    brain.model.tool_call.side_effect = [
        author_response(ToolCall("unread", "submit_answer", {"claims": [claim]}))]
    result = brain.evaluate(matter_id="mat_loop", turn_id="new-unread",
        message="Assess the notice requirement.", max_repairs=0,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 500))
    assert result.stop == "repair_limit" and len(result.attempts) == 1
    assert not judge.prompts and not result.assessments and not result.client_ready
    with pytest.raises(ProposalBindingRefused):
        prepare_claims(result.attempts[0], store.load("mat_loop"))


def test_a_lost_session_is_not_reclassified_as_an_authored_binding_failure(tmp_path):
    store, brain, _, judge, _ = _case(tmp_path)
    assessment(store, brain)
    brain.reviewer.session_current = lambda: False
    before = brain.model.tool_call.call_count
    result = run(brain)
    assert result.stop == "review_refused" and len(result.attempts) == 1
    assert brain.model.tool_call.call_count == before and not judge.prompts
    assert not result.client_ready and not store.load("mat_loop").turn_receipts
    assert not issubclass(ReviewRefused, ProposalBindingRefused)


def test_served_unretrieved_quote_is_saved_as_a_grounding_failure_not_a_file_race(client):
    app, matter, author, judges = approved(client)
    author.tool_call.return_value = _response(ToolCall("unread", "submit_answer", {
        "claims": [{"id": "unchecked", "text": "An unchecked legal conclusion.",
            "sources": [{"locator": "invented-rule", "quote": "Invented quotation."}],
            "premise_ids": [], "contrary": [], "depends_on": []}]}))
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200, posted.text
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["result_state"] == "proposal_binding_failed"
    assert not shown.json()["paragraphs"]
    assert "An unchecked legal conclusion." not in shown.text
    assert author.tool_call.call_count == 1 and not any(row.prompts for row in judges)
    saved = app.store.load(matter.id)
    assert not saved.turn_receipts and not saved.facts
    assert len(saved.loop_records) == 1 and saved.loop_records[0].terminal
    assert saved.loop_records[0].events[-1].payload["proposal"]["claims"][0]["sources"] == [
        {"locator": "invented-rule", "quote": "Invented quotation."}]
