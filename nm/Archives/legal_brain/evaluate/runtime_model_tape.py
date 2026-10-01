"""Finite actual ModelPort observations; no provider or executable loader.

These private rows have no persistence or authority of their own. The existing
protected runtime journal must seal them, and the actual loop/check owners must
consume their restored model values. They are never ToolEnvelopes or verdicts.
"""

from __future__ import annotations

from enum import Enum
from threading import Lock

from nm.Archives.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, closed
from nm.Archives.legal_brain.evaluate.runtime_port_tape import MAX_ROWS, _bounded, _typed
from nm.shared import model_port as port
from nm.shared.json_values import same_json_value
from nm.shared.store_file_store import _enc


class ModelRole(str, Enum):
    LEAD = "lead"
    VERIFIER = "verifier"
    CONTEXT = "context"
    RESEARCH = "research"


ERRORS = {
    kind.__name__: kind
    for kind in (
        port.ModelError,
        port.RateLimited,
        port.ProviderUnavailable,
        port.OutputTruncated,
        port.ContextOverflow,
        port.ContentRefused,
        port.SchemaViolation,
        port.TierUnavailable,
        port.ConfigurationError,
    )
}
OBSERVATIONS = {"provider", "resolved_model", "context_budget"}
DISPATCHES = {"tool_call", "structured", "complete"}


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ReplayCaptureRefused(label + " must be its actual nonempty identity")
    return value


