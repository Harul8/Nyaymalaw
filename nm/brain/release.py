"""Review prepared work privately and release only a greeting or receipt.

This initial release owner does not publish model-authored draft prose, execute
activities, admit facts, or certify that the user's requested task is complete.
The turn owner saves this snapshot and the public response atomically.
"""
from __future__ import annotations

from copy import deepcopy
import json

from nm.brain.message_labels import validate_label
from nm.brain.disputes_objectives import (
    CONTRACT as EXTRACTION_CONTRACT, LEGACY_CONTRACT as LEGACY_EXTRACTION_CONTRACT,
    extraction_units,
)
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)


RENDERER_VERSION = "initial_brain_release_v2"
EXTRACTION_RENDERER = "disputes_objectives_release_v2"
LEGACY_EXTRACTION_RENDERER = "disputes_objectives_release_v1"
_EXTRACTION_SYSTEM = """Message: You receive the complete original conversation,
then private dispute/objective proposals and any held items. Sources retain
their exact words and speakers. Proposals are interpretations, not evidence.

Purpose: Independently check the support and completeness of this turn's
dispute/objective extraction. No general facts, plans or answers are requested.

Look for:
1. Read the latest message in its full original context before the proposals.
   Identify what it contributes, rather than extracting the history again.
   A dispute is an expressed disagreement, contested conduct, claim, refusal or
   unresolved conflict affecting someone's position in the underlying situation.
   A matter objective is a party's desired substantive result in that situation.
   Producing an NM output or controlling how NM works is a work instruction, not
   that result. Where a work request also states a matter objective, review only
   the separately supported objective. Either collection may be empty.
2. Check each description and selected exact passage against original words.
   The latest words must communicate, confirm, revise or withdraw the item, or
   specifically request review of its interpretation. Mere continuity, social
   exchange or diversion cannot renew an item from history. Reject that mismatch
   as scope even when the historical item itself was correctly understood.
   Preserve attribution, scope, conditions, uncertainty, corrections, withdrawals
   and negation. Exact quotation alone does not establish correct interpretation.
   A current review request may authorise repair using earlier original account;
   it supplies context, not the restored fact. NM's wording cannot substantiate
   itself. Do not demand a fresh factual assertion for an authorised repair.
3. Mark each item supported, unsupported or unresolved, with the consequential
   reason. Independently report any dispute or objective in the latest message
   that the preparation missed, including when the proposed lists are empty.
   Do not demand general facts or work instructions as missing objectives.
4. Select greeting only if a social acknowledgement is appropriate. Only a fixed
   greeting or receipt is public; all extraction and review remain private.

Outcome: Return greeting, unit_reviews and omissions. Review every supplied
unit exactly once using its owned ID, verdict and reason. Supported items use
reason=none; other verdicts identify the mismatch. An omission names its original
source_id and kind=disputes or objectives. Empty arrays are valid where nothing
applies. Return no response text, source rewrites, plans or completion claims.
This review checks extraction, not factual proof, legal merit or execution."""
_SYSTEM = """Message: You receive the complete original conversation in order,
ending with the user's current message, followed by unreviewed preparation.
Sources retain their speaker and exact words. Preparation, its draft and its
labels are proposals, not evidence, permissions or completed work.

Purpose: Independently review the internal preparation against the original
conversation and decide whether a social acknowledgement is appropriate.

Look for:
1. Read original messages first. Identify current information and requests,
   including restrictions, uncertainty, quotations, corrections and references.
   Earlier NM statements are context, not independent evidence of the account.
2. Examine every supplied material/action unit against those original words.
   Mark it supported, unsupported or unresolved. Select only its supplied
   advocate source IDs that support the whole unit; action selections must
   include the current request. Check attribution, scope, conditions and omitted
   distinctions. Do not endorse a proposal merely because its explanation sounds
   plausible. Report significant current information or requests the preparation
   omitted, even if a label suggested otherwise.
3. Select greeting only when a social acknowledgement is appropriate. The code
   displays only a fixed greeting or receipt acknowledgement. Source quotations,
   extracted details, proposed activities, drafts and review findings remain
   internal. The acknowledgement does not claim that the requested work was
   performed, that extraction is complete, or that the account is proved.

Outcome: Return greeting, unit_reviews and omissions using only the supplied
IDs and permitted verdict/reason values. Review every supplied unit once. A
supported unit uses reason=none and source_ids supporting its complete meaning;
otherwise select the consequential mismatch. An omission names its original
source and whether information or action was missed. No response prose, altered
quotes, execution claims or new sources. Empty arrays are valid where nothing
applies. This review does not establish factual truth or task completion."""

