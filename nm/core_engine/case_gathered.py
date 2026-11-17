"""The case account gathered where it is written (plan AN.49, piece 49d; D181, D233, D234; owner, 12 Nov 2026, of the matter board:
"consolidate and bring logically connected aspects into one bullet").

Version 3 of the case step of nm/core_engine/case_strength.py, built beside it in a new module because that one is pinned (AN.48,
D143; D234). The same two calls - the account and its check - read the same material and give the account in one gathered shape:
the headings of the model's own choosing, as many as the dispute needs; each element as v2 gives it, with the number of its heading;
each thing to get from one person or place, with the numbers of every element it serves; each thing the other side will rely on as
v2 gives it, with the numbers of the elements it attacks (D285: the paid check found the check call naming elements where D233
asked for a heading; code reads the heading from the element); and the few things that most decide the dispute as the papers
stand. Gathering and deciding are judgments of meaning, left to the model. Code checks only what is mechanical, made again exactly
on replay (P46):
- every check of v2, by case_strength.admit itself: the points of the papers' list, "shown" only with a point found on its page;
  and v2's own law check, case_strength._law, for each passage of an item's law (D293);
- an element whose heading number names no heading with a name is put under code's own heading, 'Other things the law requires',
  and said so - never dropped; a heading no element sits under is not shown;
- a number of what a point of the other side attacks that names no element is taken off; the point's heading is that of the first
  element it attacks, 0 where it attacks none;
- an ask's numbers that name no element, or an element the papers already show, are taken off it; an ask left serving none is set
  aside, as v2 sets one aside;
- a deciding item's numbers that name nothing are taken off and its words kept; one with no words is not shown;
- nothing lost unremarked (D286): the record keeps the first call's account; the check call says of each element it gives which
  element of that account it is (its number there, 0 where the check added it), and code names each element of the first account
  that the checked one no longer holds. The paid check (AN.49 point (b), 17 Nov 2026) measured that words cannot say this: the
  check rewords every element. Whether the note is shown is the owner's.
The view keeps each ask's 'for' (the first element it serves), so that what the pages draw today reads it as before, and adds
'serves' (every element it serves), each element's heading, each point's attack (the heading, as before, and 'against': the
elements it attacks, by their words) and what decides the dispute.

WIRED IN 17 Nov 2026 (D291; AN.48's register item 15, approved by the owner's word with the paid check's result): every new
answer's case step calls assess here, and every saved case is checked by validate_saved and shown by shown_saved - a case saved
before as v1 or v2 by case_strength, exactly as before (P46).

THE INDEPENDENT REVIEW OF THE ACCOUNT (plan AN.51, D290; 17 Nov 2026, before any answer was saved under v3 - D291 was not yet
applied - so v3 is the account with its review): after the two calls, one call on the review tier (the turn's own model, D294) reads the
account against the same material and names each item it finds wrong, with why. Nothing is rewritten after it, so nothing needs
reviewing again. Code leaves out of what is shown each requirement whose law's words are not in a held passage offered for the
dispute (they are not shown to the review), each item the review names, and each thing to get left serving only what was left out;
the record keeps them all, and the line on the account and the research note say what was left out and why (D185). Mechanical
only: a number the review gives that names nothing it was shown is not taken, said so. The review is not made where nothing is
left to show it. A failed review leaves the account as checked, said so; 'checked' is the view's state only where the second look
and the review were both made (F-03). A usage limit stops the turn, as at every step.

SEVERAL PASSAGES OF LAW FOR ONE REQUIREMENT (plan AN.49, D293; the owner's "D293 - Ok", 17 Nov 2026, before any answer was saved
under v3 - so v3 takes it). The bounded live run of that evening found 7 of 13 requirements set by several provisions or judgments
read together, each named in v3's one law field ('P1; P2', each passage's words after its ID): code could not place them, and D290
left all seven out although six were quoted word for word. Each requirement, and each point of the other side, now gives its law
as a list of passages, each with its own exact words (none where no held law is theirs). Code looks for each quotation in its own
passage, as v2 looks for the one; the record keeps each with whether it was found, and a note for each not found. A requirement is
left out by law only where none of its quotations is found; it is shown with the quotations found, and those not found are shown
as not found, as v2 shows its one. The view gives each item's law as a list, each entry as v2's view gives the one; the board and
the note show each as they show the one (the owner's yes under D60, for this only).
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
#: D293: an item's law - each passage it rests on, with its own exact words.
LAWS = {"type": "array", "items": case_strength.LAW}
#: v2's element and point of the other side, each with its number in the gathering and its law as a list (D293); the asks and what
#: decides it, new.
ELEMENT = _object({"element": _ELEMENT["element"], "label": _ELEMENT["label"], "heading": NUMBER,
                   **{key: value for key, value in _ELEMENT.items() if key not in ("element", "label", "law")}, "law": LAWS})
TO_GET = _object({"what": STRING, "from_whom": STRING, "elements": NUMBERS, "why": STRING, "helps": STRING})
OTHER_SIDE = _object({"relies_on": _OTHER_SIDE["relies_on"], "label": _OTHER_SIDE["label"], "attacks": NUMBERS,
                      **{key: value for key, value in _OTHER_SIDE.items() if key not in ("relies_on", "label", "law")},
                      "law": LAWS})
#: What v2's own checks are given in place of an item's law, which v3 checks passage by passage (D293).
NO_LAW = {"source_id": "", "quote": ""}
DECIDES = _object({"what": STRING, "why": STRING, "elements": NUMBERS, "other_side": NUMBERS})
SCHEMA = _object({"headings": {"type": "array", "items": STRING}, "elements": {"type": "array", "items": ELEMENT},
                  "to_get": {"type": "array", "items": TO_GET}, "other_side": {"type": "array", "items": OTHER_SIDE},
                  "decides": {"type": "array", "items": DECIDES}})
EMPTY = {"headings": [], "elements": [], "to_get": [], "other_side": [], "decides": []}
#: What the check call gives (D286): the same account, each element with the number it has in the first call's account ("was"),
#: 0 where the check added it.
ELEMENT_CHECKED = _object({**ELEMENT["properties"], "was": NUMBER})
SCHEMA_CHECKED = _object({**SCHEMA["properties"], "elements": {"type": "array", "items": ELEMENT_CHECKED}})
#: The items of an account, as the review names them (D290), and the list of the record each is in.
ITEMS = {"element": "elements", "to_get": "to_get", "other_side": "other_side", "decides": "decides"}
REVIEW_FAULT = _object({"item": {"type": "string", "enum": list(ITEMS)}, "number": NUMBER, "why": STRING})
REVIEW_SCHEMA = _object({"faults": {"type": "array", "items": REVIEW_FAULT}})
#: Why an item is left out (D290): the review found it wrong; its law's words are not in a held passage; a thing to get was only
#: for what was left out.
BY = ("review", "law", "with")

CASE = """Message: You receive one dispute of an advocate's matter as our research has set it out: every point our reading of the papers set out, each with its ID, what it is, the papers' own words, the pages it stands on (or that its words were not found on a page) and how the weighing of the points weighed it; the advocate's own messages; the dispute, with its legal questions, the rights at stake, the relief sought and what is still missing; and the held law our research read for it - provisions of the Acts and paragraphs of judgments, each under its short ID (P1, J1 ...).

