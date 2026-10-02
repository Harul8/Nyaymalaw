"""Project current dispute readings from their attributed conversation history."""
from __future__ import annotations

from nm.brain.material import SCOPES
from nm.work_the_file.matter_contracts import Matter

_RELATIONS = frozenset({"new", "adds", "corrects", "contradicts", "withdraws"})
_IDENTIFICATIONS = frozenset({"identified", "needs_clarification"})


def belongs_to_current_matter(scope: object, *, route: object,
                              opened_before_turn: bool,
                              first_saved_turn: bool) -> bool:
    """Keep the opening chat's proposals, not a later possible new matter.

    An older turn without a route has no verifiable opening transition. Only
    its first saved turn can seed the matter; later ambiguous proposals remain
    in the raw conversation until their ownership is established.
    """
    return scope == "current" or (scope == "proposed" and
                                  not opened_before_turn and
                                  (route in ("non_matter", "matter")
                                   or (route is None and first_saved_turn)))


def _short_label(quoted: str) -> str:
    source = " ".join(quoted.split())
    if len(source) <= 120:
        return source
    excerpt = source[:117].rsplit(" ", 1)[0] or source[:117]
    return excerpt.rstrip() + "..."


def _read_identity(proposal: dict) -> tuple[str, str, str, list[str]] | None:
    """Read display fields without confusing legacy absence with a valid link."""
    label = proposal.get("label")
    identification = (proposal["identification"] if "identification" in proposal
                      else "unassessed")
    clarification = proposal.get("clarification")
    related = proposal.get("related_dispute_ids")
    if label is None:
        label = _short_label(proposal["quoted"])
    if clarification is None:
        clarification = ""
    if related is None:
        related = []
    if (not isinstance(label, str) or not label.strip()
            or not isinstance(clarification, str)
            or (identification not in _IDENTIFICATIONS
                and not (identification == "unassessed"
                         and "identification" not in proposal))
            or not isinstance(related, list)
            or any(not isinstance(item, str) or not item.strip() for item in related)
            or len(related) != len(set(related))):
        return None
    return label.strip(), identification, clarification.strip(), related


def proposed_disputes(matter: Matter, *, prior_conversation=()) -> dict:
    """Expose active readings while retaining every verified source-linked change.

    A model can identify an issue without establishing the underlying facts.
    Only a validated link to an active proposal may retire that proposal.
    """
    active: dict[str, dict] = {}
    history: list[dict] = []
    problems: list[str] = []
    prior_words = {(item.turn_id, item.role): item.text
                   for item in prior_conversation}
    seen_ids: set[str] = set()
    matter_opened = False
    for turn_index, entry in enumerate(matter.brain_chat):
        message = entry.get("message")
        response = entry.get("response")
        proposals = response.get("material") if isinstance(response, dict) else None
        route = response.get("route") if isinstance(response, dict) else None
        opened_before_turn = matter_opened
        if route == "matter":
            matter_opened = True
        if (not isinstance(message, str) or not isinstance(proposals, list)
                or entry.get("committed") is not True
                or entry.get("release_state") != "released"
                or response.get("turn_id") != entry.get("turn_id")
                or entry.get("elements") != response.get("elements")):
            problems.append("a conversation proposal could not be read")
            continue
        previous_active = dict(active)
        turn_rows: list[dict] = []
        turn_retire: set[str] = set()
        turn_incomplete = False
        for proposal in proposals:
            if not isinstance(proposal, dict):
                problems.append("a conversation proposal could not be read")
                turn_incomplete = True
                continue
            if proposal.get("kind") != "dispute":
                continue
            scope = proposal.get("matter_scope")
            if scope not in SCOPES:
                problems.append("a dispute proposal has an unknown matter scope")
                turn_incomplete = True
                continue
            if not belongs_to_current_matter(
                    scope, route=route, opened_before_turn=opened_before_turn,
                    first_saved_turn=turn_index == 0):
                continue
            quoted = proposal.get("quoted")
            statement = proposal.get("statement")
            proposal_id = proposal.get("id")
            references = proposal.get("prior_references")
            relation = proposal.get("relation")
            if (scope not in ("current", "proposed", "uncertain")
                    or proposal.get("state") != "proposed"
                    or not isinstance(statement, str) or not statement.strip()
                    or not isinstance(quoted, str) or not quoted.strip()
                    or quoted not in message
                    or proposal.get("source_turn_id") != entry.get("turn_id")
                    or not isinstance(proposal_id, str) or not proposal_id.strip()
                    or proposal_id in seen_ids
                    or relation not in _RELATIONS
                    or not isinstance(references, list)
                    or (relation != "new" and not references)
                    or (relation == "withdraws" and not proposal.get(
                        "related_dispute_ids"))
                    or any(not isinstance(ref, dict)
                           or not isinstance(ref.get("quoted"), str)
                           or not ref["quoted"].strip()
                           or ref["quoted"] not in prior_words.get(
                               (ref.get("turn_id"), ref.get("role")), "")
                           for ref in references)):
                problems.append("a dispute proposal lacks its saved source")
                turn_incomplete = True
                continue
            identity = _read_identity(proposal)
            if identity is None:
                problems.append("a dispute proposal has an invalid display contract")
                turn_incomplete = True
                continue
            label, identification, clarification, related = identity
            if ((relation == "new" and related)
                    or any(item not in previous_active for item in related)
                    or any(not any(
                        ref.get("role") == "advocate"
                        and ref.get("turn_id") == previous_active[item]["source_turn_id"]
                        and (previous_active[item]["quoted"] in ref["quoted"]
                             or ref["quoted"] in previous_active[item]["quoted"])
                        for ref in references) for item in related)):
                problems.append("a dispute change names no active saved dispute")
                turn_incomplete = True
                continue
            row = {**proposal, "label": label,
                   "identification": identification,
                   "clarification": clarification,
                   "related_dispute_ids": related}
            seen_ids.add(proposal_id)
            history.append(row)
            turn_rows.append(row)
            turn_retire.update(related)
        if not turn_incomplete:
            for related_id in turn_retire:
                active.pop(related_id)
            for row in turn_rows:
                if row["relation"] != "withdraws":
                    active[row["id"]] = row
        turn_id = entry.get("turn_id")
        if isinstance(turn_id, str):
            prior_words[(turn_id, "advocate")] = message
            elements = response.get("elements")
            if isinstance(elements, list):
                prior_words[(turn_id, "nm")] = "\n".join(
                    item.get("text", "") for item in elements
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                    and item["text"].strip())
    return {"state": "incomplete" if problems else "ok",
            "rows": list(active.values()), "history": history,
            "problems": problems}
