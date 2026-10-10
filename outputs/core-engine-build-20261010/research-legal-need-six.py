"""Bounded planner comparison against saved synthetic baselines; no retrieval.

Default writes the predeclared sample and does not load credentials or call a model.
The explicit run flag uses the approved shared USD5 ledger, at most six logical
calls, no semantic retries, and a USD0.08 additional actual-spend stop.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import evaluate_understanding_five as common
from nm.core_engine import research
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier

OUT = Path(__file__).resolve().parent
PREPARED = OUT / "research-legal-need-six-prepared.json"
EVIDENCE = OUT / "research-legal-need-six.json"
LIMIT = 0.08


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(name):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")), digest(path.read_bytes())


def cases():
    baseline, baseline_hash = read("research-probe.json")
    capacity, capacity_hash = read("offline-retrieval-capacity-snapshot.json")
    understanding, understanding_hash = read("understanding-five-live.json")
    rows = []
    for old in baseline["cases"]:
        original = json.loads(old["calls"][0]["user"])
        expected = deepcopy(old["expected_before_run"])
        if old["name"] == "deposit_and_drive":
            expected["qualifications"] = [
                "Damage is alleged and disputed",
                "Joint inspection report has not been supplied; existence is unknown",
                "Drive purpose is client-reported",
                "Client being based in Hyderabad does not establish jurisdiction"]
        rows.append({"name": old["name"], "context": original["original_context"],
            "interpretation_proposal": original["interpretation_proposal"],
            "expected_before_run": expected, "baseline_plan": deepcopy(old["accepted_plan"]),
            "baseline_origin": "research-probe.json", "input_origin": "exact saved original call"})
    rows.append({"name": "capacity_deposit_drive", "context": capacity["context"],
        "interpretation_proposal": capacity["interpretation"],
        "baseline_plan": capacity["research"]["plan"],
        "baseline_origin": "offline-retrieval-capacity-snapshot.json",
        "input_origin": "exact saved capacity case; no retrieval rerun",
        "expected_before_run": {
            "independent_results": ["Conditional deposit and drive analysis including contrary positions",
                                    "Draft useful client questions"],
            "qualifications": ["Damage remains alleged and denied", "No joint report was sent, not proved nonexistent",
                               "Client reports return, documents and drive purpose; none is independently checked",
                               "Hyderabad client location alone does not fix jurisdiction",
                               "Owner claims a right to retain the drive; no entitlement is established"],
            "restrictions": ["Do not contact anyone", "Do not admit damage", "Do not treat reported documents as checked"],
            "search_distinction": "Questions can use the same law; output format alone does not justify additional enquiries"}})
    old = next(row for row in understanding["cases"] if row["name"] == "correction")
    rows.append({"name": "date_correction", "context": old["context"],
        "interpretation_proposal": old["accepted"], "baseline_plan": None,
        "baseline_origin": None, "input_origin": "saved understanding case, not previously measured by this planner",
        "expected_before_run": {**old["expected_before_run"],
            "independent_results": ["Correct NM's summary date from 14 May to the original 14 April"],
            "expected_enquiries": [], "search_distinction": "This factual repair requires no legal retrieval"}})
    return rows, {"research-probe.json": baseline_hash,
                  "offline-retrieval-capacity-snapshot.json": capacity_hash,
                  "understanding-five-live.json": understanding_hash}


class RecordedModel:
    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def context_budget(self, tier):
        return self.inner.context_budget(tier)

    def structured(self, prompt, schema, tier, **kwargs):
        assert tier is Tier.ROUTINE and len(self.calls) < 6
        record = {"system": prompt.system, "user": prompt.user,
                  "operation": prompt.operation, "schema": deepcopy(schema), "kwargs": kwargs}
        self.calls.append(record)
        try:
            result = self.inner.structured(prompt, schema, tier, **kwargs)
            record["result"] = {"data": deepcopy(result.data), "model": result.model,
                                "usage": asdict(result.usage), "latency_ms": result.latency_ms,
                                "retries": result.retries, "completion": result.completion.value}
            return result
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            if getattr(exc, "usage", None):
                record["usage"] = asdict(exc.usage)
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-after-prompt-freeze", action="store_true")
    args = parser.parse_args()
    sample, baseline_hashes = cases()
    source = common.ROOT / "nm/core_engine/research.py"
    source_hash = digest(source.read_bytes())
    manifest = {"model": common.MODEL, "source_sha256": source_hash,
        "prompt_sha256": digest(research.SYSTEM.encode("utf-8")), "baseline_sha256": baseline_hashes,
        "maximum_logical_calls": 6, "semantic_retries": 0, "actual_spend_stop_usd": LIMIT,
        "shared_ledger": "api-budget.sqlite", "shared_hard_cap_usd": 5,
        "scope": "Fixed saved samples; historical baseline is not contemporaneous A/B or a fresh holdout estimate",
        "expectation_correction": "Historical report-absent label corrected only in this new assessment to not supplied/existence unknown",
        "success_distinctions_before_run": [
            "Preserve every independent requested result, restrictions and factual qualifications.",
            "Queries seek distinct legal relationships/propositions, not instructions to draft outputs.",
            "Shared research can leave an independent work item's enquiries empty without dropping that work.",
            "Materially different legal needs still receive distinct enquiries; fewer queries alone is not success.",
            "Plans and source selections remain unadmitted semantic proposals; schema does not certify coverage.",
            "No source retrieval or writer capacity claim follows from this planner-only comparison."],
        "cases": [{key: row[key] for key in ("name", "expected_before_run", "input_origin", "baseline_origin")}
                  for row in sample]}
    if not args.run_after_prompt_freeze:
        if PREPARED.exists():
            assert json.loads(PREPARED.read_text(encoding="utf-8")) == manifest
        else:
            PREPARED.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"prepared": PREPARED.name, "logical_calls": 0, "cases": len(sample)}))
        return
    assert not EVIDENCE.exists(), "Evidence already exists; refusing another paid run."
    assert json.loads(PREPARED.read_text(encoding="utf-8")) == manifest
    load_dotenv(common.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == common.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(common.MODEL,))
    # The exact synthetic inputs above are the only matter data approved here.
    model = RecordedModel(OpenAIModelAdapter(config, call_budget=budget).for_matter_text(lambda: None))
    before = budget.status()
    result = {"started_utc": datetime.now(timezone.utc).isoformat(), "preparation": manifest,
              "budget_before": before, "model": common.MODEL, "output_ceiling": research.MAX_OUTPUT,
              "source_sha256": source_hash, "cases": []}
    for item in sample:
        if len(model.calls) >= 6 or budget.status()["charged_usd"] - before["charged_usd"] >= LIMIT:
            result["stopped_reason"] = "Bounded comparison call/spend stop"
            break
        assert digest(source.read_bytes()) == source_hash, "Planner source changed during measurement"
        row, start = deepcopy(item), len(model.calls)
        try:
            row["accepted_plan"] = research.plan(model, row["context"], row["interpretation_proposal"])
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        row["calls"] = deepcopy(model.calls[start:])
        result["cases"].append(row)
        result["logical_calls"] = len(model.calls)
        result["budget_after"] = budget.status()
        result["actual_cost_usd"] = result["budget_after"]["charged_usd"] - before["charged_usd"]
        result["source_sha256_after"] = digest(source.read_bytes())
        EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": row["name"], "calls": len(row["calls"]),
                          "error": row.get("error_type"), "cost_usd": result["actual_cost_usd"]}), flush=True)
    print(json.dumps({"logical_calls": len(model.calls), "actual_cost_usd": result.get("actual_cost_usd", 0),
                      "budget": budget.status()}), flush=True)


if __name__ == "__main__":
    main()
