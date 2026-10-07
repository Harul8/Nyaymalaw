"""Provisional legal material identified in an attributed conversation."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Literal

from nm.brain.checked import checked_unit_read
from nm.brain.mutation_contracts import model_mutation_context
from nm.brain.record_review import derived_record, owned_source_treatments
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
)

KINDS = ("dispute", "event", "circumstance", "position", "objective",
         "evidence", "procedure", "risk", "other")
RELATIONS = ("new", "adds", "corrects", "contradicts", "withdraws")
SCOPES = ("current", "proposed", "other", "none", "uncertain")
BASES = ("stated", "attributed", "described_record", "inferred",
         "uncertain", "hypothetical")
IMPORTANCE = ("central", "relevant", "uncertain")
PLACEMENTS = ("disputes", "matter", "unresolved")


def assignment_targets(disputes: tuple[dict, ...], current_matter_id: str | None) -> list[dict]:
    """Present one owned assignment decision; scope and placement follow it."""
    scope = "current" if current_matter_id else "proposed"
    targets = [dict(id="matter:discussion", kind="matter", matter_scope=scope,
                    placement="matter"),
               dict(id="matter:unlinked", kind="matter", matter_scope=scope,
                    placement="unresolved"),
               *[dict(id=f"matter:{value}", kind="matter", matter_scope=value,
                      placement="unresolved") for value in ("other", "none", "uncertain")]]
    seen = {target["id"] for target in targets}
    for record in disputes:
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or not record["id"].strip() or record["id"] in seen):
            raise SchemaViolation(
                "The active dispute assignment catalogue has conflicting identities")
        seen.add(record["id"])
        targets.append(dict(id=record["id"], kind="dispute", matter_scope=scope,
                            placement="disputes", record=derived_record(deepcopy(record))))
    return targets


def resolve_assignment(row: dict, targets: dict[str, dict]) -> dict:
    """Resolve only the selected assignment; semantic acceptance remains independent."""
    selected = row.get("assignment_ids")
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(identity, str) or identity not in targets
                   for identity in selected)):
        raise SchemaViolation("A detail must select known assignment IDs")
    # Assignment is a set of owned targets. Repeating the same exact target
    # adds no meaning; validate ownership before this lossless normalization.
    selected = list(dict.fromkeys(selected))
    values = [targets[identity] for identity in selected]
    if len(values) > 1 and any(value["kind"] != "dispute" for value in values):
        raise SchemaViolation(
            "A detail may select active dispute IDs or one general matter assignment, "
            "not mixed targets"
        )
    target = values[0]
    return {**{key: value for key, value in row.items() if key != "assignment_ids"},
            "matter_scope": target["matter_scope"], "placement": target["placement"],
            "dispute_ids": selected if target["kind"] == "dispute" else []}


@dataclass(frozen=True)
class PriorReference:
    turn_id: str
    role: Literal["advocate", "nm"]
    quoted: str


@dataclass(frozen=True)
class MaterialCandidate:
    kind: str
    statement: str
    quoted: str
    relation: str
    prior_references: tuple[PriorReference, ...]
    matter_scope: str
    basis: str
    importance: str
    why_material: str
    label: str = ""
    identification: str = ""
    clarification: str = ""
    related_dispute_ids: tuple[str, ...] = ()
    placement: str = ""
    dispute_ids: tuple[str, ...] = ()
    related_material_ids: tuple[str, ...] = ()
    source_id: str | None = None

    def recorded(self, turn_id: str, index: int) -> dict:
        record = {
            "id": f"{turn_id}:material:{index}",
            "source_turn_id": turn_id,
            "state": "proposed",
            "kind": self.kind,
            "statement": self.statement,
            "quoted": self.quoted,
            "relation": self.relation,
            "prior_references": [vars(ref) for ref in self.prior_references],
            "matter_scope": self.matter_scope,
            "basis": self.basis,
            "importance": self.importance,
            "why_material": self.why_material,
        }
        if self.source_id is not None:
            record["source_id"] = self.source_id
        if self.kind == "dispute":
            record.update(label=self.label, identification=self.identification,
                          clarification=self.clarification,
                          related_dispute_ids=list(self.related_dispute_ids))
        else:
            record.update(placement=self.placement,
                          dispute_ids=list(self.dispute_ids),
                          related_material_ids=list(self.related_material_ids))
        return record


SCHEMA = {
    "type": "array",
    "items": {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "statement", "quoted", "relation", "prior_references",
                     "matter_scope", "basis", "importance", "why_material"],
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "statement": {"type": "string"},
            "quoted": {"type": "string"},
            "relation": {"type": "string", "enum": list(RELATIONS)},
            "prior_references": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["turn_id", "role", "quoted"],
                "properties": {
                    "turn_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["advocate", "nm"]},
                    "quoted": {"type": "string"},
                },
            }},
            "matter_scope": {"type": "string", "enum": list(SCOPES)},
            "basis": {"type": "string", "enum": list(BASES)},
            "importance": {"type": "string", "enum": list(IMPORTANCE)},
            "why_material": {"type": "string"},
        },
    },
}


def addressed_sources(earlier: tuple[object, ...], latest: str
                      ) -> tuple[dict, dict[str, str], dict[str, PriorReference]]:
    """Present every saved word once, in ordered spans with local source IDs."""
    boundary = re.compile(r"(?<=[.!?;])(?=[ \t]+\S)|(?<=\n)(?=\S)")
    prior_sources: dict[str, PriorReference] = {}

    def spans(text: str, prefix: str) -> list[dict[str, str]]:
        pieces = []
        for piece in boundary.split(text):
            while len(piece) > 640:
                end = piece.rfind(" ", 320, 640)
                end = end if end > 0 else 640
                pieces.append(piece[:end])
                piece = piece[end:]
            pieces.append(piece)
        return [{"id": f"{prefix}{index}", "text": piece}
                for index, piece in enumerate(pieces, start=1)]

    previous = []
    for message_index, message in enumerate(earlier, start=1):
        pieces = spans(message.text, f"P{message_index}S")
        for piece in pieces:
            if piece["text"].strip():
                prior_sources[piece["id"]] = PriorReference(
                    message.turn_id, message.role, piece["text"].strip())
        previous.append({"turn_id": message.turn_id, "role": message.role,
                         "source_spans": pieces})
    current = spans(latest, "L")
    latest_sources = {piece["id"]: piece["text"].strip()
                      for piece in current if piece["text"].strip()}
    payload = {"earlier_conversation": previous,
               "latest_message_spans": current}
    return payload, latest_sources, prior_sources


def addressed_item_schema(*, kinds: tuple[str, ...] | None,
                          latest_ids: tuple[str, ...],
                          prior_ids: tuple[str, ...],
                          has_current_matter: bool) -> dict:
    """Constrain model citations to existing source IDs before generation."""
    item = SCHEMA["items"]
    properties = dict(item["properties"])
    required = [field for field in item["required"]
                if field not in {"quoted", "prior_references"}]
    properties.pop("quoted")
    properties.pop("prior_references")
    properties["source_id"] = {"type": "string", "enum": list(latest_ids)}
    required.append("source_id")
    if prior_ids:
        properties["prior_source_ids"] = {
            "type": "array", "items": {"type": "string", "enum": list(prior_ids)}}
        required.append("prior_source_ids")
    else:
        properties["relation"] = {"type": "string", "enum": ["new"]}
    if kinds is None:
        properties.pop("kind")
        required.remove("kind")
    else:
        properties["kind"] = {"type": "string", "enum": list(kinds)}
    if not has_current_matter:
        properties["matter_scope"] = {
            "type": "string", "enum": [scope for scope in SCOPES if scope != "current"]}
    return {**item, "required": required, "properties": properties}


def resolve_sources(rows: list[dict], *, latest: dict[str, str],
                    prior: dict[str, PriorReference]) -> list[dict]:
    """Build exact citations from immutable input, never generated quote text."""
    resolved = []
    for row in rows:
        source_id = row.get("source_id")
        prior_ids = row.get("prior_source_ids", [])
        if (not isinstance(source_id, str) or source_id not in latest
                or not isinstance(prior_ids, list)
                or any(not isinstance(key, str) or key not in prior
                       for key in prior_ids)):
            raise SchemaViolation("A material source selection is invalid")
        resolved.append({**{key: value for key, value in row.items()
                            if key != "prior_source_ids"},
                         "quoted": latest[source_id],
                         "prior_references": [vars(ref) for ref in
                                              dict.fromkeys(prior[key] for key in prior_ids)]})
    return resolved


def saved_source_ids(saved: dict, prior: dict[str, PriorReference]) -> tuple[str, ...]:
    """Address a saved item's original selected span in this full transcript."""
    selected_source = saved.get("source_id")
    if selected_source is not None:
        ordinal = (re.fullmatch(r"L([1-9][0-9]*)", selected_source)
                   if isinstance(selected_source, str) else None)
        if ordinal is None:
            raise SchemaViolation("A saved material source identity is invalid")
        selected = []
        for identity, ref in prior.items():
            previous = re.fullmatch(r"P[1-9][0-9]*S([1-9][0-9]*)", identity)
            if (previous is not None and previous[1] == ordinal[1]
                    and ref.role == "advocate"
                    and ref.turn_id == saved.get("source_turn_id")):
                selected.append((identity, ref))
        if (len(selected) != 1 or not isinstance(saved.get("quoted"), str)
                or selected[0][1].quoted != saved["quoted"]):
            raise SchemaViolation(
                "A saved material source identity does not match its original owned passage")
        return (selected[0][0],)
    return tuple(source_id for source_id, ref in prior.items()
                 if ref.role == "advocate"
                 and ref.turn_id == saved.get("source_turn_id")
                 and isinstance(saved.get("quoted"), str)
                 and (saved["quoted"] in ref.quoted
                      or ref.quoted in saved["quoted"]))


