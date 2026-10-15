"""Understand the matter, phrase its legal questions, search held law and pick what answers.

v7 is a reasoning loop, never one shot (owner standing instruction, 13 Oct 2026): the
model sets out the matter, code checks it mechanically, the model reviews it against
the conversation and corrects it (at most MAX_REVISIONS times); search phrases are
written per dispute in parallel beside one judgment-phrase call; each legal question is
searched with every phrase and its named Acts; the model picks the provisions that
answer each question and, from v8, the judgment paragraphs. Earlier plans replay unchanged.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from nm.core_engine.retrieval import SearchUnavailable, validate_search
from nm.core_engine.understanding import REFERENCE, TEXT, select, source_catalogue
from nm.shared.model_port import (
    ModelError, Prompt, SchemaViolation, Tier, canonical_schema_data, require_schema,
)

LEGACY_CONTRACT = "core_research_v2"
PREVIOUS_CONTRACT = "core_research_v3"
WINDOWED_CONTRACT = "core_research_v4"
ACCOUNT_CONTRACT = "core_research_v5"
#: v6 (owner decision, 12 Oct 2026): each investigation states the legal relationship,
#: roles and questions, phrases its enquiries in statute vocabulary with one rule probe,
#: and names the Acts that may govern; search looks inside those held Acts too.
INSTRUMENTED_CONTRACT = "core_research_v6"
#: v7 (owner decisions, 13-14 Oct 2026): the loop above; one work item per legal question.
PICKED_CONTRACT = "core_research_v7"
#: v8 (owner decision, 15 Oct 2026): beside the provision pick, the model picks for each
#: question the judgment paragraphs a lawyer would rely on, only among the six the search
#: returns. The answer reads the picked paragraphs with their neighbours and every other
#: returned paragraph alone: a paragraph-level pick dropped 4 of 16 key judgments
#: (measured 15 Oct), so it focuses the reading and never removes a returned judgment.
CONTRACT = "core_research_v8"
_QUESTION_PLANS = (PICKED_CONTRACT, CONTRACT)
CONTRACTS = (LEGACY_CONTRACT, PREVIOUS_CONTRACT, WINDOWED_CONTRACT, ACCOUNT_CONTRACT,
             INSTRUMENTED_CONTRACT, PICKED_CONTRACT, CONTRACT)
MAX_REVISIONS = 2
#: The pick chooses from each question's first PROVISIONS_FOR_PICK provisions.
PROVISIONS_FOR_PICK = 20
#: Answer limits per step. Calls in flight are budgeted at their limit.
MAX_OUTPUT = {"understand": 12000, "check": 6000, "revise": 12000, "phrases": 6000,
              "judgment_phrases": 8000, "pick": 8000, "judgment_pick": 8000}

# The prompts below were developed and measured in outputs/decomposition-scratch
# (13-14 Oct 2026). They state the purpose and the needed outcome in plain language
# and leave understanding to the model; code makes the mechanical checks afterwards.
UNDERSTAND = """You are a senior Indian litigation lawyer working with a colleague, the advocate, who practises in Telangana. You receive the conversation so far: the advocate's messages and any earlier notes from our research assistant. The last message is the one we are acting on now.

Advocates bring matters to us so that we can find the law that governs them. Your job in this step is to understand the matter well enough that the right law can be researched. You are not answering the legal questions yet. Read the whole conversation, think about what has happened, who is involved, what the advocate wants now and why, and then set out your understanding.

What we need from you:

- What the advocate wants from us now. Often they say so. When they only tell us what has happened, they want to know where the law stands on those events: the legal questions a lawyer would need answered to advise on them. Also note anything they have told us not to do (for example to pause research, not to contact anyone, not to assume a disputed event).
- The people involved and their roles.
- The facts, each kept exactly as certain as the advocate put it: confirmed, reported by someone, uncertain, or disputed. Give the advocate's own words for each fact. What the advocate reports is their account, not proven fact, and we never add facts they did not give.
- The separate disputes. A dispute is one set of events between particular parties that needs its own legal answer. Events that call for different kinds of law, such as a civil wrong and a crime, or that concern different transactions, are separate disputes, even when they happen together or involve the same people.
- For each dispute, think through every legal consequence the events may have, civil, criminal and under any special statute, and for each: the right or liability, the remedy, how and where it is pursued and within what time, and, where the case turns on particular evidence, how that evidence is proved. Ask as legal questions those that bear on what the advocate wants; put the rest in related points.
- For each dispute, the legal questions we must research to do what the advocate wants. A legal question is about one legal point: a right, an obligation, a remedy, a defence, a procedure, a time limit, a presumption or an offence. If answering it would need two different rules, such as what a right is and how it is enforced, it is two questions. Write each so that a lawyer could answer it from one or two provisions of law, and say briefly why we need it. Where the facts leave open something that changes the governing law (for example when the events happened, or which personal law applies), say what is open.
- For each legal question, the law you would check first: the Indian Acts, and sections if you know them, that you believe govern it. This is your recollection to guide the search; it will be checked against the statutes we hold, so say only what you believe and do not guess.
- For each dispute, the rights that may be at stake, the relief or outcome being sought, and the facts we would still need.
- Related points: things the advocate did not ask about but a careful lawyer would want them to know, such as a presumption that helps, a time limit that may be running, or an alternative remedy, with why each matters. We will tell the advocate about these and let them decide; we do not research them now.

Some messages need no legal research: thanks or social messages, an instruction to keep research paused, a request to transcribe or tidy text. In that case say so and why, and leave the research questions empty; you may still record the disputes already known from the conversation.
"""
CHECK = """You are a senior Indian litigation lawyer reviewing a colleague's understanding of a matter before any research starts. You receive the conversation with the advocate and your colleague's written understanding of it.

