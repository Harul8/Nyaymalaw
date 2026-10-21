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

import json
import re
from copy import deepcopy
from datetime import date

from nm.core_engine import limitation, research
from nm.core_engine.understanding import TYPOGRAPHY as _TYPOGRAPHY, nearest, source_catalogue
from nm.shared import clock_contracts
from nm.shared.held_acts import ActUnavailable
from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, require_schema

#: v1 asked the model for source IDs the conversation it reads does not show.
V1_CONTRACT = "core_calculation_v1"
#: v2: the model quotes; code finds the message or page holding the words (15 Oct 2026).
V2_CONTRACT = "core_calculation_v2"
#: v3 (owner, 16 Oct 2026): one correction pass when code refuses a proposed time limit.
V3_CONTRACT = "core_calculation_v3"
#: v4 (18 Oct 2026, after two of three live runs called an unfiled suit "in time"): a step
#: taken is the step the time limit governs, never the event time runs from, and code
#: refuses one quoted from that event's own words. A limit that cannot be worked out for
#: want of a fact (its starting date not given, or the earlier limit it waits on not worked
#: out) spends no correction, which cannot supply a fact; every live run had spent one so.
V4_CONTRACT = "core_calculation_v4"
#: v5 (owner decision Q16, 19 Oct 2026; two of three live runs that day dated the payee's
#: thirty days for the demand notice from the bank's return of the cheque, not from the payee
#: receiving the bank's information): the step's own check says which event the words it
#: quotes date, and whether that is the very event the Act's words say time runs from. Where
#: its check says it is not, code leaves the date not given and the limit not worked out - a
#: missing fact, which no correction can supply.
V5_CONTRACT = "core_calculation_v5"
#: v6 (owner decision P34, 21 Oct 2026; live runs 2-4 left a suit for the price not worked out,
#: Article 15 running "when the period of credit expires" and no one dating that end): where the
#: event the Act names is the end of a period the facts set, the step quotes the date that period
#: runs from and the period itself, and code counts the period's end, from which the Act's period
#: runs.
CONTRACT = "core_calculation_v6"
OPERATION = "core_calculation"
CORRECTION_OPERATION = "core_calculation_correct"
MAX_OUTPUT = 12000
#: The Acts whose held text the step reads, all three listed as current.
SUPPLIED = ("The Limitation Act, 1963", "The Negotiable Instruments Act, 1881", "The Code of Civil Procedure, 1908")
#: An Act longer than this (the Code of Civil Procedure, about 1.1 million characters) is
#: supplied as every section and rule of it that states a period, word for word.
WHOLE_LIMIT = 300_000

