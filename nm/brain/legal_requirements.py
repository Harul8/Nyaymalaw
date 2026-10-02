"""Source-linked search plans and legal-material requirements for disputes."""
from __future__ import annotations

import json

from nm.brain.checked import checked_read
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    OutputTruncated,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
)

_DECOMPOSE_SYSTEM = """Message: The input contains the complete ordered,
attributed conversation, active dispute formulations, and material already
linked to each dispute. The advocate's account and described records are not
verified. A search phrase is a retrieval hypothesis, not a finding.

Purpose: Produce complementary queries for finding candidate bare-Act sections
and judgment passages for each supplied dispute. This call does not decide
which law applies or what the advocate must prove or gather.

Look for: The conduct and contested relationship, relevant timing and place
when stated, the practical outcome, and material that changes the legal
question. Use several genuinely different entry points, including the
advocate's concrete words and plausible legal terminology. A legal term can
be explored in a query without being asserted as a fact or applicable rule.
Do not import another dispute's facts, assume a jurisdiction or statute, or
expand a hypothetical into an event. Avoid near-duplicate formulations.

Outcome: Return only the declared JSON object. Return exactly one plan per
supplied dispute ID and preferably three or four distinct, concise queries
per plan, never more than four. When the record cannot ground that many
different useful queries, return fewer. Keep each plan's queries grounded in
that dispute and its linked material. Do not cite an unsupplied source, invent
an incident, or present a query as legal advice."""


_REQUIREMENTS_SYSTEM = """Message: The input contains the complete ordered,
attributed conversation, each active dispute and its linked material, and
candidate bare-Act sections and judgment passages retrieved for that dispute.
Each candidate has an ID, exact passage, and locator. Retrieval ranks are
search signals, not findings of applicability or legal support. The
advocate's account and any described records remain unverified.

Purpose: Identify source-supported things to establish, obtain, or check for
each dispute so the advocate can test and strengthen the case. This is a
proposed work record, not a conclusion that a claim succeeds.

Look for: What a potentially applicable provision actually mandates, its
conditions, exceptions, timing and procedural requirements; what a judgment
actually decides or explains, including limits or adverse reasoning; and
which facts or records would address those points in this dispute. Distinguish
a legally required step or element from material that would strengthen proof
or answer a possible objection. Do not promote a judgment's passing statement
or a search score into a binding rule. Do not apply a provision or judgment
when the supplied passage does not support the proposed need in this factual
and temporal context. A retrieved passage alone may not establish an in-force
statutory version, jurisdictional reach, precedent treatment, or binding
weight; express legal force conditionally when applicability is unverified.
Treat mentioned documents as reported, not inspected.

Outcome: Return only the declared JSON object. For each useful, supported
item, give a short actionable `label` suitable for a bullet under its
dispute, a fuller `need`, and a concise `why` tied to the cited passage.
Choose `force` as `required` only when the cited text establishes a mandatory
legal condition or step for the proposed applicability; otherwise use
`strengthening`. Select one or more `source_ids` from that dispute's supplied
passages; the server will attach their exact text and locators. Select
`material_ids` only for supplied attributed material that explicitly addresses
the item; an ID does not prove that the item is satisfied. Leave them empty
when the record has not addressed it. Do not invent a document type, rule,
holding, fact, citation, or source passage. If no candidate passage supports
a useful item, return no item for that dispute."""