Check the understanding carefully against the conversation itself, the way you would before letting a junior start research:

- Has anything the advocate asked for, reported or ruled out been missed or misread?
- Are separate disputes kept apart (events that call for different kinds of law, or that concern different transactions), and is anything that belongs together split up?
- Does each legal question ask about one legal point, or would answering it need two different rules? Taken together, would the questions let us do what the advocate asked? Are any of them duplicates, or so general that no particular law answers them?
- Have the events' other legal consequences (civil, criminal, under a special statute), and how each is pursued and proved, been considered, and asked where they bear on what the advocate wants?
- Is any fact stated more strongly than the advocate put it, or added?
- Are the related points genuinely useful to the advocate, and kept separate from what we research now?
- Is research being started when the advocate has ruled it out, or skipped when it is needed? When the advocate only tells us what has happened, they want to know where the law stands on those events.

Report only problems that matter: ones that would change what we research, or would leave us misunderstanding the matter or the advocate's instructions. Small differences of wording or emphasis do not matter. Give each real problem precisely, with what should change. If the understanding is sound, say so plainly. Do not invent problems to have something to say.
"""
REVISE = """You are a senior Indian litigation lawyer. You wrote an understanding of a matter, and a reviewing colleague (and our mechanical checks) found problems with it. You receive the conversation, your understanding and the problems.

Think about each problem against the conversation. Correct what is genuinely wrong and keep everything that was right. If you believe a reported problem is mistaken, keep your original and explain why in your notes. Then give the complete corrected understanding.
"""
PHRASES = """You are a senior Indian litigation lawyer about to search a library of Indian statutes, central Acts and Telangana State Acts, for the provisions that answer a set of legal questions. You receive the matter as a colleague has understood it: its disputes and, for each, the legal questions with the law your colleague would check first.

Statutes rarely use everyday words. They use terms of art and frame rules in their own way, so a search in plain English often misses the provision that answers the question. Use your knowledge of Indian law to write, for each legal question, the language the statutes themselves are likely to use:

- Heading terms: the words a section heading for this rule would use, for example "compensation for loss of goods in transit" rather than "the courier lost my parcel".
- Alternative terms: other terms of art the law uses for the same idea, such as the term another Act uses, the term of an older or newer enactment on the subject, or the closely related concept a lawyer would also look under.
- A rule statement: one sentence framing the governing rule the way a provision would, in your own words. Do not try to recite a section from memory; this is only a search probe, and the actual words will be read from the statutes we hold.

For each question give two or three search phrases in all, choosing the kinds that will best find the governing provision. Keep heading and alternative terms to a few words each, and the rule statement to one sentence.

Also name the Acts to search in: the Indian Acts you believe govern the question, by short title and year. When the date of the events decides which law applies, include both the Act in force then and the Act that replaced it or that it replaced.
"""
JUDGMENT_PHRASES = """You are a senior Indian litigation lawyer about to search a library of Indian judgments, the Supreme Court of India and the High Court of Andhra Pradesh, for the authorities that answer a set of legal questions. You receive the matter as a colleague has understood it: its disputes and, for each, the legal questions, with the law your colleague would check first.

Judgments do not read like statutes. Courts frame the point in issue in their own way, name doctrines and tests, discuss the provision by its section number and Act, and state the principle they decide in a sentence of their own. A search phrased in the words of the statute mostly finds paragraphs that merely quote it. Use your knowledge of how Indian courts write to give, for each legal question, the language a judgment deciding it is likely to use:

- The issue as a court frames it, for example "whether a writ petition lies against a private body discharging a public function".
- The holding: one sentence stating the principle the way a court would hold it, in your own words. Do not try to recite a judgment from memory; this is only a search probe, and the actual words will be read from the judgments we hold.
- The doctrine or test: the name courts give the principle, such as "promissory estoppel" or "constructive res judicata", tied to the provision where courts usually discuss it that way.

For each question give two or three search phrases in all, choosing the kinds that will best find a judgment that decides the point.
"""
PICK = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for each question a search of the statutes we hold has returned up to twenty provisions, each shown with its Act, section, heading and opening words.

For each question, choose the provisions a lawyer must read to answer it: the ones that state the governing rule, right, liability, remedy, procedure, time limit, presumption or offence the question asks about. Most questions are answered by one to three provisions; choose more only when each one is needed. Put the most necessary first.

Judge each provision by what it actually says, not by whether it shares words with the question. If no shown provision answers a question, choose none for it and say what is missing.
"""
JUDGMENT_PICK = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for each question a search of the judgments we hold, the Supreme Court of India and the High Court of Andhra Pradesh, has returned up to six paragraphs, each shown with its judgment, court, year, how many later judgments cite it, and the paragraph's words.

For each question, choose the paragraphs a lawyer would rely on to answer it: those where a court decides or authoritatively explains the point the question asks about. Most questions need one to three; choose more only when each adds something, and put the most useful first.