def _count(value, label, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ReplayCaptureRefused(label + " must be an exact bounded integer")
    return value


def _exact_json(value):
    snapshot = _bounded(value)
    if not same_json_value(value, snapshot):
        raise ReplayCaptureRefused("Model JSON values cannot be coerced on capture")
    return snapshot


def _raw_json_fields(value):
    if type(value) is port.ToolDefinition:
        _exact_json(value.parameters)
    elif type(value) is port.ToolCall:
        _exact_json(value.arguments)
    elif type(value) is port.ToolMessage:
        for call in value.calls:
            _raw_json_fields(call)
    elif type(value) is port.Usage:
        _exact_json(value.provider_extra)
    elif type(value) in (port.ToolCallResult, port.ModelResult):
        _raw_json_fields(value.usage)
        if type(value) is port.ModelResult:
            _exact_json(value.data)
        else:
            for call in value.calls:
                _raw_json_fields(call)


def _tier(value, *, wire):
    tier = _typed(port.Tier, value, wire=wire)
    if tier is port.Tier.EMBED:
        raise ReplayCaptureRefused("Embedding dispatch is outside this runtime population")
    return tier


def _identity(value):
    closed(value, {"provider", "model", "context_budget"}, "model dispatch identity")
    _text(value["provider"], "provider")
    _text(value["model"], "resolved model")
    _count(value["context_budget"], "context budget", positive=True)


def encode_model_arguments(
    operation, *, prompt=None, tier=None, max_tokens=None, tools=(), messages=(), schema=None
):
    """Snapshot exact typed input, including owned schema metadata, not wire stripping."""
    if operation == "provider":
        return {}
    if operation in ("resolved_model", "context_budget"):
        return {"tier": _tier(tier, wire=False).value}
    if operation not in DISPATCHES:
        raise ReplayCaptureRefused("The model method is outside the finite owned population")
    prompt = _typed(port.Prompt, prompt, wire=False)
    tier = _tier(tier, wire=False)
    if max_tokens is not None:
        _count(max_tokens, "token grant", positive=True)
    value = {"prompt": _enc(prompt), "tier": tier.value, "max_tokens": max_tokens}
    if operation == "tool_call":
        for row in (*tools, *messages):
            _raw_json_fields(row)
        tools = _typed(tuple[port.ToolDefinition, ...], tools, wire=False)
        messages = _typed(tuple[port.ToolMessage, ...], messages, wire=False)
        port.require_tool_request(tools, messages)
        value.update(tools=_enc(tools), messages=_enc(messages))
    elif operation == "structured":
        if type(schema) is not dict:
            raise ReplayCaptureRefused("The structured request needs its actual schema object")
        value["schema"] = _exact_json(schema)
    return _bounded(value)


def _arguments(operation, value):
    if operation == "provider":
        closed(value, set(), "provider observation arguments")
        return
    if operation in ("resolved_model", "context_budget"):
        closed(value, {"tier"}, "model identity observation arguments")
        _tier(value["tier"], wire=True)
        return
    names = {"prompt", "tier", "max_tokens"}
    names |= (
        {"tools", "messages"}
        if operation == "tool_call"
        else ({"schema"} if operation == "structured" else set())
    )
    closed(value, names, "model dispatch arguments")
    prompt = _typed(port.Prompt, value["prompt"], wire=True)
    tier = _tier(value["tier"], wire=True)
    extra = {}
    if operation == "tool_call":
        extra = {
            "tools": _typed(tuple[port.ToolDefinition, ...], value["tools"], wire=True),
            "messages": _typed(tuple[port.ToolMessage, ...], value["messages"], wire=True),
        }
    elif operation == "structured":
        extra = {"schema": value["schema"]}
    rebuilt = encode_model_arguments(
        operation, prompt=prompt, tier=tier, max_tokens=value["max_tokens"], **extra
    )
    if not same_json_value(rebuilt, value):
        raise ReplayCaptureRefused("The full model request changed on typed restoration")


def _result(operation, value, *, wire):
    if operation in ("provider", "resolved_model"):
        return _text(value, "model identity observation")
    if operation == "context_budget":
        return _count(value, "context budget observation", positive=True)
    kind = port.ToolCallResult if operation == "tool_call" else port.ModelResult
    if not wire:
        _raw_json_fields(value)
    result = _typed(kind, value, wire=wire)
    _text(result.provider, "result provider")
    _text(result.model, "result model")
    _count(result.latency_ms, "latency")
    _count(result.retries, "retries")
    # Completion, downgrade, raw output and paid usage are retained. This owner
    # must not turn partial/unknown output into an error or a checked success.
    return result


def encode_model_outcome(operation, *, result=None, error=None):
    if error is not None:
        if type(error).__name__ not in ERRORS or type(error) is not ERRORS[type(error).__name__]:
            raise ReplayCaptureRefused("An unnormalized model failure is not replay evidence")
        reason = str(error)
        if type(reason) is not str or len(reason) > 16000:
            raise ReplayCaptureRefused("The normalized failure exceeds its private bound")
        _count(error.latency_ms, "failure latency")
        _count(error.retries, "failure retries")
        if error.usage is not None:
            _raw_json_fields(error.usage)
        usage = None if error.usage is None else _enc(_typed(port.Usage, error.usage, wire=False))
        return _bounded(
            {
                "state": "refused",
                "exception": type(error).__name__,
                "reason": reason,
                "usage": usage,
                "latency_ms": error.latency_ms,
                "retries": error.retries,
            }
        )
    return _bounded({"state": "returned", "value": _enc(_result(operation, result, wire=False))})


def validate_model_exchange(row):
    """Closed shared decoder; typed value restoration is not saved legal review."""
    closed(
        row,
        {"schema", "sequence", "role", "operation", "arguments", "identity", "outcome"},
        "model exchange",
    )
    if type(row["schema"]) is not int or row["schema"] != 1:
        raise ReplayCaptureRefused("Unsupported model tape contract")
    _count(row["sequence"], "model sequence", positive=True)
    _typed(ModelRole, row["role"], wire=True)
    operation = row["operation"]
    if type(operation) is not str or operation not in OBSERVATIONS | DISPATCHES:
        raise ReplayCaptureRefused("Unknown model tape operation")
    _arguments(operation, row["arguments"])
    if operation in DISPATCHES:
        _identity(row["identity"])
    elif row["identity"] is not None:
        raise ReplayCaptureRefused("A metadata observation cannot invent a dispatch identity")
    outcome = row["outcome"]
    if type(outcome) is not dict:
        raise ReplayCaptureRefused("A model outcome must be explicitly typed")
    if outcome.get("state") == "returned":
        closed(outcome, {"state", "value"}, "returned model outcome")
        result = _result(operation, outcome["value"], wire=True)
        if not same_json_value(_enc(result), outcome["value"]):
            raise ReplayCaptureRefused("Model output changed on typed restoration")
    elif outcome.get("state") == "refused":
        closed(
            outcome,
            {"state", "exception", "reason", "usage", "latency_ms", "retries"},
            "refused model outcome",
        )
        if type(outcome["exception"]) is not str or outcome["exception"] not in ERRORS:
            raise ReplayCaptureRefused("Unknown normalized model refusal")
        if type(outcome["reason"]) is not str or len(outcome["reason"]) > 16000:
            raise ReplayCaptureRefused("The actual normalized refusal must be bounded")
        usage = (
            None if outcome["usage"] is None else _typed(port.Usage, outcome["usage"], wire=True)
        )
        _count(outcome["latency_ms"], "failure latency")
        _count(outcome["retries"], "failure retries")
        result = ERRORS[outcome["exception"]](
            outcome["reason"],
            usage=usage,
            latency_ms=outcome["latency_ms"],
            retries=outcome["retries"],
        )
    else:
        raise ReplayCaptureRefused("An absent model observation is not a returned result")
    _bounded(row)
    return result


class ModelTapeCapture:
    """Bootstrap-selected real ports only; no captured provider config or signing."""

    def __init__(self):
        self._rows = []
        self._failed = False
        self._dispatch_lock = Lock()
        self._dispatch_active = False

    @property
    def rows(self):
        if self._failed:
            raise ReplayCaptureRefused("An uncaptured model dispatch leaves this tape incomplete")
        return _bounded(self._rows)

    def wrap(self, role: ModelRole, actual: port.ModelPort):
        _typed(ModelRole, role, wire=False)
        return _ObservedModel(self, role, actual)

    def _room(self, arguments):
        if self._failed or len(self._rows) >= MAX_ROWS:
            raise ReplayCaptureRefused("The bounded model observation population is exhausted")
        _bounded([*self._rows, arguments])

    def observe(self, role, operation, arguments, invoke, identity=None):
        self._room(arguments)
        try:
            result = invoke()
        except port.ModelError as exc:
            try:
                self._append(
                    role, operation, arguments, identity, encode_model_outcome(operation, error=exc)
                )
            except Exception:
                self._failed = True
                # The actual consumer still owns this paid/unmeasured failure.
                # Do not replace its usage with an observer's decoding failure.
            raise
        except BaseException:
            self._failed = True
            raise
        try:
            self._append(
                role, operation, arguments, identity, encode_model_outcome(operation, result=result)
            )
        except Exception:
            self._failed = True
            # The actual model value and accounting still reach the loop/check
            # owner. Export refuses this incomplete tape; nothing is fabricated.
        return result

    def _append(self, role, operation, arguments, identity, outcome):
        row = {
            "schema": 1,
            "sequence": len(self._rows) + 1,
            "role": role.value,
            "operation": operation,
            "arguments": arguments,
            "identity": identity,
            "outcome": outcome,
        }
        validate_model_exchange(row)
        _bounded([*self._rows, row])
        self._rows.append(_bounded(row))


class ModelTapeReplay:
    """Only actual model methods; execution, budget and checking still run normally."""

    def __init__(self, rows):
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ReplayCaptureRefused("Model replay needs a finite observed population")
        self._rows, self.position = _bounded(rows), 0
        for index, row in enumerate(self._rows, 1):
            validate_model_exchange(row)
            if row["sequence"] != index:
                raise ReplayCaptureRefused("Model observations must be contiguous and ordered")
        observed = {}
        for row in self._rows:
            role, operation = row["role"], row["operation"]
            if operation in OBSERVATIONS and row["outcome"]["state"] == "returned":
                key = (role, operation, row["arguments"].get("tier"))
                observed[key] = row["outcome"]["value"]
            if operation in DISPATCHES:
                tier = row["arguments"]["tier"]
                actual = {
                    "provider": observed.get((role, "provider", None)),
                    "model": observed.get((role, "resolved_model", tier)),
                    "context_budget": observed.get((role, "context_budget", tier)),
                }
                if not same_json_value(actual, row["identity"]):
                    raise ReplayCaptureRefused(
                        "Dispatch identity lacks its actual metadata observations"
                    )

    def port(self, role: ModelRole):
        _typed(ModelRole, role, wire=False)
        return _FrozenModel(self, role)

    def consume(self, role, operation, arguments, identity=None):
        if self.position >= len(self._rows):
            raise ReplayCaptureRefused("Model tape exhausted at actual invocation")
        row = self._rows[self.position]
        if (
            row["role"] != role.value
            or row["operation"] != operation
            or not same_json_value(row["arguments"], arguments)
            or not same_json_value(row["identity"], identity)
        ):
            raise ReplayCaptureRefused("Actual model role/order/request/grant/identity differs")
        result = validate_model_exchange(row)
        self.position += 1
        if row["outcome"]["state"] == "refused":
            raise result
        return result

    def remaining(self):
        return len(self._rows) - self.position

    def assert_exhausted(self):
        if self.remaining():
            raise ReplayCaptureRefused("Unconsumed actual model observations remain")


class _ModelMethods:
    def _identity(self, tier):
        return {
            "provider": self.provider,
            "model": self.resolved_model(tier),
            "context_budget": self.context_budget(tier),
        }

    def tool_call(self, prompt, tools, tier, *, messages=(), max_tokens=None):
        arguments = encode_model_arguments(
            "tool_call",
            prompt=prompt,
            tools=tools,
            tier=tier,
            messages=messages,
            max_tokens=max_tokens,
        )
        return self._call(
            "tool_call",
            arguments,
            tier,
            (prompt, tools, tier),
            {"messages": messages, "max_tokens": max_tokens},
        )

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        arguments = encode_model_arguments(
            "structured", prompt=prompt, schema=schema, tier=tier, max_tokens=max_tokens
        )
        return self._call(
            "structured", arguments, tier, (prompt, schema, tier), {"max_tokens": max_tokens}
        )

    def complete(self, prompt, tier, *, max_tokens=None):
        arguments = encode_model_arguments(
            "complete", prompt=prompt, tier=tier, max_tokens=max_tokens
        )
        return self._call("complete", arguments, tier, (prompt, tier), {"max_tokens": max_tokens})

    def _call(self, operation, arguments, tier, args, kwargs):
        return self._dispatch(operation, arguments, self._identity(tier), args, kwargs)

    def embed(self, texts):
        raise ReplayCaptureRefused("Embedding observations are not populated by this contract")


class _ObservedModel(_ModelMethods):
    def __init__(self, tape, role, actual):
        self.tape, self.role, self.actual = tape, role, actual

    @property
    def provider(self):
        return self.tape.observe(self.role, "provider", {}, lambda: self.actual.provider)

    def resolved_model(self, tier):
        arguments = encode_model_arguments("resolved_model", tier=tier)
        return self.tape.observe(
            self.role, "resolved_model", arguments, lambda: self.actual.resolved_model(tier)
        )

    def context_budget(self, tier):
        arguments = encode_model_arguments("context_budget", tier=tier)
        return self.tape.observe(
            self.role, "context_budget", arguments, lambda: self.actual.context_budget(tier)
        )

    def _dispatch(self, operation, arguments, identity, args, kwargs):
        return self.tape.observe(
            self.role,
            operation,
            arguments,
            lambda: getattr(self.actual, operation)(*args, **kwargs),
            identity,
        )

    def _call(self, operation, arguments, tier, args, kwargs):
        # Reserve the finite population before the three internal identity reads
        # and the actual paid dispatch. A cap is not a recorded provider refusal.
        with self.tape._dispatch_lock:
            if self.tape._dispatch_active:
                self.tape._failed = True
                raise ReplayCaptureRefused("Overlapping model dispatch capture is not populated")
            if self.tape._failed or len(self.tape._rows) + 4 > MAX_ROWS:
                self.tape._failed = True
                raise ReplayCaptureRefused("The finite model dispatch population is exhausted")
            self.tape._dispatch_active = True
        try:
            return super()._call(operation, arguments, tier, args, kwargs)
        finally:
            with self.tape._dispatch_lock:
                self.tape._dispatch_active = False


class _FrozenModel(_ModelMethods):
    def __init__(self, tape, role):
        self.tape, self.role = tape, role

    @property
    def provider(self):
        return self.tape.consume(self.role, "provider", {})

    def resolved_model(self, tier):
        return self.tape.consume(
            self.role, "resolved_model", encode_model_arguments("resolved_model", tier=tier)
        )

    def context_budget(self, tier):
        return self.tape.consume(
            self.role, "context_budget", encode_model_arguments("context_budget", tier=tier)
        )

    def _dispatch(self, operation, arguments, identity, args, kwargs):
        return self.tape.consume(self.role, operation, arguments, identity)

    def _call(self, operation, arguments, tier, args, kwargs):
        # The wrapper's three admission observations and dispatch are one replay
        # invocation. A wrong request cannot partially consume those observations.
        position = self.tape.position
        try:
            return super()._call(operation, arguments, tier, args, kwargs)
        except ReplayCaptureRefused:
            self.tape.position = position
            raise
