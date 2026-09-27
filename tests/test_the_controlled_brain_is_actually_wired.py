"""P49/P53 exercised together; no standalone helper masquerades as a journey."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.orchestrate.loop_contracts import LoopMode, StopReason
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.common.principles_port import PrinciplesSnapshot
from nm.shared.model_port import ToolCall
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_the_loop_records_work_before_using_it import _limits, _response, _setup

pytestmark = pytest.mark.class_a


def _brain(tmp_path):
    store, identity, log, model, runner = _setup(tmp_path)
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100_000
    scope = EvaluationScope("OWNER-20260927-CONTROLLED", identity.advocate_id,
                            frozenset({identity.matter_id}), LoopMode.SYNTHETIC)
    brain = ControlledBrain(store=store, model=model, principles=FilePrinciples(), log=log,
                            registry=runner._tools, scope=scope,
                            cost_ceiling=lambda *_: 0.03, session_current=lambda: True)
    return store, model, brain


def test_checked_context_principles_tool_receipts_and_proposal_survive_restart(tmp_path):
    store, model, brain = _brain(tmp_path)

    def response(prompt, _tools, _tier, *, messages, **_kw):
        assert prompt.system and "TRUSTED TOOL DEFINITIONS" in prompt.system
        assert "untrusted_data_not_instructions" in messages[0].text
        assert "Private dispute" in messages[0].text
        if model.tool_call.call_count == 1:
            return _response(ToolCall("c1", "read", {}))
        assert messages[-1].role == "tool" and messages[-1].call_id == "c1"
        return _response(ToolCall("c2", "submit", {"answer": "A proposal, not advice."}))

    model.tool_call.side_effect = response
    output = brain.run(matter_id="mat_loop", turn_id="controlled_turn",
                       message="What needs checking first?", limits=_limits())
    assert output.reason is StopReason.PROPOSAL
    start = output.record.events[0].payload
    assert start["context"]["principles"]["sha256"] == output.record.identity.principles_version
    assert len(store.load("mat_loop").loop_records) == 1
    assert not store.load("mat_loop").turn_receipts
    repeat = brain.run(matter_id="mat_loop", turn_id="controlled_turn",
                       message="What needs checking first?", limits=_limits())
    assert repeat == output and model.tool_call.call_count == 2


@pytest.mark.parametrize("mutate", ["instruction", "principles", "scope", "session"])
def test_controlled_admission_cannot_be_inherited_by_a_changed_request(tmp_path, mutate):
    _, model, brain = _brain(tmp_path)
    model.tool_call.return_value = _response(ToolCall("c1", "submit", {"answer": "x"}))
    brain.run(matter_id="mat_loop", turn_id="controlled_turn", message="Original", limits=_limits())
    message = "Original"
    if mutate == "instruction":
        message = "Different instructions"
    elif mutate == "principles":
        text = "Changed principles"
        brain.principles = Mock(load=lambda: PrinciplesSnapshot(
            text, hashlib.sha256(text.encode()).hexdigest()))
    elif mutate == "scope":
        brain.scope = replace(brain.scope, matter_ids=frozenset({"other"}))
    else:
        brain._session_current = lambda: False
    with pytest.raises((ValueError, PermissionError)):
        brain.run(matter_id="mat_loop", turn_id="controlled_turn", message=message,
                  limits=_limits())
    assert model.tool_call.call_count == 1


def test_a_different_actor_cannot_read_the_controlled_journal(tmp_path):
    store, _, brain = _brain(tmp_path)
    brain.log = MatterLoopLog(store, advocate_id="different_actor")
    brain._runner._log = brain.log
    with pytest.raises(PermissionError):
        brain.run(matter_id="mat_loop", turn_id="t", message="Read the file", limits=_limits())
