"""Project an attributed material record from saved, source-checked turns."""
from __future__ import annotations

from nm.brain.dispute_state import belongs_to_current_matter
from nm.brain.material import BASES, IMPORTANCE, KINDS, PLACEMENTS, RELATIONS, SCOPES
from nm.work_the_file.matter_contracts import Matter


def sourced_detail_for_display(row: dict, saved_words: str) -> dict | None:
    """Expose old unchecked readings as their exact advocate passage only."""
    quoted = row.get("quoted")
    if (not isinstance(quoted, str) or not quoted.strip()
            or quoted not in saved_words):
        return None
    if row.get("grounding") == "advocate_semantic_v1":
        return row
    return {**row, "statement": quoted,
            "why_material": (
                "This earlier interpretation has not been "
                "independently checked."),
            "placement": "unresolved", "dispute_ids": [],
            "basis": "uncertain", "importance": "uncertain",
            "grounding": "legacy_unverified"}


def _identity(proposal: dict) -> tuple[str, list[str], list[str]] | None:
    """Older detail proposals had no placement; leave them unassigned."""
    fields = ("placement", "dispute_ids", "related_material_ids")
    if not any(field in proposal for field in fields):
        return "unresolved", [], []
    placement, disputes, related = (proposal.get(field) for field in fields)
    if (placement not in PLACEMENTS or not isinstance(disputes, list)
            or not isinstance(related, list)
            or any(not isinstance(item, str) or not item.strip()
                   for item in [*disputes, *related])
            or len(disputes) != len(set(disputes))
            or len(related) != len(set(related))
            or (placement == "disputes") != bool(disputes)):
        return None
    return placement, disputes, related


def _source_matches(proposal: dict, *, turn: dict,
                    prior_words: dict[tuple[str, str], str]) -> bool:
    quote = proposal.get("quoted")
    references = proposal.get("prior_references")
    relation = proposal.get("relation")
    return (
        proposal.get("state") == "proposed"
        and proposal.get("source_turn_id") == turn.get("turn_id")
        and isinstance(quote, str) and bool(quote.strip())
        and quote in turn["message"]
        and isinstance(proposal.get("statement"), str)
        and bool(proposal["statement"].strip())
        and isinstance(proposal.get("why_material"), str)
        and bool(proposal["why_material"].strip())
        and relation in RELATIONS
        and proposal.get("matter_scope") in SCOPES
        and proposal.get("basis") in BASES
        and proposal.get("importance") in IMPORTANCE
        and isinstance(references, list)
        and (relation == "new" or bool(references))
        and all(isinstance(ref, dict)
                and ref.get("role") in ("advocate", "nm")
                and isinstance(ref.get("quoted"), str)
                and bool(ref["quoted"].strip())
                and ref["quoted"] in prior_words.get(
                    (ref.get("turn_id"), ref.get("role")), "")
                for ref in references)
    )


def _current_links(dispute_id: str, *, active: set[str],
                   successors: dict[str, set[str]]) -> set[str]:
    """Carry an old link across a single clear replacement, never a split."""
    reached: set[str] = set()
    pending = [dispute_id]
    seen: set[str] = set()
    while pending:
        item = pending.pop()
        if item in seen:
            continue
        seen.add(item)
        if item in active:
            reached.add(item)
        else:
            pending.extend(successors.get(item, ()))
    return reached


