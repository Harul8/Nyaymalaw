"""One focused interpretation call; source-linked proposals, never executed effects."""
from __future__ import annotations

import json
from copy import deepcopy

from nm.shared.model_port import (
    ContextOverflow, ModelError, Prompt, SchemaViolation, Tier, canonical_schema_data,
    estimate_tokens, require_schema,
)

CONTRACT = "core_understanding_v2"
MAX_OUTPUT = 6000

FIRST = "Message: This is the advocate's opening message. No earlier conversation exists."
FOLLOW_UP = """Message: This is the advocate's next message. You receive the complete
ordered conversation with speakers and source IDs, current records and saved work."""
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
Distinguish a requested deliverable from a declaration or social closing that
merely invites acknowledgement. Preserve the specified target of a correction;
do not extend the requested scope to other records or work products.

Outcome: Return four arrays: courtesies, information, requests and restrictions.
Every item selects exact latest-message words and briefly explains its function.
Each request item represents one independently completable result with its work
type and desired result. Select earlier source IDs and exact words when needed
to support contextual meaning or limits; do not substitute latest-message echoes.
Use empty arrays when a function is absent. Empty context is valid when no earlier
context is needed. Quotes may overlap across functions. A restriction embedded in
a request also belongs in restrictions. No invented facts, permissions, IDs,
completion claims or additional work. Proposals never establish an executed effect.
"""

TEXT = {"type": "string", "minLength": 1}
REFERENCE = {"type": "object", "additionalProperties": False,
             "required": ["source_id", "quote"],
             "properties": {"source_id": TEXT, "quote": TEXT}}
COMMON = {
    "quote": {**TEXT, "description": "Exact latest-message words for this function; overlapping quotes are allowed."},
    "meaning": {**TEXT, "description": "Concise interpretation preserving original speaker, conditions, timing and certainty."},
    "context": {"type": "array", "items": REFERENCE,
                "description": "Earlier original references needed for contextual meaning and applicable limits; empty when none is needed."},
    "unresolved": {"type": "array", "items": TEXT,
                   "description": "Only ambiguities or missing inputs materially blocking understanding or execution; no optional stylistic preferences."}}
KINDS = {"courtesies": "courtesy", "information": "information",
         "requests": "request", "restrictions": "restriction"}


def _items(description, *, request=False):
    fields = deepcopy(COMMON)
    if request:
        fields.update({"requested_work": {"type": "string", "enum": [
            "research", "citation_check", "analysis", "drafting", "document_work",
            "record_update", "conversation", "other"]}, "desired_result": {
                **TEXT, "description": "One independently completable result within the original target and scope."}})
    return {"type": "array", "description": description,
            "items": {"type": "object", "additionalProperties": False,
                      "required": list(fields), "properties": fields}}


SCHEMA = {"type": "object", "additionalProperties": False, "required": list(KINDS),
          "properties": {
              "courtesies": _items("Social contact, thanks and social closing; empty if absent."),
              "information": _items("Substantive non-social accounts or supplied content, including information accompanying requests or restrictions."),
              "requests": _items("One item for each independently completable result explicitly or contextually requested from NM, not a declaration merely inviting acknowledgement.", request=True),
              "restrictions": _items("One item for each instruction limiting, suspending or cancelling work, including instructions also present inside a request.")}}


def source_catalogue(context):
    """Server context only. Preserve exact words and provenance, including NM roles."""
    rows = [*context["conversation"], context["latest"]]
    result = {}
    for row in rows:
        identity = row["source_id"]
        if (type(identity) is not str or not identity or identity in result
                or type(row["text"]) is not str):
            raise ValueError("Context source identity is missing or repeated")
        result[identity] = deepcopy(row)
    return result


def select(reference, sources):
    """Resolve an unambiguous exact passage. No paraphrase or whitespace repair."""
    require_schema(reference, REFERENCE)
    source = sources.get(reference["source_id"])
    if source is None:
        raise SchemaViolation("Selected source_id is not in the supplied context")
    quote, text = reference["quote"], source["text"]
    start = text.find(quote)
    if start < 0:
        raise SchemaViolation("Selected quote is not exact original source text")
    if text.find(quote, start + 1) >= 0:
        raise SchemaViolation("Selected quote has multiple occurrences; select a longer unique passage")
    return {**deepcopy(source), "start": start, "end": start + len(quote), "text": quote}


def accept(proposal, context):
    data = canonical_schema_data(proposal, SCHEMA)
    require_schema(data, {**SCHEMA, "properties": {
        key: {"type": "array", "items": {}} for key in KINDS}})
    sources = source_catalogue(context)
    units, issues = [], []
    proposals = [(key, unit) for key in KINDS for unit in data[key]]
    if not proposals:
        raise SchemaViolation("An empty interpretation does not account for the nonblank message")
    for index, (key, unit) in enumerate(proposals, 1):
        identity = context["latest"]["turn_id"] + f":u{index}"
        try:
            require_schema(unit, SCHEMA["properties"][key]["items"])
            primary = select({"source_id": context["latest"]["source_id"],
                              "quote": unit["quote"]}, sources)
            selected = [select(ref, sources) for ref in unit["context"]]
            if key == "requests":
                if not unit["requested_work"] or not unit["desired_result"].strip():
                    raise SchemaViolation("A request needs its work kind and desired result")
            units.append({"id": identity, "kind": KINDS[key], "source": primary,
                          "meaning": unit["meaning"], "context": selected,
                          "requested_work": unit.get("requested_work"),
                          "desired_result": unit.get("desired_result"),
                          "unresolved": deepcopy(unit["unresolved"])})
        except SchemaViolation as exc:
            issues.append({"unit": identity, "source_id": context["latest"]["source_id"],
                           "quote": unit.get("quote") if isinstance(unit, dict) else None,
                           "mismatch": str(exc)})
    return {"contract": CONTRACT, "units": units, "issues": issues,
            "status": "partial" if issues else "proposed",
            "semantic_review": "pending"}


def understand(model, context):
    # The server determines position. The model receives only the relevant intro.
    source_catalogue(context)
    if context["position"] != ("follow_up" if context["conversation"] else "first"):
        raise ValueError("Conversation position disagrees with original history")
    system = (FIRST if context["position"] == "first" else FOLLOW_UP) + SYSTEM
    payload = {key: deepcopy(value) for key, value in context.items() if key != "position"}
    prompt = Prompt(system=system, user=json.dumps(payload, ensure_ascii=False),
                    operation="core_understanding")
    if (estimate_tokens(system + prompt.user + json.dumps(SCHEMA)) + MAX_OUTPUT
            > model.context_budget(Tier.ROUTINE)):
        raise ContextOverflow("The complete conversation exceeds the model context budget")
    try:
        result = model.structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=MAX_OUTPUT)
    except SchemaViolation as exc:
        # Only the port's unambiguous completed quarantine is eligible for this
        # explicit per-unit check. Its semantics remain unadmitted below.
        if exc.rejected_result is None:
            raise
        result = exc.rejected_result
    if not result.usable or result.data is None:
        raise ModelError("Understanding did not complete", usage=result.usage,
                         latency_ms=result.latency_ms, retries=result.retries)
    return accept(result.data, context)
