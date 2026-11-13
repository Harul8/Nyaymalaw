"""The case account gathered where it is written (plan AN.49, piece 49d; D181, D233, D234; owner, 12 Nov 2026, of the matter board:
"consolidate and bring logically connected aspects into one bullet").

Version 3 of the case step of nm/core_engine/case_strength.py, built beside it in a new module because that one is pinned (AN.48,
D143; D234). The same two calls - the account and its check - read the same material and give the account in one gathered shape:
the headings of the model's own choosing, as many as the dispute needs; each element as v2 gives it, with the number of its heading;
each thing to get from one person or place, with the numbers of every element it serves; each thing the other side will rely on as
v2 gives it, with the number of the heading it attacks (0 for none); and the few things that most decide the dispute as the papers
stand. Gathering and deciding are judgments of meaning, left to the model. Code checks only what is mechanical, made again exactly
on replay (P46):
- every check of v2, by case_strength.admit itself: the law's exact words in a held passage offered for the dispute, the points of
  the papers' list, "shown" only with a point found on its page;
- an element whose heading number names no heading with a name is put under code's own heading, 'Other things the law requires',
  and said so - never dropped; a heading no element sits under is not shown;
- an attack that names no heading shown stands as attacking none;
- an ask's numbers that name no element, or an element the papers already show, are taken off it; an ask left serving none is set
  aside, as v2 sets one aside;
- a deciding item's numbers that name nothing are taken off and its words kept; one with no words is not shown;
- nothing lost unremarked: the record keeps the first call's account, and code notes each element of it whose words are not among
  the elements of the account kept. Whether that note is shown, and how an element reworded is told from one taken out, is for the
  paid check (AN.49 point (b)) to measure first.
The view keeps each ask's 'for' (the first element it serves), so that what the pages draw today reads it as before, and adds
'serves' (every element it serves), each element's heading, each attack and what decides the dispute.

NOT WIRED IN (D234): no turn calls assess, and no saved case is read by validate_saved or shown_saved, until the owner approves the
exception in AN.48's register together with the paid check.
"""
from __future__ import annotations

import json
from copy import deepcopy

from nm.core_engine import case_strength, reasoning
from nm.shared.model_port import (ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data,
                                  estimate_tokens, require_schema)

#: v3 (plan AN.49, D181/D233): the account gathered under headings, asks by who can give them, attacks, what decides it.
CONTRACT = "core_case_v3"
#: The heading code puts an element under when the one it names has no name or is not in the list (D233).
OTHER = "Other things the law requires"
STRING = {"type": "string"}
NUMBER = {"type": "integer"}
NUMBERS = {"type": "array", "items": NUMBER}


