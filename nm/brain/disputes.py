"""Propose distinct, sourced disputes in one attributed conversation read."""
from __future__ import annotations

import json

from nm.brain.checked import checked_read
from nm.brain.material import (
    MaterialCandidate,
    addressed_item_schema,
    addressed_sources,
    fill_empty_link_sources,
    parse_material,
    resolve_sources,
    saved_source_ids,
)
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
)

_SYSTEM = """Message: You receive the advocate's latest message and the
complete earlier conversation as ordered source spans with IDs, speakers, and
turn IDs, plus the current matter ID and active sourced dispute formulations
if they exist. The spans contain the original words in order. Earlier words
and formulations are context, not new assertions. The account and mentioned
records remain unverified. An empty earlier conversation is a valid first turn.

Purpose: Identify independently contestable disputes contributed by the latest
message in context and whether each dispute is clearly identifiable. This is a
sourced formulation, not an admitted fact, legal finding, action, or completed
assessment.

Look for: Each asserted right, obligation, or completed harmful act needing
its own practical conclusion, rather than each paragraph, person, encounter,
or story. Separate conclusions that could be answered differently or receive
different remedies, even when actors, place, or evidence overlap. Do not make
supporting acts, positions, legal theories, evidence questions, or alternative
remedies into separate disputes. A possible future harm is a risk unless an
independently contested right already exists. Interpret a short answer or
correction using earlier attributed words. When the latest words change an
active formulation, identify its exact prior dispute ID. Shared people or
source passages alone do not establish that two formulations are the same.
An unanswered question about whether a reported step was effective, or the
absence of a record, belongs with the underlying contested conduct unless
the advocate reports a separately contested act, right, or position.
Preserve uncertainty and matter scope without repeating unchanged disputes.
When a supporting detail changes but the contested conduct remains the same,
retain that dispute's identity and describe the conduct, not the correction.

Outcome: Return only the declared JSON object with a `disputes` array. Give
each issue a crisp, plain-language `label` for the board naming the concrete
conduct or contested position. Paraphrase the advocate's words when that makes
the heading clearer, but preserve the meaning and do not add facts. Include
the actor and act or object that distinguish this issue from the other issues
in the matter; include timing or place only when it helps that distinction.
Avoid a generic topic label, legal conclusion, correction label, or question.
Do not imply an unstated legal or contractual requirement in the heading. Put the
full neutral question in `statement`. In `why_material`, explain why the words
identify a distinct question needing a practical conclusion, without
predicting its legal outcome. Set
`identification` to `identified` only when the issue itself is
clear from the advocate's words; this never proves an allegation or legal
merit. Otherwise set `needs_clarification` and ask the single consequential
missing question in `clarification`. Do not call an issue uncertain merely
because its merits are contested. Ground each formulation in a latest-message
`source_id`; the server inserts those exact saved words. If earlier words are
needed to understand a reply, change, or withdrawal, select their IDs in
`prior_source_ids`. Each active dispute supplies `source_ids` addressing its
saved advocate passage. For every `related_dispute_id`, select one of that
item's `source_ids` if selecting any earlier spans. If that array is empty,
the server resolves each linked item's exact saved advocate passage. Select
other earlier spans when needed to understand the change. Set
`related_dispute_ids` to the exact active formulations
changed, or an empty array when no safe link exists. Corrections and
withdrawals must identify what they change. Use `withdraws` only with at least
one exact active `related_dispute_id`. If no safe link exists, express the
uncertainty without claiming that an earlier dispute was withdrawn. Choose
`relation`, `matter_scope`,
`basis`, and `importance` according to the attributed evidence. Use current
scope only when a current matter ID is supplied; use proposed for a possible
new matter. Return an empty array when the latest message adds no dispute.
Do not invent an event, record content, legal theory, or proceeding."""


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
    return {
        "type": "object", "additionalProperties": False,
        "required": ["disputes"],
        "properties": {"disputes": {"type": "array", "items": item}},
    }


def extract_disputes(model: ModelPort, *, earlier: tuple[object, ...],
                     latest: str, current_matter_id: str | None,
                     prior_disputes: tuple[dict, ...] = ()
                     ) -> tuple[MaterialCandidate, ...]:
    """Make one full-context dispute read and validate each source reference."""
    if not latest.strip():
        raise ValueError("The latest message is empty")
    payload, latest_sources, prior_sources = addressed_sources(earlier, latest)
    payload["current_matter_id"] = current_matter_id
    payload["prior_disputes"] = [
        {key: row.get(key) for key in (
            "id", "label", "statement", "identification", "clarification",
            "source_turn_id", "quoted")}
        | {"source_ids": list(saved_source_ids(row, prior_sources))}
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
        if any(row["relation"] == "withdraws" and not row["related_dispute_ids"]
               for row in data["disputes"]):
            raise SchemaViolation(
                "A withdrawal needs an exact active related dispute ID; "
                "express uncertainty if no safe link exists")
        selected = [fill_empty_link_sources(
            row, link_field="related_dispute_ids", known=known,
            prior=prior_sources) for row in data["disputes"]]
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