SYSTEM = """You work with an Indian advocate on time limits: the limitation periods for suits, appeals and applications, and the time limits special laws set, such as the steps for a cheque-bounce complaint under the Negotiable Instruments Act. You receive the conversation (the advocate's messages and the documents they sent), today's date where the advocate practises, and below, the held text of the Acts under which time limits may be worked out.

First decide whether what the advocate wants needs any time limit worked out. If it does not, say so and give no calculations.

If it does, for each time limit that bears on it, go by what the Act says. Read the Act's own words to find the provision that governs the step, the period, and the event from which time runs. Under "words", quote the words that set the period and say what it runs from, exactly as they appear below; that phrase is enough, not the whole clause. Under "period_words", give the period itself as it stands inside those words, such as "thirty days". Where one provision sets more than one period, such as a period and an outer limit to which a court may extend it, give each period its own calculation with its own words. For an article of the Limitation Act's Schedule, give its number and, where it has lettered parts, the letter. Then find the date of that event in what the advocate or their documents say, and quote those words exactly as written there. Check that the words you quote date that very event, not one before or after it: the bank returning a cheque is not the payee receiving the bank's information about it, and posting a notice is not its delivery. Say under "dated_event", in a few words, what the quoted words date, and under "same_event" whether it is the event the Act's words name. Where the event the Act names is the end of a period the advocate or a document sets (a period of credit, a time agreed for payment or performance) and nothing dates that end itself, quote instead the date that period runs from as given (the delivery, the agreement), say under "same_event" whether the quoted words date the very event that period runs from, give the period under "period_words" as the facts state it, such as "30 days", and quote the words stating it under "period_quote"; code counts the period's end, and the Act's period runs from that day. Otherwise leave "period_words" and "period_quote" empty. Where nothing the advocate or a document says dates the event or the start of such a period, leave the date and quote empty and say under "missing" what date is needed. Where the Act lets time be left out for obtaining certified copies, give the dates the copy was applied for and was ready, if they are known. Where the steps form a chain (notice, the period to pay, then the complaint), give each step its own id. A period that runs from an event the advocate or a document dates (the drawer receiving the notice) starts from that date, quoted, even when the event belongs to an earlier step. Only a period that begins when an earlier period has run out (the complaint period, which begins once the period to pay has ended unpaid) names that earlier step's id in "after" and leaves the date empty; code then starts it the day after the earlier step's last day. Where a step is premature if taken before an earlier period has run out (a complaint filed before the period to pay ends), put that earlier step's id in "earliest_after"; a step that merely follows an earlier event in time needs nothing there. Under "done", give the step this time limit governs only if the advocate or a document says it has already been taken (the suit or complaint filed, the notice given, the payment made), with its date and the words saying so; otherwise leave it empty. The event time runs from is never the step itself: for a suit for the price, the delivery starts the time and filing the suit is the step; for the drawer's time to pay, the notice reaching the drawer starts it and the payment is the step. Write every date as YYYY-MM-DD. Name anything that may extend or restart time (a written acknowledgment, a part payment, time in a court without jurisdiction, a disability, fraud, condonation of delay) under "may_extend", with the provision; these are flagged for the advocate, not counted.

Do not count days yourself: give the starting date, the Act's words for the period and any copy dates, and the dates will be counted by code. Where a date is missing or uncertain, do not guess: list what is needed under "missing". Where two provisions could govern, give a calculation for each. If a time limit is set by an Act that is not given below, put it under "not_assessed" and say why. List only time limits, each a period within which a step must be taken; the documents, proof and other things a case needs are for the answer, not for you, so leave them out altogether, not under "not_assessed" either.

Work in a loop: decide what needs working out, read the Act's words, choose, check each choice against the words and the facts as given, correct anything wrong, and only then answer."""

#: The one correction pass (owner, 16 Oct 2026), asked after the conversation and the
#: proposal; the system text and the held Acts stay exactly as for the proposal.
CORRECT = """Code checked the time limits you proposed against the held text of the Acts and the conversation. It could not check the ones listed above, and says why for each. Look at each again against the Act's words and the conversation, find what was wrong and correct it, then check the correction against the words before answering. Quote the Act's words and the advocate's or a document's words exactly as they stand.

Give back each of these time limits corrected, with its own id, under "calculations"; the ones that were checked stand and are not given again. If one cannot be worked out from the held text and what was said, list its id under "cannot" with why."""

