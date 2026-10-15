"""Time limits worked out for an answer (owner decisions, 15 Oct 2026; item 9, A4).

One model step reads the conversation (with the documents sent) and the held text of
the Acts listed as current, and proposes each time limit that bears on what the
advocate wants: the provision, the Act's own words for the period and the event time
runs from (the owner's governing principle: go by what the Acts say), the date of that
event in the advocate's or a document's exact words, any copy time, and what may extend
time. It reasons, checks itself against the words and corrects before answering.

Code then checks every quotation (the Act's words against the held text, the facts
against the conversation, finding for itself which message or page holds them), the
Act's listing and the dates, and does the arithmetic
(nm/core_engine/limitation.py). A time limit that cannot be checked is reported not
assessed with its reason; nothing is guessed. The record keeps its inputs and the
checksums of the Acts read, so replay recomputes it without the corpus.
"""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date

from nm.core_engine import limitation, research
from nm.core_engine.understanding import source_catalogue
from nm.shared import clock_contracts
from nm.shared.held_acts import ActUnavailable
from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, require_schema

#: v1 asked the model for source IDs the conversation it reads does not show.
V1_CONTRACT = "core_calculation_v1"
#: v2: the model quotes; code finds the message or page holding the words (15 Oct 2026).
CONTRACT = "core_calculation_v2"
OPERATION = "core_calculation"
MAX_OUTPUT = 12000
#: The Acts whose held text the step reads; the Code of Civil Procedure is listed as
#: current but too large to supply whole, so its own time limits are not assessed yet.
SUPPLIED = ("The Limitation Act, 1963", "The Negotiable Instruments Act, 1881")

SYSTEM = """You work with an Indian advocate on time limits: the limitation periods for suits, appeals and applications, and the time limits special laws set, such as the steps for a cheque-bounce complaint under the Negotiable Instruments Act. You receive the conversation (the advocate's messages and the documents they sent), today's date where the advocate practises, and below, the held text of the Acts under which time limits may be worked out.

First decide whether what the advocate wants needs any time limit worked out. If it does not, say so and give no calculations.

If it does, for each time limit that bears on it, go by what the Act says. Read the Act's own words to find the provision that governs the step, the period, and the event from which time runs. Quote the words that set the period and say what it runs from, exactly as they appear below; that phrase is enough, not the whole clause. For an article of the Limitation Act's Schedule, give its number and, where it has lettered parts, the letter. Then find the date of that event in what the advocate or their documents say, and quote those words exactly as written there. Where the Act lets time be left out for obtaining certified copies, give the dates the copy was applied for and was ready, if they are known. Where the steps form a chain (notice, the period to pay, then the complaint), give each step its own id. A period that runs from an event the advocate or a document dates (the drawer receiving the notice) starts from that date, quoted, even when the event belongs to an earlier step. Only a period that begins when an earlier period has run out (the complaint period, which begins once the period to pay has ended unpaid) names that earlier step's id in "after" and leaves the date empty; code then starts it the day after the earlier step's last day. Where a step is premature if taken before an earlier period has run out (a complaint filed before the period to pay ends), put that earlier step's id in "earliest_after"; a step that merely follows an earlier event in time needs nothing there. Write every date as YYYY-MM-DD. Name anything that may extend or restart time (a written acknowledgment, a part payment, time in a court without jurisdiction, a disability, fraud, condonation of delay) under "may_extend", with the provision; these are flagged for the advocate, not counted.

Do not count days yourself: give the starting date, the Act's words for the period and any copy dates, and the dates will be counted by code. Where a date is missing or uncertain, do not guess: list what is needed under "missing". Where two provisions could govern, give a calculation for each. If a time limit is set by an Act that is not given below, put it under "not_assessed" and say why.

Work in a loop: decide what needs working out, read the Act's words, choose, check each choice against the words and the facts as given, correct anything wrong, and only then answer."""