Purpose: Our client's case on this dispute is to be made as strong as the law and the facts allow. A lawyer preparing it asks what the law requires to be proven, which of it the papers already prove, which they prove only weakly, and which they do not prove at all - and so what must still be gathered from the client or elsewhere before the matter is argued, and what the other side will rely on. The advocate reads the account on the matter board at a glance and acts on it, so it is gathered as a lawyer would brief it: the requirements under a few headings that belong together for this dispute, each thing to get asked once of the person or place that can give it however many requirements it serves, each point of the other side set against what it attacks, and the few things that most decide the dispute as the papers stand.

Look for: each element the governing provisions and the judgments' tests require for the client to succeed, or that the other side must establish against the client - said in plain words, with the provisions' or the judgments' own words that set it (each passage's short ID and its exact words - one passage or several, as the law sets it), and who must prove it. For each, how the papers stand: shown (name the points that show it), weak (shown only in part, contested by another paper, or resting on the advocate's word alone - say why), or missing. For each element weak or missing, what would prove it - the document, record, certified copy, statement or witness - from whom it can be had, why the law needs it and how it would help; where one document or one person would prove several elements, that is one thing to get, serving each of them. What the other side will rely on, with the law's words or the points they would cite where there are any, what it attacks and what would answer it. And which few things most decide this dispute as the papers stand.

Outcome: headings - the headings you gather the elements under, each named in a few words, as many as this dispute needs; elements - each with element, label (the element named in a few words, as the advocate's matter board lists it), heading (the number of its heading in your list, from 1), law (each passage that sets it, with its source_id and quote - the exact words of that passage alone), proves (client or other_side), status (shown, weak or missing), points (the IDs of the points that show it or bear on it), why (a sentence or two); to_get - each thing to get from one person or place, with what, from_whom, elements (the numbers of every element in your list, from 1, that it would prove or help to prove), why and helps; other_side - each with relies_on, label (what they will rely on, in a few words), attacks (the numbers of the elements in your list, from 1, that it attacks; none where it attacks none), law (each passage they would rely on, with its source_id and quote - that passage's exact words; none where no held law is theirs), answer and points; decides - the few things that most decide this dispute as the papers stand, each with what (in a few words), why, elements (the numbers of the elements it concerns) and other_side (the numbers of the other side's points it concerns, from 1). Ask only for what the papers do not already show; leave out what the law does not require of this dispute.

Work in a loop: read the material, set out the elements and gather them, check each against the law's words and the points before you give it, correct what does not hold, then give the whole."""

CASE_CHECK = """Message: You receive the same material, and a colleague's account of what the law requires of this dispute, gathered under headings - how the papers stand on each element, what to gather and from whom, what the other side will rely on and what it attacks, and what most decides the dispute - with what code found it could not check: a law quotation not in the passage it names, a point that is not in the papers' list, an element called shown none of whose points was found on its page, an ask for an element the papers show or for no element, a number that names nothing in the account's own lists.

Purpose: The account goes to the advocate as the case's list of what to prove and what to gather, read on the matter board at a glance. Every element must be one the law requires, in its own words; every status must be what the papers actually show; nothing may be asked of the client that the papers already prove; each heading must hold what belongs together; and nothing the case needs may be missing from it - no element of your colleague's account is lost in the gathering unless the law does not require it.

Outcome: the account again, corrected - the same where it is right; each heading, element, ask, point of the other side and deciding item as it should stand, each name in a few words fitting what it names; any element or ask it lacks, added; and what code could not check put right where the material allows (the passage's own words, the points that are in the list, the numbers of the account's own lists). With each element give was: the number that element has in your colleague's account where yours is that element kept or corrected, and 0 where you added it - so that an element of your colleague's that your account no longer holds is known to have been taken out, and is not lost unremarked. Every other number you give - the elements an ask serves, those a point of the other side attacks, those a deciding item concerns - is of your own corrected lists.

Work in a loop: check each item against the law and the points, correct it, check again, then give the whole."""

CASE_REVIEW = """Message: You receive one dispute of an advocate's matter as our research has set it out - every point our reading of the papers set out, each with its ID, what it is, the papers' own words, the pages it stands on and how it was weighed; the advocate's own messages; the dispute itself; and the held law our research read for it, each passage under its short ID (P1, J1 ...) - and, after it, the account of the case NM has prepared from that material for the advocate: what the law requires, each requirement under its heading with how the papers stand on it, what to get and from whom, what the other side will rely on, and what most decides the dispute. Each item carries its number.

Purpose: You are the independent review of this account before the advocate acts on it. The advocate will gather evidence, ask the client for papers and prepare argument from it, so an item that is wrong misleads them: a requirement the law it quotes does not set, or sets differently; a burden put on the wrong side; a status the papers do not bear out - called shown when the points it names do not show it, or missing when the papers show it; an ask for what the papers already show, or for something that would not prove what it is for; a point of the other side, or a thing said to decide the dispute, that misstates the papers, the law or the matter. An item that is right stands, even where it could be put better.

Outcome: faults - each item you find wrong, with item (element, to_get, other_side or decides), number (its number in the account) and why (a sentence or two the advocate can read, saying what is wrong by the papers or the law). None where nothing is wrong. NM leaves out each item you name, tells the advocate so with your reason, and changes nothing else.

Work in a loop: read the material, check each item of the account against the law's words and the points it rests on, check your findings against the material again, keep only those you can stand behind, then give them."""


def _plain(text):
    return " ".join(str(text or "").split())


def _words(text):
    return _plain(text).casefold()


def _call(model, operation, system, user, step, schema=SCHEMA, tier=Tier.ROUTINE):
    """One call of the step, as case_strength makes its own (the same steps of the one reasoning policy, the same cache prefix),
    in the gathered shape; the review on the review tier (D290)."""
    receipt = model.structured(Prompt(system=system, user=user, operation=operation,
                                      effort=reasoning.effort(step, tokens=estimate_tokens(user)),
                                      cache_through=case_strength.shared_through(user)), schema,
                               tier, max_tokens=reasoning.room(model, tier, system, user, json.dumps(schema)))
    if not receipt.usable or receipt.data is None:
        raise ModelError(f"The gathered case step {step} did not complete", usage=receipt.usage, latency_ms=receipt.latency_ms,
                         retries=receipt.retries)
    return canonical_schema_data(receipt.data, schema)


def admit(data, offered, points, sources):
    """The gathered account as the record keeps it, and what code said of it (notes: told to the check call, and kept).
    Deterministic in its inputs, so that replay re-derives it."""
    # v2's checks of the points and the status, by case_strength.admit itself; each item's law checked here, passage by passage
    # (D293) - so v2's note on the law it was not given is not kept.
    base = case_strength.admit({"elements": [{**item, "law": NO_LAW} for item in data["elements"]], "to_get": [],
                                "other_side": [{**item, "law": NO_LAW} for item in data["other_side"]]}, offered, points, sources,
                               case_strength.CONTRACT)
    unasked = {f"Element {number}'s law is not words of a held passage offered for this dispute"
               for number in range(1, len(data["elements"]) + 1)}
    elements, other_side = base["elements"], base["other_side"]
    notes = [note for note in base["notes"] if note not in unasked]
    for number, (item, entry) in enumerate(zip(data["elements"], elements), 1):
        entry["law"], entry["law_found"] = _laws(item["law"], offered, sources)
        if not entry["law"]:
            notes.append(f"Element {number} names no law")
        notes += [f"Element {number}'s law {index} ({given['source_id'] or 'naming no passage'}) is not words of that held passage "
                  "offered for this dispute" for index, (given, found) in enumerate(zip(entry["law"], entry["law_found"]), 1)
                  if not found]
    for item, entry in zip(data["other_side"], other_side):
        entry["law"], entry["law_found"] = _laws(item["law"], offered, sources)
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
        # D285: the elements the point attacks, by their numbers; its heading is the first of them's.
        given = list(dict.fromkeys(item["attacks"]))
        entry["against"] = [element for element in given if 1 <= element <= len(elements)]
        entry["attacks"] = elements[entry["against"][0] - 1]["heading"] if entry["against"] else 0
        notes += [f"The other side's point {number} names element {element}, which is not in the list: it is taken off what "
                  "the point attacks" for element in given if not 1 <= element <= len(elements)]
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


def _laws(given, offered, sources):
    """An item's law as code finds it (D293): each passage as given, and whether its words are exactly in the held passage it names
    - v2's own check (case_strength._law), passage by passage."""
    checked = [case_strength._law(law, offered, sources, case_strength.CONTRACT) for law in given]
    return [law for law, _ in checked], [found is True for _, found in checked]


def not_carried(first, kept, checked=True):
    """Each element of the first call's account that the checked account no longer holds, by its number there (D181: nothing of the
    account lost unremarked between the first call and the gathered form; D286: known by the number the check call gives each of
    its elements, since it rewords them). None where the account kept is the first call's own (checked: whether the check call gave
    it). In the record only (D233)."""
    if first is None or kept is None or not checked:
        return []
    held = {item.get("was") for item in kept["elements"]}
    return [{"number": number, "element": _plain(item["element"])} for number, item in enumerate(first["elements"], 1)
            if number not in held]


def _kept(account, out):
    """The admitted account without the items out ({(item, number)}), each item kept with its number in the account ('number'), and
    the numbers of the things to get that go with what is out (D290): a thing to get keeps the requirements kept that it serves and
    goes where it serves none of them; a point of the other side and a deciding item keep their words, losing the numbers of what is
    out (a point's heading is that of the first requirement kept that it attacks, 0 where none)."""
    elements = {number: {**item, "number": number} for number, item in enumerate(account["elements"], 1)
                if ("element", number) not in out}
    other_side = {number: {**item, "number": number, "against": [element for element in item["against"] if element in elements]}
                  for number, item in enumerate(account["other_side"], 1) if ("other_side", number) not in out}
    for item in other_side.values():
        item["attacks"] = elements[item["against"][0]]["heading"] if item["against"] else 0
    to_get, went = [], []
    for number, ask in enumerate(account["to_get"], 1):
        if ("to_get", number) in out:
            continue
        serves = [element for element in ask["elements"] if element in elements]
        if serves:
            to_get.append({**ask, "number": number, "elements": serves})
        else:
            went.append(number)
    decides = [{**item, "number": number, "elements": [element for element in item["elements"] if element in elements],
                "other_side": [point for point in item["other_side"] if point in other_side]}
               for number, item in enumerate(account["decides"], 1) if ("decides", number) not in out]
    return {"headings": list(account["headings"]), "elements": list(elements.values()), "to_get": to_get,
            "other_side": list(other_side.values()), "decides": decides}, went


def _law_out(account):
    """The requirements none of whose law's quotations is in the held passage it names, offered for the dispute (D290; D293)."""
    return {("element", number) for number, item in enumerate(account["elements"], 1) if not any(item["law_found"])}


def for_review(account):
    """The account as the review is shown it (D290): what would be shown of it but for the review, each item with its number in the
    account, each requirement with its heading's name."""
    kept, _ = _kept(account, _law_out(account))
    return {"elements": [{"number": item["number"], "heading": kept["headings"][item["heading"] - 1], "element": item["element"],
                          "label": item["label"], "law": item["law"], "proves": item["proves"], "status": item["status"],
                          "points": item["points"], "why": item["why"]} for item in kept["elements"]],
            "to_get": [{"number": ask["number"], "what": ask["what"], "from_whom": ask["from_whom"], "for": ask["elements"],
                        "why": ask["why"], "helps": ask["helps"]} for ask in kept["to_get"]],
            "other_side": [{"number": item["number"], "relies_on": item["relies_on"], "label": item["label"],
                            "attacks": item["against"], "law": item["law"], "answer": item["answer"], "points": item["points"]}
                           for item in kept["other_side"]],
            "decides": [{"number": item["number"], "what": item["what"], "why": item["why"], "elements": item["elements"],
                         "other_side": item["other_side"]} for item in kept["decides"]]}


def left_out(account, review):
    """What the account leaves out of what is shown (D290), in the account's order, and what code said of the review: each
    requirement whose law was not found; each item the review names among those it was shown, with its reason (the first, where it
    names one twice); each thing to get left serving only what was left out. Deterministic in its inputs, so that replay re-derives
    it."""
    law, shown_to = _law_out(account), for_review(account)
    offered = {(kind, item["number"]) for kind, key in ITEMS.items() for item in shown_to[key]}
    faults, notes = {}, []
    for fault in (review or {}).get("faults") or ():
        named = (fault["item"], fault["number"])
        if named not in offered:
            notes.append(f"The review names {fault['item']} {fault['number']}, which it was not shown: nothing is left out for it")
        elif named not in faults:
            faults[named] = _plain(fault["why"])
    _, went = _kept(account, law | set(faults))
    left = []
    for kind, key in ITEMS.items():
        for number in range(1, len(account[key]) + 1):
            if (kind, number) in law:
                left.append({"item": kind, "number": number, "by": "law", "why": ""})
            elif (kind, number) in faults:
                left.append({"item": kind, "number": number, "by": "review", "why": faults[(kind, number)]})
            elif kind == "to_get" and number in went:
                left.append({"item": kind, "number": number, "by": "with", "why": ""})
    return left, notes


def _admitted(record, offered, points, sources):
    account = admit(record["proposal"] or EMPTY, offered, points, sources)
    left, said = left_out(account, record["review"])
    return {**record, **account, "notes": account["notes"] + said, "left_out": left,
            "not_carried": not_carried(record["first"], record["proposal"], record["checked"] == "checked")}


def assess(model, context, part, sources, dispute):
    """One dispute's gathered case: the account, checked by a second call shown what code could not check, then read by the
    independent review (D290), admitted. As v2: a failed first call leaves the case unassessed, said so; a failed check keeps the
    first account, marked unchecked; a failed review leaves out only what code finds, said so; a usage limit stops the turn."""
    user, offered, points = case_strength.material(context, part, sources, dispute)
    record = {"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": None, "first": None, "checked": "unchecked",
              "failures": [], "review": None}
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
                        + "\n\nWhat code could not check:\n" + (json.dumps(told, ensure_ascii=False) if told else "nothing"), "case_check",
                        SCHEMA_CHECKED)
        record.update(proposal=checked, checked="checked")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        record.update(proposal=first)
        record["failures"].append({"step": "case_check", "reason": type(exc).__name__})
    shown_to = for_review(admit(record["proposal"], offered, points, sources))
    if any(shown_to.values()):
        try:
            record["review"] = _call(model, "core_case_review", CASE_REVIEW,
                                     user + "\n\nThe account NM has prepared:\n" + json.dumps(shown_to, ensure_ascii=False),
                                     "case_review", REVIEW_SCHEMA, Tier.JUDGE)
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation) as exc:
            record["failures"].append({"step": "case_review", "reason": type(exc).__name__})
    return _admitted(record, offered, points, sources)


