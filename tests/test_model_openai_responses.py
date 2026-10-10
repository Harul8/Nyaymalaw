"""Offline provider-shape checks for the live GPT-6 adapter."""
from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import (ConfigurationError, ContentRefused, OutputTruncated,
    Prompt, ProviderUnavailable, SchemaViolation, Tier, ToolDefinition)

from nm.shared.model_openai_adapter import OpenAIModelAdapter as Adapter

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"],
          "properties": {"answer": {"type": "string"}}}

def response(model="gpt-6.1-sol", text='{"answer":"supported"}', status="completed",
             cached=30, written=20, incoming=100, outgoing=10):
    return N(id="response-owned", model=model, status=status, error=None, incomplete_details=None,
             usage=N(input_tokens=incoming, output_tokens=outgoing,
                     input_tokens_details=N(cached_tokens=cached, cache_write_tokens=written)),
             output=[N(type="reasoning", summary=[]), N(type="message", role="assistant",
                     status="completed", content=[N(type="output_text", text=text)])])

class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.counts = []
        self.count_result = N(object="response.input_tokens", input_tokens=100)
        self.responses = N(create=self.create, input_tokens=N(count=self.count))
        self.chat = N(completions=N(create=self.chat_create))
    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return self.result
    def count(self, **kwargs):
        self.counts.append(deepcopy(kwargs))
        return self.count_result
    def chat_create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return N(id="legacy", usage=N(prompt_tokens=100, completion_tokens=10,
             prompt_tokens_details=N(cached_tokens=30)),
             choices=[N(finish_reason="stop", message=N(content='{"answer":"supported"}'))])

class FakeLedger:
    def __init__(self):
        self.reserved = []
        self.settled = []
    def reserve(self, model):
        self.reserved.append(model)
        return "owned-reservation"
    def settle(self, token, result):
        self.settled.append((token, result))

class FakeSession(SessionCallBudget):
    def __init__(self):
        self.requests = []
        self.ledger = FakeLedger()
    def for_request(self, model, output_tokens, *, input_upper_bound=None):
        self.requests.append((model, output_tokens, input_upper_bound))
        return self.ledger, output_tokens or 200

def adapter(model="gpt-6.1-sol", result=None, budget=None):
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", model, "unused", None)})
    client = FakeClient(result or response(model=model))
    return Adapter(config, client=client, call_budget=budget), client

@pytest.mark.parametrize("model,effort", [("gpt-6.1-sol", "low"), ("gpt-6-luna", "none")])
def test_exact_responses_payload_is_counted_without_trimming(model, effort):
    session = FakeSession()
    port, client = adapter(model=model, budget=session)
    permissions = []
    port = port.for_matter_text(lambda: permissions.append("checked"))
    prompt = Prompt(user="Exact original account — with qualifications.", system="Stable instructions")
    result = port.structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=200)
    generated = client.calls[0]
    assert generated["input"] == [{"role": "system", "content": [{"type": "input_text", "text": prompt.system, "prompt_cache_breakpoint": {"mode": "explicit"}}]}, {"role": "user", "content": prompt.user}]
    assert generated["reasoning"] == {"effort": effort}
    assert generated["store"] is False and generated["truncation"] == "disabled"
    assert generated["text"]["format"] == {"type": "json_schema", "name": "nm_result", "strict": True, "schema": SCHEMA}
    assert client.counts == [{k:v for k,v in generated.items() if k not in {"store", "max_output_tokens", "prompt_cache_options"}}]
    assert session.requests == [(model, 200, 100)]
    assert permissions == ["checked", "checked"]
    settled = session.ledger.settled[0][1]
    assert settled.model == model and settled.usage.prompt_tokens == 100
    assert settled.usage.prompt_tokens_details.cache_write_tokens == 20
    assert result.data == {"answer":"supported"}
    assert result.usage.cached_tokens == 30 and result.usage.provider_extra["cache_write_tokens"] == 20
    assert result.usage.cost_usd == port._config.for_tier(Tier.ROUTINE).cost(100,10,cached_tokens=30,cache_write_tokens=20)

