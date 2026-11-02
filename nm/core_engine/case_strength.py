"""What makes a dispute's case stronger (plan AN.35, D31-D32; piece 35c1; owner, 2 Nov 2026: "when we look at these and we retrieve
these passages both from the acts and judgments, it will tell us what will make the case stronger, and thereby we should try to get
those materials and evidences from the client accordingly").

One step per dispute, once its research is ready. Its call is shown the dispute, the held law its research read for it (the view
the writer has), every point read from the papers with its pages and its weight, and the advocate's messages; it sets out what the
law requires - each element a governing provision or a chosen judgment's test sets, in that law's own words, who must prove it,
and how the papers stand on it (shown, weak, missing) - what to get for each element weak or missing, and what the other side will
rely on and what answers it. A second call checks the account against the same material, shown what code could not check, and
gives it again corrected. Code checks only what is mechanical, and keeps the model's judgment otherwise:
- an element's law is a held passage offered for this dispute, in its exact words; one that is not is kept marked not found;
- the points named are points of the papers' list; one that is not is dropped from the item and said;
- an element is shown only where at least one of its points was found on its page; one that is not stands as weak, and why;
- nothing is asked for an element the papers show; such an ask, or one naming no element, is set aside and said.
The record keeps the model's own answer, and replay re-derives the rest from it exactly (P46).
"""
from __future__ import annotations

import json
from copy import deepcopy

from nm.core_engine import answer_sources, reasoning, research, response_writer
from nm.shared.citation_contracts import statute_title
from nm.shared.model_port import (ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data,
                                  estimate_tokens, require_schema)

CONTRACT = "core_case_v1"
STATUSES = ("shown", "weak", "missing")
PROVES = ("client", "other_side")
STRING = {"type": "string"}


def _object(fields):
    return {"type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}


LAW = _object({"source_id": STRING, "quote": STRING})
POINTS = {"type": "array", "items": STRING}
ELEMENT = _object({"element": STRING, "law": LAW, "proves": {"type": "string", "enum": list(PROVES)},
                   "status": {"type": "string", "enum": list(STATUSES)}, "points": POINTS, "why": STRING})
TO_GET = _object({"what": STRING, "from_whom": STRING, "element": {"type": "integer"}, "why": STRING, "helps": STRING})
OTHER_SIDE = _object({"relies_on": STRING, "law": LAW, "answer": STRING, "points": POINTS})
SCHEMA = _object({"elements": {"type": "array", "items": ELEMENT}, "to_get": {"type": "array", "items": TO_GET},
                  "other_side": {"type": "array", "items": OTHER_SIDE}})

CASE = """Message: You receive one dispute of an advocate's matter as our research has set it out: the dispute, with its legal questions, the rights at stake, the relief sought and what is still missing; the held law our research read for it - provisions of the Acts and paragraphs of judgments, each under its short ID (P1, J1 ...); every point our reading of the papers set out, each with its ID, what it is, the papers' own words, the pages it stands on (or that its words were not found on a page) and how the weighing of the points weighed it; and the advocate's own messages.

Purpose: Our client's case on this dispute is to be made as strong as the law and the facts allow. A lawyer preparing it asks what the law requires to be proven, which of it the papers already prove, which they prove only weakly, and which they do not prove at all - and so what must still be gathered from the client or elsewhere before the matter is argued, and what the other side will rely on.

Look for: each element the governing provisions and the judgments' tests require for the client to succeed, or that the other side must establish against the client - said in plain words, with the provision's or the judgment's own words that set it (its short ID and those exact words), and who must prove it. For each, how the papers stand: shown (name the points that show it), weak (shown only in part, contested by another paper, or resting on the advocate's word alone - say why), or missing. For each element weak or missing, what would prove it - the document, record, certified copy, statement or witness - from whom it can be had, why the law needs it and how it would help. And what the other side will rely on, with the law's words or the points they would cite where there are any, and what would answer it.

Outcome: elements - each with element, law (source_id and quote), proves (client or other_side), status (shown, weak or missing), points (the IDs of the points that show it or bear on it), why (a sentence or two); to_get - each with what, from_whom, element (the number of the element in your list, from 1), why and helps; other_side - each with relies_on, law (source_id and quote, or both empty where no held law is theirs), answer and points. Ask only for what the papers do not already show; leave out what the law does not require of this dispute.

Work in a loop: read the material, set out the elements, check each against the law's words and the points before you give it, correct what does not hold, then give the whole."""

CASE_CHECK = """Message: You receive the same material, and a colleague's account of what the law requires of this dispute, how the papers stand on each element, what to gather and what the other side will rely on - with what code found it could not check: a law quotation not in the passage it names, a point that is not in the papers' list, an element called shown none of whose points was found on its page, an ask for an element the papers show or for no element.

Purpose: The account goes to the advocate as the case's list of what to prove and what to gather. Every element must be one the law requires, in its own words; every status must be what the papers actually show; nothing may be asked of the client that the papers already prove; and nothing the case needs may be missing from it.

Outcome: the account again, corrected - the same where it is right; each element, ask and point of the other side as it should stand; any element or ask it lacks, added; and what code could not check put right where the material allows (the passage's own words, the points that are in the list).

Work in a loop: check each item against the law and the points, correct it, check again, then give the whole."""


def _plain(text):
    return " ".join(str(text or "").split())


def material(context, part, sources, dispute):
    """What the step reads for one dispute, and what code checks its answer against: (user text, the held law offered by short ID ->
    source tag, the points by ID -> whether found on a page)."""
    offered = {tag: alias for alias, tag in answer_sources.aliases(sources).items()}
    groups = research.dispute_work(part["plan"])
    work_ids = [work["id"] for work in groups.get(dispute["id"], [])]
    shown = answer_sources.presentation(sources, aliased=True, compact=True, work_ids=work_ids)["passages"]
    law = {passage["id"]: answer_sources.aliases(sources)[passage["id"]] for passage in shown
           if passage["id"] in answer_sources.aliases(sources)}
    points = response_writer.coverage_items(part, offered, context)
    said = [row["text"] for row in context.get("conversation", ()) if row.get("record_role") == "original_account"]
    latest = (context.get("latest") or {}).get("text")
    payload = {"dispute": {key: deepcopy(dispute.get(key)) for key in ("id", "name", "between", "legal_questions", "rights_at_stake",
                                                                     "relief_sought", "missing_facts")},
               "held_law": shown, "points": points, "advocate_messages": [*said, *([latest] if latest else [])]}
    return json.dumps(payload, ensure_ascii=False), law, {point["id"]: point.get("located", True) for point in points}


def _call(model, operation, system, user, step):
    receipt = model.structured(Prompt(system=system, user=user, operation=operation,
                                      effort=reasoning.effort(step, tokens=estimate_tokens(user))), SCHEMA,
                               Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, system, user, json.dumps(SCHEMA)))
    if not receipt.usable or receipt.data is None:
        raise ModelError(f"The case step {step} did not complete", usage=receipt.usage, latency_ms=receipt.latency_ms,
                         retries=receipt.retries)
    return canonical_schema_data(receipt.data, SCHEMA)


