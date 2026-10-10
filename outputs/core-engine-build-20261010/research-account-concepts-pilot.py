"""Standalone candidate: exact account discovery plus <=3 concept phrases.

Default preparation/self-check is offline. --run-approved is the sole provider
path and must not be used until the parent reviews the frozen candidate. There
are six candidate calls, no semantic repair, no retrieval or application edits.
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

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
sys.path.insert(0, str(ROOT))
from nm.core_engine.understanding import source_catalogue, select
from nm.shared.model_port import Prompt, Tier, require_schema, estimate_tokens

MODEL = "gpt-4.1-mini-2025-04-14"
PREFIX = "research-account-concepts"
INPUTS = OUT / f"{PREFIX}-inputs.json"
ORACLE = OUT / f"{PREFIX}-hidden-oracle.json"
PREPARED = OUT / f"{PREFIX}-prepared.json"
RESULTS = OUT / f"{PREFIX}-results.json"
MAX_OUTPUT = 6500
MAX_CALLS = 6
SPEND_STOP = 0.08

SYSTEM = """Message: You receive the advocate's exact latest message, complete
attributed earlier conversation, current records and saved work, plus an earlier
interpretation proposal and an owned catalogue of original source spans. A span
ID identifies exact words, not their factual truth or their semantic category.
Original accounts, NM interpretations and work instructions remain distinct.

Purpose: Plan the independently useful work needed now and searches of held law.
For each independent legal investigation, select the original account to search
first, then propose no more than three focused legal concept searches. Do not
answer, decide applicable law, execute actions or change records.

Look for:
1. Read the complete original conversation before the interpretation. Return a
separate work item for each independent legal investigation or dispute, even when
requested together, and separately preserve other requested results and applicable
limits. A diversion does not cancel earlier
work; earlier work does not override the current instruction. Do not force legal
work onto a greeting or research onto a task that the supplied account can resolve.
2. Select work-supporting whole sources by source_id with quote=null, including
the current instruction. account_source_ids selects original account passages
exclusively for LEGAL SEARCH, not for factual extraction or internal work generally.
For work needing law, select these IDs from the offered original spans. Use focused spans where a
message mixes facts, social words and instructions. Keep attribution, uncertainty,
timing, negation, relationships and contrary positions. Do not copy or paraphrase
the account: code supplies the selected exact words. An uncovered range is merely
text not selected earlier, not proof that it is factual or irrelevant. Inspect it.
An NM statement may be reviewed but cannot prove its own factual content.
3. Where law is needed, normally propose two or three concise phrases in the
terminology likely to occur in provisions or judicial reasoning. Each must seek
a distinct useful concept connected to this investigation, not a synonym or a
generic request to explain applicable law or draft questions. A client questionnaire
may use the available account and relevant research without its own duplicate
search. Use fewer when sufficient. Independent disputes do not share one three-phrase cap merely because
the advocate asked about them together.
4. A model-proposed legal concept is conditional discovery vocabulary, not an
established legal relationship. It must not add or alter a factual premise. Keep
consequential missing conditions in unresolved. An expressly requested hypothetical
remains distinct from the actual account. Do not invent an Act, provision number,
case citation, jurisdiction or governing rule. A user-supplied legal reference may
guide discovery but remains unverified.

