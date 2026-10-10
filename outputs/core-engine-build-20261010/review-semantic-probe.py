"""Eight bounded actual-reviewer calls on explicitly synthetic paired evidence.

Only this output directory is written. No production prompt change, no browser,
no real corpus relevance claim, no provider-output salvage or correction calls.
All charges use the existing shared USD5 session ledger. --prepare is free.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from nm.core_engine import answer_sources, research, response_review, response_writer
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Tier

OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "review-semantic-probe.json"
PREPARED = OUT / "review-semantic-probe-prepared.json"
MODEL = "gpt-4.1-mini-2025-04-14"
FILES = ["nm/core_engine/response_review.py", "nm/core_engine/response_writer.py",
         "nm/core_engine/answer_sources.py", "nm/core_engine/research.py",
         "nm/core_engine/retrieval.py"]


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def source(turn, text):
    return {"source_id": turn + ":advocate", "turn_id": turn, "speaker": "advocate",
            "record_role": "original_account", "text": text}


class SyntheticCollection:
    """Exact artificial sources; ranking is a fixture, not measured retrieval."""
    def __init__(self, kind, texts=()):
        self.kind = kind
        self.rows = {i: {"chunk_id": "synthetic:" + str(i), "full_text": text,
            **({"case_id": "synthetic-case", "case_name": "Synthetic training judgment",
                "paragraph_num": str(i + 1), "atom_type": "unassessed"}
               if kind == "judgment" else {"act_id": "synthetic-act",
                "act_name": "Synthetic training Act", "section_number": str(i + 1)})}
            for i, text in enumerate(texts)}
    def revision(self): return "explicitly-synthetic-review-fixture-v1"
    def lexical(self, query, depth): return list(self.rows)
    def semantic(self, query, depth): return list(self.rows)
    def read(self, positions): return {p: deepcopy(self.rows[p]) for p in positions}
    def rerank(self, pairs): return [1.0] * len(pairs)
    def context(self, position, row):
        return {"scope": "adjacent_indexed_segments", "bounded": False,
                "unread_positions": [], "segments": [
                    {"position": p, "row": deepcopy(r)} for p, r in self.rows.items()]}


def setup(name, message, *, earlier=None, legal=(), needs_search=True):
    ctx = {"position": "follow_up" if earlier else "first",
           "conversation": [source(name + "-earlier", earlier)] if earlier else [],
           "latest": source(name, message), "current_records": {}, "saved_work": []}
    refs = [{"source_id": ctx["latest"]["source_id"], "quote": message}]
    if earlier: refs.append({"source_id": ctx["conversation"][0]["source_id"], "quote": earlier})
    plan = research.accept({"work": [{"purpose": message, "outcome": message,
        "sources": refs, "constraints": [], "unresolved": [],
        "enquiries": [{"text": message, "purpose": "Find sources for the requested legal explanation",
                       "basis": "conditional"}] if needs_search else []}]}, ctx)
    record = research.retrieve(plan, HybridSearcher({
        "provision": SyntheticCollection("provision"),
        "judgment": SyntheticCollection("judgment", legal)}), ctx)
    return ctx, record, answer_sources.build(ctx, record)


def ref(row, quote=None):
    return {"source_id": row["id"], "quote": quote or row["text"]}


def use(row, role, *, speaker=None, treatment="not_applicable", treatment_source=None, quote=None):
    return {**ref(row, quote), "role": role, "speaker": speaker, "treatment": treatment,
            "treatment_source": ref(treatment_source) if treatment_source else None}


def unit(ctx, text, uses, kind="account", address=None):
    return {"kind": kind, "text": text, "uses": uses,
            "addresses": [{"source_id": ctx["latest"]["source_id"],
                           "quote": address or ctx["latest"]["text"]}]}


def pair(name, setup_result, faulty, correct, defect, legitimate):
    ctx, record, catalogue = setup_result
    result = []
    for variant, expected, units, rationale in [
        ("planted_error", False, faulty, defect), ("legitimate_neighbor", True, correct, legitimate)]:
        draft = response_writer.accept({"units": units}, ctx, catalogue)
        response_writer.validate(draft, ctx, catalogue)
        result.append({"pair": name, "variant": variant, "expected_acceptance_before_run": expected,
            "independent_rationale_before_run": rationale,
            "evidence_kind": "Explicitly synthetic controlled source and matter fixture",
            "context": ctx, "research_record": record, "sources": catalogue,
            "draft": draft, "execution": None})
    return result


def cases():
    rows = []
    setup_result = setup("submission", "Explain the defendant's submission and what the court decided about it.", legal=[
        "Counsel for the defendant submitted that the payment claim was barred because notice arrived after 30 days.",
        "The Court rejected that submission. The agreement imposed no 30-day notice requirement, so the claim was not barred on that ground. The merits of the payment claim remain to be tried."])
    ctx, _, sources = setup_result
    legal = sorted([s for s in sources.values() if s["kind"] == "judgment"],
                   key=lambda s: s["source_identity"]["position"])
    argument, decision = legal
    bad = [unit(ctx, "The court held that the payment claim was barred because notice arrived after 30 days.",
                [use(argument, "court_reasoning", speaker="Court")], "law")]
    good = [unit(ctx, "The defendant argued that notice after 30 days barred the payment claim. The court rejected that argument because the agreement contained no such notice requirement; the payment claim's merits remained to be tried.",
                 [use(argument, "party_submission", speaker="Defendant's counsel", treatment="rejected", treatment_source=decision),
                  use(decision, "court_disposition", speaker="Court")], "law")]
    rows += pair("party_submission_and_rejection", setup_result, bad, good,
        "The draft attributes a rejected party submission to the court and reverses the disposition.",
        "The draft attributes the submission, preserves the court's exact rejection and does not decide the unresolved merits.")

    setup_result = setup("absence", "Summarise the present position about the inspection report, preserving what is unknown.",
        earlier="No inspection report has been supplied to us. We do not know whether the lessor has one.", needs_search=False)
    ctx, _, sources = setup_result
    account = sources[ctx["conversation"][0]["source_id"]]
    bad = [unit(ctx, "There is no inspection report; none exists.", [use(account, "original_account", speaker="Advocate")])]
    good = [unit(ctx, "You report that no inspection report has been supplied to you. Whether the lessor has one remains unknown.",
                 [use(account, "original_account", speaker="Advocate")])]
    rows += pair("not_supplied_vs_nonexistence", setup_result, bad, good,
        "A failure to supply a report and explicit uncertainty do not establish that no report exists.",
        "The attributed summary retains both non-supply and explicit uncertainty without demanding new work.")

    setup_result = setup("contract", "Explain the quoted contract term in this judgment and whether the passage establishes a rule for all leases.", legal=[
        "The parties' lease contained clause 8: 'If the deposit is not repaid on handover, the tenant may remain without rent until repayment.' This clause is a term of the agreement before us. No general statutory entitlement to rent-free occupation is decided in this order."])
    ctx, _, sources = setup_result
    contract = next(s for s in sources.values() if s["kind"] == "judgment")
    bad = [unit(ctx, "The law entitles every tenant to remain rent-free until the deposit is returned, regardless of the lease terms.",
                [use(contract, "court_reasoning", speaker="Court")], "law")]
    good = [unit(ctx, "Clause 8 of the lease quoted in this judgment allowed that tenant to remain without rent if the deposit was not repaid on handover, until repayment. The passage treats this as a term of that agreement and expressly leaves any general statutory entitlement undecided; it does not establish the same right for all leases.",
                 [use(contract, "contract", speaker="Quoted lease", quote="If the deposit is not repaid on handover, the tenant may remain without rent until repayment."),
                  use(contract, "court_reasoning", speaker="Court", quote="This clause is a term of the agreement before us. No general statutory entitlement to rent-free occupation is decided in this order.")], "law")]
    rows += pair("contract_term_vs_universal_law", setup_result, bad, good,
        "A private term with an express reservation cannot establish a universal legal right.",
        "The explanation preserves the handover condition, repayment endpoint, private scope and express statutory reservation.")

    setup_result = setup("independent_asks", "Summarise our reported payment dates. Separately, tell us the statutory filing deadline using the retrieved sources.",
        earlier="Our client reports paying the first instalment on 4 July and the balance on 9 July. The receipts have not been supplied.", legal=[])
    ctx, _, sources = setup_result
    account = sources[ctx["conversation"][0]["source_id"]]
    summary = unit(ctx, "Your client reports paying the first instalment on 4 July and the balance on 9 July; receipts have not been supplied.",
                   [use(account, "original_account", speaker="Advocate reporting client")],
                   address="Summarise our reported payment dates.")
    limitation = unit(ctx, "No statute or judgment on a filing deadline is available in the supplied source catalogue, so this record does not support stating the applicable statutory deadline.", [],
                      "limitation", address="Separately, tell us the statutory filing deadline using the retrieved sources.")
    rows += pair("independent_ask_coverage", setup_result, [summary], [summary, limitation],
        "The draft ignores the independently requested statutory deadline despite the original request remaining available.",
        "The answer delivers the supported attributed summary and expressly limits only the unsupported deadline, without inventing law or implying no deadline exists.")
    return rows


class RecordedModel:
    def __init__(self, adapter):
        self.adapter, self.calls, self.dispatches = adapter, [], 0
        self.cost, self.current_dispatched = 0.0, False
    def before_dispatch(self):
        if self.dispatches >= 8 or self.cost >= 0.15 or self.current_dispatched:
            raise RuntimeError("Probe bound reached; transport retry not permitted")
        self.dispatches += 1
        self.current_dispatched = True
    def context_budget(self, tier): return self.adapter.context_budget(tier)
    def structured(self, prompt, schema, tier, **kwargs):
        assert tier is Tier.ROUTINE and prompt.operation == "core_response_review"
        assert len(self.calls) < 8 and self.cost < 0.15
        self.current_dispatched = False
        call = {"system": prompt.system, "user": prompt.user, "schema": deepcopy(schema),
                "kwargs": kwargs, "operation": prompt.operation}
        self.calls.append(call)
        start = time.perf_counter()
        try:
            result = self.adapter.structured(prompt, schema, tier, **kwargs)
            call["result"] = {"data": deepcopy(result.data), "model": result.model,
                "usage": asdict(result.usage), "latency_ms": result.latency_ms,
                "retries": result.retries, "completion": result.completion.value}
            self.cost += result.usage.cost_usd
            return result
        except Exception as exc:
            call["error_type"] = type(exc).__name__
            usage = getattr(exc, "usage", None)
            if usage:
                call["usage"] = asdict(usage)
                self.cost += usage.cost_usd
            # Store quarantined completed output as diagnostic only; never admit it.
            rejected = getattr(exc, "rejected_result", None)
            if rejected:
                call["rejected_result_diagnostic_only"] = {
                    "data": deepcopy(rejected.data), "completion": rejected.completion.value}
            raise
        finally:
            call["elapsed_seconds"] = time.perf_counter() - start


def main():
    prepared = cases()
    if "--prepare" in sys.argv:
        PREPARED.write_text(json.dumps({"source_hashes": hashes(), "cases": prepared},
                                     indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"prepared": len(prepared), "paid_calls": 0}))
        return
    if "--run" not in sys.argv or EVIDENCE.exists():
        raise SystemExit("Use --run once; existing evidence prevents accidental duplicate spending.")
    load_dotenv(ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(MODEL,))
    model = RecordedModel(OpenAIModelAdapter(config, call_budget=budget))
    model.adapter = model.adapter.for_matter_text(model.before_dispatch)
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL,
        "scope": "Eight controlled synthetic semantic-review probes; not corpus accuracy or browser acceptance",
        "normal_pipeline_call_impact": 0, "probe_maximum_reviewer_calls": 8,
        "probe_cost_stop_usd": 0.15, "shared_ledger": str(budget.path),
        "source_hashes_at_start": hashes(), "budget_before": budget.status(), "cases": []}
    for item in prepared:
        if model.cost >= 0.15 or model.dispatches >= 8: break
        row = deepcopy(item)
        before = len(model.calls)
        try:
            row["review"] = response_review.review(model, item["context"], item["research_record"],
                item["sources"], item["draft"], item["execution"])
            response_review.validate(row["review"], item["context"], item["research_record"],
                item["sources"], item["draft"], item["execution"])
            accepted, expected = row["review"]["accepted"], item["expected_acceptance_before_run"]
            row["assessment"] = ("correct_acceptance" if accepted else "correct_rejection") if accepted == expected else (
                "wrong_acceptance" if accepted else "false_rejection")
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["assessment"] = "terminal_or_shape_failure_not_semantic_verdict"
        row["calls"] = deepcopy(model.calls[before:])
        evidence["cases"].append(row)
        evidence.update(budget_after=budget.status(), logical_reviewer_calls=len(model.calls),
            provider_dispatches=model.dispatches, probe_measured_usage_cost_usd=model.cost,
            source_hashes_at_finish=hashes())
        evidence["counts"] = {label: sum(r["assessment"] == label for r in evidence["cases"])
            for label in ["correct_acceptance", "correct_rejection", "wrong_acceptance", "false_rejection",
                          "terminal_or_shape_failure_not_semantic_verdict"]}
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pair": item["pair"], "variant": item["variant"],
            "assessment": row["assessment"], "cost_so_far": model.cost,
            "dispatches": model.dispatches}), flush=True)
        if any("error_type" in call for call in row["calls"]): break
    print(json.dumps({"counts": evidence["counts"], "cost_usd": model.cost,
                      "dispatches": model.dispatches}), flush=True)


if __name__ == "__main__": main()
