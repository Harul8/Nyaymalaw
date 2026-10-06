"""Propose distinct, sourced disputes in one attributed conversation read."""
from __future__ import annotations

import json

from nm.brain.checked import checked_unit_read
from nm.brain.material import (
    MaterialCandidate,
    addressed_item_schema,
    addressed_sources,
    extraction_recovery_scope,
    fill_empty_link_sources,
    operation_rows,
    operation_schema,
    parse_material,
    resolve_sources,
    saved_source_ids,
)
from nm.brain.record_review import derived_record, owned_source_treatments
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
)

_SYSTEM = """Message: You receive the latest advocate message and the complete saved
conversation as exact spans with source, turn and speaker IDs. You also receive
the current matter ID, active disputes and, when available, source_treatments
and recovery_scope. Original messages, NM interpretations, review instructions
and proposed work are separate input data. An empty history is valid.

Purpose: Identify disputes actually reported in the original account and
supported repairs of existing dispute formulations. There may be no disputes.
Significant facts are captured separately by the material reader; this call
must not create a dispute merely to record or acknowledge those facts.
A dispute means reported adverse conduct or incompatible claims, positions or
rights requiring a practical resolution. Possible future disagreement about a
fact is not a reported dispute. This call proposes records; it does not prove
the account, determine law or certify an executed operation.

Activity 1 - Establish what the original account says.
Look for: Read the latest message in the complete original conversation.
Distinguish actual reported conduct and party positions from draft content,
hypotheses supplied for examination, legal theories and instructions. Preserve
who said what, negation, chronology, conditions and uncertainty. A quoted or
examined proposition is not necessarily adopted. A mixed message may contain
both a genuine account and work instructions; assess them separately.
Outcome: Use original attributed account for substantive content. Earlier words
provide context without becoming fresh assertions. Records marked
record_role=nm_interpretation and retained_proposals are derived formulations,
not original evidence. source_treatments are an earlier purpose read to examine,
not authority to add content. Mentioned documents remain reported and unverified.

Activity 2 - Decide whether a reported conflict exists.
Look for: Identify the conduct presented as adverse or the incompatible positions
or rights before deciding how many disputes to propose. Do not invent adversity
from an event's importance, its attribution, a request to record it, or a possible
legal consequence. Neutral events and supporting details remain material.
Adverse conduct needs no express opposing denial, legal label, identified actor
or proved facts. Unknown identity, responsibility or proof does not erase a
reported conflict. Do not assign an actor from an adjacent event or NM wording.
An undertaking does not establish responsibility for an earlier act; a continued
condition does not establish breach of an undertaking before it is due.
Outcome: Propose only the reported conflict. In why_material, identify that
conflict and its practical conclusion from the original account. An explanation
that an event is important, attributed or potentially contestable is insufficient.
Use an empty new_items array when no new conflict is reported; an accurate fact
need not appear here to be captured by the material reader.

Activity 3 - Separate issues and compare existing formulations.
Look for: A dispute needs its own practical resolution. Separate independently
contested conduct or rights that could be resolved differently, even with shared
actors or evidence. Supporting premises, legal theories, evidentiary gaps,
alternative remedies and legal-effect uncertainty do not alone create additional
disputes. A defence belongs to the issue it answers unless it reports another
independent conflict. Future harm is a risk unless a contested right exists now.
Compare with every active dispute. Shared words, people or sources do not prove
identity; changed supporting detail can leave the underlying conflict unchanged.
Outcome: Give each new issue a crisp label describing the conduct or position,
a neutral statement of the issue and a concise why_material. Include time or
place when needed to distinguish it. Do not invent facts, actors, terms, legal
status, proceedings or document contents. Do not repeat an unchanged issue.

Activity 4 - Select the supported operation and preserve its scope.
Look for: New account can introduce a dispute or change an identifiable saved
formulation. Relevant authorised review can repair NM's formulation using earlier
original account without requiring a fresh factual assertion. The review request
supplies authority to examine; original account supplies the restored content.
A diversion, analytical regrouping or legal theory does not change that account.
Every replacement must preserve the underlying scope, attribution and unknowns.
Multiple targets must be duplicates or the same issue. Restore wrongly merged
issues as distinct sourced successors with explicit lineage; do not erase an
independent underlying conflict to consolidate another.
Outcome: Put new issues in new_items, without relation or related_dispute_ids.
Put supported revisions in changes, with relation adds, corrects, contradicts
or withdraws and each exact active target ID in related_dispute_ids. Select the
latest source_id and relevant prior_source_ids, including original support for
repairs. Code attaches the exact saved words. A contextual citation does not
itself authorise a revision. When a target is ambiguous, do not guess or claim
that a saved record changed; preserve the unresolved distinction.
Set matter_scope=current only with a current matter ID, proposed for its opening,
and uncertain only for unresolved ownership. Another matter's account stays
separate. Use basis and clarification for factual uncertainty rather than changing
ownership. identification=identified means the dispute can be identified,
not that it is proved. Use needs_clarification only for a consequential missing
identity of the issue, with one relevant question.

Recovery: Missing source IDs in recovery_scope identify incomplete coverage to
examine against the full original account. They do not establish that a dispute
exists. Preserve retained_proposals without repeating them. Propose only supported
missing conflicts or authorised repairs; recovery does not require new rows.

Outcome: Return only the declared new_items and changes object and required
fields. Both arrays may be empty. Each proposed record needs original account
support for its conflict, attribution, scope and exact operation. Neither legal
relevance nor a request to record facts establishes a dispute."""