def fill_empty_link_sources(row: dict, *, link_field: str,
                            known: dict[str, dict],
                            prior: dict[str, PriorReference]) -> dict:
    """Attach the original source of every explicitly selected saved record."""
    if not row.get(link_field):
        return row
    source_ids = list(row.get("prior_source_ids", []))
    for item_id in row[link_field]:
        saved = known.get(item_id)
        if saved is None:
            raise SchemaViolation("A changed material item names an unknown saved ID")
        matches = saved_source_ids(saved, prior)
        if not matches:
            raise SchemaViolation("A linked material item has no addressable saved source")
        if matches[0] not in source_ids:
            source_ids.append(matches[0])
    return {**row, "prior_source_ids": source_ids}


def operation_schema(item: dict, *, link_field: str,
                     known_ids: tuple[str, ...]) -> dict:
    """Separate record creation from explicit revision in the wire contract."""
    new_item = deepcopy(item)
    for field in ("relation", link_field):
        new_item["properties"].pop(field, None)
        new_item["required"] = [key for key in new_item["required"] if key != field]
    change = deepcopy(item)
    change["properties"]["relation"] = {
        "type": "string", "enum": [relation for relation in RELATIONS if relation != "new"]}
    change["properties"][link_field] = {
        "type": "array", "minItems": 1,
        "items": {"type": "string", **({"enum": list(known_ids)} if known_ids else {})}}
    if link_field not in change["required"]:
        change["required"].append(link_field)
    return {"type": "object", "additionalProperties": False,
            "required": ["new_items", "changes"], "properties": {
                "new_items": {"type": "array", "items": new_item},
                "changes": {"type": "array", "items": change,
                            **({"maxItems": 0} if not known_ids else {})}}}


