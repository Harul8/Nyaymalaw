"""Exact model-call recording and offline replay, never a live-quality claim.

Records contain matter text. The caller persists them only through its existing
encrypted matter journal; this module never writes an unencrypted second store.
Request identity includes principle/tool versions, full prompt and conversation,
schema/tool inventory, tier and output ceiling. Mismatch never consumes a record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from nm.adapters.model._budget import guard_budget, guard_tool_budget
from nm.adapters.model.config import CONTEXT_BUDGET
from nm.core.tool_offers import OfferRefused, ToolOfferState
from nm.core.tools import Assessment, Availability, Effect, ToolEnvelope, ToolKind, ToolOutcome
from nm.domain.budget import Completion
from nm.domain.loop import LoopRecord, StepKind
from nm.ports import model as port


def _identity(
    kind,
    *,
    versions,
    prompt=None,
    schema=None,
    tools=(),
    messages=(),
    texts=(),
    tier=None,
    max_tokens=None,
):
    if not versions or any(not str(k).strip() or not str(v).strip() for k, v in versions.items()):
        raise ValueError("A recording needs nonempty principle/tool/source versions")
    payload = {
        "kind": kind,
        "versions": dict(versions),
        "tier": tier.value if tier else None,
        "max_tokens": max_tokens,
        "texts": texts,
        "schema": schema,
        "request": json.loads(port.tool_request_text(prompt, tools, messages))
        if prompt is not None
        else None,
    }
    raw = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf8")).hexdigest()


def _encode(result):
    return {"kind": type(result).__name__, "value": asdict(result)}


def _record_digest(row):
    raw = json.dumps(
        {key: value for key, value in row.items() if key != "record_digest"},
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf8")).hexdigest()


def _decode(record):
    data = dict(record["value"])
    data["usage"] = port.Usage(**data["usage"])
    kind = record["kind"]
    if kind == "EmbeddingResult":
        data["vectors"] = tuple(tuple(v) for v in data["vectors"])
        return port.EmbeddingResult(**data)
    data["tier"] = port.Tier(data["tier"])
    data["completion"] = Completion(data["completion"])
    if kind == "ToolCallResult":
        data["calls"] = tuple(port.ToolCall(**c) for c in data["calls"])
        return port.ToolCallResult(**data)
    if kind == "ModelResult":
        if data.get("downgraded_from"):
            data["downgraded_from"] = port.Tier(data["downgraded_from"])
        return port.ModelResult(**data)
    raise ValueError("Unknown recorded model result type")


def _messages_from_wire(rows):
    return tuple(
        port.ToolMessage(**{**row, "calls": tuple(port.ToolCall(**call) for call in row["calls"])})
        for row in rows
    )


def _known_error(error):
    if set(error) != {"kind", "message", "usage", "latency_ms", "retries"}:
        raise port.SchemaViolation("A saved model failure is not a complete error receipt")
    if error["kind"] not in _ERRORS:
        raise port.SchemaViolation("A saved failure has no normalized model-error type")
    if not isinstance(error["message"], str) or not error["message"].strip():
        raise port.SchemaViolation("A saved failure has no reason")
    if any(type(error[key]) is not int or error[key] < 0 for key in ("latency_ms", "retries")):
        raise port.SchemaViolation("A saved failure has invalid latency or retry accounting")
    if error["usage"] is not None:
        _usage_from_wire(error["usage"])


def _usage_from_wire(row):
    usage = port.Usage(**row)
    import math

    if (
        any(
            type(value) is not int or value < 0
            for value in (usage.tokens_in, usage.tokens_out, usage.cached_tokens)
        )
        or not math.isfinite(usage.cost_usd)
        or usage.cost_usd < 0
    ):
        raise port.SchemaViolation("A saved model call has invalid usage accounting")
    return usage


def records_from_loop(record: LoopRecord, tools, *, versions=None):
    """Import the actual sealed call journal, using the adapter's request identity.

    Incomplete dispatches cannot be replayed as successes or attempted again.
    This importer only interprets already captured model calls; it does not
    execute tool events and makes no claim about live provider quality.
    """
    if not isinstance(record, LoopRecord) or not record.terminal:
        raise port.SchemaViolation("Replay requires a closed typed loop journal")
    # Recheck every captured event as well as chain continuity at this boundary.
    # Frozen records can still have been assembled by a caller with object hooks.
    for event in record.events:
        event.__post_init__()
    record.__post_init__()
    recorded_versions = {
        "principles": record.identity.principles_version,
        "tools": record.identity.tools_version,
        "matter": str(record.identity.matter_version),
    }
    if versions is not None and dict(versions) != recorded_versions:
        raise port.SchemaViolation(
            "Current principles, tools/sources or matter differ from the journal"
        )
    captured_tools = record.events[0].payload.get("tools")
    if captured_tools != json.loads(json.dumps([asdict(tool) for tool in tools])):
        raise port.SchemaViolation("Replay tool definitions differ from the captured registry")
    inventory = tuple(sorted(tools, key=lambda row: row.name))
    offer_record = record.events[0].payload.get("tool_offer")
    try:
        state = (ToolOfferState.from_record(offer_record, inventory) if offer_record else
                 ToolOfferState(inventory, record.identity.tools_version,
                                tuple(row.name for row in inventory)))
        if state.registry_version != record.identity.tools_version:
            raise OfferRefused("The saved schema offer names another registered version.")
    except (TypeError, ValueError) as exc:
        raise port.SchemaViolation("The saved schema offer cannot be verified") from exc
    rows, pending, pending_tools, active_calls = [], None, tools, {}
    try:
        for event in record.events:
            payload = event.payload
            if event.kind is StepKind.MODEL_STARTED:
                if pending is not None:
                    raise port.SchemaViolation("A saved model dispatch has no completion receipt")
                prompt = port.Prompt(**payload["prompt"])
                messages = _messages_from_wire(payload["messages"])
                tier = port.Tier(payload["tier"])
                if "tools" in payload:
                    pending_tools = tuple(port.ToolDefinition(**row) for row in payload["tools"])
                    state.require_offer(pending_tools)
                elif offer_record:
                    raise port.SchemaViolation("A saved dispatch omitted its exact offered schemas")
                else:
                    pending_tools = tools  # A legacy eager dispatch, not lazy-loading evidence.
                port.require_tool_request(pending_tools, messages)
                ceiling = payload["max_tokens"]
                if type(ceiling) is not int or ceiling <= 0:
                    raise port.SchemaViolation("A saved model call has no positive output ceiling")
                pending = {
                    "schema": 1,
                    "fingerprint": _identity(
                        "tool_call",
                        versions=recorded_versions,
                        prompt=prompt,
                        tools=pending_tools,
                        messages=messages,
                        tier=tier,
                        max_tokens=ceiling,
                    ),
                    "versions": dict(recorded_versions),
                    "operation": "tool_call",
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                }
            elif event.kind is StepKind.MODEL_RETURNED:
                if pending is None:
                    raise port.SchemaViolation("A saved model result has no dispatch record")
                result = _decode(payload["result"])
                if not isinstance(result, port.ToolCallResult):
                    raise port.SchemaViolation(
                        "The loop did not capture a neutral tool-call result"
                    )
                _usage_from_wire(payload["result"]["value"]["usage"])
                if any(
                    type(value) is not int or value < 0
                    for value in (result.latency_ms, result.retries)
                ):
                    raise port.SchemaViolation("A saved model result has invalid accounting")
                if result.tier is not tier:
                    raise port.SchemaViolation("The saved result changed the requested tier")
                port.require_tool_calls(result.calls, pending_tools, messages)
                if (
                    payload["text"],
                    payload["calls"],
                    payload["model"],
                    payload["provider"],
                    payload["completion"],
                ) != (
                    result.text,
                    json.loads(json.dumps([asdict(call) for call in result.calls])),
                    result.model,
                    result.provider,
                    result.completion.value,
                ):
                    raise port.SchemaViolation(
                        "The journal's result and accounting receipt disagree"
                    )
                if pending["provider"] is not None and (pending["provider"], pending["model"]) != (
                    result.provider,
                    result.model,
                ):
                    raise port.SchemaViolation("A result changed the admitted provider or model")
                pending.update(
                    provider=result.provider, model=result.model, result=payload["result"]
                )
                _append_imported(rows, pending)
                pending = None
            elif event.kind is StepKind.TOOL_STARTED:
                call = port.ToolCall(**payload["call"])
                if call.call_id in active_calls:
                    raise port.SchemaViolation("A saved tool invocation reused its identity")
                active_calls[call.call_id] = call
            elif event.kind is StepKind.TOOL_RETURNED:
                call = active_calls.pop(payload["call_id"], None)
                if call is None:
                    raise port.SchemaViolation("A saved receipt has no matching invocation")
                raw = payload["receipt"]
                receipt = ToolEnvelope(**{**raw, "kind": ToolKind(raw["kind"]),
                    "outcome": ToolOutcome(raw["outcome"]),
                    "availability": Availability(raw["availability"]),
                    "assessment": Assessment(raw["assessment"]), "effect": Effect(raw["effect"])})
                state = state.loaded_by(call, receipt)
            elif event.kind is StepKind.FAILURE and pending is not None:
                error = payload.get("error")
                if not isinstance(error, dict):
                    raise port.SchemaViolation(
                        "A saved model failure has no normalized error receipt"
                    )
                _known_error(error)
                if not all(
                    isinstance(pending[key], str) and pending[key].strip()
                    for key in ("provider", "model")
                ):
                    raise port.SchemaViolation(
                        "A failed call has no captured provider/model identity"
                    )
                pending["error"] = error
                _append_imported(rows, pending)
                pending = None
            elif pending is not None:
                raise port.SchemaViolation(
                    "A saved model dispatch ended without a result or error receipt"
                )
    except (KeyError, TypeError, ValueError, OfferRefused) as exc:
        raise port.SchemaViolation("The saved model journal is malformed") from exc
    if pending is not None or not rows:
        raise port.SchemaViolation("The loop has no complete replayable model-call population")
    return tuple(rows), recorded_versions


def _append_imported(rows, row):
    row["record_digest"] = _record_digest(row)
    rows.append(row)


_ERRORS = {
    name: value
    for name, value in vars(port).items()
    if isinstance(value, type) and issubclass(value, port.ModelError)
}


class RecordingModel:
    """Transparent port wrapper; records rejected attempts as well as successes."""

    def __init__(self, inner, *, versions):
        self.inner, self.versions = inner, dict(versions)
        self.records: list[dict] = []

    @property
    def provider(self):
        return self.inner.provider

    def resolved_model(self, tier):
        return self.inner.resolved_model(tier)

    def context_budget(self, tier):
        return self.inner.context_budget(tier)

    def _run(self, kind, fn, **request):
        fingerprint = _identity(kind, versions=self.versions, **request)
        row = {
            "schema": 1,
            "fingerprint": fingerprint,
            "versions": dict(self.versions),
            "operation": kind,
            "provider": self.provider,
            "model": "not_established",
        }
        try:
            row["model"] = self.resolved_model(request.get("tier") or port.Tier.EMBED)
            result = fn()
        except port.ModelError as exc:
            row["error"] = {
                "kind": type(exc).__name__,
                "message": str(exc),
                "usage": asdict(exc.usage) if exc.usage is not None else None,
                "latency_ms": exc.latency_ms,
                "retries": exc.retries,
            }
            row["record_digest"] = _record_digest(row)
            self.records.append(row)
            raise
        row["result"] = _encode(result)
        row["record_digest"] = _record_digest(row)
        self.records.append(row)
        return result

    def tool_call(self, prompt, tools, tier, *, messages=(), max_tokens=None):
        return self._run(
            "tool_call",
            lambda: self.inner.tool_call(
                prompt, tools, tier, messages=messages, max_tokens=max_tokens
            ),
            prompt=prompt,
            tools=tools,
            tier=tier,
            messages=messages,
            max_tokens=max_tokens,
        )

    def complete(self, prompt, tier, *, max_tokens=None):
        return self._run(
            "complete",
            lambda: self.inner.complete(prompt, tier, max_tokens=max_tokens),
            prompt=prompt,
            tier=tier,
            max_tokens=max_tokens,
        )

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        return self._run(
            "structured",
            lambda: self.inner.structured(prompt, schema, tier, max_tokens=max_tokens),
            prompt=prompt,
            schema=schema,
            tier=tier,
            max_tokens=max_tokens,
        )

    def embed(self, texts):
        return self._run("embed", lambda: self.inner.embed(texts), texts=texts)


class ReplayModel:
    """No transport/client/key. Only exact recorded requests may be replayed."""

    def __init__(self, records, *, versions):
        # Deep copy: editing a live recorder must not mutate a replay verdict.
        self.records = json.loads(json.dumps(records, allow_nan=False))
        self.versions, self.position = dict(versions), 0

    @classmethod
    def from_loop(cls, record: LoopRecord, tools, *, versions=None):
        rows, captured_versions = records_from_loop(record, tools, versions=versions)
        return cls(rows, versions=captured_versions)

    @property
    def provider(self):
        return (
            self.records[self.position]["provider"]
            if self.position < len(self.records)
            else "replay"
        )

    def resolved_model(self, tier):
        return (
            self.records[self.position]["model"]
            if self.position < len(self.records)
            else "replay-exhausted"
        )

    def context_budget(self, tier):
        return CONTEXT_BUDGET[tier]

    def _run(self, kind, **request):
        fingerprint = _identity(kind, versions=self.versions, **request)
        if self.position >= len(self.records):
            raise port.ProviderUnavailable("The replay has no remaining recorded model call")
        row = self.records[self.position]
        if row.get("record_digest") != _record_digest(row):
            raise port.SchemaViolation("Replay recording integrity differs from its receipt")
        if row.get("schema") != 1 or row.get("fingerprint") != fingerprint:
            raise port.SchemaViolation("Replay request/version differs from its recording")
        if row.get("versions") != self.versions or row.get("operation") != kind:
            raise port.SchemaViolation("Replay versions or operation differ from its recording")
        if "error" in row:
            error = row["error"]
            if error["kind"] not in _ERRORS:
                raise ValueError("Unknown recorded failure type")
            self.position += 1
            raise _ERRORS[error["kind"]](
                error["message"],
                usage=port.Usage(**error["usage"]) if error["usage"] else None,
                latency_ms=error["latency_ms"],
                retries=error["retries"],
            )
        result = _decode(row["result"])
        if kind == "tool_call":
            port.require_tool_calls(result.calls, request["tools"], request["messages"])
            if not result.usable:
                raise port.OutputTruncated("Replay proposal is not complete")
        if kind == "structured":
            port.require_schema(result.data, request["schema"])
        self.position += 1
        return result

    def tool_call(self, prompt, tools, tier, *, messages=(), max_tokens=None):
        guard_tool_budget(prompt, tools, tier, messages, max_tokens)
        return self._run(
            "tool_call",
            prompt=prompt,
            tools=tools,
            tier=tier,
            messages=messages,
            max_tokens=max_tokens,
        )

    def complete(self, prompt, tier, *, max_tokens=None):
        guard_budget(prompt, tier)
        return self._run("complete", prompt=prompt, tier=tier, max_tokens=max_tokens)

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        guard_budget(prompt, tier)
        return self._run(
            "structured", prompt=prompt, schema=schema, tier=tier, max_tokens=max_tokens
        )

    def embed(self, texts):
        return self._run("embed", texts=texts)
