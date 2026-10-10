"""The OpenAI adapter.

It translates the port's vocabulary into this provider's. Nothing above it
knows that `system` becomes a message role, that structured output uses
`response_format`, or that rate limits arrive as a 429 -- which is the whole
point: that knowledge lives here and nowhere else.

The `openai` package is imported LAZILY, inside the constructor. Importing it
at module scope would make `nm.adapters.model` unimportable without the extra
installed, and the scripted adapter -- which every class-A test depends on --
lives in the same package.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any
from types import SimpleNamespace

from nm.shared.budget_contracts import Completion
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_budget import guard_budget, guard_tool_budget
from nm.shared.model_call_budget import CallBudget, SessionCallBudget
from nm.shared.model_config import (
    CONTEXT_BUDGET,
    ModelConfig,
    TierConfig,
    require_priced_snapshot,
    token_pricing,
)
from nm.shared.model_port import (
    ConfigurationError,
    ContentRefused,
    EmbeddingResult,
    ModelError,
    ModelResult,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolMessage,
    Usage,
    on_the_wire,
    require_schema,
    require_tool_calls,
)
from nm.shared.model_transport import normalise_error, request_with_retries
from nm.shared.text_contracts import blank

#: HOW A PROVIDER SAYS IT STOPPED, mapped to what that means for legal work.
#:
#: ONE TABLE RATHER THAN A COMPARISON AT EACH CALL SITE. The reason the length
#: stop went unnoticed for as long as it did is that exactly one reason was
#: ever compared, in one place, and nothing enumerated the rest.
#:
#: AN UNRECOGNISED REASON IS NOT ESTABLISHED, never complete. A provider that
#: adds a stop reason tomorrow must not have it read as "finished" by a table
#: written today.
# These checked releases use Responses for exact input accounting and explicit
# reasoning settings. Other model transports retain their existing contract.
_RESPONSES_EFFORT = {"gpt-6-luna": "none", "gpt-6.1-sol": "low"}

_FINISH_REASONS: dict[str, Completion] = {
    "stop": Completion.COMPLETE,
    "end_turn": Completion.COMPLETE,
    "length": Completion.LENGTH_LIMITED,
    "max_tokens": Completion.LENGTH_LIMITED,
    "content_filter": Completion.FILTERED,
}


def _completion_of(reason) -> Completion:
    if reason is None:
        return Completion.NOT_ESTABLISHED
    return _FINISH_REASONS.get(str(reason).strip().lower(),
                               Completion.NOT_ESTABLISHED)


def _json_object(pairs):
    """Preserve identical duplicate metadata; reject conflicting object keys."""
    result = {}
    for key, value in pairs:
        if key in result and json.dumps(result[key], sort_keys=True) != json.dumps(
                value, sort_keys=True):
            raise ValueError("response JSON repeated a conflicting object key")
        result[key] = value
    return result


def _invalid_json_constant(value):
    raise ValueError(f"response JSON used a non-finite numeric constant: {value}")


class OpenAIModelAdapter:
    def __init__(self, config: ModelConfig, client: Any | None = None,
                 call_budget: CallBudget | SessionCallBudget | None = None) -> None:
        self._config = config
        self._call_budget = call_budget
        self._before_dispatch: Callable[[], None] | None = None
        if client is not None:
            self._client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise ConfigurationError(
                "the openai package is not installed. `pip install -e .[openai]`"
            ) from exc
        cfg = config.for_tier(Tier.ROUTINE)
        if blank(cfg.api_key):
            raise ConfigurationError(
                "NM_MODEL_API_KEY is not set (or is still the placeholder). "
                "An unconfigured key is a hard failure, never a silent no-op."
            )
        import httpx
        # On Windows, the system's trusted roots may include the organisation's
        # HTTPS inspection CA. Keep certificate and hostname verification on;
        # certifi alone can reject an otherwise trusted endpoint on this host.
        verify: bool | ssl.SSLContext = True
        if sys.platform == "win32":
            try:
                import truststore
            except ImportError as exc:
                raise ConfigurationError(
                    "Windows HTTPS trust requires the truststore package") from exc
            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # The approved recipient must not redirect text/credentials elsewhere.
        # Disable implicit environment proxies as well as transport redirects.
        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key, "max_retries": 0,
            "http_client": httpx.Client(
                follow_redirects=False, trust_env=False, verify=verify),
            "base_url": cfg.base_url or "https://api.openai.com/v1",
        }
        self._client = OpenAI(**kwargs)

    def for_matter_text(self, before_dispatch: Callable[[], None]) -> OpenAIModelAdapter:
        """Request-bound authority, shared transport; no shared consent state."""
        bound = OpenAIModelAdapter(self._config, client=self._client, call_budget=self._call_budget)
        bound._before_dispatch = before_dispatch
        return bound

    def with_call_budget(self, budget: CallBudget | SessionCallBudget) -> OpenAIModelAdapter:
        bound = OpenAIModelAdapter(self._config, client=self._client, call_budget=budget)
        bound._before_dispatch = self._before_dispatch
        return bound

    # ------------------------------------------------------------- port ---
    @property
    def provider(self) -> str:
        return "openai"

    def resolved_model(self, tier: Tier) -> str:
        return self._cfg(tier).model

    def context_budget(self, tier: Tier) -> int:
        return CONTEXT_BUDGET[tier]

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        return self._call(prompt, tier, schema=None, max_tokens=max_tokens)

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        return self._call(prompt, tier, schema=schema, max_tokens=max_tokens)

    def tool_call(self, prompt: Prompt, tools: tuple[ToolDefinition, ...], tier: Tier, *,
                  messages: tuple[ToolMessage, ...] = (),
                  max_tokens: int | None = None) -> ToolCallResult:
        guard_tool_budget(prompt, tools, tier, messages, max_tokens)
        cfg = self._cfg(tier)
        if cfg.model == "gpt-6.1-sol":
            raise ConfigurationError("This model does not support Chat Completions tool calling")
        request_budget, max_tokens = self._budget_for(cfg.model, max_tokens)
        started = time.perf_counter()
        wire = []
        if prompt.system:
            wire.append({"role": "system", "content": prompt.system})
        wire.append({"role": "user", "content": prompt.user})
        for message in messages:
            row: dict[str, Any] = {"role": message.role, "content": message.text}
            if message.calls:
                row["tool_calls"] = [{"id": call.call_id, "type": "function",
                                      "function": {"name": call.name,
                                                   "arguments": json.dumps(call.arguments,
                                                                           allow_nan=False)}}
                                     for call in message.calls]
            if message.role == "tool":
                row["tool_call_id"] = message.call_id
            wire.append(row)
        kwargs = {"model": cfg.model, "messages": wire, "store": False,
                  "tools": [{"type": "function", "function": {
                      "name": tool.name, "description": tool.description,
                      "parameters": on_the_wire(tool.parameters), "strict": True}}
                      for tool in tools],
                  # This port requests a typed next action, not optional prose.
                  # The returned receipt is still checked independently below.
                  "tool_choice": "required", "parallel_tool_calls": False}
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if cfg.model == "gpt-6-luna":
            kwargs["reasoning_effort"] = "none"
        response, retries = self._retrying_counted(
            lambda: self._client.chat.completions.create(**kwargs), model=cfg.model,
            call_budget=request_budget)
        usage = self._usage(response, cfg)
        elapsed = int((time.perf_counter() - started) * 1000)
        try:
            if not getattr(response, "choices", None):
                raise SchemaViolation("The provider returned no tool response choice")
            choice = response.choices[0]
            reason = getattr(choice, "finish_reason", None)
            completion = self._require_tool_completion(reason)
            if getattr(choice.message, "refusal", None):
                raise ContentRefused("The provider refused this tool proposal")
            calls = []
            for call in getattr(choice.message, "tool_calls", None) or ():
                if getattr(call, "type", None) != "function":
                    raise SchemaViolation("The provider returned an unsupported tool kind")
                try:
                    arguments = json.loads(call.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise SchemaViolation("Tool arguments were not valid JSON") from exc
                calls.append(ToolCall(call.id, call.function.name, arguments))
            if reason == "tool_calls" and not calls:
                raise SchemaViolation("The provider declared calls but supplied none")
            if calls and reason != "tool_calls":
                raise SchemaViolation("Tool proposals lack the provider's completed-call receipt")
            require_tool_calls(tuple(calls), tools, messages)
            return ToolCallResult(
                text=getattr(choice.message, "content", None), calls=tuple(calls),
                tier=tier, provider=self.provider, model=cfg.model, usage=usage,
                latency_ms=elapsed, retries=retries, completion=completion)
        except ModelError as exc:
            exc.usage, exc.latency_ms, exc.retries = usage, elapsed, retries
            raise

    @staticmethod
    def _require_tool_completion(reason) -> Completion:
        if reason in {"stop", "tool_calls"}:
            return Completion.COMPLETE
        if reason == "length":
            raise OutputTruncated("Tool proposal stopped at the output ceiling")
        if reason == "content_filter":
            raise ContentRefused("The provider refused this tool proposal")
        raise SchemaViolation("The provider did not establish a completed tool proposal")

    @staticmethod
    def _usage(response, cfg: TierConfig) -> Usage:
        usage = getattr(response, "usage", None)
        incoming = getattr(usage, "prompt_tokens", None)
        outgoing = getattr(usage, "completion_tokens", None)
        if any(type(value) is not int or value < 0 for value in (incoming, outgoing)):
            raise ProviderUnavailable(
                "The provider did not establish request usage; cost is unknown")
        details = getattr(usage, "prompt_tokens_details", None)
        pricing = token_pricing(cfg.model)
        write_priced = pricing.write_rate is not None
        cached = getattr(details, "cached_tokens", None if write_priced else 0)
        written = getattr(details, "cache_write_tokens", None if write_priced else 0)
        if (type(cached) is not int or type(written) is not int
                or min(cached, written) < 0 or cached + written > incoming
                or (written and not write_priced)):
            # New write-priced models cannot establish actual spend without
            # both disjoint counters. The durable ledger keeps its reservation.
            if write_priced or written:
                raise ProviderUnavailable(
                    "The provider did not establish cache read/write usage; cost is unknown")
            raise ProviderUnavailable(
                "The provider returned invalid cached-token accounting",
                usage=Usage(incoming, outgoing, cfg.cost(incoming, outgoing),
                            provider_extra={"response_id": str(getattr(response, "id", "")),
                                            "cache_accounting_invalid": True}))
        return Usage(incoming, outgoing,
                     cfg.cost(incoming, outgoing, cached_tokens=cached,
                              cache_write_tokens=written), cached,
                     {"response_id": str(getattr(response, "id", "")),
                      "cache_write_tokens": written, "usage_established": True})

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        if self._before_dispatch is not None or self._call_budget is not None:
            raise ModelPermissionRefused("Matter-text permission does not enable embeddings.")
        cfg = self._cfg(Tier.EMBED)
        resp = self._retrying(lambda: self._client.embeddings.create(
            model=cfg.model, input=list(texts)))
        vectors = tuple(tuple(d.embedding) for d in resp.data)
        t_in = getattr(getattr(resp, "usage", None), "prompt_tokens", None)
        if type(t_in) is not int or t_in < 0:
            raise ProviderUnavailable("The provider did not establish embedding usage")
        return EmbeddingResult(
            vectors=vectors, model=cfg.model, provider=self.provider,
            usage=Usage(tokens_in=t_in, tokens_out=0, cost_usd=cfg.cost(t_in, 0)),
        )

    # -------------------------------------------------------- internals ---
    def _cfg(self, tier: Tier) -> TierConfig:
        return require_priced_snapshot(self._config.for_tier(tier), provider=self.provider)

    def _call(self, prompt: Prompt, tier: Tier, schema, max_tokens) -> ModelResult:
        if self._before_dispatch is not None and (
                (prompt.system is not None and not isinstance(prompt.system, str))
                or not isinstance(prompt.user, str)):
            raise ModelPermissionRefused("Only text is permitted; raw media cannot be sent.")
        cfg = self._cfg(tier)
        # The port's budget, enforced BEFORE the call and identically to every
        # other adapter. Relying on the provider to report overflow would make
        # the budget a provider concept and let a prompt that does not port
        # pass locally.
        guard_budget(prompt, tier)
        request_budget = None
        if cfg.model not in _RESPONSES_EFFORT:
            request_budget, max_tokens = self._budget_for(cfg.model, max_tokens)
        started = time.perf_counter()

        messages = []
        if prompt.system:
            # The cacheable prefix. This provider caches long stable prefixes
            # automatically, so the port's contract is honoured by keeping the
            # system message first and stable rather than by an explicit flag.
            messages.append({"role": "system", "content": prompt.system})
        messages.append({"role": "user", "content": prompt.user})

        kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages, "store": False}
        if max_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                # STRICT. The provider compiles the schema into a grammar and
                # MASKS any token that would break it, so an enum violation
                # becomes unemittable rather than caught afterwards — a role
                # read declaring eleven permitted values returned "claimant"
                # and it reached the core.
                #
                # `require_schema` in the port STAYS. One mechanism at the
                # wire and one at the boundary is not duplication here: the
                # scripted adapter has no grammar, and a second provider might
                # treat `strict` as advisory. The port's check is the one that
                # applies to every adapter.
                "json_schema": {"name": "nm_result", "strict": True,
                                # OUR METADATA NEVER GOES OVER THE WIRE.
                                # See `nm.shared.model_port.on_the_wire`.
                                "schema": on_the_wire(schema)},
            }

        if cfg.model in _RESPONSES_EFFORT:
            resp, retries = self._responses_request(messages, cfg, schema, max_tokens)
        else:
            resp, retries = self._retrying_counted(
                lambda: self._client.chat.completions.create(**kwargs), model=cfg.model,
                call_budget=request_budget)

        receipt = self._usage(resp, cfg)

        def fail(error):
            error.usage = receipt
            error.latency_ms = int((time.perf_counter() - started) * 1000)
            error.retries = retries
            return error

        response_error = getattr(resp, "normalization_error", None)
        if response_error is not None:
            raise fail(response_error)
        choice = resp.choices[0]
        completion = _completion_of(getattr(choice, "finish_reason", None))
        if completion is Completion.FILTERED:
            raise fail(ContentRefused(
                "the provider refused on content grounds. This is a provider "
                "behaviour, not a fact about the matter."))
        # THE LENGTH STOP WAS NOT CHECKED AT ALL. BK-49-AC1.
        #
        # `content_filter` was, and `length` was not -- so a response cut off
        # at the token limit came back as an ordinary answer. With a text read
        # it ends mid-sentence; with a structured read the JSON can still
        # close its braces and pass `require_schema`, and what is missing left
        # no trace for any downstream check to find.
        #
        # It is RAISED rather than returned because this method's contract is
        # a complete result. `ModelResult.completion` carries the same fact on
        # every other path, so a caller that wants whatever arrived can see it
        # without this method pretending the answer finished.
        if completion is Completion.LENGTH_LIMITED:
            raise fail(OutputTruncated(
                "the provider stopped at the output limit, so this answer "
                "ends where the budget did rather than where the reasoning "
                "did. It is unfinished, not short."))
        raw = choice.message.content or ""

        data = None
        text: str | None = raw
        if schema is not None:
            try:
                data = json.loads(
                    raw, object_pairs_hook=_json_object,
                    parse_constant=_invalid_json_constant,
                )
            except (TypeError, ValueError) as exc:
                raise fail(SchemaViolation(f"response was not valid JSON: {exc}")) from exc
            # THE DECLARED SCHEMA IS ENFORCED HERE, not by the provider.
            # Provider strict output is defence in depth, not a substitute
            # for validating the actual returned bytes. The port owns this
            # check so every adapter applies the same contract.
            try:
                # A quote-bearing enum is open only on the provider wire because
                # that grammar cannot compile it. The returned value still has
                # to meet the original closed contract here, for every read.
                require_schema(data, schema)
            except SchemaViolation as exc:
                # This remains a failed structured call. Complete, uniquely
                # decoded object bytes are available only to an independently
                # checking owner, never as an accepted provider result.
                if (completion is Completion.COMPLETE and isinstance(data, dict)
                        and len(resp.choices) == 1
                        and not getattr(choice.message, "tool_calls", None)
                        and not getattr(choice.message, "refusal", None)):
                    rejected = ModelResult(
                        text=None, data=data, tier=tier, provider=self.provider,
                        model=cfg.model, usage=receipt,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        retries=retries, completion=completion,
                    )
                    raise SchemaViolation(str(exc), rejected_result=rejected) from exc
                fail(exc)
                raise
            text = None

        return ModelResult(
            text=text, data=data, tier=tier, provider=self.provider, model=cfg.model,
            usage=receipt,
            latency_ms=int((time.perf_counter() - started) * 1000),
            retries=retries,
            completion=completion,
        )

    @staticmethod
    def _responses_receipt(response):
        """Map provider-owned accounting only; output cannot affect settlement."""
        usage = getattr(response, "usage", None)
        return SimpleNamespace(
            id=getattr(response, "id", None), model=getattr(response, "model", None),
            usage=SimpleNamespace(
                prompt_tokens=getattr(usage, "input_tokens", None),
                completion_tokens=getattr(usage, "output_tokens", None),
                prompt_tokens_details=getattr(usage, "input_tokens_details", None)))

    @classmethod
    def _responses_as_chat(cls, response):
        """Retain the existing admission/quarantine boundary after settlement."""
        receipt = cls._responses_receipt(response)
        receipt.normalization_error = None
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete, "reason", None)
        finish = None
        text = ""
        refusal = None
        if status == "incomplete" and reason == "max_output_tokens":
            finish = "length"
        elif status == "incomplete" and reason == "content_filter":
            finish = "content_filter"
        elif status == "failed" or getattr(response, "error", None) is not None:
            receipt.normalization_error = ProviderUnavailable("The provider response failed")
        elif status != "completed" or incomplete is not None:
            receipt.normalization_error = SchemaViolation(
                "The provider did not establish a completed response")
        else:
            output = getattr(response, "output", None)
            messages = []
            if isinstance(output, list):
                messages = [item for item in output if getattr(item, "type", None) == "message"]
            if (not isinstance(output, list) or len(messages) != 1
                    or any(getattr(item, "type", None) not in {"message", "reasoning"}
                           for item in output)
                    or getattr(messages[0], "role", None) != "assistant"
                    or getattr(messages[0], "status", None) != "completed"):
                receipt.normalization_error = SchemaViolation(
                    "The provider response has an ambiguous or unsupported output shape")
            else:
                content = getattr(messages[0], "content", None)
                if (not isinstance(content, list) or not content
                        or any(getattr(part, "type", None) not in {"output_text", "refusal"}
                               for part in content)):
                    receipt.normalization_error = SchemaViolation(
                        "The provider response did not establish text output")
                elif any(getattr(part, "type", None) == "refusal" for part in content):
                    finish, refusal = "content_filter", "Provider refused the response"
                elif any(not isinstance(getattr(part, "text", None), str) for part in content):
                    receipt.normalization_error = SchemaViolation(
                        "The provider response text is malformed")
                else:
                    text = "".join(part.text for part in content)
                    finish = "stop"
        receipt.choices = [SimpleNamespace(
            finish_reason=finish,
            message=SimpleNamespace(content=text, refusal=refusal, tool_calls=None))]
        return receipt

    def _responses_request(self, messages, cfg, schema, max_tokens):
        kwargs = {"model": cfg.model, "input": messages, "store": False,
                  "reasoning": {"effort": _RESPONSES_EFFORT[cfg.model]},
                  "truncation": "disabled"}
        if schema is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "nm_result",
                                         "strict": True, "schema": on_the_wire(schema)}}
        request_budget = self._call_budget
        if isinstance(request_budget, SessionCallBudget):
            # This is a non-generative provider request, with the identical
            # model input/format. It transmits matter text, so permission is
            # checked before counting and again before every generation attempt.
            count_payload = {key: value for key, value in kwargs.items() if key != "store"}
            if self._before_dispatch is not None:
                self._before_dispatch()
            try:
                counted = self._client.responses.input_tokens.count(**count_payload)
            except Exception as exc:
                normalised = normalise_error(exc)
                if normalised is exc:
                    raise
                raise normalised from exc
            incoming = getattr(counted, "input_tokens", None)
            if (getattr(counted, "object", None) != "response.input_tokens"
                    or type(incoming) is not int or incoming <= 0):
                raise ProviderUnavailable("The provider did not establish input token count")
            request_budget, max_tokens = request_budget.for_request(
                cfg.model, max_tokens, input_upper_bound=incoming)
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        response, retries = self._retrying_counted(
            lambda: self._client.responses.create(**kwargs), model=cfg.model,
            call_budget=request_budget, ledger_response=self._responses_receipt)
        return self._responses_as_chat(response), retries

    def _retrying(self, fn):
        return self._retrying_counted(fn)[0]

    def _budget_for(self, model: str, max_tokens: int | None):
        if isinstance(self._call_budget, SessionCallBudget):
            return self._call_budget.for_request(model, max_tokens)
        return self._call_budget, max_tokens

    def _retrying_counted(self, fn, *, model: str = "", call_budget=None,
                          ledger_response=lambda response: response) -> tuple[Any, int]:
        """Bounded retry with backoff. Retries are COUNTED and returned --
        an invisible retry is an invisible cost."""
        return request_with_retries(fn, model=model, before_dispatch=self._before_dispatch,
                                    call_budget=call_budget if call_budget is not None
                                    else self._call_budget,
                                    ledger_response=ledger_response)