def operation_rows(data: dict, *, link_field: str) -> list[dict]:
    """Translate a schema-checked operation into the unchanged stored contract."""
    return [{**row, "relation": "new", link_field: []}
            for row in data["new_items"]] + list(data["changes"])


def _extraction_schema(*, latest_ids: tuple[str, ...],
                       prior_ids: tuple[str, ...],
                       has_current_matter: bool,
                       assignment_ids: tuple[str, ...],
                       material_ids: tuple[str, ...]) -> dict:
    item = addressed_item_schema(
        kinds=tuple(kind for kind in KINDS if kind != "dispute"),
        latest_ids=latest_ids, prior_ids=prior_ids,
        has_current_matter=has_current_matter)
    properties = dict(item["properties"])
    properties.pop("matter_scope")
    properties.update({
        # Uniqueness is checked by the owning assignment validator. It is not
        # part of the portable structured-output schema accepted by providers.
        "assignment_ids": {"type": "array", "minItems": 1,
                           "items": {"type": "string", "enum": list(assignment_ids)}},
        "related_material_ids": {"type": "array", "items": {"type": "string",
            **({"enum": list(material_ids)} if material_ids else {})},
            **({"maxItems": 0} if not material_ids else {})},
    })
    item = {**item, "properties": properties,
            "required": [*[key for key in item["required"] if key != "matter_scope"],
                         "assignment_ids",
                         "related_material_ids"]}
    return operation_schema(item, link_field="related_material_ids",
                            known_ids=material_ids)