_REASONS = ["none", "unsupported_addition", "contradiction", "attribution",
            "scope", "uncertainty", "restriction", "unresolved_reference"]
_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["greeting", "unit_reviews", "omissions"],
    "properties": {
        "greeting": {"type": "boolean"},
        "unit_reviews": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["unit_id", "verdict", "source_ids", "reason"],
            "properties": {
                "unit_id": {"type": "string", "minLength": 1},
                "verdict": {"type": "string", "enum": ["supported", "unsupported", "unresolved"]},
                "source_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "reason": {"type": "string", "enum": _REASONS},
            },
        }},
        "omissions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["source_id", "kind"],
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "kind": {"type": "string", "enum": ["information", "action"]},
            },
        }},
    },
}


def _review_schema(focused=False):
    schema = deepcopy(_SCHEMA)
    if focused:
        item = schema["properties"]["unit_reviews"]["items"]
        item["required"].remove("source_ids")
        del item["properties"]["source_ids"]
        schema["properties"]["omissions"]["items"]["properties"]["kind"]["enum"] = ["disputes", "objectives"]
    return schema


def _inputs(prepared: dict) -> tuple[list[dict], dict, list]:
    if isinstance(prepared, dict) and "contract" in prepared:
        units = extraction_units(prepared)
        return deepcopy(prepared["sources"]), units, deepcopy(prepared["issues"])
    if not isinstance(prepared, dict) or prepared.get("state") != "prepared_unreviewed":
        raise SchemaViolation("Release needs the owned unreviewed preparation")
    sources, proposal, issues = (prepared.get(key) for key in ("sources", "proposal", "issues"))
    if not isinstance(sources, list) or not sources or not isinstance(proposal, dict) or not isinstance(issues, list):
        raise SchemaViolation("Release preparation is incomplete")
    source_ids = []
    for index, source in enumerate(sources):
        expected = "current" if index == len(sources) - 1 else f"history_{index + 1}"
        if (not isinstance(source, dict) or set(source) != {"id", "message"}
                or source["id"] != expected or not isinstance(source["message"], dict)):
            raise SchemaViolation("Release sources need their ordered owned identities")
        message = source["message"]
        if (message.get("role") not in ("advocate", "nm")
                or not isinstance(message.get("text"), str) or not message["text"].strip()
                or expected == "current" and message["role"] != "advocate"):
            raise SchemaViolation("Release sources need their original speaker and words")
        source_ids.append(expected)
    units = {}
    for collection, state in (("material", "proposed"), ("actions", "planned")):
        rows = proposal.get(collection)
        if not isinstance(rows, list):
            raise SchemaViolation("Release needs each preparation collection")
        for unit in rows:
            if (not isinstance(unit, dict) or not isinstance(unit.get("id"), str)
                    or not unit["id"] or unit["id"] in units or unit.get("state") != state
                    or not isinstance(unit.get("source_ids"), list) or not unit["source_ids"]
                    or any(identity not in source_ids for identity in unit["source_ids"])):
                raise SchemaViolation("Release units need owned unique identities and sources")
            units[unit["id"]] = {"kind": collection, "proposal": deepcopy(unit)}
    return deepcopy(sources), units, deepcopy(issues)