TEXT = {"type": "string"}
CALCULATION = {"type": "object", "additionalProperties": False, "required": [
    "id", "what", "act", "provision", "article", "part", "words", "period_words", "start", "copies", "done",
    "earliest_after", "reasoning", "assumptions", "missing", "may_extend"], "properties": {
    "id": TEXT, "what": TEXT, "act": {"type": "string", "enum": list(SUPPLIED)}, "provision": TEXT,
    "article": TEXT, "part": TEXT, "words": TEXT, "period_words": TEXT,
    "start": {"type": "object", "additionalProperties": False,
              "required": ["after", "event", "date", "quote"],
              "properties": {"after": TEXT, "event": TEXT, "date": TEXT, "quote": TEXT}},
    "copies": {"type": "array", "items": {"type": "object", "additionalProperties": False,
               "required": ["applied", "ready", "quote"],
               "properties": {"applied": TEXT, "ready": TEXT, "quote": TEXT}}},
    "done": {"type": "object", "additionalProperties": False, "required": ["what", "date", "quote"],
             "properties": {"what": TEXT, "date": TEXT, "quote": TEXT}},
    "earliest_after": TEXT, "reasoning": TEXT,
    "assumptions": {"type": "array", "items": TEXT}, "missing": {"type": "array", "items": TEXT},
    "may_extend": {"type": "array", "items": TEXT}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["needed", "why", "calculations", "not_assessed"],
          "properties": {"needed": {"type": "boolean"}, "why": TEXT,
                         "calculations": {"type": "array", "items": CALCULATION},
                         "not_assessed": {"type": "array", "items": {
                             "type": "object", "additionalProperties": False, "required": ["what", "why"],
                             "properties": {"what": TEXT, "why": TEXT}}}}}


class _Unchecked(ValueError):
    """One proposed time limit that code could not check; it is reported, not computed."""


def _flat(text):
    """Words for comparison: spacing closed up, and the editors' amendment markers in the
    held text ('5[within thirty days]') dropped, since they are not the Act's words."""
    return " ".join(re.sub(r"\]|\b\d+\[", "", text or "").split())


_TYPOGRAPHY = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                             "\u2014": "-"})


def _letters(text):
    """An Act's words compared without spacing or typographic marks: the held texts were
    extracted from print and run words together or split them ('thecheque', 'twic e'),
    so spacing cannot decide whether the Act says the words quoted."""
    return "".join(_flat(text).translate(_TYPOGRAPHY).casefold().split())


def _plain_map(text):
    """The text with quotation marks plain, spacing closed up and case folded, and for
    each of its characters the position in the original it came from."""
    chars, where, space = [], [], False
    for index, char in enumerate(text):
        if char.isspace():
            space = bool(chars)
            continue
        if space:
            chars.append(" ")
            where.append(index)
            space = False
        for folded in char.translate(_TYPOGRAPHY).casefold():
            chars.append(folded)
            where.append(index)
    return "".join(chars), where


def _day(value, what):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise _Unchecked(f"the {what} date {value!r} is not a calendar date") from exc


def _facts_in(context, catalogue):
    """Where a date may be quoted from, in the order searched: the latest message, the
    documents sent, then the advocate's earlier messages, latest first. Our own earlier
    notes are not facts."""
    order = [context["latest"]["source_id"], *(row["source_id"] for row in context.get("documents", ())),
             *(row["source_id"] for row in reversed(context["conversation"]))]
    return [identity for identity in dict.fromkeys(order)
            if catalogue[identity].get("record_role") in ("original_account", "supplied_document")]


def _fact(fact, catalogue, what, searched):
    """A date and the exact words it rests on: code finds the message or page holding
    the quoted words (typographic quotation marks, spacing and case aside) and keeps the
    original's own words and place."""
    quote, _ = _plain_map(fact["quote"].strip(" .,;:"))
    for identity in searched if quote else ():
        text = catalogue[identity]["text"]
        plain, where = _plain_map(text)
        found = plain.find(quote)
        if found >= 0:
            start, end = where[found], where[found + len(quote) - 1] + 1
            return {"date": _day(fact["date"], what).isoformat(), "source_id": identity,
                    "quote": text[start:end], "start": start, "end": end}
    raise _Unchecked(f"the words given for the {what} are not in the conversation or documents as quoted")