def shown(record, context, part, sources):
    """A saved gathered case as the answer and the board would show it: v2's view of each element, ask and point of the other side,
    made by case_strength.shown itself (each ask read there as for the first element it serves, so that its 'for' is as today), with
    the headings, each element's heading, every element each ask serves, each attack and what decides the dispute. None where the
    dispute keeps no case. D290: without what it leaves out, each number of what is shown counted in what is shown; with what was
    left out and why (left_out: each item's words, why it went, and the review's reason), the state - 'checked' only where the
    second look and the review were both made - and code's line on how the account was checked (said)."""
    if record is None:
        return None
    kept, _ = _kept(record, {(entry["item"], entry["number"]) for entry in record["left_out"] if entry["by"] != "with"})
    place = {item["number"]: index for index, item in enumerate(kept["elements"], 1)}
    theirs = {item["number"]: index for index, item in enumerate(kept["other_side"], 1)}
    elements = [{key: value for key, value in item.items() if key != "number"} for item in kept["elements"]]
    asks = [{**ask, "elements": [place[number] for number in ask["elements"]]} for ask in kept["to_get"]]
    other_side = [{**item, "against": [place[number] for number in item["against"]]} for item in kept["other_side"]]
    decides = [{"what": item["what"], "why": item["why"], "elements": [place[number] for number in item["elements"]],
                "other_side": [theirs[number] for number in item["other_side"]]} for item in kept["decides"]]
    # v2's view, made by case_strength.shown itself once for each passage of an item's law (D293), and gathered again.
    each, starts = _one_law_each(elements)
    theirs_each, their_starts = _one_law_each(other_side)
    view = case_strength.shown({**record, "elements": each, "other_side": theirs_each,
                                "to_get": [{**ask, "element": starts[ask["elements"][0] - 1] + 1} for ask in asks]},
                               context, part, sources)
    view["elements"] = _gathered_law(view["elements"], starts)
    view["other_side"] = _gathered_law(view["other_side"], their_starts)
    for entry, item in zip(view["elements"], elements):
        entry["heading"] = item["heading"]
    for entry, ask in zip(view["to_get"], asks):
        entry["serves"] = [view["elements"][number - 1]["element"] for number in ask["elements"]]
    for entry, item in zip(view["other_side"], other_side):
        entry["attacks"] = item["attacks"]
        entry["against"] = [view["elements"][number - 1]["element"] for number in item["against"]]
    reviewing_failed = any(failure["step"] == "case_review" for failure in record["failures"])
    state = ("unreviewed" if reviewing_failed and view["state"] == "checked" else view["state"])
    words = {"element": "element", "to_get": "what", "other_side": "relies_on", "decides": "what"}
    left = [{"item": entry["item"], "words": record[ITEMS[entry["item"]]][entry["number"] - 1][words[entry["item"]]],
             "by": entry["by"], "why": entry["why"]} for entry in record["left_out"]]
    return {"state": state, "headings": list(record["headings"]), "elements": view["elements"], "to_get": view["to_get"],
            "other_side": view["other_side"], "decides": decides, "left_out": left,
            "said": checked_line(record["checked"] == "checked", record["review"] is not None, left)}