_VERIFY_SYSTEM = """Message: The input contains the complete ordered,
attributed conversation, active disputes and linked material, and proposed
legal work items with the exact passages each item cites. The items are
untrusted proposals. Search rank and a citation ID do not establish support.

Purpose: Independently decide whether each cited passage actually supports
the proposed item's entire displayed label, need, why, and claimed legal force in the dispute's
factual and temporal context. This call decides which proposals may enter the
source-linked work record; it does not decide the merits of a dispute.

Look for: Examine EACH cited passage separately, including any limiting words
that define the kind of transaction, party, remedy, procedure, legal period,
or prerequisite to which it speaks. Compare those predicates with attributed
facts before judging the proposed item. If a necessary predicate is absent or
unknown, a passage supports the item only when the item itself asks to
establish that predicate or expressly states its conditional applicability.
`no_special_condition` describes the passage, not silence in the user's
account; do not use it when the passage
limits its rule. Shared vocabulary is not support; a
passage about a different legal setting cannot be stretched to this dispute.
For a judgment, distinguish the actual reasoning from a party's argument,
background, and an expressly hypothetical proposition. For a `required`
item, check that cited authority establishes a mandatory condition or step
under a potentially applicable rule; usefulness alone supports at most a
`strengthening` item. Treat reported documents as uninspected. Do not fill
gaps from legal memory, uncited sources, or another dispute. Check that the
short board label faithfully states the same source-supported need without
adding a new legal or factual proposition. Separately check every selected
material ID against its attributed words: it addresses the item only if the
reported detail explicitly concerns that need. A document merely said to be
held is not proof of its contents or satisfaction of a legal element. An
incorrect material link does not invalidate an otherwise supported need. If a
passage is fragmentary or its scope cannot be established, mark it uncertain.

Outcome: Return only the declared JSON object. For EACH candidate, return one
overall decision, a separate label decision, one check for EVERY selected
material ID, and one separate check for EVERY cited source ID. Each source
is displayed as numbered, overlapping, exact fragments of its saved passage.
Select a `support_fragment_id` from THAT source only when its words directly
support the full proposed item; otherwise use an empty ID. Select a
`scope_fragment_id` from THAT source when its words state a material limiting
predicate; use an empty ID only when there is no such predicate. A fragment
may serve both purposes. Do not copy passage text or invent an ID.
Classify whether that scope is established by the record, explicitly asked to
be established by the item, absent from the record, a different legal setting,
or impossible to determine. Mark a source `supported` only when its own exact
words support the item and the relevant scope is established, asked to be
established, or has no special condition. Mark the overall item `supported`
only if the retained source checks together support its entire need, why, and
force without an unstated premise and the label is faithful. Otherwise mark it `unsupported` or
`uncertain`. Give a short explanation for every decision. The server resolves
selected IDs to exact saved text, removes unsupported material links, and
withholds rejected items.
No verdict proves the advocate's account or the source's binding status."""


def _conversation_rows(conversation: tuple[object, ...]) -> list[dict]:
    rows = []
    for message in conversation:
        turn_id = getattr(message, "turn_id", None)
        role = getattr(message, "role", None)
        words = getattr(message, "text", None)
        if (not isinstance(turn_id, str) or not turn_id
                or role not in ("advocate", "nm")
                or not isinstance(words, str)):
            raise SchemaViolation("The supplied conversation is not attributable")
        rows.append({"turn_id": turn_id, "role": role, "text": words})
    return rows


def _dispute_input(disputes: tuple[dict, ...],
                   material_by_dispute: dict[str, list[dict]]
                   ) -> tuple[list[dict], dict[str, set[str]]]:
    rows = []
    known: dict[str, set[str]] = {}
    for dispute in disputes:
        if not isinstance(dispute, dict):
            raise SchemaViolation("A supplied dispute is invalid")
        dispute_id = dispute.get("id")
        if (not isinstance(dispute_id, str) or not dispute_id
                or dispute_id in known):
            raise SchemaViolation("A dispute needs a unique saved ID")
        material = material_by_dispute.get(dispute_id, [])
        if not isinstance(material, (list, tuple)):
            raise SchemaViolation("A dispute's attributed material is invalid")
        known[dispute_id] = set()
        linked = []
        for item in material:
            if not isinstance(item, dict):
                raise SchemaViolation("A linked material item is invalid")
            item_id = item.get("id")
            if (not isinstance(item_id, str) or not item_id
                    or item_id in known[dispute_id]):
                raise SchemaViolation("Linked material needs unique saved IDs")
            known[dispute_id].add(item_id)
            linked.append({key: item.get(key) for key in (
                "id", "kind", "statement", "quoted", "basis", "source_turn_id")})
        rows.append({"dispute": {key: dispute.get(key) for key in (
            "id", "label", "statement", "quoted", "identification",
            "source_turn_id")}, "material": linked})
    if set(material_by_dispute) - set(known):
        raise SchemaViolation("Material is linked to an unknown dispute")
    return rows, known