Judge each paragraph by what the court is doing in it. A paragraph that only quotes the statute, recites the facts of that case or reports a party's argument is rarely what a lawyer cites, unless the court adopts it as its own view. Weigh the court and the judgment's standing as a lawyer would, without passing over a recent judgment merely because few have cited it yet. If no shown paragraph answers a question, choose none for it and say what is missing.
"""


def _object(fields):
    return {"type": "object", "additionalProperties": False,
            "required": list(fields), "properties": fields}


# v7 fields are plain strings, as measured: some are legitimately empty
# (no_research_reason when research is needed, open_alternative when nothing is open).
STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}
ENQUIRY = _object({"text": TEXT, "purpose": TEXT,
                   "basis": {"type": "string", "enum": ["reported", "conditional"]}})
LEGACY_WORK = _object({
    "purpose": TEXT, "outcome": TEXT,
    "sources": {"type": "array", "minItems": 1, "items": REFERENCE},
    "constraints": {"type": "array", "items": TEXT},
    "unresolved": {"type": "array", "items": TEXT},
    "enquiries": {"type": "array", "items": ENQUIRY},
})
WORK = _object({
    "sources": LEGACY_WORK["properties"]["sources"],
    "search_account": {"type": "array", "items": REFERENCE},
    "enquiries": {"type": "array", "maxItems": 3, "items": ENQUIRY},
})
PREVIOUS_WORK = _object({**LEGACY_WORK["properties"],
    "search_account": {"type": "array", "items": REFERENCE},
    "enquiries": {"type": "array", "maxItems": 3, "items": ENQUIRY},
})
INSTRUMENTED_WORK = _object({
    "sources": WORK["properties"]["sources"],
    "search_account": WORK["properties"]["search_account"],
    "relationship": TEXT,
    "roles": {"type": "array", "items": TEXT},
    "legal_questions": {"type": "array", "maxItems": 3, "items": TEXT},
    "enquiries": {"type": "array", "maxItems": 6, "items": ENQUIRY},
    "rule_probe": TEXT,
    "instruments": {"type": "array", "maxItems": 6, "items": TEXT},
})
ACCOUNT_SCHEMA = _object({"work": {"type": "array", "items": WORK}})
INSTRUMENTED_SCHEMA = _object({"work": {"type": "array", "items": INSTRUMENTED_WORK}})
LEGACY_SCHEMA = _object({"work": {"type": "array", "items": LEGACY_WORK}})
PREVIOUS_SCHEMA = _object({"work": {"type": "array", "items": PREVIOUS_WORK}})

UNDERSTANDING = _object({
    "summary": STRING,
    "asked": STRINGS,
    "ruled_out": STRINGS,
    "needs_research": {"type": "boolean"},
    "no_research_reason": STRING,
    "parties": {"type": "array", "items": _object({"who": STRING, "role": STRING})},
    "facts": {"type": "array", "items": _object({
        "id": STRING, "fact": STRING, "advocate_words": STRING,
        "certainty": {"type": "string", "enum": ["confirmed", "reported", "uncertain", "disputed"]}})},
    "disputes": {"type": "array", "items": _object({
        "id": STRING, "name": STRING, "between": STRINGS, "fact_ids": STRINGS,
        "legal_questions": {"type": "array", "items": _object({
            "id": STRING, "question": STRING, "why_needed": STRING, "open_alternative": STRING, "law_to_check": STRINGS})},
        "rights_at_stake": STRINGS, "relief_sought": STRINGS, "missing_facts": STRINGS})},
    "related_points": {"type": "array", "items": _object({"point": STRING, "why_it_matters": STRING, "dispute_id": STRING})},
})
PROBLEM = _object({"problem": STRING, "fix": STRING})
CHECKED = _object({"verdict": {"type": "string", "enum": ["sound", "revise"]},
                   "problems": {"type": "array", "items": PROBLEM}})
REVISED = _object({"notes": STRING, "understanding": UNDERSTANDING})


def _phrase(kinds):
    return _object({"kind": {"type": "string", "enum": list(kinds)}, "text": STRING})


STATUTE_PHRASES = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "phrases": {"type": "array", "items": _phrase(("heading", "alternative", "rule"))},
    "acts": STRINGS})}})
JUDGMENT_PHRASE_SCHEMA = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "phrases": {"type": "array", "items": _phrase(("issue", "holding", "doctrine"))}})}})
CHOICE = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "chosen": STRINGS, "note": STRING})}})
FAILURE = _object({"step": STRING, "scope": STRING, "reason": STRING})
SCHEMA = _object({
    "understanding": UNDERSTANDING,
    "review_rounds": {"type": "array", "items": _object({
        "code_problems": {"type": "array", "items": PROBLEM},
        "verdict": {"type": "string", "enum": ["sound", "revise", "unavailable"]},
        "problems": {"type": "array", "items": PROBLEM}})},
    "statute_phrases": {"type": "array", "items": _object({
        "dispute_id": STRING, "questions": STATUTE_PHRASES["properties"]["questions"]})},
    "judgment_phrases": JUDGMENT_PHRASE_SCHEMA["properties"]["questions"],
    "failures": {"type": "array", "items": FAILURE},
})


def _source_windows(context):
    """Offer exact mechanical windows; only the model decides their relevance."""
    catalogue = source_catalogue(context)
    offsets, offered = {}, []
    for source in list(catalogue.values()):
        if source.get("speaker") != "advocate" or source.get("record_role") != "original_account":
            continue
        for number, match in enumerate(re.finditer(r".+?(?:[.!?](?=\s|$)|\n+|$)", source["text"], re.S), 1):
            if not match.group().strip():
                continue
            identity = f"{source['source_id']}::passage:{number}"
            if identity in catalogue:
                raise ValueError("Original passage identity collides with an existing source")
            catalogue[identity] = {**source, "text": match.group()}
            offsets[identity] = match.start()
            offered.append({"source_id": identity, "original_source_id": source["source_id"],
                            "text": match.group()})
    return catalogue, offsets, offered


def _select(reference, catalogue, offsets):
    selected = select(reference, catalogue)
    offset = offsets.get(reference["source_id"], 0)
    selected["start"] += offset
    selected["end"] += offset
    return selected


# --- v7: the conversation as the model reads it, and mechanical checks -------------

def conversation_text(context):
    """The advocate's words and our earlier notes, attributed, oldest first."""
    earlier = [row for row in context["conversation"]
               if row.get("record_role") in ("original_account", "nm_interpretation")]
    lines = ["Conversation so far (oldest first):"] if earlier else []
    for number, row in enumerate(earlier, 1):
        who = ("Advocate" if row["record_role"] == "original_account"
               else "Our research assistant (an earlier note, not the advocate's words)")
        lines.append(f"[{number}] {who}: {row['text']}")
    lines += ["", "Latest message from the advocate (the one we act on now):", context["latest"]["text"]]
    if context.get("current_records"):
        lines += ["", "Current records of this matter: "
                  + json.dumps(context["current_records"], ensure_ascii=False)]
    return "\n".join(lines).strip()


