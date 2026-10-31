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

from nm.core_engine import checklist, copy_figures, extents, research, response_rendering

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
    and, where it was not, the points left open: code's own (a quotation not found, say) as well as the model's, so that "not
    confirmed" never stands without its reason (plan AN.28, B11)."""
    rounds = record["plan"]["proposal"].get("review_rounds") or []
    last = rounds[-1] if rounds else None
    satisfied = last is not None and last["verdict"] == "sound" and not last["code_problems"]
    points = [] if satisfied or last is None else [
        problem["problem"][:_POINT_CHARACTERS] + ("..." if len(problem["problem"]) > _POINT_CHARACTERS else "")
        for problem in [*last["code_problems"], *last["problems"]]][:_OPEN_POINTS]
    return {"confirmed": satisfied, "open_points": points}


#: Said where the board has no timeline to show for papers that were sent (plan AN.27, P9; invariant I3): never left to read as
#: "nothing happened".
_NOT_MADE = "NM did not make a timeline of the papers when it answered this conversation, so there is none to show."


def _gaps(document, stretches):
    """What NM could not read of a paper, in plain words: the pages its reader could not make out, and the stretches it could not
    make a timeline from."""
    word = "part" if document.get("recording") else "page"
    said = []
    unread = [str(page["number"]) for page in document.get("unread") or ()]
    if unread:
        said.append(f"NM could not read {word}{'s' if len(unread) > 1 else ''} {', '.join(unread)} of this paper.")
    if stretches:
        many = len(stretches) > 1 or "-" in stretches[0]
        said.append(f"NM could not make a timeline from {word}{'s' if many else ''} {', '.join(stretches)} of this paper.")
    return said


def _event(group, sent):
    """One event of the timeline: the plan's event that stands for the group (research.events_once) and, where other papers record the
    same event on copies of its page (plan AN.27, P22), where else it is."""
    event = group["event"]
    return {"id": event["id"], "date": event["date"], "dated": bool(event["sort"]), "kind": event["kind"],
            "what": event["what"], "said_by": event["said_by"], "document": event["document"],
            "pages": list(event["pages"]),
            **({"recording": True} if sent.get(event["source"], {}).get("recording") else {}),
            "words": event["words"], "located": event["anchored"],
            **({"also_in": [{"document": other["document"], "pages": list(other["pages"])} for other in group["also"]]}
               if group["also"] else {})}


def _timeline(record, rows, copies=()):
    """The timeline of the papers sent, as the plan of the turn the board shows kept it (plan AN.27, P9; invariant I4): its events in
    its order - an event that several papers record, as a copy of a page does, listed once (P22; copies are the pairs of pages that
    are copies of one page) - each with where its words are and whether they were located, and every paper with what NM read of it.
    'none' where no papers were sent; 'not_made' where they were but the plan kept no timeline (an earlier conversation's)."""
    sent = {f"{row['turn_id']}:d{number}": document
            for row in rows for number, document in enumerate(row.get("documents") or (), 1)}
    if not sent:
        return {"state": "none"}
    proposal = record["plan"]["proposal"]
    if "chronology" not in proposal:
        return {"state": "not_made", "why": _NOT_MADE}
    given, stretches = {}, {}
    for event in proposal["chronology"]:
        given[event["source"]] = given.get(event["source"], 0) + 1
    for failure in proposal["chronology_failures"]:
        stretches.setdefault(failure["document"], []).append(failure["pages"])
    papers = []
    for source, document in sent.items():
        lost, count = stretches.get(document["name"], []), given.get(source, 0)
        gaps = _gaps(document, lost)
        state = "not_read" if not document["pages"] or (lost and not count) else "partly_read" if gaps else "read"
        if state == "not_read" and not gaps:
            gaps = ["NM could not read this paper."]
        papers.append({"name": document["name"], "pages_read": len(document["pages"]), "events": count, "state": state,
                       "why": " ".join(gaps), **({"recording": True} if document.get("recording") else {})})
    return {"state": "ready", "documents": papers,
            "events": [_event(group, sent) for group in research.events_once(proposal["chronology"], copies)]}


