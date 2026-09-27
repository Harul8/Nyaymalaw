"""Outgoing capacity is measured; private thoughts never become matter atoms."""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest
from nm.core.brain_context import (
    ContextPolicy,
    ContextRefused,
    ContextSession,
    assemble_brief,
    saved_source_references,
)
from nm.core.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    object_schema,
)
from nm.domain.loop import StepKind, StopReason
from nm.ports.model import ToolCall, ToolDefinition, ToolMessage, estimate_tokens, tool_request_text

from tests.test_brain_context_is_a_checked_file_projection import file_fixture, snapshot, tools
from tests.test_independent_claim_verifier import finding
from tests.test_nested_research_has_one_budget_and_one_writer import LIMITS, setup
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def source(name="read_large", *, span=None):
    held = finding(span=span or ("Unshortened source paragraph. " * 8000))
    return ToolEnvelope(name, "held-v1", ToolKind.SOURCE, ToolOutcome.RESULTS,
                        Availability.AVAILABLE, Assessment.NOT_ASSESSED,
                        {"index": "held exact primary text", "locators": [held.locator],
                         "source_version": "source-v1"}, {"findings": [held.as_record()]},
                        "Text was read; its support and application remain unassessed.")


@pytest.mark.parametrize("safe_loader", [True, False])
def test_actual_lead_request_compacts_only_when_its_outgoing_bytes_need_it(tmp_path, safe_loader):
    store, model, brain, _ = setup(tmp_path)
    brain._runner._current_matter = store.load if safe_loader else None
    model.context_budget.return_value = 14000
    receipt = source()
    brain.registry = brain.registry.extend((RegisteredTool(
        ToolDefinition("read_large", "Read exact long material.", object_schema({})),
        ToolKind.SOURCE, "held-v1", True, ("unbound_source_control",), lambda *_: receipt),))
    brain._runner._tools = brain.registry

    def response(prompt, definitions, _tier, *, messages, **_kw):
        assert estimate_tokens(tool_request_text(prompt, definitions, messages)) + 400 <= 14000
        if model.tool_call.call_count == 1:
            return _response(ToolCall("law", "read_large", {}))
        case = json.loads(messages[0].text)["data"]
        assert case["facts"][0]["statement"] == file_fixture().facts[0].statement
        assert case["facts"][0]["confirmed"] is None
        assert case["action_proposals"][0]["state"] == "proposed"
        references = json.loads(messages[-1].text)["data"]
        assert references[0]["locators"] == [finding().locator]
        assert references[0]["read_again_before_dependent_work"] is True
        assert references[0]["assessment"] == "not_assessed"
        assert receipt.data["findings"][0]["span"] not in messages[-1].text
        return _response(ToolCall("finish", "submit", {"answer": "Checked case still asserted."}))

    model.tool_call.side_effect = response
    output = brain.run(matter_id="mat_loop", turn_id="capacity",
                       message="Assess the first dispute.",
                       selected_issue_ids=("dispute_one",), limits=LIMITS)
    assert output.reason is (StopReason.PROPOSAL if safe_loader else StopReason.CONTEXT)
    calls = [row for row in output.record.events if row.kind is StepKind.MODEL_STARTED]
    assert len(calls) == (2 if safe_loader else 1)
    if safe_loader:
        assert [row.payload["context"]["generation"] for row in calls] == [1, 2]
        original = calls[-1].payload["context"]["transcript"]
        assert any(receipt.data["findings"][0]["span"] in row["text"] for row in original)
    stored_source = next(row.payload["receipt"] for row in output.record.events
                         if row.kind is StepKind.TOOL_RETURNED)
    assert stored_source == json.loads(receipt.wire())
    assert store.load("mat_loop").facts == file_fixture().facts


def test_actual_child_compaction_preserves_its_task_scope_and_source_read(tmp_path):
    receipt = source(name="read_law")
    _, model, brain, _ = setup(tmp_path, source_handler=lambda *_: receipt)
    model.context_budget.return_value = 14000
    model.tool_call.side_effect = [
        _response(ToolCall("research", "research", {
            "question": "Read material for the notice condition", "issue_ids": ["dispute_one"]})),
        _response(ToolCall("long", "read_law", {})),
        _response(ToolCall("done", "finish_research", {"findings": [], "observations": []})),
        _response(ToolCall("parent", "submit", {"answer": "No semantic clearance claimed."})),
    ]
    output = brain.run(matter_id="mat_loop", turn_id="child-capacity", message="Assess the file.",
                       selected_issue_ids=("dispute_one",), limits=LIMITS)
    returned = next(row.payload for row in output.record.events
                    if row.kind is StepKind.TOOL_RETURNED and row.payload["call_id"] == "research")
    trace = returned["child_transcript"]
    rebuilt = next(row["context"] for row in trace if row["kind"] == "context_compacted")
    assert rebuilt["generation"] == 2
    current_case = json.loads(rebuilt["messages"][0]["text"])["data"]
    assert current_case["task"]["issue_ids"] == ["dispute_one"]
    assert current_case["previous_narrative"] == "not_inherited"
    assert "An unrelated employment allegation." not in rebuilt["messages"][0]["text"]
    assert any(receipt.data["findings"][0]["span"] in row["text"]
               for row in rebuilt["transcript"])
    assert returned["child_steps"] == sum(row["kind"] in ("model_started", "tool_started")
                                          for row in trace)
    assert returned["receipt"]["data"]["research"]["state"] == "not_assessed"


