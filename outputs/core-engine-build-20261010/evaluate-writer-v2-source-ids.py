"""Prepare one writer call plus its existing conditional contract correction.

Root alone may run --run-approved after review. Full frozen input and owned source
passages are preserved. No retrieval, browser, independent review, or production edit.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("writer_comparison_support", OUT / "compare-writer-v2-frozen.py")
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)

from nm.core_engine.calls import TurnCalls
from nm.shared.model_port import SchemaViolation, Tier

PREFIX = "writer-v2-source-ids"
CANDIDATE = OUT / "response-writer-v2-candidate.py"
INPUT = support.INPUT
MODEL = support.MODEL
LEDGER = support.LEDGER


def save_once(name, value):
    with (OUT / f"{PREFIX}-{name}.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare():
    arguments = support.read(INPUT)["value"]
    writer = support.load_module("writer_source_id_candidate", CANDIDATE)
    capture = support.Capture()
    try:
        writer.write(capture, **deepcopy(arguments))
    except support.Prepared:
        pass
    else:
        raise AssertionError("Writer did not reach the capture boundary")
    payload = json.loads(capture.wire["user"])
    assert payload["original_context"] == arguments["context"]
    assert set(writer.SOURCE_REFERENCE["properties"]) == {"source_id"}
    assert payload["source_kinds"] == {identity: row["kind"] for identity, row in arguments["sources"].items()}
    next_bound = support.bound(capture.wire)
    assert next_bound["next_request_micro_usd"] <= 300_000
    manifest = {"contract": "writer_source_ids_measurement_v1", "writer_contract": writer.CONTRACT,
        "script_sha256": support.sha(Path(__file__)), "candidate_sha256": support.sha(CANDIDATE),
        "support_script_sha256": support.sha(Path(support.__file__)),
        "input_sha256": support.sha(INPUT), "frozen_input": str(INPUT),
        "model": MODEL, "maximum_calls": 2, "maximum_corrections": 1,
        "correction_owner": "Unchanged TurnCalls.checked; only a typed SchemaViolation can request correction",
        "maximum_slice_usd": 0.30, "shared_cap_usd": 5, "shared_ledger": str(LEDGER),
        "transport_retries": 0, "next_request_bound": next_bound,
        "bound_note": "The previous conservative twice-serialized-UTF8-byte plus 8192 framing allowance is retained. Every next dispatch must fit the remaining $0.30 slice; the existing shared ledger separately reserves the model's full verified input ceiling. A long correction may therefore be refused before spending.",
        "preserved_copy_experiment": support.read(OUT / "writer-v2-copy-experiment-snapshots.json"),
        "acceptance_limit": "Mechanical source admission only; root must inspect substantive accuracy and arrange final independent review/browser validation",
        "offline_checks": {"provider_calls": 0, "same_full_context": True,
                           "retrieval_calls": 0, "production_changes": 0}}
    return writer, manifest, arguments, capture.wire


class ObservedPort:
    def __init__(self, adapter, sdk, expected, rows):
        self.adapter, self.sdk, self.expected, self.rows = adapter, sdk, expected, rows

    def context_budget(self, tier):
        return self.adapter.context_budget(tier)

    def structured(self, prompt, schema, tier, *, max_tokens):
        assert len(self.rows) < 2, "One initial writer call and one conditional contract correction"
        wire = {"system": prompt.system, "user": prompt.user, "operation": prompt.operation,
                "schema": deepcopy(schema), "tier": tier.value, "max_tokens": max_tokens}
        assert all(wire[key] == value for key, value in self.expected.items() if key != "user")
        payload, original = json.loads(wire["user"]), json.loads(self.expected["user"])
        if not self.rows:
            assert payload == original
        else:
            correction = payload.pop("correction")
            assert payload == original
            assert correction["operation"] == "core_response_writer" and correction["mismatch"]
            assert correction["rejected_draft"] == self.rows[0]["response"]["data"]
        row = {"number": len(self.rows) + 1, "request": wire, "bound": support.bound(wire)}
        self.rows.append(row)
        self.sdk.arm(wire, row)
        capture = support.Capture(self.adapter, wire, row)
        return capture.structured(prompt, schema, tier, max_tokens=max_tokens)


def run(writer, manifest, arguments, wire):
    assert Path(sys.prefix).resolve() == (ROOT / ".venv-arrive").resolve(), "Use .venv-arrive Python"
    assert LEDGER.is_file(), "Existing shared ledger is required"
    assert not list(OUT.glob(f"{PREFIX}-*.json")), "This experiment already started; do not replay"
    save_once("started", {"utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest})
    save_once("input", {"manifest": manifest, "arguments": arguments, "initial_request": wire})
    from nm.shared.model_call_budget import SessionCallBudget
    from nm.shared.model_config import load, load_dotenv, PRICES
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    load_dotenv(ROOT / ".env")
    config = load()
    cfg = config.for_tier(Tier.ROUTINE)
    assert cfg.provider == "openai" and cfg.model == MODEL
    assert cfg.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(LEDGER, "5", models=(MODEL,))
    before = budget.status()
    raw = OpenAIModelAdapter(config, call_budget=budget)
    sdk = support.OneShotSDK(raw._client, budget, Decimal(str(before["charged_usd"])))
    adapter = OpenAIModelAdapter(config, client=sdk, call_budget=budget).for_matter_text(sdk.before_dispatch)
    rows = []
    calls = TurnCalls(ObservedPort(adapter, sdk, wire, rows))
    result = {"manifest": manifest, "budget_before": before, "attempts": rows}

    def attempt():
        assert support.sha(CANDIDATE) == manifest["candidate_sha256"]
        assert support.sha(INPUT) == manifest["input_sha256"]
        assert support.sha(Path(__file__)) == manifest["script_sha256"]
        assert support.sha(Path(support.__file__)) == manifest["support_script_sha256"]
        try:
            draft = writer.write(calls, **deepcopy(arguments))
            assert writer.validate(draft, arguments["context"], arguments["sources"]) == draft
            rows[-1].update(admission="accepted_mechanically", draft=draft)
            return draft
        except SchemaViolation as exc:
            rows[-1].update(admission="rejected", mismatch=str(exc))
            raise
        finally:
            if rows:
                row = rows[-1]
                row["budget_after"] = budget.status()
                row["total_sdk_dispatches"] = sdk.dispatches
                save_once(f"attempt-{row['number']:02d}", row)
                assert row["budget_after"]["reserved_or_unknown_usd"] == before["reserved_or_unknown_usd"], "Unknown usage; stop"
                if row.get("response"):
                    usage = row["response"]["usage"]
                    measured = Decimal(usage["tokens_in"]) * Decimal(str(PRICES[MODEL][0])) + Decimal(usage["tokens_out"]) * Decimal(str(PRICES[MODEL][1]))
                    assert measured <= row["bound"]["next_request_micro_usd"], "Measured use exceeded planning allowance"

    try:
        result["draft"] = calls.checked("core_response_writer", attempt)
        result["admission"] = "accepted_mechanically"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = "Provider request failed; no retry" if any(row.get("provider_error_type") for row in rows) else str(exc)
    result.update(metrics=calls.metrics(), budget_after=budget.status(),
        actual_sdk_dispatches=sdk.dispatches, finished_utc=datetime.now(timezone.utc).isoformat())
    save_once("results", result)
    print(json.dumps({"admission": result.get("admission"), "error_type": result.get("error_type"),
        "actual_sdk_dispatches": sdk.dispatches, "metrics": result["metrics"],
        "budget_after": result["budget_after"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved", action="store_true", help="Root-reviewed paid path")
    args = parser.parse_args()
    writer, manifest, arguments, wire = prepare()
    if args.run_approved:
        run(writer, manifest, arguments, wire)
    else:
        print(json.dumps({"prepared_in_memory": True, "provider_calls": 0, "contract": writer.CONTRACT,
            "maximum_calls": 2, "maximum_corrections": 1, "slice_cap_usd": 0.30,
            "next_request_bound_usd": manifest["next_request_bound"]["next_request_micro_usd"] / 1_000_000}))