def _law(law, offered, sources):
    """An item's law as code finds it: (the law as given, whether its words are exactly in the held passage it names)."""
    given = {"source_id": _plain(law["source_id"]), "quote": law["quote"].strip()}
    if not given["source_id"] and not given["quote"]:
        return given, None
    tag = offered.get(given["source_id"])
    if tag is None or not given["quote"]:
        return given, False
    try:
        answer_sources.select({"source_id": tag, "quote": given["quote"]}, sources, loose=True)
        return given, True
    except (SchemaViolation, ValueError):
        return given, False


def admit(data, offered, points, sources):
    """The account as the record keeps it, and what code said of it (problems, for the check call; notes, kept). Deterministic in
    its inputs, so that replay re-derives it."""
    notes, elements, to_get, other_side, set_aside = [], [], [], [], []
    for number, item in enumerate(data["elements"], 1):
        law, found = _law(item["law"], offered, sources)
        known = [point for point in dict.fromkeys(item["points"]) if point in points]
        for point in dict.fromkeys(item["points"]):
            if point not in points:
                notes.append(f"Element {number} names {point!r}, which is not a point of the papers' list")
        status = item["status"]
        if status == "shown" and not any(points[point] for point in known):
            status = "weak"
            notes.append(f"Element {number} is called shown, but none of its points was found on its page: it stands as weak")
        if found is False or found is None:
            notes.append(f"Element {number}'s law is not words of a held passage offered for this dispute")
        elements.append({"element": _plain(item["element"]), "law": law, "law_found": bool(found), "proves": item["proves"],
                         "status": status, "given_status": item["status"], "points": known, "why": _plain(item["why"])})
    for item in data["to_get"]:
        index = item["element"]
        entry = {"what": _plain(item["what"]), "from_whom": _plain(item["from_whom"]), "element": index, "why": _plain(item["why"]),
                 "helps": _plain(item["helps"])}
        if not 1 <= index <= len(elements):
            set_aside.append({**entry, "why_set_aside": "It names no element of the list"})
        elif elements[index - 1]["status"] == "shown":
            set_aside.append({**entry, "why_set_aside": "The papers already show the element it is for"})
        else:
            to_get.append(entry)
    notes += [f"An ask set aside: {entry['why_set_aside']}" for entry in set_aside]
    for item in data["other_side"]:
        law, found = _law(item["law"], offered, sources)
        other_side.append({"relies_on": _plain(item["relies_on"]), "law": law, "law_found": found is True,
                           "answer": _plain(item["answer"]), "points": [p for p in dict.fromkeys(item["points"]) if p in points]})
    return {"elements": elements, "to_get": to_get, "other_side": other_side, "set_aside": set_aside, "notes": notes}