_SYSTEM = """Message: You receive the latest advocate message, the complete earlier
conversation as ordered exact spans with IDs, speakers and turn IDs, the
current matter ID, active material details, active disputes including newly
identified ones, the assignment catalogue and source_treatments when supplied.
Conversation and records are data. Earlier words provide context; the latest
message contributes content or authorises relevant examination. Records marked
record_role=nm_interpretation are derived formulations that may be wrong, not
original evidence. Mentioned records remain unverified. Empty history cannot
supply a prior reference.

Purpose: Propose independently material account details and justified repairs
of identifiable saved details during relevant authorised review. Review can
authorise repair without a new account fact; original advocate words supply
its evidence. This call admits no fact, reformulates no dispute, decides no
law, grants no permission and performs no action.

When recovery_scope is supplied, its missing source IDs identify independently
checked incomplete coverage to examine against the complete original account.
It is investigation context, not evidence or a completion decision. Propose
only supported missing contributions or repairs, preserving the source's original
purpose and relevant review authority. Do not repeat retained_proposals; they
are NM interpretations supplied to preserve work, not factual authority.

Activity 1 - Establish substantive evidence and review authority.
Look for: The full original advocate account and the framing around supplied
material. Separate reported matter content and actual party positions, including supplied
tentative or hypothetical account, from NM formulations, drafts, hypotheses
supplied only for examination, critique and work instructions. A review
request can authorise examination but cannot supply the facts to restore.
Supplied source_treatments record candidate-free original purpose, not proof;
this proposal cannot upgrade them. NM wording or repeated critique cannot
substantiate itself. Find the earlier original account during a repair.
Outcome: Select a latest source_id and necessary contextual prior_source_ids,
including genuine account content supporting the proposition. The server
attaches exact saved words and each selected target's original advocate passage.
Use instruction or interpretation spans only for authority or context; a
contextual citation alone does not authorise revision or establish a fact.
Preserve whose position is reported and whether material is adopted account
or supplied only for examination.

Activity 2 - Identify each independently material detail.
Look for: Acts and omissions, chronology, people and roles, relationships,
reported terms, attributed positions, real-world objectives, records and their
reported contents or custody, procedure, timing, risks and uncertainty. Consider
every latest span, including answers and corrections. A detail is material
when it could affect an issue, assessment or next useful step. A request can
contain matter content but is not itself a matter fact.
Dispute headings and definitions guide association; they are not material-detail
records. Capture independently material content even when a dispute mentions it.
Omit an unchanged detail only when active_material faithfully preserves the
same proposition, including attribution, chronology, uncertainty and source purpose.
An objective is a desired real-world outcome for the client or dispute. NM
explanation, investigation and production requests belong to work progress,
not a duplicated matter objective without independent content. A promise or
inability to supply a record can concern custody but does not establish its
contents. Critique or correction of a draft or NM interpretation belongs to
work and response, not a new party position in the account.
Outcome: Return one concise attributed statement, kind and why_material per
independently checkable detail. Do not merge claims that could be confirmed,
denied or corrected separately or output a dispute formulation.
Distinguish obligation, conduct, an actual reported party
position and a described record. Conduct alone is not an express position;
a described record is not proof of its contents. Do not invent facts, terms,
reasons, record content, permission, legal status or conclusions, including
as a tentative or inferred position of your own.

Activity 3 - Choose an owned creation or explicit revision.
Look for: Whether a distinct proposition is new or changes an identifiable
saved one. Newly received words, shared actors or source wording alone do not
establish a revision. Distinguish an advocate account change from repair of
NM's unsupported interpretation against exact earlier account during relevant
current authorised work. Preserve account uncertainty, source status and known
record identity; a diversion or new legal theory authorises no account change.
Each replacement remains one independently checkable underlying proposition.
Multiple targets must be duplicates or the same proposition, not independent
details sharing source or review instructions. If NM merged details wrongly,
restore atomic sourced successors with explicit lineage and preserve all
underlying accounts rather than replacing them with correction-process text.
Outcome: Put a distinct new item in new_items without relation or
related_material_ids; it cannot retire a saved record. Put a revision in
changes with at least one exact active ID in related_material_ids and relation adds,
corrects, contradicts or withdraws. New is not a change operation. A correction
or withdrawal retires only its selected supported detail. Explain an NM repair
as that layer's repair, not a new factual correction by the advocate.
If no safe target exists, a current independently material proposition may
enter new_items with earlier context and preserved uncertainty; never claim
that a saved record changed or was withdrawn without the supported operation.

Activity 4 - Select assignment and preserve status.
Look for: Which active disputes the supported content directly bears on and
which matter owns it. Ownership is distinct from whether facts are proved,
actors are known, records examined or legal effect settled. A first account
can clearly belong to a proposed matter despite those uncertainties.
Outcome: Select every directly relevant active dispute ID in assignment_ids,
or exactly one general matter target. Discussion means matter-wide content;
unlinked means known ownership with its dispute unresolved; other means
another matter, none means non-matter content, and uncertain means unresolved
ownership. Never mix disputes with general targets or select several general
targets. Do not guess a link from proximity or merge another matter's account.
Explain the assignment in why_material. The server derives scope and placement
from this one selection; do not supply them separately. The independent
checker decides whether the semantic link is supported.
An active dispute identifies the matter under discussion, current with a
current matter ID and proposed otherwise. If ownership is genuinely unresolved,
choose uncertain instead of a dispute or discussion target. Preserve stated,
attributed, described-record, inferred, uncertain or hypothetical status in
basis and provisional relevance in importance, retaining the attributed
statement's unknowns rather than making ownership ambiguous.

Outcome: Return only the declared new_items and changes object. Both arrays
may be empty when no new detail or justified repair is supported by the latest
contribution or authorised review. Review alone does not require a mutation."""


