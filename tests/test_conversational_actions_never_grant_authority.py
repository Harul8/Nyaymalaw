"""Actual preparation transaction; no connectors, model or human approval forged."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.act import action, drafting
from nm.act.action_contracts import ActionState
from nm.act.action_proposal_tool import NAME, action_proposal_tools
from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode, StepKind, StopReason
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.orchestrate.tool_discovery import discovery_tools
from nm.legal_brain.orchestrate.tools import foundation_tools
from nm.shared.model_port import ToolCall
from nm.work_the_file.matter_contracts import Thread
from tests.test_the_drafting_package_is_checkable import _brief
from tests.test_the_loop_records_work_before_using_it import ALLOW, _limits, _response, _setup

pytestmark = pytest.mark.class_a
MESSAGE = "Prepare the held draft for my review. Proposed destination: Example registry."
ARGS = {"package_id": "pkg_1", "destination_quote": "Example registry"}


def case(tmp_path, *, alter=lambda row: row, selected=()):
    store, identity, log, model, _ = _setup(tmp_path)
    matter = store.load(identity.matter_id)
    raw = drafting.as_dict(_brief(matter_id=matter.id))
    matter = store.commit(replace(matter, drafting_packages=(alter(raw),),
        threads=(Thread("d1", "First dispute"), Thread("d2", "Other dispute")),
        version=matter.version + 1), expected_version=matter.version)
    registry = foundation_tools(store, Mock(), manifest=Mock(), source_version="held-v1",
                                 before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    registry = registry.extend(action_proposal_tools(store))
    principles = FilePrinciples()
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    model.context_budget.return_value = 100000
    brain = ControlledBrain(store=store, model=model, principles=principles, log=log,
        registry=registry, scope=EvaluationScope("owner", matter.advocate_id,
        frozenset({matter.id}), LoopMode.SYNTHETIC), session_current=lambda: True,
        cost_ceiling=lambda *_: 0.02)
    return store, brain, model, selected


def run(values, args=ARGS, *, message=MESSAGE):
    store, brain, model, selected = values
    model.tool_call.side_effect = [_response(ToolCall("inspect", "inspect_tool", {"name": NAME})),
        _response(ToolCall("prepare", NAME, args)),
        _response(ToolCall("end", "ask_advocate", {"question": "What would you like to review?"}))]
    limits = _limits()
    return brain.run(matter_id="mat_loop", turn_id="prepared_action", message=message,
                     selected_issue_ids=selected,
                     limits=LoopLimits(limits.budget, 12, limits.per_call_tokens))


def test_conversational_action_preparation_uses_actual_draft_and_never_approves(tmp_path):
    values = case(tmp_path)
    store, brain, model, _ = values
    outcome = run(values)
    assert outcome.reason is StopReason.QUESTION
    current = store.load("mat_loop")
    actual = action.rows(current)
    assert len(actual) == 1 and actual[0].state is ActionState.PREPARED
    proposal = actual[0]
    assert not proposal.confirmed and not proposal.authority
    assert proposal.destination == "Example registry" and proposal.actor == current.advocate_id
    assert proposal.content_digest == drafting.export(drafting.rows(current)[0])["content_digest"]
    event = next(row for row in outcome.record.events if row.kind is StepKind.TOOL_RETURNED
                 and row.payload["receipt"]["tool"] == NAME)
    assert event.payload["mutation_identity"] == event.payload["receipt"]["receipt"]["snapshot"]
    assert event.payload["receipt"]["data"]["dispatched"] is False
    assert event.payload["receipt"]["data"]["advocate_approval"] is False
    assert "Nothing here has been sent" in action.projection(proposal)["dispatch_note"]
    assert not current.turn_receipts and not store.transcripts_for(current.id)
    calls = model.tool_call.call_count
    retry = brain.run(matter_id=current.id, turn_id="prepared_action", message=MESSAGE,
        limits=LoopLimits(_limits().budget, 12, _limits().per_call_tokens))
    assert retry.record == outcome.record and model.tool_call.call_count == calls
    assert len(store.load(current.id).action_proposals) == 1


@pytest.mark.parametrize("change", [
    {"package_id": "other"}, {"destination_quote": "invented registry"},
    {"destination_quote": ""}, {"authority": "approved"}, {"state": "approved"},
    {"content_digest": "a" * 64}, {"actor": "other"}, {"success": True},
])
def test_author_arguments_cannot_create_content_permission_or_destination(tmp_path, change):
    values = case(tmp_path)
    result = run(values, {**ARGS, **change})
    assert result.reason is StopReason.REFUSED
    assert not values[0].load("mat_loop").action_proposals


def test_missing_destination_stays_absent_and_narrow_scope_cannot_reach_package(tmp_path):
    values = case(tmp_path / "whole")
    assert run(values, {**ARGS, "destination_quote": None}).reason is StopReason.QUESTION
    proposal = action.rows(values[0].load("mat_loop"))[0]
    assert proposal.destination == "" and proposal.absent()
    narrow = case(tmp_path / "narrow", selected=("d1",))
    assert run(narrow).reason is StopReason.REFUSED
    assert not narrow[0].load("mat_loop").action_proposals


@pytest.mark.parametrize("field,value", [("verified", "true"), ("unknown_field", True)])
def test_lossy_package_reconstruction_cannot_back_an_action(tmp_path, field, value):
    def alter(row):
        if field == "verified":
            row["material_facts"][0][field] = value
        else:
            row[field] = value
        return row
    values = case(tmp_path, alter=alter)
    assert run(values).reason is StopReason.REFUSED
    assert not values[0].load("mat_loop").action_proposals
