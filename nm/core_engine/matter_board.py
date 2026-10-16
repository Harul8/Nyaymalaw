"""The matter board: what the saved understanding holds about one conversation
(owner decision, 15 Oct 2026).

Read from the latest saved turn whose research set out the matter (research v7 or
later); a later courtesy or thanks does not empty it. Every field is the research
step's understanding of the advocate's words and the documents they sent, checked only
by that turn's research loop, so the board presents it as NM's working understanding
and facts as the advocate or a document gave them, never as established. A question's
status is what the saved research actually did for it, not a judgment that it was
answered well.
"""
from __future__ import annotations

from nm.core_engine import research

_UNDERSTOOD = research.QUESTION_PLANS


def _status(record, work_id):
    if work_id is None:
        return "not_researched"
    if work_id in record["failures"]:
        return "search_failed"
    return "researched" if work_id in record["searches"] else "not_researched"


def _where(words, rows):
    """Where a fact's quoted words appear: the advocate's messages, or one page of a
    document they sent (owner decisions, 15 Oct 2026). Code finds this; the model's
    understanding does not label it."""
    pieces = research.fact_pieces(words)
    if not pieces:
        return {"from": "not_found"}
    said = research._bare(" ".join(row["message"] for row in rows))
    if all(piece in said for piece in pieces):
        return {"from": "advocate"}
    pages = [(document, page) for row in rows for document in row.get("documents", ())
             for page in document["pages"]]
    places = []
    # Each piece of the quotation may sit on its own page, even of another document.
    for piece in pieces:
        found = next(((document, page) for document, page in pages if piece in research._bare(page["text"])), None)
        if found is None:
            return {"from": "not_found"}
        place = {"document": found[0]["name"], "page": found[1]["number"], "read_by": found[1]["read_by"],
                 **({"recording": True} if found[0].get("recording") else {})}
        if place not in places:
            places.append(place)
    return {"from": "document", "places": places}


def board(rows):
    """The board for a conversation's checked saved rows, newest understanding first."""
    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        record = (row.get("activities") or {}).get("research") or {}
        if record.get("contract") not in _UNDERSTOOD:
            continue
        understanding = record["plan"]["proposal"]["understanding"]
        if not understanding["disputes"] and not understanding["facts"]:
            continue
        work = {item["question_id"]: item["id"] for item in record["plan"]["work"]}
        names = {dispute["id"]: dispute["name"] for dispute in understanding["disputes"]}
        return {
            "state": "ready", "turn_id": row["turn_id"],
            "summary": understanding["summary"], "asked": list(understanding["asked"]),
            "instructions": list(understanding["ruled_out"]),
            "parties": [{"who": p["who"], "role": p["role"]} for p in understanding["parties"]],
            "facts": [{"id": f["id"], "fact": f["fact"], "certainty": f["certainty"], "words": f["advocate_words"],
                       **_where(f["advocate_words"], rows[:index + 1])}
                      for f in understanding["facts"]],
            # Each dispute with the facts it rests on (where it was picked up from), why each
            # question was asked, and, from research v9, why it matters (16 Oct 2026).
            "disputes": [{
                "id": d["id"], "name": d["name"], "between": list(d["between"]),
                **({"why_it_matters": d["why_it_matters"]} if d.get("why_it_matters", "").strip() else {}),
                "fact_ids": list(d["fact_ids"]),
                "questions": [{"question": q["question"], "why": q["why_needed"], "open": q["open_alternative"],
                               "status": _status(record, work.get(q["id"]))}
                              for q in d["legal_questions"]],
                "still_needed": list(d["missing_facts"]), "rights_at_stake": list(d["rights_at_stake"]),
                "relief_sought": list(d["relief_sought"])} for d in understanding["disputes"]],
            "related_points": [{"point": r["point"], "why": r["why_it_matters"], "dispute_id": r["dispute_id"] or None,
                                "dispute": names.get(r["dispute_id"])} for r in understanding["related_points"]],
        }
    return {"state": "empty"}