def _prompt(system: str, operation: str, payload: dict,
            model: ModelPort, output_limit: int, schema: dict) -> Prompt:
    prompt = Prompt(system=system,
                    user=json.dumps(payload, ensure_ascii=False,
                                    separators=(",", ":")),
                    operation=operation)
    # Structured-output instructions consume the same context as the input.
    schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    if (estimate_tokens(prompt.user + (prompt.system or "") + schema_text)
            + output_limit
            > model.context_budget(Tier.ROUTINE)):
        raise ContextOverflow(
            "The complete conversation and dispute group exceed the model context budget")
    return prompt


def _ordered_batches(rows: list[dict], prepare):
    """Make the fewest consecutive complete groups that fit the model budget.

    Every group repeats the full conversation. Preflight single disputes first
    so no model call occurs if any one complete dispute cannot fit.
    """
    try:
        return [prepare(rows)]
    except ContextOverflow:
        pass
    singles = [prepare([row]) for row in rows]
    batches = []
    start = 0
    while start < len(rows):
        largest = singles[start]
        end = start + 1
        while end < len(rows):
            try:
                candidate = prepare(rows[start:end + 1])
            except ContextOverflow:
                break
            largest = candidate
            end += 1
        batches.append(largest)
        start = end
    return batches


def _decomposition_schema(dispute_ids: tuple[str, ...]) -> dict:
    query = {
        "type": "object", "additionalProperties": False,
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
        },
    }
    plan = {
        "type": "object", "additionalProperties": False,
        "required": ["dispute_id", "queries"],
        "properties": {
            "dispute_id": {"type": "string", "enum": list(dispute_ids)},
            "queries": {"type": "array", "minItems": 1, "maxItems": 4,
                        "items": query},
        },
    }
    return {"type": "object", "additionalProperties": False,
            "required": ["plans"],
            "properties": {"plans": {"type": "array", "items": plan}}}


def decompose(model: ModelPort, *, disputes: tuple[dict, ...],
              material_by_dispute: dict[str, list[dict]],
              conversation: tuple[object, ...]) -> dict[str, tuple[str, ...]]:
    """Plan grounded searches in as few complete-context calls as fit."""
    dispute_rows, _ = _dispute_input(disputes, material_by_dispute)
    if not dispute_rows:
        return {}
    conversation_rows = _conversation_rows(conversation)

    def prepare(group: list[dict]):
        ids = tuple(row["dispute"]["id"] for row in group)
        payload = {"conversation": conversation_rows, "disputes": group}
        output_limit = min(12288, max(3072, len(ids) * 1024))
        schema = _decomposition_schema(ids)
        prompt = _prompt(_DECOMPOSE_SYSTEM, "decompose_disputes", payload,
                         model, output_limit, schema)
        return ids, prompt, schema, output_limit

    combined: dict[str, tuple[str, ...]] = {}
    for ids, prompt, schema, output_limit in _ordered_batches(
            dispute_rows, prepare):
        def accept(data: dict, ids=ids) -> dict[str, tuple[str, ...]]:
            plans = data["plans"]
            if len(plans) != len(ids):
                raise SchemaViolation(
                    "Search plans must cover every supplied dispute once")
            result = {}
            for plan in plans:
                dispute_id = plan["dispute_id"]
                if dispute_id in result:
                    raise SchemaViolation("A dispute has duplicate search plans")
                texts = []
                for query in plan["queries"]:
                    phrase = query["text"].strip()
                    if not phrase or len(phrase) > 300:
                        raise SchemaViolation("A search query must be concise and nonempty")
                    if phrase.casefold() in {item.casefold() for item in texts}:
                        raise SchemaViolation("A dispute has duplicate search queries")
                    texts.append(phrase)
                result[dispute_id] = tuple(texts)
            return result

        combined.update(checked_read(model, prompt, schema, output_limit, accept))
    return combined


