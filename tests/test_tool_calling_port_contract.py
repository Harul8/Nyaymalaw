"""P49: the same proposals, correlation and refusals on every provider path.

SDK-shaped doubles prove the wire translation, not live provider quality.
Planted invalid arguments never become executable calls or free attempts.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace as NS  # noqa: N814 -- SDK-shaped fixture

import pytest

from nm.shared.egress_contracts import EgressRefused, Policy
from nm.shared.model_anthropic_adapter import AnthropicModelAdapter
from nm.shared.model_call_budget import MODEL, CallBudget
from nm.shared.model_config import PERMITTED_PROVIDERS, ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    require_schema,
    validate_tool_history,
)
from nm.shared.model_replay import RecordingModel, ReplayModel
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.model_traced import TracedModel

pytestmark = pytest.mark.class_a

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["locators"],
    "properties": {
        "locators": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "kind": {"type": ["string", "null"], "enum": ["passage", None]},
                },
            },
        }
    },
}
TOOL = ToolDefinition("read_sources", "Read exact held passage locators", SCHEMA)
ARGS = {"locators": [{"id": "held:17", "kind": "passage"}]}
PROMPT = Prompt("Assess the file", "Stable instructions", operation="reasoning_loop")
VERSIONS = {"principles": "p1", "tools": "t1", "sources": "s1"}


def config(provider):
    return ModelConfig(
        {
            Tier.ROUTINE: TierConfig(Tier.ROUTINE, provider, MODEL, "fake", None),
            Tier.EMBED: TierConfig(Tier.EMBED, provider, "text-embedding-3-large", "fake", None),
        }
    )


def factory(
    provider,
    *,
    arguments=None,
    name="read_sources",
    finish=None,
    call_id="call_1",
    error=None,
    budget=None,
    missing_usage=False,
):
    args = ARGS if arguments is None else arguments
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        if provider == "openai":
            return NS(
                id="response-1",
                usage=None if missing_usage else NS(prompt_tokens=100, completion_tokens=20),
                choices=[
                    NS(
                        finish_reason=finish or "tool_calls",
                        message=NS(
                            content=None,
                            tool_calls=[
                                NS(
                                    id=call_id,
                                    type="function",
                                    function=NS(name=name, arguments=json.dumps(args)),
                                )
                            ],
                        ),
                    )
                ],
            )
        return NS(
            id="response-1",
            usage=None if missing_usage else NS(input_tokens=100, output_tokens=20),
            stop_reason=finish or "tool_use",
            content=[NS(type="tool_use", id=call_id, name=name, input=args)],
        )

    if provider == "openai":
        model = OpenAIModelAdapter(
            config(provider), client=NS(chat=NS(completions=NS(create=create))), call_budget=budget
        )
    elif provider == "anthropic":
        model = AnthropicModelAdapter(
            config(provider), client=NS(messages=NS(create=create)), call_budget=budget
        )
    else:
        model = ScriptedModelAdapter(
            config(provider),
            tool_responses=(
                {"calls": [{"call_id": call_id, "name": name, "arguments": args}], "text": None},
            ),
        )
    return model, calls


def test_the_provider_contract_population_covers_every_permitted_provider():
    assert PERMITTED_PROVIDERS == {"openai", "anthropic", "scripted"}


@pytest.mark.parametrize("provider", sorted(PERMITTED_PROVIDERS))
def test_identical_tool_proposals_are_normalised_on_every_provider(provider):
    model, _ = factory(provider)
    assert isinstance(model, ModelPort)
    result = model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, max_tokens=2048)
    assert result.usable and result.calls == (ToolCall("call_1", TOOL.name, ARGS),)
    assert result.usage.tokens_in > 0 and result.usage.tokens_out > 0


@pytest.mark.parametrize("provider", sorted(PERMITTED_PROVIDERS))
@pytest.mark.parametrize(
    "mutate",
    [
        lambda args: args["locators"][0].update(kind="invented"),
        lambda args: args["locators"][0].pop("id"),
        lambda args: args["locators"][0].update(extra="undeclared"),
        lambda args: args.update(locators=[False]),
        lambda args: args.update(locators="not an array"),
    ],
)
def test_nested_invalid_arguments_never_become_executable_proposals(provider, mutate):
    args = copy.deepcopy(ARGS)
    mutate(args)
    model, _ = factory(provider, arguments=args)
    with pytest.raises(SchemaViolation):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)


@pytest.mark.parametrize("provider", sorted(PERMITTED_PROVIDERS))
def test_undeclared_tool_proposals_are_refused(provider):
    model, _ = factory(provider, name="arbitrary_database")
    with pytest.raises(SchemaViolation, match="Undeclared"):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_completed_call_receipt_and_usage_survive_a_rejected_output(provider):
    model, _ = factory(provider, finish="length" if provider == "openai" else "max_tokens")
    with pytest.raises(OutputTruncated) as error:
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
    assert error.value.usage.tokens_in == 100
    assert error.value.usage.cost_usd > 0


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_unknown_usage_is_not_a_free_successful_call(provider):
    model, _ = factory(provider, missing_usage=True)
    with pytest.raises((ProviderUnavailable, SchemaViolation)):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)


def test_nested_schema_rules_apply_to_ordinary_structured_reads_too():
    with pytest.raises(SchemaViolation):
        require_schema({"locators": [{"id": "a", "kind": "invented"}]}, SCHEMA)


@pytest.mark.parametrize("provider", sorted(PERMITTED_PROVIDERS))
def test_full_transcript_and_tool_schema_consume_context_before_dispatch(provider):
    model, wire = factory(provider)
    messages = (ToolMessage("user", "x" * 500_000),)
    with pytest.raises(ContextOverflow):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, messages=messages)
    assert not wire


@pytest.mark.parametrize(
    "messages",
    [
        (ToolMessage("tool", "receipt", call_id="orphan"),),
        (ToolMessage("assistant", calls=(ToolCall("a", TOOL.name, ARGS),)),),
        (
            ToolMessage("assistant", calls=(ToolCall("a", TOOL.name, ARGS),)),
            ToolMessage("user", "jump past unresolved call"),
        ),
        (
            ToolMessage("assistant", calls=(ToolCall("a", TOOL.name, ARGS),)),
            ToolMessage("tool", "receipt", call_id="a"),
            ToolMessage("tool", "duplicate", call_id="a"),
        ),
    ],
)
def test_incomplete_or_orphaned_tool_rounds_are_rejected_before_dispatch(messages):
    model, wire = factory("openai")
    with pytest.raises(ValueError):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, messages=messages)
    assert not wire


def test_context_can_observe_pending_calls_without_owning_a_second_validator():
    messages = (ToolMessage("assistant", calls=(ToolCall("a", TOOL.name, ARGS),)),)
    assert validate_tool_history(messages, allow_pending=True) == ("a",)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_the_same_append_only_history_is_translated_to_provider_native_receipts(provider):
    model, wire = factory(provider, call_id="next_call")
    messages = (
        ToolMessage("assistant", calls=(ToolCall("old_call", TOOL.name, ARGS),)),
        ToolMessage("tool", '{"state":"not_assessed"}', call_id="old_call"),
    )
    model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, messages=messages)
    sent = wire[0]
    if provider == "openai":
        assert sent["store"] is False
        assert sent["messages"][-1]["tool_call_id"] == "old_call"
        assert sent["tools"][0]["function"]["strict"] is True
    else:
        assert sent["messages"][-1]["content"][0]["tool_use_id"] == "old_call"
        assert sent["tools"][0]["strict"] is True


@pytest.mark.parametrize(
    "fault", [NameError("connection"), KeyError("timeout"), TypeError("rate limit")]
)
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_programming_faults_never_masquerade_as_provider_outages(provider, fault):
    model, _ = factory(provider, error=fault)
    with pytest.raises(type(fault)):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)


def test_egress_refusal_precedes_the_new_tool_call_route():
    inner, wire = factory("openai")
    model = PolicedModel(inner, Policy(processors=()))
    with pytest.raises(EgressRefused):
        model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
    assert not wire


def test_tool_calls_are_traced_without_being_misreported_as_empty():
    inner, _ = factory("scripted")
    trace = TracedModel(inner)
    result = trace.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
    assert result.calls and trace.take()["empty"] == 0


def test_rejected_proposal_cost_is_kept_in_the_budget_and_trace(tmp_path):
    budget = CallBudget(tmp_path / "ledger.db", "1")
    inner, _ = factory("openai", name="undeclared", budget=budget)
    traced = TracedModel(inner)
    with pytest.raises(SchemaViolation):
        traced.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
    (call,) = traced.take()["calls"]
    assert call["failed"] and call["tokens"]["in"] == 100
    import sqlite3

    with sqlite3.connect(budget.path) as db:
        assert db.execute("SELECT state,charge FROM attempts").fetchone() == ("measured", 27)


def test_record_and_replay_match_exactly_without_a_client_or_api_key():
    inner, _ = factory("scripted")
    recorder = RecordingModel(inner, versions=VERSIONS)
    expected = recorder.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, max_tokens=100)
    replay = ReplayModel(recorder.records, versions=VERSIONS)
    assert isinstance(replay, ModelPort)
    assert replay.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, max_tokens=100) == expected
    assert replay.position == 1


@pytest.mark.parametrize(
    "change", ["prompt", "prefix", "tools", "messages", "tier", "ceiling", "versions"]
)
def test_replay_refuses_any_changed_request_without_consuming_the_record(change):
    inner, _ = factory("scripted")
    recorder = RecordingModel(inner, versions=VERSIONS)
    recorder.tool_call(PROMPT, (TOOL,), Tier.ROUTINE, max_tokens=100)
    prompt, tools, messages, tier, ceiling, versions = (
        PROMPT,
        (TOOL,),
        (),
        Tier.ROUTINE,
        100,
        VERSIONS,
    )
    if change == "prompt":
        prompt = Prompt("Changed facts", PROMPT.system)
    if change == "prefix":
        prompt = Prompt(PROMPT.user, "Changed principles")
    if change == "tools":
        tools = (ToolDefinition(TOOL.name, "Changed description", SCHEMA),)
    if change == "messages":
        messages = (ToolMessage("user", "Changed file"),)
    if change == "tier":
        tier = Tier.HARD
    if change == "ceiling":
        ceiling = 101
    if change == "versions":
        versions = {**VERSIONS, "principles": "p2"}
    replay = ReplayModel(recorder.records, versions=versions)
    with pytest.raises(SchemaViolation):
        replay.tool_call(prompt, tools, tier, messages=messages, max_tokens=ceiling)
    assert replay.position == 0


def test_replay_does_not_trust_changed_result_bytes():
    inner, _ = factory("scripted")
    recorder = RecordingModel(inner, versions=VERSIONS)
    recorder.tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
    recorder.records[0]["result"]["value"]["calls"][0]["arguments"] = {}
    with pytest.raises(SchemaViolation, match="integrity"):
        ReplayModel(recorder.records, versions=VERSIONS).tool_call(PROMPT, (TOOL,), Tier.ROUTINE)