def test_deferred_archive_cannot_dispatch_an_oversized_request():
    matter = file_fixture()
    context = ContextSession(snapshot(), tools(), assemble_brief(matter, advocate_id="advocate"),
                             provider="scripted", model="held", policy=ContextPolicy(14000, 400))
    original = context.to_record()
    context.append(ToolMessage("user", "unchecked narrative " * 30000), defer_fit=True)
    with pytest.raises(ContextRefused):
        context.assert_request(context.system, context.messages, model="held")
    assert context.transcript[:len(original["transcript"])]
    assert matter.facts == file_fixture().facts


@pytest.mark.parametrize("bad", ["invented_locator", "wrong_kind", "truncated_case"])
def test_compaction_cannot_invent_sources_or_trim_a_selected_case(bad):
    receipt = json.loads(source(span="An exact source condition.").wire())
    if bad == "invented_locator":
        receipt["receipt"]["locators"] = ["not-the-read-source"]
    elif bad == "wrong_kind":
        receipt["kind"] = "matter"
    else:
        matter = replace(file_fixture(), facts=(replace(file_fixture().facts[0],
            statement="Exact case material, not a summary. " * 30000), *file_fixture().facts[1:]))
        with pytest.raises(ContextRefused):
            assemble_brief(matter, ("dispute_one",), ContextPolicy(14000, 400),
                           advocate_id="advocate")
        return
    with pytest.raises(ContextRefused):
        saved_source_references((receipt,))


def test_contrary_facts_outside_initial_scope_survive_source_projection_and_compaction():
    file = file_fixture()
    first, second, third = file.facts
    first = replace(first, conflicts_with=(third.id,))
    file = replace(file, facts=(first, second, third))
    brief = assemble_brief(file, ("dispute_one",), advocate_id="advocate")
    case = json.loads(brief.text)["data"]
    assert [row["statement"] for row in case["facts"]] == [row.statement for row in file.facts]
    context = ContextSession(snapshot(), tools(), brief, provider="scripted", model="held")
    context.append(ToolMessage("assistant", "UNSUPPORTED conclusion to forget."))
    context.compact(file, reason="actual request capacity reached")
    assert "UNSUPPORTED conclusion" not in context.messages[0].text
    assert context.messages[0].text == brief.text
    assert context.transcript[-2].text == "UNSUPPORTED conclusion to forget."
    assert file.facts[0].confirmed is None


def test_stable_prefix_indexes_schemas_without_paying_for_a_second_schema_copy():
    from nm.domain.loop import digest

    marker = "FULL_SCHEMA_PROPERTY_IS_SENT_EXACTLY_ONCE"
    definition = ToolDefinition("deep_tool", "A declared tool.", object_schema({
        marker: {"type": "string", "description": "Exact supported property " * 300},
    }))
    context = ContextSession(
        snapshot(), (definition,), assemble_brief(file_fixture(), advocate_id="advocate"),
        provider="scripted", model="held")
    prefix = json.loads(context.system.split("TRUSTED TOOL DEFINITIONS\n", 1)[1].split("\n", 1)[0])
    assert prefix == [{"name": definition.name, "description": definition.description,
                       "schema_identity": digest(definition.parameters)}]
    from nm.ports.model import Prompt

    request = tool_request_text(Prompt("Read the file", context.system), (definition,),
                                context.messages)
    # The property's name occurs in both `properties` and `required` within
    # one schema. Count the unique body instead, and check the actual wire
    # schema rather than mistaking that required-name reference for a copy.
    assert marker not in context.system
    assert request.count("Exact supported property " * 300) == 1
    assert json.loads(request)["tools"][0]["parameters"] == definition.parameters
    assert context.to_record()["tool_specs"][0]["parameters"] == definition.parameters
    # Both actual schema mutation and catalogued description mutation fail;
    # reducing duplicate bytes never relaxes the contract identity.
    old = copy.deepcopy(context.tool_specs)
    context.tool_specs[0]["parameters"]["properties"][marker]["type"] = "number"
    with pytest.raises(ContextRefused):
        context.assert_request(context.system, context.messages, model="held")
    context.tool_specs = old
    context.tool_specs[0]["description"] = "Other capabilities"
    with pytest.raises(ContextRefused):
        context.assert_request(context.system, context.messages, model="held")