def _provision(item, acts, entries):
    """The Act's own words for this step, checked against the held text."""
    act = acts.get(item["act"])
    if act is None:
        raise _Unchecked(f"{item['act']} could not be read")
    if item["article"].strip():
        if item["act"] != "The Limitation Act, 1963":
            raise _Unchecked("only the Limitation Act's Schedule has articles")
        rows = [row for row in entries.get(item["article"].strip(), [])
                if (row["part"] or "") == item["part"].strip().strip("()").lower()]
        if len(rows) != 1:
            raise _Unchecked(f"Article {item['article']}{item['part']} is not an entry of the held Schedule "
                             "with a countable period")
        row = rows[0]
        held = _letters(" ".join((row["description"], row["period"], row["from"])))
        if item["words"].strip() and _letters(item["words"]) not in held:
            raise _Unchecked(f"the words quoted for Article {item['article']} are not in its held entry")
        return {"act": act["title"], "sha256": act["sha256"], "article": row["article"], "part": row["part"],
                "description": row["description"], "period_words": row["period"], "from": row["from"]}
    words = _flat(item["words"])
    if not words or _letters(words) not in _letters(act["text"]):
        raise _Unchecked(f"the words quoted from {item['act']} are not in its held text")
    if not item["period_words"].strip() or _letters(item["period_words"]) not in _letters(words):
        raise _Unchecked("the period words are not within the quoted provision")
    return {"act": act["title"], "sha256": act["sha256"], "article": None, "part": None,
            "words": words, "period_words": _flat(item["period_words"])}


def _compute(entry, start, today):
    """The arithmetic and standing for one checked entry; replay runs exactly this."""
    worked = limitation.working(date.fromisoformat(start), entry["provision"]["period_words"],
                                copies=[(date.fromisoformat(c["applied"]), date.fromisoformat(c["ready"]))
                                        for c in entry["copies"]])
    done = entry["done"]
    earliest = date.fromisoformat(entry["earliest"]) if entry["earliest"] else None
    standing = limitation.standing(date.fromisoformat(worked["last_day"]), today=today,
                                   done_on=date.fromisoformat(done["date"]) if done else None, earliest=earliest)
    return worked, standing


def accept(proposal, context, acts, *, today):
    """The checked record: each time limit computed, or reported not assessed with why."""
    require_schema(proposal, SCHEMA)
    catalogue = source_catalogue(context)
    searched = _facts_in(context, catalogue)
    entries = (limitation.schedule(acts["The Limitation Act, 1963"]["text"])
               if "The Limitation Act, 1963" in acts else {})
    checked, not_assessed, done_ids = [], [deepcopy(item) for item in proposal["not_assessed"]], {}
    for item in proposal["calculations"] if proposal["needed"] else []:
        try:
            provision = _provision(item, acts, entries)
            start = item["start"]
            if start["after"].strip():
                earlier = done_ids.get(start["after"].strip())
                if earlier is None:
                    raise _Unchecked(f"it starts after {start['after']!r}, which was not worked out first")
                begin = date.fromordinal(date.fromisoformat(earlier["working"]["last_day"]).toordinal() + 1)
                origin = {"after": earlier["id"], "event": start["event"], "date": begin.isoformat()}
            elif not start["date"].strip():
                raise _Unchecked("the starting date is not given" + (
                    f"; needed: {'; '.join(item['missing'])}" if item["missing"] else ""))
            else:
                origin = {"after": None, "event": start["event"],
                          **_fact(start, catalogue, "starting event", searched)}
            copies = [{"applied": _day(c["applied"], "copy applied").isoformat(),
                       "ready": _day(c["ready"], "copy ready").isoformat(),
                       **{k: v for k, v in _fact({"date": c["applied"], "quote": c["quote"]}, catalogue, "copy",
                                                 searched).items() if k != "date"}}
                      for c in item["copies"]]
            done = (_fact(item["done"], catalogue, "step taken", searched) | {"what": item["done"]["what"]}
                    if item["done"]["date"].strip() else None)
            earliest = None
            if item["earliest_after"].strip():
                before = done_ids.get(item["earliest_after"].strip())
                if before is None:
                    raise _Unchecked(f"it must follow {item['earliest_after']!r}, which was not worked out first")
                earliest = date.fromordinal(date.fromisoformat(before["working"]["last_day"]).toordinal() + 1).isoformat()
            entry = {"id": item["id"], "what": item["what"], "provision_name": item["provision"],
                     "provision": provision, "start": origin, "copies": copies, "done": done, "earliest": earliest,
                     "reasoning": item["reasoning"], "assumptions": list(item["assumptions"]),
                     "missing": list(item["missing"]), "may_extend": list(item["may_extend"])}
            entry["working"], entry["standing"] = _compute(entry, origin["date"], today)
            if earliest and earliest > entry["working"]["last_day"]:
                raise _Unchecked(f"its earliest day ({earliest}) falls after its last day "
                                 f"({entry['working']['last_day']}), so the steps are not linked as the Act links them")
        except (_Unchecked, limitation.LimitationUnassessed) as exc:
            not_assessed.append({"what": item["what"], "why": str(exc)})
            continue
        checked.append(entry)
        done_ids[item["id"]] = entry
    return {"contract": CONTRACT, "state": "worked" if proposal["needed"] else "not_needed",
            "today": today.isoformat(), "acts": [{"title": a["title"], "sha256": a["sha256"], "file": a["file"]}
                                                 for a in acts.values()],
            "proposal": deepcopy(proposal), "calculations": checked, "not_assessed": not_assessed}