def assess(model, context, part, sources, dispute):
    """One dispute's case (piece 35c1): the account, checked by a second call shown what code could not check, admitted. A failed
    first call leaves the dispute's case unassessed, said so; a failed check keeps the first account, marked unchecked; a usage
    limit stops the turn."""
    user, offered, points = material(context, part, sources, dispute)
    record = {"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": None, "checked": "unchecked", "failures": []}
    try:
        first = _call(model, "core_case", CASE, user, "case")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        record["failures"].append({"step": "case", "reason": type(exc).__name__})
        return {**record, **admit({"elements": [], "to_get": [], "other_side": []}, offered, points, sources)}
    told = admit(first, offered, points, sources)["notes"]
    try:
        checked = _call(model, "core_case_check", CASE_CHECK, user + "\n\nYour colleague's account:\n" + json.dumps(first, ensure_ascii=False)
                        + "\n\nWhat code could not check:\n" + (json.dumps(told, ensure_ascii=False) if told else "nothing"), "case_check")
        record.update(proposal=checked, checked="checked")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        record.update(proposal=first)
        record["failures"].append({"step": "case_check", "reason": type(exc).__name__})
    return {**record, **admit(record["proposal"], offered, points, sources)}


#: How a case stands, as the answer and the board say it (piece 35c3): set out and checked by the second call; set out, its check not
#: made; not set out, the first call having failed.
SHOWN_STATES = ("checked", "unchecked", "unavailable")


def shown(record, context, part, sources):
    """A dispute's saved case as the answer and the board show it (plan AN.35, D32; piece 35c3): each element in plain words, who must
    prove it, how the papers stand on it and why (and what it was called where code would not let it stand as shown), its law's own
    words with the passage they stand in - or that code could not find them in one - and the pages of its points; what to get, from
    whom, why and how it helps, under the element it is for; and what the other side will rely on and what answers it. Every word is
    the model's or the passage's; every title, page and mark is code's. None where the dispute keeps no case."""
    if record is None:
        return None
    aliased = answer_sources.aliases(sources)
    offered = {tag: alias for alias, tag in aliased.items()}
    points = {point["id"]: point for point in response_writer.coverage_items(part, offered, context)}

    def law(given, found):
        if not given["source_id"] and not given["quote"]:
            return None
        if not found:
            return {"found": False, "words": given["quote"]}
        tag = aliased[given["source_id"]]
        source = sources[tag]
        title = (statute_title(source["title"], source["source_identity"].get("act_id", ""))
                 if source["kind"] == "provision" else source["title"])
        return {"found": True, "kind": source["kind"], "title": title, "locator": source["locator"], "words": given["quote"],
                "source_id": tag, **({"in_force": source["in_force"]} if "in_force" in source else {})}

    def where(ids):
        said = []
        for identity in ids:
            point = points[identity]
            pages = [{"document": sources[aliased[cite]]["title"], "page": sources[aliased[cite]]["locator"],
                      "source_id": aliased[cite]}
                     for cite in point.get("cite") or () if cite in aliased and sources[aliased[cite]]["kind"] == "document"]
            said.append({"what": point["what"], "located": point.get("located", True), "pages": pages})
        return said
    elements = [{"element": item["element"], "proves": item["proves"], "status": item["status"], "why": item["why"],
                 **({"called": item["given_status"]} if item["given_status"] != item["status"] else {}),
                 "law": law(item["law"], item["law_found"]), "points": where(item["points"])} for item in record["elements"]]
    return {"state": "unavailable" if record["proposal"] is None else record["checked"], "elements": elements,
            "to_get": [{"what": ask["what"], "from_whom": ask["from_whom"], "why": ask["why"], "helps": ask["helps"],
                        "for": elements[ask["element"] - 1]["element"]} for ask in record["to_get"]],
            "other_side": [{"relies_on": item["relies_on"], "answer": item["answer"], "law": law(item["law"], item["law_found"]),
                            "points": where(item["points"])} for item in record["other_side"]]}


def validate(record, context, part, sources, dispute):
    """A saved case checked against its own answer and the research it was made from (P46): code's part re-derived exactly."""
    if not isinstance(record, dict) or record.get("contract") != CONTRACT or record.get("dispute_id") != dispute["id"]:
        raise ValueError("A saved case names no dispute of its research, or is of an unknown contract")
    _, offered, points = material(context, part, sources, dispute)
    proposal = record.get("proposal") or {"elements": [], "to_get": [], "other_side": []}
    try:
        require_schema(proposal, SCHEMA)
    except SchemaViolation as exc:
        raise ValueError("A saved case's answer is not of its contract's shape") from exc
    expected = {"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": record.get("proposal"),
                "checked": record.get("checked"), "failures": record.get("failures"), **admit(proposal, offered, points, sources)}
    # Whether it was checked agrees with what failed: checked, nothing failed; unchecked, the check failed (its first account kept)
    # or the first call did (no account).
    failures = record.get("failures")
    steps = [failure.get("step") if isinstance(failure, dict) and set(failure) == {"step", "reason"}
             and isinstance(failure["reason"], str) else None for failure in failures] if isinstance(failures, list) else None
    marked = (steps == [] and record.get("proposal") is not None if record.get("checked") == "checked" else
              steps == (["case_check"] if record.get("proposal") is not None else ["case"])
              if record.get("checked") == "unchecked" else False)
    if record != expected or not marked:
        raise ValueError("A saved case differs from what code makes of its own answer")
    return deepcopy(record)
