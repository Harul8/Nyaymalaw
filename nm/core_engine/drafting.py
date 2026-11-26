"""Plan AN.67 (D315, D323; owner, 19 and 22 Nov 2026): drafting on request - a document written part by part from a versioned
template, on the shared loop runner (rounds.py, D322), not as an open-ended agent.

The template is the plan: its parts, in order, each with what it is for and the particulars it states, and the law it rests on.
The writer drafts every part from the conversation with its papers, the held law the research admitted and the time limits code
worked out; code then checks each part mechanically - every passage it rests on is one NM owns, every particular stands in the very
words of the passage it cites and in the paragraph, every particular is stated or marked as missing, no date is worked out - and a
part at fault is written again on its own, told what was wrong.

Piece 23b: a draft code finds nothing in is reviewed independently, whole, against the whole conversation, the held law and the time
limits, for what it adds, leaves out, frames otherwise or contradicts. Code admits each finding to the part it names; the parts found
at fault are written again, told what the review found, checked by code again and the draft reviewed again. Code's checks and the
review share one allowance of rewrites, as an answer's section does (REWRITES, P25), and the draft as last rewritten is always
reviewed. The rounds end when the review finds nothing and code nothing (rounds.COMPLETE), when a rewrite corrects nothing, at the
allowance, or when the writer or the reviewer cannot be asked. What is still at fault is kept with what found it, for the advocate to
see: the draft is for the advocate's review (SEQ.7), never sent by NM.

The saved draft keeps its template, each round - a writing with what code found of it, or a review with what code admitted of it -
and the parts as they stand; on reading it is checked again from those alone (P46). Piece 23c: the saved draft as a Word file,
from what it saved and nothing else. The request that starts a draft (23d) builds on it.

Piece 23d1 (D330): the first template NM holds, the demand notice under section 138 of the Negotiable Instruments Act, 1881, as
version 1. A template may now hold set wording - a part code writes from wording the owner agreed, filling in only particulars the
writer stated in the other parts, never the writer's to write - a part used only when the papers show what it needs, a value code
works out from a stated particular (the cheque's amount in words), and fixed notes for the advocate that go with every draft of it.
A part of set wording is composed again after every writing, so the review, the saved draft and its reading see it as it stands; what
the review finds in it is kept for the advocate and never written again.

Piece 23d4 (D331): a draft changed as the advocate asks. A change begins from the latest version as saved - its parts, what code and
the last review found in them - and writes again the parts the advocate's message asked to change, the writer told which message
asks it; then code's checks and the review of the whole draft follow, with an allowance of rewrites of its own, as for any draft.
It is saved as the draft's next version, keeping the parts asked and the message that asked; read again, it is checked from the
version before it. Each draft keeps how many messages the advocate had added while the matter waited when it was written, and is
checked against the conversation as it then stood (written_from), so that a later message cannot unsettle what code found of it.

Piece 23d5 (D331, D309): a draft asked for in the advocate's message. Where the understanding of the message marks a request whose
work is drafting (asked_drafting), one small call reads which held document it asks for and for which disputes (asked_for); the
turn drafts it, as a stop's draft is, where the dispute's research rests on it (rests_on) - in a run that writes and finishes.

D352 (from the paid run of 24 Nov 2026): a writer that marks a particular as not given and also lists it among the paragraph's
particulars, its own mark as the words and no source, is taken as marking it missing (_taken_in) - not as citing a passage not
offered, which spent every rewrite of that run and left three parts flagged.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from xml.etree import ElementTree

from nm.core_engine import answer_sources, reasoning, research, research_note, response_writer
from nm.core_engine import rounds as runner
from nm.shared.citation_contracts import instrument_key, provision_label, statute_title
from nm.shared.clock_contracts import IST
from nm.shared.model_port import (
    ModelError,
    Prompt,
    SchemaViolation,
    Tier,
    canonical_schema_data,
    require_schema,
)

#: v2 (23b): a draft's rounds are its writings and its reviews. No draft was ever saved under v1 (23a): no template was held and
#: nothing called it, so v1 is not read.
CONTRACT = "core_draft_v2"
OPERATION = "core_draft_writer"
REVIEW_OPERATION = "core_draft_review"
#: The rewrites a draft may make of its parts at fault, as an answer's section may (calls.SECTION_ALLOWANCE, P25), whether code or
#: the review found the fault.
REWRITES = 2
#: The two kinds of round a draft keeps.
WRITING, REVIEW = "writing", "review"
#: Where a particular not given would go, as the writer marks it: [[its id]].
_MARK = re.compile(r"\[\[([a-z0-9_]+)\]\]")
#: The draft's status until the advocate has reviewed it (SEQ.7).
FOR_REVIEW = "for_advocate_review"
#: 23d4: the versions of one dispute's draft a matter keeps - a bound on what its record holds; a change beyond it is not made.
MOST_VERSIONS = 20
#: What every saved draft keeps; from 23d4 also how many messages the advocate had added when it was written ("added"), and, for a
#: version that changes the one before, the change asked ("change").
_KEYS = frozenset({"contract", "template", "rounds", "stopped", "parts", "beside", "reviewed", "state"})
#: What the review may find of a part, and how the writer and the advocate are told it.
FINDS = {"adds": "states what nothing given bears out",
         "leaves_out": "leaves out what it needs and the conversation gives",
         "frames": "presents something otherwise than the papers or the advocate do",
         "contradicts": "says the opposite of what the papers, the advocate or the held law say"}

STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}


def _object(fields):
    return {"type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}


PARAGRAPH = _object({"text": STRING, "source_ids": STRINGS,
                     "particulars": {"type": "array", "items": _object({"particular_id": STRING, "words": STRING,
                                                                       "source_id": STRING})},
                     "missing": STRINGS})
SCHEMA = _object({"parts": {"type": "array", "items": _object({"part_id": STRING, "paragraphs": {"type": "array",
                                                                                                "items": PARAGRAPH}})}})
REVIEW_SCHEMA = _object({"findings": {"type": "array", "items": _object({
    "part_id": STRING, "kind": {"type": "string", "enum": list(FINDS)}, "said": STRING, "why": STRING, "source_ids": STRINGS})}})

WRITER = """You are an Indian advocate's junior, drafting a document for the advocate to review before it goes out. You receive the document to be drafted, set out as its parts - what each part is for and the particulars it states - the conversation with the advocate (their messages and the papers they sent, each passage under its ID), the held law our research admitted, each passage under its ID, and the time limits code worked out from the Act and the papers.

Purpose: a draft the advocate can send after their own review: each part doing what it is for, in the plain, formal language of such a document, every fact in it the papers' or the advocate's own and every provision the held law's.

Outcome: each part, in the order given, as its paragraphs. For each paragraph give the IDs of the passages it rests on. For each particular it states, give the particular's words exactly as the papers or the advocate's messages write them, and the ID of the passage they stand in, and write those words into the paragraph as they stand. Where a particular is given nowhere, do not supply it: write [[its id]] where it would go and list its id under missing. Give a date only as the papers, the advocate or the time limits give it; work none out. Where you are shown faults found in an earlier draft of a part, write that part again so that none of them remains. Where you are told that the advocate asked, in one of their messages, for parts of the draft to be changed, write those parts again as that message asks, as far as the papers, the advocate's words and the held law bear it out. A part shown with its set wording is there so you see how the document runs: its particulars are filled in from the parts you write, so it is not yours to write. A part said to be used only when something holds is given only where the papers or the advocate show that it does.

Work in a loop: draft each part, check each particular and each date against the passage you cite, correct what does not stand there, then give the whole."""

REVIEWER = """You are a senior Indian advocate, reviewing a junior's draft of a document before it goes to the advocate who asked for it. You receive the document as its parts - what each part is for and the particulars it states - the conversation with the advocate (their messages and the papers they sent, each passage under its ID), the held law our research admitted, each passage under its ID, the time limits code worked out from the Act and the papers, and the complete draft, each paragraph under its ID.

Purpose: the advocate can take the draft as a sound starting point for their own review: nothing in it that the papers, the advocate or the held law do not bear out; nothing left out that the document needs and the conversation gives; nothing presented otherwise than the papers or the advocate present it; nothing that contradicts them or the held law.

Where you are told that the advocate asked, in one of their messages, for this draft to be changed, the draft should do as that message asks.

Outcome: each problem you find, as the part it is in (its part_id); what kind it is - adds (states what nothing given bears out), leaves_out (leaves out what the part needs and the conversation gives), frames (presents something otherwise than the papers or the advocate do: an allegation as established, say, or one party for another), contradicts (says the opposite of the papers, the advocate or the held law); the words of the draft that carry it, copied exactly (nothing, for what is left out); why it matters to the advocate; and the IDs of the passages that show it. Where the draft says a particular is needed, the papers and the advocate do not give it and the advocate will supply it - unless the conversation does give it, which the draft then leaves out.

