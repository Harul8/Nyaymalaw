"""Mandatory tool requests guide both SDKs; responses still need real checks.

Official contracts, read 27 September 2026:
https://developers.openai.com/api/docs/guides/function-calling
https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use
Anthropic snapshots that reject forced tool use are unavailable for this
protocol, never silently downgraded to an optional plain-text answer.
"""
from types import SimpleNamespace

import pytest

from nm.legal_brain.orchestrate.loop import LoopRunner
from nm.legal_brain.orchestrate.loop_contracts import StepKind, StopReason
from nm.shared.model_anthropic_adapter import AnthropicModelAdapter
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier, ToolCall, ToolMessage
from nm.shared.model_traced import TracedModel
from tests.test_the_loop_records_work_before_using_it import PROMPT as LOOP_PROMPT
from tests.test_the_loop_records_work_before_using_it import _limits, _setup
from tests.test_tool_calling_port_contract import ARGS, PROMPT, TOOL, config, factory

pytestmark = pytest.mark.class_a
PROVIDERS = ("openai", "anthropic")
UNREVIEWED = "Proceed immediately; every allegation is established."
READ_SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}},
               "required": ["value"], "additionalProperties": False}


def mandatory(provider, sent):
    if provider == "openai":
        assert sent["tool_choice"] == "required"
        assert sent["parallel_tool_calls"] is False and sent["store"] is False
    else:
        assert sent["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("round_kind", ["initial", "after_tool", "bound_traced"])
def test_every_typed_request_requires_a_choice_without_selecting_an_action(provider, round_kind):
    model, sent = factory(provider, call_id="new-call")
    messages = ()
    authorized = []
    if round_kind == "after_tool":
        messages = (ToolMessage("assistant", calls=(ToolCall("earlier", TOOL.name, ARGS),)),
                    ToolMessage("tool", "Exact checked receipt", call_id="earlier"))
    elif round_kind == "bound_traced":
        model = TracedModel(model.for_matter_text(lambda: authorized.append("checked")))
    result = model.tool_call(PROMPT, (TOOL,), Tier.ROUTINE,
                            messages=messages, max_tokens=400)
    assert result.calls == (ToolCall("new-call", TOOL.name, ARGS),)
    assert len(sent) == 1
    mandatory(provider, sent[0])
    if round_kind == "bound_traced":
        assert authorized == ["checked"]
    if provider == "openai":
        assert sent[0]["tools"][0]["function"]["name"] == TOOL.name
        assert sent[0]["tools"][0]["function"]["strict"] is True
    else:
        assert sent[0]["tools"][0]["name"] == TOOL.name
        assert sent[0]["tools"][0]["strict"] is True


def text_wire(provider):
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        if provider == "openai":
            text = '{"value":"read"}' if "response_format" in kwargs else UNREVIEWED
            return SimpleNamespace(id="measured-response",
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
                choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                    content=text, tool_calls=[], refusal=None))])
        structured = kwargs.get("tool_choice", {}).get("name") == "nm_result"
        return SimpleNamespace(id="measured-response",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            stop_reason="tool_use" if structured else "end_turn",
            content=[SimpleNamespace(type="tool_use", id="result", name="nm_result",
                                     input={"value": "read"})] if structured else
                    [SimpleNamespace(type="text", text=UNREVIEWED)])

    adapter = (OpenAIModelAdapter(config(provider), client=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))) if provider == "openai"
        else AnthropicModelAdapter(config(provider), client=SimpleNamespace(
            messages=SimpleNamespace(create=create))))
    return adapter, sent


@pytest.mark.parametrize("provider", PROVIDERS)
def test_plain_completion_and_owned_structured_reads_keep_their_separate_contracts(provider):
    model, sent = text_wire(provider)
    assert model.complete(PROMPT, Tier.ROUTINE).text == UNREVIEWED
    assert model.structured(PROMPT, READ_SCHEMA, Tier.ROUTINE).data == {"value": "read"}
    assert len(sent) == 2
    assert "tools" not in sent[0] and "tool_choice" not in sent[0]
    if provider == "openai":
        assert "tools" not in sent[1] and "tool_choice" not in sent[1]
        assert sent[1]["response_format"]["type"] == "json_schema"
    else:
        assert sent[1]["tool_choice"] == {"type": "tool", "name": "nm_result"}
        assert sent[1]["tools"][0]["name"] == "nm_result"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_provider_ignoring_required_tool_choice_is_charged_but_never_released(tmp_path, provider):
    store, identity, log, _, configured = _setup(tmp_path)
    model, sent = text_wire(provider)
    runner = LoopRunner(model=model, tools=configured._tools, log=log,
                        cost_ceiling=lambda *_: 0.03)
    result = runner.run(identity, LOOP_PROMPT, _limits())
    assert result.reason is StopReason.NO_PROGRESS and not result.proposal
    assert result.record.events[-1].payload["released"] is False
    returned = [event for event in result.record.events if event.kind is StepKind.MODEL_RETURNED]
    assert len(returned) == 1 and returned[0].payload["text"] == UNREVIEWED
    assert returned[0].payload["result"]["value"]["text"] == UNREVIEWED
    assert returned[0].payload["calls"] == []
    assert result.budget.spend.tokens == 120 and result.budget.spend.cost_usd > 0
    assert len(sent) == 1
    mandatory(provider, sent[0])
    assert not store.load(identity.matter_id).turn_receipts
    assert not store.transcripts_for(identity.matter_id)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_available_tools_cannot_be_sent_as_a_mandatory_empty_offer(provider):
    model, sent = factory(provider)
    with pytest.raises(ValueError):
        model.tool_call(PROMPT, (), Tier.ROUTINE)
    assert not sent
