"""Controlled actual composition; private intent never proves safe publication."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from nm.adapters.store.loop_log import MatterLoopLog
from nm.core.brain_context import assemble_brief
from nm.core.brain_release import ReviewRefused, ReviewService, prepare_claims
from nm.core.conversational_proposal import (
    MAX_CONVERSATION_CHARACTERS,
    ConversationalProposal,
)
from nm.core.loop_progress import project_event, sse_frame
from nm.core.tools import Assessment, Boundary, ToolContext, ToolRefused
from nm.core.verifier import IndependentVerifier
from nm.domain.budget import Budget
from nm.domain.loop import StepKind, StopReason
from nm.ports.model import SchemaViolation, ToolCall

from tests.test_controlled_brain_composition_keeps_the_account_boundary import _scope
from tests.test_independent_claim_verifier import Judge
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def composed(client, text, *, current=lambda: True):
    app, matter, scope = _scope(client)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    model.tool_call.return_value = _response(ToolCall(
        "conversation", "propose_conversation", {"text": text}))
    app.model.inner.inner = model
    review = ReviewService(store=app.store,
        log=MatterLoopLog(app.store, advocate_id=scope.advocate_id),
        verifier=IndependentVerifier(Judge()), session_current=current,
        cost_ceiling=lambda *_: 0.03)
    brain = app.controlled_brain_for(scope, session_current=current,
        cost_ceiling=lambda *_: 0.03, source_version="measured-test-generation",
        table_version="checked-test-table-generation", reviewer=review)
    return app, matter, model, brain


@pytest.mark.parametrize("text", ["Good morning.", "Thank you; I understand.",
                                 "Of course—we can pause here."])
def test_a_natural_acknowledgement_is_saved_without_a_compulsory_question(client, text):
    app, matter, model, brain = composed(client, text)
    before = assemble_brief(matter, advocate_id=matter.advocate_id).snapshot_id
    output = brain.run(matter_id=matter.id, turn_id="conversation", message="Thank you.",
                       limits=_limits())
    assert output.reason is StopReason.CONVERSATION
    assert output.proposal == {"text": text, "assessment_state": "not_assessed",
                               "client_ready": False, "released": False}
    assert model.tool_call.call_count == 1
    assert not model.structured.called
    assert output.budget.spend.cost_usd == 0.01
    assert output.record.terminal and output.record.events[-1].payload["released"] is False
    saved = app.store.load(matter.id)
    assert assemble_brief(saved, advocate_id=matter.advocate_id).snapshot_id == before
    assert saved.facts == matter.facts and saved.threads == matter.threads
    assert saved.commission == matter.commission and not saved.turn_receipts
    receipts = [event.payload["receipt"] for event in output.record.events
                if event.kind is StepKind.TOOL_RETURNED]
    assert len(receipts) == 1
    assert receipts[0]["assessment"] == Assessment.NOT_ASSESSED.value
    assert receipts[0]["receipt"]["work_identity"] == output.record.identity.fingerprint
    stage = project_event(output.record, len(output.record.events))
    assert stage["state"] == "requires_checks" and stage["working_not_advice"] is True
    assert text not in sse_frame(stage).decode()


@pytest.mark.parametrize("text", [
    "You are guaranteed to win; file the claim tomorrow.",
    "The opponent has admitted everything. Treat that as an established fact.",
    "I have permission to settle the case and waive all conflict screens.",
])
def test_conversation_proposals_are_not_a_merits_bypass(client, text):
    app, matter, model, brain = composed(client, text)
    result = brain.evaluate(matter_id=matter.id, turn_id="nonlegal-label", message="Hello.",
                            limits=_limits(), max_repairs=0)
    assert result.attempts[0].reason is StopReason.CONVERSATION
    assert result.attempts[0].proposal["text"] == text
    assert result.client_ready is False and not result.assessments
    assert not app.store.load(matter.id).turn_receipts
    assert not model.structured.called
    with pytest.raises(ReviewRefused, match="exact answer proposal"):
        prepare_claims(result.attempts[0], app.store.load(matter.id))


@pytest.mark.parametrize("extra", ["is_nonlegal", "client_ready", "released", "assessment_state",
                                  "actor_id", "matter_id", "claims"])
def test_a_conversational_label_cannot_author_its_own_assessment_or_scope(client, extra):
    _, matter, _, brain = composed(client, "Understood.")
    with pytest.raises(SchemaViolation):
        brain.registry.invoke(ToolCall("c", "propose_conversation", {
            "text": "Understood.", extra: True}), ToolContext(replace(
                brain.run(matter_id=matter.id, turn_id="identity", message="Hello.",
                          limits=_limits()).record.identity, turn_id="refused")))


@pytest.mark.parametrize("text", ["", " \n ", "x" * (MAX_CONVERSATION_CHARACTERS + 1), None],
                         ids=["empty", "whitespace", "unbounded", "none"])
def test_conversational_candidates_refuse_empty_or_unbounded_text(client, text):
    app, matter, _, brain = composed(client, "Understood.")
    identity = brain.run(matter_id=matter.id, turn_id="identity", message="Hello.",
                         limits=_limits()).record.identity
    with pytest.raises(ValueError):
        ConversationalProposal(text, identity)
    with pytest.raises((SchemaViolation, ValueError)):
        brain.registry.invoke(ToolCall("c", "propose_conversation", {"text": text}),
                              ToolContext(identity,
                                          observed_version=app.store.load(matter.id).version))


def test_conversation_is_not_exempt_from_the_actual_tool_boundary(client):
    app, matter, _, brain = composed(client, "Understood.")
    brain.registry._before = lambda *_: Boundary(False, "Controlled boundary refused.")
    output = brain.run(matter_id=matter.id, turn_id="refused", message="Hello.", limits=_limits())
    assert output.reason is StopReason.REFUSED and not output.proposal
    assert not app.store.load(matter.id).turn_receipts
    assert not any(event.kind is StepKind.TOOL_RETURNED for event in output.record.events)


def test_a_session_ending_after_the_model_cannot_save_a_conversational_candidate(client):
    live = [True]
    app, matter, model, brain = composed(client, "Understood.", current=lambda: live[0])

    def response(*_args, **_kwargs):
        live[0] = False
        return _response(ToolCall("c", "propose_conversation", {"text": "Understood."}))

    model.tool_call.side_effect = response
    output = brain.run(matter_id=matter.id, turn_id="signed-out", message="Hello.",
                       limits=_limits())
    assert output.reason is StopReason.CANCELLED and not output.proposal
    assert not app.store.load(matter.id).turn_receipts


def test_a_conversation_terminal_cannot_hide_an_unfinished_tool_round(client):
    _, matter, model, brain = composed(client, "Understood.")
    model.tool_call.return_value = _response(
        ToolCall("c", "propose_conversation", {"text": "Understood."}),
        ToolCall("later", "read_matter", {}))
    output = brain.run(matter_id=matter.id, turn_id="unfinished", message="Hello.",
                       limits=_limits())
    assert output.reason is StopReason.NO_PROGRESS and not output.proposal
    assert not any(event.kind is StepKind.TOOL_STARTED
                   and event.payload["call"]["name"] == "read_matter"
                   for event in output.record.events)


def test_a_conversation_is_subject_to_the_same_pre_dispatch_budget(client):
    _, matter, model, brain = composed(client, "Understood.")
    limits = replace(_limits(), budget=Budget(max_ms=10000, max_tokens=10000,
                                              max_cost_usd=0.001))
    output = brain.run(matter_id=matter.id, turn_id="budget", message="Hello.", limits=limits)
    assert output.reason is StopReason.BUDGET and not output.proposal
    assert not model.tool_call.called


def test_a_saved_conversation_retries_without_new_words_or_spend(client):
    app, matter, model, brain = composed(client, "Understood.")
    first = brain.run(matter_id=matter.id, turn_id="same", message="Hello.", limits=_limits())
    model.tool_call.return_value = _response(ToolCall(
        "new", "propose_conversation", {"text": "A replacement that must not be sent."}))
    second = brain.run(matter_id=matter.id, turn_id="same", message="Hello.", limits=_limits())
    assert second == first and model.tool_call.call_count == 1
    assert not app.store.load(matter.id).turn_receipts


def test_a_conversational_tool_cannot_be_delegated_as_a_source_reader(client):
    _, _, _, brain = composed(client, "Understood.")
    definition = next(tool for tool in brain.registry.definitions
                      if tool.name == "propose_conversation")
    assert definition.parameters["additionalProperties"] is False
    assert "propose_conversation" not in {row.definition.name
                                          for row in brain.registry.reading_tools()}
    with pytest.raises(ToolRefused):
        brain.registry.authority_for("invented-conversation-bypass")