def _requirements_schema(dispute_ids: tuple[str, ...],
                         source_ids: tuple[str, ...],
                         material_ids: tuple[str, ...]) -> dict:
    row = {
        "type": "object", "additionalProperties": False,
        "required": ["dispute_id", "label", "need", "why", "force",
                     "source_ids", "material_ids"],
        "properties": {
            "dispute_id": {"type": "string", "enum": list(dispute_ids)},
            "label": {"type": "string", "minLength": 1},
            "need": {"type": "string", "minLength": 1},
            "why": {"type": "string", "minLength": 1},
            "force": {"type": "string", "enum": ["required", "strengthening"]},
            "source_ids": {"type": "array", "minItems": 1,
                           "items": {"type": "string", "enum": list(source_ids)}},
            "material_ids": {"type": "array",
                             "items": {"type": "string", "enum": list(material_ids)}},
        },
    }
    return {"type": "object", "additionalProperties": False,
            "required": ["requirements"],
            "properties": {"requirements": {"type": "array", "items": row}}}


def read_requirements(model: ModelPort, *, disputes: tuple[dict, ...],
                      material_by_dispute: dict[str, list[dict]],
                      search_results: dict[str, dict],
                      conversation: tuple[object, ...]) -> dict[str, list[dict]]:
    """Read candidate passages once; attach only exact retrieved sources."""
    dispute_rows, material_ids = _dispute_input(disputes, material_by_dispute)
    ids = tuple(material_ids)
    if set(search_results) - set(ids):
        raise SchemaViolation("Search results name an unknown dispute")
    result: dict[str, list[dict]] = {dispute_id: [] for dispute_id in ids}
    if not ids:
        return result
    hits: dict[str, dict[str, dict]] = {}
    for dispute_id in ids:
        search = search_results.get(dispute_id)
        if not isinstance(search, dict) or search.get("state") not in (
                "ok", "partial", "unavailable"):
            raise SchemaViolation("Dispute search has no reliable state")
        candidates = search.get("candidates")
        if not isinstance(candidates, list):
            raise SchemaViolation("Dispute search candidates are invalid")
        hits[dispute_id] = {}
        if search["state"] == "unavailable":
            if candidates:
                raise SchemaViolation("Unavailable search cannot provide candidate passages")
            continue
        for hit in candidates:
            if not isinstance(hit, dict):
                raise SchemaViolation("A retrieved passage is invalid")
            hit_id = hit.get("id")
            if (not isinstance(hit_id, str) or not hit_id
                    or hit_id in hits[dispute_id]
                    or hit.get("kind") not in ("provision", "judgment")
                    or any(not isinstance(hit.get(key), str) or not hit[key].strip()
                           for key in ("title", "locator", "text"))):
                raise SchemaViolation("A retrieved passage needs a unique exact locator")
            hits[dispute_id][hit_id] = hit
    active_rows = [row for row in dispute_rows
                   if hits[row["dispute"]["id"]]]
    if not active_rows:
        return result
    for row in active_rows:
        dispute_id = row["dispute"]["id"]
        row["candidates"] = list(hits[dispute_id].values())
    conversation_rows = _conversation_rows(conversation)

    def prepare(group: list[dict]):
        group_ids = tuple(row["dispute"]["id"] for row in group)
        source_ids = tuple(dict.fromkeys(
            hit_id for dispute_id in group_ids for hit_id in hits[dispute_id]))
        group_material_ids = tuple(dict.fromkeys(
            item["id"] for row in group for item in row["material"]))
        payload = {"conversation": conversation_rows, "disputes": group}
        output_limit = min(16384, max(4096, len(source_ids) * 384))
        schema = _requirements_schema(
            group_ids, source_ids, group_material_ids)
        prompt = _prompt(_REQUIREMENTS_SYSTEM, "read_legal_requirements",
                         payload, model, output_limit, schema)
        return group_ids, prompt, schema, output_limit

    for group_ids, prompt, schema, output_limit in _ordered_batches(
            active_rows, prepare):
        def accept(data: dict, group_ids=group_ids) -> dict[str, list[dict]]:
            read = {dispute_id: [] for dispute_id in group_ids}
            seen: set[tuple[str, str]] = set()
            for row in data["requirements"]:
                dispute_id = row["dispute_id"]
                sources = row["source_ids"]
                linked = row["material_ids"]
                label, need, why = (
                    row[key].strip() for key in ("label", "need", "why"))
                if not label or len(label) > 120 or not need or not why:
                    raise SchemaViolation(
                        "A requirement needs a short label and explanation")
                if (len(sources) != len(set(sources))
                        or not set(sources) <= set(hits[dispute_id])):
                    raise SchemaViolation(
                        f"A requirement for dispute {dispute_id!r} cites "
                        "a passage from another dispute")
                if (len(linked) != len(set(linked))
                        or not set(linked) <= material_ids[dispute_id]):
                    raise SchemaViolation(
                        f"A requirement for dispute {dispute_id!r} links unrelated material")
                key = (dispute_id, label.casefold())
                if key in seen:
                    raise SchemaViolation(
                        "A dispute has duplicate requirement labels")
                seen.add(key)
                read[dispute_id].append({
                    "label": label, "need": need, "why": why,
                    "force": row["force"],
                    "source_ids": list(sources), "material_ids": list(linked),
                    "sources": [dict(hits[dispute_id][source_id])
                                for source_id in sources],
                    "record_status": "mentioned" if linked else "not_mentioned",
                })
            return read

        result.update(checked_read(model, prompt, schema, output_limit, accept))
    return result


