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
and the parts as they stand; on reading it is checked again from those alone (P46). The Word export (23c) and the request that
starts a draft (23d) build on it.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

from nm.core_engine import answer_sources, reasoning, response_writer
from nm.core_engine import rounds as runner
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

Outcome: each part, in the order given, as its paragraphs. For each paragraph give the IDs of the passages it rests on. For each particular it states, give the particular's words exactly as the papers or the advocate's messages write them, and the ID of the passage they stand in, and write those words into the paragraph as they stand. Where a particular is given nowhere, do not supply it: write [[its id]] where it would go and list its id under missing. Give a date only as the papers, the advocate or the time limits give it; work none out. Where you are shown faults found in an earlier draft of a part, write that part again so that none of them remains.

Work in a loop: draft each part, check each particular and each date against the passage you cite, correct what does not stand there, then give the whole."""

REVIEWER = """You are a senior Indian advocate, reviewing a junior's draft of a document before it goes to the advocate who asked for it. You receive the document as its parts - what each part is for and the particulars it states - the conversation with the advocate (their messages and the papers they sent, each passage under its ID), the held law our research admitted, each passage under its ID, the time limits code worked out from the Act and the papers, and the complete draft, each paragraph under its ID.

Purpose: the advocate can take the draft as a sound starting point for their own review: nothing in it that the papers, the advocate or the held law do not bear out; nothing left out that the document needs and the conversation gives; nothing presented otherwise than the papers or the advocate present it; nothing that contradicts them or the held law.

Outcome: each problem you find, as the part it is in (its part_id); what kind it is - adds (states what nothing given bears out), leaves_out (leaves out what the part needs and the conversation gives), frames (presents something otherwise than the papers or the advocate do: an allegation as established, say, or one party for another), contradicts (says the opposite of the papers, the advocate or the held law); the words of the draft that carry it, copied exactly (nothing, for what is left out); why it matters to the advocate; and the IDs of the passages that show it. Where the draft says a particular is needed, the papers and the advocate do not give it and the advocate will supply it - unless the conversation does give it, which the draft then leaves out.

Work in a loop: read the conversation and its papers first, then the draft part by part against them and the held law; check each problem against the passages before you give it, and drop any they do not bear out. List only what you find: no problems means the draft can go to the advocate as it is."""

#: The templates NM drafts from, by id and version: none until the owner agrees one (AN.67: template selection is the owner's).
TEMPLATES: dict[tuple[str, int], dict] = {}


def check_template(template):
    """A template as drafting reads it: {"id", "version", "title", "law": {"act", "sections"}, "parts": [{"id", "title", "for",
    "particulars": [{"id", "said"}]}]} - every id once, the parts in order."""
    if (not isinstance(template, dict) or set(template) != {"id", "version", "title", "law", "parts"}
            or not isinstance(template["id"], str) or not template["id"] or type(template["version"]) is not int
            or not isinstance(template["title"], str) or not template["title"].strip()
            or not isinstance(template["law"], dict) or set(template["law"]) != {"act", "sections"}
            or not isinstance(template["parts"], list) or not template["parts"]):
        raise ValueError("A template names itself, its version, its law and its parts")
    parts, particulars = set(), set()
    for part in template["parts"]:
        if (not isinstance(part, dict) or set(part) != {"id", "title", "for", "particulars"} or part["id"] in parts
                or not _MARK.fullmatch(f"[[{part['id']}]]") or not all(isinstance(part[k], str) and part[k].strip()
                                                                      for k in ("title", "for"))
                or not isinstance(part["particulars"], list)):
            raise ValueError("Each part of a template is named once and says what it is for")
        parts.add(part["id"])
        for item in part["particulars"]:
            if (not isinstance(item, dict) or set(item) != {"id", "said"} or item["id"] in particulars
                    or not _MARK.fullmatch(f"[[{item['id']}]]") or not isinstance(item["said"], str) or not item["said"].strip()):
                raise ValueError("Each particular of a template is named once and says what it is")
            particulars.add(item["id"])
    return template


def _shared(context, sources, time_limits):
    """What every call of a draft sends first and alike: the conversation, the held law by their offered IDs and the time limits,
    so that each later call of the same step reads them from the provider's cache."""
    return {"original_context": answer_sources.shown_context(context, sources),
            "held_law": answer_sources.presentation(sources, aliased=True, compact=True),
            "time_limits": time_limits or []}