Outcome: Return the declared work array. Each item contains purpose, outcome,
sources, account_source_ids, constraints, unresolved and enquiries. Each enquiry
contains text, its distinct purpose, and basis: reported if the original source
supplies that legal concept, otherwise conditional. Neither basis proves it applies.
All references use offered IDs; every sources quote is null. Use zero to three
enquiries per independent legal investigation. For work not needing legal search,
return BOTH account_source_ids=[] and enquiries=[]; its supporting sources and full
context still supply the account needed for that work. A general legal question
with no factual account may have enquiries with account_source_ids=[].
Use an empty work list where no work is currently requested
or justified. All outputs are proposals, not execution or completion claims.
"""

TEXT = {"type": "string", "minLength": 1}
def obj(fields):
    return {"type": "object", "additionalProperties": False,
            "required": list(fields), "properties": fields}

REFERENCE = obj({"source_id": TEXT, "quote": {"type": "null"}})
ENQUIRY = obj({"text": TEXT, "purpose": TEXT,
               "basis": {"type": "string", "enum": ["reported", "conditional"]}})
WORK = obj({"purpose": TEXT, "outcome": TEXT,
    "sources": {"type": "array", "minItems": 1, "items": REFERENCE},
    "account_source_ids": {"type": "array", "items": TEXT},
    "constraints": {"type": "array", "items": TEXT},
    "unresolved": {"type": "array", "items": TEXT},
    "enquiries": {"type": "array", "maxItems": 3, "items": ENQUIRY}})
SCHEMA = obj({"work": {"type": "array", "items": WORK}})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write_once(path, value):
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        assert path.read_text(encoding="utf-8") == encoded, f"Frozen file differs: {path.name}"
    else:
        path.write_text(encoded, encoding="utf-8")


def span_bank(context, interpretation):
    """Mechanical coordinates only; never infer facts from missing coverage."""
    originals = source_catalogue(context)
    accounts = {k: v for k, v in originals.items() if v["record_role"] == "original_account"}
    ranges = {k: set() for k in accounts}
    ignored = []
    for unit in interpretation.get("units", []):
        for value in [unit.get("source"), *unit.get("context", [])]:
            if not isinstance(value, dict) or value.get("source_id") not in accounts:
                continue
            source = accounts[value["source_id"]]
            start, end = value.get("start"), value.get("end")
            if start is None and end is None and value.get("text") == source["text"]:
                start, end = 0, len(source["text"])
            if (type(start) is int and type(end) is int and 0 <= start < end <= len(source["text"])
                    and value.get("text") == source["text"][start:end]
                    and all(value.get(k) == source.get(k) for k in ("speaker", "record_role", "turn_id"))):
                # Full-source selection provides no segmentation; it must not hide gaps.
                if (start, end) != (0, len(source["text"])):
                    ranges[value["source_id"]].add((start, end))
            else:
                ignored.append({"unit_id": unit.get("id"), "source_id": value["source_id"],
                                "reason": "Prior span is not mechanically bound to original words/provenance"})
    rows = []
    for identity, source in accounts.items():
        if not source["text"]:
            continue
        offered = {(0, len(source["text"])): "complete_original"}
        for pair in ranges[identity]:
            offered[pair] = "earlier_exact_selection"
        cursor = 0
        for start, end in sorted(ranges[identity]):
            if start > cursor:
                offered[(cursor, start)] = "uncovered_original_range"
            cursor = max(cursor, end)
        if cursor < len(source["text"]):
            offered.setdefault((cursor, len(source["text"])), "uncovered_original_range")
        for (start, end), origin in sorted(offered.items()):
            span_id = identity if (start, end) == (0, len(source["text"])) else f"{identity}:{start}:{end}"
            rows.append({"id": span_id, "source_id": identity, "start": start, "end": end,
                         "origin": origin})
    assert len({r["id"] for r in rows}) == len(rows), "Ambiguous offered span ID"
    return rows, ignored


def presentation(context, bank):
    originals = source_catalogue(context)
    return [{**row, "text": originals[row["source_id"]]["text"][row["start"]:row["end"]],
             **{k: originals[row["source_id"]][k] for k in ("speaker", "record_role", "turn_id")}}
            for row in bank]


def scripted_spans(context, passages):
    """Explicit synthetic upstream fixture, never a production segmentation rule."""
    originals = source_catalogue(context)
    units = []
    for number, (identity, passage) in enumerate(passages, 1):
        selected = select({"source_id": identity, "quote": passage}, originals)
        units.append({"id": f"fixture:u{number}", "kind": "unclassified_fixture",
                      "source": selected, "context": []})
    return {"contract": "synthetic_exact_spans_only", "units": units, "issues": [],
            "semantic_review": "not_assessed"}


def build_cases():
    original = read("offline-retrieval-capacity-snapshot.json")
    live = read("live-served-capacity-remeasurement.json")
    priors = read("research-premise-fidelity-six.json")
    old = {r["name"]: r for r in priors["cases"]}
    baseline = {r["name"]: r for r in read("research-probe.json")["cases"]}
    cases, oracle = [], []
    def add(name, context, interpretation, expectations, origin):
        bank, ignored = span_bank(context, interpretation)
        cases.append({"name": name, "origin": origin, "context": deepcopy(context),
            "interpretation_proposal": deepcopy(interpretation), "account_spans": bank,
            "ignored_prior_spans": ignored})
        oracle.append({"name": name, "expected_before_run": expectations})
    actual = live["turns"][0]["canonical_rows"][0]
    assert actual["message"] == original["context"]["latest"]["text"]
    add("original_aster_held_drive", original["context"], actual["activities"]["interpretation"], {
        "independent_legal_work": ["Deposit retention and disputed damage", "Retention/return of design drive"],
        "other_work": ["Draft useful client questions"],
        "required_distinctions": ["Drive holder is owner's technician; owner asserts retention entitlement",
            "Damage remains alleged and denied", "Report not sent, not known nonexistent",
            "Reported documents neither supplied nor examined", "Client location does not establish jurisdiction"],
        "restrictions": ["No contact", "No damage admission", "No verified-document claim"],
        "account_selection": "Drive text held by interpretation must remain available through an uncovered original range; no greetings/task directions as factual query"},
        "Exact saved first Aster message and actual interpretation with held u8; no reconstructed successful extraction")
    c = deepcopy(old["deposit_and_drive"])
    s = c["context"]["latest"]["source_id"]
    text = c["context"]["latest"]["text"]
    pieces = ["Hello.", text[text.index("We act"):text.index("Identify legal")],
              text[text.index("Identify legal"):text.index("Do not send")], text[text.index("Do not send"):]]
    add("not_supplied_is_not_nonexistent", c["context"], scripted_spans(c["context"], [(s,p) for p in pieces]), {
        "independent_legal_work": ["Deposit recovery", "Drive return"], "other_work": ["Client questions"],
        "required_distinctions": ["No joint inspection report supplied does not establish absence",
            "Technician holds drive; no pleaded entitlement to retain it supplied", "Client disputes damage"],
        "forbidden": ["Make a report nonexistent", "Assert a technician/lessor lien, entitlement or admission as established", "Invent jurisdiction"],
        "allowed": ["Investigate a lien or other retention concept conditionally without assuming its prerequisites or changing the actual holder"],
        "upstream_limit": "Exact historical account; upstream segmentation is a frozen synthetic fixture, not observed model success"},
        "Historical failed planner input; scripted exact-span fixture isolates the new planner")
    c = deepcopy(old["explicit_alternative"])
    history = c["context"]["conversation"][0]
    current = c["context"]["latest"]
    boundary = current["text"].index("Identify how")
    old_boundary = history["text"].index("Identify the legal")
    interp = scripted_spans(c["context"], [(history["source_id"], history["text"][:old_boundary]),
        (history["source_id"], history["text"][old_boundary:]),
        (current["source_id"], current["text"][:boundary]),
        (current["source_id"], current["text"][boundary:])])
    add("actor_agency_and_explicit_alternative", c["context"], interp, {
        "legal_work": "Alternative legal analysis of express agency authority and effect of assumed absent email",
        "required_distinctions": ["Original client denies authority; hospital alleges extension",
            "Specimen collection does not establish authority to alter fees", "Original email unforwarded/existence unknown",
            "Latest explicit assumptions are authorised hypothetical only; they must remain analysable"],
        "forbidden": ["Apply hypothetical as actual matter fact", "Swap client, agency and hospital roles", "Contact anyone or update record"]},
        "Exact saved hypothetical neighbour and original agency account; scripted exact spans")
    c = baseline["permission_followup"]
    payload = json.loads(c["calls"][0]["user"])
    context = payload["original_context"]
    latest = context["latest"]
    spans = [(r["source_id"], r["text"]) for r in context["conversation"] if r["record_role"] == "original_account"]
    spans += [(latest["source_id"], p) for p in [
        "Before returning to the passage issue, give me a short explanation of interim relief.",
        "Then resume the work on whether use can continue after the permission ends, keeping the ownership question open.",
        "The plan is still unavailable.", "Do not draft a notice yet."]]
    add("mixed_independent_requests_followup", context, scripted_spans(context, spans), {
        "independent_work": ["Explain interim relief", "Resume continued passage use analysis"],
        "required_distinctions": ["Ownership remains unsettled", "Neighbour claims independent right; client denies",
            "No court determination", "Deed plan unavailable", "Earlier permission expiry retained"],
        "restrictions": ["No notice drafting"],
        "forbidden": ["Treat earlier NM interpretation as original proof", "Drop either independent request"]},
        "Exact saved mixed follow-up account; scripted exact spans retain complete history")
    c = deepcopy(old["date_correction"])
    c["context"]["latest"]["text"] += " Do not send anything to anyone."
    latest = c["context"]["latest"]
    interp = scripted_spans(c["context"], [(r["source_id"],r["text"]) for r in c["context"]["conversation"]
        if r["record_role"] == "original_account"] + [(latest["source_id"],latest["text"])])
    add("correction_no_send_no_law", c["context"], interp, {
        "required_work": "Correct NM summary date to earlier original 14 April, not 14 May",
        "expected_enquiries": [], "expected_account_source_ids": [],
        "restrictions": ["No confirmed payment figure", "No sending"],
        "forbidden": ["Legal search for simple factual repair", "Treat NM's erroneous date as evidence", "Claim executed correction"]},
        "Saved date correction with explicit synthetic no-send addition; prior factual inputs unchanged")
    c = deepcopy(old["social_closing"])
    add("greeting_social_close", c["context"], c["interpretation_proposal"], {
        "expected_work": [], "forbidden": ["Restart pending work", "Create legal research or material changes"]},
        "Exact saved social closing and complete earlier pending-work context")
    return cases, oracle


def admit(data, context, bank):
    require_schema(data, SCHEMA)
    originals, spans = source_catalogue(context), {r["id"]: r for r in bank}
    work = []
    for number, item in enumerate(data["work"], 1):
        selected = [select(ref, originals) for ref in item["sources"]]
        if context["latest"]["source_id"] not in [r["source_id"] for r in selected]:
            raise ValueError("Work did not select current instruction/contribution")
        account = []
        for identity in item["account_source_ids"]:
            if identity not in spans:
                raise ValueError("Unknown account span ID")
            row, original = spans[identity], originals[spans[identity]["source_id"]]
            if original["record_role"] != "original_account":
                raise ValueError("Account span is not original supplied material")
            account.append({**deepcopy(row), "text": original["text"][row["start"]:row["end"]],
                **{k: original[k] for k in ("speaker", "record_role", "turn_id")}})
        work.append({**deepcopy(item), "id": context["latest"]["turn_id"]+f":w{number}",
                     "sources": selected, "resolved_account": account})
    return {"proposal": deepcopy(data), "work": work, "semantic_review": "not_assessed"}


def selfcheck(cases):
    for case in cases:
        sources = source_catalogue(case["context"])
        for row in case["account_spans"]:
            source = sources[row["source_id"]]
            assert source["record_role"] == "original_account"
            assert 0 <= row["start"] < row["end"] <= len(source["text"])
        for identity, source in sources.items():
            if source["record_role"] == "original_account" and source["text"]:
                assert any(r["id"] == identity and r["start"] == 0 and r["end"] == len(source["text"])
                           for r in case["account_spans"])
    first = cases[0]
    assert first["interpretation_proposal"]["issues"], "Actual failed extraction must remain present"
    assert any("technician still has" in r["text"] and r["origin"] == "uncovered_original_range"
               for r in presentation(first["context"], first["account_spans"]))
    # Same words at different owned coordinates remain different valid choices.
    source = {"source_id":"repeat:advocate", "turn_id":"repeat", "speaker":"advocate",
              "record_role":"original_account", "text":"Same. Same."}
    ctx = {"latest":source,"conversation":[]}
    interp = {"units":[{"source":{**source,"text":"Same.","start":0,"end":5},"context":[]},
                       {"source":{**source,"text":"Same.","start":6,"end":11},"context":[]}]}
    bank, _ = span_bank(ctx, interp)
    assert {r["id"] for r in bank if r["origin"] == "earlier_exact_selection"} == {
        "repeat:advocate:0:5", "repeat:advocate:6:11"}
    proposal = {"work":[{"purpose":"Review account","outcome":"Review account",
        "sources":[{"source_id":source["source_id"],"quote":None}],
        "account_source_ids":["repeat:advocate:6:11"],"constraints":[],"unresolved":[],"enquiries":[]}]}
    assert admit(proposal,ctx,bank)["work"][0]["resolved_account"][0]["start"] == 6
    bad = deepcopy(proposal); bad["work"][0]["account_source_ids"] = ["unknown"]
    try: admit(bad,ctx,bank)
    except ValueError: pass
    else: raise AssertionError("Unknown span accepted")
    return {"cases":len(cases),"original_held_drive_offered":True,
            "repeated_words_distinct_by_coordinates":True,"unknown_span_rejected":True,
            "complete_original_sources_preserved":True,"paid_calls":0}


def prepare():
    cases, oracle = build_cases()
    checks = selfcheck(cases)
    write_once(INPUTS, {"contract":"standalone_account_concepts_inputs_v1", "cases":cases})
    write_once(ORACLE, {"contract":"standalone_account_concepts_oracle_v1",
        "label_owner":"Human-readable predeclared evaluator expectations; not visible to candidate model",
        "limitations":"Six selected regression cases; not held-out accuracy, retrieval quality or browser acceptance.",
        "search_routing_invariant":"Nonresearch work has account_source_ids=[] and enquiries=[]; either nonempty field requests legal search. Original context/work sources still support internal work.",
        "cases":oracle})
    manifest = {"model":MODEL,"script_sha256":sha(Path(__file__).read_bytes()),
        "inputs_sha256":sha(INPUTS.read_bytes()),"hidden_oracle_sha256":sha(ORACLE.read_bytes()),
        "system":SYSTEM,"schema":SCHEMA,"max_output_tokens":MAX_OUTPUT,
        "maximum_logical_calls":MAX_CALLS,"semantic_retries":0,"actual_spend_stop_usd":SPEND_STOP,
        "shared_ledger":"api-budget.sqlite","shared_hard_cap_usd":5,
        "scope":"Candidate-only planner; no retrieval, no production edits; schema checks do not certify semantics",
        "admission_scope":"Pilot mechanically rejects the whole candidate on any schema/reference defect; proposed production per-work isolation is not exercised here.",
        "selfchecks":checks}
    write_once(PREPARED, manifest)
    return manifest


def run(manifest):
    assert not RESULTS.exists(), "Refuse accidental second paid run"
    # Credentials/provider construction occur only after explicit run flag.
    from nm.shared.model_call_budget import SessionCallBudget
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    load_dotenv(ROOT / ".env")
    config = load(); routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == MODEL
    assert routine.base_url in (None,"","https://api.openai.com/v1","https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite","5",models=(MODEL,))
    model = OpenAIModelAdapter(config,call_budget=budget).for_matter_text(lambda: None)
    before = budget.status()
    result = {"started_utc":datetime.now(timezone.utc).isoformat(),"prepared":manifest,
              "budget_before":before,"calls":[],"logical_calls":0}
    for case in read(INPUTS.name)["cases"]:
        if result["logical_calls"] >= MAX_CALLS or budget.status()["charged_usd"]-before["charged_usd"] >= SPEND_STOP:
            result["stopped_reason"] = "Candidate call/spend bound"
            break
        assert sha(Path(__file__).read_bytes()) == manifest["script_sha256"]
        assert sha(INPUTS.read_bytes()) == manifest["inputs_sha256"]
        payload = {"original_context":case["context"],"interpretation_proposal":case["interpretation_proposal"],
                   "original_span_catalogue":presentation(case["context"],case["account_spans"])}
        prompt = Prompt(system=SYSTEM,user=json.dumps(payload,ensure_ascii=False),operation="account_concepts_pilot")
        assert estimate_tokens(SYSTEM+prompt.user+json.dumps(SCHEMA))+MAX_OUTPUT <= model.context_budget(Tier.ROUTINE)
        row = {"name":case["name"],"prompt_input":payload}
        result["calls"].append(row); result["logical_calls"] += 1
        try:
            reply = model.structured(prompt,SCHEMA,Tier.ROUTINE,max_tokens=MAX_OUTPUT)
            row["response"] = {"data":reply.data,"model":reply.model,"usage":asdict(reply.usage),
                "latency_ms":reply.latency_ms,"retries":reply.retries,"completion":reply.completion.value}
            if reply.usable and reply.data is not None:
                row["mechanically_admitted"] = admit(reply.data,case["context"],case["account_spans"])
            else:
                row["error_type"] = "UnusableProviderOutput"
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc)
            if getattr(exc,"usage",None): row["usage"] = asdict(exc.usage)
        result["budget_after"] = budget.status()
        result["actual_cost_usd"] = result["budget_after"]["charged_usd"]-before["charged_usd"]
        RESULTS.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"case":case["name"],"error":row.get("error_type"),
                          "cost_usd":result["actual_cost_usd"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved",action="store_true",help="Paid path; use only after explicit parent authorization")
    args = parser.parse_args()
    manifest = prepare()
    if args.run_approved: run(manifest)
    else: print(json.dumps({"prepared":PREPARED.name,"inputs":INPUTS.name,"oracle":ORACLE.name,
                           "checks":manifest["selfchecks"]}),flush=True)
