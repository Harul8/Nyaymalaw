"""Sequential retry after a confirmed zero-dispatch experiment; default is offline preparation.

The only candidate differences are source-selection-before-prose wire ordering and
one Outcome sentence. No production files, retrieval, retries, or saved matter edits.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
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
from nm.shared.model_port import Tier

PREFIX = "writer-v2-support-first-sequential"
CANDIDATE = OUT / "response-writer-v2-support-first-candidate.py"
BASELINE = OUT / "writer-v2-source-ids-tested-baseline.py"
INPUT, LEDGER, MODEL = support.INPUT, support.LEDGER, support.MODEL


def save_once(name, value):
    with (OUT / f"{PREFIX}-{name}.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def meaning(schema):
    if isinstance(schema, dict):
        return {key: sorted(value) if key == "required" else meaning(value)
                for key, value in schema.items()}
    if isinstance(schema, list):
        return [meaning(value) for value in schema]
    return schema


def capture(module, arguments):
    port = support.Capture()
    try:
        module.write(port, **deepcopy(arguments))
    except support.Prepared:
        pass
    else:
        raise AssertionError("Writer did not reach the capture boundary")
    return port.wire


def prepare():
    writer = support.load_module("writer_support_first_candidate", CANDIDATE)
    baseline = support.load_module("writer_source_ids_baseline", BASELINE)
    arguments = support.read(INPUT)["value"]
    prior_path = OUT / "writer-v2-support-first-result.json"
    prior = support.read(prior_path)
    assert prior["actual_sdk_dispatches"] == 0
    assert "sdk_request" not in prior and "response" not in prior and "provider_response" not in prior
    assert prior["error"] == "Next call exceeds slice allowance"
    assert support.sha(CANDIDATE) == prior["manifest"]["candidate_sha256"]
    assert support.sha(INPUT) == prior["manifest"]["input_sha256"]
    old_wire, new_wire = capture(baseline, arguments), capture(writer, arguments)
    assert old_wire["user"] == new_wire["user"], "All full variable input must remain unchanged"
    assert meaning(baseline.SCHEMA) == meaning(writer.SCHEMA), "Only schema field order may change"
    assert baseline.LEGACY_SCHEMA == writer.LEGACY_SCHEMA
    assert list(writer.SCHEMA["properties"]["units"]["items"]["properties"]) == ["addresses", "uses", "kind", "text"]
    assert writer.SCHEMA["properties"]["units"]["items"]["required"] == ["addresses", "uses", "kind", "text"]
    insertion = " For each unit, select the addressed message and supporting\nfactual and legal passages first, then choose the kind and write only what those sources\nsupport."
    assert writer.SYSTEM == baseline.SYSTEM.replace("addresses and source uses.", "addresses and source uses." + insertion, 1)
    initial_bound = support.bound(new_wire)
    assert initial_bound["next_request_micro_usd"] <= 300_000
    manifest = {"contract": "writer_ordering_experiment_v1", "model": MODEL,
        "script_sha256": support.sha(Path(__file__)), "candidate_sha256": support.sha(CANDIDATE),
        "baseline_sha256": support.sha(BASELINE), "input_sha256": support.sha(INPUT),
        "support_script_sha256": support.sha(Path(support.__file__)),
        "frozen_input": str(INPUT), "maximum_calls": 1, "corrections": 0, "transport_retries": 0,
        "maximum_slice_usd": 0.30, "shared_cap_usd": 5, "shared_ledger": str(LEDGER),
        "next_request_bound": initial_bound,
        "changed_decision_order": "addresses, uses, kind, text",
        "new_instruction": insertion.strip(),
        "acceptance_limit": "A source-ordering experiment, not a guarantee of grounded reasoning. Root must compare legal assertions with the selected held law. Mechanical admission is not semantic or browser acceptance.",
        "retry_basis": {"prior_result": str(prior_path), "prior_result_sha256": support.sha(prior_path),
            "actual_prior_dispatches": 0, "prior_error": prior["error"],
            "constraint": "Root executes sequentially after the other paid experiment completes; no automatic wait, retry or spending-bound change"},
        "offline_checks": {"provider_calls": 0, "identical_full_variable_input": True,
                           "same_schema_meaning": True, "unchanged_legacy_schema": True,
                           "one_added_prompt_sentence": True, "production_changes": 0}}
    return writer, manifest, arguments, new_wire


def run(writer, manifest, arguments, wire):
    assert Path(sys.prefix).resolve() == (ROOT / ".venv-arrive").resolve(), "Use .venv-arrive Python"
    assert LEDGER.is_file(), "Existing shared ledger is required"
    assert not list(OUT.glob(f"{PREFIX}-*.json")), "This experiment already started; do not replay"
    save_once("started", {"utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest})
    save_once("input", {"manifest": manifest, "arguments": arguments, "request": wire})
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
    row = {"manifest": manifest, "budget_before": before}
    try:
        assert support.sha(CANDIDATE) == manifest["candidate_sha256"]
        assert support.sha(BASELINE) == manifest["baseline_sha256"]
        assert support.sha(INPUT) == manifest["input_sha256"]
        assert support.sha(Path(__file__)) == manifest["script_sha256"]
        assert support.sha(Path(support.__file__)) == manifest["support_script_sha256"]
        sdk.arm(wire, row)
        port = support.Capture(adapter, wire, row)  # Rejects a second structured call.
        draft = writer.write(port, **deepcopy(arguments))
        assert writer.validate(draft, arguments["context"], arguments["sources"]) == draft
        row.update(admission="accepted_mechanically", draft=draft)
        assert budget.status()["reserved_or_unknown_usd"] == before["reserved_or_unknown_usd"], "Unknown usage; stop"
        usage = row["response"]["usage"]
        measured = Decimal(usage["tokens_in"]) * Decimal(str(PRICES[MODEL][0])) + Decimal(usage["tokens_out"]) * Decimal(str(PRICES[MODEL][1]))
        assert measured <= manifest["next_request_bound"]["next_request_micro_usd"], "Measured use exceeded planning allowance"
    except Exception as exc:
        row["error_type"] = type(exc).__name__
        row["error"] = "Provider request failed; no retry" if row.get("provider_error_type") else str(exc)
    row.update(budget_after=budget.status(), actual_sdk_dispatches=sdk.dispatches,
               finished_utc=datetime.now(timezone.utc).isoformat())
    assert sdk.dispatches <= 1
    save_once("result", row)
    print(json.dumps({"admission": row.get("admission"), "error_type": row.get("error_type"),
        "actual_sdk_dispatches": sdk.dispatches, "budget_after": row["budget_after"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved", action="store_true", help="Root-reviewed paid path")
    args = parser.parse_args()
    writer, manifest, arguments, wire = prepare()
    if args.run_approved:
        run(writer, manifest, arguments, wire)
    else:
        print(json.dumps({"prepared_in_memory": True, "provider_calls": 0,
            "maximum_calls": 1, "corrections": 0, "slice_cap_usd": 0.30,
            "next_request_bound_usd": manifest["next_request_bound"]["next_request_micro_usd"] / 1_000_000,
            "checks": manifest["offline_checks"]}))
