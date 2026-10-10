"""Prepare an isolated evaluation of the actual research.plan implementation.

Default execution constructs all eight real production prompts, without an SDK,
credentials, ledger writes or provider calls. --run-approved is the paid path.
All stored output files use exclusive creation; an interrupted run cannot restart.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))

from nm.core_engine import research
from nm.shared.model_config import CONTEXT_BUDGET, PRICES
from nm.shared.model_port import ModelError, SchemaViolation, Tier, on_the_wire

MODEL = "gpt-4.1-mini-2025-04-14"
MAX_CALLS = 8
SLICE_CAP_MICRO = 200_000
PER_CALL_CAP_MICRO = 50_000
PREFIX = "research-v3-runtime-ready"
BASE = OUT / "research-only-concepts-inputs.json"
EARLIER = OUT / "research-account-concepts-inputs.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_once(suffix, value):
    target = OUT / f"{PREFIX}-{suffix}.json"
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def original(turn, text, *, speaker="advocate", role="original_account"):
    return {"source_id": f"{turn}:{speaker}", "turn_id": turn,
            "speaker": speaker, "record_role": role, "text": text}


def cases():
    old = {row["name"]: row for row in read(EARLIER)["cases"]}
    rows = []
    for row in read(BASE)["cases"]:
        prior = old[row["name"]]
        assert row["context"] == prior["context"], "Original context differs between frozen inputs"
        rows.append({"name": row["name"], "origin": row["origin"],
            "context": deepcopy(row["context"]),
            "interpretation": deepcopy(prior["interpretation_proposal"]),
            "interpretation_origin": "Unchanged earlier recorded proposal from research-account-concepts-inputs.json",
            "assessment_scope": "Same six regression contexts; not unfamiliar holdouts"})
    assert len(rows) == 6
    text = (
        "This is a synthetic matter. We represent a swimmer registered with a regional sports association. "
        "The secretary emailed that her competition eligibility is temporarily suspended pending an inquiry "
        "into alleged tampering with a sample. She denies touching the sample. The email says no final "
        "disciplinary finding has been made. She requested the chain-of-custody record; it has not been "
        "supplied to us, and we do not know whether it exists. Selection closes in six days. Separately, "
        "a sponsor has withheld an agreed appearance fee after hearing about the allegation. Our client "
        "reports a sponsorship agreement but has not provided it here. Give conditional source-backed "
        "analysis of the eligibility restriction and withheld fee, including material contrary positions, "
        "and prepare a short list of questions for her. Do not contact the association or sponsor."
    )
    rows.append({"name": "holdout_temporary_sport_restriction_and_fee",
        "origin": "New synthetic holdout, not used by preceding planner pilots",
        "context": {"position": "first", "latest": original("v3-holdout-a", text),
                    "conversation": [], "current_records": {}, "saved_work": []},
        "interpretation": {},
        "interpretation_origin": "No earlier interpretation is supplied; isolated research-plan evaluation",
        "expected_before_run": ["Preserve two independent disputes and the separate questions request",
            "Temporary restriction is not a final finding; alleged tampering remains denied",
            "Unprovided record and agreement do not establish nonexistence or inspected terms",
            "Original relevant words precede distinct conditional legal concepts; no external contact"]})
    first = original("v3-holdout-b1", (
        "Synthetic matter: a museum trustee told us that an independent conservator may have moved a loaned "
        "sculpture to off-site storage. The museum says it has not authorised the move, but has not yet checked "
        "the loan agreement. We do not know who currently holds it. Leave legal research paused until I ask. "
        "For now, prepare only a factual summary."
    ))
    mistaken = original("v3-holdout-b1", (
        "The museum moved the sculpture off-site without the owner's permission."
    ), speaker="nm", role="nm_interpretation")
    latest = original("v3-holdout-b2", (
        "Please correct that summary: the trustee only reported that the independent conservator may have "
        "moved it. We still do not know who has the sculpture, and the museum has not checked the agreement. "
        "Keep the research paused. Only provide the corrected factual summary; do not contact anyone."
    ))
    rows.append({"name": "holdout_correct_reported_actor_without_research",
        "origin": "New synthetic follow-up holdout with an explicitly erroneous NM interpretation",
        "context": {"position": "follow_up", "latest": latest, "conversation": [first, mistaken],
                    "current_records": {}, "saved_work": []},
        "interpretation": {},
        "interpretation_origin": "No earlier interpretation is supplied; isolated research-plan evaluation",
        "expected_before_run": ["Plan the summary correction without any legal enquiries",
            "Original reported conservator possibility remains distinct from NM's incorrect museum assertion",
            "Possession, authorisation and agreement terms remain unresolved; research stays paused"]})
    assert len(rows) == MAX_CALLS
    return rows


class Prepared(Exception):
    pass


def port_wire(prompt, schema, tier, max_tokens):
    return {"system": prompt.system, "user": prompt.user, "operation": prompt.operation,
            "schema": deepcopy(schema), "tier": tier.value, "max_tokens": max_tokens}


def sdk_request(wire):
    return {"model": MODEL, "messages": [{"role": "system", "content": wire["system"]},
            {"role": "user", "content": wire["user"]}], "store": False,
            "max_completion_tokens": wire["max_tokens"],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "nm_result", "strict": True, "schema": on_the_wire(wire["schema"])}}}


def request_bound(wire):
    size = len(json.dumps(sdk_request(wire), ensure_ascii=False).encode("utf-8"))
    incoming = 2 * size + 8192
    price_in, price_out = (Decimal(str(x)) for x in PRICES[MODEL])
    charge = int((incoming * price_in + wire["max_tokens"] * price_out).to_integral_value(rounding=ROUND_CEILING))
    return {"serialized_sdk_bytes": size, "input_planning_tokens": incoming,
            "output_hard_cap": wire["max_tokens"], "next_request_micro_usd": charge}


class CapturePort:
    def __init__(self, actual=None, expected=None, row=None):
        self.actual, self.expected, self.row, self.wire = actual, expected, row, None

    def context_budget(self, tier):
        return self.actual.context_budget(tier) if self.actual else CONTEXT_BUDGET[tier]

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        assert self.wire is None, "Only one planning call is authorised per case"
        self.wire = port_wire(prompt, schema, tier, max_tokens)
        if self.actual is None:
            raise Prepared()
        assert self.wire == self.expected, "Production prompt changed after preparation"
        self.row["model_port_request"] = deepcopy(self.wire)
        def capture_result(result):
            self.row["response"] = {"data": deepcopy(result.data), "model": result.model,
                "usage": asdict(result.usage), "latency_ms": result.latency_ms,
                "retries": result.retries, "completion": result.completion.value}
            assert result.model == MODEL and result.retries == 0

        try:
            result = self.actual.structured(prompt, schema, tier, max_tokens=max_tokens)
        except SchemaViolation as exc:
            if exc.rejected_result is not None:
                capture_result(exc.rejected_result)
                self.row["adapter_shape_rejection"] = str(exc)
            # Actual research.plan owns per-unit admission of completed quarantined
            # output. The harness neither salvages nor substitutes its result.
            raise
        capture_result(result)
        return result


def prepare():
    rows = cases()
    for row in rows:
        capture = CapturePort()
        try:
            research.plan(capture, deepcopy(row["context"]), deepcopy(row["interpretation"]))
        except Prepared:
            pass
        else:
            raise AssertionError("Production planner did not reach the capture boundary")
        row["wire"] = capture.wire
        payload = json.loads(row["wire"]["user"])
        assert payload["original_context"] == row["context"]
        assert payload["interpretation_proposal"] == row["interpretation"]
        assert row["wire"]["schema"] == research.SCHEMA
        row["request_bound"] = request_bound(row["wire"])
        assert row["request_bound"]["next_request_micro_usd"] <= PER_CALL_CAP_MICRO
    manifest = {"contract": "actual_research_v3_live_check_v1", "research_contract": research.CONTRACT,
        "script_sha256": sha(Path(__file__)), "production_research_sha256": sha(Path(research.__file__)),
        "frozen_inputs_sha256": sha(BASE), "earlier_inputs_sha256": sha(EARLIER),
        "model": MODEL, "maximum_calls": MAX_CALLS, "transport_retries": 0,
        "shared_ledger": "api-budget.sqlite", "shared_cap_usd": 5,
        "slice_cap_usd": SLICE_CAP_MICRO / 1_000_000,
        "per_call_planning_cap_usd": PER_CALL_CAP_MICRO / 1_000_000,
        "bound_note": "Twice complete SDK JSON UTF-8 bytes plus 8192 input tokens, uncached configured prices and production output cap. This is an engineering planning envelope; SessionCallBudget separately reserves the full verified model input ceiling before every dispatch.",
        "scope": "Actual research.plan only, with full original context and recorded interpretation where available; no synthetic success output, artificial source bank, retrieval, answer generation, save, or browser acceptance.",
        "offline_checks": {"actual_production_prompt_capture": True, "complete_context_unchanged": True,
            "case_count": len(rows), "new_holdouts": 2, "sdk_dispatches": 0}}
    return manifest, rows


class SDKCapture:
    def __init__(self, actual, budget, starting_charge):
        self.actual, self.budget, self.starting_charge = actual, budget, starting_charge
        self.chat = SimpleNamespace(completions=self)
        self.dispatches = 0
        self.row = self.wire = None
        self.reservation_attempted = False

    def arm(self, wire, row):
        charge = Decimal(str(self.budget.status()["charged_usd"]))
        delta = int((charge - self.starting_charge) * 1_000_000)
        bound = request_bound(wire)["next_request_micro_usd"]
        assert self.dispatches < MAX_CALLS and bound <= PER_CALL_CAP_MICRO
        assert delta + bound <= SLICE_CAP_MICRO, "Next request exceeds bounded slice allowance"
        self.wire, self.row, self.reservation_attempted = deepcopy(wire), row, False
        row["pre_reservation_charged_usd"] = float(charge)

    def before_dispatch(self):
        assert self.row is not None and not self.reservation_attempted, "No transport retry authorised"
        self.reservation_attempted = True

    def create(self, **kwargs):
        assert self.reservation_attempted and self.dispatches < MAX_CALLS
        assert not self.row.get("sdk_create_requests"), "No second SDK dispatch authorised"
        assert kwargs == sdk_request(self.wire), "SDK payload differs from captured production request"
        self.row["sdk_create_requests"] = [deepcopy(kwargs)]
        self.dispatches += 1
        try:
            raw = self.actual.chat.completions.create(**kwargs)
        except Exception as exc:
            self.row["provider_error_type"] = type(exc).__name__
            # Plain ModelError is not retryable: even a provider 429 stops this experiment.
            raise ModelError("Provider dispatch failed; no retry is authorised") from exc
        self.row["provider_response"] = raw.model_dump(mode="json")
        return raw


def run(manifest, rows):
    assert not list(OUT.glob(f"{PREFIX}-case-*.json")), "Prior case evidence exists"
    assert not (OUT / f"{PREFIX}-results.json").exists(), "Prior result exists"
    save_once("started", {"started_utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest})
    save_once("inputs", {"manifest": manifest, "cases": rows})
    from nm.shared.model_call_budget import SessionCallBudget
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    load_dotenv(ROOT / ".env")
    config = load()
    cfg = config.for_tier(Tier.ROUTINE)
    assert cfg.provider == "openai" and cfg.model == MODEL
    assert cfg.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(MODEL,))
    before = budget.status()
    underlying = OpenAIModelAdapter(config, call_budget=budget)
    sdk = SDKCapture(underlying._client, budget, Decimal(str(before["charged_usd"])))
    adapter = OpenAIModelAdapter(config, client=sdk, call_budget=budget).for_matter_text(sdk.before_dispatch)
    output = {"manifest": manifest, "budget_before": before, "calls": []}
    for number, case in enumerate(rows, 1):
        row = {"name": case["name"], "request_bound": case["request_bound"]}
        output["calls"].append(row)
        try:
            assert sha(Path(__file__)) == manifest["script_sha256"]
            assert sha(Path(research.__file__)) == manifest["production_research_sha256"]
            assert sha(BASE) == manifest["frozen_inputs_sha256"]
            assert sha(EARLIER) == manifest["earlier_inputs_sha256"]
            sdk.arm(case["wire"], row)
            port = CapturePort(adapter, case["wire"], row)
            row["admitted_plan"] = research.plan(port, deepcopy(case["context"]), deepcopy(case["interpretation"]))
            row["constructed_queries"] = {work["id"]: research.search_queries(work) for work in row["admitted_plan"]["work"]}
            after = budget.status()
            assert after["reserved_or_unknown_usd"] == before["reserved_or_unknown_usd"], "Unknown usage remains; stop"
            usage = row["response"]["usage"]
            measured = Decimal(usage["tokens_in"]) * Decimal(str(PRICES[MODEL][0])) + Decimal(usage["tokens_out"]) * Decimal(str(PRICES[MODEL][1]))
            assert measured <= case["request_bound"]["next_request_micro_usd"], "Measured usage exceeds planning bound"
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc) if not row.get("provider_error_type") else "Provider dispatch failed; see provider_error_type"
            if getattr(exc, "usage", None) is not None:
                row["error_usage"] = asdict(exc.usage)
            output["stopped_reason"] = "Stop after error or unknown outcome; no retry"
        row["budget_after"] = budget.status()
        row["actual_sdk_dispatches_total"] = sdk.dispatches
        save_once(f"case-{number:02d}", row)
        print(json.dumps({"case": case["name"], "dispatches": sdk.dispatches,
                          "error_type": row.get("error_type"), "budget": row["budget_after"]}), flush=True)
        if row.get("error_type"):
            break
    output["budget_after"] = budget.status()
    output["actual_sdk_dispatches"] = sdk.dispatches
    output["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save_once("results", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved", action="store_true", help="Dispatch paid calls only after parent review")
    args = parser.parse_args()
    prepared, prepared_rows = prepare()
    if args.run_approved:
        run(prepared, prepared_rows)
    else:
        print(json.dumps({"prepared_in_memory": True, "checks": prepared["offline_checks"],
            "research_contract": prepared["research_contract"],
            "maximum_calls": MAX_CALLS, "slice_cap_usd": prepared["slice_cap_usd"],
            "next_call_bounds_usd": [row["request_bound"]["next_request_micro_usd"] / 1_000_000 for row in prepared_rows]}))
