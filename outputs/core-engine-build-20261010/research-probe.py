"""Four unfamiliar synthetic research-planning probes; shared USD5 ledger.

Owner-approved slice allowance: up to USD0.08, four logical calls, no repairs.
Production prompt/schema/output ceiling are used unchanged. No corpus search runs.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import evaluate_understanding_five as common

from nm.core_engine import research
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier

OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "research-probe.json"


def interpretation(context, meaning, work="research"):
    """An explicitly unadmitted stage proposal, including deliberate omissions."""
    return {"contract": "core_understanding_v2", "status": "proposed",
            "semantic_review": "pending", "issues": [], "units": [{
                "id": context["latest"]["turn_id"] + ":u1",
                "kind": "request" if work else "courtesy",
                "source": deepcopy(context["latest"]), "context": [],
                "meaning": meaning, "requested_work": work,
                "desired_result": meaning if work else None, "unresolved": []}]}


CASES = [
    common.case("deposit_and_drive",
        "Hello. We act for Vale Makers, based in Hyderabad. They leased a laser cutter "
        "and returned it on 3 September. The lessor is retaining the deposit, alleging "
        "damage; our client disputes causing it, and no joint inspection report has "
        "been supplied. Separately, the lessor's technician still has the client's "
        "design drive, which the client says was loaned only for setup. Identify legal "
        "routes for recovery of the deposit and return of the drive, and separately "
        "draft a short list of questions for our client. Do not send anything or treat "
        "the damage allegation as admitted.", {
            "independent_results": ["Legal routes to recover deposit", "Legal routes to recover drive", "Draft client questions"],
            "qualifications": ["Damage is alleged and disputed", "Joint inspection report absent", "Drive purpose is client-reported"],
            "restrictions": ["Do not send anything", "No admission of damage"],
            "discovery_distinctions": ["Contractual basis/limits of deposit retention versus proof of alleged damage", "Possession and conditional retention/return of loaned property", "Useful remedies/procedure or adverse bases, only conditionally"],
            "forbidden": ["Merge away independently requested results", "Assume the alleged damage is proved", "Invent legal citations or exact provisions"]}),
    common.case("permission_followup",
        "Before returning to the passage issue, give me a short explanation of interim "
        "relief. Then resume the work on whether use can continue after the permission "
        "ends, keeping the ownership question open. The plan is still unavailable. "
        "Do not draft a notice yet.", {
            "independent_results": ["Explain interim relief", "Examine continued passage use after permission ends"],
            "qualifications": ["Ownership unsettled", "Neighbour claims independent right and client denies it", "No judicial determination", "Deed plan unavailable", "Permission end date from prior account"],
            "restrictions": ["Do not draft notice", "Do not equate permission with settled ownership"],
            "forbidden": ["Treat earlier NM ownership interpretation as proof", "Abandon passage work due to diversion", "Pretend missing deed plan is available"]},
        history=[common.source("p1", "advocate", "In a Hyderabad matter, our client granted a neighbour written permission to use a passage until 30 June. We have the permission letter, but not the deed plan. Do not assume ownership of the passage is settled."),
                 common.source("p1", "nm", "We can compare withdrawal of permission with any claimed independent access right when the deed plan is supplied."),
                 common.source("p2", "advocate", "The neighbour claims an access right independent of permission; we deny that, but no court has decided it."),
                 common.source("p2", "nm", "The deed plan is still missing and no ownership determination has been made.")],
        records={"ownership": {"state": "disputed"}},
        work=[{"id": "passage-review", "status": "waiting_for_deed_plan", "purpose": "Examine continuing passage use"}]),
    common.case("social_closing",
        "Thanks, this is enough for today. Good night.", {
            "independent_results": [], "expected_work": [],
            "forbidden": ["Resume pending legal work despite social closure", "Invent a legal task or record update"]},
        history=[common.source("s1", "advocate", "When I return with the tenancy papers, we can look at the rent demand."),
                 common.source("s1", "nm", "The papers have not been provided; that work remains pending.")],
        work=[{"id": "rent-review", "status": "waiting_for_documents"}]),
    common.case("opponent_allegation",
        "Opposing counsel's letter says, 'Your client concealed defects and must pay "
        "our inspection costs.' Our client denies prior knowledge of defects; I have "
        "not yet reviewed the sale agreement. Explain what questions in law would "
        "matter to that allegation and list what we need to check in the agreement. "
        "This is an allegation to examine, not an admission or authority to pay.", {
            "independent_results": ["Explain legal questions relevant to opposing allegation", "List agreement checks"],
            "qualifications": ["Concealment is opposing allegation", "Client denies knowledge", "Sale agreement unreviewed", "No asset type or transaction terms supplied"],
            "restrictions": ["No admission", "No authority to pay"],
            "discovery_distinctions": ["Whether a duty of disclosure/knowledge requirement applies", "Relevance of agreement terms and allocation of risk", "Conditional entitlement to claimed inspection costs and contrary positions"],
            "forbidden": ["Admit concealment", "Assume seller/buyer roles or asset type without qualification", "Invent contract terms, legal citations or exact provisions"]}),
]

# Deliberately incomplete/overstated proposals test whether original context owns
# planning. These are evaluation input, not model-generated or admitted evidence.
PROPOSAL_MEANINGS = [
    ("Research the deposit dispute only.", "research"),
    ("Recover our client's owned passage.", "research"),
    ("A social closing for today.", None),
    ("The client concealed defects; research inspection costs.", "research"),
]


def main():
    if EVIDENCE.exists():
        raise SystemExit("Research evidence exists; refusing an accidental second run.")
    load_dotenv(common.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == common.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(common.MODEL,))
    model = common.RecordedModel(OpenAIModelAdapter(config, call_budget=budget))
    source_path = common.ROOT / "nm/core_engine/research.py"
    before = budget.status()
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(), "model": common.MODEL,
                "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "slice_allowance_usd": 0.08, "budget_before": before,
                "production_output_ceiling": research.MAX_OUTPUT, "cases": []}
    for item, (meaning, work_kind) in zip(CASES, PROPOSAL_MEANINGS, strict=True):
        assert len(model.calls) < 4
        if budget.status()["charged_usd"] - before["charged_usd"] >= 0.08:
            raise SystemExit("Probe allowance reached; no further call authorised.")
        row = deepcopy(item)
        proposal = interpretation(item["context"], meaning, work_kind)
        row["interpretation_proposal"] = proposal
        call_start = len(model.calls)
        try:
            row["accepted_plan"] = research.plan(model, item["context"], proposal)
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        row["calls"] = deepcopy(model.calls[call_start:])
        evidence["cases"].append(row)
        evidence["logical_calls"] = len(model.calls)
        evidence["budget_after"] = budget.status()
        evidence["source_sha256_after"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        plan = row.get("accepted_plan", {})
        print(json.dumps({"case": item["name"], "work_items": len(plan.get("work", [])),
                          "enquiries": sum(len(w["enquiries"]) for w in plan.get("work", [])),
                          "issues": plan.get("issues", []), "error": row.get("error_type")}), flush=True)
    print(json.dumps({"calls": len(model.calls), "budget": budget.status()}), flush=True)


if __name__ == "__main__":
    main()