def _document(template, asked):
    return {"title": template["title"], "law": template["law"],
            "parts": [{"part_id": part["id"], "title": part["title"], "for": part["for"],
                       "particulars": [{"id": item["id"], "is": item["said"]} for item in part["particulars"]]}
                      for part in template["parts"] if part["id"] in asked]}


def _sent(shared, payload):
    """A call's user text, and how much of it every call of its step sends alike."""
    user = json.dumps({**shared, **payload}, ensure_ascii=False, default=str)
    return user, len(json.dumps(shared, ensure_ascii=False, default=str)) - 1


def _material(template, context, sources, time_limits, asked, earlier):
    """What the writer reads: the shared material first; then the parts asked for, and for a rewrite the earlier draft of each with
    what code and the review found in it."""
    return _sent(_shared(context, sources, time_limits),
                 {"document": _document(template, asked),
                  **({"earlier_draft": [{"part_id": part_id, "paragraphs": earlier[part_id]["paragraphs"],
                                         "faults": earlier[part_id]["faults"]} for part_id in asked]} if earlier else {})})


def _needed(template):
    """A particular not given, as a reader is shown it where it goes: [particular needed: what it is]."""
    said = {item["id"]: item["said"] for part in template["parts"] for item in part["particulars"]}
    return lambda text: _MARK.sub(lambda match: f"[particular needed: {said.get(match.group(1), match.group(1))}]", text)


def _review_material(template, context, sources, time_limits, draft):
    """What the reviewer reads: the shared material first, then the whole document and the whole draft, each paragraph under its
    ID (the part's id and the paragraph's place), a particular not given shown as needed."""
    needed = _needed(template)
    return _sent(_shared(context, sources, time_limits),
                 {"document": _document(template, [part["id"] for part in template["parts"]]),
                  "draft": [{"part_id": part["id"], "paragraphs": [{"id": f"{part['id']}.{at}", "text": needed(paragraph["text"])}
                                                                   for at, paragraph in enumerate(draft[part["id"]]["paragraphs"], 1)]}
                            for part in template["parts"]]})


def _faults(proposal, template, asked, context, sources, time_limits):
    """What code finds wrong in each part a writer's proposal gives, by part id: nothing for a part that stands. A part asked for
    and not given, or given twice, is at fault; a part not asked for is never taken."""
    offered = answer_sources.aliases(sources)
    parts = {part["id"]: part for part in template["parts"]}
    given = [item["part_id"] for item in proposal["parts"]]
    found = {part_id: [] for part_id in asked}
    for part_id in asked:
        if given.count(part_id) != 1:
            found[part_id].append("This part was not given once.")
    for item in proposal["parts"]:
        part_id = item["part_id"]
        if part_id not in found or given.count(part_id) != 1:
            continue
        faults, part = found[part_id], parts[part_id]
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
                name, words, cited = particular["particular_id"], particular["words"], particular["source_id"]
                if name not in known:
                    faults.append(f"Paragraph {at} gives {name}, which is not a particular of this part.")
                    continue
                source = sources.get(offered.get(cited)) if cited in offered else None
                if source is None:
                    faults.append(f"Paragraph {at} cites {cited} for {name}, which was not offered.")
                elif not response_writer.stands(source["text"], words):
                    faults.append(f"The words given for {name} do not stand in {cited}: {words!r}.")
                elif not response_writer.stands(text, words):
                    faults.append(f"Paragraph {at} does not state {name} in the words given for it: {words!r}.")
                else:
                    stated.add(name)
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


def _told(finding):
    """A finding of the review as the writer and the advocate are told it."""
    words = f" (the words {finding['said']!r})" if finding["said"] else ""
    cited = f" See {', '.join(finding['source_ids'])}." if finding["source_ids"] else ""
    return f"An independent review found that this part {FINDS[finding['kind']]}{words}: {finding['why'].strip()}{cited}"


def _drafted(draft, proposal, faults):
    """The draft after a writing: each part the writing asked for as it now stands - its paragraphs as given (the last given, where
    a part was not given once) with what code found in them."""
    draft = deepcopy(draft) if draft is not None else {}
    given = {item["part_id"]: item["paragraphs"] for item in proposal["parts"]}
    for part_id, found in faults.items():
        before = draft.get(part_id, {"paragraphs": []})["paragraphs"]
        once = [item["part_id"] for item in proposal["parts"]].count(part_id) == 1
        draft[part_id] = {"paragraphs": deepcopy(given[part_id]) if once else before, "faults": list(found)}
    return draft


