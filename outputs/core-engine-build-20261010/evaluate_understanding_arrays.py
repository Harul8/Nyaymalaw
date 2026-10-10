"""Unpromoted four-array interpretation prototype; same five cases and USD5 ledger."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import evaluate_understanding_five as baseline

from nm.core_engine.understanding import accept
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Prompt, Tier, require_schema

OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "understanding-arrays-prototype-live.json"
SYSTEM = """
Purpose: Interpret what the advocate communicates and wants now. Produce proposals
for subsequent work; do not answer, research, execute work or change records.

Look for: Read the whole latest message in its complete conversation and saved
work context. Independently identify social courtesies, substantive information,
requested results, and instructions limiting work. Several functions may apply
to the same words. Separate requested results whenever one can be completed,
withheld or cancelled independently. Retain limiting instructions separately.
Quoted instructions remain attributed to their original speaker; they become
requests to NM only when the advocate authorises them. Preserve reported speech,
uncertainty, timing, conditions and negation. NM interpretations are not original
evidence; saved work does not grant new consent. A temporary diversion does not
cancel earlier work. Resolve references from supplied original context and retain
applicable limits or missing inputs. State only ambiguities or missing inputs that
materially obstruct understanding or execution, not optional style preferences.

Outcome: Return four arrays: courtesies, information, requests and restrictions.
Every item selects exact latest-message words and briefly explains its function.
Each request item represents one independently completable result with its work
type and desired result. Select earlier source IDs and exact words when needed
to support contextual meaning or limits; do not substitute latest-message echoes.
Use empty arrays when a function is absent. Empty context is valid when no earlier
context is needed. Quotes may overlap across functions. No invented facts,
permissions, IDs, completion claims or additional work.
"""

TEXT = {"type": "string", "minLength": 1}
REF = {"type": "object", "additionalProperties": False,
       "required": ["source_id", "quote"], "properties": {
           "source_id": {**TEXT, "description": "An earlier supplied source ID supporting contextual meaning or a limiting condition."},
           "quote": {**TEXT, "description": "Exact continuous original words, long enough to be unambiguous."}}}
COMMON = {
    "quote": {**TEXT, "description": "Exact latest-message words for this function; overlapping quotes are allowed."},
    "meaning": {**TEXT, "description": "Concise interpretation preserving original speaker, conditions, timing and certainty."},
    "context": {"type": "array", "items": REF,
                "description": "Earlier original references needed for contextual meaning and applicable limits; empty when none is needed."},
    "unresolved": {"type": "array", "items": TEXT,
                   "description": "Only ambiguities or missing inputs materially blocking understanding or execution; no optional stylistic preferences."},
}


def item(description, *, request=False):
    props = deepcopy(COMMON)
    if request:
        props.update({
            "requested_work": {"type": "string", "enum": ["research", "citation_check", "analysis", "drafting", "document_work", "record_update", "conversation", "other"]},
            "desired_result": {**TEXT, "description": "One independently completable result, preserving the target and limits of the advocate's instruction."}})
    return {"type": "array", "description": description,
            "items": {"type": "object", "additionalProperties": False,
                      "required": list(props), "properties": props}}


SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["courtesies", "information", "requests", "restrictions"],
          "properties": {
              "courtesies": item("Social contact, thanks and social closing; empty if absent."),
              "information": item("Substantive non-social accounts or supplied content, including information accompanying requests or restrictions."),
              "requests": item("One item for EACH independently completable result the advocate asks NM to deliver, even within a shared sentence.", request=True),
              "restrictions": item("One item for EACH instruction limiting, suspending or cancelling work, even when embedded in another function.")}}
KINDS = {"courtesies": "courtesy", "information": "information",
         "requests": "request", "restrictions": "restriction"}


def main():
    if EVIDENCE.exists():
        raise SystemExit("Prototype evidence exists; refusing an accidental repeated evaluation.")
    load_dotenv(baseline.ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == baseline.MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(baseline.MODEL,))
    model = baseline.RecordedModel(OpenAIModelAdapter(config, call_budget=budget))
    evidence = {"prototype_only": True, "started_utc": datetime.now(timezone.utc).isoformat(),
                "model": baseline.MODEL, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "budget_before": budget.status(), "cases": []}
    for case in baseline.CASES:
        ctx = case["context"]
        intro = ("Message: This is the advocate's opening message; no earlier conversation exists.\n"
                 if ctx["position"] == "first" else
                 "Message: This is the advocate's next message, with the complete ordered attributed conversation, current records and saved work.\n")
        prompt = Prompt(system=intro + SYSTEM,
                        user=json.dumps({k: v for k, v in ctx.items() if k != "position"}, ensure_ascii=False),
                        operation="prototype_understanding_arrays")
        row = deepcopy(case)
        before = len(model.calls)
        try:
            result = model.structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=6000)
            assert result.usable and result.data is not None
            require_schema(result.data, SCHEMA)
            units = []
            for name, kind in KINDS.items():
                for original in result.data[name]:
                    value = {**deepcopy(original), "kind": kind}
                    if name != "requests":
                        value.update(requested_work=None, desired_result=None)
                    units.append(value)
            # Exercise the existing mechanical reference checks only. This is not
            # admission to the application's records or semantic acceptance.
            row["existing_source_checks"] = accept({"units": units}, ctx)
            row["prototype_output"] = deepcopy(result.data)
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        row["calls"] = deepcopy(model.calls[before:])
        evidence["cases"].append(row)
        evidence["logical_calls"] = len(model.calls)
        evidence["budget_after"] = budget.status()
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": case["name"],
                          "counts": {k: len(v) for k, v in row.get("prototype_output", {}).items()},
                          "issues": row.get("existing_source_checks", {}).get("issues", []),
                          "error": row.get("error_type")}), flush=True)
    print(json.dumps({"calls": len(model.calls), "budget": budget.status()}), flush=True)


if __name__ == "__main__":
    main()
