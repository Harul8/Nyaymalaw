"""Actual work reaches the wording owner; historic proofs are never upgraded."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.Archives.legal_brain.evaluate.evaluation_models import VerifierOnly
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.verify.interaction_review import (
    COMMUNICATION_WORK_REVIEW_SCHEMA,
    InteractionReviewService,
    build_work_prompt,
    communication_subject,
)
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind
from nm.Archives.legal_brain.communicate.preview_display import displayed_questions, interaction_text
from nm.Archives.legal_brain.orchestrate.tools import Boundary, foundation_tools
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.Archives.legal_brain.orchestrate.work_receipts import require_work_receipts, work_receipts
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, ToolCall, Usage
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_communication_evidence_roles_are_owned import (
    EvidenceJudge,
    _evidence_judgment,
    _v3_case,
)
from tests.test_interaction_review_units_are_server_owned import _v2_case
from tests.test_interaction_words_require_an_independent_exact_review import _case
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


class WorkJudge(EvidenceJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_WORK_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        assert packet["protocol_version"] == 4
        data = self.mutation(deepcopy(_evidence_judgment(packet)))
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _work_case(tmp_path, **kwargs):
    store, brain, outcome, _, old = _case(tmp_path, **kwargs)
    judge = WorkJudge()
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=4)
    return store, brain, outcome, judge, service


def test_actual_primary_read_and_terminal_receipts_reach_the_dispatched_review(tmp_path):
    store, _, outcome, judge, service = _work_case(tmp_path, read_source=True)
    result = service.review(outcome)
    packet = json.loads(judge.prompts[0].user)
    payload = packet["subject"]
    work = payload["work_receipts"]
    assert result.checked and result.check_turn_id.endswith(":check:communication_work")
    assert work["count"] == 2 == len(work["attempts"])
    assert [row["call"]["name"] for row in work["attempts"]] == [
        "read_provision", "propose_conversation"]
    actual = [event.payload["receipt"] for event in outcome.record.events
              if event.kind is StepKind.TOOL_RETURNED]
    for projected, raw in zip(work["attempts"], actual, strict=True):
        assert projected["result"]["receipt"] == raw["receipt"]
        assert projected["result"]["assessment"] == raw["assessment"]
    assert payload["law_windows"]
    assert "findings" not in work["attempts"][0]["result"]["data"]
    assert "execution_data_not_facts_law_or_authorization" == work["trust"]
    require_work_receipts(payload, outcome.record)
    assert service.recorded(outcome) == result
    assert service.review(outcome) == result and len(judge.prompts) == 1
    assert not store.load("mat_loop").turn_receipts


def test_actual_unavailable_source_is_not_an_absent_or_successful_work_record(tmp_path):
    from unittest.mock import Mock

    store, brain, _, judge, service = _work_case(tmp_path)
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(Coverage.NOT_ASSESSED,
        missing="The actual index is unavailable.", searched_stores=("held-index",))
    registry = foundation_tools(store, evidence, manifest=Mock(), source_version="actual-test-gen",
        before=lambda *_: Boundary(True, "Controlled admission"),
        after=lambda *_: Boundary(True, "Controlled result"))
    assert registry.version == brain.registry.version
    brain._runner._tools = registry
    brain.model.tool_call.side_effect = [
        _response(ToolCall("unavailable", "read_provision", {
            "act": "Recorded rule", "section": "1", "as_of": "2026-01-01"})),
        _response(ToolCall("question", "ask_advocate", {"question": "Which record is held?"}))]
    outcome = brain.run(matter_id="mat_loop", turn_id="unavailable-parent",
        message="Read the rule.",
        limits=LoopLimits(_budget(), 20, 400))
    service.review(outcome)
    payload = json.loads(judge.prompts[0].user)["subject"]
    result = payload["work_receipts"]["attempts"][0]["result"]
    assert result["availability"] == "unavailable" and result["outcome"] == "failed"
    assert result["data"] == {} and "unavailable" in result["reason"]
    assert result["receipt"]["primary_reads"][0]["coverage"] == "not_assessed"
    assert payload["law_windows"] == []


def _budget():
    from nm.shared.budget_contracts import Budget

    return Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1)


@pytest.mark.parametrize("mutation", ["missing", "empty", "changed", "invented", "quote"])
def test_saved_work_population_cannot_omit_change_or_invent_an_attempt(tmp_path, mutation):
    store, _, outcome, _, service = _work_case(tmp_path, read_source=True)
    subject = communication_subject(service.owner, outcome, store.load("mat_loop"), 4)
    payload = subject.payload
    if mutation == "missing":
        del payload["work_receipts"]
    elif mutation == "empty":
        payload["work_receipts"]["attempts"] = []
    elif mutation == "changed":
        payload["work_receipts"]["attempts"][0]["result"]["availability"] = "unavailable"
    elif mutation == "invented":
        payload["work_receipts"]["attempts"].append({"call": "not dispatched"})
    else:
        next(row for row in payload["quote_sources"] if row["id"] == "work_receipts")["text"] = "{}"
    with pytest.raises(ReviewRefused):
        require_work_receipts(payload, outcome.record)


def test_tool_call_without_return_is_unknown_and_refusal_remains_distinct(tmp_path):
    _, _, outcome, _, _ = _work_case(tmp_path, read_source=True)
    index = next(i for i, event in enumerate(outcome.record.events)
                 if event.kind is StepKind.TOOL_STARTED)
    prefix = SimpleNamespace(events=outcome.record.events[:index + 1])
    assert work_receipts(prefix)["attempts"][0]["state"] == "outcome_unknown"
    refused = SimpleNamespace(kind=StepKind.FAILURE, fingerprint="actual-failure",
        payload={"call_id": "law", "kind": "tool_boundary_refused"})
    projection = work_receipts(SimpleNamespace(events=(*prefix.events, refused)))
    assert projection["attempts"][0]["state"] == "refused"
    assert "result" not in projection["attempts"][0]
    return_only = SimpleNamespace(events=(outcome.record.events[index + 1],))
    with pytest.raises(ReviewRefused):
        work_receipts(return_only)


def test_actual_boundary_refusal_is_preserved_as_an_unperformed_tool_attempt(tmp_path):
    _, brain, _, _, _ = _work_case(tmp_path)
    brain.registry._before = lambda *_: Boundary(False, "The actual permission owner refuses.")
    brain.model.tool_call.side_effect = [_response(ToolCall("unowned", "read_matter", {}))]
    outcome = brain.run(matter_id="mat_loop", turn_id="refused-parent", message="Read the file.",
                        limits=LoopLimits(_budget(), 20, 400))
    attempts = work_receipts(outcome.record)["attempts"]
    assert len(attempts) == 1 and attempts[0]["call"]["name"] == "read_matter"
    assert attempts[0]["state"] == "refused" and "result" not in attempts[0]


def test_delegated_unknown_unavailable_and_refused_work_retains_its_complete_population(tmp_path):
    _, _, outcome, _, _ = _work_case(tmp_path, read_source=True)
    start = next(event for event in outcome.record.events if event.kind is StepKind.TOOL_STARTED)
    returned = next(event for event in outcome.record.events
                    if event.kind is StepKind.TOOL_RETURNED)
    unavailable = deepcopy(returned.payload["receipt"])
    unavailable.update(availability="unavailable", outcome="failed", assessment="not_assessed",
                       data={}, reason="The actual child reader is unavailable.")
    trace = [{"kind": "tool_started", "call": start.payload["call"]},
             {"kind": "tool_returned", "receipt": unavailable},
             {"kind": "tool_started", "call": {"call_id": "blocked", "name": "denied",
                                                "arguments": {}}},
             {"kind": "refused", "error": "ToolRefused", "reason": "Child boundary refused."},
             {"kind": "tool_started", "call": {"call_id": "unknown", "name": "attempted",
                                                "arguments": {}}}]
    payload = {**returned.payload, "child_steps": 3, "child_released": False,
               "child_transcript": trace}
    event = SimpleNamespace(kind=returned.kind, fingerprint=returned.fingerprint, payload=payload)
    saved = SimpleNamespace(events=(start, event))
    children = work_receipts(saved)["attempts"][0]["child_work"]
    assert len(children) == 3
    assert children[0]["result"]["availability"] == "unavailable"
    assert children[1]["state"] == "refused" and "result" not in children[1]
    assert children[2]["state"] == "outcome_unknown" and "result" not in children[2]
    for mutation in ({"child_steps": 0}, {"child_transcript": []}, {"child_released": True}):
        changed = SimpleNamespace(kind=event.kind, fingerprint=event.fingerprint,
                                  payload={**payload, **mutation})
        with pytest.raises(ReviewRefused):
            work_receipts(SimpleNamespace(events=(start, changed)))


def test_overflow_refuses_the_whole_receipt_population_without_truncating_it(tmp_path, monkeypatch):
    from nm.Archives.legal_brain.orchestrate import work_receipts as owner

    _, _, outcome, _, _ = _work_case(tmp_path, read_source=True)
    actual = owner.work_receipts(outcome.record)
    assert actual["count"] == 2
    monkeypatch.setattr(owner, "MAX_WORK_RECEIPT_CHARACTERS", 1)
    with pytest.raises(ReviewRefused, match="ceiling"):
        owner.work_receipts(outcome.record)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_work_protocol_retains_exact_old_subjects_results_and_historical_proofs(tmp_path, version):
    fixture = {1: _case, 2: _v2_case, 3: _v3_case}[version]
    store, _, outcome, judge, old = fixture(tmp_path, kind="ask_advocate",
                                          text="Which record is held?")
    before = old.owner.build(outcome, store.load("mat_loop"))
    result = old.review(outcome)
    proof = store.load("mat_loop").loop_records[-1]
    new = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=4)
    assert new.recorded(outcome) == result
    assert communication_subject(old.owner, outcome, store.load("mat_loop"), version) == before
    assert "work_receipts" not in before.payload
    assert interaction_text(outcome.record, proof)[0] == outcome.proposal["question"]
    with pytest.raises(ReviewRefused, match="upgraded"):
        new.review(outcome)
    assert len(judge.prompts) == 1
    with pytest.raises(ReviewRefused):
        build_work_prompt(before, old.owner.principles.load().text)


def test_served_v4_review_reopens_and_records_display_without_extra_model_work(client):
    app, matter, author, _ = approved(client)
    judges = []

    def reviewer(application, scope, current):
        judge = WorkJudge()
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)

    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
        reviewer_factory=reviewer, interaction_protocol_version=4,
        limits=replace(app.controlled_evaluations[0].limits,
            budget=replace(app.controlled_evaluations[0].limits.budget, max_tokens=100000))),)
    assert client.post(path(matter), json=request(matter)).status_code == 200
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}]
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    saved = app.store.load(matter.id)
    history = displayed_questions(saved, before_version=saved.version, selected_issue_ids=())
    assert history[0]["text"] == PRIVATE
    assert client.get(preview(matter)).json()["paragraphs"] == shown.json()["paragraphs"]
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1
    VerifierOnly(judges[0]).structured(judges[0].prompts[0], COMMUNICATION_WORK_REVIEW_SCHEMA,
                                      Tier.JUDGE)