def _one_law_each(items):
    """Each item once for each passage of its law, as v2 gives an item its one law (once with none where it gives none), and the
    place each item's first copy has (D293)."""
    each, starts = [], []
    for item in items:
        starts.append(len(each))
        each += [{**item, "law": given, "law_found": found}
                 for given, found in (list(zip(item["law"], item["law_found"])) or [(NO_LAW, False)])]
    return each, starts


def _gathered_law(entries, starts):
    """v2's view of each copy of an item gathered back into the item, its law the list of each copy's (D293)."""
    ends = [*starts[1:], len(entries)]
    return [{**entries[start], "law": [entry["law"] for entry in entries[start:end] if entry["law"] is not None]}
            for start, end in zip(starts, ends)]


#: How many of what was left out, and why, in code's words (D290).
_LEFT = {"review": ("item the independent review found wrong", "items the independent review found wrong"),
         "law": ("requirement whose law NM could not find in the law it read",
                 "requirements whose law NM could not find in the law it read"),
         "with": ("thing to get that was only for what was left out", "things to get that were only for what was left out")}


def checked_line(second, reviewed, left):
    """How a gathered account was checked, in code's words, wherever it is shown (D185; D290): a second look and the review claimed
    only where they were made, and how many items were left out and why."""
    looked = "code looked for each quotation of law in the passage it names"
    if reviewed:
        line = (f"This is NM's working list: {'a second look checked it, ' if second else ''}{looked}, and the independent review "
                "read it against the papers and the law.")
    else:
        line = (f"This is NM's working list: {'a second look checked it and ' if second else ''}{looked}. It has not been "
                "through the independent review.")
    counts = [(sum(entry["by"] == by for entry in left), words) for by, words in _LEFT.items()]
    parts = [f"{count} {words[count != 1]}" for count, words in counts if count]
    if parts:
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        line += f" Left out of it: {joined}; the research note says which and why."
    return line


