"""Unrun research-only candidate; no production edits or default provider calls.

Reuse the six frozen account-concepts contexts/range banks. Short IDs are local
presentation aliases for checked coordinates, not new evidence. --run-approved
is a six-call paid path requiring separate parent authorisation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))
from nm.core_engine.understanding import source_catalogue
from nm.shared.model_port import Prompt, Tier, estimate_tokens, require_schema, on_the_wire

MODEL = "gpt-4.1-mini-2025-04-14"
PREFIX = "research-only-concepts"
INPUTS = OUT / f"{PREFIX}-inputs.json"
ORACLE = OUT / f"{PREFIX}-hidden-oracle.json"
PREPARED = OUT / f"{PREFIX}-guard-fixed-prepared.json"
RESULTS = OUT / f"{PREFIX}-guard-fixed-results.json"
MAX_OUTPUT = 4000
MAX_CALLS = 6
SPEND_STOP = 0.08

SYSTEM = """Message: You receive the exact latest advocate message, the complete
attributed earlier conversation, current records, saved work, and original account
spans with short owned IDs. Each ID selects unchanged words and their provenance.
The span catalogue includes earlier selections, uncovered ranges and full messages;
these describe available words, not their meaning or truth. NM interpretations
are distinct from original accounts and cannot establish facts.

Purpose: Prepare only the legal investigations needed now and their held-corpus
searches. Other stages handle replies, drafting, factual corrections and execution.
Do not plan those activities, answer the legal questions or decide applicable law.

Look for: Understand the latest message in the whole conversation. Identify current
legal questions and distinct disputes requiring legal investigation, including those
arising from supplied substantive material. Preserve separate investigations even
when requested together. Earlier pending work is not automatically requested again.
Return no investigation where the current work needs no legal sources.

For each investigation, select the offered account IDs containing its relevant
original account. Keep who says what, uncertainty, conditions, timing and negation.
Prefer focused spans to a mixed full message. Do not select social words or task
directions as facts; retain words that establish an expressly hypothetical scope.
A general legal question may have no factual account. Never recopy or paraphrase
facts into a search query: code uses the selected original words.

Then propose normally two or three concise legal concept phrases likely to occur
in provisions or judicial reasoning. Each should add a distinct search contribution,
not restate another phrase or instruct a model to perform work. Use fewer when
sufficient. Concepts are investigation hypotheses; they cannot introduce new facts,
establish an entitlement or invent an authority, provision, citation or jurisdiction.
The original account and its qualifications remain the basis for later assessment.