def _plain(text):
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split()).casefold()


def _quoted_fragments(quote):
    """The pieces of a quotation that must appear word for word: typographic quotes,
    a leading turn marker such as "[1]" and edge punctuation are not the advocate's
    words, and an ellipsis joins separately quoted pieces."""
    text = re.sub(r"^\s*\[\d+\]\s*", "", _plain(quote))
    inline = re.findall(r'"([^"]+)"', text)
    pieces = [p for part in (inline or [text]) for p in re.split(r"\.\.\.|…", part)]
    return [p.strip(" .,;:\"'") for p in pieces if p.strip(" .,;:\"'")]


def code_checks(understanding, context):
    """Mechanical checks only; meaning is the model's work."""
    problems = []
    advocate = _plain(" ".join([row["text"] for row in context["conversation"]
                                if row.get("record_role") == "original_account"] + [context["latest"]["text"]]))
    facts = {f["id"] for f in understanding["facts"]}
    if len(facts) != len(understanding["facts"]):
        problems.append({"problem": "Two facts share an id.", "fix": "Give each fact its own id."})
    for fact in understanding["facts"]:
        if any(piece not in advocate for piece in _quoted_fragments(fact["advocate_words"])):
            problems.append({"problem": f"Fact {fact['id']}: the quoted advocate words do not appear in the "
                                        f"advocate's messages ({fact['advocate_words']!r}).",
                             "fix": "Quote the advocate's exact words for this fact, or remove the fact if they did not say it."})
    disputes = {d["id"] for d in understanding["disputes"]}
    if len(disputes) != len(understanding["disputes"]):
        problems.append({"problem": "Two disputes share an id.", "fix": "Give each dispute its own id."})
    questions = [q["id"] for d in understanding["disputes"] for q in d["legal_questions"]]
    if len(set(questions)) != len(questions):
        problems.append({"problem": "Two legal questions share an id.", "fix": "Give each legal question its own id."})
    for dispute in understanding["disputes"]:
        missing = [f for f in dispute["fact_ids"] if f not in facts]
        if missing:
            problems.append({"problem": f"Dispute {dispute['id']} refers to facts that do not exist: {missing}.",
                             "fix": "Refer only to listed facts."})
    for point in understanding["related_points"]:
        if point["dispute_id"] and point["dispute_id"] not in disputes:
            problems.append({"problem": f"A related point refers to an unknown dispute {point['dispute_id']!r}.",
                             "fix": "Refer to a listed dispute, or leave it empty for the matter as a whole."})
    if not understanding["needs_research"] and questions:
        problems.append({"problem": "Research is marked as not needed, yet legal questions are listed for research.",
                         "fix": "Either research is needed (say so) or the questions belong with the known disputes for later."})
    return problems


def _matter_text(understanding, disputes):
    lines = [f"Matter: {understanding['summary']}", "Asked: " + "; ".join(understanding["asked"])]
    for dispute in disputes:
        lines.append(f"\nDispute {dispute['id']}: {dispute['name']} (between {', '.join(dispute['between'])})")
        for q in dispute["legal_questions"]:
            law = "; ".join(q["law_to_check"]) or "none named"
            lines.append(f"- {q['id']}: {q['question']} [law your colleague would check first: {law}]")
    return "\n".join(lines)


def _call(model, operation, system, user, schema, step):
    receipt = model.structured(Prompt(system=system, user=user, operation=operation),
                               schema, Tier.ROUTINE, max_tokens=MAX_OUTPUT[step])
    if not receipt.usable or receipt.data is None:
        raise ModelError(f"Research step {step} did not complete", usage=receipt.usage,
                         latency_ms=receipt.latency_ms, retries=receipt.retries)
    return canonical_schema_data(receipt.data, schema)


#: Recorded when the loop is not run: a courtesy, a restriction alone, or thanks needs no law.
NO_NEW_MATTER = "The interpretation found no new information or request in the latest message."


def _carries_matter(interpretation):
    """Whether the interpretation step found information or a request; an unchecked or
    partial interpretation is never taken as proof that nothing needs research."""
    if (not isinstance(interpretation, dict) or interpretation.get("issues")
            or not isinstance(interpretation.get("units"), list) or not interpretation["units"]):
        return True
    return any(unit.get("kind") in ("information", "request") for unit in interpretation["units"])


