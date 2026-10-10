"""Unrun model-only GPT-4.1 comparison of the six frozen synthetic mini requests.

Default is offline preparation. --run-approved still requires parent dispatch approval.
No production configuration is changed. No retries, repair or truncated-output salvage.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))
BASE_PATH = OUT / "research-only-concepts-executed-pilot.py"
spec = importlib.util.spec_from_file_location("frozen_research_pilot", BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

MODEL = "gpt-4.1-2025-04-14"
PRICES = ("2", "8")
MODEL_INPUT_CEILING = 1_047_576
MAX_OUTPUT = 4000
MAX_CALLS = 6
SLICE_CAP_MICRO = 100_000
FRAMING_MARGIN_TOKENS = 8192
SHARED_RESERVATION_MICRO = MODEL_INPUT_CEILING * 2 + MAX_OUTPUT * 8
BASELINE = OUT / "research-only-concepts-guard-fixed-results.json"
INPUTS = OUT / "research-only-concepts-inputs.json"
ORACLE = OUT / "research-only-concepts-hidden-oracle.json"
PREPARED = OUT / "research-only-concepts-gpt41-prepared.json"
RESULTS = OUT / "research-only-concepts-gpt41-results.json"
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_bound(request):
    """Slice planning bound; shared ledger separately reserves full model ceiling."""
    wire_bytes = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
    bound_input = 2 * wire_bytes + FRAMING_MARGIN_TOKENS
    return {"serialized_sdk_bytes": wire_bytes, "wire_byte_multiplier": 2,
            "framing_margin_tokens": FRAMING_MARGIN_TOKENS,
            "input_token_planning_bound": bound_input,
            "output_token_hard_cap": MAX_OUTPUT,
            "next_request_micro_usd": bound_input * 2 + MAX_OUTPUT * 8}


def requests():
    prior, cases = read(BASELINE), read(INPUTS)["cases"]
    assert len(prior["calls"]) == len(cases) == MAX_CALLS
    prepared = []
    for previous, case in zip(prior["calls"], cases, strict=True):
        assert previous["name"] == case["name"]
        assert len(previous["sdk_create_requests"]) == 1
        original = previous["sdk_create_requests"][0]
        assert original["model"] == "gpt-4.1-mini-2025-04-14"
        request = {**deepcopy(original), "model": MODEL}
        assert {k:v for k,v in request.items() if k != "model"} == {k:v for k,v in original.items() if k != "model"}
        assert request["max_completion_tokens"] == MAX_OUTPUT and request["store"] is False
        prepared.append({"name":case["name"], "request":request, "bound":request_bound(request),
                         "baseline_input_tokens":previous["response"]["usage"]["tokens_in"]})
    return prepared


def can_dispatch(spent_micro, bounds, dispatches):
    return dispatches < MAX_CALLS and spent_micro + bounds["next_request_micro_usd"] <= SLICE_CAP_MICRO


def prepare():
    rows = requests()
    assert can_dispatch(0, rows[0]["bound"], 0)
    assert not can_dispatch(SLICE_CAP_MICRO, rows[0]["bound"], 0)
    assert not can_dispatch(0, rows[0]["bound"], 6)
    for row in rows:
        assert row["bound"]["input_token_planning_bound"] > row["baseline_input_tokens"]
        worst = row["bound"]["next_request_micro_usd"]
        assert can_dispatch(SLICE_CAP_MICRO-worst, row["bound"], 0)
        assert not can_dispatch(SLICE_CAP_MICRO-worst+1, row["bound"], 0)
    manifest={"script_sha256":digest(Path(__file__)), "executed_baseline_script_sha256":digest(BASE_PATH),
              "baseline_results_sha256":digest(BASELINE), "inputs_sha256":digest(INPUTS), "oracle_sha256":digest(ORACLE),
              "model":MODEL, "only_request_change":"model", "maximum_actual_sdk_dispatches":MAX_CALLS,
              "provider_retries":0, "slice_cap_usd":0.10, "maximum_output_tokens":MAX_OUTPUT,
              "verified_price_per_million":PRICES, "pricing_source":PRICING_SOURCE,
              "pricing_verified_date":"2026-10-10", "shared_ledger":"api-budget.sqlite", "shared_cap_usd":5,
              "shared_reservation_micro_usd_each":SHARED_RESERVATION_MICRO,
              "slice_bound_description":"Twice the UTF-8 byte count of complete SDK JSON plus 8192 framing/schema tokens, charged as uncached input, plus hard 4000-token output maximum. This conservative exact-wire planning bound is not a provider-certified token ceiling; the existing shared ledger separately retains its full published model-ceiling reservation. Stop before any next request whose planning bound plus measured-or-unknown prior comparison charges exceeds $0.10. Stop after any unknown/error outcome.",
              "payload_provenance":"Same six synthetic original_context hashes established in research-only-concepts-egress-provenance.json; requests copied from captured mini SDK arguments, with model alone changed.",
              "cases":[{"name":r["name"],"sdk_request_sha256":hashlib.sha256(json.dumps(r["request"],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),"bound":r["bound"],"prior_input_tokens":r["baseline_input_tokens"]} for r in rows],
              "offline_checks":{"exact_nonmodel_sdk_fields_unchanged":True,"six_frozen_contexts":True,"next_request_cost_guard_boundary_pairs":True,"maximum_six_dispatches":True,"paid_calls":0}}
    base.write_once(PREPARED, manifest)
    return manifest


def invalid_constant(value):
    raise ValueError("Nonfinite JSON is not admitted")


def unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError("Duplicate output object key")
        result[key]=value
    return result


def run(manifest):
    assert not RESULTS.exists(), "Refuse a second comparison run"
    from openai import OpenAI
    from nm.shared.model_call_budget import CallBudget
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_port import Tier
    load_dotenv(ROOT / ".env")
    cfg=load().for_tier(Tier.ROUTINE)
    assert cfg.provider == "openai"
    assert cfg.base_url in (None,"","https://api.openai.com/v1","https://api.openai.com/v1/")
    client=OpenAI(api_key=cfg.api_key,base_url=cfg.base_url or None,max_retries=0,timeout=60)
    budget=CallBudget(OUT/"api-budget.sqlite","5",model=MODEL,price_per_million=PRICES,
        reservation_micro_usd=SHARED_RESERVATION_MICRO,require_returned_model=True)
    output={"started_utc":datetime.now(timezone.utc).isoformat(),"preparation":manifest,
            "budget_before":budget.status(),"calls":[],"actual_sdk_dispatches":0,"comparison_measured_micro_usd":0,"comparison_charged_micro_usd":0}
    cases={row["name"]:row for row in read(INPUTS)["cases"]}
    for item in requests():
        assert digest(Path(__file__))==manifest["script_sha256"]
        assert digest(BASELINE)==manifest["baseline_results_sha256"] and digest(INPUTS)==manifest["inputs_sha256"]
        if not can_dispatch(output["comparison_charged_micro_usd"],item["bound"],output["actual_sdk_dispatches"]):
            output["stopped_reason"]="Next exact request planning bound exceeds remaining approved comparison spend"
            break
        row={"name":item["name"],"bound":item["bound"],"charged_before":budget.status(),"pre_dispatch_comparison_micro_usd":output["comparison_charged_micro_usd"]}
        output["calls"].append(row)
        token=None; started=time.perf_counter()
        try:
            token=budget.reserve(MODEL)
            row["reservation_id"]=token
            request=deepcopy(item["request"])
            assert request==item["request"]
            row["sdk_create_requests"]=[deepcopy(request)]
            output["actual_sdk_dispatches"]+=1
            raw=client.chat.completions.create(**request)
            row["provider_response"]=raw.model_dump(mode="json")
            budget.settle(token,raw)
            assert raw.model==MODEL,"Returned model identity differs"
            usage=raw.usage
            assert usage is not None and type(usage.prompt_tokens) is int and type(usage.completion_tokens) is int
            measured=int((Decimal(usage.prompt_tokens)*Decimal(PRICES[0])+Decimal(usage.completion_tokens)*Decimal(PRICES[1])).to_integral_value(rounding=ROUND_CEILING))
            row["measured_micro_usd"]=measured
            output["comparison_measured_micro_usd"]+=measured
            assert measured <= item["bound"]["next_request_micro_usd"],"Observed request exceeds slice planning bound"
            assert len(raw.choices)==1,"Ambiguous provider choices"
            choice=raw.choices[0]
            assert choice.finish_reason=="stop","Incomplete provider output"
            assert not choice.message.refusal and not choice.message.tool_calls,"Refused or unexpected provider output"
            data=json.loads(choice.message.content,object_pairs_hook=unique_pairs,parse_constant=invalid_constant)
            case=cases[item["name"]]
            row["mechanically_admitted"]=base.admit(data,case["context"],case["aliases"],case["wire"]["schema"])
            row["response_data"]=data
        except Exception as exc:
            row["error_type"],row["error"]=type(exc).__name__,str(exc)
            output["stopped_reason"]="Stop after error or unknown outcome; no retry or salvage"
        row["latency_ms"]=int((time.perf_counter()-started)*1000)
        output["budget_after"]=budget.status()
        output["comparison_charged_micro_usd"]=int((Decimal(str(output["budget_after"]["charged_usd"]))-Decimal(str(output["budget_before"]["charged_usd"])))*1_000_000)
        RESULTS.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"case":item["name"],"dispatches":output["actual_sdk_dispatches"],"measured_usd":output["comparison_measured_micro_usd"]/1_000_000,"error":row.get("error_type")}),flush=True)
        if row.get("error_type"): break
    output["budget_after"]=budget.status()
    output["finished_utc"]=datetime.now(timezone.utc).isoformat()
    RESULTS.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-approved",action="store_true")
    args=parser.parse_args()
    manifest=prepare()
    if args.run_approved: run(manifest)
    else: print(json.dumps({"prepared":PREPARED.name,"checks":manifest["offline_checks"],"bounds":[r["bound"]["next_request_micro_usd"]/1_000_000 for r in manifest["cases"]]}))
