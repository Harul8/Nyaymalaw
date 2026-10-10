"""One narrow prompt candidate, six synthetic planner calls, no retrieval/repair."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import evaluate_understanding_five as common
from nm.core_engine import research
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier

OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prior_planner_probe", OUT / "research-legal-need-six.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
PREPARED = OUT / "research-premise-fidelity-six-prepared.json"
EVIDENCE = OUT / "research-premise-fidelity-six.json"


def cases():
    previous, previous_hash = prior.read("research-legal-need-six.json")
    rows = []
    for name in ("capacity_deposit_drive", "deposit_and_drive"):
        old = next(row for row in previous["cases"] if row["name"] == name)
        rows.append({key: deepcopy(old[key]) for key in
                     ("name", "context", "interpretation_proposal", "expected_before_run")})
        rows[-1].update(baseline_plan=old["baseline_plan"],
                        unsuccessful_prior_candidate=old["accepted_plan"],
                        origin="Exact saved input with a historical baseline and failed sharing candidate")
    unfamiliar = common.case("authority_to_bind",
        "We act for Merin Diagnostics. A hospital owes fees for reported laboratory services. "
        "The hospital says a collection agency agreed on our client's behalf to extend payment by 90 days. "
        "Our client says the agency only collected specimens and denies authorising any change to payment terms. "
        "I have not examined the written service agreement. No email recording the extension has been forwarded to us. "
        "Identify the legal questions governing whether the agency could bind our client and whether the hospital "
        "could rely on that extension. Do not contact the hospital or agency.", {
            "requested_result": "Identify the legal questions about claimed authority and reliance on the alleged extension",
            "factual_premises": ["Hospital alleges extension by agency; client denies authority to alter terms",
                "Specimen collection role is client-reported", "Agreement is unexamined",
                "Extension email not forwarded, not proved nonexistent"],
            "allowed_conditional_legal_characterisations": ["Whether an agency or other binding-authority relationship exists",
                "Whether reliance on an alleged extension can affect payment rights"],
            "forbidden": ["Treat actual or apparent authority as established", "Swap hospital/agency/client conduct",
                "Treat unforwarded email as nonexistent", "Contact either counterparty"]})
    rows.append({**unfamiliar, "interpretation_proposal": {}, "baseline_plan": None,
                 "origin": "New synthetic relation; one observation, not a holdout accuracy estimate"})
    alternative = common.case("explicit_alternative",
        "For a separate alternative analysis only, assume the agency was expressly authorised to extend payment "
        "and that no email recording the extension was ever created. Identify how those assumed facts would change "
        "the legal questions. Keep both assumptions separate from our client's actual denial and from what we know "
        "about the unforwarded email. Do not change the matter record or contact anyone.", {
            "requested_result": "Plan the expressly requested alternative analysis",
            "allowed_hypothetical_premises": ["Agency expressly authorised", "No extension email ever created"],
            "factual_premises": ["Actual original account remains client's denial of authority",
                "Original email status remains unforwarded and existence unknown"],
            "forbidden": ["Reject or silently drop the authorised hypothetical because it differs from original account",
                "State either assumption as actual fact", "Change matter record", "Contact anyone"]},
        history=[deepcopy(unfamiliar["context"]["latest"])])
    rows.append({**alternative, "interpretation_proposal": {}, "baseline_plan": None,
                 "origin": "Legitimate hypothetical neighbour of new synthetic relation"})
    for name in ("date_correction", "social_closing"):
        old = next(row for row in previous["cases"] if row["name"] == name)
        rows.append({key: deepcopy(old[key]) for key in
                     ("name", "context", "interpretation_proposal", "expected_before_run")})
        rows[-1].update(baseline_plan=old["baseline_plan"],
                        unsuccessful_prior_candidate=old["accepted_plan"],
                        origin="Exact saved regression input; no new holdout claim")
    return rows, previous_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-after-prompt-freeze", action="store_true")
    args = parser.parse_args()
    sample, baseline_hash = cases()
    source = common.ROOT / "nm/core_engine/research.py"
    source_hash = prior.digest(source.read_bytes())
    manifest = {"model": common.MODEL, "source_sha256": source_hash,
        "prompt_sha256": prior.digest(research.SYSTEM.encode("utf-8")),
        "baseline_evidence": "research-legal-need-six.json", "baseline_sha256": baseline_hash,
        "maximum_logical_calls": 6, "semantic_retries": 0, "actual_spend_stop_usd": 0.08,
        "shared_ledger": "api-budget.sqlite", "shared_hard_cap_usd": 5,
        "scope": "Factual-premise fidelity only; no new sharing/dedup instructions or provider stages",
        "success_distinctions_before_run": [
            "Reported actor and conduct remain attributable to the correct party.",
            "Unseen/unforwarded evidence remains unknown, not nonexistent or reviewed.",
            "A conditional legal hypothesis does not license unmarked alternative facts.",
            "An expressly hypothetical factual alternative remains allowed and separate from actual account.",
            "All requested meanings and restrictions remain; factual correction requires no law search; social closure does not renew work.",
            "Successful shape/source checks do not certify these semantic judgments."],
        "cases": [{key: row[key] for key in ("name", "origin", "expected_before_run")}
                  for row in sample]}
    if not args.run_after_prompt_freeze:
        if PREPARED.exists():
            assert json.loads(PREPARED.read_text(encoding="utf-8")) == manifest
        else:
            PREPARED.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"prepared": PREPARED.name, "calls": 0, "cases": len(sample)}))
        return
    assert not EVIDENCE.exists(), "Existing evidence; refuse a second paid run."
    assert json.loads(PREPARED.read_text(encoding="utf-8")) == manifest
    load_dotenv(common.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == common.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(common.MODEL,))
    model = prior.RecordedModel(OpenAIModelAdapter(config, call_budget=budget).for_matter_text(lambda: None))
    before = budget.status()
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(), "preparation": manifest,
        "model": common.MODEL, "source_sha256": source_hash, "budget_before": before, "cases": []}
    for item in sample:
        if len(model.calls) >= 6 or budget.status()["charged_usd"] - before["charged_usd"] >= 0.08:
            evidence["stopped_reason"] = "Approved logical-call or actual-spend stop"
            break
        assert prior.digest(source.read_bytes()) == source_hash, "Planner changed during evaluation"
        row, start = deepcopy(item), len(model.calls)
        try:
            row["accepted_plan"] = research.plan(model, row["context"], row["interpretation_proposal"])
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        row["calls"] = deepcopy(model.calls[start:])
        evidence["cases"].append(row)
        evidence["logical_calls"] = len(model.calls)
        evidence["budget_after"] = budget.status()
        evidence["actual_cost_usd"] = evidence["budget_after"]["charged_usd"] - before["charged_usd"]
        evidence["source_sha256_after"] = prior.digest(source.read_bytes())
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": row["name"], "calls": len(row["calls"]),
            "error": row.get("error_type"), "cost_usd": evidence["actual_cost_usd"]}), flush=True)
    print(json.dumps({"logical_calls": len(model.calls), "actual_cost_usd": evidence.get("actual_cost_usd", 0),
                      "budget": budget.status()}), flush=True)


if __name__ == "__main__":
    main()
