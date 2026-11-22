"""Plan AN.67 (D315, D323; owner, 19 and 22 Nov 2026): drafting on request - a document written part by part from a versioned
template, on the shared loop runner (rounds.py, D322), not as an open-ended agent.

The template is the plan: its parts, in order, each with what it is for and the particulars it states, and the law it rests on.
The writer drafts every part from the conversation with its papers, the held law the research admitted and the time limits code
worked out; code then checks each part mechanically - every passage it rests on is one NM owns, every particular stands in the very
words of the passage it cites and in the paragraph, every particular is stated or marked as missing, no date is worked out - and a
part at fault is written again on its own, told what was wrong, while the draft's allowance lasts. The rounds end when nothing is
left to correct (rounds.COMPLETE), when a rewrite corrects nothing, at the allowance, or when the writer cannot be asked. A part
still at fault is kept with its faults, for the advocate to see: the draft is for the advocate's review (SEQ.7), never sent by NM.

The saved draft keeps its template, each round's proposal and what code found of it, and the parts as they stand; on reading it is
checked again from those alone (P46). Piece 23a: the writer and code's checks. The independent review (23b), the Word export (23c)
and the request that starts a draft (23d) build on it.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

from nm.core_engine import answer_sources, reasoning, response_writer
from nm.core_engine import rounds as runner
from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, canonical_schema_data, require_schema

CONTRACT = "core_draft_v1"
OPERATION = "core_draft_writer"
#: The rewrites a draft may make of its parts at fault, as an answer's section may (calls.SECTION_ALLOWANCE, P25).
REWRITES = 2
#: Where a particular not given would go, as the writer marks it: [[its id]].
_MARK = re.compile(r"\[\[([a-z0-9_]+)\]\]")
#: The draft's status until the advocate has reviewed it (SEQ.7).
FOR_REVIEW = "for_advocate_review"

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

WRITER = """You are an Indian advocate's junior, drafting a document for the advocate to review before it goes out. You receive the document to be drafted, set out as its parts - what each part is for and the particulars it states - the conversation with the advocate (their messages and the papers they sent, each passage under its ID), the held law our research admitted, each passage under its ID, and the time limits code worked out from the Act and the papers.

Purpose: a draft the advocate can send after their own review: each part doing what it is for, in the plain, formal language of such a document, every fact in it the papers' or the advocate's own and every provision the held law's.

Outcome: each part, in the order given, as its paragraphs. For each paragraph give the IDs of the passages it rests on. For each particular it states, give the particular's words exactly as the papers or the advocate's messages write them, and the ID of the passage they stand in, and write those words into the paragraph as they stand. Where a particular is given nowhere, do not supply it: write [[its id]] where it would go and list its id under missing. Give a date only as the papers, the advocate or the time limits give it; work none out. Where you are shown faults found in an earlier draft of a part, write that part again so that none of them remains.

Work in a loop: draft each part, check each particular and each date against the passage you cite, correct what does not stand there, then give the whole."""

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


def _material(template, context, sources, time_limits, asked, earlier):
    """What the writer reads, and how much of it every round of the draft sends alike: the conversation, the held law by their
    offered IDs and the time limits first, so that a rewrite reads them from the provider's cache; then the parts asked for, and
    for a rewrite the earlier draft of each with the faults code found in it."""
    shared = {"original_context": answer_sources.shown_context(context, sources),
              "held_law": answer_sources.presentation(sources, aliased=True, compact=True),
              "time_limits": time_limits or []}
    payload = {**shared,
               "document": {"title": template["title"], "law": template["law"],
                            "parts": [{"part_id": part["id"], "title": part["title"], "for": part["for"],
                                       "particulars": [{"id": item["id"], "is": item["said"]} for item in part["particulars"]]}
                                      for part in template["parts"] if part["id"] in asked]},
               **({"earlier_draft": [{"part_id": part_id, "paragraphs": earlier[part_id]["paragraphs"],
                                      "faults": earlier[part_id]["faults"]} for part_id in asked]} if earlier else {})}
    user = json.dumps(payload, ensure_ascii=False, default=str)
    return user, len(json.dumps(shared, ensure_ascii=False, default=str)) - 1


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


def _asked(template, draft):
    """The parts a round asks for: every part first, then those still at fault, in the template's order."""
    if draft is None:
        return [part["id"] for part in template["parts"]]
    return [part["id"] for part in template["parts"] if draft[part["id"]]["faults"]]