Work in a loop: read the conversation and its papers first, then the draft part by part against them and the held law; check each problem against the passages before you give it, and drop any they do not bear out. List only what you find: no problems means the draft can go to the advocate as it is."""

def _said_text(value):
    return isinstance(value, str) and bool(value.strip())


def check_template(template):
    """A template as drafting reads it: {"id", "version", "title", "law": {"act", "sections"}, "parts": [{"id", "title", "for",
    "particulars": [{"id", "said"}]}]} - every id once, the parts in order - with, where it has them (23d1), "computed": {id:
    {"from", "as", "said"}} (a value code works out, by a way of _COMPUTE, from a particular a written part states) and "notes" (fixed
    words for the advocate). A part may be set wording ("wording": its paragraphs, each [[id]] in them a particular of a written part
    or a computed value, the part itself stating none) or used only when something holds ("when": what must hold); at least one
    part is written."""
    if (not isinstance(template, dict) or not {"id", "version", "title", "law", "parts"} <= set(template)
            or not set(template) <= {"id", "version", "title", "law", "parts", "computed", "notes", "forum", "word_layout"}
            or not isinstance(template["id"], str) or not template["id"] or type(template["version"]) is not int
            or not _said_text(template["title"])
            or not isinstance(template["law"], dict) or set(template["law"]) != {"act", "sections"}
            or not isinstance(template["parts"], list) or not template["parts"]):
        raise ValueError("A template names itself, its version, its law and its parts")
    if "forum" in template and (not isinstance(template["forum"], list) or not template["forum"]
                                or not all(_said_text(name) for name in template["forum"])):
        raise ValueError("A court-specific template gives the exact accepted names of its forum")
    if "word_layout" in template and (not isinstance(template["word_layout"], str)
                                      or template["word_layout"] not in _WORD_LAYOUTS):
        raise ValueError("A template uses a registered Word layout")
    parts, particulars, written, marks = set(), set(), set(), set()
    for part in template["parts"]:
        if (not isinstance(part, dict) or not {"id", "title", "for", "particulars"} <= set(part)
                or set(part) - {"id", "title", "for", "particulars"} not in ({"wording"}, {"when"}, set()) or part["id"] in parts
                or not _MARK.fullmatch(f"[[{part['id']}]]") or not all(_said_text(part[k]) for k in ("title", "for"))
                or not isinstance(part["particulars"], list) or ("when" in part and not _said_text(part["when"]))):
            raise ValueError("Each part of a template is named once and says what it is for")
        parts.add(part["id"])
        if "wording" in part:
            if (part["particulars"] or not isinstance(part["wording"], list) or not part["wording"]
                    or not all(_said_text(text) for text in part["wording"])):
                raise ValueError("A part of set wording gives its paragraphs and states no particular of its own")
            marks |= {mark for text in part["wording"] for mark in _MARK.findall(text)}
            continue
        for item in part["particulars"]:
            if (not isinstance(item, dict) or set(item) != {"id", "said"} or item["id"] in particulars
                    or not _MARK.fullmatch(f"[[{item['id']}]]") or not _said_text(item["said"])):
                raise ValueError("Each particular of a template is named once and says what it is")
            particulars.add(item["id"])
            written.add(item["id"])
    computed = template.get("computed", {})
    if not any("wording" not in part for part in template["parts"]) or not isinstance(computed, dict):
        raise ValueError("A template has a part the writer writes")
    for name, how in computed.items():
        if (not _MARK.fullmatch(f"[[{name}]]") or name in particulars or not isinstance(how, dict)
                or set(how) != {"from", "as", "said"} or how["from"] not in written or how["as"] not in _COMPUTE
                or not _said_text(how["said"])):
            raise ValueError("A computed value of a template says what it is and how code works it out")
    if not marks <= written | set(computed):
        raise ValueError("Set wording fills in only particulars the written parts state or code works out")
    notes = template.get("notes", [])
    if not isinstance(notes, list) or not all(_said_text(note) for note in notes):
        raise ValueError("A template's notes are words for the advocate")
    return template


def _written(template):
    """The ids of the parts the writer writes, in order: every part but those of set wording."""
    return [part["id"] for part in template["parts"] if "wording" not in part]


def _said(template):
    """What each particular and each computed value of a template is, by id."""
    return {**{item["id"]: item["said"] for part in template["parts"] for item in part["particulars"]},
            **{name: how["said"] for name, how in template.get("computed", {}).items()}}


_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
         "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
#: A sum in figures as Indian papers write it: digits alone, or grouped by commas in the Indian way (2,50,000) or in threes
#: (250,000), with paise after a point.
_FIGURES = re.compile(r"(?<![\d,])(\d+|\d{1,2}(?:,\d\d)*,\d{3}|\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?(?![\d,]|\.\d)")
#: The only words a sum in figures may carry for code to write it in words: the currency's names and "only". A sum that carries
#: any other word (lakh, thousand, its own words) is not one code turns into words.
_CURRENCY = {"rs", "inr", "rupee", "rupees", "re", "only"}


def _below_hundred(number):
    return _ONES[number] if number < 20 else " ".join(filter(None, (_TENS[number // 10], _ONES[number % 10])))


def _indian(number):
    """A whole number above nought in words in the Indian way: crore, lakh, thousand, hundred."""
    crore, number = divmod(number, 10 ** 7)
    lakh, number = divmod(number, 10 ** 5)
    thousand, number = divmod(number, 1000)
    hundred, number = divmod(number, 100)
    said = [f"{_indian(crore)} Crore" if crore else "", f"{_below_hundred(lakh)} Lakh" if lakh else "",
            f"{_below_hundred(thousand)} Thousand" if thousand else "", f"{_ONES[hundred]} Hundred" if hundred else "",
            _below_hundred(number) if number else ""]
    return " ".join(filter(None, said))


def rupees_in_words(words):
    """A sum of rupees given in figures, as it is written in words on an Indian cheque or notice ("Rs. 2,50,000/-": "Rupees Two
    Lakh Fifty Thousand only"); None where the words give no one sum in figures, carry any word but the currency's, or give
    nought - code then leaves the sum in words marked as needed rather than guess it."""
    found = list(_FIGURES.finditer(str(words)))
    if len(found) != 1 or re.search(r"\d", _FIGURES.sub(" ", str(words))):
        return None
    if not {word.lower() for word in re.findall(r"[A-Za-z]+", _FIGURES.sub(" ", str(words)))} <= _CURRENCY:
        return None
    rupees, paise = int(found[0].group(1).replace(",", "")), int((found[0].group(2) or "0").ljust(2, "0"))
    if not rupees and not paise:
        return None
    said = " and ".join(filter(None, (f"Rupees {_indian(rupees)}" if rupees else "", f"{_below_hundred(paise)} Paise" if paise
                                      else "")))
    return f"{said} only"


#: The ways code works out a template's computed value from the words of the particular it comes from.
_COMPUTE = {"rupees_in_words": rupees_in_words}


def _shared(context, sources, time_limits):
    """What every call of a draft sends first and alike: the conversation, the held law by their offered IDs and the time limits,
    so that each later call of the same step reads them from the provider's cache."""
    return {"original_context": answer_sources.shown_context(context, sources),
            "held_law": answer_sources.presentation(sources, aliased=True, compact=True),
            "time_limits": time_limits or []}


def _entry(part):
    """A part as the writer and the reviewer read it: what it is for and the particulars it states, when it is used if only
    sometimes, and its set wording if it has some."""
    return {"part_id": part["id"], "title": part["title"], "for": part["for"],
            "particulars": [{"id": item["id"], "is": item["said"]} for item in part["particulars"]],
            **({"used_only_when": part["when"]} if "when" in part else {}),
            **({"set_wording": list(part["wording"])} if "wording" in part else {})}


def _document(template, asked):
    """The document as a call reads it: the parts asked for, and every part of set wording, so that the writer sees how the
    document runs and the reviewer what code wrote."""
    return {"title": template["title"], "law": template["law"],
            "parts": [_entry(part) for part in template["parts"] if part["id"] in asked or "wording" in part]}


def _sent(shared, payload):
    """A call's user text, and how much of it every call of its step sends alike."""
    user = json.dumps({**shared, **payload}, ensure_ascii=False, default=str)
    return user, len(json.dumps(shared, ensure_ascii=False, default=str)) - 1


def _asked(change, sources):
    """A change the advocate asked for (23d4), as the writer and the reviewer are told it: the message that asks it, by the ID they
    see it under, and the parts it asked to change."""
    shown = {identity: alias for alias, identity in answer_sources.aliases(sources).items()}
    return {"change_asked": {"in_message": shown.get(change["asked_in"], change["asked_in"]), "parts": list(change["parts"])}}


def _material(template, context, sources, time_limits, asked, earlier, change=None):
    """What the writer reads: the shared material first; then the parts asked for, and for a rewrite the earlier draft of each with
    what code and the review found in it; for a change the advocate asked for (23d4), which message asks it, in every writing of it."""
    return _sent(_shared(context, sources, time_limits),
                 {"document": _document(template, asked),
                  **({"earlier_draft": [{"part_id": part_id, "paragraphs": earlier[part_id]["paragraphs"],
                                         "faults": earlier[part_id]["faults"]} for part_id in asked]} if earlier else {}),
                  **(_asked(change, sources) if change else {})})


def _needed(template):
    """A particular not given, as a reader is shown it where it goes: [particular needed: what it is]."""
    said = _said(template)
    return lambda text: _MARK.sub(lambda match: f"[particular needed: {said.get(match.group(1), match.group(1))}]", text)


def _review_material(template, context, sources, time_limits, draft, change=None):
    """What the reviewer reads: the shared material first, then the whole document and the whole draft, each paragraph under its
    ID (the part's id and the paragraph's place), a particular not given shown as needed; for a change the advocate asked for
    (23d4), which message asks it."""
    needed = _needed(template)
    return _sent(_shared(context, sources, time_limits),
                 {"document": _document(template, [part["id"] for part in template["parts"]]),
                  "draft": [{"part_id": part["id"], "paragraphs": [{"id": f"{part['id']}.{at}", "text": needed(paragraph["text"])}
                                                                   for at, paragraph in enumerate(draft[part["id"]]["paragraphs"], 1)]}
                            for part in template["parts"]],
                  **(_asked(change, sources) if change else {})})


def _unstood(particular, known, text, sources, offered, at):
    """What code finds wrong in a particular a paragraph states (at: the paragraph's place), or None where it stands: a
    particular of its part, its words standing in an offered passage it cites and in the paragraph."""
    name, words, cited = particular["particular_id"], particular["words"], particular["source_id"]
    if name not in known:
        return f"Paragraph {at} gives {name}, which is not a particular of this part."
    source = sources.get(offered.get(cited)) if cited in offered else None
    if source is None:
        return f"Paragraph {at} cites {cited} for {name}, which was not offered."
    if not response_writer.stands(source["text"], words):
        return f"The words given for {name} do not stand in {cited}: {words!r}."
    if not response_writer.stands(text, words):
        return f"Paragraph {at} does not state {name} in the words given for it: {words!r}."
    return None


def _faults(proposal, template, asked, context, sources, time_limits):
    """What code finds wrong in each part a writer's proposal gives, by part id: nothing for a part that stands. A part asked for
    and not given, or given twice, is at fault - except that a part used only when something holds may be left out, or given
    with no paragraph, where it does not (23d1); a part not asked for is never taken."""
    offered = answer_sources.aliases(sources)
    parts = {part["id"]: part for part in template["parts"]}
    given = [item["part_id"] for item in proposal["parts"]]
    found = {part_id: [] for part_id in asked}
    for part_id in asked:
        if given.count(part_id) > 1 or (not given.count(part_id) and "when" not in parts[part_id]):
            found[part_id].append("This part was not given once.")
    for item in proposal["parts"]:
        part_id = item["part_id"]
        if part_id not in found or given.count(part_id) != 1:
            continue
        faults, part = found[part_id], parts[part_id]
        if not item["paragraphs"] and "when" in part:
            continue
        known = {particular["id"] for particular in part["particulars"]}
        stated, missing = set(), set()
        if not item["paragraphs"]:
            faults.append("This part has no paragraph.")
        for at, paragraph in enumerate(item["paragraphs"], 1):
            text = paragraph["text"]
            if not text.strip():
                faults.append(f"Paragraph {at} has no words.")
            unknown = [identity for identity in paragraph["source_ids"] if identity not in offered]
            if unknown:
                faults.append(f"Paragraph {at} rests on passages that were not offered: {', '.join(unknown)}.")
            for particular in paragraph["particulars"]:
                fault = _unstood(particular, known, text, sources, offered, at)
                if fault is None:
                    stated.add(particular["particular_id"])
                else:
                    faults.append(fault)
            marked = set(_MARK.findall(text))
            listed = set(paragraph["missing"])
            if marked != listed:
                faults.append(f"Paragraph {at} marks {sorted(marked) or 'nothing'} as missing but lists "
                              f"{sorted(listed) or 'nothing'}.")
            if listed - known:
                faults.append(f"Paragraph {at} lists as missing what is not a particular of this part: {sorted(listed - known)}.")
            missing |= listed & known
        left = known - stated - missing
        if left:
            faults.append("Neither stated nor marked as missing: " + ", ".join(sorted(left)) + ".")
        units = {"units": [{"id": f"{part_id}.{at}", "text": paragraph["text"]}
                           for at, paragraph in enumerate(item["paragraphs"], 1)]}
        for finding in response_writer.dates_not_given(units, context, sources, time_limits):
            faults.append(finding["mismatch"])
    return found


def _admitted(returned, template, draft, sources):
    """What code takes of a review: (by part id, each finding the review gave of that part of the draft, with only the passages it
    cites that NM offered and its words only where they stand in the part; beside the draft, each finding that names no part of it
    or says no reason, kept for the advocate to read and never acted on). A review's slip never drops what it found (P29)."""
    offered = answer_sources.aliases(sources)
    found = {part["id"]: [] for part in template["parts"]}
    beside = []
    for finding in returned["findings"]:
        item = {"part_id": finding["part_id"], "kind": finding["kind"], "said": finding["said"], "why": finding["why"],
                "source_ids": [identity for identity in finding["source_ids"] if identity in offered]}
        if finding["part_id"] not in found or not finding["why"].strip():
            beside.append(item)
            continue
        text = "\n".join(paragraph["text"] for paragraph in draft[finding["part_id"]]["paragraphs"])
        if not (finding["said"].strip() and response_writer.stands(text, finding["said"])):
            item["said"] = ""
        found[finding["part_id"]].append(item)
    return found, beside


def _told(finding, *, cited=True):
    """A finding of the review as the writer and the advocate are told it: in the Word file without the IDs of the passages,
    which mean nothing there (cited False)."""
    words = f" (the words {finding['said']!r})" if finding["said"] else ""
    see = f" See {', '.join(finding['source_ids'])}." if cited and finding["source_ids"] else ""
    return f"An independent review found that this part {FINDS[finding['kind']]}{words}: {finding['why'].strip()}{see}"


def _drafted(template, draft, proposal, faults):
    """The draft after a writing: each part the writing asked for as it now stands - its paragraphs as given (the last given, where
    a part was not given once; none, where a part used only sometimes was left out) with what code found in them."""
    draft = deepcopy(draft) if draft is not None else {}
    sometimes = {part["id"] for part in template["parts"] if "when" in part}
    given = {item["part_id"]: item["paragraphs"] for item in proposal["parts"]}
    for part_id, found in faults.items():
        before = draft.get(part_id, {"paragraphs": []})["paragraphs"]
        times = [item["part_id"] for item in proposal["parts"]].count(part_id)
        paragraphs = deepcopy(given[part_id]) if times == 1 else [] if not times and part_id in sometimes else before
        draft[part_id] = {"paragraphs": paragraphs, "faults": list(found)}
    return draft


def _composed(template, draft, sources):
    """The draft with its parts of set wording written by code (23d1): each [[id]] in their wording filled with the words a written
    part states for that particular - the first place the draft states it and code finds it stands - or with the value code works
    out from such words; left marked where neither is there. Each paragraph keeps, as a written one does, the passages it rests on,
    the particulars it states and what it leaves marked; a part of set wording is never at code's fault."""
    offered = answer_sources.aliases(sources)
    values = {}
    for part in template["parts"]:
        if "wording" in part or part["id"] not in draft:
            continue
        known = {item["id"] for item in part["particulars"]}
        for at, paragraph in enumerate(draft[part["id"]]["paragraphs"], 1):
            for particular in paragraph["particulars"]:
                if (particular["particular_id"] not in values
                        and _unstood(particular, known, paragraph["text"], sources, offered, at) is None):
                    values[particular["particular_id"]] = (particular["words"], particular["source_id"])
    computed = template.get("computed", {})
    for name, how in computed.items():
        made = _COMPUTE[how["as"]](values[how["from"]][0]) if how["from"] in values else None
        if made is not None:
            values[name] = (made, values[how["from"]][1])
    draft = dict(draft)
    for part in template["parts"]:
        if "wording" not in part:
            continue
        paragraphs = []
        for text in part["wording"]:
            used = list(dict.fromkeys(_MARK.findall(text)))
            paragraphs.append({
                "text": _MARK.sub(lambda match: values[match.group(1)][0] if match.group(1) in values else match.group(0), text),
                "source_ids": list(dict.fromkeys(values[name][1] for name in used if name in values)),
                "particulars": [{"particular_id": name, "words": values[name][0], "source_id": values[name][1]}
                                for name in used if name in values and name not in computed],
                "missing": [name for name in used if name not in values]})
        draft[part["id"]] = {"paragraphs": paragraphs, "faults": []}
    return draft


def _begun(template, earlier=None, change=None):
    """Where a draft's rounds begin: from nothing, every written part to be written; or, for a change the advocate asked for (23d4),
    from the version before it as saved - its parts, what code and its last review found in them, what that review said beside them
    and whether it was reviewed - the parts the change asked to be written first."""
    if earlier is None:
        return {"draft": None, "findings": {}, "beside": [], "rewrites": 0, "reviewed": False, "last": None, "changed": False,
                "begin": _written(template)}
    return {"draft": {part["part_id"]: {"paragraphs": deepcopy(part["paragraphs"]), "faults": list(part["faults"])}
                      for part in earlier["parts"]},
            "findings": {part["part_id"]: deepcopy(part["findings"]) for part in earlier["parts"] if part["findings"]},
            "beside": deepcopy(earlier["beside"]), "rewrites": 0, "reviewed": earlier["reviewed"], "last": None,
            "changed": False, "begin": list(change["parts"])}


def _state(template, kept, sources, begun=None):
    """Where the kept rounds leave the draft: its parts, the findings of the last review that still bear on their words, what that
    review said beside them, the rewrites used, whether the draft as it stands was reviewed, and what the last round was and
    whether, a writing, it changed the draft. After each writing, the parts of set wording are composed again from it. begun:
    where the rounds began (_begun; a first draft where None). Every writing after a version's first is a rewrite."""
    state = deepcopy(begun) if begun is not None else _begun(template)
    for entry in kept:
        if entry["kind"] == WRITING:
            before = state["draft"]
            after = _composed(template, _drafted(template, before, entry["proposal"], entry["faults"]), sources)
            if state["last"] is not None:
                state["rewrites"] += 1
            changed = after != before
            if changed:
                state["reviewed"] = False
                # A finding is of the words it was found in: a part written again is no longer at the earlier review's fault.
                state["findings"] = {part_id: found for part_id, found in state["findings"].items()
                                     if before is not None and before.get(part_id) == after.get(part_id)}
            state.update(draft=after, last=WRITING, changed=changed)
        else:
            state.update(findings={part_id: found for part_id, found in entry["findings"].items() if found},
                         beside=entry["beside"], reviewed=True, last=REVIEW, changed=False)
    return state


def _next(template, state):
    """What follows the rounds kept: (WRITING, the parts to write), (REVIEW, None), or (None, why the rounds end).

    The first writing writes every part - or, for a change (23d4), the parts it asked to change. After a writing, the parts code finds at fault are written again while rewrites are left
    and the writing changed something; otherwise the draft is reviewed - unless it was reviewed as it stands, a rewrite having
    changed nothing (NOTHING_NEW). After a review, the parts it or code found at fault are written again while rewrites are left; a
    review that finds nothing leaves the draft COMPLETE where code finds nothing either, and otherwise (code's faults, which the
    writer has already been told) ends the rounds as the writings did: NOTHING_NEW, or BACKSTOP at the allowance. Only the written
    parts are ever written; what the review finds in set wording alone ends the rounds as NOTHING_NEW, no rewrite being able to
    correct it - it is kept for the advocate."""
    draft = state["draft"]
    order = _written(template)
    if state["last"] is None:
        return WRITING, list(state["begin"])
    faulted = [part_id for part_id in order if draft[part_id]["faults"]]
    left = state["rewrites"] < REWRITES
    if state["last"] == WRITING:
        if not state["changed"] and state["reviewed"]:
            return None, runner.NOTHING_NEW
        if faulted and state["changed"] and left:
            return WRITING, faulted
        return REVIEW, None
    found = [part_id for part_id in order if draft[part_id]["faults"] or state["findings"].get(part_id)]
    if not found:
        return None, runner.NOTHING_NEW if state["findings"] else runner.COMPLETE
    if not left:
        return None, runner.BACKSTOP
    if not any(state["findings"].get(part_id) for part_id in order):
        return None, runner.NOTHING_NEW
    return WRITING, found


def _earlier(state, asked):
    """The parts asked for again as the writer is shown them: their paragraphs, with what code found and what the review found."""
    return {part_id: {"paragraphs": state["draft"][part_id]["paragraphs"],
                      "faults": [*state["draft"][part_id]["faults"], *map(_told, state["findings"].get(part_id, []))]}
            for part_id in asked}


def _failed(receipt, said):
    return ModelError(said, usage=receipt.usage, latency_ms=receipt.latency_ms, retries=receipt.retries)


def _write_call(model, template, context, sources, time_limits, asked, earlier, change=None):
    """One writing: the whole draft first, at the writer's level; a rewrite of the parts at fault - or of the parts a change the
    advocate asked for names (23d4) - at a repair's (reasoning.py)."""
    user, shared = _material(template, context, sources, time_limits, asked, earlier, change)
    prompt = Prompt(system=WRITER, user=user, operation=OPERATION, cache_through=shared,
                    effort=reasoning.effort("repair" if earlier else "write"))
    writes = reasoning.room(model, Tier.HARD, WRITER, user, json.dumps(SCHEMA))
    receipt = model.structured(prompt, SCHEMA, Tier.HARD, max_tokens=writes)
    if not receipt.usable or receipt.data is None:
        raise _failed(receipt, "The draft could not be written")
    proposal = canonical_schema_data(receipt.data, SCHEMA)
    require_schema(proposal, SCHEMA)
    return _taken_in(proposal)


def _restated_mark(particular, paragraph):
    """D352: whether an entry among a paragraph's particulars only restates a particular the paragraph marks as not given - its
    words exactly its own mark, no source, and the paragraph both carrying that mark and listing it under missing."""
    name = particular["particular_id"]
    mark = f"[[{name}]]"
    return (particular["words"] == mark and not particular["source_id"].strip() and name in paragraph["missing"]
            and mark in paragraph["text"])


def _taken_in(proposal):
    """A writing as code takes it in (D352): an entry that only restates a particular marked as not given (_restated_mark) is left
    out - the particular is the missing one it already is, not a citation of a passage not offered. Every other entry stays, to be
    checked. A saved round keeps the writing as taken in, so a draft saved before reads as saved."""
    return {**proposal, "parts": [
        {**item, "paragraphs": [{**paragraph, "particulars": [particular for particular in paragraph["particulars"]
                                                             if not _restated_mark(particular, paragraph)]}
                                for paragraph in item["paragraphs"]]}
        for item in proposal["parts"]]}


def _review_call(model, template, context, sources, time_limits, draft, change=None):
    """One review of the whole draft, on the judging tier at a review's level, as an answer's review is."""
    user, shared = _review_material(template, context, sources, time_limits, draft, change)
    prompt = Prompt(system=REVIEWER, user=user, operation=REVIEW_OPERATION, cache_through=shared,
                    effort=reasoning.effort("review"))
    writes = reasoning.room(model, Tier.JUDGE, REVIEWER, user, json.dumps(REVIEW_SCHEMA))
    receipt = model.structured(prompt, REVIEW_SCHEMA, Tier.JUDGE, max_tokens=writes)
    if not receipt.usable or receipt.data is None:
        raise _failed(receipt, "The draft could not be reviewed")
    returned = canonical_schema_data(receipt.data, REVIEW_SCHEMA)
    require_schema(returned, REVIEW_SCHEMA)
    return returned


def _round(template, context, sources, time_limits, state, entry):
    """A round as kept: a writing with what code finds of its proposal, or a review with what code admits of it."""
    if entry["kind"] == WRITING:
        return {**entry, "faults": _faults(entry["proposal"], template, entry["asked"], context, sources, time_limits)}
    found, beside = _admitted(entry["returned"], template, state["draft"], sources)
    return {**entry, "findings": found, "beside": beside}


def _run(model, template, context, sources, time_limits, begun, change):
    """The rounds of one version of a draft, from where they begin (begun; a first draft where None), on the shared loop runner,
    as _next calls for them: (the rounds kept, how they stopped). A writer or reviewer that cannot be asked after the version's
    first writing leaves the draft as the rounds before left it, said why."""
    kept = []

    def upcoming():
        return _next(template, _state(template, kept, sources, begun))

    def ask(done):
        state = _state(template, kept, sources, begun)
        kind, asked = _next(template, state)
        if kind == WRITING:
            earlier = _earlier(state, asked) if state["draft"] is not None else None
            return {"kind": WRITING, "asked": asked,
                    "proposal": _write_call(model, template, context, sources, time_limits, asked, earlier, change)}
        return {"kind": REVIEW,
                "returned": _review_call(model, template, context, sources, time_limits, state["draft"], change)}

    def admit(proposal, done):
        return _round(template, context, sources, time_limits, _state(template, kept, sources, begun), proposal), None

    def carry_out(entry, done):
        kept.append(entry)
        return upcoming()

    def spend():
        if upcoming() == (None, runner.BACKSTOP):
            raise runner.Backstop("The draft's rewrites are used")
    _, stopped = runner.run(ask, admit, carry_out, lambda outcome, done: outcome != (None, runner.NOTHING_NEW), spend=spend,
                            unavailable=(ModelError, SchemaViolation),
                            finished=lambda outcome, done: outcome == (None, runner.COMPLETE))
    return kept, stopped


def _count(context):
    """How many messages the advocate added while the matter waited (48h) the conversation carries."""
    return len(context.get("added", ()))


def written_from(record, context):
    """The conversation as a saved draft was written from it (23d4): with only the messages the advocate had added while the matter
    waited when it was written (its "added"), so that a later message - a change asked for, say - cannot unsettle what code found
    of it then (a date found not given, which the later message gives). Sources for validate are built from it. A draft saved
    before 23d4 keeps no count and is read against the conversation as it is. ValueError where the conversation has fewer."""
    if not isinstance(record, dict) or "added" not in record:
        return context
    count, added = record["added"], list(context.get("added", ()))
    if type(count) is not int or not 0 <= count <= len(added):
        raise ValueError("A saved draft was written from messages the conversation does not have")
    if count == len(added):
        return context
    return {**{key: value for key, value in context.items() if key != "added"}, **({"added": added[:count]} if count else {})}


def _change_of(template, change, context):
    """A change the advocate asked for (23d4) as a draft keeps it: {"parts": the written parts of the template it asked to change,
    in the template's order, each once; "asked_in": the advocate's message that asks it, one they added while the matter waited}.
    ValueError where it is not."""
    if not isinstance(change, dict) or set(change) != {"parts", "asked_in"}:
        raise ValueError("A change of a draft names its parts and the message that asked it")
    parts, written = change["parts"], _written(template)
    if not isinstance(parts, list) or not parts or parts != [part for part in written if part in parts]:
        raise ValueError("A change of a draft names, once each and in order, parts the writer writes")
    if change["asked_in"] not in {row["source_id"] for row in context.get("added", ())}:
        raise ValueError("A change of a draft was asked in a message the conversation does not hold")
    return change


def write(model, template, context, sources, *, time_limits=None):
    """A draft of template for the matter (D323), checked by code and reviewed independently (23b), as saved: {"contract",
    "template", "rounds": [{"kind": WRITING, "asked", "proposal", "faults"} | {"kind": REVIEW, "returned", "findings", "beside"}],
    "stopped", "parts": [{"part_id", "paragraphs", "faults", "findings"}], "beside", "reviewed", "state", "added"} - "added", from
    23d4, how many messages the advocate had added while the matter waited. The rounds follow _next. A first writing that cannot
    be made is ModelError: there is no draft. template is one the caller chose from TEMPLATES; validate reads a draft only of a
    template NM holds."""
    check_template(template)
    kept, stopped = _run(model, template, context, sources, time_limits, None, None)
    if not kept:
        raise ModelError("The draft could not be written")
    return _record(template, kept, stopped, sources, added=_count(context))


def change(model, earlier, context, sources, *, parts, asked_in, time_limits=None):
    """23d4: the next version of a draft (earlier: its latest version, as validate read it), changed as the advocate asked in their
    message asked_in (one they added while the matter waited, which context carries): the parts it names written again, the writer
    told which message asks it, then code's checks and the review of the whole draft with an allowance of rewrites of its own.
    Saved as write's record is, with "change": the parts asked and the message. A first writing that cannot be made is
    ModelError: the draft is not changed. ValueError where parts are not parts of the draft the writer writes."""
    template = check_template(earlier["template"])
    written = _written(template)
    if (not isinstance(parts, (list, tuple)) or not parts or len(set(parts)) != len(parts)
            or not all(isinstance(part, str) for part in parts) or not set(parts) <= set(written)):
        raise ValueError("A change of a draft names parts the writer writes")
    request = _change_of(template, {"parts": [part for part in written if part in parts], "asked_in": asked_in}, context)
    begun = _begun(template, earlier, request)
    kept, stopped = _run(model, template, context, sources, time_limits, begun, request)
    if not kept:
        raise ModelError("The draft could not be changed")
    return _record(template, kept, stopped, sources, begun=begun, change=request, added=_count(context))


def _record(template, kept, stopped, sources, *, begun=None, change=None, added=None):
    state = _state(template, kept, sources, begun)
    parts = [{"part_id": part["id"], **deepcopy(state["draft"][part["id"]]),
              "findings": deepcopy(state["findings"].get(part["id"], []))} for part in template["parts"]]
    return {"contract": CONTRACT, "template": deepcopy(template), "rounds": kept, "stopped": stopped, "parts": parts,
            "beside": deepcopy(state["beside"]), "reviewed": state["reviewed"], "state": FOR_REVIEW,
            **({"added": added} if added is not None else {}), **({"change": deepcopy(change)} if change is not None else {})}


_KEPT = {WRITING: ({"kind", "asked", "proposal", "faults"}, "proposal", SCHEMA),
         REVIEW: ({"kind", "returned", "findings", "beside"}, "returned", REVIEW_SCHEMA)}


def validate(record, context, sources, *, time_limits=None, templates=None, earlier=None):
    """A saved draft checked again from what it kept (P46): its template one NM holds; each round the one _next gives after the
    rounds before it, a writing finding at fault what code finds in its proposal now and a review admitting what code admits of
    what it returned; the stop as the rounds end, and the parts, findings and review as they leave them. context: the conversation
    as the draft was written from it (written_from), sources built from it. earlier (23d4): for a version that changes the one
    before, that version as validate read it - the change's rounds begin from it; None for a first version. Returns the record."""
    held = TEMPLATES if templates is None else templates
    if (not isinstance(record, dict) or not _KEYS <= set(record) <= _KEYS | {"added", "change"}
            or ("change" in record and "added" not in record)
            or record["contract"] != CONTRACT or record["state"] != FOR_REVIEW):
        raise ValueError("A saved draft is not one this code reads")
    if "added" in record and (type(record["added"]) is not int or record["added"] != _count(context)):
        raise ValueError("A saved draft is not read against the conversation it was written from")
    template = check_template(record["template"])
    if held.get((template["id"], template["version"])) != template:
        raise ValueError("A saved draft's template is not one NM holds")
    change = record.get("change")
    if (change is None) != (earlier is None):
        raise ValueError("A later version of a draft is a change of the one before it, and the first is not")
    if change is not None and (not isinstance(earlier, dict) or earlier.get("template") != template
                               or _change_of(template, change, context) != change):
        raise ValueError("A change of a draft keeps the template of the version it changes")
    begun = _begun(template, earlier, change) if change is not None else None
    stopped, rounds = record["stopped"], record["rounds"]
    if (not isinstance(stopped, dict) or set(stopped) != {"why", "reason"} or stopped["why"] not in runner.STOPS
            or not isinstance(rounds, list) or not rounds):
        raise ValueError("A saved draft does not say how its rounds ended")
    for at, entry in enumerate(rounds):
        state = _state(template, rounds[:at], sources, begun)
        kind, asked = _next(template, state)
        if kind is None:
            raise ValueError("A draft's rounds go on after they ended")
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            raise ValueError("A round of a draft is not the one its rounds before call for")
        keys, field, schema = _KEPT[kind]
        if set(entry) != keys:
            raise ValueError("A round of a draft keeps what it asked for, what came back and what code found")
        try:
            returned = canonical_schema_data(entry[field], schema)
            require_schema(returned, schema)
        except SchemaViolation:
            raise ValueError("A round of a draft keeps what the writer's or reviewer's form does not hold") from None
        if returned != entry[field] or (kind == WRITING and entry["asked"] != asked):
            raise ValueError("A round of a draft differs from what code finds of it")
        if _round(template, context, sources, time_limits, state, {key: entry[key] for key in ("kind", field, "asked")
                                                                   if key in entry}) != entry:
            raise ValueError("A round of a draft differs from what code finds of it")
    # How the rounds ended: as the last round left them; otherwise at a writer or reviewer that could not be asked.
    kind, why = _next(template, _state(template, rounds, sources, begun))
    if kind is None:
        expected = stopped["why"] == why and (bool(stopped["reason"]) if why == runner.BACKSTOP else stopped["reason"] is None)
    else:
        expected = stopped["why"] == runner.UNAVAILABLE and bool(stopped["reason"])
    if not expected:
        raise ValueError("A saved draft does not end as its rounds do")
    if record != _record(template, rounds, stopped, sources, begun=begun, change=change, added=record.get("added")):
        raise ValueError("A saved draft's parts are not as its rounds leave them")
    return record


#: Said under a draft whose last form no review saw: the reviewer could not be asked.
NOT_REVIEWED = "This draft as it stands was not reviewed independently: the review could not be made."


def _used(part):
    """Whether a saved part of a draft is shown: not a part used only sometimes that the draft left out, with nothing found in it."""
    return bool(part["paragraphs"] or part["faults"] or part["findings"])


def shown(record, earlier=None):
    """The draft as the advocate reads it on the page (23d3): each part's title and paragraphs, a particular not given written
    where it goes as [particular needed: what it is], whether code still finds the part at fault and what the review found in it -
    in the Word file's words (word), without the IDs of passages, which mean nothing to the advocate on the page either; a part
    used only sometimes that the draft leaves out, with nothing found in it, not shown; what the review said of no part; whether
    the draft as it stands was reviewed; and the template's notes for the advocate. Code's own words of each fault stay in the
    saved record. earlier (23d4): the version before it, where it changes one - "changed" then names, in order, the parts whose
    words differ from it ([] where none does); None for a first version."""
    template = record["template"]
    needed = _needed(template)
    titles = {part["id"]: part["title"] for part in template["parts"]}
    before = {} if earlier is None else {part["part_id"]: part["paragraphs"] for part in earlier["parts"]}
    changed = None if earlier is None else [
        titles[part["part_id"]] for part in record["parts"]
        if [paragraph["text"] for paragraph in part["paragraphs"]]
        != [paragraph["text"] for paragraph in before.get(part["part_id"], [])]]
    return {"title": template["title"], "state": record["state"], "changed": changed,
            "parts": [{"part_id": part["part_id"], "title": titles[part["part_id"]],
                       "paragraphs": [needed(paragraph["text"]) for paragraph in part["paragraphs"]],
                       "faults": [STILL_AT_FAULT] if part["faults"] else [],
                       "found": [_told(finding, cited=False) for finding in part["findings"]]}
                      for part in record["parts"] if _used(part)],
            "beside": [f"The review also said: {finding['why'].strip() or FINDS[finding['kind']]}" for finding in record["beside"]],
            "reviewed": None if record["reviewed"] else NOT_REVIEWED, "notes": list(template.get("notes", []))}


#: A particular not given, highlighted where it goes in the Word file, for the advocate to fill.
_HIGHLIGHT = '<w:rPr><w:highlight w:val="yellow"/></w:rPr>'
#: Said at the foot of a draft's Word file.
DRAFTED = ("Drafted by Nyaymalaw for your review from the conversation, its papers and the law NM holds. NM has not sent it: read it "
           "against the papers before it goes out.")
#: Said of a part code still finds at fault, in the Word file, where its own words name passages by IDs that mean nothing there.
STILL_AT_FAULT = "NM's own checks still find that this part does not stand as the papers and the held law give it; check it against them."


def _delhi_word_layout(document):
    """Main pleading format in Delhi High Court Practice Direction 90/Rules/DHC (10 Oct 2022)."""
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ElementTree.fromstring(document)
    margins = root.find(f".//{namespace}pgMar")
    for name, value in {"left": "2268", "right": "2268", "top": "1134", "bottom": "1134"}.items():
        margins.set(namespace + name, value)
    for paragraph in root.iter(namespace + "p"):
        properties = paragraph.find(namespace + "pPr")
        ElementTree.SubElement(properties, namespace + "spacing", {
            namespace + "line": "360", namespace + "lineRule": "auto",
        })
    for run in root.iter(namespace + "r"):
        properties = run.find(namespace + "rPr")
        if properties is None:
            properties = ElementTree.Element(namespace + "rPr")
            run.insert(0, properties)
        font = ElementTree.Element(namespace + "rFonts", {
            namespace + name: "Times New Roman" for name in ("ascii", "hAnsi", "cs", "eastAsia")
        })
        properties.insert(0, font)
        properties.insert(1, ElementTree.Element(namespace + "sz", {namespace + "val": "28"}))
        properties.insert(2, ElementTree.Element(namespace + "szCs", {namespace + "val": "28"}))
    return ElementTree.tostring(root, encoding="unicode")


_WORD_LAYOUTS = {"delhi_a4_v1": _delhi_word_layout}


def word(record, saved_at):
    """The saved draft as a Word file (23c), from what the draft saved and nothing else (record: a draft validate has read;
    saved_at: when it was saved): its title, each part's heading and paragraphs as they stand, a particular not given highlighted
    where it goes, and after the document, apart from it, what is still for the advocate to settle - the template's notes, the
    particulars needed (each once, under the first part that needs it), what code and the review still find, what the review said
    of no part, and whether the draft as it stands was reviewed. A part shown() leaves out is left out here too. The same saved
    draft always gives the same bytes. Returns (the file's name, without its extension; its bytes)."""
    template = record["template"]
    said = _said(template)
    titles = {part["id"]: part["title"] for part in template["parts"]}
    moment = datetime.fromisoformat(saved_at).astimezone(IST)
    body = [research_note.paragraph("Title", template["title"]),
            research_note.paragraph("Meta", f"Draft for your review · saved {moment.day} {moment:%B %Y}")]
    notes, noted = list(template.get("notes", [])), set()
    for part in filter(_used, record["parts"]):
        title = titles[part["part_id"]]
        body.append(research_note.paragraph("Heading2", title))
        needed = []
        for paragraph in part["paragraphs"]:
            pieces, at = [], 0
            for match in _MARK.finditer(paragraph["text"]):
                pieces.append(research_note.runs(paragraph["text"][at:match.start()]))
                pieces.append(research_note.runs(f"[particular needed: {said.get(match.group(1), match.group(1))}]", _HIGHLIGHT))
                needed.append(said.get(match.group(1), match.group(1)))
                at = match.end()
            pieces.append(research_note.runs(paragraph["text"][at:]))
            body.append(research_note.paragraph("Normal", "", "".join(pieces)))
        notes += [f"{title}: the papers do not give {item}." for item in dict.fromkeys(needed) if item not in noted]
        noted |= set(needed)
        notes += [f"{title}: {STILL_AT_FAULT}"] if part["faults"] else []
        notes += [f"{title}: {_told(finding, cited=False)}" for finding in part["findings"]]
    notes += [f"The review also said: {finding['why'].strip() or FINDS[finding['kind']]}" for finding in record["beside"]]
    notes += [] if record["reviewed"] else [NOT_REVIEWED]
    if notes:
        body += [research_note.paragraph("Heading1", "For your review"),
                 research_note.paragraph("Meta", "Not part of the document: remove these notes before it is sent.")]
        body += [research_note.paragraph("Normal", f"• {note}") for note in notes]
    body.append(research_note.paragraph("Meta", DRAFTED))
    name = f"Draft {moment:%Y-%m-%d} - " + (" ".join(re.sub(r"[^\w\s-]", "", template["title"]).split())[:60].strip() or "document")
    document = research_note.document_xml(body)
    layout = _WORD_LAYOUTS.get(template.get("word_layout"))
    return name, research_note.word_file(layout(document) if layout else document, name, saved_at)



#: D330 (23 Nov 2026, the owner's word on Claude's recommendation): the demand notice under section 138 of the Negotiable
#: Instruments Act, 1881, version 1, in English. The demand, what follows if the amount is not paid and the close are set wording;
#: a drawer that is a company or firm has its part, used only where the papers show one; other sums only where the advocate asks
#: for them, apart from the cheque's amount; the advocate's name and office address marked as needed until their account holds
#: them. The notes say what the held text of section 138 and section 142 requires of the dates. A draft of it is for the
#: advocate's own review before anything is sent; the set wording is the owner's to correct, as a new version.
NI_138_V1 = {
    "id": "ni_138_demand_notice", "version": 1,
    "title": "Demand notice under section 138 of the Negotiable Instruments Act, 1881",
    "law": {"act": "Negotiable Instruments Act, 1881", "sections": ["138"]},
    "parts": [
        {"id": "heading", "title": "Notice", "for": "The opening of the notice: its date, how it is sent and the place it is sent from.",
         "particulars": [
             {"id": "notice_date", "said": "the date of the notice"},
             {"id": "modes", "said": "how the notice is sent (registered post, speed post, courier, e-mail or another way)"},
             {"id": "place", "said": "the place the notice is sent from"}]},
        {"id": "parties", "title": "From and to",
         "for": "Who sends the notice and for whom, and the drawer of the cheque, to whom it is addressed.",
         "particulars": [
             {"id": "advocate_name", "said": "the advocate's name"},
             {"id": "advocate_address", "said": "the advocate's office address"},
             {"id": "client_name", "said": "the name of the advocate's client, the payee or holder in due course of the cheque"},
             {"id": "client_address", "said": "the client's address"},
             {"id": "drawer_name", "said": "the name of the drawer of the cheque"},
             {"id": "drawer_address", "said": "the drawer's address"}]},
        {"id": "company", "title": "Those in charge of the drawer",
         "for": ("The persons the papers show were in charge of, and responsible to, the drawer for the conduct of its business "
                 "(section 141), to whom the notice is also addressed."),
         "when": "the papers show that the drawer is a company, a firm or another association of individuals",
         "particulars": [{"id": "persons_in_charge", "said": "the names, positions and addresses of those persons"}]},
        {"id": "debt", "title": "The debt",
         "for": ("The legally enforceable debt or other liability for whose discharge, in whole or in part, the cheque was drawn, "
                 "and how it arose, as the papers show it."),
         "particulars": [
             {"id": "debt_nature", "said": "what the debt or other liability is and how it arose"},
             {"id": "debt_amount", "said": "the amount of the debt or liability"}]},
        {"id": "cheque", "title": "The cheque",
         "for": "The cheque the drawer drew on their account and gave to the client for that debt or liability.",
         "particulars": [
             {"id": "cheque_number", "said": "the cheque's number"},
             {"id": "cheque_date", "said": "the date the cheque bears"},
             {"id": "cheque_amount", "said": "the cheque's amount in figures, as the cheque or the papers give it"},
             {"id": "drawee_bank", "said": "the bank and branch on which the cheque is drawn"}]},
        {"id": "dishonour", "title": "Its return unpaid",
         "for": ("How the cheque was presented and returned unpaid: when and through which bank it was presented, the reason the "
                 "bank gave in its own words, and when the client received the bank's information of its return."),
         "particulars": [
             {"id": "presented_on", "said": "when the cheque was presented"},
             {"id": "presented_through", "said": "the bank and branch through which the client presented the cheque"},
             {"id": "returned_on", "said": "the date of the bank's memo returning the cheque"},
             {"id": "return_reason", "said": "the reason for the return, in the words of the bank's memo"},
             {"id": "information_received",
              "said": "when the client received the bank's information that the cheque was returned unpaid"}]},
        {"id": "other_sums", "title": "Other sums claimed",
         "for": ("Each sum the advocate asks the notice to claim besides the cheque's amount, stated apart from it and on the basis "
                 "the advocate gives."),
         "when": "the advocate asks for interest, notice charges or another sum to be claimed besides the cheque's amount",
         "particulars": [{"id": "other_sums_claimed", "said": "each such sum and its basis"}]},
        {"id": "demand", "title": "Demand",
         "for": ("The demand for payment of the cheque's amount within fifteen days of the receipt of the notice (section 138, "
                 "provisos (b) and (c))."),
         "particulars": [],
         "wording": ["My client therefore calls upon you to pay the said amount of [[cheque_amount]] ([[amount_in_words]]), the "
                     "amount of the said cheque, to my client within fifteen days of the receipt of this notice."]},
        {"id": "consequence", "title": "If it is not paid", "for": "What follows if the amount is not paid within that time.",
         "particulars": [],
         "wording": ["Take notice that if you fail to pay the said amount to my client within fifteen days of the receipt of this "
                     "notice, my client shall be constrained to make a complaint against you for the offence punishable under "
                     "section 138 of the Negotiable Instruments Act, 1881, as section 142 of that Act provides, and to take such "
                     "other proceedings as the law allows, entirely at your risk as to costs and consequences."]},
        {"id": "close", "title": "Close", "for": "The close of the notice.", "particulars": [],
         "wording": ["A copy of this notice is retained in my office for further action.", "[[advocate_name]], Advocate",
                     "Place: [[place]]", "Date: [[notice_date]]"]},
    ],
    "computed": {"amount_in_words": {"from": "cheque_amount", "as": "rupees_in_words", "said": "the cheque's amount in words"}},
    "notes": [
        ("Section 138, proviso (a): the cheque must have been presented to the bank within six months from the date on which it "
         "is drawn or within the period of its validity, whichever is earlier. Check the date of presentation against both."),
        ("Section 138, proviso (b): this notice must be given in writing within thirty days of the receipt of information from "
         "the bank regarding the return of the cheque as unpaid. Check that it goes out within that time."),
        ("Section 138, proviso (c), and section 142(1)(b): the fifteen days for payment run from the drawer's receipt of this "
         "notice, and a complaint is to be made within one month of the date on which the cause of action arises under proviso "
         "(c). Keep proof of when the notice was sent and when it was received."),
        ("The demand, what follows if the amount is not paid and the close are set wording, with only the particulars filled in "
         "from the papers; correct it where the matter needs it."),
    ],
}

#: AN.68, D316. Ordinary English demand for payment between private contracting parties.
PRIVATE_PAYMENT_V1 = {
    "id": "private_contractual_payment_demand",
    "version": 1,
    "title": "Private contractual payment demand notice",
    "law": {"act": "Indian Contract Act, 1872", "sections": ["37", "73"]},
    "parts": [
        {
            "id": "heading", "title": "Date and delivery",
            "for": "State the notice date and the proposed delivery method, with no claim that service has occurred.",
            "particulars": [
                {"id": "notice_date", "said": "the date of the notice"},
                {"id": "delivery_method", "said": "the proposed method of delivery"},
            ],
        },
        {
            "id": "parties", "title": "Sender and recipient",
            "for": "Identify the advocate, the client claiming payment and the contracting party addressed.",
            "particulars": [
                {"id": "advocate", "said": "the advocate's name and correspondence address"},
                {"id": "claimant", "said": "the client's correct name and address"},
                {"id": "recipient", "said": "the recipient's correct legal name and service address"},
            ],
        },
        {
            "id": "agreement", "title": "Agreement and obligation",
            "for": "Summarise the agreement, the client's performance and the recipient's payment obligation in order. "
                   "Use the actual agreement, invoice or other identified record and attribute disputed facts.",
            "particulars": [
                {"id": "agreement_reference", "said": "the agreement or transaction giving rise to the demand"},
                {"id": "performance", "said": "what the claimant supplied or performed"},
                {"id": "payment_obligation", "said": "the payment term, including when the amount fell due"},
            ],
        },
        {
            "id": "account", "title": "Balance claimed",
            "for": "Explain the default and identify the amount the client claims is outstanding after supported "
                   "credits or payments. Preserve disputed amounts and never calculate a new balance.",
            "particulars": [
                {"id": "default_details", "said": "what remains unpaid and the basis for saying so"},
                {"id": "amount_due", "said": "the stated outstanding principal amount"},
            ],
        },
        {
            "id": "interest", "title": "Interest or additional sum",
            "for": "State the amount or rate, period and basis of any additional sum separately from the principal.",
            "when": "the advocate asks to include it and the papers or held law support its basis",
            "particulars": [
                {"id": "interest_basis", "said": "the basis, amount or rate, and period of the additional claim"},
            ],
        },
        {
            "id": "demand_amount", "title": "Demand",
            "for": "State the claimant's demand for the supported outstanding principal.",
            "particulars": [],
            "wording": ["On my client's instructions, I call upon you to pay the claimed outstanding principal "
                        "of [[amount_due]]."],
        },
        {
            "id": "reply_terms", "title": "Payment and response terms",
            "for": "Give only the supported payment or reply instructions. Identify any requested period as the "
                   "client's request unless a supported contractual term governs it.",
            "when": "the advocate gives payment instructions, requests a reply by a stated time, "
                    "or the papers establish an applicable notice or cure term",
            "particulars": [
                {"id": "response_terms", "said": "the stated payment instructions or response terms"},
            ],
        },
        {
            "id": "close", "title": "Close",
            "for": "Reserve the client's position without stating that any action will be taken.",
            "particulars": [],
            "wording": ["My client reserves the remedies available under the agreement and applicable law.",
                        "Yours faithfully,", "[[advocate]]"],
        },
    ],
    "notes": [
        "This template is for a private contractual payment demand. Check any applicable contract notice clause, "
        "cure period, special statutory procedure and limitation separately before issuing it.",
        "Check the parties, payment ledger and credits against original records. Confirm the delivery address and "
        "method, and retain proof of dispatch and receipt.",
    ],
}

def _written_part(identity, title, purpose, particulars, *, when=None):
    part = {"id": identity, "title": title, "for": purpose,
            "particulars": [{"id": field, "said": said} for field, said in particulars.items()]}
    if when is not None:
        part["when"] = when
    return part


def _fixed_part(identity, title, purpose, *paragraphs):
    return {"id": identity, "title": title, "for": purpose, "particulars": [], "wording": list(paragraphs)}


_DELHI_HIGH_COURT = ["High Court of Delhi", "Delhi High Court"]
_ARTICLE_226 = {"act": "Constitution of India, 1950", "sections": ["Article 226"]}

#: AN.69, D317. Civil writ petition under Article 226 in the High Court of Delhi.
DELHI_CIVIL_WRIT_V1 = {
    "id": "delhi_high_court_civil_writ", "version": 1,
    "title": "Civil writ petition under Article 226 in the High Court of Delhi",
    "forum": list(_DELHI_HIGH_COURT), "law": deepcopy(_ARTICLE_226),
    "word_layout": "delhi_a4_v1",
    "parts": [
        _fixed_part("court", "Cause title", "Identify the named forum and the jurisdiction.",
                    "IN THE HIGH COURT OF DELHI AT NEW DELHI", "CIVIL WRIT JURISDICTION",
                    "W.P.(C) No. ______ of ______"),
        _written_part("parties", "Memo of parties", "Identify and describe each party in its supported role.", {
            "petitioners": "each petitioner's name, description and service particulars",
            "respondents": "each respondent's name, designation and service particulars",
        }),
        _written_part("synopsis", "Synopsis and list of dates",
                      "Summarise the case and set out the necessary events in chronological order.", {
            "short_case": "the challenged act or omission and the relief sought",
            "dated_facts": "the material events and their supported dates",
        }),
        _written_part("facts", "Material facts", "Plead numbered, concise material facts and identify their annexures.", {
            "grounds_facts": "the material facts and their supporting records",
            "impugned_act": "the challenged decision, action or omission and the respondent responsible",
        }),
        _written_part("maintainability", "Jurisdiction and maintainability",
                      "Set out the basis of territorial jurisdiction and maintainability, including available "
                      "alternative remedies and any explanation the papers support.", {
            "venue_facts": "the material facts giving this court territorial jurisdiction",
            "remedy_position": "the basis for proceeding by writ and the position on alternative remedies",
            "delay_position": "the filing chronology and any explanation for delay",
        }),
        _written_part("grounds", "Grounds", "State each supported ground separately, tied to the facts and held law.", {
            "legal_grounds": "the grounds the advocate relies on and the supporting authority and facts",
        }),
        _written_part("previous", "Earlier proceedings",
                      "Disclose earlier or parallel proceedings for related relief. Do not assume that there were none.", {
            "prior_proceedings": "the stated position on related proceedings and any earlier petition and order",
        }),
        _written_part("prayer", "Prayer", "Identify the specific writ, direction or relief and the respondent it is sought against.", {
            "relief": "the exact final relief sought and against whom",
        }),
        _written_part("interim", "Interim relief", "State the supported interim request and its urgency separately.", {
            "interim_relief": "the precise interim relief and its factual basis",
        }, when="the advocate has asked for interim relief"),
        _written_part("filing", "Annexures and signatures", "Identify existing annexures and leave dispatch, signature and filing for review.", {
            "annexures": "the annexures relied on, including the challenged order where applicable",
            "signatures": "the petitioner and counsel who will sign and their filing particulars",
        }),
    ],
    "notes": [
        "Prepare the signed memo of parties, synopsis and chronology, indexed annexures and a separate attested "
        "supporting affidavit. Include relevant earlier petitions and orders where disclosed.",
        "Check advance service and proof, including service on nominated counsel where required by the "
        "Delhi High Court amended civil writ rules. Verify the current registry checklist before filing.",
    ],
}


#: The templates NM drafts from, by id and version (AN.67: template selection is the owner's). A version, once a draft of it is
#: saved, stays held as it is so that the draft reads as saved (P46); a change is a new version.
TEMPLATES: dict[tuple[str, int], dict] = {
    (template["id"], template["version"]): check_template(template)
    for template in (NI_138_V1, PRIVATE_PAYMENT_V1, DELHI_CIVIL_WRIT_V1)
}


def rests_on(record, *, requested=None):
    """The held templates a dispute's research rests on (plan AN.67, 23d2; D331), the latest version of each, in the order NM
    holds them: those whose Act, and a section of it the template names, the research's picks chose (research.chosen_candidates).
    The Act is matched by its instrument key - the one grouping of held copies (citation_contracts) - and the section by its one
    rendering; never by topic words or a near title. Court-specific templates additionally need an explicit selection
    with the named forum checked by the request reader. [] where none does."""
    read = set()
    for candidate in research.chosen_candidates(record):
        if candidate["kind"] != "provision":
            continue
        row = candidate.get("source") or {}
        title = statute_title(row.get("act_name") or row.get("title") or "", row.get("act_id") or "")
        read.add((instrument_key(title), provision_label("", str(row.get("section_number") or ""))))
    return [template for template in held()
            if (not template.get("forum") or template["id"] == requested)
            and any((instrument_key(template["law"]["act"]), provision_label("", section)) in read
                   for section in template["law"]["sections"])]


def held():
    """The latest version of each template NM holds, in the order NM holds them."""
    latest = {}
    for (identity, version), template in TEMPLATES.items():
        if identity not in latest or version > latest[identity]["version"]:
            latest[identity] = template
    return list(latest.values())


def law_said(template):
    """The law a template rests on, in words: "section 138 of the Negotiable Instruments Act, 1881"."""
    sections = template["law"]["sections"]
    if all(section.startswith("Article ") for section in sections):
        return f"{' or '.join(sections)} of the {template['law']['act']}"
    return f"{'section' if len(sections) == 1 else 'sections'} {' or '.join(sections)} of the {template['law']['act']}"


def forum_named(template, words):
    """The exact name of the court named in the original request, not a semantic routing rule."""
    names = template.get("forum")
    return not names or any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", words, flags=re.IGNORECASE) for name in names)


# Piece 23d5 (D331, D309): a draft asked for in the advocate's message. The understanding of the message, made already, marks each
# thing the advocate asks of NM with the kind of work it is (understanding.py); a request whose work is drafting is a deliverable of
# its own. Which held document it asks for, and for which disputes, is the model's reading of the request - one small call, made only
# where drafting is asked - never topic words; whether the law fits stays code's (rests_on).

def asked_drafting(interpretation):
    """The requests in the advocate's message whose work is drafting, as the understanding of it marked them: the advocate's words,
    what NM understood they mean and the result they want. [] where none is."""
    return [{"words": (unit.get("source") or {}).get("text") or "", "meaning": unit.get("meaning") or "",
             "wanted": unit.get("desired_result") or ""}
            for unit in (interpretation or {}).get("units") or ()
            if isinstance(unit, dict) and unit.get("kind") == "request" and unit.get("requested_work") == "drafting"]


ASKED_OPERATION = "core_draft_asked"

ASKED = """You are an Indian advocate's junior. In their message the advocate asked for something to be drafted. You receive what they asked - their own words and what we understood they want - the disputes of the matter, each with the legal questions its research asks, and the documents we hold a template for, each with the law it rests on.

Purpose: we draft from a template only the document the advocate asked for, and only for the disputes they asked it for, so that they are given what they asked and nothing they did not.

Outcome: document - the id of the template that is the document the advocate asked for, or none where none of them is; disputes - the ids of the disputes they asked it for, or an empty list where they named none or asked for it for the whole matter.

Work in a loop: read the request with the disputes and the documents, decide, check your answer against the advocate's exact words, correct it, then answer."""


def _asked_refused(data, templates, ids):
    """Why a reading of the request cannot be admitted; None where it can."""
    if not isinstance(data, dict) or data.get("document") not in (*templates, "none"):
        return "document must be one of: " + ", ".join([*templates, "none"])
    named = data.get("disputes")
    if (not isinstance(named, list) or not all(isinstance(name, str) for name in named) or len(set(named)) != len(named)
            or not set(named) <= set(ids)):
        return "disputes must name, once each, only these disputes: " + ", ".join(ids)
    return None


def asked_for(model, requests, disputes):
    """Which held document the advocate's request to draft asks for, and for which of the matter's disputes (23d5). requests:
    asked_drafting's; disputes: [{"id", "name", "legal_questions"}], in the matter's order. {"template": the held template asked for,
    or None where none of them is; "disputes": the ids asked, in the matter's order - [] where the request names none}. Asked once
    more, told why, where the reading cannot be admitted; None where it still cannot. A failure of the model raises, for the caller
    to say so."""
    templates = {template["id"]: template for template in held()}
    ids = [dispute["id"] for dispute in disputes]
    schema = _object({"document": {"type": "string", "enum": [*templates, "none"]}, "disputes": STRINGS})
    given = {"asked": requests, "disputes": disputes,
             "documents_we_hold": [{"id": template["id"], "title": template["title"], "rests_on": law_said(template)}
                                   for template in templates.values()]}
    asked = dict(given)
    for _ in range(2):
        user = json.dumps(asked, ensure_ascii=False)
        receipt = model.structured(Prompt(system=ASKED, user=user, operation=ASKED_OPERATION,
                                          effort=reasoning.effort("draft_asked")),
                                   schema, Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, ASKED, user, json.dumps(schema)))
        data = canonical_schema_data(receipt.data, schema) if receipt.usable and receipt.data is not None else None
        why = _asked_refused(data, templates, ids)
        if why is None:
            chosen = templates.get(data["document"])
            selection = {"template": chosen, "disputes": [name for name in ids if name in data["disputes"]]}
            if chosen is not None and not all(forum_named(chosen, request["words"]) for request in requests):
                selection["forum_needed"] = chosen["forum"][0]
            return selection
        asked = {**given, "your_last_answer": data, "why_it_cannot_be_taken": why}
    return None