def _sent(rows):
    """The pages of the documents sent up to the turn the board shows, as the copy finder holds them."""
    return [{"document": document["name"], "key": f"{row['turn_id']}:d{number}", "page": page["number"], "text": page["text"],
             **({"recording": True} if document.get("recording") else {})}
            for row in rows for number, document in enumerate(row.get("documents") or (), 1) for page in document["pages"]]


def _copies(pages):
    """The figures that copies of one page read differently, among the pages of the documents sent up to the turn the board shows
    (plan AN.27, P13; invariant I6): found by code from the saved pages, never settled - each is both readings and the words before
    it."""
    return [{"first": {"document": found["first"]["document"], "page": found["first"]["page"]},
             "second": {"document": found["second"]["document"], "page": found["second"]["page"]},
             "figures": found["figures"]} for found in copy_figures.differences(pages)]


def _extents(record, pages):
    """The figures the papers record, added up by code for each property or account (plan AN.27, P13d; AN.28, D7; invariant I6):
    the transactions the plan kept, those whose words and figures were found added by extents.py - areas with areas, sums with
    sums - and the rest listed and never added, giver by giver (P20 (a)) with each giver's sums, what a paper's stated whole leaves
    after them or how far they go beyond it, and the caveat that a sum is only of what was found. One sale read on copies of a page is one (P20 (b)): pages are those sent up to the turn
    shown. [] where the plan kept none."""
    return extents.shown(record["plan"]["proposal"].get("transfers") or [], copy_figures.copies(pages))


def _side_by_side(record):
    """What research v13 found with the papers read side by side (plan AN.28, piece 3e), as the plan kept it: each point with the
    pages code found its words on, or marked as not found; whether the papers could be read together; and where each of the client's
    people stands on the pages, as code found the name, a near spelling a candidate only. Nothing where the plan kept none of it."""
    proposal = record["plan"]["proposal"]
    if "connections" not in proposal:
        return {}
    return {"connections": [{"id": item["id"], "kind": item["kind"], "point": item["point"], "why": item["why_it_matters"],
                             "anchored": item["anchored"], "places": item["places"]} for item in proposal["connections"]],
            "connections_failures": [{"reason": failure["reason"]} for failure in proposal.get("connections_failures", [])],
            "appearances": proposal.get("appearances", [])}


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
        sent = _sent(rows[:index + 1])
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
            # From research v13 (plan AN.28, piece 3f): whether a party is on the client's side and its part in each proceeding,
            # each part and each subject the papers identify where code finds its words.
            "parties": [{"who": p["who"], "role": p["role"], **({"client": p["client"]} if "client" in p else {}),
                         **({"parts": [{"proceeding": part["proceeding"], "part": part["part"],
                                        **_where(part["words"], rows[:index + 1], pages)} for part in p["parts"]]}
                            if p.get("parts") else {})}
                        for p in understanding["parties"]],
            "subjects": [{"identifier": s["identifier"], "what": s["what"], **_where(s["words"], rows[:index + 1], pages)}
                         for s in understanding.get("subjects", ())],
            "facts": [{"id": f["id"], "fact": f["fact"], "certainty": f["certainty"], "words": f["advocate_words"],
                       **_where(f["advocate_words"], rows[:index + 1], pages)}
                      for f in understanding["facts"]],
            # Each dispute with the facts it rests on (where it was picked up from), why each
            # question was asked, and, from research v9, why it matters (16 Oct 2026).
            "disputes": [_dispute(d, record, work, checklists) for d in _urgent(understanding["disputes"], checklists)],
            "understanding": _confirmed(record),
            "timeline": _timeline(record, rows[:index + 1], copy_figures.copies(sent)),
            "copies": _copies(sent),
            "extents": _extents(record, sent),
            **_side_by_side(record),
            "related_points": [{"point": r["point"], "why": r["why_it_matters"], "dispute_id": r["dispute_id"] or None,
                                "dispute": names.get(r["dispute_id"])} for r in understanding["related_points"]],
        }
    return {"state": "empty"}