TEXT = {"type": "string"}
CALCULATION = {"type": "object", "additionalProperties": False, "required": [
    "id", "what", "act", "provision", "article", "part", "words", "period_words", "start", "copies", "done",
    "earliest_after", "reasoning", "assumptions", "missing", "may_extend"], "properties": {
    "id": TEXT, "what": TEXT, "act": {"type": "string", "enum": list(SUPPLIED)}, "provision": TEXT,
    "article": TEXT, "part": TEXT, "words": TEXT, "period_words": TEXT,
    "start": {"type": "object", "additionalProperties": False,
              "required": ["after", "event", "date", "quote", "dated_event", "same_event", "period_words",
                           "period_quote"],
              "properties": {"after": TEXT, "event": TEXT, "date": TEXT, "quote": TEXT,
                             "dated_event": {**TEXT, "description": "What the quoted words date, in a few words."},
                             "same_event": {"type": "boolean",
                                            "description": "Whether that is the very event the Act's words say "
                                                           "time runs from, or, with a period the facts set, the "
                                                           "event that period runs from."},
                             "period_words": {**TEXT, "description": "A period the facts set whose end is the event "
                                                                     "the Act names, such as \"30 days\"; else empty."},
                             "period_quote": {**TEXT, "description": "The advocate's or a document's exact words "
                                                                     "stating that period; else empty."}}},
    "copies": {"type": "array", "items": {"type": "object", "additionalProperties": False,
               "required": ["applied", "ready", "quote"],
               "properties": {"applied": TEXT, "ready": TEXT, "quote": TEXT}}},
    "done": {"type": "object", "additionalProperties": False, "required": ["what", "date", "quote"],
             "description": "The step this time limit governs, only if already taken; never the event time runs "
                            "from. Empty when the step has not been taken.",
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
CORRECTION = {"type": "object", "additionalProperties": False, "required": ["calculations", "cannot"],
              "properties": {"calculations": {"type": "array", "items": CALCULATION},
                             "cannot": {"type": "array", "items": {
                                 "type": "object", "additionalProperties": False, "required": ["id", "why"],
                                 "properties": {"id": TEXT, "why": TEXT}}}}}


class _Unchecked(ValueError):
    """One proposed time limit that code could not check; it is reported, not computed.
    `near` holds the Act's own words closest to a quotation code could not find, for
    the correction pass only. `correctable` is False for a fact that is missing, which
    the correction pass cannot supply."""

    def __init__(self, why, near=None, *, correctable=True):
        super().__init__(why)
        self.near = near
        self.correctable = correctable


def _flat(text):
    """Words for comparison: spacing closed up, and the editors' amendment markers in the
    held text ('5[within thirty days]') dropped, since they are not the Act's words."""
    return " ".join(re.sub(r"\]|\b\d+\[", "", text or "").split())


def _letters(text):
    """An Act's words compared without spacing or typographic marks: the held texts were
    extracted from print and run words together or split them ('thecheque', 'twic e'),
    so spacing cannot decide whether the Act says the words quoted."""
    return "".join(_flat(text).translate(_TYPOGRAPHY).casefold().split())


def _entry_words(text):
    """A Schedule entry's words for the cross-check, letters and digits alone (17 Oct 2026):
    code finds the entry by its number and joins its columns itself, so the mark the model
    joins them with ('Three years; The date fixed for the performance') is not the Act's
    and cannot decide whether the right entry was read."""
    return re.sub(r"[\W_]", "", _letters(text))


def _nearest(quote, text):
    """A held text's own words nearest to a quotation, an Act's or what the advocate or a
    document says (owner, 16 Oct 2026: code locates; the model judges what to quote), spacing
    closed up: this step compares an Act's words without spacing, which its held texts got
    wrong in print."""
    window = nearest(quote, text)
    if window is None:
        return None
    start, end = window
    return ("…" if start > 0 else "") + " ".join(text[start:end].split()) + ("…" if end < len(text) else "")


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
    original's own words and place. Words not found there are refused with the words
    nearest to them, from the first text searched that holds any (live run 8, 21 Oct 2026:
    a step quoted "I delivered" for the advocate's "my client delivered", and its
    correction, told only that the words were not there, quoted them so again)."""
    quote, _ = _plain_map(fact["quote"].strip(" .,;:"))
    for identity in searched if quote else ():
        text = catalogue[identity]["text"]
        plain, where = _plain_map(text)
        found = plain.find(quote)
        if found >= 0:
            start, end = where[found], where[found + len(quote) - 1] + 1
            return {"date": _day(fact["date"], what).isoformat(), "source_id": identity,
                    "quote": text[start:end], "start": start, "end": end}
    near = next((words for identity in searched if quote
                 if (words := _nearest(fact["quote"], catalogue[identity]["text"]))), None)
    raise _Unchecked(f"the words given for the {what} are not in the conversation or documents as quoted", near=near)


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
        # The period and its start are taken from the held columns below; the quoted words
        # only confirm that this entry was read.
        entry = " ".join(" ".join((row["description"], row["period"], row["from"])).split())
        if item["words"].strip() and _entry_words(item["words"]) not in _entry_words(entry):
            # The held entry is short: its own words are the words nearest to the quotation.
            raise _Unchecked(f"the words quoted for Article {item['article']} are not in its held entry", near=entry)
        return {"act": act["title"], "sha256": act["sha256"], "article": row["article"], "part": row["part"],
                "description": row["description"], "period_words": row["period"], "from": row["from"]}
    words = _flat(item["words"])
    if not words or _letters(words) not in _letters(act["text"]):
        raise _Unchecked(f"the words quoted from {item['act']} are not in its held text",
                         near=_nearest(words, act["text"]))
    if not item["period_words"].strip() or _letters(item["period_words"]) not in _letters(words):
        raise _Unchecked("the period words are not within the quoted provision")
    return {"act": act["title"], "sha256": act["sha256"], "article": None, "part": None,
            "words": words, "period_words": _flat(item["period_words"])}


def _agreed(start, catalogue, searched):
    """P34: the end of a period the facts set (thirty days' credit from the delivery), counted
    by code from the date it runs from, both quoted as the advocate or a document gives them;
    the Act's period runs from that end. The record keeps both quotations and the count."""
    runs_from = _fact(start, catalogue, "date the agreed period runs from", searched)
    stated = _fact({"date": start["date"], "quote": start["period_quote"]}, catalogue, "agreed period", searched)
    words = " ".join(start["period_words"].split())
    if not start["period_quote"].strip() or _letters(words) not in _letters(stated["quote"]):
        raise _Unchecked("the agreed period is not within the words quoted as stating it")
    period = limitation.period_from_words(words)
    if period is None:
        raise _Unchecked(f"no countable period in the agreed period's words {words!r}")
    end, _ = limitation.end_of_period(date.fromisoformat(runs_from["date"]), period[0], period[1])
    assumed = (f"The {period[2]} the facts set are counted from {runs_from['date']}, that day left out, ending on "
               f"{end.isoformat()}; the agreement's own terms may count them differently.")
    return {"after": None, "event": start["event"], "date": end.isoformat(),
            "agreed": {"runs_from": runs_from, "period_words": period[2],
                       "period": {key: stated[key] for key in ("source_id", "quote", "start", "end")},
                       "assumed": assumed}}


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
    checked, not_assessed, _ = _check(proposal, context, acts, today)
    return _record(proposal, acts, today, checked, not_assessed)


def _record(proposal, acts, today, checked, not_assessed, correction=None):
    """The saved record: the proposal, the one correction if it was asked for, and the
    results code checked and computed."""
    return {"contract": CONTRACT, "state": "worked" if proposal["needed"] else "not_needed",
            "today": today.isoformat(), "acts": [{"title": a["title"], "sha256": a["sha256"], "file": a["file"]}
                                                 for a in acts.values()],
            "proposal": deepcopy(proposal), "correction": deepcopy(correction), "calculations": checked,
            "not_assessed": not_assessed}


def _check(proposal, context, acts, today):
    """Each proposed time limit checked and computed, or refused with why: the checked
    entries, what is not assessed, and the refused ones by id."""
    catalogue = source_catalogue(context)
    searched = _facts_in(context, catalogue)
    entries = (limitation.schedule(acts["The Limitation Act, 1963"]["text"])
               if "The Limitation Act, 1963" in acts else {})
    checked, not_assessed, done_ids = [], [deepcopy(item) for item in proposal["not_assessed"]], {}
    refused, unassessed = [], {}

    def waiting(identity, how):
        """A limit that waits on another: correctable only where that other is not one
        listed before it and found unworkable for want of a fact."""
        if identity in unassessed:
            return _Unchecked(f"it {how} “{unassessed[identity]}” ends, and that could not be worked out",
                              correctable=False)
        return _Unchecked(f"it {how} {identity!r}, which is not a time limit worked out before it")

    for item in proposal["calculations"] if proposal["needed"] else []:
        try:
            start = item["start"]
            if not start["after"].strip() and not start["date"].strip():
                # A missing fact first: without its date nothing can be worked out, whatever the
                # quotation, and no correction can supply it (the fifth live run spent one so).
                raise _Unchecked("the starting date is not given" + (
                    f"; needed: {'; '.join(item['missing'])}" if item["missing"] else ""), correctable=False)
            if start["after"].strip() and start["after"].strip() in unassessed:
                raise waiting(start["after"].strip(), "starts once")
            if not start["after"].strip() and start.get("same_event") is False:
                # Q16: by the step's own check, the words it quotes date another event than the
                # one time runs from; that event's date is still to be given.
                raise _Unchecked(f"the words quoted date {start.get('dated_event', '').strip() or 'another event'}, "
                                 f"not the event time runs from ({start['event'].strip() or 'as the Act words it'}), "
                                 "whose date is not given" + (f"; needed: {'; '.join(item['missing'])}"
                                                              if item["missing"] else ""), correctable=False)
            provision = _provision(item, acts, entries)
            if start["after"].strip():
                earlier = done_ids.get(start["after"].strip())
                if earlier is None:
                    raise waiting(start["after"].strip(), "starts once")
                begin = date.fromordinal(date.fromisoformat(earlier["working"]["last_day"]).toordinal() + 1)
                origin = {"after": earlier["id"], "event": start["event"], "date": begin.isoformat()}
            elif start.get("period_words", "").strip():
                origin = _agreed(start, catalogue, searched)
                item = {**item, "assumptions": [*item["assumptions"], origin["agreed"]["assumed"]]}
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
            if (done and origin.get("source_id") == done["source_id"]
                    and done["start"] < origin["end"] and origin["start"] < done["end"]):
                # v4: the words of the event time runs from cannot also be the step taken.
                raise _Unchecked("the step taken is quoted from the words of the event time runs from; give the "
                                 "step this time limit governs (the suit filed, the notice given, the payment "
                                 "made) only if it has been taken, and leave it empty otherwise")
            earliest = None
            if item["earliest_after"].strip():
                before = done_ids.get(item["earliest_after"].strip())
                if before is None:
                    raise waiting(item["earliest_after"].strip(), "may not be taken before")
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
            unassessed[item["id"]] = item["what"]
            if getattr(exc, "correctable", True):
                refused.append({"id": item["id"], "what": item["what"], "why": str(exc),
                                "near": getattr(exc, "near", None)})
            continue
        checked.append(entry)
        done_ids[item["id"]] = entry
    return checked, not_assessed, refused


def _corrected(proposal, correction, refused):
    """The proposal with each refused time limit replaced by its correction, matched by
    id: what was checked stands, a correction for anything else is ignored, and one the
    model says it cannot work out leaves the proposal with its reason."""
    ids = {row["id"] for row in refused}
    fixes = {item["id"]: item for item in correction["calculations"] if item["id"] in ids}
    cannot = {row["id"]: row["why"] for row in correction["cannot"] if row["id"] in ids and row["id"] not in fixes}
    merged = deepcopy(proposal)
    merged["calculations"] = [deepcopy(fixes.get(item["id"], item)) for item in proposal["calculations"]
                              if item["id"] not in cannot]
    first = {row["id"]: row for row in refused}
    dropped = [{"what": first[id_]["what"], "why": f"{first[id_]['why']}; on a second look: {why}"}
               for id_, why in cannot.items()]
    return merged, dropped


def unavailable(why):
    """No calculation could be made; the answer must not state a time limit as worked out."""
    return {"contract": CONTRACT, "state": "unavailable", "why": why, "calculations": [], "not_assessed": []}


def skipped():
    return {"contract": CONTRACT, "state": "not_needed", "why": "no legal research was needed for this message",
            "calculations": [], "not_assessed": []}


def _held_text(act):
    """An Act's held text as the step reads it: whole, or for an Act too large to supply
    whole, every section and rule of it that states a period, word for word, under where
    it sits. Quotations are checked against the whole held text either way."""
    if len(act["text"]) <= WHOLE_LIMIT:
        return f"=== {act['title']} (held text) ===\n{act['text']}"
    parts = limitation.provisions_with_periods(act["text"])
    return (f"=== {act['title']} (held text: every section and rule that states a period of days, months or "
            f"years, word for word; the rest of it is held but not shown here) ===\n"
            + "\n\n".join(f"[{part['label']}]\n{part['text']}" for part in parts))


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
    system = SYSTEM + "\n\n" + "\n\n".join(_held_text(act) for act in acts.values())
    user = research.conversation_text(context)
    try:
        result = model.structured(Prompt(system=system, user=user, operation=OPERATION), SCHEMA, Tier.ROUTINE,
                                  max_tokens=MAX_OUTPUT)
    except ModelError as exc:
        return unavailable(f"the time limits could not be worked out ({type(exc).__name__})")
    if not result.usable or result.data is None:
        return unavailable("the time limits could not be worked out")
    proposal = result.data
    try:
        require_schema(proposal, SCHEMA)
    except SchemaViolation:
        return unavailable("the proposal for the time limits was not in the expected shape")
    checked, not_assessed, refused = _check(proposal, context, acts, today)
    if not refused:
        return _record(proposal, acts, today, checked, not_assessed)
    # ONE CORRECTION PASS (owner, 16 Oct 2026): only when code refused something, shown
    # each refusal's reason; its corrections face exactly the same checks.
    correction = _correct(model, system, user, proposal, refused)
    if correction["state"] != "corrected":
        return _record(proposal, acts, today, checked, not_assessed, correction)
    merged, dropped = _corrected(proposal, correction["proposal"], refused)
    checked, not_assessed, _ = _check(merged, context, acts, today)
    return _record(proposal, acts, today, checked, not_assessed + dropped, correction)


def _correct(model, system, user, proposal, refused):
    """The one correction call: the same system text and held Acts, then the conversation,
    the model's own proposal and why code could not check each refused time limit."""
    reasons = "\n".join(f"- {row['id']} ({row['what']}): {row['why']}"
                        + (f". The held text nearest to the words you quoted reads: “{row['near']}”"
                           if row.get("near") else "") for row in refused)
    text = (f"{user}\n\nYour proposal:\n{json.dumps(proposal, ensure_ascii=False, indent=1)}\n\n"
            f"Not checked:\n{reasons}\n\n{CORRECT}")
    made = {"refused": deepcopy(refused), "state": "unavailable", "why": None, "proposal": None}
    try:
        result = model.structured(Prompt(system=system, user=text, operation=CORRECTION_OPERATION), CORRECTION,
                                  Tier.ROUTINE, max_tokens=MAX_OUTPUT)
    except (ModelError, SchemaViolation) as exc:
        return {**made, "why": type(exc).__name__}
    if not result.usable or result.data is None:
        return {**made, "why": "no usable correction"}
    try:
        require_schema(result.data, CORRECTION)
    except SchemaViolation:
        return {**made, "why": "SchemaViolation"}
    return {**made, "state": "corrected", "proposal": deepcopy(result.data)}


def validate(record, context):
    """Replay: the saved record recomputed from its own inputs, without the corpus."""
    if not isinstance(record, dict) or record.get("contract") not in (V1_CONTRACT, V2_CONTRACT, V3_CONTRACT,
                                                                      V4_CONTRACT, V5_CONTRACT, CONTRACT):
        raise ValueError("Unknown saved calculation contract")
    correction = (record.get("correction") if record["contract"] in (V3_CONTRACT, V4_CONTRACT, V5_CONTRACT, CONTRACT)
                  else None)
    if correction is not None and (
            not isinstance(correction, dict) or correction.get("state") not in ("corrected", "unavailable")
            or not correction.get("refused") or (correction["state"] == "corrected") != (correction["proposal"] is not None)):
        raise ValueError("A saved correction has no checked disposition")
    if record["state"] in ("unavailable",) or (record["state"] == "not_needed" and "proposal" not in record):
        if record["calculations"] or record["not_assessed"]:
            raise ValueError("A calculation that did not run has no results")
        return deepcopy(record)
    catalogue = source_catalogue(context)
    today = date.fromisoformat(record["today"])
    for entry in record["calculations"]:
        agreed = entry["start"].get("agreed")
        if agreed is not None:
            # P34 (v6): the period's end recounted from its two quoted facts.
            period = limitation.period_from_words(agreed["period_words"])
            if (record["contract"] != CONTRACT or period is None or entry["start"]["date"] != limitation.end_of_period(
                    date.fromisoformat(agreed["runs_from"]["date"]), period[0], period[1])[0].isoformat()):
                raise ValueError("A saved calculation's agreed period does not recount to its start")
        starts = [agreed["runs_from"], agreed["period"]] if agreed else [
            entry["start"] if not entry["start"]["after"] else None]
        for fact in [*starts, entry["done"], *entry["copies"]]:
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