def _checked_proof(proof: dict, sources: list[dict], units: dict, *, focused=False) -> dict:
    require_schema(proof, _review_schema(focused))
    originals = {source["id"]: source["message"] for source in sources}
    seen = set()
    checked = deepcopy(proof)
    for review in checked["unit_reviews"]:
        identity = review["unit_id"]
        if identity not in units or identity in seen:
            raise SchemaViolation("Review must name every owned unit exactly once")
        seen.add(identity)
        unit = units[identity]
        selected = ([identity for identity in unit["proposal"]["source_ids"]
                     if originals[identity]["role"] == "advocate"] if focused
                    else list(dict.fromkeys(review["source_ids"])))
        if any(source not in unit["proposal"]["source_ids"] for source in selected):
            raise SchemaViolation(f"Review {identity} selected a source outside its unit")
        if any(originals[source]["role"] != "advocate" for source in selected):
            raise SchemaViolation(f"Review {identity} cannot present NM wording as the account")
        if review["verdict"] == "supported":
            if not selected or review["reason"] != "none":
                raise SchemaViolation(f"Supported review {identity} needs original support and no mismatch")
            if unit["kind"] == "actions" and "current" not in selected:
                raise SchemaViolation(f"Action review {identity} must include its current request")
        elif review["reason"] == "none":
            raise SchemaViolation(f"Unaccepted review {identity} needs its consequential mismatch")
        if not focused:
            review["source_ids"] = selected
    if seen != set(units):
        raise SchemaViolation("Review omitted a supplied preparation unit")
    for omission in checked["omissions"]:
        source = originals.get(omission["source_id"])
        if source is None or source["role"] != "advocate":
            raise SchemaViolation("An omission must identify original advocate content")
    return checked


def _element(text: str) -> dict:
    return {"kind": "finding", "text": text, "thread": None, "by_when": None,
            "no_deadline_reason": None, "signal": "none", "collapsible": False,
            "disclosure": False, "refs": [], "source": None, "section": "answer"}


def _render_v1(sources: list[dict], units: dict, issues: list, proof: dict) -> tuple[list, str | None, str]:
    originals = {source["id"]: source["message"] for source in sources}
    elements = [_element("Hello. How can I help?")] if proof["greeting"] else []
    rendered = set()
    actions_selected = False
    for review in proof["unit_reviews"]:
        if review["verdict"] != "supported":
            continue
        kind = units[review["unit_id"]]["kind"]
        for identity in review["source_ids"]:
            key = (kind, identity)
            if key in rendered:
                continue
            rendered.add(key)
            prefix = "You reported" if kind == "material" else "Your requested work"
            elements.append(_element(f"{prefix}: “{originals[identity]['text']}”"))
        actions_selected |= kind == "actions"
    if actions_selected:
        elements.append(_element("This step proposes work only; it does not carry out the requested activities."))
    incomplete = bool(issues or proof["omissions"] or any(
        row["verdict"] != "supported" for row in proof["unit_reviews"]))
    status = ("Some of this message could not be prepared for a response."
              if incomplete and elements else None)
    if not elements:
        return [], "A response could not be prepared for this message.", "withheld"
    return elements, status, "partial" if incomplete else "ready"


def _render_v2(sources: list[dict], units: dict, issues: list, proof: dict) -> tuple[list, str | None, str]:
    supported = any(row["verdict"] == "supported" for row in proof["unit_reviews"])
    if not proof["greeting"] and not supported:
        return [], "A response could not be prepared for this message.", "withheld"
    incomplete = bool(issues or proof["omissions"] or any(
        row["verdict"] != "supported" for row in proof["unit_reviews"]))
    text = "Hello. How can I help?" if proof["greeting"] else "Message received."
    return [_element(text)], None, "partial" if incomplete else "ready"


def _render_extraction(sources: list[dict], units: dict, issues: list, proof: dict) -> tuple[list, str | None, str]:
    # Reviewed absence is different from held proposals or missed extraction.
    if not units and not issues and not proof["omissions"] and not proof["greeting"]:
        return [_element("Message received.")], None, "ready"
    return _render_v2(sources, units, issues, proof)


_RENDERERS = {"initial_brain_release_v1": _render_v1,
              "initial_brain_release_v2": _render_v2,
              LEGACY_EXTRACTION_RENDERER: _render_extraction,
              EXTRACTION_RENDERER: _render_extraction}