def parse_material(rows: object, *, latest: str,
                   earlier: tuple[object, ...], current_matter_id: str | None
                   ) -> tuple[MaterialCandidate, ...]:
    if not isinstance(rows, list):
        raise SchemaViolation("The material proposals are missing")
    prior_words = {(item.turn_id, item.role): item.text for item in earlier}
    _, current_sources, _ = addressed_sources((), latest)
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            raise SchemaViolation("A material proposal is not an object")
        quote = row.get("quoted")
        source_id = row.get("source_id")
        if source_id is not None and (
                not isinstance(source_id, str) or source_id not in current_sources
                or current_sources[source_id] != quote):
            raise SchemaViolation(
                "A material source identity does not match its exact owned passage")
        statement = row.get("statement")
        reason = row.get("why_material")
        references = row.get("prior_references")
        if not isinstance(quote, str) or not quote.strip() or quote not in latest:
            raise SchemaViolation(
                "The selected latest source is absent from the saved message")
        if not isinstance(statement, str) or not statement.strip():
            raise SchemaViolation("A material proposal needs a nonempty statement")
        if not isinstance(reason, str) or not reason.strip():
            raise SchemaViolation("A material proposal needs a materiality reason")
        if not isinstance(references, list):
            raise SchemaViolation("Earlier source references must be a list")
        prior = []
        for ref in references:
            if not isinstance(ref, dict):
                raise SchemaViolation("A material reference is not an object")
            turn_id, role, quoted = (ref.get("turn_id"), ref.get("role"),
                                     ref.get("quoted"))
            words = prior_words.get((turn_id, role))
            if (not isinstance(turn_id, str) or not isinstance(role, str)
                    or not isinstance(quoted, str) or not quoted.strip()
                    or words is None or quoted not in words):
                raise SchemaViolation("A material reference does not match saved words")
            prior.append(PriorReference(turn_id, role, quoted))
        if len(prior) != len(set(prior)):
            raise SchemaViolation("A material proposal repeats a prior reference")
        if (row.get("kind") not in KINDS or row.get("relation") not in RELATIONS
                or row.get("matter_scope") not in SCOPES
                or row.get("basis") not in BASES
                or row.get("importance") not in IMPORTANCE):
            raise SchemaViolation("A material proposal has an unknown classification")
        if row["relation"] != "new" and not prior:
            raise SchemaViolation("A material change needs an attributable earlier reference")
        if row["matter_scope"] == "current" and not current_matter_id:
            raise SchemaViolation("There is no current matter for this material")
        label = identification = clarification = ""
        related_ids: tuple[str, ...] = ()
        if row["kind"] == "dispute":
            label = row.get("label")
            identification = row.get("identification")
            clarification = row.get("clarification")
            related = row.get("related_dispute_ids")
            if not isinstance(label, str) or not label.strip():
                raise SchemaViolation("A dispute needs a nonempty label")
            if identification not in ("identified", "needs_clarification"):
                raise SchemaViolation("A dispute needs an identification decision")
            if not isinstance(clarification, str):
                raise SchemaViolation("A dispute clarification must be text")
            if (identification == "needs_clarification") != bool(clarification.strip()):
                raise SchemaViolation(
                    "An uncertain dispute needs one clarification; "
                    "an identified dispute needs none")
            if (not isinstance(related, list)
                    or any(not isinstance(value, str) or not value.strip()
                           for value in related)
                    or len(related) != len(set(related))):
                raise SchemaViolation("A dispute has invalid related dispute IDs")
            if row["relation"] == "new" and related:
                raise SchemaViolation(
                    "A new dispute must have empty related_dispute_ids. If this "
                    "proposal revises the selected saved dispute, choose the "
                    "supported relationship to that earlier proposition; "
                    "otherwise remove the link.")
            related_ids = tuple(related)
        candidates.append(MaterialCandidate(
            kind=row["kind"], statement=statement, quoted=quote,
            relation=row["relation"], prior_references=tuple(prior),
            matter_scope=row["matter_scope"], basis=row["basis"],
            importance=row["importance"], why_material=reason,
            label=label, identification=identification,
            clarification=clarification, related_dispute_ids=related_ids,
            source_id=source_id))
    return tuple(candidates)


