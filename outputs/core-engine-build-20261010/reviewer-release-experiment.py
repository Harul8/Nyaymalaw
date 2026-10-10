"""Prepared reviewer-only comparison. Default is offline preparation, never dispatch.

Canonical synthetic evidence is retained. The expected judgments live in a separate
oracle that run() never opens. No writer, retrieval, repair or matter-save calls.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

import evaluate_understanding_five as common
from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.turn import execution_record
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Prompt, Tier, estimate_tokens

OUT = Path(__file__).resolve().parent
CASES = OUT / "reviewer-release-inputs-v2.json"
ORACLE = OUT / "reviewer-release-hidden-oracle-v2.json"
BASELINE = OUT / "reviewer-release-baseline.json"
RESULTS = OUT / "reviewer-release-results-v2.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def use(source_id, quote=None):
    return {"source_id": source_id, "quote": quote, "role": "original_account",
            "speaker": "advocate", "treatment": "not_applicable", "treatment_source": None}


def unit(context, kind, text, uses=()):
    return {"kind": kind, "text": text,
            "addresses": [{"source_id": context["latest"]["source_id"], "quote": None}],
            "uses": list(uses)}


def fixture(context, proposal, activity=None):
    if activity is None:
        plan = research.accept({"work": []}, context)
        record = research.retrieve(plan, None, context)
        sources = answer_sources.build(context, record)
        execution = execution_record(record)
    else:
        record, sources, execution = (deepcopy(activity[key]) for key in ("research", "sources", "execution"))
    draft = response_writer.accept(proposal, context, sources)
    authorities = response_authorities.check(context, record, sources, draft)
    return {"context": deepcopy(context), "research_record": record, "sources": sources,
            "draft": draft, "execution": execution, "authority_evidence": authorities}


def dependencies(arguments):
    return response_review._dependencies(arguments["context"], arguments["research_record"],
        arguments["sources"], arguments["draft"], arguments["execution"],
        authority_evidence=arguments["authority_evidence"], contract=response_review.CONTRACT)


def prepare():
    live = read(OUT / "live-served-capacity-remeasurement.json")
    first = live["turns"][0]["canonical_rows"][0]["activities"]
    second = live["turns"][1]["canonical_rows"][-1]["activities"]
    contexts = [json.loads(live["calls"][index]["user"])["original_context"] for index in (2, 6)]
    rows, labels = [], []

    def add(identity, arguments, verdict, reason, expected_focus, origin):
        dependencies(arguments)
        rows.append({"case_id": identity, "arguments": arguments})
        labels.append({"case_id": identity, "expected_verdict": verdict,
                       "reason": reason, "expected_focus": expected_focus, "origin": origin})

    def exact_activity(context, activity):
        return {"context": deepcopy(context), **{key: deepcopy(activity[old]) for key, old in
            (("research_record", "research"), ("sources", "sources"), ("draft", "draft"),
             ("execution", "execution"), ("authority_evidence", "authority_evidence"))}}

    add("reply-01", exact_activity(contexts[0], first), "reject",
        "The sole greeting supplies none of the requested analysis, contrary positions or client questions. "
        "Internal partial research does not deliver a task-specific limit or justify omitting possible independent work.",
        ["Greeting itself remains supported", "Independent requested outcomes marked missing",
         "Do not invent a limitation absent from the reply"], "Exact first live draft and all original evidence")
    add("reply-02", exact_activity(contexts[1], second), "reject",
        "The corrected 8 September assertion selects only the superseded 6 September account in uses; "
        "addresses identifies the request but is not its factual support. Actual draft also contains "
        "model-authored record-effect statuses and overstates what the disputed damage account establishes.",
        ["Unit b3 current date uses wrong original source", "Unit b4 current date also lacks current supporting use",
         "Effect-status assertions remain code-owned", "Preserve correct greeting and useful question work"],
        "Exact second live draft and all original evidence, including genuine additional defects")

    greeting = common.case("review-social", "Good morning, NM. I hope you are well.", {})["context"]
    add("reply-03", fixture(greeting, {"units": [unit(greeting, "greeting", "Good morning. How can I help?")]}),
        "accept", "A genuine social opening has no substantive task to omit; a natural greeting is sufficient.",
        ["No fabricated substantive request", "No requirement to create matter work"], "New legitimate social neighbour")

    ctx = contexts[1]
    earlier, latest = "live-served-1:advocate", "live-served-2:advocate"
    positive = {"units": [
        unit(ctx, "greeting", "Hello again."),
        unit(ctx, "analysis", "In this account, the owner alleges damage and your client denies causing it. "
            "Those competing statements are not, by themselves, a verified finding about cause. 'Allegation' "
            "refers here to the claim being made; 'proved fact' would refer to a conclusion established on "
            "supporting evidence. The supplied account does not let me decide whether damage occurred or who caused it.",
            [use(earlier), use(latest)]),
        unit(ctx, "account", "Your latest clarification gives 8 September 2026 as the client's reported return date, "
            "in place of the earlier reported 6 September. The event itself remains reported.", [use(latest)]),
        unit(ctx, "question", "For your internal client discussion: 1. What records or communications support the "
            "reported return on 8 September? 2. What was the cutter's condition at return, and what records support "
            "that account? 3. Was a joint inspection conducted or a report created, and is any such report available? "
            "4. Can the client provide the signed hire agreement and transfer receipt it reports holding? "
            "5. What does the technician's estimate say, and what response does the client have to it? "
            "6. What was agreed about the design drive's setup use and return, and what communication records the "
            "owner's claimed right to retain it?", [use(earlier), use(latest)])]}
    add("reply-04", fixture(ctx, positive, second), "accept",
        "Addresses every current request with attributed ordinary-language explanation, reported corrected date "
        "supported by the current original message, and useful internal questions; no completed-operation claim.",
        ["Current original support for 8 September", "Unverified account remains attributed",
         "Useful questions do not need law or imply damage proved", "No false requirement for a record mutation"],
        "Source-corrected semantic neighbour using exact full second-turn context and held evidence")

    missing = common.case("review-documents", "Compare the cancellation clauses in the two versions of our supply "
        "agreement. I have not provided either version yet. In the meantime, give me brief questions to obtain the "
        "documents and context you need. Keep this internal.", {})["context"]
    current = missing["latest"]["source_id"]
    limited = {"units": [
        unit(missing, "limitation", "I cannot compare the cancellation wording until both agreement versions are "
            "available; neither version has been provided here.", [use(current)]),
        unit(missing, "question", "For the internal discussion: Can you provide both complete agreement versions? "
            "What is the date and status of each version, including whether it was signed or proposed, if known? "
            "What practical cancellation outcome "
            "does the client want the comparison to address?", [use(current)])]}
    add("reply-05", fixture(missing, limited), "accept",
        "The reply states the exact source-backed reason comparison cannot yet be performed and still supplies "
        "the independently requested useful questions. No unavailable legal source is invented.",
        ["Comparison has a delivered task-specific justified limit", "Question work is addressed independently"],
        "New explicit missing-document neighbour with complete original context")

    negative_effect = deepcopy(positive)
    negative_effect["units"].append(unit(ctx, "limitation",
        "I have not changed any separate saved fact record.", [use(latest)]))
    add("reply-06", fixture(ctx, negative_effect, second), "reject",
        "The otherwise supported reply adds an NM-authored negative saved-effect statement. Current contract "
        "reserves execution and no-execution statuses to code even when a read-only receipt is available.",
        ["Reject appended effect-status unit", "Do not reject supported explanation, current date or questions"],
        "Controlled negative-effect neighbour of reply-04")

    baseline = read(BASELINE)
    assert baseline["system"] == live["calls"][3]["system"]
    for path, content in ((CASES, {"cases": rows}), (ORACLE, {
            "status": "awaiting independent root confirmation", "not_model_input": True, "labels": labels})):
        if path.exists():
            assert read(path) == content, "Do not overwrite prepared evidence"
        else:
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"prepared_cases": 6, "maximum_calls_if_approved": 12, "paid_calls": 0,
                      "inputs": CASES.name, "oracle": ORACLE.name, "baseline": BASELINE.name}))


class SystemOverride:
    def __init__(self, model, system, receipt):
        self.model, self.system, self.receipt = model, system, receipt

    def context_budget(self, tier):
        return self.model.context_budget(tier)

    def structured(self, prompt, schema, tier, **kwargs):
        assert tier is Tier.ROUTINE and not self.receipt.get("dispatched")
        actual = Prompt(system=self.system, user=prompt.user, operation=prompt.operation)
        assert estimate_tokens(self.system + prompt.user + json.dumps(schema)) + kwargs["max_tokens"] <= self.context_budget(tier)
        self.receipt.update(dispatched=True, user_sha256=digest(prompt.user.encode("utf-8")),
                            operation=prompt.operation, output_ceiling=kwargs["max_tokens"])
        result = self.model.structured(actual, schema, tier, **kwargs)
        self.receipt["provider_result"] = {"data": deepcopy(result.data), "model": result.model,
            "completion": result.completion.value, "usage": asdict(result.usage),
            "latency_ms": result.latency_ms, "retries": result.retries}
        return result


def run(allowance):
    # The hidden oracle is deliberately never read here or sent to either model call.
    assert 0 < allowance <= 0.30 and not RESULTS.exists()
    cases, baseline = read(CASES)["cases"], read(BASELINE)
    assert len(cases) == 6 and response_review.SYSTEM != baseline["system"], "Revised prompt not frozen yet"
    systems = {"baseline": baseline["system"], "revised": response_review.SYSTEM}
    load_dotenv(common.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == common.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(common.MODEL,))
    model = OpenAIModelAdapter(config, call_budget=budget).for_matter_text(lambda: None)
    source_path = common.ROOT / "nm/core_engine/response_review.py"
    source_hash = digest(source_path.read_bytes())
    before = budget.status()
    result = {"started_utc": datetime.now(timezone.utc).isoformat(), "model": common.MODEL,
        "systems": systems, "schema": deepcopy(response_review.SCHEMA), "input_sha256": digest(CASES.read_bytes()),
        "maximum_calls": 12, "semantic_retries": 0, "actual_spend_stop_usd": allowance,
        "source_sha256": source_hash, "budget_before": before, "reviews": []}
    tasks = [(case, version) for case in cases for version in systems]
    random.Random(10719).shuffle(tasks)
    for case, version in tasks:
        if budget.status()["charged_usd"] - before["charged_usd"] >= allowance:
            result["stopped_reason"] = "Approved actual-spend stop"
            break
        assert digest(source_path.read_bytes()) == source_hash, "Reviewer changed during comparison"
        receipt = {"case_id": case["case_id"], "version": version}
        wrapped = SystemOverride(model, systems[version], receipt)
        try:
            receipt["checked_review"] = response_review.review(wrapped, **case["arguments"])
        except Exception as exc:
            receipt["error_type"] = type(exc).__name__
        result["reviews"].append(receipt)
        result["budget_after"] = budget.status()
        result["actual_cost_usd"] = result["budget_after"]["charged_usd"] - before["charged_usd"]
        result["logical_calls"] = sum(bool(row.get("dispatched")) for row in result["reviews"])
        RESULTS.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": case["case_id"], "version": version,
                          "error": receipt.get("error_type"), "cost_usd": result["actual_cost_usd"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-with-approved-allowance-usd", type=float)
    args = parser.parse_args()
    if args.run_with_approved_allowance_usd is None:
        prepare()
    else:
        run(args.run_with_approved_allowance_usd)