def plan(model, context, interpretation=None, *, progress=None):
    """The v7 reasoning loop. Expected model failures after the first understanding are
    recorded where they occur; independent work continues. The loop reads the
    conversation itself; the interpretation only spares it for a message that carries
    no information or request."""
    if interpretation is not None and not _carries_matter(interpretation):
        return accept({"understanding": {"summary": "", "asked": [], "ruled_out": [], "needs_research": False,
                                         "no_research_reason": NO_NEW_MATTER, "parties": [], "facts": [],
                                         "disputes": [], "related_points": []},
                       "review_rounds": [], "statute_phrases": [], "judgment_phrases": [], "failures": []}, context)
    report = progress or (lambda stage, **detail: None)
    text = conversation_text(context)
    report("understanding_matter")
    understanding = _call(model, "core_research_understand", UNDERSTAND, text, UNDERSTANDING, "understand")
    rounds, failures = [], []
    for number in range(MAX_REVISIONS + 1):
        mechanical = code_checks(understanding, context)
        report("checking_understanding", round=number + 1)
        try:
            review = _call(model, "core_research_check", CHECK, text + "\n\nYour colleague's understanding:\n"
                           + json.dumps(understanding, ensure_ascii=False, indent=1), CHECKED, "check")
        except (ModelError, SchemaViolation) as exc:
            rounds.append({"code_problems": mechanical, "verdict": "unavailable", "problems": []})
            failures.append({"step": "check", "scope": f"round {number + 1}", "reason": type(exc).__name__})
            break
        rounds.append({"code_problems": mechanical, **review})
        problems = mechanical + (review["problems"] if review["verdict"] == "revise" else [])
        if not problems or number == MAX_REVISIONS:
            break
        report("revising_understanding", round=number + 1)
        try:
            revised = _call(model, "core_research_revise", REVISE, text + "\n\nYour understanding:\n"
                            + json.dumps(understanding, ensure_ascii=False, indent=1)
                            + "\n\nProblems found:\n" + json.dumps(problems, ensure_ascii=False, indent=1),
                            REVISED, "revise")
        except (ModelError, SchemaViolation) as exc:
            failures.append({"step": "revise", "scope": f"round {number + 1}", "reason": type(exc).__name__})
            break
        understanding = revised["understanding"]
    statute, judgment = [], []
    disputes = [d for d in understanding["disputes"] if d["legal_questions"]]
    if understanding["needs_research"] and disputes:
        report("writing_search_terms", total=sum(len(d["legal_questions"]) for d in disputes))
        tasks = [("statute", dispute) for dispute in disputes] + [("judgment", None)]

        def phrase(task):
            kind, dispute = task
            try:
                if kind == "statute":
                    return task, _call(model, "core_research_phrases", PHRASES,
                                       _matter_text(understanding, [dispute]), STATUTE_PHRASES, "phrases"), None
                return task, _call(model, "core_research_judgment_phrases", JUDGMENT_PHRASES,
                                   _matter_text(understanding, disputes), JUDGMENT_PHRASE_SCHEMA, "judgment_phrases"), None
            except (ModelError, SchemaViolation) as exc:
                return task, None, type(exc).__name__

        # Owner decision, 14 Oct 2026: one statute-phrase call per dispute, all at once,
        # beside one judgment-phrase call for the matter (measured 61% faster, no loss).
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
            for (kind, dispute), data, error in pool.map(phrase, tasks):
                if error:
                    failures.append({"step": f"{kind}_phrases", "scope": dispute["id"] if dispute else "matter",
                                     "reason": error})
                elif kind == "statute":
                    statute.append({"dispute_id": dispute["id"], "questions": data["questions"]})
                else:
                    judgment = data["questions"]
    return accept({"understanding": understanding, "review_rounds": rounds, "statute_phrases": statute,
                   "judgment_phrases": judgment, "failures": failures}, context)


def _accept_v7(proposal, context):
    data = canonical_schema_data(proposal, SCHEMA)
    require_schema(data, SCHEMA)
    catalogue = source_catalogue(context)
    latest = select({"source_id": context["latest"]["source_id"], "quote": None}, catalogue)
    understanding, issues = data["understanding"], []
    for failure in data["failures"]:
        issues.append({"work_id": None, "mismatch": f"{failure['step']} unavailable for {failure['scope']}: "
                                                    f"{failure['reason']}", "proposal": deepcopy(failure)})
    rounds = data["review_rounds"]
    if rounds and (rounds[-1]["code_problems"] or rounds[-1]["verdict"] == "revise"):
        issues.append({"work_id": None, "mismatch": "The understanding kept open problems after review",
                       "proposal": deepcopy(rounds[-1])})
    questions = {q["id"]: (dispute, q) for dispute in understanding["disputes"] for q in dispute["legal_questions"]}
    statute, judgment = {}, {}
    for entry in data["statute_phrases"]:
        for item in entry["questions"]:
            owner = questions.get(item["question_id"])
            if owner is None or owner[0]["id"] != entry["dispute_id"] or item["question_id"] in statute:
                issues.append({"work_id": None, "mismatch": "Statute phrases name no question of their dispute",
                               "proposal": deepcopy(item)})
                continue
            statute[item["question_id"]] = item
    for item in data["judgment_phrases"]:
        if item["question_id"] not in questions or item["question_id"] in judgment:
            issues.append({"work_id": None, "mismatch": "Judgment phrases name no question",
                           "proposal": deepcopy(item)})
            continue
        judgment[item["question_id"]] = item
    work = []
    if understanding["needs_research"]:
        for question_id, (dispute, question) in questions.items():
            texts = [p for p in [*statute.get(question_id, {}).get("phrases", []),
                                 *judgment.get(question_id, {}).get("phrases", [])] if p["text"].strip()]
            texts = list({p["text"].strip(): p for p in texts}.values())
            if not texts:
                issues.append({"work_id": None, "mismatch": f"Legal question {question_id} has no search phrases",
                               "proposal": deepcopy(question)})
                continue
            identity = context["latest"]["turn_id"] + f":w{len(work) + 1}"
            acts = list(dict.fromkeys(" ".join(name.split()) for name in statute.get(question_id, {}).get("acts", [])
                                      if name.strip()))
            work.append({"id": identity, "sources": [deepcopy(latest)], "search_account": [],
                         "dispute": {"id": dispute["id"], "name": dispute["name"], "between": list(dispute["between"])},
                         "question_id": question_id, "question": question["question"],
                         "why_needed": question["why_needed"], "law_to_check": list(question["law_to_check"]),
                         "instruments": acts,
                         "enquiries": [{"text": p["text"].strip(), "purpose": p["kind"], "basis": "conditional",
                                        "query_id": f"{identity}:q{i}"} for i, p in enumerate(texts, 1)]})
    return {"proposal": data, "work": work, "issues": issues, "semantic_review": "pending"}