def _object(fields):
    return {"type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}


_ELEMENT = case_strength.ELEMENT["properties"]
_OTHER_SIDE = case_strength.OTHER_SIDE["properties"]
#: v2's element and point of the other side, each with its number in the gathering; the asks and what decides it, new.
ELEMENT = _object({"element": _ELEMENT["element"], "label": _ELEMENT["label"], "heading": NUMBER,
                   **{key: value for key, value in _ELEMENT.items() if key not in ("element", "label")}})
TO_GET = _object({"what": STRING, "from_whom": STRING, "elements": NUMBERS, "why": STRING, "helps": STRING})
OTHER_SIDE = _object({"relies_on": _OTHER_SIDE["relies_on"], "label": _OTHER_SIDE["label"], "attacks": NUMBER,
                      **{key: value for key, value in _OTHER_SIDE.items() if key not in ("relies_on", "label")}})
DECIDES = _object({"what": STRING, "why": STRING, "elements": NUMBERS, "other_side": NUMBERS})
SCHEMA = _object({"headings": {"type": "array", "items": STRING}, "elements": {"type": "array", "items": ELEMENT},
                  "to_get": {"type": "array", "items": TO_GET}, "other_side": {"type": "array", "items": OTHER_SIDE},
                  "decides": {"type": "array", "items": DECIDES}})
EMPTY = {"headings": [], "elements": [], "to_get": [], "other_side": [], "decides": []}

CASE = """Message: You receive one dispute of an advocate's matter as our research has set it out: every point our reading of the papers set out, each with its ID, what it is, the papers' own words, the pages it stands on (or that its words were not found on a page) and how the weighing of the points weighed it; the advocate's own messages; the dispute, with its legal questions, the rights at stake, the relief sought and what is still missing; and the held law our research read for it - provisions of the Acts and paragraphs of judgments, each under its short ID (P1, J1 ...).

Purpose: Our client's case on this dispute is to be made as strong as the law and the facts allow. A lawyer preparing it asks what the law requires to be proven, which of it the papers already prove, which they prove only weakly, and which they do not prove at all - and so what must still be gathered from the client or elsewhere before the matter is argued, and what the other side will rely on. The advocate reads the account on the matter board at a glance and acts on it, so it is gathered as a lawyer would brief it: the requirements under a few headings that belong together for this dispute, each thing to get asked once of the person or place that can give it however many requirements it serves, each point of the other side set against what it attacks, and the few things that most decide the dispute as the papers stand.

Look for: each element the governing provisions and the judgments' tests require for the client to succeed, or that the other side must establish against the client - said in plain words, with the provision's or the judgment's own words that set it (its short ID and those exact words), and who must prove it. For each, how the papers stand: shown (name the points that show it), weak (shown only in part, contested by another paper, or resting on the advocate's word alone - say why), or missing. For each element weak or missing, what would prove it - the document, record, certified copy, statement or witness - from whom it can be had, why the law needs it and how it would help; where one document or one person would prove several elements, that is one thing to get, serving each of them. What the other side will rely on, with the law's words or the points they would cite where there are any, what it attacks and what would answer it. And which few things most decide this dispute as the papers stand.

Outcome: headings - the headings you gather the elements under, each named in a few words, as many as this dispute needs; elements - each with element, label (the element named in a few words, as the advocate's matter board lists it), heading (the number of its heading in your list, from 1), law (source_id and quote), proves (client or other_side), status (shown, weak or missing), points (the IDs of the points that show it or bear on it), why (a sentence or two); to_get - each thing to get from one person or place, with what, from_whom, elements (the numbers of every element in your list, from 1, that it would prove or help to prove), why and helps; other_side - each with relies_on, label (what they will rely on, in a few words), attacks (the number of the heading it attacks, or 0 where it attacks none), law (source_id and quote, or both empty where no held law is theirs), answer and points; decides - the few things that most decide this dispute as the papers stand, each with what (in a few words), why, elements (the numbers of the elements it concerns) and other_side (the numbers of the other side's points it concerns, from 1). Ask only for what the papers do not already show; leave out what the law does not require of this dispute.

Work in a loop: read the material, set out the elements and gather them, check each against the law's words and the points before you give it, correct what does not hold, then give the whole."""

CASE_CHECK = """Message: You receive the same material, and a colleague's account of what the law requires of this dispute, gathered under headings - how the papers stand on each element, what to gather and from whom, what the other side will rely on and what it attacks, and what most decides the dispute - with what code found it could not check: a law quotation not in the passage it names, a point that is not in the papers' list, an element called shown none of whose points was found on its page, an ask for an element the papers show or for no element, a number that names nothing in the account's own lists.

Purpose: The account goes to the advocate as the case's list of what to prove and what to gather, read on the matter board at a glance. Every element must be one the law requires, in its own words; every status must be what the papers actually show; nothing may be asked of the client that the papers already prove; each heading must hold what belongs together; and nothing the case needs may be missing from it - no element of your colleague's account is lost in the gathering unless the law does not require it.

Outcome: the account again, corrected - the same where it is right; each heading, element, ask, point of the other side and deciding item as it should stand, each name in a few words fitting what it names; any element or ask it lacks, added; and what code could not check put right where the material allows (the passage's own words, the points that are in the list, the numbers of the account's own lists).

Work in a loop: check each item against the law and the points, correct it, check again, then give the whole."""


def _plain(text):
    return " ".join(str(text or "").split())


def _words(text):
    return _plain(text).casefold()


def _call(model, operation, system, user, step):
    """One call of the step, as case_strength makes its own (the same steps of the one reasoning policy, the same cache prefix),
    in the gathered shape."""
    receipt = model.structured(Prompt(system=system, user=user, operation=operation,
                                      effort=reasoning.effort(step, tokens=estimate_tokens(user)),
                                      cache_through=case_strength.shared_through(user)), SCHEMA,
                               Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, system, user, json.dumps(SCHEMA)))
    if not receipt.usable or receipt.data is None:
        raise ModelError(f"The gathered case step {step} did not complete", usage=receipt.usage, latency_ms=receipt.latency_ms,
                         retries=receipt.retries)
    return canonical_schema_data(receipt.data, SCHEMA)