def _drafted(draft, proposal, faults):
    """The draft after a round: each part the round asked for as it now stands - its paragraphs as given (the last given, where a
    part was not given once) with what code found in them."""
    draft = deepcopy(draft) if draft is not None else {}
    given = {item["part_id"]: item["paragraphs"] for item in proposal["parts"]}
    for part_id, found in faults.items():
        before = draft.get(part_id, {"paragraphs": []})["paragraphs"]
        once = [item["part_id"] for item in proposal["parts"]].count(part_id) == 1
        draft[part_id] = {"paragraphs": deepcopy(given[part_id]) if once else before, "faults": list(found)}
    return draft


def _call(model, template, context, sources, time_limits, asked, earlier):
    """One round's writing: the whole draft first, at the writer's level; a rewrite of the parts at fault at a repair's (reasoning.py)."""
    user, shared = _material(template, context, sources, time_limits, asked, earlier)
    prompt = Prompt(system=WRITER, user=user, operation=OPERATION, cache_through=shared,
                    effort=reasoning.effort("repair" if earlier else "write"))
    writes = reasoning.room(model, Tier.HARD, WRITER, user, json.dumps(SCHEMA))
    receipt = model.structured(prompt, SCHEMA, Tier.HARD, max_tokens=writes)
    if not receipt.usable or receipt.data is None:
        raise ModelError("The draft could not be written", usage=receipt.usage, latency_ms=receipt.latency_ms,
                         retries=receipt.retries)
    proposal = canonical_schema_data(receipt.data, SCHEMA)
    require_schema(proposal, SCHEMA)
    return proposal


def write(model, template, context, sources, *, time_limits=None):
    """A draft of template for the matter (D323), as saved: {"contract", "template", "rounds": [{"asked", "proposal", "faults"}],
    "stopped", "parts": [{"part_id", "paragraphs", "faults"}], "state"}. The first round writes every part; each later round,
    within REWRITES, writes again only the parts code found at fault, told what was wrong. A writer that cannot be asked for a
    rewrite leaves the draft as the rounds before left it, said why; one that cannot be asked for the first is ModelError: there
    is no draft. template is one the caller chose from TEMPLATES; validate reads a draft only of a template NM holds."""
    check_template(template)
    state = {"draft": None, "rewrites": 0}

    def ask(done):
        draft = done[-1]["outcome"] if done else None
        return {"asked": _asked(template, draft), "proposal": _call(model, template, context, sources, time_limits,
                                                                     _asked(template, draft), draft)}

    def admit(proposal, done):
        return {"asked": proposal["asked"], "proposal": proposal["proposal"],
                "faults": _faults(proposal["proposal"], template, proposal["asked"], context, sources, time_limits)}, None

    def carry_out(actions, done):
        return _drafted(done[-1]["outcome"] if done else None, actions["proposal"], actions["faults"])

    def progressed(outcome, done):
        before = done[-1]["outcome"] if done else None
        return before is None or outcome != before

    def spend():
        # The first round is the draft itself; each later round is one of its rewrites.
        if state["draft"] is not None:
            if state["rewrites"] >= REWRITES:
                raise runner.Backstop("The draft's rewrites are used")
            state["rewrites"] += 1
        state["draft"] = True
    done, stopped = runner.run(ask, admit, carry_out, progressed, spend=spend, unavailable=(ModelError, SchemaViolation),
                               finished=lambda outcome, done: not any(part["faults"] for part in outcome.values()))
    if not done:
        raise ModelError("The draft could not be written")
    return _record(template, [{"asked": entry["actions"]["asked"], "proposal": entry["actions"]["proposal"],
                               "faults": entry["actions"]["faults"]} for entry in done], stopped)


