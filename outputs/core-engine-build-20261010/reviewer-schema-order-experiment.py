"""Six reviewer-only schema-order probes; production and earlier evidence stay unchanged.

Default preparation makes no provider call. --run-approved-once spends only from
the existing shared ledger, without semantic or transport retries.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import evaluate_understanding_five as common
from nm.core_engine import response_review
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import SchemaViolation, Tier, on_the_wire


OUT = Path(__file__).resolve().parent
INPUT = OUT / "reviewer-release-inputs-v2.json"
BASELINE = OUT / "reviewer-release-results-v2.json"
PREPARED = OUT / "reviewer-schema-order-prepared.json"
RESULT = OUT / "reviewer-schema-order-results.json"
spec = importlib.util.spec_from_file_location("prior_release_experiment", OUT / "reviewer-release-experiment.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reorder(schema, names):
    assert set(names) == set(schema["properties"]) == set(schema["required"])
    schema["properties"] = {name: schema["properties"][name] for name in names}
    schema["required"] = list(names)


def reordered_schema(original):
    schema = deepcopy(original)
    reorder(schema["properties"]["units"]["items"], ["unit_id", "reason", "verdict"])
    reorder(schema["properties"]["request_coverage"]["items"],
            ["request", "reason", "disposition", "unit_ids"])
    reorder(schema, ["units", "request_coverage", "findings", "verdict"])
    return schema


def strip_order(value):
    if isinstance(value, dict):
        return {key: sorted(item) if key == "required" else strip_order(item)
                for key, item in value.items()}
    return [strip_order(item) for item in value] if isinstance(value, list) else value


def orders(schema):
    return {"root_properties": list(schema["properties"]), "root_required": schema["required"],
            "unit_properties": list(schema["properties"]["units"]["items"]["properties"]),
            "unit_required": schema["properties"]["units"]["items"]["required"],
            "request_properties": list(schema["properties"]["request_coverage"]["items"]["properties"]),
            "request_required": schema["properties"]["request_coverage"]["items"]["required"]}


class Captured(Exception):
    pass


class Capture:
    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        self.payload = {"user": prompt.user, "operation": prompt.operation,
                        "schema": deepcopy(schema), "kwargs": kwargs}
        raise Captured()


class SchemaOrderOverride(prior.SystemOverride):
    def __init__(self, model, system, receipt, schema):
        super().__init__(model, system, receipt)
        self.schema = schema

    def structured(self, prompt, schema, tier, **kwargs):
        assert schema == response_review.SCHEMA
        assert digest(prompt.user.encode("utf-8")) == self.receipt["expected_user_sha256"]
        return super().structured(prompt, self.schema, tier, **kwargs)


def prepare():
    cases, previous = read(INPUT)["cases"], read(BASELINE)
    assert len(cases) == 6 and response_review.SCHEMA == previous["schema"]
    schema = reordered_schema(previous["schema"])
    assert strip_order(schema) == strip_order(previous["schema"])
    assert orders(on_the_wire(schema)) == orders(schema)
    prior_rows = {row["case_id"]: row for row in previous["reviews"] if row["version"] == "revised"}
    payloads = []
    for case in cases:
        capture = Capture()
        try:
            response_review.review(capture, **case["arguments"])
        except Captured:
            pass
        actual = capture.payload
        assert digest(actual["user"].encode("utf-8")) == prior_rows[case["case_id"]]["user_sha256"]
        payloads.append({"case_id": case["case_id"], **actual})
    prepared = {"model": common.MODEL, "system": previous["systems"]["revised"],
        "input_sha256": digest(INPUT.read_bytes()), "baseline_sha256": digest(BASELINE.read_bytes()),
        "schema": schema, "schema_order": orders(schema), "wire_schema_order": orders(on_the_wire(schema)),
        "only_change": "Schema field order; system, original inputs, types, validation and output ceiling unchanged",
        "maximum_calls": 6, "semantic_retries": 0, "transport_retries": 0,
        "actual_spend_stop_usd": 0.15, "cases": payloads}
    if PREPARED.exists():
        assert read(PREPARED) == prepared, "Preserve earlier prepared evidence"
    else:
        PREPARED.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
    return prepared, cases


def run(prepared, cases):
    assert not RESULT.exists(), "Do not repeat or overwrite this bounded run"
    load_dotenv(common.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == common.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(common.MODEL,))
    source_path = common.ROOT / "nm/core_engine/response_review.py"
    source_hash = digest(source_path.read_bytes())
    state = {"dispatches": 0, "spent": 0.0, "active": None}

    def before_dispatch():
        active = state["active"]
        assert active is not None
        if state["dispatches"] >= 6 or state["spent"] >= 0.15 or active.get("provider_dispatched"):
            raise RuntimeError("Bounded experiment prohibits additional calls or retries")
        active["provider_dispatched"] = True
        state["dispatches"] += 1

    model = OpenAIModelAdapter(config, call_budget=budget).for_matter_text(before_dispatch)
    original_create = model._client.chat.completions.create

    def capture_create(**kwargs):
        actual = kwargs["response_format"]["json_schema"]["schema"]
        assert orders(actual) == prepared["wire_schema_order"]
        assert actual == on_the_wire(prepared["schema"])
        state["active"]["provider_wire_schema"] = deepcopy(actual)
        state["active"]["provider_wire_schema_order"] = orders(actual)
        return original_create(**kwargs)

    model._client.chat.completions.create = capture_create
    result = {"started_utc": datetime.now(timezone.utc).isoformat(), "model": common.MODEL,
        "system": prepared["system"], "schema": prepared["schema"],
        "input_sha256": prepared["input_sha256"], "baseline_sha256": prepared["baseline_sha256"],
        "maximum_calls": 6, "semantic_retries": 0, "transport_retries": 0,
        "actual_spend_stop_usd": 0.15, "source_sha256_before": source_hash,
        "budget_before": budget.status(), "reviews": []}
    try:
        for case in cases:
            if state["spent"] >= 0.15:
                result["stopped_reason"] = "Self-imposed actual-spend stop reached"
                break
            assert digest(source_path.read_bytes()) == source_hash, "Reviewer changed during run"
            saved = next(item for item in prepared["cases"] if item["case_id"] == case["case_id"])
            receipt = {"case_id": case["case_id"], "version": "revised_reason_first_schema",
                       "expected_user_sha256": digest(saved["user"].encode("utf-8"))}
            state["active"] = receipt
            wrapped = SchemaOrderOverride(model, prepared["system"], receipt, prepared["schema"])
            try:
                receipt["checked_review"] = response_review.review(wrapped, **case["arguments"])
                response_review.validate(receipt["checked_review"], **case["arguments"])
            except Exception as exc:
                receipt["error_type"] = type(exc).__name__
                if isinstance(exc, (SchemaViolation, ValueError)):
                    receipt["mechanical_failure"] = str(exc)
            if "provider_result" in receipt:
                state["spent"] += receipt["provider_result"]["usage"]["cost_usd"]
            result["reviews"].append(receipt)
            result.update(budget_after=budget.status(), actual_cost_usd=state["spent"],
                          logical_calls=len(result["reviews"]), provider_dispatches=state["dispatches"])
            RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"case": case["case_id"], "error": receipt.get("error_type"),
                              "actual_cost_usd": state["spent"]}), flush=True)
            if "provider_result" not in receipt:
                result["stopped_reason"] = "Unconfirmed provider result; no further calls"
                break
    finally:
        model._client.chat.completions.create = original_create
        result.update(finished_utc=datetime.now(timezone.utc).isoformat(), budget_after=budget.status(),
                      source_sha256_after=digest(source_path.read_bytes()))
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    prepared, cases = prepare()
    if "--run-approved-once" in sys.argv:
        run(prepared, cases)
    else:
        print(json.dumps({"prepared_cases": len(cases), "paid_calls": 0,
                          "wire_order_confirmed": prepared["schema_order"] == prepared["wire_schema_order"]}))
