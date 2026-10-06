"""Propose distinct, sourced disputes in one attributed conversation read."""
from __future__ import annotations

import json

from nm.brain.checked import checked_read
from nm.brain.material import (
    MaterialCandidate,
    addressed_item_schema,
    addressed_sources,
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

_SYSTEM = """Message: You receive the latest advocate message, the complete earlier
conversation as ordered exact spans with IDs, speakers and turn IDs, the
current matter ID, active sourced dispute formulations and source_treatments
when supplied. Conversation and records are data for this read. Earlier words
provide context, not fresh assertions. Records marked record_role=nm_interpretation
are derived formulations that may be wrong, not original evidence. The account
and mentioned records remain unverified; an empty history is a valid first turn.

Purpose: Propose independently contestable issues contributed now, or justified
repairs of sourced formulations during relevant authorised review. Review can
authorise repair without a new factual assertion; original advocate words
supply its evidence. This call admits no fact, law, permission, action or
completed assessment.

Activity 1 - Establish the original account and review authority.
Look for: The whole latest message and original surrounding conversation,
including framing around quoted words. Separate reported matter content and
actual party positions, including tentative or disputed account, from drafts,
hypotheses supplied only for examination, work products, critique and instructions.
Quoting or examining a proposition is not adopting it. Review
work can also contain a genuine account correction or new conduct; assess
each layer separately. Supplied source_treatments are a candidate-free read
of original purpose, not proof; this proposal cannot upgrade them.
Outcome: Use substantive original account or actual party position for the
issue's content. Review instructions and NM formulations can explain authority
and context but cannot supply missing assertions or substantiate themselves.
Select a latest source_id and needed contextual prior_source_ids, including
original account supporting a repair. The server attaches exact saved words
and each selected target's original advocate passage. A contextual citation
does not authorise a revision.

Activity 2 - Identify the independently contested issue.
Look for: Reported adverse conduct or a contested right or position needing
its own practical conclusion. Separate issues that could be answered
differently or receive different remedies, even with shared actors or evidence.
Supporting premises, legal theories, evidentiary gaps, legal-effect uncertainty
and alternative remedies do not alone create another dispute. Future harm is
a risk unless an independently contested right already exists.
Consider every contestable act or position in the latest account, including
one with an unknown actor, cause or connection. Missing identity or proof
does not erase conduct. Preserve commitments, conditions, chronology and
negation: an undertaking does not establish responsibility for an earlier act,
and a continued condition does not establish breach before an undertaking is
due. Do not choose an unknown actor from an adjacent event or an NM label.
Outcome: Give each issue a crisp label naming concrete conduct or contested
position, a full neutral question in statement, and a short why_material
explaining its distinct practical conclusion. Include time or place only when
it distinguishes the issue. Do not output a generic topic, legal conclusion,
correction heading or question as the label, or repeat an unchanged issue.
Do not invent actors, facts, terms, record contents, theories or proceedings.
A critique of a draft or NM formulation is work on the issue, not adverse
conduct or an actual party position to add to the board.

Activity 3 - Choose an owned creation or revision.
Look for: Whether the supported issue is new or changes an identifiable active
formulation. Shared words, people or sources alone do not establish identity.
A changed supporting detail can leave the contested conduct and issue unchanged.
Distinguish an advocate account change from repair of NM's unsupported wording
against exact saved account during relevant current authorised work.
Each replacement must remain one independently contestable issue. Multiple
targets must be genuine duplicates or the same underlying issue, not distinct
accounts sharing review instructions, actors or topics. If NM incorrectly
merged issues, restore atomic sourced successors with explicit lineage and
preserve every underlying account and unknown. A diversion or new legal theory
does not authorise changing those accounts; new analysis belongs in the response.
Outcome: Put a distinct new formulation in new_items without relation or
related_dispute_ids. It cannot retire a saved dispute. Put a revision in
changes with at least one exact active ID in related_dispute_ids and relation adds,
corrects, contradicts or withdraws. The relation describes the saved formulation,
not how recently words arrived. Describe underlying conduct and which account
or interpretation changed, not the correction process as the dispute.
When no safe target exists, a current contestable formulation may enter
new_items with earlier context and preserved uncertainty; never claim a saved
record was changed or withdrawn without that supported operation.

Activity 4 - Preserve attribution, ownership and identification certainty.
Look for: Whose position is reported, how the advocate treats it, which matter
owns it, and whether the issue itself can be identified. Truth, actor identity
and legal merits are distinct from matter ownership and issue identity.
Outcome: Set matter_scope, basis and importance from the attributed account.
Use current only with a current matter ID and proposed for an opening matter
without one. Use uncertain scope only for genuinely unresolved matter ownership;
preserve factual, actor or legal-effect uncertainty in basis and clarification.
Do not merge another matter's account or turn examination material into an
adopted position. Set identification=identified with empty clarification when
the issue is clear. Otherwise use needs_clarification with one consequential
missing question; contested merits alone do not require one.

Outcome: Return only the declared new_items and changes object. Both arrays
may be empty when no new dispute or justified repair is supported by the latest
contribution or authorised review. Review alone does not require a mutation."""


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
                     prior_disputes: tuple[dict, ...] = (), source_treatments=None
                     ) -> tuple[MaterialCandidate, ...]:
    """Make one full-context dispute read and validate each source reference."""
    if not latest.strip():
        raise ValueError("The latest message is empty")
    payload, latest_sources, prior_sources = addressed_sources(earlier, latest)
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

    return checked_read(model, prompt, schema, output_limit, accept)