def _record(template, kept, stopped):
    draft = None
    for entry in kept:
        draft = _drafted(draft, entry["proposal"], entry["faults"])
    parts = [{"part_id": part["id"], **deepcopy((draft or {}).get(part["id"], {"paragraphs": [], "faults": []}))}
             for part in template["parts"]]
    return {"contract": CONTRACT, "template": deepcopy(template), "rounds": kept, "stopped": stopped, "parts": parts,
            "state": FOR_REVIEW}


def validate(record, context, sources, *, time_limits=None, templates=None):
    """A saved draft checked again from what it kept (P46): its template one NM holds, each round asked for what the draft before
    it left at fault and found at fault what code finds in its proposal now, no more rewrites than REWRITES, the parts as the
    rounds leave them and the stop as they ended. Returns the record."""
    held = TEMPLATES if templates is None else templates
    if (not isinstance(record, dict) or set(record) != {"contract", "template", "rounds", "stopped", "parts", "state"}
            or record["contract"] != CONTRACT or record["state"] != FOR_REVIEW):
        raise ValueError("A saved draft is not one this code reads")
    template = check_template(record["template"])
    if held.get((template["id"], template["version"])) != template:
        raise ValueError("A saved draft's template is not one NM holds")
    stopped, rounds = record["stopped"], record["rounds"]
    if (not isinstance(stopped, dict) or set(stopped) != {"why", "reason"} or stopped["why"] not in runner.STOPS
            or not isinstance(rounds, list) or not rounds or len(rounds) > 1 + REWRITES):
        raise ValueError("A saved draft does not say how its rounds ended")
    draft, ended = None, None
    for entry in rounds:
        if ended is not None:
            raise ValueError("A draft's rounds end when nothing is left to correct, or a rewrite corrects nothing")
        if not isinstance(entry, dict) or set(entry) != {"asked", "proposal", "faults"}:
            raise ValueError("A round of a draft keeps what it asked for, what came back and what code found")
        try:
            proposal = canonical_schema_data(entry["proposal"], SCHEMA)
            require_schema(proposal, SCHEMA)
        except SchemaViolation:
            raise ValueError("A round of a draft keeps a proposal the writer's form does not hold") from None
        if (proposal != entry["proposal"] or entry["asked"] != _asked(template, draft)
                or entry["faults"] != _faults(proposal, template, entry["asked"], context, sources, time_limits)):
            raise ValueError("A round of a draft differs from what code finds of it")
        after = _drafted(draft, proposal, entry["faults"])
        if not any(part["faults"] for part in after.values()):
            ended = runner.COMPLETE
        elif draft is not None and after == draft:
            ended = runner.NOTHING_NEW
        draft = after
    # How the rounds ended: as the last round left the draft; otherwise at the allowance, after every rewrite it gives, or at a
    # writer that could not be asked for the next rewrite.
    if ended is not None:
        expected = stopped == {"why": ended, "reason": None}
    elif stopped["why"] == runner.BACKSTOP:
        expected = len(rounds) == 1 + REWRITES and bool(stopped["reason"])
    else:
        expected = stopped["why"] == runner.UNAVAILABLE and bool(stopped["reason"])
    if not expected:
        raise ValueError("A saved draft does not end as its rounds do")
    if record != _record(template, rounds, stopped):
        raise ValueError("A saved draft's parts are not as its rounds leave them")
    return record


def shown(record):
    """The draft as the advocate reads it: each part's title and paragraphs, a particular not given written where it goes as
    [particular needed: what it is], and the faults code still finds in a part."""
    template = record["template"]
    said = {item["id"]: item["said"] for part in template["parts"] for item in part["particulars"]}
    titles = {part["id"]: part["title"] for part in template["parts"]}
    return {"title": template["title"], "state": record["state"],
            "parts": [{"part_id": part["part_id"], "title": titles[part["part_id"]],
                       "paragraphs": [_MARK.sub(lambda match: f"[particular needed: {said.get(match.group(1), match.group(1))}]",
                                                paragraph["text"]) for paragraph in part["paragraphs"]],
                       "faults": list(part["faults"])} for part in record["parts"]]}
