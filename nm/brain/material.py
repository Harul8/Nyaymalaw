"""Provisional legal material identified in an attributed conversation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Literal

from nm.brain.checked import checked_read
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
                            if key not in {"source_id", "prior_source_ids"}},
                         "quoted": latest[source_id],
                         "prior_references": [vars(prior[key]) for key in prior_ids]})
    return resolved


def saved_source_ids(saved: dict, prior: dict[str, PriorReference]) -> tuple[str, ...]:
    """Address a saved item's exact advocate passage in this full transcript."""
    return tuple(source_id for source_id, ref in prior.items()
                 if ref.role == "advocate"
                 and ref.turn_id == saved.get("source_turn_id")
                 and isinstance(saved.get("quoted"), str)
                 and (saved["quoted"] in ref.quoted
                      or ref.quoted in saved["quoted"]))


def fill_empty_link_sources(row: dict, *, link_field: str,
                            known: dict[str, dict],
                            prior: dict[str, PriorReference]) -> dict:
    """Resolve an omitted citation only from explicitly selected saved IDs."""
    if row.get("prior_source_ids") or not row.get(link_field):
        return row
    source_ids = []
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


def _extraction_schema(*, latest_ids: tuple[str, ...],
                       prior_ids: tuple[str, ...],
                       has_current_matter: bool,
                       dispute_ids: tuple[str, ...],
                       material_ids: tuple[str, ...]) -> dict:
    item = addressed_item_schema(
        kinds=tuple(kind for kind in KINDS if kind != "dispute"),
        latest_ids=latest_ids, prior_ids=prior_ids,
        has_current_matter=has_current_matter)
    properties = dict(item["properties"])
    properties.update({
        "placement": {"type": "string", "enum": list(PLACEMENTS)},
        "dispute_ids": {"type": "array", "items": {"type": "string",
            **({"enum": list(dispute_ids)} if dispute_ids else {})},
            **({"maxItems": 0} if not dispute_ids else {})},
        "related_material_ids": {"type": "array", "items": {"type": "string",
            **({"enum": list(material_ids)} if material_ids else {})},
            **({"maxItems": 0} if not material_ids else {})},
    })
    item = {**item, "properties": properties,
            "required": [*item["required"], "placement", "dispute_ids",
                         "related_material_ids"]}
    return {"type": "object", "additionalProperties": False,
            "required": ["details"],
            "properties": {"details": {"type": "array", "items": item}}}

_SYSTEM = """Message: This is a legal-detail read of the advocate's latest
message. The input contains that message and the complete earlier conversation
as ordered source spans with IDs, speakers, and turn IDs, plus the current
matter ID if there is one, active material details, and active disputes
including those identified in the latest message. The spans contain the
original words in order.
Earlier messages supply context; only the latest advocate message can add new
material. The account and any mentioned records remain unverified. An empty
earlier conversation cannot support a prior reference.

Purpose: Identify materially significant legal details contributed by the
latest message against the whole conversation. This produces sourced proposals
for a matter file, not admitted facts, dispute formulations, legal conclusions,
permission, or action.

Look for: Material acts and omissions, chronology, people and roles,
relationships, stated terms, attributed positions, objectives, evidence and
its stated source or custody, procedural posture and timing, risks, and
uncertainty. Capture each separately assessable item even when the dispute
reader already describes its issue: a reported obligation, conduct against
that obligation, a party's stated explanation, and a mentioned record can
be different items. A detail matters if it could affect a dispute, response,
remedy, forum, proof, timing, risk, or next useful step. Read the latest words
in context, including a reply to an earlier question or a correction. A
greeting, general question, or request for work is not itself a matter fact,
though it may contain one. Do not merge material from another or ambiguous
matter into the current matter.

Outcome: Return only the declared JSON object with a `details` array. Put one
neutral, attributed proposition per independently checkable material detail,
or an empty array if the latest message adds none. If two claims could be
confirmed, denied, or corrected separately, do not compress them into one
statement. Do not output a dispute statement or repeat the same proposition.
Check each latest-message span for independently material details before
returning, including records whose existence or stated contents may matter.
For each detail set `kind`, a concise `statement`, and `why_material`
explaining its possible relevance. The statement must be supported by the
cited words in context: do not turn conduct into a party's express position,
or add an unstated reason, requirement, record content, or legal effect.
Use `position` for a position actually attributed to a speaker, `event` for
reported conduct, and `evidence` for a record's stated existence or content;
describing an available record does not establish its contents. Ground every proposal
by selecting a `source_id` from the latest message's spans that directly
supports it; the server inserts those exact saved words. If interpreting a
reply, reference, or change needs earlier words, select their IDs in
`prior_source_ids`. Mark `relation` to those words; corrections,
contradictions, and withdrawals must identify the earlier words affected.
For a detail that bears on an active dispute, list every directly relevant
`dispute_id` and set `placement` to `disputes`; use `why_material` to say why
it bears on the named dispute(s). A detail relevant to the matter as a whole
without a reliable dispute link has `placement` `matter`; use `unresolved`
when its connection is genuinely unclear. If there is no active dispute to
select, leave `dispute_ids` empty and use `matter` or `unresolved`, even when
the message describes conduct that may become a dispute. Do not guess a link from shared
people, words, or proximity. Link a changed detail to the exact active
`related_material_ids` when it corrects, contradicts, adds to, or withdraws
their content. For each linked item, select one of its `source_ids` in
`prior_source_ids` if selecting any earlier spans. If the array is empty,
the server resolves each linked item's exact saved advocate passage. Select
additional earlier spans when needed to understand the change.
An empty link list means no safe link. A correction or
withdrawal retires only the specifically linked detail, not other details.
Use `withdraws` only with at least one exact active `related_material_id`.
If no safe link exists, express uncertainty without claiming an earlier
detail was withdrawn; retain a sourced detail if independently material.
Set `matter_scope` to current only when
a current matter ID is supplied; use proposed for a possible new matter, other
for a different matter, and uncertain when the reference is unresolved. Set
`basis` to reflect whether content is directly stated, attributed to another
person, a description of a record not read, inferred, uncertain, or
hypothetical. Set provisional `importance` without treating the account as
established. Do not repeat unchanged earlier material or invent a legal theory,
record contents, event, or permission."""