def validate(record, context, part, sources, dispute):
    """A saved gathered case checked against its own answers and the research it was made from (P46): code's part re-derived
    exactly, and its first account consistent with how it was checked."""
    if not isinstance(record, dict) or record.get("contract") != CONTRACT or record.get("dispute_id") != dispute["id"]:
        raise ValueError("A saved case names no dispute of its research, or is of an unknown contract")
    _, offered, points = case_strength.material(context, part, sources, dispute)
    proposal, first, review = record.get("proposal"), record.get("first"), record.get("review")
    try:
        for given, schema in ((proposal, SCHEMA_CHECKED if record.get("checked") == "checked" else SCHEMA), (first, SCHEMA),
                              (review, REVIEW_SCHEMA)):
            if given is not None:
                require_schema(given, schema)
    except SchemaViolation as exc:
        raise ValueError("A saved case's answer is not of its contract's shape") from exc
    failures = record.get("failures")
    steps = [failure.get("step") if isinstance(failure, dict) and set(failure) == {"step", "reason"}
             and isinstance(failure["reason"], str) else None for failure in failures] if isinstance(failures, list) else None
    if steps is None:
        raise ValueError("A saved case differs from what code makes of its own answer")
    expected = _admitted({"contract": CONTRACT, "dispute_id": dispute["id"], "proposal": proposal, "first": first,
                          "checked": record.get("checked"), "failures": failures, "review": review}, offered, points, sources)
    # D290: the review is made exactly where something was left to show it, and is there exactly where it answered.
    failed_review = steps[-1:] == ["case_review"]
    before = steps[:-1] if failed_review else steps
    asked = proposal is not None and any(for_review(admit(proposal, offered, points, sources)).values())
    reviewed = (review is None) == failed_review if asked else review is None and not failed_review
    # As v2: checked, nothing failed; unchecked, the check failed (its first account kept as the account) or the first call did
    # (no account) - and the first account is there exactly where the first call answered.
    marked = (before == [] and proposal is not None and first is not None if record.get("checked") == "checked" else
              (before == ["case_check"] and first == proposal if proposal is not None else before == ["case"] and first is None)
              if record.get("checked") == "unchecked" else False)
    if record != expected or not marked or not reviewed:
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
