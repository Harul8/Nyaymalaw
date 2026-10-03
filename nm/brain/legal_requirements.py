"""Plan, read and independently check passage-grounded research subjects."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass

from nm.brain.checked import require_independent_result
from nm.shared.model_port import (
    ContextOverflow,
    ModelError,
    ModelPort,
    OutputTruncated,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
    require_schema,
)

RESEARCH_KINDS = ("gathering", "principle", "condition", "support", "adverse")
RESEARCH_VERIFICATION = "research_support_v1"

_DECOMPOSE_SYSTEM = """Message: You receive the complete ordered, attributed
conversation and research subjects with their owner, scope, purpose, question
and attributed record. A subject is a research instruction, not a finding that
a dispute, event, rule or permission exists. Reported material is unverified.

Purpose: Form complementary retrieval queries for candidate bare-Act sections
and judgment passages addressing each subject's question. This call gathers
evidence; it does not decide applicable law or the answer.

Look for: The question and requested outcome, contested relationships and
conduct when stated, factual and temporal limits, and potentially relevant
legal concepts. Use genuinely different entry points, including concrete
language and plausible legal terminology. Exploring a term does not assert
it as a fact or applicable rule. Preserve scope and purpose; do not import
another subject's facts, assume missing jurisdiction, expand hypothetical
events or make near-duplicate formulations.

Outcome: Return only plans under the schema, exactly one per subject_id.
Prefer three or four distinct concise queries, never more than four; return
fewer when further useful entry points cannot be grounded. Queries are
search hypotheses, not legal advice, facts or citations."""

_REQUIREMENTS_SYSTEM = """Message: You receive the complete ordered, attributed
conversation, research subjects and their attributed record, and candidate
bare-Act sections and judgment passages retrieved for each subject. Each has
a local ID, exact text and locator. Rank and IDs do not establish legal support
or applicability. Reported documents are uninspected.

Purpose: Propose passage-supported findings addressing each subject's purpose
and question. For gathering work, identify things to establish, obtain or
check. For requested legal work, capture supported principles, conditions,
helpful reasoning and adverse limits needed for a useful answer. Do not
replace legal research with model legal memory.

Look for: What provisions mandate and the conditions, exceptions, timing and
procedure limiting them; what judgments actually decide or explain, including
contrary reasoning. Distinguish holdings from arguments, background and
hypothetical discussion. Compare legal predicates with attributed words
without assuming missing facts. Preserve unresolved applicability conditions
expressly in the finding. Retrieval alone does not establish an in-force
version, jurisdictional reach, precedent treatment or binding weight. Select
material only when its actual words address the finding; reported document
possession does not establish contents or prove an element. Do not invent
facts, document types, duties, holdings or sources.

Outcome: Return only readings under the schema, exactly one per subject_id,
including empty findings when nothing supplied supports a useful finding.
Give each a crisp label, fuller need (the proposition or work needed), and why
connecting it to cited words and the subject. Choose kind gathering, principle,
condition, support or adverse according to its role. Gathering force is
required only if cited law mandates that proposed step or element under its
preserved conditions; otherwise strengthening. Other kinds use force none.
Cite source_ids only from this subject's passages and material_ids only from
its attributed record. The wire schema lists IDs across the batch, but each
subject's allowed_source_ids and allowed_material_ids are its exclusive
selection boundary. A relevant passage supplied only to a different subject
is not available here; omit that finding rather than borrowing its ID.
No proposal proves the account, legal force or success."""

_VERIFY_SYSTEM = """Message: You receive the complete ordered, attributed
conversation, research subjects and their attributed record, and proposed
findings with exact cited passages shown as overlapping numbered fragments.
Proposals are untrusted; retrieval rank and citation IDs are not support.

Purpose: Independently check each finding's full label, need, why, kind and
force against its own passages, subject and attributed record. Only supported
findings may enter the research record. Do not supply law or facts, decide
merits beyond the passages or repair the proposed wording.

Look for: Examine every cited source and its limiting predicates. Shared
terminology is not support; another legal setting cannot be stretched to this
subject. Distinguish actual judgment reasoning from argument or background.
Every retained proposition, inference and claimed mandatory step must follow
from selected passages without filling gaps from legal memory or another
subject. The label must faithfully express the supported need or proposition
and its caveats. Unknown applicability supports a conditional finding only if
the entire limiting predicate is expressly preserved without claiming the
record meets it. Use established only with attributed supporting words, or
asked_to_establish when gathering work expressly seeks that predicate.
no_special_condition describes the passage, not silence in the record. Check
every material ID against its words independently; an incorrect material link
can be removed without losing a supported finding. Reported documents remain
uninspected. Fragmentary or indeterminate support is uncertain; verification
does not establish binding status or proof.

