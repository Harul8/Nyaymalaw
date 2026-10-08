"""Review prepared work privately and release only a greeting or receipt.

This initial release owner does not publish model-authored draft prose, execute
activities, admit facts, or certify that the user's requested task is complete.
The turn owner saves this snapshot and the public response atomically.
"""
from __future__ import annotations

from copy import deepcopy
from functools import partial
import json

from nm.brain.message_labels import validate_label
from nm.brain.disputes_objectives import (
    CONTRACT as EXTRACTION_CONTRACT, LEGACY_CONTRACT as LEGACY_EXTRACTION_CONTRACT,
    PASSAGE_LEGACY_CONTRACT as PASSAGE_LEGACY_EXTRACTION_CONTRACT,
    WORDING_OPERATIONS, check_targets, extraction_units, _passage_input, _check_item,
    _presented_saved,
)
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)


RENDERER_VERSION = "initial_brain_release_v2"
# Every rendering version below is bound to exactly one extraction contract (see
# _EXTRACTION_CONTRACTS), so a saved reply is re-checked with the passages it was
# reviewed against. v5-v7 review records cut by sentence; v2-v4 records cut at
# every mark; v1 records carry model-copied quotes. v7 also asks the user to
# confirm each objective NM worded; v6 replies keep their original rendering.
EXTRACTION_RENDERER = "disputes_objectives_release_v5"
PASSAGE_REVIEW_RENDERER = "disputes_objectives_release_v7"
UNCONFIRMED_REVIEW_RENDERER = "disputes_objectives_release_v6"
PASSAGE_LEGACY_EXTRACTION_RENDERER = "disputes_objectives_release_v2"
PASSAGE_LEGACY_REVIEW_RENDERER = "disputes_objectives_release_v4"
LEGACY_EXTRACTION_RENDERER = "disputes_objectives_release_v1"
LEGACY_PASSAGE_REVIEW_RENDERER = "disputes_objectives_release_v3"
_PASSAGE_REVIEW_SYSTEM = """Message: You receive the complete attributed earlier
conversation followed by the current user message, as exact ordered passages
with code-owned IDs. Private proposals follow the originals. Proposals and NM
wording are interpretations, not original evidence.

Purpose: Independently read the latest original message and check whether its
dispute/objective extraction is accurate and complete.

Look for:
1. Read the current words in their full original context. A dispute contribution
   reports adverse conduct or incompatible party positions in the underlying
   situation. It needs no express denial, legal label or proof. An objective
   contribution expresses whose substantive result is wanted in that situation.
   Examine these independently. A desired result does not replace the reported
   conflict it addresses. Separate meanings requiring independent decisions.
   Opposing accounts of the same conduct, and a defence, proof gap or missing
   evidence, belong to the dispute they concern and are represented by it.
2. Preserve changes to previously reported disputes or objectives: resolved
   means reported resolution or satisfaction; withdrawn means the position or
   desired result is no longer maintained; changed means revised content;
   reported means introduced or continued content. Agreement alone does not
   establish a previous conflict. Do not invent a goal from an event. When
   saved_items are supplied, each proposal states its operation (new, adds,
   corrects, contradicts, confirms, resolves or withdraws) and the saved item it
   changes: an unsupported operation or wrong saved item makes the proposal
   unsupported. Confirms is supported only when the current words affirm NM's
   wording of that saved objective, such as yes to NM's question about it.
3. NM work, social exchange and ordinary facts without either contribution are
   outside this extraction. Anything the user wants NM to do - record, note,
   remember, review, summarise, advise or draft - is NM work and never an
   objective, however it is phrased. History clarifies current references, not a backlog
   to repeat. An explicit request to correct NM's understanding permits
   interpretation_repair: describe the restored original dispute or objective,
   not the repair request. Earlier original account supplies support; the current
   instruction and NM wording supply context only. NM's misunderstanding is not
   a party dispute in the underlying situation.
4. Preserve attribution, uncertainty, conditions, negation and hypothetical scope.
   Select original words supporting the whole description and needed context.
   Compare each proposed unit with its selected original support. Do not add
   facts, legal merit, unexpressed objectives or completed work.

Outcome: Return readings first, then unit_reviews and greeting. Readings has one
entry for every supplied current passage ID. Each entry lists its coherent
meanings as decisions, each with exactly one kind. For a dispute or objective,
describe the original contribution, its contribution type, support_passage_ids,
context_passage_ids and uncertainty; then select represented_by: the smallest
set of proposed IDs in that same category whose descriptions jointly represent
this whole meaning and share its original support. An empty represented_by
means this contribution was missed. Another category cannot represent it.
Outside_scope has purpose=nm_work, social, background or other and a concise
reason; it never means a missing item. Allow several decisions for distinct
meanings in one passage; select other original passages where meaning crosses
boundaries. Review every proposed unit exactly once: supported has ID/verdict
only; unsupported or unresolved also gives its consequential reason. Select
greeting only when a greeting response is appropriate. All extraction and review
remain private. Return no public text, admitted facts or execution claims."""
_EXTRACTION_SYSTEM = """Message: You receive the complete original conversation,
then private dispute/objective proposals and any held items. Sources retain
their exact words and speakers. Proposals are interpretations, not evidence.

Purpose: Independently check the support and completeness of this turn's
dispute/objective extraction. No general facts, plans or answers are requested.

Look for:
1. Read the latest message in its full original context before the proposals.
   Locate its substantive contributions, including changes to earlier positions.
   A request to use existing content for NM's work does not assert, reaffirm or
   change that content. History supplies context for contributions, not a recap.
   A dispute is an expressed disagreement, contested conduct, claim, refusal or
   unresolved conflict affecting someone's position in the underlying situation.
   A matter objective is a party's desired substantive result in that situation.
   Producing an NM output or controlling how NM works is a work instruction, not
   that result. Where a work request also states a matter objective, review only
   the separately supported objective. Either collection may be empty.
2. Check each description against its selected support and the original context.
   Selected support must cover the complete description. Correct information
   elsewhere in the conversation cannot fill a missing support selection.
   The latest words must communicate, confirm, revise or withdraw the item, or
   specifically ask to check the accuracy of NM's saved interpretation. Mere continuity, social
   exchange or diversion cannot renew an item from history. Reject that mismatch
   as scope even when the historical item itself was correctly understood.
   Preserve attribution, scope, conditions, uncertainty, corrections, withdrawals
   and negation. Exact quotation alone does not establish correct interpretation.
   A request to check that interpretation may authorise repair using earlier original account;
   it supplies context, not the restored fact. NM's wording cannot substantiate
   itself. Do not demand a fresh factual assertion for an authorised repair.
3. Mark each item supported, unsupported or unresolved, with the consequential
   reason. Independently report any dispute or objective in the latest message
   that the preparation missed, including when the proposed lists are empty.
   Explicit resolution, correction and withdrawal are contributions even when
   no outcome is still sought. Check each distinct meaning; a selected passage
   mentioning a change does not represent it unless the description captures it.
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


def _passage_review_schema(sources, units, contract):
    presented, choices = _passage_input(sources, contract)
    roles = {source["id"]: source["message"]["role"] for source in sources}
    support = [identity for identity, span in choices.items() if roles[span["source_id"]] == "advocate"]

    def identities(values, minimum=0):
        return {"type": "array", "minItems": minimum,
                "items": {"type": "string", "enum": values}}

    text = {"type": "string", "minLength": 1}
    decisions = []
    for category in ("dispute", "objective"):
        owned = [identity for identity, unit in units.items() if unit["kind"] == category + "s"]
        properties = {
            "kind": {"type": "string", "enum": [category]},
            "contribution": {"type": "string", "enum": ["reported", "changed", "resolved", "withdrawn", "interpretation_repair"]},
            "description": text, "support_passage_ids": identities(support, 1),
            "context_passage_ids": identities(list(choices)),
            "uncertainty": {"type": ["string", "null"]},
            "represented_by": identities(owned) if owned else {
                "type": "array", "maxItems": 0, "items": {"type": "string"}},
        }
        decisions.append({"type": "object", "additionalProperties": False,
                          "required": list(properties), "properties": properties})
    decisions.append({"type": "object", "additionalProperties": False,
        "required": ["kind", "purpose", "reason"], "properties": {
            "kind": {"type": "string", "enum": ["outside_scope"]},
            "purpose": {"type": "string", "enum": ["nm_work", "social", "background", "other"]},
            "reason": text}})
    current = [identity for identity, span in choices.items() if span["source_id"] == "current"]
    identity = {"type": "string", "enum": list(units)} if units else text
    accepted = {"type": "object", "additionalProperties": False,
        "required": ["unit_id", "verdict"], "properties": {
            "unit_id": identity, "verdict": {"type": "string", "enum": ["supported"]}}}
    rejected = {"type": "object", "additionalProperties": False,
        "required": ["unit_id", "verdict", "reason"], "properties": {
            "unit_id": identity, "verdict": {"type": "string", "enum": ["unsupported", "unresolved"]},
            "reason": {"type": "string", "enum": _REASONS[1:]}}}
    reviews = {"type": "array", "items": {"anyOf": [accepted, rejected]}}
    if not units:
        reviews["maxItems"] = 0
    schema = {"type": "object", "additionalProperties": False,
        "required": ["readings", "unit_reviews", "greeting"], "properties": {
            "readings": {"type": "object", "additionalProperties": False,
                "required": current, "properties": {
                    identity: {"type": "array", "minItems": 1, "items": {"anyOf": decisions}}
                    for identity in current}},
            "unit_reviews": reviews, "greeting": {"type": "boolean"}}}
    return schema, presented, choices


def _passage_review_findings(proof, sources, units, *, contract, isolate_associations=True):
    """Check selected source/record bindings; never certify their semantic meaning."""
    schema, _, choices = _passage_review_schema(sources, units, contract)
    require_schema(proof, schema)
    verdicts = {}
    for row in proof["unit_reviews"]:
        if row["unit_id"] in verdicts:
            raise SchemaViolation(f"Review repeats owned unit {row['unit_id']}")
        verdicts[row["unit_id"]] = row["verdict"]
    if set(verdicts) != set(units):
        raise SchemaViolation("Review must examine every owned unit exactly once")
    catalogue = {source["id"]: source["message"] for source in sources}
    missing, represented_units = [], set()
    for anchor, decisions in proof["readings"].items():
        for index, decision in enumerate(decisions, 1):
            if decision["kind"] == "outside_scope":
                if not decision["reason"].strip():
                    raise SchemaViolation(f"Outside-scope reading {anchor} needs its substantive reason")
                continue
            support = list(dict.fromkeys(decision["support_passage_ids"]))
            context = list(dict.fromkeys([*decision["context_passage_ids"], anchor]))
            passages = [{**deepcopy(choices[identity]), "passage_id": identity, "purpose": "support"}
                        for identity in support]
            passages.extend({**deepcopy(choices[identity]), "passage_id": identity, "purpose": "context"}
                            for identity in context if identity not in support)
            checked = _check_item({"description": decision["description"], "passages": passages,
                                   "uncertainty": decision["uncertainty"]}, catalogue, contract)
            represented = list(dict.fromkeys(decision["represented_by"]))
            binding_issues = []
            for identity in represented:
                # Context and verdicts alone cannot bind another meaning to a
                # record. Shared original support permits legitimate repetition
                # and authorised repair without inventing another fact record.
                spans = units[identity]["proposal"]["passages"]
                if not any(span["purpose"] == "support" and selected["purpose"] == "support"
                           and span["source_id"] == selected["source_id"]
                           and span["start"] < selected["end"] and selected["start"] < span["end"]
                           for span in spans for selected in checked["passages"]):
                    binding_issues.append({"unit_id": identity,
                        "reason": "The selected record shares no original support with this reading; context alone cannot represent it."})
                else:
                    represented_units.add(identity)
            if binding_issues and not isolate_associations:
                raise SchemaViolation(f"Reading {anchor} has a rejected original-support association")
            if binding_issues or not represented or any(verdicts[identity] != "supported" for identity in represented):
                missing.append({"id": f"{anchor}:{index}", "kind": decision["kind"] + "s",
                    "contribution": decision["contribution"], **checked,
                    **({"rejected_associations": binding_issues} if binding_issues else {})})
    unbound = [identity for identity, verdict in verdicts.items()
               if verdict == "supported" and identity not in represented_units]
    if unbound:
        raise SchemaViolation("Supported units have no in-scope current reading: " + ", ".join(unbound))
    return missing


def extraction_review_gaps(release):
    """Return owned missing interpretations for bounded turn-level recovery."""
    version = release.get("renderer_version")
    if version not in _PASSAGE_REVIEWS:
        return []
    return _passage_review_findings(release["proof"], release["sources"], release["units"],
        contract=_EXTRACTION_CONTRACTS[version],
        isolate_associations=version != LEGACY_PASSAGE_REVIEW_RENDERER)


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


def _confirmation_question(units, proof):
    """Ask the user to confirm each objective NM worded and the review accepted.

    The question is code-owned around NM's short title and states that it is
    NM's understanding; disputes are never put to the user to confirm.
    """
    accepted = {row["unit_id"] for row in proof["unit_reviews"] if row["verdict"] == "supported"}
    titles = [unit["proposal"]["title"] for identity, unit in units.items()
              if identity in accepted and unit["kind"] == "objectives"
              and unit["proposal"].get("operation") in WORDING_OPERATIONS]
    if not titles:
        return None
    if len(titles) == 1:
        return f"I've noted this aim: “{titles[0]}”. Is that right?"
    return "I've noted these aims: " + "; ".join(f"“{title}”" for title in titles) + ". Are they right?"


def _render_passage_review(sources, units, issues, proof, *, contract, isolate_associations=True,
                           confirm=False):
    missing = _passage_review_findings(proof, sources, units, contract=contract,
                                       isolate_associations=isolate_associations)
    unresolved = any(row["verdict"] == "unresolved" for row in proof["unit_reviews"])
    # A checked outside-scope reading can reject a spurious historical/work
    # proposal without converting that proposal into a missing matter item.
    incomplete = bool(issues or missing or unresolved)
    supported = any(row["verdict"] == "supported" for row in proof["unit_reviews"])
    if incomplete and not supported and not proof["greeting"]:
        return [], "A response could not be prepared for this message.", "withheld"
    text = "Hello. How can I help?" if proof["greeting"] else "Message received."
    elements = [_element(text)]
    question = _confirmation_question(units, proof) if confirm else None
    if question:
        elements.append(_element(question))
    return elements, None, "partial" if incomplete else "ready"


_EXTRACTION_CONTRACTS = {
    LEGACY_EXTRACTION_RENDERER: LEGACY_EXTRACTION_CONTRACT,
    PASSAGE_LEGACY_EXTRACTION_RENDERER: PASSAGE_LEGACY_EXTRACTION_CONTRACT,
    LEGACY_PASSAGE_REVIEW_RENDERER: PASSAGE_LEGACY_EXTRACTION_CONTRACT,
    PASSAGE_LEGACY_REVIEW_RENDERER: PASSAGE_LEGACY_EXTRACTION_CONTRACT,
    EXTRACTION_RENDERER: EXTRACTION_CONTRACT,
    UNCONFIRMED_REVIEW_RENDERER: EXTRACTION_CONTRACT,
    PASSAGE_REVIEW_RENDERER: EXTRACTION_CONTRACT,
}
_PASSAGE_REVIEWS = frozenset({LEGACY_PASSAGE_REVIEW_RENDERER, PASSAGE_LEGACY_REVIEW_RENDERER,
                              UNCONFIRMED_REVIEW_RENDERER, PASSAGE_REVIEW_RENDERER})
# The focused (non-passage) review version that a new review of each contract records.
_FOCUSED_RENDERERS = {contract: version for version, contract in _EXTRACTION_CONTRACTS.items()
                      if version not in _PASSAGE_REVIEWS}
_RENDERERS = {"initial_brain_release_v1": _render_v1,
              "initial_brain_release_v2": _render_v2,
              **{version: _render_extraction for version in _FOCUSED_RENDERERS.values()},
              **{version: partial(_render_passage_review, contract=_EXTRACTION_CONTRACTS[version],
                                  isolate_associations=version != LEGACY_PASSAGE_REVIEW_RENDERER,
                                  confirm=version == PASSAGE_REVIEW_RENDERER)
                 for version in _PASSAGE_REVIEWS}}


def prepare_release(model: ModelPort, prepared: dict, label: str, *, passage_review=False,
                    saved=()) -> dict:
    """One independent review. The caller owns correction, saving and release.

    `saved` holds the open saved items the extraction compared against; every
    change a proposal makes must name one of them.
    """
    label = validate_label({"label": label})
    sources, units, issues = _inputs(prepared)
    if "contract" in prepared:
        check_targets(units, saved)
    focused = prepared.get("contract") in _FOCUSED_RENDERERS
    # One assignment per path: a review version can never be left unset.
    version = (PASSAGE_REVIEW_RENDERER if passage_review
               else _FOCUSED_RENDERERS[prepared["contract"]] if focused else RENDERER_VERSION)
    if passage_review:
        if prepared.get("contract") != EXTRACTION_CONTRACT:
            raise SchemaViolation("Passage review needs the current owned passage extraction contract")
        schema, presented, _ = _passage_review_schema(sources, units, EXTRACTION_CONTRACT)
        payload = {"earlier_conversation": presented[:-1], "current_message": presented[-1],
            "proposals": {kind: [{"id": row["id"],
                **{key: row[key] for key in ("title", "operation", "target_id") if key in row},
                "description": row["description"],
                "support_passage_ids": [span["passage_id"] for span in row["passages"] if span["purpose"] == "support"],
                "context_passage_ids": [span["passage_id"] for span in row["passages"] if span["purpose"] == "context"],
                "uncertainty": row["uncertainty"]} for row in rows]
                for kind, rows in prepared["proposal"].items()}, "held_items": issues}
        if saved:
            payload["saved_items"] = _presented_saved(saved)
        system = _PASSAGE_REVIEW_SYSTEM
    else:
        payload = {"original_conversation": sources, "preparation": prepared["proposal"],
                   "held_preparation_units": issues, "permitted_unit_ids": list(units),
                   "permitted_source_ids": [row["id"] for row in sources]}
        if not focused:
            payload["proposed_label"] = label
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
        system = _EXTRACTION_SYSTEM if focused else _SYSTEM
    prompt = Prompt(system=system, user=json.dumps(payload, ensure_ascii=False),
                    operation="review_prepared_response")
    limit = max(2048, len(units) * 160 + len(sources) * 80)
    if passage_review:
        limit = max(limit, len(schema["properties"]["readings"]["properties"]) * 320 + len(units) * 96)
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
        if passage_review:
            _passage_review_findings(result.data, sources, units, contract=EXTRACTION_CONTRACT)
            proof = deepcopy(result.data)
        else:
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
    passage_review = version in _PASSAGE_REVIEWS
    focused = version in _EXTRACTION_CONTRACTS
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
        prepared["contract"] = _EXTRACTION_CONTRACTS[version]
    sources, units, issues = _inputs(prepared)
    if passage_review:
        _passage_review_findings(saved["proof"], sources, units, contract=_EXTRACTION_CONTRACTS[version],
                                 isolate_associations=version != LEGACY_PASSAGE_REVIEW_RENDERER)
        proof = deepcopy(saved["proof"])
    else:
        proof = _checked_proof(saved["proof"], sources, units, focused=focused)
    elements, status, state = _RENDERERS[version](sources, units, issues, proof)
    reconstructed = {"renderer_version": version, "label": label, "sources": sources,
                     "units": units, "issues": issues, "proof": proof, "elements": elements,
                     "service_status": status, "state": state}
    if reconstructed != saved:
        raise SchemaViolation("Saved response differs from its original-source rendering")
    return reconstructed