def _state(template, kept):
    """Where the kept rounds leave the draft: its parts, the findings of the last review that still bear on their words, what that
    review said beside them, the rewrites used, whether the draft as it stands was reviewed, and what the last round was and
    whether, a writing, it changed the draft."""
    state = {"draft": None, "findings": {}, "beside": [], "rewrites": 0, "reviewed": False, "last": None, "changed": False}
    for entry in kept:
        if entry["kind"] == WRITING:
            before = state["draft"]
            after = _drafted(before, entry["proposal"], entry["faults"])
            if before is not None:
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

    The first writing writes every part. After a writing, the parts code finds at fault are written again while rewrites are left
    and the writing changed something; otherwise the draft is reviewed - unless it was reviewed as it stands, a rewrite having
    changed nothing (NOTHING_NEW). After a review, the parts it or code found at fault are written again while rewrites are left; a
    review that finds nothing leaves the draft COMPLETE where code finds nothing either, and otherwise (code's faults, which the
    writer has already been told) ends the rounds as the writings did: NOTHING_NEW, or BACKSTOP at the allowance."""
    draft = state["draft"]
    if draft is None:
        return WRITING, [part["id"] for part in template["parts"]]
    order = [part["id"] for part in template["parts"]]
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
        return None, runner.COMPLETE
    if not left:
        return None, runner.BACKSTOP
    if not state["findings"]:
        return None, runner.NOTHING_NEW
    return WRITING, found


def _earlier(state, asked):
    """The parts asked for again as the writer is shown them: their paragraphs, with what code found and what the review found."""
    return {part_id: {"paragraphs": state["draft"][part_id]["paragraphs"],
                      "faults": [*state["draft"][part_id]["faults"], *map(_told, state["findings"].get(part_id, []))]}
            for part_id in asked}


def _failed(receipt, said):
    return ModelError(said, usage=receipt.usage, latency_ms=receipt.latency_ms, retries=receipt.retries)


def _write_call(model, template, context, sources, time_limits, asked, earlier):
    """One writing: the whole draft first, at the writer's level; a rewrite of the parts at fault at a repair's (reasoning.py)."""
    user, shared = _material(template, context, sources, time_limits, asked, earlier)
    prompt = Prompt(system=WRITER, user=user, operation=OPERATION, cache_through=shared,
                    effort=reasoning.effort("repair" if earlier else "write"))
    writes = reasoning.room(model, Tier.HARD, WRITER, user, json.dumps(SCHEMA))
    receipt = model.structured(prompt, SCHEMA, Tier.HARD, max_tokens=writes)
    if not receipt.usable or receipt.data is None:
        raise _failed(receipt, "The draft could not be written")
    proposal = canonical_schema_data(receipt.data, SCHEMA)
    require_schema(proposal, SCHEMA)
    return proposal


def _review_call(model, template, context, sources, time_limits, draft):
    """One review of the whole draft, on the judging tier at a review's level, as an answer's review is."""
    user, shared = _review_material(template, context, sources, time_limits, draft)
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


def write(model, template, context, sources, *, time_limits=None):
    """A draft of template for the matter (D323), checked by code and reviewed independently (23b), as saved: {"contract",
    "template", "rounds": [{"kind": WRITING, "asked", "proposal", "faults"} | {"kind": REVIEW, "returned", "findings", "beside"}],
    "stopped", "parts": [{"part_id", "paragraphs", "faults", "findings"}], "beside", "reviewed", "state"}. The rounds follow
    _next. A writer or reviewer that cannot be asked after the first writing leaves the draft as the rounds before left it, said
    why; a first writing that cannot be made is ModelError: there is no draft. template is one the caller chose from TEMPLATES;
    validate reads a draft only of a template NM holds."""
    check_template(template)
    kept = []

    def upcoming():
        return _next(template, _state(template, kept))

    def ask(done):
        state = _state(template, kept)
        kind, asked = _next(template, state)
        if kind == WRITING:
            earlier = _earlier(state, asked) if state["draft"] is not None else None
            return {"kind": WRITING, "asked": asked,
                    "proposal": _write_call(model, template, context, sources, time_limits, asked, earlier)}
        return {"kind": REVIEW, "returned": _review_call(model, template, context, sources, time_limits, state["draft"])}

    def admit(proposal, done):
        return _round(template, context, sources, time_limits, _state(template, kept), proposal), None

    def carry_out(entry, done):
        kept.append(entry)
        return upcoming()

    def spend():
        if upcoming() == (None, runner.BACKSTOP):
            raise runner.Backstop("The draft's rewrites are used")
    _, stopped = runner.run(ask, admit, carry_out, lambda outcome, done: outcome != (None, runner.NOTHING_NEW), spend=spend,
                            unavailable=(ModelError, SchemaViolation),
                            finished=lambda outcome, done: outcome == (None, runner.COMPLETE))
    if not kept:
        raise ModelError("The draft could not be written")
    return _record(template, kept, stopped)


def _record(template, kept, stopped):
    state = _state(template, kept)
    parts = [{"part_id": part["id"], **deepcopy(state["draft"][part["id"]]),
              "findings": deepcopy(state["findings"].get(part["id"], []))} for part in template["parts"]]
    return {"contract": CONTRACT, "template": deepcopy(template), "rounds": kept, "stopped": stopped, "parts": parts,
            "beside": deepcopy(state["beside"]), "reviewed": state["reviewed"], "state": FOR_REVIEW}


_KEPT = {WRITING: ({"kind", "asked", "proposal", "faults"}, "proposal", SCHEMA),
         REVIEW: ({"kind", "returned", "findings", "beside"}, "returned", REVIEW_SCHEMA)}


def validate(record, context, sources, *, time_limits=None, templates=None):
    """A saved draft checked again from what it kept (P46): its template one NM holds; each round the one _next gives after the
    rounds before it, a writing finding at fault what code finds in its proposal now and a review admitting what code admits of
    what it returned; the stop as the rounds end, and the parts, findings and review as they leave them. Returns the record."""
    held = TEMPLATES if templates is None else templates
    if (not isinstance(record, dict)
            or set(record) != {"contract", "template", "rounds", "stopped", "parts", "beside", "reviewed", "state"}
            or record["contract"] != CONTRACT or record["state"] != FOR_REVIEW):
        raise ValueError("A saved draft is not one this code reads")
    template = check_template(record["template"])
    if held.get((template["id"], template["version"])) != template:
        raise ValueError("A saved draft's template is not one NM holds")
    stopped, rounds = record["stopped"], record["rounds"]
    if (not isinstance(stopped, dict) or set(stopped) != {"why", "reason"} or stopped["why"] not in runner.STOPS
            or not isinstance(rounds, list) or not rounds):
        raise ValueError("A saved draft does not say how its rounds ended")
    for at, entry in enumerate(rounds):
        state = _state(template, rounds[:at])
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
    kind, why = _next(template, _state(template, rounds))
    if kind is None:
        expected = stopped["why"] == why and (bool(stopped["reason"]) if why == runner.BACKSTOP else stopped["reason"] is None)
    else:
        expected = stopped["why"] == runner.UNAVAILABLE and bool(stopped["reason"])
    if not expected:
        raise ValueError("A saved draft does not end as its rounds do")
    if record != _record(template, rounds, stopped):
        raise ValueError("A saved draft's parts are not as its rounds leave them")
    return record


#: Said under a draft whose last form no review saw: the reviewer could not be asked.
NOT_REVIEWED = "This draft as it stands was not reviewed independently: the review could not be made."


def shown(record):
    """The draft as the advocate reads it: each part's title and paragraphs, a particular not given written where it goes as
    [particular needed: what it is], what code still finds in a part and what the review found in it; what the review said of no
    part; and whether the draft as it stands was reviewed."""
    template = record["template"]
    needed = _needed(template)
    titles = {part["id"]: part["title"] for part in template["parts"]}
    return {"title": template["title"], "state": record["state"],
            "parts": [{"part_id": part["part_id"], "title": titles[part["part_id"]],
                       "paragraphs": [needed(paragraph["text"]) for paragraph in part["paragraphs"]],
                       "faults": list(part["faults"]), "found": [_told(finding) for finding in part["findings"]]}
                      for part in record["parts"]],
            "beside": [f"The review also said: {finding['why'].strip() or FINDS[finding['kind']]}" for finding in record["beside"]],
            "reviewed": None if record["reviewed"] else NOT_REVIEWED}
