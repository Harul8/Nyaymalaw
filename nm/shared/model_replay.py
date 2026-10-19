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

from nm.shared import model_port as port
from nm.shared.budget_contracts import Completion
from nm.shared.model_budget import guard_budget, guard_tool_budget
from nm.shared.model_config import CONTEXT_BUDGET


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


def _known_error(error, *, operation=None, tier=None, provider=None, model=None):
    fields = {"kind", "message", "usage", "latency_ms", "retries"}
    if not isinstance(error, dict) or set(error) not in (fields, fields | {"rejected_result"}):
        raise port.SchemaViolation("A saved model failure is not a complete error receipt")
    if not isinstance(error["kind"], str) or error["kind"] not in _ERRORS:
        raise port.SchemaViolation("A saved failure has no normalized model-error type")
    if not isinstance(error["message"], str) or not error["message"].strip():
        raise port.SchemaViolation("A saved failure has no reason")
    if any(type(error[key]) is not int or error[key] < 0 for key in ("latency_ms", "retries")):
        raise port.SchemaViolation("A saved failure has invalid latency or retry accounting")
    if error["usage"] is not None:
        try:
            _usage_from_wire(error["usage"])
        except (TypeError, ValueError) as exc:
            raise port.SchemaViolation("A saved failure has invalid usage accounting") from exc
    if "rejected_result" not in error:
        return None
    if error["kind"] != "SchemaViolation" or operation != "structured":
        raise port.SchemaViolation("Only a failed structured read can carry quarantined proposals")
    encoded = error["rejected_result"]
    if (not isinstance(encoded, dict) or set(encoded) != {"kind", "value"}
            or encoded["kind"] != "ModelResult" or not isinstance(encoded["value"], dict)):
        raise port.SchemaViolation("A quarantined proposal has no typed result receipt")
    try:
        rejected = _decode(encoded)
        # The port constructor owns completeness, object shape and immutable
        # JSON snapshot validation; importing a journal cannot weaken it.
        port.SchemaViolation(error["message"], rejected_result=rejected)
    except (KeyError, TypeError, ValueError) as exc:
        raise port.SchemaViolation("A quarantined proposal receipt is malformed") from exc
    if (rejected.tier is not tier or (rejected.provider, rejected.model) != (provider, model)
            or error["usage"] is None or rejected.usage != _usage_from_wire(error["usage"])
            or (rejected.latency_ms, rejected.retries)
            != (error["latency_ms"], error["retries"])):
        raise port.SchemaViolation("A quarantined proposal differs from its failed-call receipt")
    return rejected


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
            if isinstance(exc, port.SchemaViolation) and exc.rejected_result is not None:
                row["error"]["rejected_result"] = _encode(exc.rejected_result)
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
            rejected = _known_error(
                error, operation=kind, tier=request.get("tier"),
                provider=row["provider"], model=row["model"],
            )
            if rejected is not None:
                try:
                    port.require_schema(rejected.data, request["schema"])
                except port.SchemaViolation:
                    pass
                else:
                    raise port.SchemaViolation("The quarantined result did not fail this schema")
            self.position += 1
            quarantine = {"rejected_result": rejected} if rejected is not None else {}
            raise _ERRORS[error["kind"]](
                error["message"],
                usage=port.Usage(**error["usage"]) if error["usage"] else None,
                latency_ms=error["latency_ms"],
                retries=error["retries"],
                **quarantine,
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