def prepare_release(model: ModelPort, prepared: dict, label: str) -> dict:
    """One independent review. The caller owns correction, saving and release."""
    label = validate_label({"label": label})
    sources, units, issues = _inputs(prepared)
    focused = prepared.get("contract") in (EXTRACTION_CONTRACT, LEGACY_EXTRACTION_CONTRACT)
    version = (EXTRACTION_RENDERER if prepared.get("contract") == EXTRACTION_CONTRACT
               else LEGACY_EXTRACTION_RENDERER if focused else RENDERER_VERSION)
    payload = {"original_conversation": sources, "preparation": prepared["proposal"],
               "held_preparation_units": issues,
               "permitted_unit_ids": list(units),
               "permitted_source_ids": [row["id"] for row in sources]}
    if not focused:
        payload["proposed_label"] = label
    prompt = Prompt(system=_EXTRACTION_SYSTEM if focused else _SYSTEM, user=json.dumps(payload, ensure_ascii=False),
                    operation="review_prepared_response")
    schema = _review_schema(focused)
    reviews = schema['properties']['unit_reviews']
    if units:
        reviews['items']['properties']['unit_id']['enum'] = list(units)
    else:
        reviews['maxItems'] = 0
    originals = [row['id'] for row in sources if row['message']['role'] == 'advocate']
    if not focused:
        reviews['items']['properties']['source_ids']['items']['enum'] = originals
    schema['properties']['omissions']['items']['properties']['source_id']['enum'] = originals
    limit = max(2048, len(units) * 160 + len(sources) * 80)
    size = estimate_tokens(prompt.system + prompt.user + json.dumps(schema))
    if size + limit > model.context_budget(Tier.ROUTINE):
        raise ContextOverflow("The complete response review exceeds the model context budget")
    result = model.structured(prompt, schema, Tier.ROUTINE, max_tokens=limit)
    if not result.usable:
        raise ModelError("Response review did not complete", usage=result.usage,
                         latency_ms=result.latency_ms, retries=result.retries)
    try:
        if result.text is not None:
            raise SchemaViolation("Response review requires owned selectors, not public prose")
        proof = _checked_proof(result.data, sources, units, focused=focused)
    except SchemaViolation as exc:
        raise SchemaViolation(str(exc), usage=result.usage, latency_ms=result.latency_ms,
                              retries=result.retries) from exc
    elements, status, state = _RENDERERS[version](sources, units, issues, proof)
    return {"renderer_version": version, "label": label, "sources": sources,
            "units": units, "issues": issues, "proof": proof, "elements": elements,
            "service_status": status, "state": state}


def render_saved_release(saved: dict) -> dict:
    """Validate and reconstruct a saved version; never re-review or upgrade it.

    The authenticated store owns durable integrity and matter ownership. This
    function checks that saved display fields still match their exact sources,
    selectors and rendering version; it cannot establish semantic truth anew.
    """
    fields = {"renderer_version", "label", "sources", "units", "issues", "proof",
              "elements", "service_status", "state"}
    if not isinstance(saved, dict) or set(saved) != fields:
        raise SchemaViolation("Saved release has an unknown envelope")
    version = saved["renderer_version"]
    if not isinstance(version, str) or version not in _RENDERERS:
        raise SchemaViolation("Saved response rendering version is unsupported")
    label = validate_label({"label": saved["label"]})
    if not isinstance(saved["units"], dict):
        raise SchemaViolation("Saved release unit catalogue is unreadable")
    focused = version in (EXTRACTION_RENDERER, LEGACY_EXTRACTION_RENDERER)
    proposal = {"disputes": [], "objectives": []} if focused else {"material": [], "actions": []}
    for identity, row in saved["units"].items():
        if (not isinstance(row, dict) or set(row) != {"kind", "proposal"}
                or not isinstance(row["kind"], str) or row["kind"] not in proposal
                or not isinstance(row["proposal"], dict)
                or row["proposal"].get("id") != identity):
            raise SchemaViolation("Saved release unit catalogue is inconsistent")
        proposal[row["kind"]].append(row["proposal"])
    prepared = {"state": "prepared_unreviewed", "sources": saved["sources"],
                "proposal": proposal, "issues": saved["issues"]}
    if focused:
        prepared["contract"] = (EXTRACTION_CONTRACT if version == EXTRACTION_RENDERER
                                else LEGACY_EXTRACTION_CONTRACT)
    sources, units, issues = _inputs(prepared)
    proof = _checked_proof(saved["proof"], sources, units, focused=focused)
    elements, status, state = _RENDERERS[version](sources, units, issues, proof)
    reconstructed = {"renderer_version": version, "label": label, "sources": sources,
                     "units": units, "issues": issues, "proof": proof, "elements": elements,
                     "service_status": status, "state": state}
    if reconstructed != saved:
        raise SchemaViolation("Saved response differs from its original-source rendering")
    return reconstructed