def _passage_fragments(passage: str) -> list[dict[str, str]]:
    """Expose bounded, overlapping exact spans without asking the model to copy."""
    width, overlap = 700, 140
    fragments = []
    start = 0
    while start < len(passage):
        fragments.append({"id": f"f{len(fragments) + 1}",
                          "text": passage[start:start + width]})
        if start + width >= len(passage):
            break
        start += width - overlap
    return fragments


def _verification_schema(candidate_ids: tuple[str, ...],
                         source_ids: tuple[str, ...],
                         fragment_ids: tuple[str, ...],
                         material_ids: tuple[str, ...]) -> dict:
    source_check = {
        "type": "object", "additionalProperties": False,
        "required": ["source_id", "support_fragment_id", "scope_fragment_id",
                     "scope_status", "verdict", "reason"],
        "properties": {
            "source_id": {"type": "string", "enum": list(source_ids)},
            "support_fragment_id": {"type": "string",
                                    "enum": ["", *fragment_ids]},
            "scope_fragment_id": {"type": "string",
                                  "enum": ["", *fragment_ids]},
            "scope_status": {"type": "string", "enum": [
                "established", "asked_to_establish", "not_established",
                "different_legal_setting", "cannot_determine",
                "no_special_condition"]},
            "verdict": {"type": "string", "enum": [
                "supported", "unsupported", "uncertain"]},
            "reason": {"type": "string", "minLength": 1},
        },
    }
    decision = {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "label_verdict", "label_reason",
                     "material_checks", "source_checks", "verdict", "reason"],
        "properties": {
            "candidate_id": {"type": "string", "enum": list(candidate_ids)},
            "label_verdict": {"type": "string", "enum": [
                "faithful", "unsupported", "uncertain"]},
            "label_reason": {"type": "string", "minLength": 1},
            "material_checks": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["material_id", "verdict", "reason"],
                "properties": {
                    "material_id": {"type": "string", "enum": list(material_ids)},
                    "verdict": {"type": "string", "enum": [
                        "addresses", "does_not_address", "uncertain"]},
                    "reason": {"type": "string", "minLength": 1},
                }}},
            "source_checks": {"type": "array", "items": source_check},
            "verdict": {"type": "string", "enum": [
                "supported", "unsupported", "uncertain"]},
            "reason": {"type": "string", "minLength": 1},
        },
    }
    return {"type": "object", "additionalProperties": False,
            "required": ["decisions"],
            "properties": {"decisions": {"type": "array", "items": decision}}}