def _schema(*, latest_ids: tuple[str, ...], prior_ids: tuple[str, ...],
            has_current_matter: bool, dispute_ids: tuple[str, ...]) -> dict:
    item = addressed_item_schema(
        kinds=None, latest_ids=latest_ids, prior_ids=prior_ids,
        has_current_matter=has_current_matter)
    properties = dict(item["properties"])
    properties.update({
        "label": {"type": "string"},
        "identification": {"type": "string", "enum": [
            "identified", "needs_clarification"]},
        "clarification": {"type": "string"},
        "related_dispute_ids": {
            "type": "array", "items": {"type": "string",
                                       **({"enum": list(dispute_ids)} if dispute_ids else {})},
            **({"maxItems": 0} if not dispute_ids else {})},
    })
    item = {**item,
            "required": [*item["required"], "label", "identification",
                         "clarification", "related_dispute_ids"],
            "properties": properties}
    return operation_schema(item, link_field="related_dispute_ids",
                            known_ids=dispute_ids)


def extract_disputes(model: ModelPort, *, earlier: tuple[object, ...],
                     latest: str, current_matter_id: str | None,
                     prior_disputes: tuple[dict, ...] = (), source_treatments=None,
                     diagnostics: dict | None = None, recovery_scope: dict | None = None
                     ) -> tuple[MaterialCandidate, ...]:
    """Make one full-context dispute read and validate each source reference."""
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
    payload["prior_disputes"] = [
        derived_record({key: row.get(key) for key in (
            "id", "label", "statement", "identification", "clarification",
            "source_turn_id", "quoted")}
        | {"source_ids": list(saved_source_ids(row, prior_sources))})
        for row in prior_disputes]
    prompt = Prompt(
        system=_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        operation="extract_disputes",
    )
    output_limit = max(3072, min(8192, estimate_tokens(latest) * 8))
    if (estimate_tokens(prompt.user + (prompt.system or "")) + output_limit
            > model.context_budget(Tier.ROUTINE)):
        raise ContextOverflow("The full conversation exceeds this model's context budget")
    schema = _schema(latest_ids=tuple(latest_sources),
                     prior_ids=tuple(prior_sources),
                    has_current_matter=bool(current_matter_id),
                    dispute_ids=tuple(row["id"] for row in prior_disputes))
    def accept(data: dict) -> tuple[MaterialCandidate, ...]:
        known = {row["id"]: row for row in prior_disputes}
        proposals = operation_rows(data, link_field="related_dispute_ids")
        selected = [fill_empty_link_sources(
            row, link_field="related_dispute_ids", known=known,
            prior=prior_sources) for row in proposals]
        for row in selected:
            for dispute_id in row["related_dispute_ids"]:
                saved = known.get(dispute_id)
                if saved is None:
                    raise SchemaViolation("A revised dispute names an unknown saved ID")
                expected = saved_source_ids(saved, prior_sources)
                if not set(row.get("prior_source_ids", [])).intersection(expected):
                    raise SchemaViolation(
                        f"Related dispute {dispute_id!r} requires one of "
                        f"prior_source_ids {list(expected)!r}")
        rows = resolve_sources(selected, latest=latest_sources,
                               prior=prior_sources)
        rows = [{**row, "kind": "dispute"} for row in rows]
        candidates = parse_material(rows, latest=latest, earlier=earlier,
                                    current_matter_id=current_matter_id)
        return candidates

    return checked_unit_read(
        model, prompt, schema, output_limit, accept,
        unit_fields=("new_items", "changes"), diagnostics=diagnostics)