def parse_material(rows: object, *, latest: str,
                   earlier: tuple[object, ...], current_matter_id: str | None
                   ) -> tuple[MaterialCandidate, ...]:
    if not isinstance(rows, list):
        raise SchemaViolation("The material proposals are missing")
    prior_words = {(item.turn_id, item.role): item.text for item in earlier}
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            raise SchemaViolation("A material proposal is not an object")
        quote = row.get("quoted")
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
            if (not isinstance(label, str) or not label.strip()
                    or len(label.strip()) > 140):
                raise SchemaViolation("A dispute needs a short, nonempty label")
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
                raise SchemaViolation("A new dispute cannot revise an earlier dispute")
            related_ids = tuple(related)
        candidates.append(MaterialCandidate(
            kind=row["kind"], statement=statement, quoted=quote,
            relation=row["relation"], prior_references=tuple(prior),
            matter_scope=row["matter_scope"], basis=row["basis"],
            importance=row["importance"], why_material=reason,
            label=label, identification=identification,
            clarification=clarification, related_dispute_ids=related_ids))
    return tuple(candidates)


def extract_details(model: ModelPort, *, earlier: tuple[object, ...],
                    latest: str, current_matter_id: str | None,
                    disputes: tuple[dict, ...] = (),
                    prior_material: tuple[dict, ...] = ()
                    ) -> tuple[MaterialCandidate, ...]:
    """Make one complete, sourced legal-detail read of the latest message."""
    if not latest.strip():
        raise ValueError("The latest message is empty")
    payload, latest_sources, prior_sources = addressed_sources(earlier, latest)
    payload["current_matter_id"] = current_matter_id
    payload["active_disputes"] = [
        {key: row.get(key) for key in (
            "id", "label", "statement", "source_turn_id", "quoted")}
        for row in disputes]
    payload["active_material"] = [
        {key: row.get(key) for key in (
            "id", "kind", "statement", "source_turn_id", "quoted",
            "placement", "dispute_ids")}
        | {"source_ids": list(saved_source_ids(row, prior_sources))}
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
        dispute_ids=tuple(row["id"] for row in disputes),
        material_ids=tuple(row["id"] for row in prior_material))
    def accept(data: dict) -> tuple[MaterialCandidate, ...]:
        known_material = {row["id"]: row for row in prior_material}
        if any(row["relation"] == "withdraws" and not row["related_material_ids"]
               for row in data["details"]):
            raise SchemaViolation(
                "A withdrawal needs an exact active related material ID; "
                "express uncertainty if no safe link exists")
        selected = [fill_empty_link_sources(
            row, link_field="related_material_ids", known=known_material,
            prior=prior_sources) for row in data["details"]]
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
        known_disputes = {row["id"] for row in disputes}
        accepted = []
        for row, candidate in zip(rows, candidates, strict=True):
            placement = row.get("placement")
            dispute_ids = row.get("dispute_ids")
            material_ids = row.get("related_material_ids")
            if (placement not in PLACEMENTS
                    or not isinstance(dispute_ids, list)
                    or any(not isinstance(item, str) or item not in known_disputes
                           for item in dispute_ids)
                    or len(dispute_ids) != len(set(dispute_ids))):
                raise SchemaViolation("A detail has an invalid dispute placement")
            # Placement is a presentation category, while the selected IDs are
            # the substantive link. Canonicalize a contradictory pair instead
            # of rejecting an otherwise attributable detail (or the whole turn).
            if dispute_ids:
                placement = "disputes"
            elif placement == "disputes":
                placement = "unresolved"
            if (not isinstance(material_ids, list)
                    or any(not isinstance(item, str) or item not in known_material
                           for item in material_ids)
                    or len(material_ids) != len(set(material_ids))
                    or (candidate.relation == "new" and material_ids)):
                raise SchemaViolation("A detail has invalid earlier material links")
            accepted.append(replace(
                candidate, placement=placement, dispute_ids=tuple(dispute_ids),
                related_material_ids=tuple(material_ids)))
        return tuple(accepted)

    return checked_read(model, prompt, schema, output_limit, accept)
