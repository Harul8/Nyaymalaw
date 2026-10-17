"""The matter's checklist (owner decisions, 17 Oct 2026; built 18 Oct): for each dispute,
what the case needs as the held law requires it, and where each item stands.

Each dispute's part of an answer returns its dispute's checklist (writer v6): code checks
every quote at admission and the independent review checks the list. This module keeps
the matter's current checklist as the conversation's records, saved with each answered
turn (turn v5) and re-derived exactly when the conversation is reopened, so a later turn
reads it as current records and the board shows it. Nothing here judges an item: its
state is what the admitted answer gave, and an item in hand always names the words that
hold it. There is no manual tick (rules reused from the archived legal engine, not its
code).
"""
from __future__ import annotations

from copy import deepcopy

from nm.core_engine import research
from nm.shared.citation_contracts import statute_title

CONTRACT = "core_checklist_v1"
GROUPS = ("needed", "would_strengthen")
STATES = ("in_hand", "coming_or_unclear", "not_given", "not_available")


def _current(context):
    record = (context.get("current_records") or {}).get("checklist")
    return record if isinstance(record, dict) and record.get("contract") == CONTRACT else None


def saved(context):
    """The matter's checklist items as the latest saved turn left them, by id (K1, K2...)."""
    record = _current(context) or {}
    return {item["id"]: item for dispute in record.get("disputes", []) for item in dispute["items"]}


def _law(selected, sources, turn_id):
    source = sources[selected["source_id"]]
    title = (statute_title(source["title"], source["source_identity"].get("act_id", ""))
             if source["kind"] == "provision" else source["title"])
    return {"kind": source["kind"], "title": title, "locator": source["locator"], "words": selected["text"],
            "source_id": selected["source_id"], "held_in": turn_id}


def _evidence(selected, sources):
    source = sources[selected["source_id"]]
    place = ({"from": "document", "document": source["title"], "page": source["locator"]}
             if source["kind"] == "document" else {"from": "message"})
    return {**place, "turn_id": source["source_identity"]["turn_id"], "words": selected["text"],
            "source_id": selected["source_id"]}


def _same(law, other):
    return all(law.get(key) == other.get(key) for key in ("kind", "title", "locator", "words"))


def _item(item, earlier, sources, turn_id):
    """One admitted item as the matter keeps it. A not-yet-given item keeps the turn in
    which NM first listed it, carried or re-tied to the same law words."""
    carried = earlier.get(item["carries"]) if item["carries"] else None
    law = deepcopy(carried["law"]) if carried else _law(item["law"], sources, turn_id)
    before = carried or next((row for row in earlier.values() if _same(row["law"], law)), None)
    asked = None
    if item["status"] == "not_given":
        asked = (before["asked_in"] if before and before["status"] == "not_given" and before.get("asked_in")
                 else turn_id)
    return {"id": None, "need": item["need"], "group": item["group"], "law": law, "status": item["status"],
            "evidence": _evidence(item["evidence"], sources) if item["evidence"] else None,
            "asked_in": asked, "noted_in": turn_id}


def _limits(names, calculation):
    """The time limits a dispute's section named, as code worked them out that turn."""
    calculation = calculation or {}
    worked = {entry["what"]: entry for entry in calculation.get("calculations", [])}
    unassessed = {entry["what"]: entry for entry in calculation.get("not_assessed", [])}
    out = []
    for name in dict.fromkeys(names):
        if name in worked:
            entry = worked[name]
            out.append({"what": name, "provision": entry["provision_name"], "last_day": entry["working"]["last_day"],
                        "standing": deepcopy(entry["standing"]), "as_of": calculation.get("today")})
        elif name in unassessed:
            out.append({"what": name, "not_assessed": unassessed[name]["why"]})
    return out


def records(context, activity):
    """The conversation's records after this turn. A dispute this answer covers takes the
    checklist its section returned; a dispute it does not cover (or whose section is held
    back) keeps the checklist saved for it where the understanding still names it by the
    same id and name; the rest of the records is kept as it was. An answer covering no
    dispute changes nothing."""
    previous = deepcopy(context.get("current_records") or {})
    draft, record = activity.get("draft") or {}, activity.get("research") or {}
    if "checklists" not in draft or record.get("contract") not in research.QUESTION_PLANS:
        return previous
    turn_id = context["latest"]["turn_id"]
    earlier = saved(context)
    kept = {(dispute["id"], dispute["name"]): dispute for dispute in (_current(context) or {}).get("disputes", [])}
    held = set((activity.get("release") or {}).get("parts") or [])
    written = {}
    for index, (part, given) in enumerate(zip(draft["parts"], draft["checklists"])):
        if part["dispute_id"] is not None and index not in held:
            written.setdefault(part["dispute_id"], given)
    if not written:
        # An answer that covers no dispute (a courtesy, or every section held back)
        # leaves the matter's checklist as it was.
        return previous
    disputes, number = [], 0
    for dispute in record["plan"]["proposal"]["understanding"]["disputes"]:
        given = written.get(dispute["id"])
        if given is not None:
            entry = {"id": dispute["id"], "name": dispute["name"], "answered_in": turn_id,
                     "time_limits": _limits(given["time_limits"], activity.get("calculation")),
                     "items": [_item(item, earlier, activity["sources"], turn_id) for item in given["items"]]}
        elif (dispute["id"], dispute["name"]) in kept:
            entry = deepcopy(kept[(dispute["id"], dispute["name"])])
        else:
            continue
        for item in entry["items"]:
            number += 1
            item["id"] = f"K{number}"
        disputes.append(entry)
    previous["checklist"] = {"contract": CONTRACT, "turn_id": turn_id, "disputes": disputes}
    return previous


def for_board(row_records, dates):
    """Each dispute's checklist as the board shows it, by dispute id; dates: when each
    turn was answered, so the board can say when NM asked and when words were given."""
    record = (row_records or {}).get("checklist")
    if not isinstance(record, dict) or record.get("contract") != CONTRACT:
        return {}
    shown = {}
    for dispute in record["disputes"]:
        items = []
        for item in dispute["items"]:
            evidence = deepcopy(item["evidence"])
            if evidence is not None:
                evidence["given_at"] = dates.get(evidence["turn_id"])
            items.append({**{key: deepcopy(item[key]) for key in ("id", "need", "group", "status", "law")},
                          "evidence": evidence, "asked_at": dates.get(item["asked_in"]) if item["asked_in"] else None})
        shown[dispute["id"]] = {"name": dispute["name"], "answered_at": dates.get(dispute["answered_in"]),
                                "time_limits": deepcopy(dispute["time_limits"]), "items": items,
                                "in_hand": sum(item["status"] == "in_hand" for item in items)}
    return shown