def accept(proposal, context, *, contract=CONTRACT):
    if contract not in CONTRACTS:
        raise ValueError("Unknown research contract")
    if contract in _QUESTION_PLANS:
        return _accept_v7(proposal, context)
    schema = {LEGACY_CONTRACT: LEGACY_SCHEMA, PREVIOUS_CONTRACT: PREVIOUS_SCHEMA,
              WINDOWED_CONTRACT: ACCOUNT_SCHEMA, ACCOUNT_CONTRACT: ACCOUNT_SCHEMA,
              INSTRUMENTED_CONTRACT: INSTRUMENTED_SCHEMA}[contract]
    work_schema = schema["properties"]["work"]["items"]
    data = canonical_schema_data(proposal, schema)
    require_schema(data, _object({"work": {"type": "array", "items": {}}}))
    if contract in {WINDOWED_CONTRACT, ACCOUNT_CONTRACT, INSTRUMENTED_CONTRACT}:
        catalogue, offsets, _ = _source_windows(context)
    else:
        catalogue, offsets = source_catalogue(context), {}
    work, issues = [], []
    for number, item in enumerate(data["work"], 1):
        identity = context["latest"]["turn_id"] + f":w{number}"
        try:
            require_schema(item, work_schema)
            sources = [_select(ref, catalogue, offsets) for ref in item["sources"]]
            if not any(source["source_id"] == context["latest"]["source_id"] for source in sources):
                raise SchemaViolation("Work must select the current instruction or matter contribution")
            original = {}
            if contract != LEGACY_CONTRACT:
                account = [_select(ref, catalogue, offsets) for ref in item["search_account"]]
                if any(row.get("speaker") != "advocate" or
                       row.get("record_role") != "original_account" for row in account):
                    raise SchemaViolation("Search account must select original advocate words, not NM interpretations")
                order = {source_id: index for index, source_id in enumerate(catalogue)}
                account = list({(s["source_id"], s["start"], s["end"]): s for s in account}.values())
                account.sort(key=lambda s: (order[s["source_id"]], s["start"], s["end"]))
                original = {"search_account": account}
                known = {(s["source_id"], s["start"], s["end"]) for s in sources}
                for source in account:
                    key = source["source_id"], source["start"], source["end"]
                    if key not in known:
                        sources.append(source)
                        known.add(key)
            work.append({**deepcopy(item), **original, "id": identity, "sources": sources,
                         "enquiries": [{**deepcopy(enquiry), "query_id": f"{identity}:q{i}"}
                                       for i, enquiry in enumerate(item["enquiries"], 1)]})
        except SchemaViolation as exc:
            issues.append({"work_id": identity, "mismatch": str(exc), "proposal": deepcopy(item)})
    return {"proposal": deepcopy(data), "work": work, "issues": issues, "semantic_review": "pending"}


def search_queries(work, *, contract=CONTRACT):
    """Versioned exact-query construction; no semantic rewriting or ranking bonus."""
    if contract in _QUESTION_PLANS:
        # v7: every phrase is searched in both libraries; the reranker reads them with
        # the legal question they serve (measured 14 Oct 2026).
        return [{"query_id": enquiry["query_id"], "text": enquiry["text"], "context": work["question"]}
                for enquiry in work["enquiries"]]
    if contract in {PREVIOUS_CONTRACT, WINDOWED_CONTRACT, ACCOUNT_CONTRACT, INSTRUMENTED_CONTRACT}:
        if not work["enquiries"]:
            return []
        # The stored selections retain source/speaker/offsets. The search text
        # contains their words once, followed by distinct discovery concepts.
        # From v5 the advocate's words stand alone: code-authored passage labels
        # became search terms that ranked advocates' own regulation highly.
        passages = work["search_account"]
        if contract in (ACCOUNT_CONTRACT, INSTRUMENTED_CONTRACT) or len(passages) == 1:
            account = "\n\n".join(source["text"] for source in passages)
        else:
            account = "\n\n".join(f"Advocate passage {index}:\n{source['text']}"
                                  for index, source in enumerate(passages, 1))
        queries = ([{"query_id": work["id"] + ":original", "text": account, "context": account}]
                   if account else [])
        queries += [{"query_id": enquiry["query_id"], "text": enquiry["text"],
                     "context": account} for enquiry in work["enquiries"]]
        if contract == INSTRUMENTED_CONTRACT:
            # v6: the rule probe is searched as one more formulation, never shown as law.
            queries.append({"query_id": work["id"] + ":rule", "text": work["rule_probe"], "context": account})
        return queries
    if contract != LEGACY_CONTRACT:
        raise ValueError("Unknown research contract")
    # Saved v2 queries retain their original exact serialization and ordering.
    context = json.dumps({"purpose": work["purpose"], "outcome": work["outcome"],
        "original_sources": work["sources"], "constraints": work["constraints"],
        "unresolved": work["unresolved"], "enquiry_proposals": work["enquiries"]}, ensure_ascii=False)
    return [{"query_id": enquiry["query_id"], "text": enquiry["text"], "context": context}
            for enquiry in work["enquiries"]]


