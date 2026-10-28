"""The matter board: what the saved understanding holds about one conversation
(owner decision, 15 Oct 2026).

Read from the latest saved turn whose research set out the matter (research v7 or
later); a later courtesy or thanks does not empty it. Every field is the research
step's understanding of the advocate's words and the documents they sent, checked only
by that turn's research loop, so the board presents it as NM's working understanding
and facts as the advocate or a document gave them, never as established. A question's
status is what the saved research actually did for it, not a judgment that it was
answered well. From turn v5 each dispute also carries its checklist, as the answer of
that turn returned it and its checks admitted it (checklist.py). From 19 Oct 2026 the
disputes are listed most urgent first, as the answer shows its sections (P26).
"""
from __future__ import annotations

from nm.core_engine import checklist, research, response_rendering

_UNDERSTOOD = research.QUESTION_PLANS


def _status(record, work_id):
    if work_id is None:
        return "not_researched"
    if work_id in record["failures"]:
        return "search_failed"
    return "researched" if work_id in record["searches"] else "not_researched"


#: What the board says where the law has not been assessed for a dispute (plan AN.27, P6; invariant I3): never left to read as
#: "nothing is required".
_NO_QUESTIONS = "NM has not researched the law for this dispute, so what the law requires of it has not been assessed."
_NOT_FINISHED = ("NM's research of the law for this dispute did not finish, so what the law requires of it has not been "
                 "assessed.")
#: The points NM's own check raised that the board shows, and how much of each.
_OPEN_POINTS, _POINT_CHARACTERS = 5, 600


def _law(questions, assessed):
    """Whether the law has been assessed for a dispute: by a researched answer's checklist; researched, without one (an earlier
    conversation's); or not at all, with why in plain words."""
    if assessed:
        return {"state": "assessed", "why": ""}
    if any(question["status"] == "researched" for question in questions):
        return {"state": "researched", "why": ""}
    return {"state": "not_assessed", "why": _NOT_FINISHED if questions else _NO_QUESTIONS}


def _confirmed(record):
    """Whether NM's own check of its understanding was satisfied - its last round said sound, with no mechanical problem left -
    and, where it was not, the points the check raised."""
    rounds = record["plan"]["proposal"].get("review_rounds") or []
    last = rounds[-1] if rounds else None
    satisfied = last is not None and last["verdict"] == "sound" and not last["code_problems"]
    points = [] if satisfied or last is None else [
        problem["problem"][:_POINT_CHARACTERS] + ("..." if len(problem["problem"]) > _POINT_CHARACTERS else "")
        for problem in last["problems"]][:_OPEN_POINTS]
    return {"confirmed": satisfied, "open_points": points}


def _dispute(d, record, work, checklists):
    """One dispute as the board shows it: the facts it rests on, why each question was asked and what research did for it, why it
    matters (research v9, 16 Oct 2026), its checklist where the answer gave one, and whether the law has been assessed."""
    questions = [{"question": q["question"], "why": q["why_needed"], "open": q["open_alternative"],
                  "status": _status(record, work.get(q["id"]))} for q in d["legal_questions"]]
    listed = checklists.get(d["id"])
    listed = listed if listed is not None and listed["name"] == d["name"] else None
    return {"id": d["id"], "name": d["name"], "between": list(d["between"]),
            **({"why_it_matters": d["why_it_matters"]} if d.get("why_it_matters", "").strip() else {}),
            "fact_ids": list(d["fact_ids"]), "questions": questions,
            "still_needed": list(d["missing_facts"]), "rights_at_stake": list(d["rights_at_stake"]),
            "relief_sought": list(d["relief_sought"]),
            **({"checklist": listed} if listed is not None else {}),
            "law": _law(questions, listed is not None)}


def _pages(rows):
    """The pages of the documents a conversation's saved turns carry, in reading order, as the finder holds them."""
    return research.Pages(
        {"document": document["name"], "page": page["number"], "read_by": page["read_by"],
         "recording": bool(document.get("recording")), "text": page["text"]}
        for row in rows for document in row.get("documents", ()) for page in document["pages"])


def _where(words, rows, pages=None):
    """Where a fact's quoted words appear: the advocate's messages, or the page of a document they sent - or the two pages the
    words run over (owner decisions, 15 Oct 2026; plan AN.27, P2). Code finds this, with the one finder research.Pages is;
    the model's understanding does not label it. pages: the rows' pages as _pages gives them, when the caller has them."""
    pieces = research.fact_pieces(words)
    if not pieces:
        return {"from": "not_found"}
    said = research._bare(" ".join(row["message"] for row in rows))
    if all(piece in said for piece in pieces):
        return {"from": "advocate"}
    if pages is None:
        pages = _pages(rows)
    places = []
    # Each piece of the quotation may sit on its own page, even of another document.
    for piece in pieces:
        held = pages.holding(piece)
        if held is None:
            return {"from": "not_found"}
        for page in held:
            place = {"document": page["document"], "page": page["page"], "read_by": page["read_by"],
                     **({"recording": True} if page["recording"] else {})}
            if place not in places:
                places.append(place)
    return {"from": "document", "places": places}


def _urgent(disputes, checklists):
    """The disputes, most urgent first, as the answer shows its sections (owner decision P26,
    19 Oct 2026): by the earliest last day among the time limits worked out for a dispute's
    checklist, then in the understanding's order."""
    def key(pair):
        position, dispute = pair
        shown = checklists.get(dispute["id"])
        days = [limit["last_day"] for limit in (shown or {}).get("time_limits", ())
                if limit.get("last_day")] if shown and shown["name"] == dispute["name"] else []
        return (0, min(days), position) if days else (1, "", position)
    return [dispute for _, dispute in sorted(enumerate(disputes), key=key)]


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
        pages = _pages(rows[:index + 1])
        # What each dispute needs, saved with this turn from its answer (turn v5, 18 Oct
        # 2026); a dispute's checklist is shown only under the same id and name.
        dates = {saved["turn_id"]: saved["response"]["at"] for saved in rows[:index + 1]}
        checklists = checklist.for_board(row.get("records"), dates)
        for shown in checklists.values():
            for limit in shown["time_limits"]:
                limit["rows"] = response_rendering.limit_rows(limit)
        return {
            "state": "ready", "turn_id": row["turn_id"],
            "summary": understanding["summary"], "asked": list(understanding["asked"]),
            "instructions": list(understanding["ruled_out"]),
            "parties": [{"who": p["who"], "role": p["role"]} for p in understanding["parties"]],
            "facts": [{"id": f["id"], "fact": f["fact"], "certainty": f["certainty"], "words": f["advocate_words"],
                       **_where(f["advocate_words"], rows[:index + 1], pages)}
                      for f in understanding["facts"]],
            # Each dispute with the facts it rests on (where it was picked up from), why each
            # question was asked, and, from research v9, why it matters (16 Oct 2026).
            "disputes": [_dispute(d, record, work, checklists) for d in _urgent(understanding["disputes"], checklists)],
            "understanding": _confirmed(record),
            "related_points": [{"point": r["point"], "why": r["why_it_matters"], "dispute_id": r["dispute_id"] or None,
                                "dispute": names.get(r["dispute_id"])} for r in understanding["related_points"]],
        }
    return {"state": "empty"}