def extraction_recovery_scope(scope: dict, latest: dict[str, str],
                              prior: dict[str, PriorReference]) -> dict:
    """Validate owned recovery anchors; derived context supplies no new evidence."""
    fields = {"review_scope", "missing_source_ids", "retained_proposals", "reason"}
    if not isinstance(scope, dict) or set(scope) != fields:
        raise SchemaViolation("Extraction recovery requires its declared context fields")
    selected = scope["missing_source_ids"]
    owned = set(latest) | {identity for identity, ref in prior.items()
                          if ref.role == "advocate"}
    if (not isinstance(selected, (list, tuple)) or not selected
            or any(not isinstance(identity, str) or identity not in owned
                   for identity in selected)):
        raise SchemaViolation("Recovery must select owned original advocate source IDs")
    if not isinstance(scope["review_scope"], dict):
        raise SchemaViolation("Recovery requires the original code-owned review scope")
    if not isinstance(scope["reason"], str) or not scope["reason"].strip():
        raise SchemaViolation("Recovery requires the checked coverage explanation")
    retained = scope["retained_proposals"]
    if not isinstance(retained, (list, tuple)):
        raise SchemaViolation("Retained recovery proposals must be an array")
    originals = set(prior.values())
    for proposal in retained:
        if (not isinstance(proposal, dict)
                or not isinstance(proposal.get("quoted"), str)
                or proposal["quoted"] not in latest.values()):
            raise SchemaViolation("Retained recovery context requires exact current source words")
        references = proposal.get("prior_references", [])
        if (not isinstance(references, (list, tuple))
                or any(not isinstance(ref, dict) or set(ref) != {"turn_id", "role", "quoted"}
                       or any(not isinstance(value, str) for value in ref.values())
                       or PriorReference(ref["turn_id"], ref["role"], ref["quoted"])
                       not in originals for ref in references)):
            raise SchemaViolation("Retained recovery context requires owned earlier references")
    return model_mutation_context({
        "review_scope": deepcopy(scope["review_scope"]),
        "missing_source_ids": list(dict.fromkeys(selected)),
        "retained_proposals": [derived_record(deepcopy(row)) for row in retained],
        "reason": scope["reason"]})