def admit(data, offered, points, sources):
    """The gathered account as the record keeps it, and what code said of it (notes: told to the check call, and kept).
    Deterministic in its inputs, so that replay re-derives it."""
    base = case_strength.admit({"elements": data["elements"], "to_get": [], "other_side": data["other_side"]}, offered, points,
                               sources, case_strength.CONTRACT)
    elements, other_side, notes = base["elements"], base["other_side"], list(base["notes"])
    named = [_plain(name) for name in data["headings"]]
    under = []
    for number, item in enumerate(data["elements"], 1):
        if 1 <= item["heading"] <= len(named) and named[item["heading"] - 1]:
            under.append(item["heading"])
        else:
            under.append(None)
            notes.append(f"Element {number} is under no named heading of the list: it is put under '{OTHER}'")
    kept = [number for number in range(1, len(named) + 1) if number in under]
    for number in range(1, len(named) + 1):
        if number not in under:
            notes.append(f"Heading {number} has no name: it is not shown" if not named[number - 1] else
                         f"Heading {number} ({named[number - 1]!r}) has no element under it: it is not shown")
    headings = [named[number - 1] for number in kept]
    renumber = {given: place for place, given in enumerate(kept, 1)}
    other = None
    if None in under:
        other = next((place for place, name in enumerate(headings, 1) if _words(name) == _words(OTHER)), None)
        if other is None:
            headings.append(OTHER)
            other = len(headings)
    for element, given in zip(elements, under):
        element["heading"] = renumber[given] if given is not None else other
    for number, (item, entry) in enumerate(zip(data["other_side"], other_side), 1):
        entry["attacks"] = renumber.get(item["attacks"], 0)
        if item["attacks"] and item["attacks"] not in renumber:
            notes.append(f"The other side's point {number} attacks heading {item['attacks']}, which is not a heading shown: it "
                         "stands as attacking none")
    to_get, set_aside = [], []
    for number, item in enumerate(data["to_get"], 1):
        given = list(dict.fromkeys(item["elements"]))
        serves = [element for element in given if 1 <= element <= len(elements) and elements[element - 1]["status"] != "shown"]
        entry = {"what": _plain(item["what"]), "from_whom": _plain(item["from_whom"]), "elements": serves,
                 "why": _plain(item["why"]), "helps": _plain(item["helps"])}
        if not serves:
            shown_ones = [element for element in given if 1 <= element <= len(elements)]
            set_aside.append({**entry, "elements": given,
                              "why_set_aside": ("The papers already show every element it is for" if shown_ones else
                                                "It names no element of the list")})
            notes.append(f"Ask {number} is set aside: {set_aside[-1]['why_set_aside']}")
            continue
        for element in given:
            if not 1 <= element <= len(elements):
                notes.append(f"Ask {number} names element {element}, which is not in the list: it is taken off the ask")
            elif element not in serves:
                notes.append(f"Ask {number} is for element {element}, which the papers already show: it is taken off the ask")
        to_get.append(entry)
    decides = []
    for number, item in enumerate(data["decides"], 1):
        what = _plain(item["what"])
        if not what:
            notes.append(f"Deciding item {number} has no words: it is not shown")
            continue
        on, against = list(dict.fromkeys(item["elements"])), list(dict.fromkeys(item["other_side"]))
        notes += [f"Deciding item {number} names element {element}, which is not in the list: it is taken off"
                  for element in on if not 1 <= element <= len(elements)]
        notes += [f"Deciding item {number} names the other side's point {point}, which is not in the list: it is taken off"
                  for point in against if not 1 <= point <= len(other_side)]
        decides.append({"what": what, "why": _plain(item["why"]),
                        "elements": [element for element in on if 1 <= element <= len(elements)],
                        "other_side": [point for point in against if 1 <= point <= len(other_side)]})
    return {"headings": headings, "elements": elements, "to_get": to_get, "other_side": other_side, "decides": decides,
            "set_aside": set_aside, "notes": notes}


def not_carried(first, kept):
    """Each element of the first call's account whose words are not among the elements of the account kept, by its number there
    (D181: nothing of the account lost unremarked between the first call and the gathered form). In the record only (D233)."""
    if first is None or kept is None:
        return []
    words = {_words(item["element"]) for item in kept["elements"]}
    return [{"number": number, "element": _plain(item["element"])} for number, item in enumerate(first["elements"], 1)
            if _words(item["element"]) not in words]