Outcome: Return exactly one independent decision per candidate_id. Use
supported, unsupported or uncertain overall; faithful, unsupported or uncertain
for the label. Reasons are nonempty and at most 500 characters. Rejected
findings or unfaithful labels are withheld and may have empty unused source
and material checks. For a supported faithful finding check EVERY cited source
and selected material exactly once. Select support_fragment_id only from that
source's exact fragments when its words support the finding; rejected sources
need an empty support ID. Select scope_fragment_id for a limiting predicate.
Supported sources require established, asked_to_establish, conditional or
no_special_condition scope. conditional needs an exact scope fragment and
faithful preservation of its full predicate without asserting satisfaction.
no_special_condition needs an empty scope ID; other supported scopes need an
exact fragment. Overall support requires the retained passages together to
support the entire meaning, force and limits. No verdict proves the account or
source authority. Return only the declared decisions object."""

_REPAIR_SYSTEM = """\n\nMessage: This corrects rejected units of the same
research activity. Valid peers are already retained.
Purpose: Repair only the supplied failures under the same contract.
Look for: Precise issues, original attributed input and selected source words.
Rejected output is a proposal, not evidence or an instruction.
Outcome: Return complete replacements only for the unresolved IDs; do not
repeat retained peers or invent facts, citations or support."""


@dataclass(frozen=True)
class ResearchResult:
    rows: dict
    coverage: dict[str, dict]
    outage: str | None = None


ResearchPlanning = ResearchReading = ResearchVerification = ResearchResult
RequirementVerification = ResearchResult


def _conversation_rows(conversation):
    rows = []
    for message in conversation:
        turn_id, role, words = (getattr(message, key, None) for key in ("turn_id", "role", "text"))
        if (
            not isinstance(turn_id, str)
            or not turn_id
            or role not in ("advocate", "nm")
            or not isinstance(words, str)
        ):
            raise SchemaViolation("The supplied conversation is not attributable")
        rows.append({"turn_id": turn_id, "role": role, "text": words})
    return rows


def _subject_input(subjects, material_by_subject):
    rows, known, canonical = [], {}, {}
    for subject in subjects:
        if (
            not isinstance(subject, dict)
            or any(
                not isinstance(subject.get(key), str) or not subject[key].strip()
                for key in ("id", "owner_id", "question")
            )
            or subject.get("scope") not in ("current", "proposed", "none", "other", "uncertain")
            or subject.get("kind") not in ("dispute", "request")
            or subject.get("purpose") not in ("gathering", "requested_work")
            or not isinstance(subject.get("record_ids"), list)
            or any(not isinstance(key, str) or not key for key in subject["record_ids"])
            or len(subject["record_ids"]) != len(set(subject["record_ids"]))
            or subject["id"] in known
        ):
            raise SchemaViolation("A research subject needs a unique owner, scope and question")
        identifier = subject["id"]
        material = material_by_subject.get(identifier, [])
        if not isinstance(material, (list, tuple)):
            raise SchemaViolation("A research subject's attributed record is invalid")
        known[identifier] = set()
        for item in material:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or item["id"] in known[identifier]
            ):
                raise SchemaViolation("Attributed research records need unique saved IDs")
            if item["id"] in canonical and canonical[item["id"]] != item:
                raise SchemaViolation("An attributed research record has conflicting ownership")
            canonical[item["id"]] = item
            known[identifier].add(item["id"])
        if not set(subject["record_ids"]) <= known[identifier]:
            raise SchemaViolation("A research subject references unavailable attributed material")
        if subject["scope"] == "none" and material:
            raise SchemaViolation("A general research subject cannot import matter material")
        rows.append({"subject": deepcopy(subject), "material": deepcopy(list(material))})
    if set(material_by_subject) - set(known):
        raise SchemaViolation("Attributed material names an unknown research subject")
    return rows, known


def _coverage(ids):
    return {
        key: {
            "state": "ok",
            "checked_items": 0,
            "unread_items": 0,
            "withheld_items": 0,
            "diagnostics": [],
        }
        for key in ids
    }


def _prompt(system, operation, payload, model, output_limit, schema, tier=Tier.ROUTINE):
    prompt = Prompt(
        system=system,
        user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        operation=operation,
    )
    encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    if estimate_tokens(
        prompt.user + (prompt.system or "") + encoded
    ) + output_limit > model.context_budget(tier):
        raise ContextOverflow(
            "The complete conversation and research group exceed the model budget"
        )
    return prompt


def _ordered_batches(rows, prepare):
    """Preflight complete atomic units, then use the fewest consecutive groups."""
    try:
        return [prepare(rows)], []
    except ContextOverflow:
        pass
    fitting, singles, oversized = [], [], []
    for row in rows:
        try:
            single = prepare([row])
        except ContextOverflow:
            oversized.append(row)
        else:
            fitting.append(row)
            singles.append(single)
    rows = fitting
    batches, start = [], 0
    while start < len(rows):
        largest, end = singles[start], start + 1
        while end < len(rows):
            try:
                candidate = prepare(rows[start : end + 1])
            except ContextOverflow:
                break
            largest, end = candidate, end + 1
        batches.append(largest)
        start = end
    return batches, oversized


def _repair_payload(payload, issues, rejected):
    return (
        {**payload, "validation_issues": issues, "rejected_units": rejected} if issues else payload
    )


def _read_subject_groups(model, rows, prepare, *, field, accept):
    """Retain subject peers and correct only unread units once per batch."""
    by_id = {row["subject"]["id"]: row for row in rows}
    result, coverage, outage = {}, _coverage(by_id), None
    batches, oversized = _ordered_batches(rows, prepare)
    for row in oversized:
        identifier = row["subject"]["id"]
        coverage[identifier].update(state="partial", unread_items=1)
        coverage[identifier]["diagnostics"].append(
            "This research unit exceeds its model context budget; no context was omitted"
        )
    for ids, prompt, schema, limit in batches:
        pending, issues, rejected = ids, {}, {}
        for attempt in range(2):
            if outage or not pending:
                break
            if attempt:
                try:
                    _, prompt, schema, limit = prepare(
                        [by_id[key] for key in pending], issues, rejected
                    )
                except ContextOverflow:
                    break
            try:
                read = model.structured(prompt, schema, Tier.ROUTINE, max_tokens=limit)
            except (SchemaViolation, OutputTruncated) as exc:
                issues = {key: str(exc) for key in pending}
                continue
            except ContextOverflow:
                issues = {key: "This complete research unit exceeds the model context budget"
                          for key in pending}
                break
            except ModelError as exc:
                outage = type(exc).__name__
                issues = {key: "This research activity was unavailable" for key in pending}
                break
            data = read.data if read.usable and isinstance(read.data, dict) else None
            values = data.get(field) if data is not None and set(data) == {field} else None
            groups = {key: [] for key in pending}
            if isinstance(values, list):
                for value in values:
                    if (
                        isinstance(value, dict)
                        and isinstance(value.get("subject_id"), str)
                        and value["subject_id"] in groups
                    ):
                        groups[value["subject_id"]].append(value)
            unresolved, issues = [], {}
            for identifier in pending:
                group = groups[identifier]
                if len(group) != 1:
                    issues[identifier] = "Return exactly one complete unit for this subject_id"
                    rejected[identifier] = group
                    unresolved.append(identifier)
                    continue
                try:
                    require_schema(group[0], schema["properties"][field]["items"])
                    value = accept(identifier, group[0])
                except SchemaViolation as exc:
                    issues[identifier], rejected[identifier] = str(exc), group[0]
                    unresolved.append(identifier)
                else:
                    result[identifier] = value
                    coverage[identifier]["checked_items"] = 1
            pending = tuple(unresolved)
        for identifier in pending:
            coverage[identifier].update(
                state="unavailable" if outage else "partial", unread_items=1
            )
            coverage[identifier]["diagnostics"].append(
                issues.get(identifier, "This research unit could not be read")
            )
    return ResearchResult(result, coverage, outage)


def _decomposition_schema(ids):
    plan = {
        "type": "object",
        "additionalProperties": False,
        "required": ["subject_id", "queries"],
        "properties": {
            "subject_id": {"type": "string", "enum": list(ids)},
            "queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text"],
                    "properties": {"text": {"type": "string", "minLength": 1}},
                },
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["plans"],
        "properties": {"plans": {"type": "array", "items": plan}},
    }


def decompose_subjects(
    model: ModelPort,
    *,
    subjects: tuple[dict, ...],
    material_by_subject: dict[str, list[dict]],
    conversation: tuple[object, ...],
) -> ResearchPlanning:
    rows, _ = _subject_input(subjects, material_by_subject)
    words = _conversation_rows(conversation)
    if not rows:
        return ResearchResult({}, {})

    def prepare(group, issues=None, rejected=None):
        ids = tuple(row["subject"]["id"] for row in group)
        schema = _decomposition_schema(ids)
        limit = min(12288, max(3072, len(ids) * 1024))
        payload = _repair_payload({"conversation": words, "subjects": group}, issues, rejected)
        prompt = _prompt(
            _DECOMPOSE_SYSTEM + (_REPAIR_SYSTEM if issues else ""),
            "decompose_disputes",
            payload,
            model,
            limit,
            schema,
        )
        return ids, prompt, schema, limit

    def accept(identifier, row):
        phrases = [item["text"].strip() for item in row["queries"]]
        if any(not phrase or len(phrase) > 300 for phrase in phrases):
            raise SchemaViolation("Each search query must be concise and nonempty")
        if len({phrase.casefold() for phrase in phrases}) != len(phrases):
            raise SchemaViolation("A subject has duplicate search queries")
        return tuple(phrases)

    return _read_subject_groups(model, rows, prepare, field="plans", accept=accept)


def _findings_schema(ids, source_ids, material_ids):
    finding = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "label", "need", "why", "force", "source_ids", "material_ids"],
        "properties": {
            "kind": {"type": "string", "enum": list(RESEARCH_KINDS)},
            **{key: {"type": "string", "minLength": 1} for key in ("label", "need", "why")},
            "force": {"type": "string", "enum": ["required", "strengthening", "none"]},
            "source_ids": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "enum": list(source_ids)},
            },
            "material_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(material_ids)},
            },
        },
    }
    reading = {
        "type": "object",
        "additionalProperties": False,
        "required": ["subject_id", "findings"],
        "properties": {
            "subject_id": {"type": "string", "enum": list(ids)},
            "findings": {"type": "array", "items": finding},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["readings"],
        "properties": {"readings": {"type": "array", "items": reading}},
    }


def _search_hits(ids, searches):
    if set(searches) - set(ids):
        raise SchemaViolation("Search results name an unknown research subject")
    hits = {}
    for identifier in ids:
        search = searches.get(identifier)
        if (
            not isinstance(search, dict)
            or search.get("state") not in ("ok", "partial", "unavailable")
            or not isinstance(search.get("candidates"), list)
        ):
            raise SchemaViolation("Research search has no reliable state or candidate list")
        hits[identifier] = {}
        if search["state"] == "unavailable" and search["candidates"]:
            raise SchemaViolation("Unavailable search cannot provide candidate passages")
        for hit in search["candidates"]:
            if (
                not isinstance(hit, dict)
                or not isinstance(hit.get("id"), str)
                or not hit["id"]
                or hit["id"] in hits[identifier]
                or hit.get("kind") not in ("provision", "judgment")
                or any(
                    not isinstance(hit.get(key), str) or not hit[key].strip()
                    for key in ("title", "locator", "text")
                )
            ):
                raise SchemaViolation("A retrieved passage needs a unique exact locator")
            hits[identifier][hit["id"]] = deepcopy(hit)
    return hits


def _finding(row, identifier, hits, material_ids):
    label, need, why = (row[key].strip() for key in ("label", "need", "why"))
    if not label or len(label) > 120 or not need or not why:
        raise SchemaViolation("A finding needs a short label and explanation")
    if (row["kind"] == "gathering") != (row["force"] in ("required", "strengthening")):
        raise SchemaViolation(
            "Gathering force is required or strengthening; other findings use none"
        )
    selected, linked = row["source_ids"], row["material_ids"]
    if len(selected) != len(set(selected)):
        raise SchemaViolation(f"Finding for subject {identifier!r} has duplicate source_ids")
    if not set(selected) <= hits[identifier].keys():
        raise SchemaViolation(
            f"Finding for subject {identifier!r} has invalid source_ids "
            f"{sorted(set(selected) - hits[identifier].keys())!r}; choose only "
            f"from this subject's allowed_source_ids {list(hits[identifier])!r}"
        )
    if len(linked) != len(set(linked)) or not set(linked) <= material_ids[identifier]:
        raise SchemaViolation(f"Finding for subject {identifier!r} links unrelated material")
    return {
        **row,
        "label": label,
        "need": need,
        "why": why,
        "sources": [deepcopy(hits[identifier][key]) for key in selected],
        "record_status": "mentioned" if linked else "not_mentioned",
    }


def read_findings(
    model: ModelPort,
    *,
    subjects: tuple[dict, ...],
    material_by_subject: dict[str, list[dict]],
    search_results: dict[str, dict],
    conversation: tuple[object, ...],
) -> ResearchReading:
    rows, material_ids = _subject_input(subjects, material_by_subject)
    words = _conversation_rows(conversation)
    result, coverage = {}, _coverage(material_ids)
    hits = {}
    for identifier in material_ids:
        try:
            hits.update(_search_hits((identifier,), {identifier: search_results.get(identifier)}))
        except SchemaViolation as exc:
            hits[identifier] = {}
            coverage[identifier].update(state="partial", unread_items=1)
            coverage[identifier]["diagnostics"].append(str(exc))
        else:
            if search_results[identifier]["state"] == "unavailable":
                coverage[identifier].update(state="unavailable", unread_items=1)
            elif not hits[identifier]:
                result[identifier] = []
    if set(search_results) - set(material_ids):
        for row in coverage.values():
            row["diagnostics"].append("An unowned search result was discarded")
    active = [
        {**row, "candidates": list(hits[row["subject"]["id"]].values()),
         "allowed_source_ids": list(hits[row["subject"]["id"]]),
         "allowed_material_ids": sorted(material_ids[row["subject"]["id"]])}
        for row in rows
        if hits[row["subject"]["id"]]
    ]

    def prepare(group, issues=None, rejected=None):
        ids = tuple(row["subject"]["id"] for row in group)
        source_ids = tuple(dict.fromkeys(key for identifier in ids for key in hits[identifier]))
        linked_ids = tuple(
            dict.fromkeys(key for identifier in ids for key in material_ids[identifier])
        )
        schema = _findings_schema(ids, source_ids, linked_ids)
        limit = min(16384, max(4096, len(source_ids) * 384))
        payload = _repair_payload({"conversation": words, "subjects": group}, issues, rejected)
        prompt = _prompt(
            _REQUIREMENTS_SYSTEM + (_REPAIR_SYSTEM if issues else ""),
            "read_legal_requirements",
            payload,
            model,
            limit,
            schema,
        )
        return ids, prompt, schema, limit

    def accept(identifier, row):
        values = [_finding(item, identifier, hits, material_ids) for item in row["findings"]]
        if len({item["label"].casefold() for item in values}) != len(values):
            raise SchemaViolation("A subject has duplicate finding labels")
        return values

    read = (
        _read_subject_groups(model, active, prepare, field="readings", accept=accept)
        if active
        else ResearchResult({}, {})
    )
    result.update(read.rows)
    coverage.update(read.coverage)
    for identifier, row in coverage.items():
        search = search_results.get(identifier)
        search_state = search.get("state") if isinstance(search, dict) else None
        row["search_state"] = (
            search_state if search_state in ("ok", "partial", "unavailable") else "unavailable"
        )
        if row["search_state"] != "ok":
            if row["state"] != "unavailable":
                row["state"] = "partial"
            row["diagnostics"].append(
                "Search coverage is incomplete; only supplied passages were considered"
            )
    return ResearchResult(result, coverage, read.outage)


def _passage_fragments(passage: str) -> list[dict[str, str]]:
    """Expose bounded, overlapping exact spans without asking the model to copy."""
    width, overlap = 700, 140
    fragments = []
    start = 0
    while start < len(passage):
        fragments.append({"id": f"f{len(fragments) + 1}", "text": passage[start : start + width]})
        if start + width >= len(passage):
            break
        start += width - overlap
    return fragments


def _verification_schema(
    candidate_ids: tuple[str, ...],
    source_ids: tuple[str, ...],
    fragment_ids: tuple[str, ...],
    material_ids: tuple[str, ...],
) -> dict:
    source_check = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source_id",
            "support_fragment_id",
            "scope_fragment_id",
            "scope_status",
            "verdict",
            "reason",
        ],
        "properties": {
            "source_id": {"type": "string", "enum": list(source_ids)},
            "support_fragment_id": {"type": "string", "enum": ["", *fragment_ids]},
            "scope_fragment_id": {"type": "string", "enum": ["", *fragment_ids]},
            "scope_status": {
                "type": "string",
                "enum": [
                    "established",
                    "asked_to_establish",
                    "conditional",
                    "not_established",
                    "different_legal_setting",
                    "cannot_determine",
                    "no_special_condition",
                ],
            },
            "verdict": {"type": "string", "enum": ["supported", "unsupported", "uncertain"]},
            "reason": {"type": "string", "minLength": 1},
        },
    }
    decision = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "candidate_id",
            "label_verdict",
            "label_reason",
            "material_checks",
            "source_checks",
            "verdict",
            "reason",
        ],
        "properties": {
            "candidate_id": {"type": "string", "enum": list(candidate_ids)},
            "label_verdict": {"type": "string", "enum": ["faithful", "unsupported", "uncertain"]},
            "label_reason": {"type": "string", "minLength": 1},
            "material_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["material_id", "verdict", "reason"],
                    "properties": {
                        "material_id": {"type": "string", "enum": list(material_ids)},
                        "verdict": {
                            "type": "string",
                            "enum": ["addresses", "does_not_address", "uncertain"],
                        },
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
            },
            "source_checks": {"type": "array", "items": source_check},
            "verdict": {"type": "string", "enum": ["supported", "unsupported", "uncertain"]},
            "reason": {"type": "string", "minLength": 1},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decisions"],
        "properties": {"decisions": {"type": "array", "items": decision}},
    }


def _finding_verdict(
    decision: dict, *, candidate_id: str, original: tuple[str, dict, dict[str, dict]]
) -> dict | None:
    _, item, sources = original
    fragments = tuple(
        dict.fromkeys(
            fragment["id"]
            for source in sources.values()
            for fragment in _passage_fragments(source["text"])
        )
    )
    schema = _verification_schema(
        (candidate_id,), tuple(sources), fragments, tuple(item["material_ids"])
    )
    require_schema(decision, schema["properties"]["decisions"]["items"])
    checks = decision["source_checks"]
    if (
        not decision["reason"].strip()
        or len(decision["reason"]) > 500
        or not decision["label_reason"].strip()
        or len(decision["label_reason"]) > 500
    ):
        raise SchemaViolation("Keep nonempty verdict reasons within 500 characters")
    if decision["verdict"] != "supported" or decision["label_verdict"] != "faithful":
        return None
    if len(checks) != len(sources):
        raise SchemaViolation("Check every cited passage exactly once for a supported item")
    material_checks = decision["material_checks"]
    if len(material_checks) != len(item["material_ids"]):
        raise SchemaViolation("Check every linked material ID exactly once")
    seen_material: set[str] = set()
    supported_material: set[str] = set()
    for check in material_checks:
        material_id = check["material_id"]
        if (
            material_id in seen_material
            or material_id not in item["material_ids"]
            or not check["reason"].strip()
            or len(check["reason"]) > 500
        ):
            raise SchemaViolation(
                "A material link verdict is duplicated, foreign or lacks a concise reason"
            )
        seen_material.add(material_id)
        if check["verdict"] == "addresses":
            supported_material.add(material_id)
    if seen_material != set(item["material_ids"]):
        raise SchemaViolation("Check every linked material ID exactly once")
    linked = [
        material_id for material_id in item["material_ids"] if material_id in supported_material
    ]
    seen: set[str] = set()
    selected: dict[str, dict] = {}
    for check in checks:
        source_id = check["source_id"]
        if source_id in seen or source_id not in sources:
            raise SchemaViolation("A passage verdict names another or duplicate source")
        seen.add(source_id)
        fragments_by_id = {
            fragment["id"]: fragment["text"]
            for fragment in _passage_fragments(sources[source_id]["text"])
        }
        support_id = check["support_fragment_id"]
        scope_id = check["scope_fragment_id"]
        if (
            support_id
            and support_id not in fragments_by_id
            or scope_id
            and scope_id not in fragments_by_id
        ):
            raise SchemaViolation("Choose support and scope fragment IDs from this source only")
        support = fragments_by_id.get(support_id, "")
        scope = fragments_by_id.get(scope_id, "")
        scope_status = check["scope_status"]
        verdict = check["verdict"]
        if (
            not check["reason"].strip()
            or len(check["reason"]) > 500
            or (verdict == "supported") != bool(support_id)
            or (verdict == "supported" and scope_status != "no_special_condition" and not scope_id)
            or (
                verdict == "supported" and scope_status == "no_special_condition" and bool(scope_id)
            )
            or (
                verdict == "supported"
                and scope_status
                not in ("established", "asked_to_establish", "conditional", "no_special_condition")
            )
            or (
                verdict == "supported" and (not support.strip() or (scope_id and not scope.strip()))
            )
        ):
            raise SchemaViolation(
                "A supported passage needs its exact support fragment and either "
                "a checked scope fragment or no_special_condition with an empty scope ID; "
                "unsupported or uncertain passages need an empty support ID"
            )
        if verdict == "supported":
            selected[source_id] = {
                "support_excerpt": support,
                "scope_excerpt": scope,
                "scope_status": scope_status,
                "reason": check["reason"],
            }
    if seen != set(sources):
        raise SchemaViolation("Check every cited source ID exactly once")
    if decision["verdict"] == "supported" and not selected:
        raise SchemaViolation("A supported item needs at least one supported passage")
    kept = [source_id for source_id in item["source_ids"] if source_id in selected]
    return {
        **item,
        "source_ids": kept,
        "material_ids": linked,
        "record_status": "mentioned" if linked else "not_mentioned",
        "sources": [
            {**sources[source_id], "verification": selected[source_id]} for source_id in kept
        ],
    }


def verify_findings(
    model: ModelPort,
    *,
    subjects: tuple[dict, ...],
    material_by_subject: dict[str, list[dict]],
    proposed: dict[str, list[dict]],
    conversation: tuple[object, ...],
) -> ResearchVerification:
    rows, material_ids = _subject_input(subjects, material_by_subject)
    if set(proposed) != set(material_ids):
        raise SchemaViolation("Verification needs every supplied research subject")
    words = _conversation_rows(conversation)
    result = {key: [] for key in material_ids}
    coverage, originals, atoms = _coverage(material_ids), {}, []
    for row in rows:
        identifier = row["subject"]["id"]
        if not isinstance(proposed[identifier], list):
            raise SchemaViolation("Proposed research findings must be a list")
        for item in proposed[identifier]:
            if (
                not isinstance(item, dict)
                or item.get("kind") not in RESEARCH_KINDS
                or not isinstance(item.get("source_ids"), list)
                or not item["source_ids"]
                or len(item["source_ids"]) != len(set(item["source_ids"]))
                or not isinstance(item.get("sources"), list)
                or len(item["sources"]) != len(item["source_ids"])
                or not isinstance(item.get("material_ids"), list)
                or len(item["material_ids"]) != len(set(item["material_ids"]))
                or not set(item["material_ids"]) <= material_ids[identifier]
                or (
                    (item["kind"] == "gathering")
                    != (item.get("force") in ("required", "strengthening"))
                )
                or (item["kind"] != "gathering" and item.get("force") != "none")
                or any(
                    not isinstance(item.get(key), str) or not item[key].strip()
                    for key in ("label", "need", "why")
                )
            ):
                raise SchemaViolation(
                    "A proposed finding lacks checked source ownership or meaning"
                )
            sources = {}
            for source_id, source in zip(item["source_ids"], item["sources"], strict=True):
                if (
                    not isinstance(source_id, str)
                    or not source_id
                    or not isinstance(source, dict)
                    or source.get("id") != source_id
                    or source.get("kind") not in ("provision", "judgment")
                    or any(
                        not isinstance(source.get(key), str) or not source[key].strip()
                        for key in ("title", "locator", "text")
                    )
                ):
                    raise SchemaViolation("A proposed source has no exact passage")
                sources[source_id] = source
            candidate_id = f"r{len(originals) + 1}"
            originals[candidate_id] = identifier, item, sources
            candidate = {
                "candidate_id": candidate_id,
                **{
                    key: item[key]
                    for key in ("kind", "label", "need", "why", "force", "material_ids")
                },
                "sources": [
                    {
                        **{key: source[key] for key in ("id", "kind", "title", "locator")},
                        "fragments": _passage_fragments(source["text"]),
                    }
                    for source in item["sources"]
                ],
            }
            atoms.append({"context": row, "candidate": candidate})
    if not atoms:
        return ResearchResult(result, coverage)

    def prepare(group, issues=None, rejected=None):
        grouped = {}
        for atom in group:
            context = atom["context"]
            identifier = context["subject"]["id"]
            grouped.setdefault(identifier, {**context, "candidates": []})["candidates"].append(
                atom["candidate"]
            )
        candidates = [atom["candidate"] for atom in group]
        ids = tuple(candidate["candidate_id"] for candidate in candidates)
        source_ids = tuple(
            dict.fromkeys(
                source["id"] for candidate in candidates for source in candidate["sources"]
            )
        )
        fragment_ids = tuple(
            dict.fromkeys(
                fragment["id"]
                for candidate in candidates
                for source in candidate["sources"]
                for fragment in source["fragments"]
            )
        )
        linked = tuple(
            dict.fromkeys(key for candidate in candidates for key in candidate["material_ids"])
        )
        schema = _verification_schema(ids, source_ids, fragment_ids, linked)
        limit = min(
            12288,
            max(
                4096,
                len(ids) * 256 + sum(len(candidate["sources"]) for candidate in candidates) * 384,
            ),
        )
        payload = _repair_payload(
            {"conversation": words, "subjects": list(grouped.values())}, issues, rejected
        )
        prompt = _prompt(
            _VERIFY_SYSTEM + (_REPAIR_SYSTEM if issues else ""),
            "verify_legal_requirements",
            payload,
            model,
            limit,
            schema,
            Tier.JUDGE,
        )
        return ids, prompt, schema, limit

    by_id = {atom["candidate"]["candidate_id"]: atom for atom in atoms}
    retained, outage = {}, None
    batches, oversized = _ordered_batches(atoms, prepare)
    for atom in oversized:
        identifier = atom["context"]["subject"]["id"]
        coverage[identifier]["state"] = "partial"
        coverage[identifier]["unread_items"] += 1
        coverage[identifier]["diagnostics"].append(
            "A source-checking candidate exceeds its model context budget; no context was omitted"
        )
    for ids, prompt, schema, limit in batches:
        pending, issues, rejected = ids, {}, {}
        for attempt in range(2):
            if outage or not pending:
                break
            if attempt:
                try:
                    _, prompt, schema, limit = prepare(
                        [by_id[key] for key in pending], issues, rejected
                    )
                except ContextOverflow:
                    break
            try:
                read = model.structured(prompt, schema, Tier.JUDGE, max_tokens=limit)
                require_independent_result(read)
            except (SchemaViolation, OutputTruncated) as exc:
                issues = {key: str(exc) for key in pending}
                continue
            except ContextOverflow:
                issues = {key: "This complete source-checking unit exceeds the model context budget"
                          for key in pending}
                break
            except ModelError as exc:
                outage = type(exc).__name__
                issues = {key: "Independent source checking was unavailable" for key in pending}
                break
            data = read.data if read.usable and isinstance(read.data, dict) else None
            values = (
                data.get("decisions") if data is not None and set(data) == {"decisions"} else None
            )
            groups = {key: [] for key in pending}
            if isinstance(values, list):
                for decision in values:
                    if (
                        isinstance(decision, dict)
                        and isinstance(decision.get("candidate_id"), str)
                        and decision["candidate_id"] in groups
                    ):
                        groups[decision["candidate_id"]].append(decision)
            unresolved, issues = [], {}
            for candidate_id in pending:
                group = groups[candidate_id]
                if len(group) != 1:
                    issues[candidate_id] = (
                        "Return exactly one complete verdict for this candidate_id"
                    )
                    rejected[candidate_id] = group
                    unresolved.append(candidate_id)
                    continue
                try:
                    value = _finding_verdict(
                        group[0], candidate_id=candidate_id, original=originals[candidate_id]
                    )
                except SchemaViolation as exc:
                    issues[candidate_id], rejected[candidate_id] = str(exc), group[0]
                    unresolved.append(candidate_id)
                else:
                    identifier = originals[candidate_id][0]
                    coverage[identifier]["checked_items"] += 1
                    if value is None:
                        coverage[identifier]["withheld_items"] += 1
                    else:
                        retained[candidate_id] = value
            pending = tuple(unresolved)
        for candidate_id in pending:
            identifier = originals[candidate_id][0]
            coverage[identifier]["state"] = (
                "unavailable" if outage and not coverage[identifier]["checked_items"] else "partial"
            )
            coverage[identifier]["unread_items"] += 1
            coverage[identifier]["diagnostics"].append(
                issues.get(candidate_id, "Source checking did not finish")
            )
    for candidate_id, (identifier, _, _) in originals.items():
        if candidate_id in retained:
            result[identifier].append(retained[candidate_id])
    return ResearchResult(result, coverage, outage)


def _dispute_subjects(disputes, material_by_dispute):
    subjects, material = [], {}
    for dispute in disputes:
        if (
            not isinstance(dispute, dict)
            or not isinstance(dispute.get("id"), str)
            or not dispute["id"]
        ):
            raise SchemaViolation("A dispute needs a saved identity")
        identifier = dispute["id"]
        records = [dispute, *material_by_dispute.get(identifier, [])]
        subjects.append(
            {
                "id": identifier,
                "kind": "dispute",
                "owner_id": identifier,
                "scope": "current",
                "purpose": "gathering",
                "question": dispute.get("statement") or dispute.get("label") or "",
                "record_ids": [row["id"] for row in records],
            }
        )
        material[identifier] = records
    if set(material_by_dispute) - set(material):
        raise SchemaViolation("Attributed material names an unknown dispute")
    return tuple(subjects), material


def decompose(model, *, disputes, material_by_dispute, conversation):
    subjects, material = _dispute_subjects(disputes, material_by_dispute)
    return decompose_subjects(
        model, subjects=subjects, material_by_subject=material, conversation=conversation
    ).rows


def read_requirements(model, *, disputes, material_by_dispute, search_results, conversation):
    subjects, material = _dispute_subjects(disputes, material_by_dispute)
    return read_findings(
        model,
        subjects=subjects,
        material_by_subject=material,
        search_results=search_results,
        conversation=conversation,
    ).rows


def verify_requirements(model, *, disputes, material_by_dispute, proposed, conversation):
    subjects, material = _dispute_subjects(disputes, material_by_dispute)
    return verify_findings(
        model,
        subjects=subjects,
        material_by_subject=material,
        proposed=proposed,
        conversation=conversation,
    )