def extract_details(model: ModelPort, *, earlier: tuple[object, ...],
                    latest: str, current_matter_id: str | None,
                    disputes: tuple[dict, ...] = (),
                    prior_material: tuple[dict, ...] = (), source_treatments=None,
                    diagnostics: dict | None = None, recovery_scope: dict | None = None
                    ) -> tuple[MaterialCandidate, ...]:
    """Make one complete, sourced legal-detail read of the latest message."""
    if not latest.strip():
        raise ValueError("The latest message is empty")
    payload, latest_sources, prior_sources = addressed_sources(earlier, latest)
    if recovery_scope is not None:
        payload["recovery_scope"] = extraction_recovery_scope(
            recovery_scope, latest_sources, prior_sources)
    if source_treatments is not None:
        payload["source_treatments"] = owned_source_treatments(
            source_treatments, latest_sources, prior_sources)
    payload["current_matter_id"] = current_matter_id
    targets = assignment_targets(disputes, current_matter_id)
    target_by_id = {target["id"]: target for target in targets}
    payload["assignment_targets"] = targets
    payload["active_material"] = [
        derived_record({key: row.get(key) for key in (
            "id", "kind", "statement", "source_turn_id", "quoted",
            "placement", "dispute_ids", "matter_scope", "relation",
            "related_material_ids", "basis", "importance", "why_material",
            "prior_references")}
        | {"source_ids": list(saved_source_ids(row, prior_sources))})
        for row in prior_material]
    prompt = Prompt(
        system=_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        operation="extract_legal_details",
    )
    # A material read can return several independently sourced propositions.
    # Reserve enough room for that structure, and refuse if the complete
    # transcript no longer fits with the answer rather than trimming it.
    output_limit = max(6144, min(16384, estimate_tokens(latest) * 10))
    if (estimate_tokens(prompt.user + (prompt.system or "")) + output_limit
            > model.context_budget(Tier.ROUTINE)):
        raise ContextOverflow("The full conversation exceeds this model's context budget")
    schema = _extraction_schema(
        latest_ids=tuple(latest_sources), prior_ids=tuple(prior_sources),
        has_current_matter=bool(current_matter_id),
        assignment_ids=tuple(row["id"] for row in targets),
        material_ids=tuple(row["id"] for row in prior_material))
    def accept(data: dict) -> tuple[MaterialCandidate, ...]:
        known_material = {row["id"]: row for row in prior_material}
        proposals = operation_rows(data, link_field="related_material_ids")
        selected = [fill_empty_link_sources(
            resolve_assignment(row, target_by_id),
            link_field="related_material_ids", known=known_material,
            prior=prior_sources) for row in proposals]
        for row in selected:
            for material_id in row["related_material_ids"]:
                saved = known_material.get(material_id)
                if saved is None:
                    raise SchemaViolation("A changed detail names an unknown saved ID")
                expected = saved_source_ids(saved, prior_sources)
                if not set(row.get("prior_source_ids", [])).intersection(expected):
                    raise SchemaViolation(
                        f"Related material {material_id!r} requires one of "
                        f"prior_source_ids {list(expected)!r}")
        rows = resolve_sources(selected, latest=latest_sources,
                               prior=prior_sources)
        candidates = parse_material(rows, latest=latest, earlier=earlier,
                                    current_matter_id=current_matter_id)
        accepted = []
        for row, candidate in zip(rows, candidates, strict=True):
            placement = row.get("placement")
            dispute_ids = row.get("dispute_ids")
            material_ids = row.get("related_material_ids")
            if (not isinstance(material_ids, list)
                    or any(not isinstance(item, str) or item not in known_material
                           for item in material_ids)
                    or len(material_ids) != len(set(material_ids))
                    or (candidate.relation == "new" and material_ids)):
                raise SchemaViolation(
                    "Earlier material links must name known unique saved IDs; "
                    "relation new requires an empty related_material_ids array. "
                    "For a linked change, select the supported relationship "
                    "to the earlier proposition, not whether the message is new.")
            if candidate.matter_scope == "uncertain" and any(
                    known_material[item].get("matter_scope") in ("current", "proposed")
                    for item in material_ids):
                raise SchemaViolation(
                    "An ownership-ambiguous detail cannot revise current-owned "
                    "related_material_ids. Preserve uncertain ownership as a "
                    "separate new proposal without revision targets, or select "
                    "current/proposed ownership only if the attributed account "
                    "establishes it. Uncertainty about facts or proof does not "
                    "make matter ownership uncertain.")
            accepted.append(replace(
                candidate, placement=placement, dispute_ids=tuple(dispute_ids),
                related_material_ids=tuple(material_ids)))
        return tuple(accepted)

    return checked_unit_read(
        model, prompt, schema, output_limit, accept,
        unit_fields=("new_items", "changes"), diagnostics=diagnostics)
