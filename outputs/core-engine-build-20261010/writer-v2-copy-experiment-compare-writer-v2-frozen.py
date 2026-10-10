"""Prepare, then optionally run two isolated writer calls on identical saved inputs.

Default: no SDK, credentials, ledger write or paid call. Root reviews before using
--run-approved. No retrieval, browser, save, retry, or production modification.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))
from nm.shared.model_config import CONTEXT_BUDGET, PRICES
from nm.shared.model_port import ModelError, SchemaViolation, Tier, on_the_wire

MODEL = "gpt-4.1-mini-2025-04-14"
MAX_CALLS = 2
SLICE_CAP_MICRO = 300_000
PREFIX = "writer-v2-frozen-comparison"
LEDGER = OUT / "api-budget.sqlite"
DIAGNOSTIC = OUT / "browser-core-v4-diagnostics/cd29f5e8fc1645489e685354e1046535"
INPUT = DIAGNOSTIC / "010-response_writer-write-input.json"
VARIANTS = [("baseline_v1", OUT / "response-writer-v1-baseline.py"),
            ("candidate_v2", OUT / "response-writer-v2-candidate.py")]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_once(name, value):
    with (OUT / f"{PREFIX}-{name}.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def request(wire):
    return {"model": MODEL, "messages": [{"role": "system", "content": wire["system"]},
            {"role": "user", "content": wire["user"]}], "store": False,
            "max_completion_tokens": wire["max_tokens"],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "nm_result", "strict": True, "schema": on_the_wire(wire["schema"])}}}


def bound(wire):
    size = len(json.dumps(request(wire), ensure_ascii=False).encode("utf-8"))
    incoming = 2 * size + 8192
    incoming_price, outgoing_price = (Decimal(str(value)) for value in PRICES[MODEL])
    micro = int((incoming * incoming_price + wire["max_tokens"] * outgoing_price
                 ).to_integral_value(rounding=ROUND_CEILING))
    return {"serialized_sdk_bytes": size, "planning_input_tokens": incoming,
            "output_hard_cap": wire["max_tokens"], "next_request_micro_usd": micro}


class Prepared(Exception):
    pass


class Capture:
    def __init__(self, actual=None, expected=None, row=None):
        self.actual, self.expected, self.row, self.wire = actual, expected, row, None

    def context_budget(self, tier):
        return self.actual.context_budget(tier) if self.actual else CONTEXT_BUDGET[tier]

    def structured(self, prompt, schema, tier, *, max_tokens):
        assert self.wire is None, "Only one writer dispatch per variant is authorised"
        self.wire = {"system": prompt.system, "user": prompt.user, "operation": prompt.operation,
                     "schema": deepcopy(schema), "tier": tier.value, "max_tokens": max_tokens}
        if self.actual is None:
            raise Prepared()
        assert self.wire == self.expected, "Writer request changed after preparation"

        def record(result):
            self.row["response"] = {"data": deepcopy(result.data), "model": result.model,
                "usage": asdict(result.usage), "latency_ms": result.latency_ms,
                "retries": result.retries, "completion": result.completion.value}
            assert result.model == MODEL and result.retries == 0

        try:
            result = self.actual.structured(prompt, schema, tier, max_tokens=max_tokens)
        except SchemaViolation as exc:
            if exc.rejected_result is not None:
                record(exc.rejected_result)
                self.row["adapter_rejection"] = str(exc)
            raise
        record(result)
        return result


def prepare():
    arguments = read(INPUT)["value"]
    rows = []
    for name, path in VARIANTS:
        writer = load_module(name, path)
        capture = Capture()
        try:
            writer.write(capture, **deepcopy(arguments))
        except Prepared:
            pass
        else:
            raise AssertionError("Writer did not reach the capture boundary")
        payload = json.loads(capture.wire["user"])
        assert payload["original_context"] == arguments["context"]
        rows.append({"name": name, "file": str(path), "sha256": sha(path),
                     "contract": writer.CONTRACT, "wire": capture.wire, "bound": bound(capture.wire)})
    original, changed = (json.loads(row["wire"]["user"]) for row in rows)
    assert all(changed[key] == value for key, value in original.items())
    assert set(changed) - set(original) == {"source_kinds"}
    manifest = {"contract": "writer_frozen_comparison_v1", "model": MODEL,
        "script_sha256": sha(Path(__file__)), "frozen_input": str(INPUT), "input_sha256": sha(INPUT),
        "maximum_calls": MAX_CALLS, "maximum_slice_usd": SLICE_CAP_MICRO / 1_000_000,
        "shared_ledger": str(LEDGER), "shared_cap_usd": 5, "transport_retries": 0,
        "comparison": "Fresh baseline v1 and candidate v2, once each, identical complete saved context and legal sources",
        "preserved_prior_outputs": [{"file": str(DIAGNOSTIC / name), "sha256": sha(DIAGNOSTIC / name)}
                                    for name in ("012-model-output.json", "016-model-output.json")],
        "bound_note": "Twice the complete SDK JSON UTF-8 bytes plus 8192 input tokens, uncached configured prices and the output cap. This is the existing conservative engineering allowance. The shared SessionCallBudget separately reserves the full verified model input ceiling before dispatch. No bound is lowered to fit the experiment.",
        "acceptance_limit": "Contract admission alone is not semantic accuracy, independent review, or browser acceptance",
        "offline_checks": {"complete_context": True, "same_held_sources": True, "retrieval_calls": 0,
                           "provider_calls": 0, "production_changes": 0}}
    assert all(row["bound"]["next_request_micro_usd"] <= SLICE_CAP_MICRO for row in rows)
    return manifest, rows, arguments


class OneShotSDK:
    def __init__(self, actual, budget, starting_charge):
        self.actual, self.budget, self.starting_charge = actual, budget, starting_charge
        self.chat = SimpleNamespace(completions=self)
        self.dispatches, self.row, self.wire, self.reservation_attempted = 0, None, None, False

    def arm(self, wire, row):
        charged = Decimal(str(self.budget.status()["charged_usd"]))
        delta = int((charged - self.starting_charge) * 1_000_000)
        assert self.dispatches < MAX_CALLS
        assert delta + bound(wire)["next_request_micro_usd"] <= SLICE_CAP_MICRO, "Next call exceeds slice allowance"
        self.row, self.wire, self.reservation_attempted = row, deepcopy(wire), False

    def before_dispatch(self):
        assert self.row is not None and not self.reservation_attempted, "No transport retry authorised"
        self.reservation_attempted = True

    def create(self, **kwargs):
        assert self.reservation_attempted and self.dispatches < MAX_CALLS
        assert not self.row.get("sdk_request"), "One SDK dispatch per variant"
        assert kwargs == request(self.wire), "SDK request differs from prepared writer input"
        self.row["sdk_request"] = deepcopy(kwargs)
        self.dispatches += 1
        try:
            raw = self.actual.chat.completions.create(**kwargs)
        except Exception as exc:
            self.row["provider_error_type"] = type(exc).__name__
            raise ModelError("Provider request failed; no retry is authorised") from exc
        self.row["provider_response"] = raw.model_dump(mode="json")
        return raw


def run(manifest, rows, arguments):
    assert Path(sys.prefix).resolve() == (ROOT / ".venv-arrive").resolve(), "Use .venv-arrive Python"
    assert LEDGER.is_file(), "Existing shared ledger is required; never create a replacement"
    assert not list(OUT.glob(f"{PREFIX}-*.json")), "A comparison already started; do not replay it"
    save_once("started", {"utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest})
    save_once("inputs", {"manifest": manifest, "arguments": arguments, "variants": rows})
    from nm.shared.model_call_budget import SessionCallBudget
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    load_dotenv(ROOT / ".env")
    config = load()
    cfg = config.for_tier(Tier.ROUTINE)
    assert cfg.provider == "openai" and cfg.model == MODEL
    assert cfg.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(LEDGER, "5", models=(MODEL,))
    before = budget.status()
    raw_adapter = OpenAIModelAdapter(config, call_budget=budget)
    sdk = OneShotSDK(raw_adapter._client, budget, Decimal(str(before["charged_usd"])))
    adapter = OpenAIModelAdapter(config, client=sdk, call_budget=budget).for_matter_text(sdk.before_dispatch)
    output = {"manifest": manifest, "budget_before": before, "results": []}
    for index, prepared in enumerate(rows, 1):
        row = {"variant": prepared["name"], "bound": prepared["bound"]}
        output["results"].append(row)
        stop = False
        try:
            assert sha(Path(__file__)) == manifest["script_sha256"]
            assert sha(INPUT) == manifest["input_sha256"]
            path = Path(prepared["file"])
            assert sha(path) == prepared["sha256"]
            writer = load_module(prepared["name"], path)
            sdk.arm(prepared["wire"], row)
            capture = Capture(adapter, prepared["wire"], row)
            try:
                draft = writer.write(capture, **deepcopy(arguments))
            except SchemaViolation as exc:
                row.update(admission="rejected", mismatch=str(exc))
                if not row.get("response"):
                    raise
            else:
                assert writer.validate(draft, arguments["context"], arguments["sources"]) == draft
                row.update(admission="accepted_mechanically", draft=draft)
            after = budget.status()
            assert after["reserved_or_unknown_usd"] == before["reserved_or_unknown_usd"], "Unknown usage; stop"
            usage = row["response"]["usage"]
            measured = Decimal(usage["tokens_in"]) * Decimal(str(PRICES[MODEL][0])) + Decimal(usage["tokens_out"]) * Decimal(str(PRICES[MODEL][1]))
            assert measured <= prepared["bound"]["next_request_micro_usd"], "Measured use exceeded its planning allowance"
            assert Decimal(str(after["charged_usd"])) - Decimal(str(before["charged_usd"])) <= Decimal("0.30")
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = "Provider dispatch failed; see provider_error_type" if row.get("provider_error_type") else str(exc)
            stop = True
        row["budget_after"] = budget.status()
        row["total_sdk_dispatches"] = sdk.dispatches
        save_once(f"result-{index:02d}", row)
        print(json.dumps({"variant": prepared["name"], "admission": row.get("admission"),
            "error_type": row.get("error_type"), "dispatches": sdk.dispatches,
            "budget": row["budget_after"]}), flush=True)
        if stop:
            output["stopped"] = "Stop on provider, unconfirmed, resource, or artifact failure; no retry"
            break
    output.update(budget_after=budget.status(), actual_sdk_dispatches=sdk.dispatches,
                  finished_utc=datetime.now(timezone.utc).isoformat())
    save_once("results", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved", action="store_true", help="Paid path: root must review first")
    args = parser.parse_args()
    manifest, rows, arguments = prepare()
    if args.run_approved:
        run(manifest, rows, arguments)
    else:
        print(json.dumps({"prepared_in_memory": True, "provider_calls": 0,
            "contracts": [row["contract"] for row in rows], "maximum_calls": MAX_CALLS,
            "slice_cap_usd": SLICE_CAP_MICRO / 1_000_000,
            "next_call_bounds_usd": [row["bound"]["next_request_micro_usd"] / 1_000_000 for row in rows]}))
