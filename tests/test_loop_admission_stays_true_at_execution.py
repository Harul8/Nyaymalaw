"""The live runner must police admitted versions, not leave it to replay."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest
from nm.core.brain_context import ContextRefused
from nm.domain.loop import StopReason
from nm.domain.matter import Fact, Provenance, Thread
from nm.ports.model import Tier, ToolCall

from tests.test_the_controlled_brain_is_actually_wired import _brain
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("changed", ["provider", "model"])
def test_identity_is_pinned_across_rounds_not_readmitted_after_a_tool(tmp_path, changed):
    _store, model, brain = _brain(tmp_path)
    row = brain.registry._tools["read"]

    def change_after_read(args, context):
        receipt = row.handler(args, context)
        if changed == "provider":
            model.provider = "unapproved-provider"
        else:
            model.resolved_model.return_value = "unapproved-model"
        return receipt

    brain.registry._tools["read"] = replace(row, handler=change_after_read)
    model.tool_call.side_effect = [
        _response(ToolCall("first", "read", {})),
        _response(ToolCall("must-not-dispatch", "submit", {"answer": "Unchecked."}))]
    output = brain.run(matter_id="mat_loop", turn_id="runwide-identity",
                       message="Read the file.", limits=_limits())
    assert output.reason is StopReason.PROVIDER and not output.proposal
    assert model.tool_call.call_count == 1
    assert output.record.events[0].payload["model_identity"] == {
        "provider": "scripted", "model": "recorded-v1", "tier": "routine"}


@pytest.mark.parametrize("changed", ["selected_dispute", "source", "provider", "model"])
def test_free_retry_keeps_scope_source_and_provider_admission(tmp_path, changed):
    store, model, brain = _brain(tmp_path)
    original = store.load("mat_loop")
    threads = (Thread("d1", "First dispute"), Thread("d2", "Second dispute"))
    fact = Fact("fact_one", "Original recorded account.",
                Provenance("advocate_statement", "opening", span="Original recorded account."))
    store.commit(replace(original, threads=threads, facts=(fact,), version=original.version + 1),
                 expected_version=original.version)
    model.tool_call.return_value = _response(ToolCall("first", "submit", {"answer": "Private."}))
    brain.run(matter_id="mat_loop", turn_id="exact-retry", selected_issue_ids=("d1",),
              message="Review the selected dispute.", limits=_limits())
    selected = ("d1",)
    if changed == "selected_dispute":
        selected = ("d2",)
    elif changed == "source":
        current = store.load("mat_loop")
        store.commit(replace(current, facts=(replace(fact, statement="Corrected account."),),
                             version=current.version + 1), expected_version=current.version)
    elif changed == "provider":
        model.provider = "unapproved-provider"
    else:
        model.resolved_model.return_value = "unapproved-model"
    with pytest.raises((ValueError, ContextRefused)):
        brain.run(matter_id="mat_loop", turn_id="exact-retry", selected_issue_ids=selected,
                  message="Review the selected dispute.", limits=_limits())
    assert model.tool_call.call_count == 1


@pytest.mark.parametrize("changed", ["provider", "model", "tier"])
def test_a_completed_result_cannot_change_the_admitted_model_before_a_tool_runs(tmp_path, changed):
    store, model, brain = _brain(tmp_path)
    handler = Mock(side_effect=AssertionError("a switched provider's call executed"))
    row = brain.registry._tools["submit"]
    brain.registry._tools["submit"] = replace(row, handler=handler)
    result = _response(ToolCall("switched", "submit", {"answer": "Unverified candidate."}))
    result = replace(result, **{changed: {"provider": "unexpected-provider",
        "model": "different-model", "tier": Tier.JUDGE}[changed]})
    model.tool_call.return_value = result
    outcome = brain.run(matter_id="mat_loop", turn_id="changed-identity",
                       message="Read the current file.", limits=_limits())
    assert outcome.reason is StopReason.PROVIDER
    assert not handler.called and not outcome.proposal
    assert outcome.record.terminal
    assert outcome.budget.spend.cost_usd == result.usage.cost_usd
    assert store.load("mat_loop").loop_records == (outcome.record,)


def test_tool_contract_drift_after_a_provider_call_refuses_before_its_handler(tmp_path):
    _store, model, brain = _brain(tmp_path)
    handler = Mock(side_effect=AssertionError("unadmitted tool contract executed"))
    row = brain.registry._tools["read"]
    brain.registry._tools["read"] = replace(row, handler=handler)

    def changed_contract(*_args, **_kwargs):
        # Simulates configuration/hook drift, not new authorization from text.
        current = brain.registry._tools["read"]
        schema = dict(current.definition.parameters)
        schema["properties"] = {"unadmitted": {"type": "string"}}
        schema["required"] = ["unadmitted"]
        brain.registry._tools["read"] = replace(current,
            definition=replace(current.definition, parameters=schema))
        return _response(ToolCall("drifted", "read", {"unadmitted": "extra"}))

    model.tool_call.side_effect = changed_contract
    outcome = brain.run(matter_id="mat_loop", turn_id="changed-tool-contract",
                       message="Read the current file.", limits=_limits())
    assert outcome.reason is StopReason.REFUSED
    assert not handler.called and model.tool_call.call_count == 1
    assert outcome.record.terminal and not outcome.proposal


@pytest.mark.parametrize("source", ["constructor", "export"])
def test_tool_parameter_dictionaries_do_not_share_mutable_admission_state(source):
    from nm.core.tools import ToolRegistry

    from tests.test_the_loop_records_work_before_using_it import ALLOW, _registry

    original = _registry()
    rows = tuple(original._tools.values())
    registry = ToolRegistry(rows, before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    before = registry.version
    definition = rows[0].definition if source == "constructor" else registry.definitions[0]
    definition.parameters["properties"]["unadmitted"] = {"type": "string"}
    definition.parameters["required"].append("unadmitted")
    assert registry.version == before
    assert "unadmitted" not in registry.definitions[0].parameters["properties"]


@pytest.mark.parametrize("phase", ["before", "handler", "after"])
def test_tool_contract_changes_during_invocation_cannot_return_a_receipt(tmp_path, phase):
    from nm.core.tools import ToolContext, ToolRefused

    from tests.test_the_loop_records_work_before_using_it import ALLOW, _identity

    store, _model, brain = _brain(tmp_path)
    registry = brain.registry
    row = registry._tools["read"]
    called = Mock(wraps=row.handler)
    registry._tools["read"] = replace(row, handler=called)

    def change():
        current = registry._tools["read"]
        registry._tools["read"] = replace(current, version="unadmitted-version")

    def before(*_):
        if phase == "before":
            change()
        return ALLOW

    def handler(args, context):
        result = called(args, context)
        if phase == "handler":
            change()
        return result

    def after(*_):
        if phase == "after":
            change()
        return ALLOW

    registry._before, registry._after = before, after
    registry._tools["read"] = replace(row, handler=handler)
    identity = _identity(registry, store.load("mat_loop"))
    with pytest.raises(ToolRefused, match="contract changed"):
        registry.invoke(ToolCall("drift", "read", {}), ToolContext(identity))
    assert called.call_count == (0 if phase == "before" else 1)