def search_instruments(work, *, contract=CONTRACT):
    """The Acts an investigation names, each once; plans before v6 named none."""
    if contract not in (INSTRUMENTED_CONTRACT, *_QUESTION_PLANS):
        return None
    return list(dict.fromkeys(" ".join(name.split()) for name in work["instruments"] if name.strip()))


# --- v7: the provision pick; v8: the judgment pick -----------------------------------

def _of_kind(search, kind):
    return [c for c in search["candidates"] if c["kind"] == kind]


def _provisions(search):
    return _of_kind(search, "provision")


def _pick_text(plan, searches, labels):
    lines = [f"Matter: {plan['proposal']['understanding']['summary']}"]
    for work in plan["work"]:
        if work["id"] not in searches:
            continue
        label = labels[work["id"]]
        lines.append(f"\n{label}: {work['question']}")
        for number, candidate in enumerate(_provisions(searches[work["id"]]), 1):
            source = candidate["source"]
            body = (source.get("full_text") or "").splitlines()
            opening = re.sub(r"\s+", " ", " ".join(body[1:] or body)).strip()[:220]
            heading = re.sub(r"\s+", " ", source.get("section_title") or "")[:140]
            lines.append(f"  {label}.{number} {candidate['title']}, section {candidate['locator']}: {heading}. {opening}")
    return "\n".join(lines)


def _judgment_pick_text(plan, searches, labels):
    """Each returned paragraph with its judgment, court, year, standing and whole words."""
    lines = [f"Matter: {plan['proposal']['understanding']['summary']}"]
    for work in plan["work"]:
        if work["id"] not in searches:
            continue
        label = labels[work["id"]]
        lines.append(f"\n{label}: {work['question']}")
        for number, candidate in enumerate(_of_kind(searches[work["id"]], "judgment"), 1):
            source = candidate["source"]
            where = ", ".join(str(value) for value in (source.get("court"), source.get("year")) if value)
            cited = source.get("cited_by_count")
            if type(cited) is int:
                where += f", cited by {cited}"
            words = re.sub(r"\s+", " ", source.get("full_text") or "").strip()
            lines.append(f"  {label}.{number} {candidate['title']} ({where}), paragraph {candidate['locator']}: {words}")
    return "\n".join(lines)


#: Each pick's operation, prompt, output step and shown text.
PICKS = {"provision": ("core_research_pick", PICK, "pick", _pick_text),
         "judgment": ("core_research_judgment_pick", JUDGMENT_PICK, "judgment_pick", _judgment_pick_text)}


def _resolve_picks(choice, plan, searches, labels, kind="provision"):
    """Only shown IDs count; the code owns the mapping from a shown ID to a candidate."""
    by_label = {label: work_id for work_id, label in labels.items()}
    chosen, unknown = {work_id: [] for work_id in labels}, []
    for item in choice["questions"]:
        work_id = by_label.get(item["question_id"])
        for shown in dict.fromkeys(item["chosen"]):
            label, _, number = shown.rpartition(".")
            try:
                if work_id is None or label != item["question_id"] or not number.isdigit() or int(number) < 1:
                    raise ValueError
                candidate = _of_kind(searches[work_id], kind)[int(number) - 1]
            except (ValueError, IndexError):
                unknown.append(shown)
                continue
            if candidate["id"] not in chosen[work_id]:
                chosen[work_id].append(candidate["id"])
    return chosen, unknown


def _fallback_picks(searches, labels, kind="provision"):
    """When the pick is unavailable each question keeps the search's own first six."""
    return {work_id: [c["id"] for c in _of_kind(searches[work_id], kind)[:6]] for work_id in labels}


def _labels(plan, searches):
    return {work["id"]: f"Q{number}" for number, work in
            enumerate((w for w in plan["work"] if w["id"] in searches), 1)}


def pick(model, plan, searches, kind="provision"):
    labels = _labels(plan, searches)
    if not any(_of_kind(searches[work_id], kind) for work_id in labels):
        return {"state": "not_needed", "proposal": None, "chosen": {w: [] for w in labels}, "unknown": [],
                "reason": None}
    operation, system, step, text = PICKS[kind]
    try:
        choice = _call(model, operation, system, text(plan, searches, labels), CHOICE, step)
    except (ModelError, SchemaViolation) as exc:
        return {"state": "unavailable", "proposal": None, "chosen": _fallback_picks(searches, labels, kind),
                "unknown": [], "reason": type(exc).__name__}
    chosen, unknown = _resolve_picks(choice, plan, searches, labels, kind)
    return {"state": "evaluated", "proposal": choice, "chosen": chosen, "unknown": unknown, "reason": None}


def _picks_open(picks):
    return any(p["state"] == "unavailable" or p["unknown"] for p in picks)


