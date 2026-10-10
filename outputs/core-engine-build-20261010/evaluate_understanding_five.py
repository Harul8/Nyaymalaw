"""Five synthetic interpretation probes; one shared approved USD5 ledger.

No production writes, private matter text, browser use or semantic repair calls.
Expected distinctions are written before calling the model. Assessment is manual.
"""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nm.core_engine import understanding
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier

OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "understanding-five-live.json"
MODEL = "gpt-4.1-mini-2025-04-14"


def source(turn, speaker, text):
    return {"source_id": f"{turn}:{speaker}", "turn_id": turn,
            "speaker": speaker, "record_role": "original_account"
            if speaker == "advocate" else "nm_interpretation", "text": text}


def case(name, message, expected, *, history=(), records=None, work=None):
    return {"name": name, "expected_before_run": expected, "context": {
        "position": "follow_up" if history else "first",
        "conversation": list(history), "latest": source(name, "advocate", message),
        "current_records": records or {}, "saved_work": work or []}}


CASES = [
    case("mixed", "Good morning. We act for Lumen Workshop. The customer says the equipment "
         "was never collected; our dispatch register records collection on 12 August. "
         "Summarise the conflicting accounts and draft questions for our client. "
         "Do not contact the customer.", {
             "courtesy": True, "information": "Client identity and conflicting attributed accounts",
             "independent_requests": ["Summarise conflicting accounts", "Draft questions for client"],
             "restriction": "No contact with the customer", "forbidden": "Treat collection as proved"}),
    case("quoted", "For the record, the seller emailed: 'Stop the repair and refund me today.' "
         "This is their demand, not an instruction from us.", {
             "information": "Seller's reported demand", "independent_requests": [],
             "forbidden": "Treat the quoted repair/refund demand as the advocate's request to NM"}),
    case("correction", "Please correct your summary: I said 14 April, not 14 May. "
         "The amount remains uncertain; do not enter a confirmed payment figure.", {
             "independent_requests": ["Correct NM's mistaken date in its summary"],
             "information": "Amount remains uncertain; original date remains 14 April",
             "restriction": "Do not enter a confirmed payment figure",
             "forbidden": "Claim the correction has been applied or invent a payment amount"},
         history=[source("c1", "advocate", "The payment was made on 14 April. The amount is not yet checked."),
                  source("c1", "nm", "The reported payment was made on 14 May; the amount is unconfirmed.")],
         records={"reported_payment_date": {"value": "14 May", "record_role": "nm_interpretation"}},
         work=[{"id": "summary-1", "status": "completed", "kind": "summary"}]),
    case("diversion", "Before we return to the lease review, explain what 'without prejudice' "
         "means in ordinary language. Then resume the comparison. Keep the draft unsent.", {
             "independent_requests": ["Explain without prejudice", "Resume existing lease comparison"],
             "restriction": "Keep draft unsent", "forbidden": "Abandon prior comparison or send draft"},
         history=[source("d1", "advocate", "Compare the two lease versions. Prepare an internal note only; do not send it."),
                  source("d1", "nm", "I can compare the versions once the second document is provided."),
                  source("d2", "advocate", "The second version is not available yet. We will return to this.")],
         work=[{"id": "lease-review", "kind": "comparison", "status": "waiting_for_second_document"}]),
    case("closing", "Hello again, and thank you. That's all for today.", {
             "courtesy": "Greeting, thanks and social closing", "independent_requests": [],
             "forbidden": "Invent a legal task or an instruction to change matter records"},
         history=[source("g1", "advocate", "I will bring the agreement tomorrow."),
                  source("g1", "nm", "Understood. We can continue when you have it.")]),
]


class RecordedModel:
    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def context_budget(self, tier):
        return self.inner.context_budget(tier)

    def structured(self, prompt, schema, tier, **kwargs):
        assert tier is Tier.ROUTINE
        assert len(self.calls) < 5
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
            # Do not write arbitrary provider exception text or environment data.
            record["error_type"] = type(exc).__name__
            usage = getattr(exc, "usage", None)
            if usage:
                record["usage"] = asdict(usage)
            raise


def main():
    if EVIDENCE.exists():
        raise SystemExit("Evidence already exists; refusing an accidental second evaluation.")
    load_dotenv(ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == MODEL, "Unexpected routine model pin"
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(MODEL,))
    model = RecordedModel(OpenAIModelAdapter(config, call_budget=budget))
    source_path = ROOT / "nm/core_engine/understanding.py"
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL,
                "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "budget_before": budget.status(), "cases": []}
    for item in CASES:
        row = deepcopy(item)
        before = len(model.calls)
        try:
            row["accepted"] = understanding.understand(model, item["context"])
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        row["calls"] = deepcopy(model.calls[before:])
        evidence["cases"].append(row)
        evidence["budget_after"] = budget.status()
        evidence["logical_calls"] = len(model.calls)
        evidence["source_sha256_after"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": item["name"], "status": row.get("accepted", {}).get("status"),
                          "units": len(row.get("accepted", {}).get("units", [])),
                          "issues": row.get("accepted", {}).get("issues", []),
                          "error": row.get("error_type")}), flush=True)
    print(json.dumps({"logical_calls": len(model.calls), "budget": budget.status()}), flush=True)


if __name__ == "__main__":
    main()