def test_uncapped_request_does_not_add_count_request():
    port, client = adapter()
    port.structured(Prompt("Exact text"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert len(client.calls) == 1 and client.counts == []

@pytest.mark.parametrize("count", [None, True, 0, -1, 1.5])
def test_missing_invalid_input_count_prevents_reservation_and_generation(count):
    session = FakeSession()
    port, client = adapter(budget=session)
    client.count_result.input_tokens = count
    with pytest.raises(ProviderUnavailable):
        port.complete(Prompt("Exact text"), Tier.ROUTINE, max_tokens=200)
    assert not client.calls and not session.requests and not session.ledger.reserved

def test_permission_is_checked_before_count_and_again_before_generation():
    session = FakeSession()
    port, client = adapter(budget=session)
    def refuse():
        raise ConfigurationError("Permission unavailable")
    with pytest.raises(ConfigurationError):
        port.for_matter_text(refuse).complete(Prompt("Exact text"), Tier.ROUTINE, max_tokens=200)
    assert not client.counts and not client.calls

@pytest.mark.parametrize("cached,written", [(None,0),(0,None),(True,0),(0,False),(-1,0),(60,50)])
def test_gpt6_cache_counter_gap_cannot_be_priced_as_zero(cached, written):
    port, client = adapter(result=response(cached=cached, written=written))
    with pytest.raises(ProviderUnavailable) as caught:
        port.complete(Prompt("Exact text"), Tier.ROUTINE, max_tokens=200)
    assert caught.value.usage is None

@pytest.mark.parametrize("status,reason,error", [
    ("incomplete","max_output_tokens",OutputTruncated),
    ("incomplete","content_filter",ContentRefused),
    ("in_progress",None,SchemaViolation),
    ("failed",None,ProviderUnavailable),
])
def test_unfinished_output_never_becomes_a_completed_quarantine(status,reason,error):
    result = response(status=status)
    result.incomplete_details = N(reason=reason) if reason else None
    session = FakeSession()
    port, client = adapter(result=result, budget=session)
    with pytest.raises(error) as caught:
        port.structured(Prompt("Exact text"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert caught.value.usage.cost_usd > 0
    assert getattr(caught.value,"rejected_result",None) is None
    assert len(session.ledger.settled) == 1

def test_refusal_is_not_partial_text_salvage():
    result = response()
    result.output[-1].content.append(N(type="refusal",refusal="No"))
    port, _ = adapter(result=result)
    with pytest.raises(ContentRefused):
        port.structured(Prompt("Exact text"), SCHEMA, Tier.ROUTINE, max_tokens=200)

@pytest.mark.parametrize("change", ["tool","second_message","incomplete_message","bad_part"])
def test_ambiguous_output_shape_cannot_enter_quarantine(change):
    result = response()
    if change == "tool": result.output.append(N(type="function_call",name="unexpected"))
    if change == "second_message": result.output.append(deepcopy(result.output[-1]))
    if change == "incomplete_message": result.output[-1].status="incomplete"
    if change == "bad_part": result.output[-1].content.append(N(type="unknown"))
    port, _ = adapter(result=result)
    with pytest.raises(SchemaViolation) as caught:
        port.structured(Prompt("Exact text"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert caught.value.rejected_result is None and caught.value.usage.cost_usd>0

def test_completed_structured_object_keeps_existing_quarantine_contract():
    port, _ = adapter(result=response(text='{"unexpected":"value"}'))
    with pytest.raises(SchemaViolation) as caught:
        port.structured(Prompt("Exact text"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert caught.value.rejected_result.data == {"unexpected":"value"}
    assert caught.value.rejected_result.usage.cost_usd>0

def test_plain_multiple_text_parts_preserve_every_exact_character():
    result=response(text="First ")
    result.output[-1].content.append(N(type="output_text",text="second."))
    port,_=adapter(result=result)
    assert port.complete(Prompt("Exact text"),Tier.ROUTINE,max_tokens=200).text=="First second."

def test_sol_chat_tools_fail_before_dispatch_or_reservation():
    session=FakeSession()
    port,client=adapter(budget=session)
    tool=ToolDefinition("read","Read",SCHEMA)
    with pytest.raises(ConfigurationError,match="tool calling"):
        port.tool_call(Prompt("Exact text"),(tool,),Tier.ROUTINE,max_tokens=200)
    assert not client.calls and not client.counts and not session.requests

def test_legacy_chat_shape_and_cached_read_cost_remain_supported():
    port,client=adapter(model="gpt-4.1-mini-2025-04-14")
    result=port.structured(Prompt("Exact text","Stable"),SCHEMA,Tier.ROUTINE,max_tokens=200)
    assert "messages" in client.calls[0] and "input" not in client.calls[0]
    assert not client.counts
    assert result.usage.cost_usd==port._config.for_tier(Tier.ROUTINE).cost(100,10,cached_tokens=30)
