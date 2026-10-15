"""The matter board: what the saved understanding holds about one conversation
(owner decision, 15 Oct 2026).

Read from the latest saved turn whose research set out the matter (research v7 or
later); a later courtesy or thanks does not empty it. Every field is the research
step's understanding of the advocate's own words, checked only by that turn's
research loop, so the board presents it as NM's working understanding and facts as
the advocate gave them, never as established. A question's status is what the saved
research actually did for it, not a judgment that it was answered well.
"""
from __future__ import annotations

from nm.core_engine import research

_UNDERSTOOD = (research.PICKED_CONTRACT, research.CONTRACT)


def _status(record, work_id):
    if work_id is None:
        return "not_researched"
    if work_id in record["failures"]:
        return "search_failed"
    return "researched" if work_id in record["searches"] else "not_researched"


def board(rows):
    """The board for a conversation's checked saved rows, newest understanding first."""
    for row in reversed(rows):
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
            "facts": [{"fact": f["fact"], "certainty": f["certainty"], "words": f["advocate_words"]}
                      for f in understanding["facts"]],
            "disputes": [{
                "id": d["id"], "name": d["name"], "between": list(d["between"]),
                "questions": [{"question": q["question"], "status": _status(record, work.get(q["id"]))}
                              for q in d["legal_questions"]],
                "still_needed": list(d["missing_facts"]), "rights_at_stake": list(d["rights_at_stake"]),
                "relief_sought": list(d["relief_sought"])} for d in understanding["disputes"]],
            "related_points": [{"point": r["point"], "why": r["why_it_matters"],
                                "dispute": names.get(r["dispute_id"])} for r in understanding["related_points"]],
        }
    return {"state": "empty"}