def material_record(matter: Matter, *, disputes: dict,
                    prior_conversation=()) -> dict:
    """Active detail per dispute, matter-wide and unresolved, with full history.

    Only an explicit, validated prior-material link can retire a detail. A
    corrected allegation is still an attributed account, never a proved fact.
    """
    if disputes.get("state") != "ok":
        return {"state": "incomplete", "rows": [], "by_dispute": {}, "matter": [],
                "unresolved": [], "history": [],
                "problems": ["the saved dispute record is incomplete"]}
    dispute_history = disputes["history"]
    known_disputes = {row["id"]: row for row in dispute_history}
    active_disputes = {row["id"] for row in disputes["rows"]}
    successors: dict[str, set[str]] = {}
    for row in dispute_history:
        if row.get("relation") != "withdraws":
            for prior_id in row.get("related_dispute_ids", []):
                successors.setdefault(prior_id, set()).add(row["id"])

    active: dict[str, dict] = {}
    history: list[dict] = []
    problems: list[str] = []
    seen_ids: set[str] = set()
    prior_words = {(item.turn_id, item.role): item.text
                   for item in prior_conversation}
    disputes_by_turn: dict[str, list[dict]] = {}
    for row in dispute_history:
        disputes_by_turn.setdefault(row["source_turn_id"], []).append(row)
    active_at_turn: set[str] = set()
    matter_opened = False
    for turn_index, turn in enumerate(matter.brain_chat):
        message, response = turn.get("message"), turn.get("response")
        proposals = response.get("material") if isinstance(response, dict) else None
        route = response.get("route") if isinstance(response, dict) else None
        opened_before_turn = matter_opened
        if route == "matter":
            matter_opened = True
        if (not isinstance(message, str) or not isinstance(proposals, list)
                or turn.get("committed") is not True
                or turn.get("release_state") != "released"
                or response.get("turn_id") != turn.get("turn_id")
                or turn.get("elements") != response.get("elements")):
            problems.append("a saved material turn could not be read")
            continue
        for dispute in disputes_by_turn.get(turn["turn_id"], []):
            active_at_turn.difference_update(dispute.get("related_dispute_ids", []))
            if dispute["relation"] != "withdraws":
                active_at_turn.add(dispute["id"])
        previous_active = dict(active)
        additions: list[dict] = []
        retire: set[str] = set()
        bad_turn = False
        for proposal in proposals:
            if not isinstance(proposal, dict):
                problems.append("a saved material proposal could not be read")
                bad_turn = True
                continue
            if proposal.get("kind") == "dispute":
                continue
            if proposal.get("kind") not in KINDS:
                problems.append("a saved material kind is unknown")
                bad_turn = True
                continue
            if proposal.get("matter_scope") not in SCOPES:
                problems.append("a material detail has an unknown matter scope")
                bad_turn = True
                continue
            if not belongs_to_current_matter(
                    proposal.get("matter_scope"), route=route,
                    opened_before_turn=opened_before_turn,
                    first_saved_turn=turn_index == 0):
                continue
            proposal_id = proposal.get("id")
            placement = _identity(proposal)
            if (not isinstance(proposal_id, str) or not proposal_id.strip()
                    or proposal_id in seen_ids or proposal_id in known_disputes
                    or placement is None
                    or not _source_matches(proposal, turn=turn,
                                           prior_words=prior_words)
                    or (proposal.get("relation") == "withdraws"
                        and not proposal.get("related_material_ids"))):
                problems.append("a material detail lacks a valid saved source or identity")
                bad_turn = True
                continue
            scope, dispute_ids, related = placement
            if (any(dispute_id not in active_at_turn for dispute_id in dispute_ids)
                    or any(item not in previous_active for item in related)
                    or (proposal["relation"] == "new" and related)
                    or any(not any(
                        ref.get("role") == "advocate"
                        and ref.get("turn_id") == previous_active[item]["source_turn_id"]
                        and (previous_active[item]["quoted"] in ref["quoted"]
                             or ref["quoted"] in previous_active[item]["quoted"])
                        for ref in proposal["prior_references"])
                        for item in related)):
                problems.append("a material detail has an unsupported record link")
                bad_turn = True
                continue
            row = {**proposal, "placement": scope, "dispute_ids": dispute_ids,
                   "related_material_ids": related}
            additions.append(row)
            if proposal["relation"] in ("corrects", "withdraws"):
                retire.update(related)
        if not bad_turn:
            for item in retire:
                active.pop(item)
            for row in additions:
                seen_ids.add(row["id"])
                history.append(row)
                if row["relation"] != "withdraws":
                    active[row["id"]] = row
        prior_words[(turn["turn_id"], "advocate")] = message
        prior_words[(turn["turn_id"], "nm")] = "\n".join(
            item.get("text", "") for item in response["elements"]
            if isinstance(item, dict) and isinstance(item.get("text"), str)
            and item["text"].strip())

    by_dispute: dict[str, list[dict]] = {item: [] for item in active_disputes}
    matter_rows: list[dict] = []
    unresolved: list[dict] = []
    projected_rows: list[dict] = []
    unverified_count = 0
    for row in active.values():
        safe = sourced_detail_for_display(
            row, prior_words.get((row["source_turn_id"], "advocate"), ""))
        if safe is None:
            problems.append("a material detail lacks its saved advocate passage")
            continue
        if safe.get("grounding") == "legacy_unverified":
            # Earlier exact quotes remain visible, but their model-written
            # paraphrases have not passed the independent grounding check.
            # Do not feed those paraphrases or their old dispute links into
            # source-backed research as if they had been verified.
            projected_rows.append(safe)
            unresolved.append(safe)
            unverified_count += 1
            continue
        projected_rows.append(safe)
        if safe["placement"] == "matter":
            matter_rows.append(safe)
        elif safe["placement"] == "unresolved":
            unresolved.append(safe)
        else:
            links: set[str] = set()
            ambiguous = False
            for dispute_id in safe["dispute_ids"]:
                reached = _current_links(dispute_id, active=active_disputes,
                                         successors=successors)
                if len(reached) == 1:
                    links.update(reached)
                else:
                    ambiguous = True
            for dispute_id in links:
                by_dispute[dispute_id].append(safe)
            if ambiguous:
                unresolved.append(safe)
    return {"state": "incomplete" if problems else "ok",
            "rows": projected_rows, "unverified_count": unverified_count,
            "by_dispute": by_dispute, "matter": matter_rows,
            "unresolved": unresolved, "history": history,
            "problems": problems}
