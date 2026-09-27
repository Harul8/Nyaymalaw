"""Optional Messages API adapter; product vocabulary stays on the model port.

Only client tools are admitted. No hosted search, arbitrary execution, raw
media, implicit proxies or redirects are enabled by selecting this provider.
The egress wrapper must separately approve the destination before dispatch.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from nm.adapters.model._budget import guard_budget, guard_tool_budget
from nm.adapters.model._transport import request_with_retries
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, require_priced_snapshot
from nm.domain.budget import Completion
from nm.domain.external_ai import ModelPermissionRefused
from nm.ports.model import (
    ConfigurationError,
    ContentRefused,
    ModelError,
    ModelResult,
    OutputTruncated,
    Prompt,
    SchemaViolation,
    Tier,
    TierUnavailable,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolMessage,
    Usage,
    on_the_wire,
    require_schema,
    require_tool_calls,
)


class AnthropicModelAdapter:
    def __init__(self, config: ModelConfig, client=None, call_budget=None):
        self._config, self._call_budget = config, call_budget
        self._before_dispatch = None
        if client is not None:
            self._client = client
            return
        try:
            import httpx
            from anthropic import Anthropic
        except ImportError as exc:
            raise ConfigurationError("Install the optional anthropic adapter dependencies") from exc
        cfg = config.for_tier(Tier.ROUTINE)
        if not cfg.api_key or cfg.api_key == "sk-REPLACE-ME":
            raise ConfigurationError("The model API key is not configured")
        self._client = Anthropic(
            api_key=cfg.api_key,
            max_retries=0,
            base_url=cfg.base_url or "https://api.anthropic.com",
            http_client=httpx.Client(follow_redirects=False, trust_env=False),
        )

    @property
    def provider(self):
        return "anthropic"

    def resolved_model(self, tier):
        return self._config.for_tier(tier).model

    def context_budget(self, tier):
        return CONTEXT_BUDGET[tier]

    def for_matter_text(self, before_dispatch):
        bound = AnthropicModelAdapter(self._config, self._client, self._call_budget)
        bound._before_dispatch = before_dispatch
        return bound

    def with_call_budget(self, budget):
        bound = AnthropicModelAdapter(self._config, self._client, budget)
        bound._before_dispatch = self._before_dispatch
        return bound

    def embed(self, texts):
        if self._before_dispatch is not None or self._call_budget is not None:
            raise ModelPermissionRefused("Matter-text permission does not enable embeddings")
        raise TierUnavailable(
            "This provider has no native embedding endpoint; select an embedding adapter"
        )

    def complete(self, prompt, tier, *, max_tokens=None):
        guard_budget(prompt, tier)
        response, usage, retries, elapsed = self._request(prompt, tier, max_tokens=max_tokens)
        try:
            completion = self._completion(response, calls_expected=False)
            text = self._text(response)
            if not text.strip():
                raise SchemaViolation("The provider returned no text")
            return ModelResult(
                text,
                None,
                tier,
                self.provider,
                self.resolved_model(tier),
                usage,
                elapsed,
                retries=retries,
                completion=completion,
            )
        except ModelError as exc:
            exc.usage, exc.latency_ms, exc.retries = usage, elapsed, retries
            raise

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        guard_budget(prompt, tier)
        # Forced client tool, parsed and validated by the same port validator.
        # Old read schemas need not be strict-parameter schemas; false here
        # does not waive validation of any returned property.
        tool = {
            "name": "nm_result",
            "description": "Return the requested structured result",
            "input_schema": on_the_wire(schema),
        }
        response, usage, retries, elapsed = self._request(
            prompt,
            tier,
            tools=[tool],
            choice={"type": "tool", "name": "nm_result"},
            max_tokens=max_tokens,
        )
        try:
            completion = self._completion(response, calls_expected=True)
            blocks = [b for b in response.content if b.type == "tool_use"]
            if len(blocks) != 1 or blocks[0].name != "nm_result":
                raise SchemaViolation("The provider did not return the requested structured read")
            data = blocks[0].input
            require_schema(data, schema)
            return ModelResult(
                None,
                data,
                tier,
                self.provider,
                self.resolved_model(tier),
                usage,
                elapsed,
                retries=retries,
                completion=completion,
            )
        except ModelError as exc:
            exc.usage, exc.latency_ms, exc.retries = usage, elapsed, retries
            raise

    def tool_call(
        self,
        prompt: Prompt,
        tools: tuple[ToolDefinition, ...],
        tier: Tier,
        *,
        messages: tuple[ToolMessage, ...] = (),
        max_tokens=None,
    ) -> ToolCallResult:
        guard_tool_budget(prompt, tools, tier, messages, max_tokens)
        wire = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": on_the_wire(t.parameters),
                "strict": True,
            }
            for t in tools
        ]
        response, usage, retries, elapsed = self._request(
            prompt,
            tier,
            tools=wire,
            messages=messages,
            # Require one typed action, without deciding which action to take.
            # Unsupported snapshots must refuse, not silently relax to auto.
            choice={"type": "any", "disable_parallel_tool_use": True},
            max_tokens=max_tokens,
        )
        try:
            blocks = response.content
            if any(b.type not in {"text", "tool_use"} for b in blocks):
                raise SchemaViolation("The provider returned an unsupported content block")
            calls = tuple(ToolCall(b.id, b.name, b.input) for b in blocks if b.type == "tool_use")
            completion = self._completion(response, calls_expected=bool(calls))
            require_tool_calls(calls, tools, messages)
            return ToolCallResult(
                self._text(response) or None,
                calls,
                tier,
                self.provider,
                self.resolved_model(tier),
                usage,
                elapsed,
                retries=retries,
                completion=completion,
            )
        except ModelError as exc:
            exc.usage, exc.latency_ms, exc.retries = usage, elapsed, retries
            raise

    @staticmethod
    def _text(response):
        return "\n".join(b.text for b in response.content if b.type == "text")

    @staticmethod
    def _completion(response, *, calls_expected):
        reason = getattr(response, "stop_reason", None)
        if reason == "max_tokens":
            raise OutputTruncated("Tool/model output stopped at the output ceiling")
        if reason == "refusal":
            raise ContentRefused("The provider refused this request")
        expected = "tool_use" if calls_expected else "end_turn"
        if reason != expected:
            raise SchemaViolation("The provider did not establish the requested completion")
        return Completion.COMPLETE

    def _request(self, prompt, tier, *, tools=None, messages=(), choice=None, max_tokens=None):
        cfg = require_priced_snapshot(self._config.for_tier(tier), provider=self.provider)
        if not isinstance(prompt.user, str) or (
            prompt.system is not None and not isinstance(prompt.system, str)
        ):
            raise ModelPermissionRefused("Only text may be sent to this model route")
        if max_tokens is not None and (type(max_tokens) is not int or max_tokens <= 0):
            raise ValueError("Output ceiling must be positive")
        wire = [{"role": "user", "content": prompt.user}]
        for message in messages:
            if message.role == "tool":
                row = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.call_id,
                            "content": message.text,
                        }
                    ],
                }
            else:
                content = [{"type": "text", "text": message.text}] if message.text else []
                content += [
                    {
                        "type": "tool_use",
                        "id": c.call_id,
                        "name": c.name,
                        "input": dict(c.arguments),
                    }
                    for c in message.calls
                ]
                row = {"role": message.role, "content": content}
            # Multiple results belong to one Messages user turn.
            if (
                message.role == "tool"
                and wire[-1]["role"] == "user"
                and isinstance(wire[-1]["content"], list)
            ):
                wire[-1]["content"] += row["content"]
            else:
                wire.append(row)
        kwargs = {"model": cfg.model, "messages": wire, "max_tokens": max_tokens or 4096}
        if prompt.system:
            kwargs["system"] = [
                {"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}
            ]
        if tools is not None:
            kwargs["tools"], kwargs["tool_choice"] = tools, choice
        started = time.perf_counter()

        def ledger_response(response):
            usage = getattr(response, "usage", None)
            incoming = getattr(usage, "input_tokens", None)
            cached = getattr(usage, "cache_read_input_tokens", 0)
            creation = getattr(usage, "cache_creation_input_tokens", 0)
            total = (incoming + cached + 2 * creation
                     if all(type(value) is int and value >= 0
                            for value in (incoming, cached, creation)) else None)
            return SimpleNamespace(
                id=getattr(response, "id", ""),
                model=getattr(response, "model", cfg.model),
                usage=SimpleNamespace(
                    prompt_tokens=total,
                    completion_tokens=getattr(usage, "output_tokens", None),
                ),
            )

        response, retries = request_with_retries(
            lambda: self._client.messages.create(**kwargs),
            model=cfg.model,
            before_dispatch=self._before_dispatch,
            call_budget=self._call_budget,
            ledger_response=ledger_response,
        )
        native = getattr(response, "usage", None)
        incoming, outgoing = (
            getattr(native, "input_tokens", None),
            getattr(native, "output_tokens", None),
        )
        if any(type(v) is not int or v < 0 for v in (incoming, outgoing)):
            raise SchemaViolation("The provider did not establish request usage")
        cached = getattr(native, "cache_read_input_tokens", 0)
        creation = getattr(native, "cache_creation_input_tokens", 0)
        if any(type(value) is not int or value < 0 for value in (cached, creation)):
            raise SchemaViolation("The provider returned invalid cache accounting")
        # Conservative ordinary-input cost, including cache write/read tokens;
        # discounts are never guessed. Native totals stay on the receipt.
        total_in = incoming + cached + creation
        usage = Usage(
            total_in,
            outgoing,
            cfg.cost(incoming + cached + 2 * creation, outgoing),
            cached,
            {
                "response_id": str(getattr(response, "id", "")),
                "cache_creation_tokens": creation,
                "cost_basis": "ordinary-input-upper-bound",
            },
        )
        return response, usage, retries, int((time.perf_counter() - started) * 1000)