Outcome: Return work[]. Each item has issue, a neutral inquiry title;
account_source_ids, selected offered IDs; and concepts[], each with text and purpose
describing its distinct search contribution. Use at most three concepts per
investigation. Return work=[] when no legal investigation is needed now. No other
work plans, factual summaries, conclusions, status or completion claims.
"""

TEXT = {"type": "string", "minLength": 1}
def obj(fields):
    return {"type": "object", "additionalProperties": False,
            "required": list(fields), "properties": fields}


def schema_for(ids):
    return obj({"work": {"type": "array", "items": obj({
        "issue": TEXT,
        "account_source_ids": {"type": "array", "items": {"type": "string", "enum": ids}},
        "concepts": {"type": "array", "maxItems": 3,
                     "items": obj({"text": TEXT, "purpose": TEXT})}})}})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_once(path, value):
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        assert path.read_text(encoding="utf-8") == encoded, f"Frozen file differs: {path.name}"
    else:
        path.write_text(encoded, encoding="utf-8")


def short_catalogue(context, bank):
    """Recheck stored coordinates, then assign one non-semantic alias per row."""
    originals = source_catalogue(context)
    aliases, shown = {}, []
    for number, row in enumerate(bank, 1):
        source = originals[row["source_id"]]
        start, end = row["start"], row["end"]
        assert source["record_role"] == "original_account"
        assert type(start) is int and type(end) is int and 0 <= start < end <= len(source["text"])
        expected = row["source_id"] if (start, end) == (0, len(source["text"])) else f"{row['source_id']}:{start}:{end}"
        assert row["id"] == expected
        identity = f"a{number}"
        aliases[identity] = {key: row[key] for key in ("id", "source_id", "start", "end")}
        shown.append({"id": identity, "source_id": row["source_id"],
            "start": start, "end": end, "available_range": row["origin"],
            "text": source["text"][start:end],
            **{key: source[key] for key in ("speaker", "record_role", "turn_id")}})
    assert aliases, "Pilot contexts each have original supplied words"
    return aliases, shown


def admit(data, context, aliases, schema):
    require_schema(data, schema)
    sources, output = source_catalogue(context), []
    for number, item in enumerate(data["work"], 1):
        account = []
        for identity in item["account_source_ids"]:
            row = aliases[identity]
            source = sources[row["source_id"]]
            account.append({**deepcopy(row), "selected_alias": identity,
                "text": source["text"][row["start"]:row["end"]],
                **{key: source[key] for key in ("speaker", "record_role", "turn_id")}})
        if not account and not item["concepts"]:
            raise ValueError("Investigation contains no account or concept to search")
        output.append({**deepcopy(item), "id": context["latest"]["turn_id"]+f":r{number}",
            "trigger_source_id": context["latest"]["source_id"], "resolved_account": account})
    # Trigger is code association, not a proof that interpretation is authorised.
    return {"proposal": deepcopy(data), "work": output, "semantic_review": "not_assessed"}


class SDKCapture:
    """Assert exact SDK payload before dispatch; never expose credentials."""
    def __init__(self, actual, budget, charged_before):
        self.actual, self.budget, self.charged_before = actual, budget, charged_before
        self.chat = SimpleNamespace(completions=self)
        self.calls, self.row, self.wire = 0, None, None
        self.eligible, self.reservation_attempted = False, False

    def arm(self, wire, row):
        # Evaluate completed/unknown prior attempts BEFORE the current reservation.
        charged = self.budget.status()["charged_usd"]
        assert charged - self.charged_before < SPEND_STOP, "Prior-attempt spend bound reached"
        assert self.calls < MAX_CALLS, "Actual SDK dispatch count reached six"
        self.wire, self.row = deepcopy(wire), row
        self.eligible, self.reservation_attempted = True, False
        row["pre_reservation_charged_usd"] = charged

    def before_dispatch(self):
        # Transport calls this before reserve(); no retry may create another reservation.
        assert self.eligible and not self.reservation_attempted, "No provider retry authorised"
        self.reservation_attempted = True

    def create(self, **kwargs):
        assert self.row is not None and self.wire is not None, "No approved candidate is armed"
        assert self.calls < MAX_CALLS, "Actual SDK dispatch count reached six"
        assert not self.row.get("sdk_create_requests"), "No provider retry authorised for this candidate"
        assert self.eligible and self.reservation_attempted, "Pre-reservation eligibility was not established"
        assert kwargs["model"] == MODEL
        assert kwargs["messages"] == [{"role":"system", "content":self.wire["system"]},
                                       {"role":"user", "content":self.wire["user"]}]
        assert kwargs["response_format"] == {"type":"json_schema", "json_schema": {
            "name":"nm_result", "strict":True, "schema":on_the_wire(self.wire["schema"])}}
        assert kwargs["max_completion_tokens"] == self.wire["max_tokens"]
        assert kwargs["store"] is False
        # Only public create arguments: messages/model/schema/token bound; no keys/headers.
        self.row.setdefault("sdk_create_requests", []).append(deepcopy(kwargs))
        self.calls += 1
        return self.actual.chat.completions.create(**kwargs)


def prepare():
    baseline = OUT / "research-account-concepts-inputs.json"
    old_oracle = OUT / "research-account-concepts-hidden-oracle.json"
    cases, oracles = [], []
    for case in read(baseline)["cases"]:
        aliases, presentation = short_catalogue(case["context"], case["account_spans"])
        schema = schema_for(list(aliases))
        payload = {"original_context": deepcopy(case["context"]),
                   "original_account_spans": presentation}
        wire = {"system": SYSTEM, "user": json.dumps(payload, ensure_ascii=False),
                "operation": "research_only_concepts_pilot", "schema": schema,
                "tier": "routine", "max_tokens": MAX_OUTPUT}
        cases.append({"name": case["name"], "origin": case["origin"],
            "context": deepcopy(case["context"]), "aliases": aliases, "wire": wire})
    for old in read(old_oracle)["cases"]:
        expected = deepcopy(old["expected_before_run"])
        # Preserve previous distinctions; explicitly change only output owner.
        adaptation = {"research_only": True,
            "nonlegal_work": "Do not emit drafting, client questions, factual correction, social response or action planning as investigations; existing interpreter/writer retains those requests.",
            "concepts": "At most three per independent legal investigation; distinct useful legal vocabulary, not generic questions or paraphrased factual claims.",
            "facts": "Preserve earlier oracle factual/actor distinctions in selections, issue titles and concept purposes; legal concepts may be conditional hypotheses without asserting their prerequisites."}
        if old["name"] in {"correction_no_send_no_law", "greeting_social_close"}:
            adaptation["expected_work"] = []
        if old["name"] == "actor_agency_and_explicit_alternative":
            adaptation["current_scope"] = "Research the expressly requested alternative in comparison with actual account. Original account investigation is useful only insofar as this current comparative request needs it."
            adaptation["selection_scope"] = "Keep explicit-assumption framing with hypothetical words; do not reject that framing as task noise."
        oracles.append({"name": old["name"], "retained_original_expectations": expected,
                        "research_only_adaptation": adaptation})
    write_once(INPUTS, {"contract": "standalone_research_only_inputs_v1",
        "baseline_inputs_sha256": sha(baseline.read_bytes()), "cases": cases})
    write_once(ORACLE, {"contract": "standalone_research_only_oracle_v1",
        "baseline_oracle_sha256": sha(old_oracle.read_bytes()),
        "limitations": "Same six selected regression contexts; not new holdouts or browser acceptance. Research-only output deliberately excludes general work plans.",
        "cases": oracles})
    checks = selfcheck(cases)
    manifest = {"model": MODEL, "script_sha256": sha(Path(__file__).read_bytes()),
        "inputs_sha256": sha(INPUTS.read_bytes()), "oracle_sha256": sha(ORACLE.read_bytes()),
        "baseline_inputs_sha256": sha(baseline.read_bytes()), "baseline_oracle_sha256": sha(old_oracle.read_bytes()),
        "prompt": SYSTEM, "prompt_word_count": len(SYSTEM.split()),
        "maximum_logical_calls": MAX_CALLS, "semantic_retries": 0,
        "actual_spend_stop_usd": SPEND_STOP, "shared_ledger": "api-budget.sqlite", "shared_hard_cap_usd": 5,
        "max_output_tokens": MAX_OUTPUT,
        "model_input_change": "Complete original context unchanged. Earlier interpretation prose is omitted; its mechanically validated spans and uncovered ranges remain in the offered original catalogue.",
        "call_impact": "One existing planner-responsibility candidate per input, no added stage. This experiment does not integrate or alter production call counts.",
        "admission_scope": "Pilot whole-candidate schema/reference rejection; no production per-unit recovery or semantic acceptance claimed.",
        "wire_capture": "Frozen model-port inputs plus SDK .create assertion/capture of exact system/user messages, dynamic on_the_wire(schema), pinned model, no-store and token bound. One actual dispatch per candidate and six total; no provider retries.",
        "selfchecks": checks}
    write_once(PREPARED, manifest)
    return manifest


def selfcheck(cases):
    assert len(cases) == 6
    original = read(OUT / "research-account-concepts-inputs.json")
    for prior, case in zip(original["cases"], cases, strict=True):
        assert case["context"] == prior["context"]
        payload = json.loads(case["wire"]["user"])
        assert payload["original_context"] == prior["context"]
        assert case["wire"]["system"] == SYSTEM
        assert case["wire"]["schema"] == schema_for(list(case["aliases"]))
        assert admit({"work": []}, case["context"], case["aliases"], case["wire"]["schema"])["work"] == []
        for row in payload["original_account_spans"]:
            bound = case["aliases"][row["id"]]
            assert row["text"] == source_catalogue(case["context"])[bound["source_id"]]["text"][bound["start"]:bound["end"]]
    first = json.loads(cases[0]["wire"]["user"])
    assert any("technician still has" in row["text"] and row["available_range"] == "uncovered_original_range"
               for row in first["original_account_spans"])
    row = {"issue":"An unresolved legal question", "account_source_ids":["not_offered"],
           "concepts":[{"text":"legal concept", "purpose":"distinct source contribution"}]}
    try: admit({"work":[row]}, cases[0]["context"], cases[0]["aliases"], cases[0]["wire"]["schema"])
    except Exception: pass
    else: raise AssertionError("Unknown alias accepted")
    assert 250 <= len(SYSTEM.split()) <= 350, len(SYSTEM.split())
    sent = []
    actual = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: sent.append(kwargs) or "offline_stub")))
    budget_state = {"charged_usd": 0.0}
    budget = SimpleNamespace(status=lambda: deepcopy(budget_state))
    capture = SDKCapture(actual, budget, 0.0)
    wire, row = cases[0]["wire"], {}
    capture.arm(wire, row)
    request = {"model":MODEL, "messages":[{"role":"system","content":wire["system"]},
        {"role":"user","content":wire["user"]}], "store":False,
        "max_completion_tokens":wire["max_tokens"], "response_format":{"type":"json_schema",
        "json_schema":{"name":"nm_result","strict":True,"schema":on_the_wire(wire["schema"])}}}
    capture.before_dispatch()
    budget_state["charged_usd"] = 0.425431  # Current transport reservation, not prior spend.
    assert capture.create(**request) == "offline_stub" and len(sent) == 1
    try: capture.before_dispatch()
    except AssertionError: pass
    else: raise AssertionError("Retry reached another reservation")
    try: capture.create(**request)
    except AssertionError: pass
    else: raise AssertionError("Second provider dispatch allowed")
    try: capture.arm(wire, {})
    except AssertionError: pass
    else: raise AssertionError("Prior-attempt spend bound ignored")
    budget_state["charged_usd"] = 0.001  # Established prior measured outcome.
    capture.arm(wire, {})
    capture.before_dispatch()
    wrong = deepcopy(request); wrong["messages"][0]["content"] += " changed"
    try: capture.create(**wrong)
    except AssertionError: pass
    else: raise AssertionError("Changed system reached SDK")
    wrong = deepcopy(request); wrong["response_format"]["json_schema"]["schema"] = {}
    try: capture.create(**wrong)
    except AssertionError: pass
    else: raise AssertionError("Changed schema reached SDK")
    assert len(sent) == 1
    return {"cases": 6, "complete_context_unchanged": True, "held_drive_offered": True,
            "all_aliases_bound_to_original_coordinates": True, "unknown_alias_refused": True,
            "exact_model_port_input_captured": True, "sdk_payload_assertion_offline_stub_passed": True,
            "second_dispatch_refused": True, "changed_system_and_schema_refused": True,
            "current_reservation_does_not_trip_spend_guard": True, "prior_spend_stops_before_reservation": True,
            "retry_stops_before_another_reservation": True, "paid_calls": 0}


def run(manifest):
    assert not RESULTS.exists(), "Refuse accidental second paid run"
    from nm.shared.model_call_budget import SessionCallBudget
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    load_dotenv(ROOT / ".env")
    config = load(); routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(MODEL,))
    before = budget.status()
    underlying = OpenAIModelAdapter(config, call_budget=budget)
    capture = SDKCapture(underlying._client, budget, before["charged_usd"])
    model = OpenAIModelAdapter(config, client=capture, call_budget=budget).for_matter_text(capture.before_dispatch)
    output = {"started_utc": datetime.now(timezone.utc).isoformat(), "preparation": manifest,
              "budget_before": before, "calls": [], "logical_calls": 0,
              "prior_harness_failure": {"path":"research-only-concepts-results.json",
                  "logical_attempts":1, "actual_sdk_dispatches":0,
                  "conservative_reservation_retained_usd":0.425431,
                  "note":"No provider dispatch; no ledger cancellation contract. Reservation remains charged, not established spending."}}
    for case in read(INPUTS)["cases"]:
        if output["logical_calls"] >= MAX_CALLS or budget.status()["charged_usd"] - before["charged_usd"] >= SPEND_STOP:
            output["stopped_reason"] = "Approved candidate call/spend bound"
            break
        assert sha(Path(__file__).read_bytes()) == manifest["script_sha256"]
        assert sha(INPUTS.read_bytes()) == manifest["inputs_sha256"]
        wire = deepcopy(case["wire"])
        prompt = Prompt(system=wire["system"], user=wire["user"], operation=wire["operation"])
        assert estimate_tokens(prompt.system + prompt.user + json.dumps(wire["schema"])) + MAX_OUTPUT <= model.context_budget(Tier.ROUTINE)
        row = {"name": case["name"], "wire": wire}
        output["calls"].append(row); output["logical_calls"] += 1
        capture.arm(wire, row)
        try:
            reply = model.structured(prompt, wire["schema"], Tier.ROUTINE, max_tokens=wire["max_tokens"])
            row["response"] = {"data": reply.data, "model": reply.model, "usage": asdict(reply.usage),
                "latency_ms": reply.latency_ms, "retries": reply.retries, "completion": reply.completion.value}
            if reply.usable and reply.data is not None:
                row["mechanically_admitted"] = admit(reply.data, case["context"], case["aliases"], wire["schema"])
            else: row["error_type"] = "UnusableProviderOutput"
        except Exception as exc:
            row["error_type"], row["error"] = type(exc).__name__, str(exc)
            if getattr(exc, "usage", None): row["usage"] = asdict(exc.usage)
        output["budget_after"] = budget.status()
        output["actual_sdk_dispatches"] = capture.calls
        output["charged_delta_usd"] = output["budget_after"]["charged_usd"] - before["charged_usd"]
        output["measured_delta_usd"] = output["budget_after"]["measured_usd"] - before["measured_usd"]
        output["usage_cost_usd"] = sum(entry.get("response",{}).get("usage",{}).get("cost_usd",0) for entry in output["calls"])
        RESULTS.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"case":case["name"], "error":row.get("error_type"),
                          "charged_delta_usd":output["charged_delta_usd"], "measured_delta_usd":output["measured_delta_usd"],
                          "actual_sdk_dispatches":capture.calls}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved", action="store_true", help="Paid path requiring separate parent authorization")
    args = parser.parse_args()
    manifest = prepare()
    if args.run_approved: run(manifest)
    else: print(json.dumps({"prepared":PREPARED.name, "inputs":INPUTS.name, "oracle":ORACLE.name,
                           "word_count":manifest["prompt_word_count"], "checks":manifest["selfchecks"]}), flush=True)