def _admitted(record, offered, points, sources):
    return {**record, **admit(record["proposal"] or EMPTY, offered, points, sources),
            "not_carried": not_carried(record["first"], record["proposal"])}


def assess(model, context, part, sources, dispute):
    """One dispute's gathered case: the account, checked by a second call shown what code could not check, admitted. As v2: a
    failed first call leaves the case unassessed, said so; a failed check keeps the first account, marked unchecked; a usage limit
    stops the turn."""
    user, offered, points = case_strength.material(context, part, sources, dispute)
    record = {"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": None, "first": None, "checked": "unchecked",
              "failures": []}
    try:
        first = _call(model, "core_case", CASE, user, "case")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        record["failures"].append({"step": "case", "reason": type(exc).__name__})
        return _admitted(record, offered, points, sources)
    record["first"] = first
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
    return _admitted(record, offered, points, sources)


def shown(record, context, part, sources):
    """A saved gathered case as the answer and the board would show it: v2's view of each element, ask and point of the other side,
    made by case_strength.shown itself (each ask read there as for the first element it serves, so that its 'for' is as today), with
    the headings, each element's heading, every element each ask serves, each attack and what decides the dispute. None where the
    dispute keeps no case."""
    if record is None:
        return None
    view = case_strength.shown({**record, "to_get": [{**ask, "element": ask["elements"][0]} for ask in record["to_get"]]},
                               context, part, sources)
    for entry, item in zip(view["elements"], record["elements"]):
        entry["heading"] = item["heading"]
    for entry, ask in zip(view["to_get"], record["to_get"]):
        entry["serves"] = [view["elements"][number - 1]["element"] for number in ask["elements"]]
    for entry, item in zip(view["other_side"], record["other_side"]):
        entry["attacks"] = item["attacks"]
    return {"state": view["state"], "headings": list(record["headings"]), "elements": view["elements"], "to_get": view["to_get"],
            "other_side": view["other_side"], "decides": deepcopy(record["decides"])}


def validate(record, context, part, sources, dispute):
    """A saved gathered case checked against its own answers and the research it was made from (P46): code's part re-derived
    exactly, and its first account consistent with how it was checked."""
    if not isinstance(record, dict) or record.get("contract") != CONTRACT or record.get("dispute_id") != dispute["id"]:
        raise ValueError("A saved case names no dispute of its research, or is of an unknown contract")
    _, offered, points = case_strength.material(context, part, sources, dispute)
    proposal, first = record.get("proposal"), record.get("first")
    try:
        for given in (proposal, first):
            if given is not None:
                require_schema(given, SCHEMA)
    except SchemaViolation as exc:
        raise ValueError("A saved case's answer is not of its contract's shape") from exc
    expected = _admitted({"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": proposal, "first": first,
                          "checked": record.get("checked"), "failures": record.get("failures")}, offered, points, sources)
    # As v2: checked, nothing failed; unchecked, the check failed (its first account kept as the account) or the first call did
    # (no account) - and the first account is there exactly where the first call answered.
    failures = record.get("failures")
    steps = [failure.get("step") if isinstance(failure, dict) and set(failure) == {"step", "reason"}
             and isinstance(failure["reason"], str) else None for failure in failures] if isinstance(failures, list) else None
    marked = (steps == [] and proposal is not None and first is not None if record.get("checked") == "checked" else
              (steps == ["case_check"] and first == proposal if proposal is not None else steps == ["case"] and first is None)
              if record.get("checked") == "unchecked" else False)
    if record != expected or not marked:
        raise ValueError("A saved case differs from what code makes of its own answer")
    return deepcopy(record)


def validate_saved(record, context, part, sources, dispute):
    """A saved case of any version, checked as its version checks it: v3 here; v1 and v2 by case_strength, exactly as before."""
    if isinstance(record, dict) and record.get("contract") == CONTRACT:
        return validate(record, context, part, sources, dispute)
    return case_strength.validate(record, context, part, sources, dispute)


def shown_saved(record, context, part, sources):
    """A saved case of any version, shown as its version shows it: v3 here; v1 and v2 by case_strength, exactly as before."""
    if isinstance(record, dict) and record.get("contract") == CONTRACT:
        return shown(record, context, part, sources)
    return case_strength.shown(record, context, part, sources)
