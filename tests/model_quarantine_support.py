"""Completed rejected envelopes stay errors while owned rows remain inspectable."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from nm.shared.model_anthropic_adapter import AnthropicModelAdapter
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import (
    Prompt,
    SchemaViolation,
    Tier,
)
from nm.shared.model_replay import RecordingModel

pytestmark = pytest.mark.class_a

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "state"],
                "properties": {
                    "id": {"type": "string"},
                    "state": {"type": "string", "enum": ["supported", "uncertain"]},
                },
            },
        },
    },
}
MIXED = {"items": [{"id": "one", "state": "supported"}, {"id": "two", "state": "foreign"}]}
PROMPT = Prompt("Read the complete supplied account.", operation="quarantine_test")
VERSIONS = {"principles": "checked-v1", "tools": "typed-v1", "sources": "original-v1"}


def config(provider):
    return ModelConfig({
        tier: TierConfig(tier, provider, model, "offline", None)
        for tier, model in (
            (Tier.ROUTINE, "gpt-4.1-mini-2025-04-14"),
            (Tier.JUDGE, "gpt-5.1-2025-11-13"),
        )
    })


def adapter(provider, *, data=None, raw=None, finish=None, blocks=None, extra_choices=0,
            tool_calls=(), refusal=None):
    payload = copy.deepcopy(MIXED if data is None else data)
    calls = []
    if provider == "openai":
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason=finish or "stop",
                message=SimpleNamespace(
                    content=json.dumps(payload) if raw is None else raw,
                    tool_calls=tool_calls, refusal=refusal,
                ),
            )],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=12),
        )
        response.choices += copy.deepcopy(response.choices) * extra_choices

        def create(**kwargs):
            calls.append(kwargs)
            return response

        model = OpenAIModelAdapter(
            config(provider), client=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            ),
        )
    else:
        response = SimpleNamespace(
            stop_reason=finish or "tool_use",
            content=blocks if blocks is not None else [SimpleNamespace(
                type="tool_use", id="result-1", name="nm_result", input=payload,
            )],
            usage=SimpleNamespace(input_tokens=20, output_tokens=12),
        )

        def create(**kwargs):
            calls.append(kwargs)
            return response

        model = AnthropicModelAdapter(
            config(provider), client=SimpleNamespace(messages=SimpleNamespace(create=create)),
        )
    return model, calls, response


def recorded_failure():
    inner, calls, _ = adapter("openai")
    recorder = RecordingModel(inner, versions=VERSIONS)
    with pytest.raises(SchemaViolation) as caught:
        recorder.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=512)
    return recorder, caught.value, calls

