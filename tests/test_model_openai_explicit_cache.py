"""Offline SDK transport checks; never makes a provider request."""
from copy import deepcopy
import inspect
import json

import httpx2
import pytest
from openai import OpenAI
from openai.resources.responses.input_tokens import InputTokens

from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Prompt, Tier
from tests.test_model_openai_responses import FakeSession, SCHEMA, adapter


def sdk_port(model, text, *, structured):
    requests = []

    def transport(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path == "/v1/responses/input_tokens":
            return httpx2.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        assert request.url.path == "/v1/responses"
        return httpx2.Response(200, json={
            "id": "synthetic-response", "object": "response", "created_at": 0,
            "model": model, "status": "completed", "error": None,
            "incomplete_details": None,
            "usage": {"input_tokens": 100, "output_tokens": 10,
                      "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}},
            "output": [{"type": "message", "id": "synthetic-message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": text, "annotations": []}]}]})

    client = OpenAI(api_key="synthetic-no-network", base_url="http://fixture.invalid/v1",
        max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(transport)))
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", model, "unused", None)})
    session = FakeSession()
    return OpenAIModelAdapter(config, client=client, call_budget=session), client, requests, session


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol"])
@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("system", [None, "Exact stable instruction.", "Stable instruction. " * 800])
def test_installed_sdk_preserves_roles_words_schema_and_count(model, structured, system):
    original = '{"conversation":[{"text":"Exact earlier words\\n—not a finding."}],"latest":"New words"}'
    answer = '{"answer":"supported"}' if structured else "Supported."
    port, client, requests, session = sdk_port(model, answer, structured=structured)
    try:
        prompt = Prompt(user=original, system=system)
        result = (port.structured(prompt, deepcopy(SCHEMA), Tier.ROUTINE, max_tokens=200)
                  if structured else port.complete(prompt, Tier.ROUTINE, max_tokens=200))
    finally:
        client.close()
    assert len(requests) == 2
    count_path, counted = requests[0]
    generate_path, generated = requests[1]
    assert count_path == "/v1/responses/input_tokens" and generate_path == "/v1/responses"
    assert counted == {key: value for key, value in generated.items()
                      if key not in {"store", "max_output_tokens", "prompt_cache_options"}}
    expected = ([{"role": "system", "content": [{"type": "input_text", "text": system,
                    "prompt_cache_breakpoint": {"mode": "explicit"}}]}] if system else [])
    expected.append({"role": "user", "content": original})
    assert generated["input"] == expected
    assert generated["prompt_cache_options"] == {"mode": "explicit"}
    assert generated["truncation"] == "disabled" and generated["store"] is False
    assert generated["max_output_tokens"] == 200
    assert "previous_response_id" not in generated and "conversation" not in generated
    assert "prompt_cache_key" not in generated
    assert generated.get("text") == ({"format": {"type": "json_schema", "name": "nm_result",
        "strict": True, "schema": SCHEMA}} if structured else None)
    assert session.requests == [(model, 200, 100)]
    assert len(session.ledger.reserved) == len(session.ledger.settled) == 1
    # An ineligible or cold prefix is not an error and triggers no retry/prewarm.
    assert result.usage.cached_tokens == 0 and result.retries == 0
    assert prompt.system == system and prompt.user == original


def test_sdk_count_policy_argument_is_not_invented():
    assert "prompt_cache_options" not in inspect.signature(InputTokens.count).parameters


def test_changing_user_suffix_keeps_only_the_instruction_breakpoint():
    port, client = adapter()
    for user in ['{"draft":"one"}', '{"draft":"two","correction":"precise mismatch"}']:
        port.complete(Prompt(user=user, system="Exact stable instruction"), Tier.ROUTINE, max_tokens=200)
    first, second = client.calls
    assert first["input"][0] == second["input"][0]
    assert first["input"][1] != second["input"][1]
    assert all(isinstance(call["input"][1]["content"], str) for call in client.calls)
    assert client.counts == []  # Unbounded test port still adds no counting call.


def test_private_transport_does_not_mutate_the_callers_messages_or_schema():
    port, client = adapter()
    messages = [{"role": "system", "content": "\n Exact words\r\n"},
                {"role": "user", "content": "\u0c35\u0c3f\u0c35\u0c3e\u0c26\u0c02 — original"}]
    before, schema = deepcopy(messages), deepcopy(SCHEMA)
    port._responses_request(messages, port._cfg(Tier.ROUTINE), schema, 200)
    assert messages == before and schema == SCHEMA
    assert client.calls[0]["input"][0]["content"][0]["text"] == before[0]["content"]


def test_legacy_chat_never_receives_responses_cache_fields():
    port, client = adapter(model="gpt-4.1-mini-2025-04-14")
    port.structured(Prompt(user="Exact user", system="Exact system"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert client.calls[0]["messages"] == [{"role": "system", "content": "Exact system"},
                                           {"role": "user", "content": "Exact user"}]
    assert "prompt_cache_options" not in client.calls[0]
    assert client.counts == []