def unavailable(why):
    """No calculation could be made; the answer must not state a time limit as worked out."""
    return {"contract": CONTRACT, "state": "unavailable", "why": why, "calculations": [], "not_assessed": []}


def skipped():
    return {"contract": CONTRACT, "state": "not_needed", "why": "no legal research was needed for this message",
            "calculations": [], "not_assessed": []}


def work_out(model, context, held_acts, *, now=None):
    """The step: read, propose, check, compute. A model or reading failure is recorded,
    never a reason to fail the answer or to state a time limit unchecked."""
    acts = {}
    for title in SUPPLIED:
        try:
            acts[title] = held_acts.read(title)
        except ActUnavailable:
            continue
    if not acts:
        return unavailable("the held text of the Acts used for time limits could not be read")
    where = clock_contracts.setting(now)
    today = date.fromisoformat(where["today"])
    system = SYSTEM + "\n\n" + "\n\n".join(f"=== {a['title']} (held text) ===\n{a['text']}" for a in acts.values())
    user = research.conversation_text(context)
    try:
        result = model.structured(Prompt(system=system, user=user, operation=OPERATION), SCHEMA, Tier.ROUTINE,
                                  max_tokens=MAX_OUTPUT)
    except ModelError as exc:
        return unavailable(f"the time limits could not be worked out ({type(exc).__name__})")
    if not result.usable or result.data is None:
        return unavailable("the time limits could not be worked out")
    try:
        return accept(result.data, context, acts, today=today)
    except SchemaViolation:
        return unavailable("the proposal for the time limits was not in the expected shape")


def validate(record, context):
    """Replay: the saved record recomputed from its own inputs, without the corpus."""
    if not isinstance(record, dict) or record.get("contract") not in (V1_CONTRACT, CONTRACT):
        raise ValueError("Unknown saved calculation contract")
    if record["state"] in ("unavailable",) or (record["state"] == "not_needed" and "proposal" not in record):
        if record["calculations"] or record["not_assessed"]:
            raise ValueError("A calculation that did not run has no results")
        return deepcopy(record)
    catalogue = source_catalogue(context)
    today = date.fromisoformat(record["today"])
    for entry in record["calculations"]:
        for fact in [entry["start"] if not entry["start"]["after"] else None, entry["done"], *entry["copies"]]:
            if fact and catalogue.get(fact["source_id"], {}).get("text", "")[fact["start"]:fact["end"]] != fact["quote"]:
                raise ValueError("A saved calculation's words are not in the saved conversation")
        if _compute(entry, entry["start"]["date"], today) != (entry["working"], entry["standing"]):
            raise ValueError("A saved calculation does not recompute to the same result")
    return deepcopy(record)


def presentation(record):
    """What the writer and the reviewer see: each checked result and each limit not assessed."""
    return {"state": record["state"], "why": record.get("why"),
            "today": record.get("today"),
            "worked_out": [{"what": e["what"], "provision": e["provision_name"],
                            "act": e["provision"]["act"], "period": e["provision"]["period_words"],
                            "runs_from": e["start"], "copies": e["copies"], "period_end": e["working"]["period_end"],
                            "copy_days": e["working"]["copy_days"], "last_day": e["working"]["last_day"],
                            "owner_rulings_applied": [limitation.RULINGS[r] for r in e["working"]["rulings"]],
                            "court_closure": "Limitation Act s.4 is not applied: the court calendar is not held.",
                            "step_taken": e["done"],
                            "earliest_day": e["earliest"], "standing": e["standing"],
                            "assumptions": e["assumptions"], "missing": e["missing"], "may_extend": e["may_extend"]}
                           for e in record["calculations"]],
            "not_assessed": record["not_assessed"]}


def for_answer(record):
    """What the writer and the reviewer receive: the time limits when any were worked out
    or could not be; nothing when none was needed, so such an answer binds exactly what
    an answer before item 9 bound."""
    return None if record["state"] == "not_needed" else presentation(record)