def verify_requirements(model: ModelPort, *, disputes: tuple[dict, ...],
                        material_by_dispute: dict[str, list[dict]],
                        proposed: dict[str, list[dict]],
                        conversation: tuple[object, ...]) -> dict[str, list[dict]]:
    """Independently retain only proposals supported by their exact citations.

    Each dispute is checked separately so unrelated citations cannot supply
    one another's context. Oversized disputes split into complete item groups.
    An invalid or incomplete verdict fails closed rather than saving a guess.
    """
    dispute_rows, material_ids = _dispute_input(disputes, material_by_dispute)
    if set(proposed) != set(material_ids):
        raise SchemaViolation("Verification needs every supplied dispute")
    result: dict[str, list[dict]] = {dispute_id: [] for dispute_id in material_ids}
    grouped = []
    originals: dict[str, tuple[str, dict, dict[str, dict]]] = {}
    for dispute_row in dispute_rows:
        dispute_id = dispute_row["dispute"]["id"]
        candidates = proposed[dispute_id]
        if not isinstance(candidates, list):
            raise SchemaViolation("Proposed legal items must be a list")
        presented = []
        for item in candidates:
            if not isinstance(item, dict):
                raise SchemaViolation("A proposed legal item is invalid")
            source_ids = item.get("source_ids")
            sources = item.get("sources")
            linked = item.get("material_ids")
            if (not isinstance(source_ids, list) or not source_ids
                    or not isinstance(sources, list)
                    or len(source_ids) != len(sources)
                    or len(source_ids) != len(set(source_ids))
                    or not isinstance(linked, list)
                    or not set(linked) <= material_ids[dispute_id]
                    or item.get("force") not in ("required", "strengthening")
                    or any(not isinstance(item.get(key), str) or not item[key].strip()
                           for key in ("label", "need", "why"))):
                raise SchemaViolation("A proposed legal item lacks checked sources")
            source_by_id = {}
            for source_id, source in zip(source_ids, sources, strict=True):
                if (not isinstance(source_id, str) or not source_id
                        or not isinstance(source, dict)
                        or source.get("id") != source_id
                        or source.get("kind") not in ("provision", "judgment")
                        or any(not isinstance(source.get(key), str)
                               or not source[key].strip()
                               for key in ("title", "locator", "text"))):
                    raise SchemaViolation("A proposed source has no exact passage")
                source_by_id[source_id] = source
            candidate_id = f"r{len(originals) + 1}"
            originals[candidate_id] = dispute_id, item, source_by_id
            presented.append({
                "candidate_id": candidate_id,
                "sources": [{
                    **{key: source[key] for key in (
                        "id", "kind", "title", "locator")},
                    "fragments": _passage_fragments(source["text"]),
                } for source in sources],
                "material_ids": linked,
                "label": item["label"], "need": item["need"],
                "why": item["why"], "force": item["force"],
            })
        if presented:
            grouped.append({**dispute_row, "candidates": presented})
    if not grouped:
        return result
    conversation_rows = _conversation_rows(conversation)

    def prepare(dispute_row: dict, candidates: list[dict]):
        candidate_ids = tuple(candidate["candidate_id"]
                              for candidate in candidates)
        source_ids = tuple(dict.fromkeys(
            source["id"] for candidate in candidates
            for source in candidate["sources"]))
        fragment_ids = tuple(dict.fromkeys(
            fragment["id"] for candidate in candidates
            for source in candidate["sources"]
            for fragment in source["fragments"]))
        group_material_ids = tuple(dict.fromkeys(
            material_id for candidate in candidates
            for material_id in candidate["material_ids"]))
        schema = _verification_schema(
            candidate_ids, source_ids, fragment_ids, group_material_ids)
        output_limit = min(12288, max(
            3072, len(candidate_ids) * 256 +
            sum(len(candidate["sources"]) for candidate in candidates) * 384))
        prompt = _prompt(_VERIFY_SYSTEM, "verify_legal_requirements",
                         {"conversation": conversation_rows,
                          "dispute": dispute_row["dispute"],
                          "material": dispute_row["material"],
                          "candidates": candidates},
                         model, output_limit, schema)
        return candidate_ids, prompt, schema, output_limit

    for dispute_row in grouped:
        for candidate_ids, prompt, schema, output_limit in _ordered_batches(
                dispute_row["candidates"],
                lambda batch, dispute_row=dispute_row: prepare(dispute_row, batch)):
            def accept(data: dict, candidate_ids=candidate_ids,
                       source_subset: dict[str, set[str]] | None = None):
                decisions = data["decisions"]
                if len(decisions) != len(candidate_ids):
                    raise SchemaViolation(
                        "Verification must decide every supplied item once")
                accepted = {candidate_id: None for candidate_id in candidate_ids}
                for decision in decisions:
                    candidate_id = decision["candidate_id"]
                    if accepted[candidate_id] is not None:
                        raise SchemaViolation("A legal item has duplicate verdicts")
                    dispute_id, item, sources = originals[candidate_id]
                    if source_subset is not None:
                        sources = {source_id: source
                                   for source_id, source in sources.items()
                                   if source_id in source_subset[candidate_id]}
                    checks = decision["source_checks"]
                    if (len(checks) != len(sources)
                            or not decision["reason"].strip()
                            or len(decision["reason"]) > 500
                            or not decision["label_reason"].strip()
                            or len(decision["label_reason"]) > 500):
                        raise SchemaViolation(
                            "Verification must examine every cited passage")
                    material_checks = decision["material_checks"]
                    if len(material_checks) != len(item["material_ids"]):
                        raise SchemaViolation(
                            "Verification must examine every linked material item")
                    seen_material: set[str] = set()
                    supported_material: set[str] = set()
                    for check in material_checks:
                        material_id = check["material_id"]
                        if (material_id in seen_material
                                or material_id not in item["material_ids"]
                                or not check["reason"].strip()
                                or len(check["reason"]) > 500):
                            raise SchemaViolation(
                                "A material link verdict is invalid")
                        seen_material.add(material_id)
                        if check["verdict"] == "addresses":
                            supported_material.add(material_id)
                    if seen_material != set(item["material_ids"]):
                        raise SchemaViolation(
                            "Verification omitted a linked material item")
                    linked = [material_id for material_id in item["material_ids"]
                              if material_id in supported_material]
                    seen: set[str] = set()
                    selected: dict[str, dict] = {}
                    for check in checks:
                        source_id = check["source_id"]
                        if source_id in seen or source_id not in sources:
                            raise SchemaViolation(
                                "A passage verdict names another or duplicate source")
                        seen.add(source_id)
                        fragments = {
                            fragment["id"]: fragment["text"]
                            for fragment in _passage_fragments(
                                sources[source_id]["text"])}
                        support_id = check["support_fragment_id"]
                        scope_id = check["scope_fragment_id"]
                        if (support_id and support_id not in fragments
                                or scope_id and scope_id not in fragments):
                            raise SchemaViolation(
                                "A passage verdict selects an invalid fragment ID")
                        support = fragments.get(support_id, "")
                        scope = fragments.get(scope_id, "")
                        scope_status = check["scope_status"]
                        verdict = check["verdict"]
                        if (not check["reason"].strip()
                                or len(check["reason"]) > 500
                                or (verdict == "supported") != bool(support_id)
                                or (verdict == "supported"
                                    and scope_status != "no_special_condition"
                                    and not scope_id)
                                or (verdict == "supported"
                                    and scope_status == "no_special_condition"
                                    and bool(scope_id))
                                or (verdict == "supported" and scope_status not in (
                                    "established", "asked_to_establish",
                                    "no_special_condition"))
                                or (verdict == "supported"
                                    and (not support.strip()
                                         or (scope_id and not scope.strip())))):
                            raise SchemaViolation(
                                "A passage verdict lacks exact, applicable support")
                        if verdict == "supported":
                            selected[source_id] = {
                                "support_excerpt": support,
                                "scope_excerpt": scope,
                                "scope_status": scope_status,
                                "reason": check["reason"],
                            }
                    if seen != set(sources):
                        raise SchemaViolation(
                            "Verification omitted a cited passage")
                    if decision["verdict"] == "supported" and not selected:
                        raise SchemaViolation(
                            "A legal item lacks a supported passage")
                    accepted[candidate_id] = (
                        dispute_id, item, sources,
                        selected if (decision["verdict"] == "supported"
                                     and decision["label_verdict"] == "faithful")
                        else {}, linked)
                return accepted

            presented = {candidate["candidate_id"]: candidate
                         for candidate in dispute_row["candidates"]}

            def isolated_item(candidate_id: str, *,
                              try_combined: bool = True,
                              presented=presented,
                              dispute_row=dispute_row) -> tuple:
                candidate = presented[candidate_id]
                dispute_id, item, sources = originals[candidate_id]
                if try_combined:
                    try:
                        ids, one_prompt, one_schema, one_limit = prepare(
                            dispute_row, [candidate])
                        return checked_read(
                            model, one_prompt, one_schema, one_limit,
                            lambda data, ids=ids: accept(data, ids))[candidate_id]
                    except (SchemaViolation, ContextOverflow, OutputTruncated):
                        pass
                if len(sources) == 1:
                    return dispute_id, item, sources, {}, []
                # A single malformed citation must not suppress support from
                # another cited passage. Recheck the full item against each
                # passage independently, only after the grouped check fails.
                selected = {}
                linked_support = None
                for source_id in item["source_ids"]:
                    one_source = [source for source in candidate["sources"]
                                  if source["id"] == source_id]
                    ids, one_prompt, one_schema, one_limit = prepare(
                        dispute_row, [{**candidate, "sources": one_source}])
                    try:
                        checked = checked_read(
                            model, one_prompt, one_schema, one_limit,
                            lambda data, ids=ids, source_id=source_id: accept(
                                data, ids, {candidate_id: {source_id}}))
                    except (SchemaViolation, ContextOverflow, OutputTruncated):
                        continue
                    source_support = checked[candidate_id][3]
                    selected.update(source_support)
                    if source_support:
                        material_support = set(checked[candidate_id][4])
                        linked_support = (material_support if linked_support is None
                                          else linked_support & material_support)
                linked = [material_id for material_id in item["material_ids"]
                          if linked_support is not None
                          and material_id in linked_support]
                return dispute_id, item, sources, selected, linked

            try:
                accepted = checked_read(model, prompt, schema, output_limit,
                                        accept)
            except (SchemaViolation, ContextOverflow, OutputTruncated):
                if len(candidate_ids) == 1:
                    candidate_id = candidate_ids[0]
                    if len(originals[candidate_id][2]) == 1:
                        raise
                    accepted = {candidate_id: isolated_item(
                        candidate_id, try_combined=False)}
                else:
                    # A malformed answer for one item must not discard
                    # independently checkable items in the same dispute.
                    accepted = {candidate_id: isolated_item(candidate_id)
                                for candidate_id in candidate_ids}
            for candidate_id in candidate_ids:
                dispute_id, item, sources, selected, linked = accepted[candidate_id]
                if not selected:
                    continue
                kept = [source_id for source_id in item["source_ids"]
                        if source_id in selected]
                result[dispute_id].append({
                    **item, "source_ids": kept,
                    "material_ids": linked,
                    "record_status": "mentioned" if linked else "not_mentioned",
                    "sources": [
                        {**sources[source_id],
                         "verification": selected[source_id]}
                        for source_id in kept],
                })
    return result