def retrieve(plan, searcher, context, model=None, *, progress=None):
    """Independent work items retain checked snapshots or explicit read-only gaps; the
    model then picks the provisions and the judgment paragraphs that answer each
    question, both at once (v8)."""
    if accept(plan["proposal"], context) != plan:
        raise ValueError("Research plan differs from its original sources")
    report = progress or (lambda stage, **detail: None)
    record = {"contract": CONTRACT, "plan": deepcopy(plan), "searches": {}, "failures": {}}
    for number, work in enumerate(plan["work"], 1):
        report("searching", done=number - 1, total=len(plan["work"]))
        queries = search_queries(work)
        if not queries:
            continue
        try:
            if searcher is None:
                raise SearchUnavailable("Held-law search is not configured")
            instruments = search_instruments(work)
            record["searches"][work["id"]] = validate_search(
                searcher.search(queries, instruments, results={"provision": PROVISIONS_FOR_PICK}),
                queries, instruments)
        except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            # This independent read-only adapter/snapshot failed. It supplies no
            # admitted evidence; peers remain available and the failure stays explicit.
            record["failures"][work["id"]] = {"stage": "search", "reason": str(exc) or type(exc).__name__}
    kinds = {"provision": "picks", "judgment": "judgment_picks"}
    if model is None:
        labels = _labels(plan, record["searches"])
        for kind, field in kinds.items():
            record[field] = {"state": "unavailable", "proposal": None, "unknown": [], "reason": "No model for the pick",
                             "chosen": _fallback_picks(record["searches"], labels, kind)}
    else:
        if record["searches"]:
            report("choosing_provisions")
        with ThreadPoolExecutor(max_workers=len(kinds)) as pool:
            chosen = dict(zip(kinds, pool.map(lambda kind: pick(model, plan, record["searches"], kind), kinds)))
        for kind, field in kinds.items():
            record[field] = chosen[kind]
    record["state"] = "partial" if (plan["issues"] or record["failures"]
                                    or _picks_open([record[field] for field in kinds.values()]) or any(
        search["state"] == "partial" for search in record["searches"].values())) else "evaluated"
    return record


def admitted_provisions(record):
    """The provision candidates the answer may use: v7 and v8 admit only the pick;
    earlier records admit every returned provision."""
    if record.get("contract") not in _QUESTION_PLANS:
        return None
    return {candidate_id for ids in record["picks"]["chosen"].values() for candidate_id in ids}


def picked_judgments(record):
    """The judgment paragraphs the v8 pick chose, which the answer reads with their
    neighbouring paragraphs; None for earlier records, which read every returned
    paragraph with its whole saved context."""
    if record.get("contract") != CONTRACT:
        return None
    return {candidate_id for ids in record["judgment_picks"]["chosen"].values() for candidate_id in ids}


def validate(record, plan, context):
    contract = record.get("contract") if isinstance(record, dict) else None
    if contract not in CONTRACTS:
        raise ValueError("Unknown research contract")
    try:
        replayed = accept(plan["proposal"], context, contract=contract)
    except SchemaViolation as exc:
        raise ValueError("Saved research plan does not fit its research contract") from exc
    if replayed != plan:
        raise ValueError("Saved research plan differs from its original sources")
    fields = ({"contract", "plan", "searches", "failures", "state"}
              | ({"picks"} if contract in _QUESTION_PLANS else set())
              | ({"judgment_picks"} if contract == CONTRACT else set()))
    if (not isinstance(record, dict)
            or set(record) != fields
            or record.get("plan") != plan or not isinstance(record.get("searches"), dict)
            or not isinstance(record.get("failures"), dict)):
        raise ValueError("Research snapshot does not belong to its plan")
    for failure in record["failures"].values():
        if (not isinstance(failure, dict) or set(failure) != {"stage", "reason"}
                or failure["stage"] != "search" or not isinstance(failure["reason"], str)
                or not failure["reason"].strip()):
            raise ValueError("Research failure has no checked search disposition")
    required = {work["id"] for work in plan["work"] if work["enquiries"]}
    successes, failures = set(record["searches"]), set(record["failures"])
    if successes & failures or successes | failures != required:
        raise ValueError("Each research work item needs one execution disposition")
    for work in plan["work"]:
        if work["id"] in successes:
            validate_search(record["searches"][work["id"]], search_queries(work, contract=contract),
                            search_instruments(work, contract=contract))
    picks = []
    if contract in _QUESTION_PLANS:
        _validate_picks(record["picks"], plan, record["searches"])
        picks.append(record["picks"])
    if contract == CONTRACT:
        _validate_picks(record["judgment_picks"], plan, record["searches"], "judgment")
        picks.append(record["judgment_picks"])
    expected = "partial" if (plan["issues"] or failures or _picks_open(picks) or any(
        search["state"] == "partial" for search in record["searches"].values())) else "evaluated"
    if record["state"] != expected:
        raise ValueError("Research status disagrees with actual search outcomes")
    return deepcopy(record)


def _validate_picks(picks, plan, searches, kind="provision"):
    labels = _labels(plan, searches)
    if (not isinstance(picks, dict) or set(picks) != {"state", "proposal", "chosen", "unknown", "reason"}
            or picks["state"] not in ("evaluated", "unavailable", "not_needed")):
        raise ValueError(f"The {kind} pick has no checked disposition")
    if picks["state"] == "evaluated":
        choice = canonical_schema_data(picks["proposal"], CHOICE)
        require_schema(choice, CHOICE)
        if (picks["proposal"] != choice or picks["reason"] is not None
                or (picks["chosen"], picks["unknown"]) != _resolve_picks(choice, plan, searches, labels, kind)):
            raise ValueError(f"The saved {kind} pick differs from its proposal")
    elif picks["state"] == "unavailable":
        if (picks["proposal"] is not None or picks["unknown"] or not isinstance(picks["reason"], str)
                or not picks["reason"] or picks["chosen"] != _fallback_picks(searches, labels, kind)):
            raise ValueError(f"An unavailable {kind} pick keeps each question's first six")
    elif (picks["proposal"] is not None or picks["unknown"] or picks["reason"] is not None
          or picks["chosen"] != {w: [] for w in labels} or any(_of_kind(searches[w], kind) for w in labels)):
        raise ValueError(f"A {kind} pick is not needed only when none was returned")
