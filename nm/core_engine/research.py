"""Understand the matter, phrase its legal questions, search held law and pick what answers.

v7 is a reasoning loop, never one shot (owner standing instruction, 13 Oct 2026): the
model sets out the matter, code checks it mechanically, the model reviews it against
the conversation and corrects it (at most MAX_REVISIONS times); search phrases are
written per dispute in parallel beside one judgment-phrase call; each legal question is
searched with every phrase and its named Acts; the model picks the provisions that
answer each question and, from v8, the judgment paragraphs. From search v9 (owner decision
P32, 20 Oct 2026) the provision pick also chooses among the provisions the Acts connect to
the results; a saved pick resolves against its own saved search. Earlier plans replay unchanged.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date

from nm.core_engine import extents
from nm.core_engine.replay_scope import known, once
from nm.core_engine.retrieval import SearchUnavailable, _digest, _valid_location, in_force, validate_search
from nm.core_engine.understanding import REFERENCE, TEXT, select, source_catalogue
from nm.shared import clock_contracts
from nm.shared.model_port import (
    ModelError, OutputTruncated, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data, estimate_tokens,
    require_schema,
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
JUDGMENT_PICKED_CONTRACT = "core_research_v8"
#: v9 (owner decision, 16 Oct 2026): each dispute also says why it matters to the
#: advocate's client, shown on the matter board. v7 and v8 records keep their own shape.
PURPOSED_CONTRACT = "core_research_v9"
#: v10 (owner, 21 Oct 2026: step 4, P26 as first decided): each dispute's questions are picked
#: apart from the other disputes', as soon as its own questions are searched, so that its
#: section can be written while the others are still being researched. The record keeps each
#: dispute's picks under its ID, and a dispute's part of the record reads on its own (part_of),
#: exactly as its section was written from it. v9 and earlier records replay unchanged.
PER_DISPUTE_CONTRACT = "core_research_v10"
#: v11 (owner decision P31, 20-21 Oct 2026): the research chooses judgments, not paragraphs.
#: The judgments a dispute's pick chose, at most JUDGMENTS_PER_DISPUTE in the order chosen, are
#: read whole when no longer than WHOLE_JUDGMENT_CHARACTERS (about 8,000 tokens, three in four
#: held judgments); a longer one is read as an extract that says so - its opening and its order,
#: the paragraphs search found with those beside them, and the paragraphs they name and where
#: the court sets out the issues - and the paragraphs search found are marked either way.
JUDGMENTS_READ_CONTRACT = "core_research_v11"
#: v12 (plan AN.27, P8c; 28 Oct 2026): the plan also records the chronology of the documents the advocate sent - what each paper
#: records, event by event, with its dates read by code and its words found in the paper (chronology_of) - and the stretches of
#: a paper that could not be read. v11 and earlier records replay unchanged.
CHRONICLED_CONTRACT = "core_research_v12"
#: v13 (plan AN.28, D1-D3, 31 Oct 2026): each paper's chronology is read with the whole file in view - the advocate's messages
#: and every paper - by a call that answers for one paper; an event is dated by when it happened, an order said with what it
#: found and directed, a proceeding with who brought it and who answers it, an act a paper recites again listed once. Code checks
#: each event: its words found on its pages, and its date's numbers found in its words or on those pages; where an event fails or
#: a date on a paper's pages is carried by none of its events, one check call for that paper looks again. A numbered month and
#: year with no day ("-09-2017", invented) is read as that month. v12 and earlier records replay unchanged.
CONTRACT = "core_research_v13"
#: The plans that set out the matter as disputes and legal questions (v7 on).
QUESTION_PLANS = (PICKED_CONTRACT, JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
                  CHRONICLED_CONTRACT, CONTRACT)
_QUESTION_PLANS = QUESTION_PLANS
#: The records that pick judgment paragraphs and answer in parts per dispute (v8 on).
JUDGMENT_PICKS = (JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
                  CHRONICLED_CONTRACT, CONTRACT)
#: The records that keep each dispute's picks apart (v10 on).
BY_DISPUTE = (PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT, CHRONICLED_CONTRACT, CONTRACT)
#: The records that read the chosen judgments whole or as extracts (v11 on).
JUDGMENTS_READ = (JUDGMENTS_READ_CONTRACT, CHRONICLED_CONTRACT, CONTRACT)
#: The records that also keep the chronology of the documents (v12 on).
CHRONICLED = (CHRONICLED_CONTRACT, CONTRACT)
#: The records whose papers are read with the whole file in view, their dates checked by code (v13 on).
WHOLE_FILE = (CONTRACT,)
CONTRACTS = (LEGACY_CONTRACT, PREVIOUS_CONTRACT, WINDOWED_CONTRACT, ACCOUNT_CONTRACT, INSTRUMENTED_CONTRACT,
             PICKED_CONTRACT, JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
             CHRONICLED_CONTRACT, CONTRACT)
#: The papers a record step sees whole (D1, the owner: "a safe fixed limit like 100k tokens"): above it, each call sees the paper
#: it answers for, with the advocate's messages.
WHOLE_FILE_TOKENS = 100_000
#: P31 (owner, 21 Oct 2026): four to five judgments a dispute; a judgment is read whole up to about
#: 8,000 tokens; an extract keeps one or two paragraphs either side of each one found.
JUDGMENTS_PER_DISPUTE = 5
WHOLE_JUDGMENT_CHARACTERS = 32000
AROUND_CHOSEN, AROUND_FOUND = 2, 1
#: Why a paragraph of a long judgment is in its extract, in the order the extract keeps them
#: when it must keep fewer: the opening (court, bench, parties), the conclusion and order, a
#: paragraph the pick chose, one search found, one beside either, one they name by number, and
#: one where the court sets out the issues.
_WHY = ("opening", "order", "chosen", "found", "beside", "named", "issues")
#: "para 14", "paragraphs 12 to 15", "para 7 and 9": a judgment naming its own paragraphs.
_PARAGRAPH_NAMED = re.compile(r"\bpara(?:graph)?s?\.?\s*(\d{1,3})(?:\s*(?:to|-|\u2013|and|&)\s*(\d{1,3}))?", re.I)
#: Where a court sets out the questions or issues it decides.
_ISSUES = re.compile(r"\b(?:questions?|issues?|points?)\b[^.]{0,80}?\b(?:arises?|arise for|for (?:our )?"
                     r"(?:consideration|determination|decision)|to be (?:decided|determined|considered)|that fall)",
                     re.I)
#: What a question's search records, and its dispute's picks, when the answer stopped first.
UNFINISHED = "The answer stopped before this research was finished"
#: The receipts of what research did (execution).
EXECUTION = "core_read_only_execution_v1"
#: One check-and-fix round, then the last check (owner, 18 Oct 2026, for speed: a second
#: round took about 45 s in the eighth live run).
MAX_REVISIONS = 1
#: The pick chooses from each question's first PROVISIONS_FOR_PICK provisions.
PROVISIONS_FOR_PICK = 20
#: Answer limits per step. Calls in flight are budgeted at their limit.
MAX_OUTPUT = {"understand": 12000, "check": 6000, "revise": 12000, "phrases": 6000,
              "judgment_phrases": 8000, "pick": 8000, "judgment_pick": 8000, "chronology": 12000, "transfers": 12000,
              "chronology_check": 8000, "transfers_check": 8000, "connections": 8000, "connections_check": 6000}

# The prompts below were developed and measured in outputs/decomposition-scratch
# (13-14 Oct 2026). They state the purpose and the needed outcome in plain language
# and leave understanding to the model; code makes the mechanical checks afterwards.
UNDERSTAND = """You are a senior Indian litigation lawyer working with a colleague, the advocate, who practises in Telangana. You receive the conversation so far: the advocate's messages, any documents they sent and any earlier notes from our research assistant. The last message is the one we are acting on now.

Advocates bring matters to us so that we can find the law that governs them. Your job in this step is to understand the matter well enough that the right law can be researched. You are not answering the legal questions yet. Read the whole conversation, think about what has happened, who is involved, what the advocate wants now and why, and then set out your understanding.

What we need from you:

- What the advocate wants from us now. Often they say so. When they only tell us what has happened, they want to know where the law stands on those events: the legal questions a lawyer would need answered to advise on them. Also note, in the advocate's own words, anything they have told us not to do (for example to pause research or not to contact anyone) in ruled_out, and where they have told us nothing of the kind leave ruled_out empty. What the papers leave open or unproved is not something the advocate ruled out: it belongs in the facts as uncertain and in the facts we would still need.
- The people involved and their roles: whether each is the advocate's client or one of the client's people (client), and, for each proceeding the papers name - a suit, appeal, revision, petition, complaint or other case - each person's part in it (who brought it, who answers it, who else is joined), with the page's own words (parts). A person the papers name in a proceeding is listed even when the advocate did not mention them.
- Every subject of the matter the papers identify - a property, an account, a contract, a policy, a case or a document - by its identifier exactly as the page writes it (a survey, account, policy, case or document number), what it is, and the page's own words (subjects). List a subject the papers name even where it seems not to bear on what the advocate asked, so that none is overlooked.
- The facts, each kept exactly as certain as the advocate put it: confirmed, reported by someone, uncertain, or disputed. Give the advocate's own words for each fact, or, for a fact that comes from a document they sent, the document's own words. What the advocate reports is their account, and what a document says is what its author wrote; neither is proven fact, and we never add facts they did not give.
- The separate disputes. A dispute is one set of events between particular parties that needs its own legal answer. Events that call for different kinds of law, such as a civil wrong and a crime, or that concern different transactions, are separate disputes, even when they happen together or involve the same people.
- For each dispute, think through every legal consequence the events may have, civil, criminal and under any special statute, and for each: the right or liability, the remedy, how and where it is pursued and within what time, and, where the case turns on particular evidence, how that evidence is proved. Ask as legal questions those that bear on what the advocate wants; put the rest in related points.
- For each dispute, the legal questions we must research to do what the advocate wants. A legal question is about one legal point: a right, an obligation, a remedy, a defence, a procedure, a time limit, a presumption or an offence. If answering it would need two different rules, such as what a right is and how it is enforced, it is two questions. Write each so that a lawyer could answer it from one or two provisions of law, and say briefly why we need it. Where the facts leave open something that changes the governing law (for example when the events happened, or which personal law applies), say what is open.
- For each legal question, the law you would check first: the Indian Acts, and sections if you know them, that you believe govern it. This is your recollection to guide the search; it will be checked against the statutes we hold, so say only what you believe and do not guess.
- For each dispute, the rights that may be at stake, the relief or outcome being sought, and the facts we would still need.
- For each dispute, why it matters to the advocate's client: in a sentence or two, what is at stake for them and why it needs attention now.
- Related points: things the advocate did not ask about but a careful lawyer would want them to know, such as a presumption that helps, a time limit that may be running, or an alternative remedy, with why each matters. We will tell the advocate about these and let them decide; we do not research them now.

Some messages need no legal research: thanks or social messages, an instruction to keep research paused, a request to transcribe or tidy text. In that case say so and why, and leave the research questions empty; you may still record the disputes already known from the conversation.
"""
CHECK = """You are a senior Indian litigation lawyer reviewing a colleague's understanding of a matter before any research starts. You receive the conversation with the advocate and your colleague's written understanding of it.

Check the understanding carefully against the conversation itself, the way you would before letting a junior start research:

- Has anything the advocate asked for, reported or ruled out been missed or misread?
- Are separate disputes kept apart (events that call for different kinds of law, or that concern different transactions), and is anything that belongs together split up?
- Does each legal question ask about one legal point, or would answering it need two different rules? Taken together, would the questions let us do what the advocate asked? Are any of them duplicates, or so general that no particular law answers them?
- Have the events' other legal consequences (civil, criminal, under a special statute), and how each is pursued and proved, been considered, and asked where they bear on what the advocate wants?
- Is any fact stated more strongly than the advocate or a document they sent put it, or added?
- Is anyone's part in a proceeding the papers name, or a subject the papers identify, missed or misread?
- Are the related points genuinely useful to the advocate, and kept separate from what we research now?
- Is research being started when the advocate has ruled it out, or skipped when it is needed? Our purpose with every matter is to find where the law stands for each dispute in it, so that the advocate can see what the case needs. They do not have to ask for that: when they only tell us what has happened, or ask us to understand, summarise or set out the events, they still want to know where the law stands on them. Skipping research is a problem unless the advocate has told us not to research or the message needs none (thanks, or a request to tidy or transcribe text); starting it is a problem only when they have ruled it out. Where we could find instructions from the advocate limiting our work in their latest message, they are listed after the conversation; the conversation itself may hold earlier ones. Do not report research as a problem because the advocate's words did not literally ask for advice.

Counting is code's work for figures as it is for days: do not add, subtract or convert areas, sums of money or any other figures yourself, and do not report that figures disagree because they do not seem to add up. Where two papers give different figures for the same thing, say so with each figure as it is given; where figures might or might not add up, say that they have not been added up.

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

After each question's search results come the provisions their Acts connect to them: provisions a result names in its own words, provisions that name a result, and the provisions printed beside a result, each shown with its heading and the words that connect them. A lawyer reads a rule with what its Act reads it with: its exceptions and provisos, the defences, presumptions and conditions that bear on it, its time limits and the procedure for enforcing it.

For each question, choose the provisions a lawyer must read to answer it: the ones that state the governing rule, right, liability, remedy, procedure, time limit, presumption or offence the question asks about, and the connected provisions that qualify or complete them in a way the answer needs. Choose only what is needed, and put the most necessary first. Whatever you choose is read whole.

Judge each provision by what it actually says, not by whether it shares words with the question. A provision whose Act India Code, the government's record of the Acts in force, no longer lists is marked not in force; weigh that as a lawyer would. If no shown provision answers a question, choose none for it and say what is missing.
"""
JUDGMENT_PICK = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for each question a search of the judgments we hold, the Supreme Court of India and the High Court of Andhra Pradesh, has returned up to six paragraphs, each shown with its judgment, court, year, how many later judgments cite it, and the paragraph's words.

For each question, choose the paragraphs a lawyer would rely on to answer it: those where a court decides or authoritatively explains the point the question asks about. Most questions need one to three; choose more only when each adds something, and put the most useful first. Each judgment whose paragraph you choose is then read whole, or, when it is long, as an extract around what was found, so choose the judgments a lawyer would rely on as much as the paragraphs.

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

DISPUTE_V8 = _object({
    "id": STRING, "name": STRING, "between": STRINGS, "fact_ids": STRINGS,
    "legal_questions": {"type": "array", "items": _object({
        "id": STRING, "question": STRING, "why_needed": STRING, "open_alternative": STRING, "law_to_check": STRINGS})},
    "rights_at_stake": STRINGS, "relief_sought": STRINGS, "missing_facts": STRINGS})
DISPUTE = _object({**DISPUTE_V8["properties"], "why_it_matters": STRING})


def _understanding(dispute):
    return _object({
        "summary": STRING,
        "asked": STRINGS,
        "ruled_out": STRINGS,
        "needs_research": {"type": "boolean"},
        "no_research_reason": STRING,
        "parties": {"type": "array", "items": _object({"who": STRING, "role": STRING})},
        "facts": {"type": "array", "items": _object({
            "id": STRING, "fact": STRING, "advocate_words": STRING,
            "certainty": {"type": "string", "enum": ["confirmed", "reported", "uncertain", "disputed"]}})},
        "disputes": {"type": "array", "items": dispute},
        "related_points": {"type": "array", "items": _object({"point": STRING, "why_it_matters": STRING, "dispute_id": STRING})},
    })


UNDERSTANDING_V8 = _understanding(DISPUTE_V8)
UNDERSTANDING = _understanding(DISPUTE)
PROBLEM = _object({"problem": STRING, "fix": STRING})
CHECKED = _object({"verdict": {"type": "string", "enum": ["sound", "revise"]},
                   "problems": {"type": "array", "items": PROBLEM}})
REVISED = _object({"notes": STRING, "understanding": UNDERSTANDING})
#: v13 (AN.28, A1 and B12): whether each party is the client or one of the client's people, each party's part in each proceeding the
#: papers name, and every subject the papers identify, each with the page's own words, which code finds.
PART = _object({"proceeding": STRING, "part": STRING, "words": STRING})
PARTY_V13 = _object({"who": STRING, "role": STRING, "client": {"type": "boolean"}, "parts": {"type": "array", "items": PART}})
SUBJECT = _object({"identifier": STRING, "what": STRING, "words": STRING})
UNDERSTANDING_V13 = {**UNDERSTANDING, "required": [*UNDERSTANDING["required"], "subjects"],
                     "properties": {**UNDERSTANDING["properties"], "parties": {"type": "array", "items": PARTY_V13},
                                    "subjects": {"type": "array", "items": SUBJECT}}}
REVISED_V13 = _object({"notes": STRING, "understanding": UNDERSTANDING_V13})
#: A v13 plan keeps an understanding without them as one that gives none (P29: a slip never refuses what was understood).
UNDERSTANDING_V13_RECORD = {**UNDERSTANDING_V13, "required": UNDERSTANDING["required"],
                            "properties": {**UNDERSTANDING_V13["properties"], "parties": {"type": "array", "items": {
                                **PARTY_V13, "required": ["who", "role"]}}}}


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


#: The chronology of each document (plan AN.27, P8; invariants I4, I5): what the papers record, event by event, so that nothing in
#: them is overlooked when the matter's history is told. Never an answer to a legal question, and never a judgment of which account
#: is right. A window is at most this many characters of one document's pages.
CHRONOLOGY_WINDOW = 40000
EVENT_KINDS = ("transaction", "order", "filing", "pending", "other")
CHRONOLOGY = """Message: You receive one document an advocate sent about a client's matter, or one stretch of its pages, each page under its number, with the document's name. A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. A page read from a scan may carry [illegible] and square-bracket notes about stamps, signatures and handwriting; those are the reader's, not the document's.

Purpose: Set out the document's own chronology for the advocate and for our research assistant: every event, order, direction, filing, transaction and proceeding it records or reports, with its date, so that nothing in the paper is overlooked when the matter's history is told. You are not judging which account is right, and you are not answering any legal question.

Look for:
- Each event the document records, whatever its date: a sale, partition or other deed, a mutation or entry in a revenue or other record, an order or direction of a court or authority, an appeal, revision, petition, suit, complaint, FIR or charge sheet, a notice, a hearing or listing, a payment, a death; and each proceeding it says is pending, with what it says of its stage.
- Who says it. A document may record an event itself (an order's own date and directions) or report it (a recital of an earlier order, a party's account or pleading). Give the authority or party whose words they are, and keep a party's allegation as that party's.
- The date as the page gives it, in the page's own form ("30-10-1985", "17 August 2019", "2008", "1961-62"); where the page gives none, say undated. Do not work out, convert or guess a date.
- The figures and identifiers that belong to the event, such as extents, sums, and deed, case, file and survey numbers, exactly as the page gives them.
- One event for each act and date. Do not merge events the page keeps apart, do not repeat an event the same page says twice, and do not add anything the page does not say. A register or list of many similar entries (a line for each survey number, say) is one event for the whole list, naming its range and the figures that matter, with the words of its first entries.
Work in a loop: list the events page by page, then read each page again against your list for any event or date you skipped or misread, and correct the list before you answer.

Outcome: events, in the order of the pages. Each has: date; kind (transaction, order, filing, pending, or other); what (one plain sentence saying what happened, with its figures and identifiers); said_by (whose words they are: the document's own author, or the party or authority it reports); words (the exact words on a page that record it, copied exactly as the page gives them, without the reader's square-bracket notes - a sentence that runs over a page may be copied whole - or several passages joined with '...'; never reword)."""
EVENT = _object({"date": STRING, "kind": {"type": "string", "enum": list(EVENT_KINDS)}, "what": STRING, "said_by": STRING,
                 "words": STRING})
CHRONOLOGY_SCHEMA = _object({"events": {"type": "array", "items": EVENT}})
#: An event as the plan records it (v12): what the model said, and what code made of it - the sort date, the document and the
#: turn's source it belongs to, the pages its words are on and whether they are found there, and its number.
EVENT_RECORD = _object({"id": STRING, "date": STRING, "sort": STRING, "kind": EVENT["properties"]["kind"], "what": STRING,
                        "said_by": STRING, "document": STRING, "source": STRING,
                        "pages": {"type": "array", "items": {"type": "integer"}}, "words": STRING,
                        "anchored": {"type": "boolean"}})
CHRONOLOGY_FAILURE = _object({"document": STRING, "pages": STRING, "reason": STRING})


TRANSFER_KINDS = ("sale", "partition", "gift", "settlement", "decree", "other")
#: v13 (AN.28, D7): the transactions of any matter - land or other property, money, shares, goods or a right.
TRANSACTION_KINDS = (*TRANSFER_KINDS[:-1], "lease", "mortgage", "loan", "payment", "other")
#: The transfers of land each document records (plan AN.27, P13d; invariant I6): so that the extents can be added up by code, never by
#: a model, and set against the parcel's whole extent. The model reads what a page records; code reads the extents, finds the words
#: and does the arithmetic (extents.py).
TRANSFERS = """Message: You receive one document an advocate sent about a client's matter, or one stretch of its pages, each page under its number, with the document's name. A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. A page read from a scan may carry [illegible] and square-bracket notes about stamps, signatures and handwriting; those are the reader's, not the document's.

Purpose: List the transfers of land the document records or reports - a sale, partition, gift, settlement, decree or order that gives an extent of a parcel from one person to another - so that code can add the extents up for each parcel and set them against the parcel's whole extent, which we need to check against the advocate's own figures. You are not adding or working out anything yourself, and you are not judging which account is right.

Look for:
- Each transfer of an extent of land the document records or reports, whatever its date: who gave it up (from), who took it (to), the parcel (its survey number as the page writes it, with any sub-number), the extent transferred exactly as the page writes it (for example "Ac.1.18 guntas"), and the date as the page gives it ("undated" where it gives none).
- The whole extent of the parcel, where the same passage states it (for example "out of Ac.8.24 guntas in Sy.No.487"), exactly as written; otherwise leave it empty.
- The exact words on a page that record the transfer, copied exactly as the page gives them, without the reader's square-bracket notes - or several passages joined with '...'; never reword.
- One entry for each transfer. If a page reports the same transfer twice, give it once. Do not list a transfer that gives no extent, do not add or work out an extent the page does not give, and do not merge transfers the page keeps apart.
Work in a loop: list the transfers page by page, then read each page again against your list for any transfer, extent or date you skipped or misread, and correct the list before you answer.

Outcome: transfers, in the order of the pages. Each has: date; kind (sale, partition, gift, settlement, decree, or other); parcel; extent; total; from; to; words."""
TRANSFER = _object({"date": STRING, "kind": {"type": "string", "enum": list(TRANSFER_KINDS)}, "parcel": STRING, "extent": STRING,
                    "total": STRING, "from": STRING, "to": STRING, "words": STRING})
TRANSFERS_SCHEMA = _object({"transfers": {"type": "array", "items": TRANSFER}})
#: A transfer as the plan records it: what the model said, and what code made of it - the sort date, the paper and the turn's source
#: it belongs to, the pages its words are on and whether they are found there, and its number.
TRANSFER_RECORD = _object({"id": STRING, "date": STRING, "sort": STRING, "kind": TRANSFER["properties"]["kind"], "parcel": STRING,
                           "extent": STRING, "total": STRING, "from": STRING, "to": STRING, "document": STRING, "source": STRING,
                           "pages": {"type": "array", "items": {"type": "integer"}}, "words": STRING,
                           "anchored": {"type": "boolean"}})


def _record_schema(understanding, chronology=False):
    return _object({
        "understanding": understanding,
        "review_rounds": {"type": "array", "items": _object({
            "code_problems": {"type": "array", "items": PROBLEM},
            "verdict": {"type": "string", "enum": ["sound", "revise", "unavailable"]},
            "problems": {"type": "array", "items": PROBLEM}})},
        "statute_phrases": {"type": "array", "items": _object({
            "dispute_id": STRING, "questions": STATUTE_PHRASES["properties"]["questions"]})},
        "judgment_phrases": JUDGMENT_PHRASE_SCHEMA["properties"]["questions"],
        "failures": {"type": "array", "items": FAILURE},
        **({"chronology": {"type": "array", "items": EVENT_RECORD},
            "chronology_failures": {"type": "array", "items": CHRONOLOGY_FAILURE}} if chronology else {}),
    })


SCHEMA_V8 = _record_schema(UNDERSTANDING_V8)
SCHEMA = _record_schema(UNDERSTANDING)
SCHEMA_V12 = _record_schema(UNDERSTANDING, chronology=True)
# The transfers of land (P13d) are optional in v12: a plan saved before them has none and validates as it did.
SCHEMA_V12["properties"]["transfers"] = {"type": "array", "items": TRANSFER_RECORD}
SCHEMA_V12["properties"]["transfers_failures"] = {"type": "array", "items": CHRONOLOGY_FAILURE}
#: v13 (AN.28, D3, D7, B16): a transaction of any kind, with the model's plain reading of its figure and the number of the document
#: that records it, as the plan records it.
TRANSACTION = _object({"date": STRING, "kind": {"type": "string", "enum": list(TRANSACTION_KINDS)}, "parcel": STRING,
                       "extent": STRING, "reading": STRING, "total": STRING, "from": STRING, "to": STRING, "instrument": STRING,
                       "words": STRING})
TRANSACTIONS_SCHEMA = _object({"transfers": {"type": "array", "items": TRANSACTION}})
TRANSACTION_RECORD = _object({**TRANSFER_RECORD["properties"], "kind": TRANSACTION["properties"]["kind"],
                              "reading": STRING, "instrument": STRING})
SCHEMA_V13 = _record_schema(UNDERSTANDING_V13_RECORD, chronology=True)
#: v13 (AN.28, piece 3e): what matters to the client only when the papers are read side by side, each point with the pages' words.
CONNECTION_KINDS = ("client_appears", "against_client", "after_death", "after_time_limit", "further_subject", "other")
CONNECTION = _object({"kind": {"type": "string", "enum": list(CONNECTION_KINDS)}, "point": STRING, "why_it_matters": STRING,
                      "words": STRING})
CONNECTIONS_SCHEMA = _object({"client_people": STRINGS, "connections": {"type": "array", "items": CONNECTION}})
PLACE = _object({"document": STRING, "source": STRING, "page": {"type": "integer"}})
CONNECTION_RECORD = _object({"id": STRING, **CONNECTION["properties"], "anchored": {"type": "boolean"},
                             "places": {"type": "array", "items": PLACE}})
APPEARANCE = _object({"name": STRING, "places": {"type": "array", "items": PLACE},
                      "near": {"type": "array", "items": _object({"as_written": STRING, **PLACE["properties"]})}})
# Optional in v13, as the transactions are in v12: a plan without them validates.
SCHEMA_V13["properties"]["connections"] = {"type": "array", "items": CONNECTION_RECORD}
SCHEMA_V13["properties"]["connections_failures"] = {"type": "array", "items": CHRONOLOGY_FAILURE}
SCHEMA_V13["properties"]["client_people"] = STRINGS
SCHEMA_V13["properties"]["appearances"] = {"type": "array", "items": APPEARANCE}
SCHEMA_V13["properties"]["transfers"] = {"type": "array", "items": TRANSACTION_RECORD}
SCHEMA_V13["properties"]["transfers_failures"] = {"type": "array", "items": CHRONOLOGY_FAILURE}


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
    """Today's date where the advocate works, then the advocate's words and our earlier
    notes, attributed, oldest first."""
    earlier = [row for row in context["conversation"]
               if row.get("record_role") in ("original_account", "nm_interpretation")]
    where = clock_contracts.setting()
    lines = [f"Today is {where['weekday']}, {where['today']}, where the advocate practises "
             f"({where['advocate_practises_in']}).", ""]
    lines += ["Conversation so far (oldest first):"] if earlier else []
    for number, row in enumerate(earlier, 1):
        who = ("Advocate" if row["record_role"] == "original_account"
               else "Our research assistant (an earlier note, not the advocate's words)")
        lines.append(f"[{number}] {who}: {row['text']}")
    lines += ["", "Latest message from the advocate (the one we act on now):", context["latest"]["text"]]
    if "documents" in context:
        lines += ["", "Documents the advocate sent (each page says what its document says; "
                      "these are not the advocate's own words):"]
        for row in context["documents"]:
            about = row["document"]
            sent = ("with the latest message" if row["turn_id"] == context["latest"]["turn_id"]
                    else "earlier in the conversation")
            if about.get("recording"):
                lines.append(f'["{about["name"]}", recording, sent {sent}; transcribed by AI] {row["text"]}')
                continue
            read = "; read by AI from a scan" if about["read_by"] == "ai" else ""
            lines.append(f'["{about["name"]}", page {about["page"]}, sent {sent}{read}] {row["text"]}')
        for page in context["unread_document_pages"]:
            where = "recording" if page.get("recording") else f'page {page["page"]}'
            lines.append(f'["{page["name"]}", {where}: not read ({page["reason"]})]')
    if context.get("current_records"):
        lines += ["", "Current records of this matter: "
                  + json.dumps(context["current_records"], ensure_ascii=False)]
    return "\n".join(lines).strip()


def _plain(text):
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split()).casefold()


def _bare(text):
    """Plain words without quotation marks: a quotation's marks are typography, not the
    words, and a page read from a scan may set them differently from the quoting fact."""
    return " ".join(re.sub(r"[\"']", " ", _plain(text)).split())


def fact_pieces(words):
    """The pieces of a fact's quoted words that must each appear in the material."""
    return [piece for piece in (_bare(fragment) for fragment in _quoted_fragments(words)) if piece]


def _quoted_fragments(quote):
    """The pieces of a quotation that must appear word for word: typographic quotes,
    a leading turn marker such as "[1]" and edge punctuation are not the advocate's
    words, and an ellipsis joins separately quoted pieces."""
    text = re.sub(r"^\s*\[\d+\]\s*", "", _plain(quote))
    inline = re.findall(r'"([^"]+)"', text)
    pieces = [p for part in (inline or [text]) for p in re.split(r"\.\.\.|…", part)]
    return [p.strip(" .,;:\"'") for p in pieces if p.strip(" .,;:\"'")]


#: How much of a page's foot or head - a stamp, a signature, a page number, the reader's marks - a sentence may run over when
#: it goes on to the next page of the same document (plan AN.27, P1).
PAGE_FURNITURE = 400
#: The most words of a refused quotation Pages.nearest will search the pages for (plan AN.27, P21).
NEAREST_WORDS = 120
#: How many words of the page it shows on each side of the run it found.
NEAREST_AROUND = 8
_MARKS = re.compile(r"\[[^\[\]]*\]")


def _reading(text):
    """A page as quoted words are found in it: plain, as _bare gives it, and without the square-bracket marks the reader puts
    in to say what the page shows - [signature], [stamp: ...], [Handwritten: ...] - which are not the page's words."""
    marked = _bare(text)
    while True:
        plain = _MARKS.sub(" ", marked)
        if plain == marked:
            return " ".join(plain.split())
        marked = plain


class Pages:
    """The pages of the documents the advocate sent, in reading order, and where quoted words are found in them. A page is
    {"document": name, "page": number, "text": text, ...}. Words are found on one page, or run over a page break onto the next
    page of the same document past what a page's foot and head hold; never across two documents, or across pages that are
    not next to each other. One finder for every check of where a fact's words come from (plan AN.27, P1)."""

    def __init__(self, pages):
        self.pages = list(pages)
        self._plain = [_bare(page["text"]) for page in self.pages]
        self._read = [_reading(page["text"]) for page in self.pages]

    @classmethod
    def of_context(cls, context):
        """The pages of a turn's context: each row is one page of one document the advocate sent."""
        return cls({"document": row["document"]["name"], "page": row["document"].get("page"), "text": row["text"]}
                   for row in context.get("documents", ()))

    def holding(self, piece):
        """The page, or the two pages the words run over, that hold these words (a piece as fact_pieces gives it); or None."""
        for index, plain in enumerate(self._plain):
            if piece in plain:
                return [self.pages[index]]
        words = _reading(piece)
        if not words:
            return None
        for index, read in enumerate(self._read):
            if words in read:
                return [self.pages[index]]
        for index in range(len(self.pages) - 1):
            first, second = self.pages[index], self.pages[index + 1]
            if (first["document"] == second["document"] and type(first["page"]) is int and type(second["page"]) is int
                    and second["page"] == first["page"] + 1 and self._over(words, self._read[index], self._read[index + 1])):
                return [first, second]
        return None

    @staticmethod
    def _over(words, foot, head):
        """Whether the words end one page and go on at the start of the next: some of them end the first page's foot, at a word's
        end, and the rest begin the second's head, at a word's start, with no more than PAGE_FURNITURE characters beside them."""
        parts = words.split(" ")
        room = len(words) + PAGE_FURNITURE
        foot, head = foot[-room:], head[:room]
        if parts[0] not in foot or parts[-1] not in head:
            return False
        for cut in range(1, len(parts)):
            ending, going = " ".join(parts[:cut]), " ".join(parts[cut:])
            at_head = re.search(r"(?<!\S)" + re.escape(going), head)
            if (at_head is not None and at_head.start() <= PAGE_FURNITURE
                    and any(len(foot) - m.end() <= PAGE_FURNITURE for m in re.finditer(re.escape(ending) + r"(?!\S)", foot))):
                return True
        return False

    def nearest(self, piece):
        """The page's own words nearest to a quotation that is not found (plan AN.27, P21): the longest run of at least four of the
        quotation's words that one page holds, with a few words of the page on each side of it, as {"document", "page", "run",
        "words"}; None where no page holds four in a row, or the quotation is longer than NEAREST_WORDS. A run that goes over a page
        break is not guessed at: the longest run that one page holds is the one shown. Code finds the words; the model that
        quoted is shown them and decides what to quote - and a quotation is still found exactly or not at all."""
        words = piece.split(" ")
        if len(words) > NEAREST_WORDS:
            return None
        for length in range(len(words) - 1, 3, -1):
            for start in range(len(words) - length + 1):
                run = " ".join(words[start:start + length])
                held = self.holding(run)
                if held is not None and len(held) == 1:
                    index = next(i for i, page in enumerate(self.pages) if page is held[0])
                    plain = self._plain[index]
                    if run not in plain:
                        plain, run = self._read[index], _reading(run)
                    at = plain.find(run)
                    first, last = plain[:at].count(" "), plain[:at + len(run)].count(" ") + 1
                    around = " ".join(plain.split(" ")[max(0, first - NEAREST_AROUND):last + NEAREST_AROUND])
                    return {"document": held[0]["document"], "page": held[0]["page"], "run": run, "words": around}
        return None

    def stops(self, piece):
        """Where words that are not found stop matching, to say so: the words found as far as they go (their last few) and the
        words from where they are not found (the next few), as a sentence for the model that quoted them - and, where a page holds
        a run of them, the page's own words around that run (P21), so that what is quoted next can be copied."""
        words = piece.split(" ")
        found, lost = 0, len(words)
        while lost - found > 1:
            middle = (found + lost) // 2
            if self.holding(" ".join(words[:middle])) is not None:
                found = middle
            else:
                lost = middle
        near = self.nearest(piece)
        where = ""
        if near:
            page = f", page {near['page']}" if near["page"] else ""
            where = f"; the nearest words on a page ({near['document']}{page}) read {near['words']!r}"
        if found < 3:  # a word or two that happen to be on a page say nothing about where the quotation is from
            return f"they are not found from their first words: {' '.join(words[:12])!r}{where}"
        gone = " ".join(words[found:found + 12])
        return (f"they match up to {('... ' if found > 6 else '') + ' '.join(words[max(0, found - 6):found])!r} "
                f"and are not found from {gone!r}{where}")


#: Where an understanding's own words are, as the model that wrote them is told (plan AN.27, P23): by field, and by ID for the facts,
#: disputes and legal questions.
_PLACES = {"asked": "what was asked", "ruled_out": "what was ruled out", "no_research_reason": "the reason given for no research"}
_ITEMS = {"facts": "fact", "disputes": "dispute", "legal_questions": "legal question"}
#: What the model is told when its understanding states an extent that none of the advocate's messages and none of the documents give.
EXTENT_FIX = ("Do not work out an extent or a sum yourself: use one the advocate or a paper gives, copied as it stands, or say that it "
              "has not been worked out. Code adds up the figures of the papers' transactions.")


def _extents_written(text):
    """Each extent some words write, as (the words as written, its guntas - None where the notation cannot be an extent, as Ac.0.55
    cannot: 40 guntas make an acre - and the extent itself: its guntas, or for such a notation its acres and guntas as written, so that
    a paper's own slip is the same slip). The finder and the reading are extents.py's own, so that the notations stay in one place."""
    found = []
    for _, _, how, match in extents._extents_in(" ".join(text.split())):
        value = extents._guntas(how, match.groups())[0]
        found.append((match.group(0), value, value if value is not None else tuple(int(part) for part in match.groups())))
    return found


def _words_of(value, place, key=""):
    """Each string in a part of an understanding with where it is - the fact, dispute or legal question it belongs to, by its ID, else
    the field - and without the quotations of facts, which have their own check."""
    if isinstance(value, str):
        yield place, value
    elif isinstance(value, list):
        for item in value:
            yield from _words_of(item, place, key)
    elif isinstance(value, dict):
        if key in _ITEMS and value.get("id"):
            place = f"{_ITEMS[key]} {value['id']}"
        for name, item in value.items():
            if name != "advocate_words":
                yield from _words_of(item, place, name)


def _extent_problems(understanding, context):
    """The extents the understanding states that none of the advocate's messages and none of the documents they sent give (plan AN.27,
    P23; invariant I6). Counting is code's work (extents.py adds the papers' transfers of land): a total, a difference or an estimate
    that a model worked out is refused to it, in words, and left out when it revises. An extent is the same extent however it is written
    (Ac.1.10, 1 acre 10 guntas and 50 guntas), and one that no paper can write - guntas of 40 or more - is refused unless a paper
    itself writes those figures. One problem for each extent, naming every place it is stated. What an earlier note of ours or a
    record of the matter holds is not a message or a paper."""
    sources = [row["text"] for row in context["conversation"] if row.get("record_role") == "original_account"]
    sources += [context["latest"]["text"]] + [row["text"] for row in context.get("documents", ())]
    given = {extent for text in sources for _, _, extent in _extents_written(text)}
    # And sums of money (AN.28, D7): a sum is the same sum in figures or in words, lakhs or rupees.
    given_sums = {value for text in sources for _, value in extents.sums_written(" ".join(text.split()))}
    stated = {}
    for name, item in understanding.items():
        for place, text in _words_of(item, _PLACES.get(name, f"the {name.replace('_', ' ')}"), name):
            found = [(words, value, extent) for words, value, extent in _extents_written(text) if extent not in given]
            found += [(words, value, ("sum", value)) for words, value in extents.sums_written(" ".join(text.split()))
                      if value not in given_sums]
            for words, value, extent in found:
                kept = stated.setdefault(extent, {"words": words, "value": value, "places": []})
                if place not in kept["places"]:
                    kept["places"].append(place)
    problems = []
    for key, kept in stated.items():
        where = ", ".join(kept["places"])
        if isinstance(key, tuple) and key[:1] == ("sum",):
            said = (f"The understanding states the sum {kept['words']!r} ({where}), which is in none of the advocate's messages or the "
                    "documents they sent; it reads as a total, a difference or an estimate that was worked out.")
        elif kept["value"] is None:
            said = (f"The understanding writes the extent {kept['words']!r} ({where}), which cannot be an extent as a paper writes it - 40 "
                    "guntas make an acre, so the guntas after the acres are under 40 - and is in none of the advocate's messages or the "
                    "documents they sent.")
        else:
            said = (f"The understanding states the extent {kept['words']!r} ({where}), which is in none of the advocate's messages or the "
                    "documents they sent; it reads as a total, a difference or an estimate that was worked out.")
        problems.append({"problem": said, "fix": EXTENT_FIX})
    return problems


def code_checks(understanding, context):
    """Mechanical checks only; meaning is the model's work."""
    problems = []
    advocate = _bare(" ".join([row["text"] for row in context["conversation"]
                               if row.get("record_role") == "original_account"] + [context["latest"]["text"]]))
    # A fact may rest on a document the advocate sent; where its words appear is the
    # code's to establish (owner decisions, 15 Oct 2026).
    pages = Pages.of_context(context)
    facts = {f["id"] for f in understanding["facts"]}
    if len(facts) != len(understanding["facts"]):
        problems.append({"problem": "Two facts share an id.", "fix": "Give each fact its own id."})
    for fact in understanding["facts"]:
        missing = [piece for piece in fact_pieces(fact["advocate_words"])
                   if piece not in advocate and pages.holding(piece) is None]
        if missing:
            problems.append({"problem": f"Fact {fact['id']}: the quoted words do not appear in the advocate's "
                                        f"messages or the documents they sent ({fact['advocate_words']!r}); "
                                        f"{pages.stops(missing[0])}.",
                             "fix": "Quote the exact words this fact rests on, as the page gives them - copy them as they stand, a "
                                    "misread letter or an odd spacing included, and keep what you add yourself outside the quotation "
                                    "marks (separate passages joined with '...') - or remove the fact if they were not given."})
    # v13 (AN.28): each party's part in a proceeding and each subject rest on the page's own words, found by code as a fact's are.
    said = [(f"{party['who']}'s part in {part['proceeding']}", part["words"]) for party in understanding.get("parties", ())
            for part in party.get("parts", ())]
    said += [(f"the subject {subject['identifier']}", subject["words"]) for subject in understanding.get("subjects", ())]
    for place, quoted in said:
        missing = [piece for piece in fact_pieces(quoted) if piece not in advocate and pages.holding(piece) is None]
        if missing:
            problems.append({"problem": f"For {place}, the quoted words do not appear in the advocate's messages or the documents "
                                        f"they sent ({quoted!r}); {pages.stops(missing[0])}.",
                             "fix": "Quote the exact words, as the page gives them - copy them as they stand, a misread letter or an "
                                    "odd spacing included (separate passages joined with '...') - or leave it out if the papers do "
                                    "not give it."})
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
    return problems + _extent_problems(understanding, context)


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


def _restrictions_note(found):
    """What the advocate restricted in their latest message, as the interpretation step found it, for the steps that check and
    correct the understanding (plan AN.27, P4): found is a list of their exact words (empty: nothing was restricted), or None
    where that is not known, which says nothing rather than 'none'."""
    if found is None:
        return ""
    head = "\n\nInstructions from the advocate limiting our work, as our reading of their latest message found them: "
    return head + ("none." if not found else "\n" + "\n".join(f"- {words}" for words in found))


#: Recorded when the loop is not run: a courtesy, a restriction alone, or thanks needs no law.
NO_NEW_MATTER = "The interpretation found no new information or request in the latest message."


def carries_matter(interpretation):
    """Whether the interpretation step found information or a request; an unchecked or
    partial interpretation is never taken as proof that nothing needs research."""
    if (not isinstance(interpretation, dict) or interpretation.get("issues")
            or not isinstance(interpretation.get("units"), list) or not interpretation["units"]):
        return True
    return any(unit.get("kind") in ("information", "request") for unit in interpretation["units"])


def _no_matter(context):
    return accept({"understanding": {"summary": "", "asked": [], "ruled_out": [], "needs_research": False,
                                     "no_research_reason": NO_NEW_MATTER, "parties": [], "facts": [],
                                     "disputes": [], "related_points": [], "subjects": []},
                   "review_rounds": [], "statute_phrases": [], "judgment_phrases": [], "failures": [],
                   "chronology": [], "chronology_failures": []}, context)


def _phrases(model, understanding, report):
    """The search phrases for an understanding, with any step that failed. Owner decision,
    14 Oct 2026: one statute-phrase call per dispute, all at once, beside one
    judgment-phrase call for the matter (measured 61% faster, no loss)."""
    statute, judgment, failures = [], [], []
    disputes = [d for d in understanding["disputes"] if d["legal_questions"]]
    if not (understanding["needs_research"] and disputes):
        return statute, judgment, failures
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

    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
        for (kind, dispute), data, error in pool.map(phrase, tasks):
            if error:
                failures.append({"step": f"{kind}_phrases", "scope": dispute["id"] if dispute else "matter",
                                 "reason": error})
            elif kind == "statute":
                statute.append({"dispute_id": dispute["id"], "questions": data["questions"]})
            else:
                judgment = data["questions"]
    return statute, judgment, failures


_MONTHS = {name: number for number, names in enumerate((
    ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
    ("august", "aug"), ("september", "sept", "sep"), ("october", "oct"), ("november", "nov"), ("december", "dec")), 1)
    for name in names}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NUMBERED_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4}|\d{2})(?!\d)")
_DAY_FIRST_NAMED = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?({_MONTH})\b\.?,?\s*(\d{{4}})(?!\d)")
_MONTH_FIRST_NAMED = re.compile(rf"\b({_MONTH})\b\.?\s+(\d{{1,2}})\s*(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)")
_MONTH_AND_YEAR = re.compile(rf"\b({_MONTH})\b\.?,?\s+(\d{{4}})(?!\d)")
_YEAR_ONLY = re.compile(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)")
#: v13 (AN.28, B10): a month and year in numbers with no day - "-09-2017", "09/2017" (invented) - read as that month.
_NUMBERED_MONTH = re.compile(r"(?<![\d./-])[-./]?\s*(\d{1,2})\s*[-./]\s*(\d{4})(?!\d)")


def _day(year, month, day):
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _numbered(match):
    first, second, year = (int(part) for part in match.groups())
    if len(match.group(3)) == 2:  # "19/07/21": a paper's two-digit year is this century up to 2030, the last century after
        year += 2000 if year <= 30 else 1900
    return _day(year, second, first) or (_day(year, first, second) if first <= 12 else "")


def _month_year(year, month):
    return f"{year:04d}-{month:02d}" if 1 <= month <= 12 and 1000 <= year <= 2099 else ""


def read_date(words, *, months=False):
    """The date a page gives, as a sortable "YYYY-MM-DD", "YYYY-MM" or "YYYY", read by code and never guessed (plan AN.27, P8):
    numbers day first, as an Indian paper writes them (month first only where that is the only way a day is a day); a month by its
    name; a year alone, or the first year of "1961-62", where that is all the page gives. "" where there is none. Where the words hold
    more than one date, the first."""
    text = " ".join(str(words).casefold().split())
    found = []
    for pattern, build in (
            (_NUMBERED_DATE, _numbered),
            (_DAY_FIRST_NAMED, lambda m: _day(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))),
            (_MONTH_FIRST_NAMED, lambda m: _day(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))),
            (_MONTH_AND_YEAR, lambda m: _month_year(int(m.group(2)), _MONTHS[m.group(1)])),
            *(((_NUMBERED_MONTH, lambda m: _month_year(int(m.group(2)), int(m.group(1)))),) if months else ()),
            (_YEAR_ONLY, lambda m: m.group(1))):
        for match in pattern.finditer(text):
            value = build(match)
            if value:
                found.append((match.start(), value))
                break
    return min(found)[1] if found else ""


def _documents(context):
    """The documents of a turn's context, each with its pages in reading order: a document is the pages that share a source - the
    turn it was sent with and its place among that turn's documents - so two files of one name stay two documents."""
    documents = {}
    for row in context.get("documents", ()):
        key = row["source_id"].rsplit("p", 1)[0]
        about = row["document"]
        documents.setdefault(key, {"source": key, "name": about["name"], "recording": bool(about.get("recording")),
                                   "pages": []})["pages"].append(
            {"document": about["name"], "page": about.get("page"), "text": row["text"]})
    return list(documents.values())


def _windows(pages):
    """A document's pages in stretches of at most CHRONOLOGY_WINDOW characters, a page never cut; a page longer than that is a
    stretch of its own."""
    windows, current, size = [], [], 0
    for page in pages:
        if current and size + len(page["text"]) > CHRONOLOGY_WINDOW:
            windows.append(current)
            current, size = [], 0
        current.append(page)
        size += len(page["text"])
    return windows + ([current] if current else [])


def _window_text(document, pages):
    lines = [f'Document: "{document["name"]}"' + (" (a recording, transcribed by AI)" if document["recording"] else "")]
    for page in pages:
        lines.append(f"\n[{'Part' if document['recording'] else 'Page'} {page['page']}]\n{page['text']}")
    return "\n".join(lines)


def _anchor(words, pages):
    """Where an event's words are found, by the one finder and never by the model (plan AN.27, P8 and P8c): whether every passage
    of them is on the pages of its document, and the numbers of the pages they are on."""
    held = [pages.holding(piece) for piece in fact_pieces(words)]
    anchored = bool(held) and all(found is not None for found in held)
    return anchored, (sorted({page["page"] for found in held if found for page in found}) if anchored else [])


def _file_context(context, documents, document, window, whole):
    """What a v13 record step is shown before the pages it reads for (plan AN.28, D1): the advocate's messages, oldest first, and,
    where the file is within WHOLE_FILE_TOKENS, every other page of it under its paper's name - so that the step knows what the
    matter is about and who is who while it answers for its own pages."""
    said = [row["text"] for row in context.get("conversation", ()) if row.get("record_role") == "original_account"]
    latest = (context.get("latest") or {}).get("text")
    lines = ["The advocate's messages, oldest first:", *(f"- {words}" for words in [*said, *([latest] if latest else [])])]
    focus = {page["page"] for page in window}
    rest = [(other, page) for other in documents for page in other["pages"]
            if not (other["source"] == document["source"] and page["page"] in focus)] if whole else []
    if rest:
        lines += ["", "The rest of the file, for context - the pages you do not read for:"]
        lines += [f'Paper "{other["name"]}", {"part" if other["recording"] else "page"} {page["page"]}: {page["text"]}'
                  for other, page in rest]
    return "\n".join(lines)


def _whole_file(context, documents):
    """Whether the whole file is shown to each call of a v13 record step: its pages and the advocate's messages within
    WHOLE_FILE_TOKENS (D1: "a safe fixed limit like 100k tokens"); above it, each call sees the pages it reads for."""
    said = " ".join(row["text"] for row in context.get("conversation", ()) if row.get("record_role") == "original_account")
    pages = " ".join(page["text"] for document in documents for page in document["pages"])
    return estimate_tokens(said + " " + pages) <= WHOLE_FILE_TOKENS


def _read_stretches(model, context, wanted, operation, system, schema, step, shape, whole=None):
    """What the documents of a turn record of one kind, read for it (plan AN.27, P8 and P13d): one call for each document, or each
    stretch of a long one, all at once; shape(data, document, finder) makes the records one stretch's answer holds. Returns
    (records, failures). A stretch whose answer was cut off is read again in two halves, twice at most; a stretch that could not be
    read is a failure, never an empty success; a usage limit still stops the turn. wanted: asked once before any call; False and
    nothing is read."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], []
    tasks = [(document, window) for document in documents for window in _windows(document["pages"])]
    finders = {document["source"]: Pages(document["pages"]) for document in documents}

    def read(task, depth=0):
        document, window = task
        first, last = window[0]["page"], window[-1]["page"]
        user = (_window_text(document, window) if whole is None else
                _file_context(context, documents, document, window, whole) + "\n\nThe pages you read for:\n"
                + _window_text(document, window))
        try:
            data = _call(model, operation, system, user, schema, step)
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation) as exc:
            if isinstance(exc, OutputTruncated) and len(window) > 1 and depth < 2:
                # A stretch with more records than one answer holds is read again in two halves (twice at most).
                middle = len(window) // 2
                (one, lost), (two, also) = read((document, window[:middle]), depth + 1), read((document, window[middle:]), depth + 1)
                return one + two, lost + also
            return [], [{"document": document["name"], "pages": f"{first}-{last}" if first != last else f"{first}",
                         "reason": type(exc).__name__}]
        return shape(data, document, finders[document["source"]]), []

    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
        done = list(pool.map(read, tasks))
    return [record for found, _ in done for record in found], [failure for _, lost in done for failure in lost]


def _numbered_by_date(records, prefix, months=False):
    """Records ordered by the date code reads from each - the undated last, in the papers' order - and numbered prefix1....
    months: v13 reads a numbered month and year as that month."""
    for record in records:
        record["sort"] = read_date(record["date"], months=months)
    ordered = sorted(enumerate(records), key=lambda pair: (0, pair[1]["sort"], pair[0]) if pair[1]["sort"] else (1, "", pair[0]))
    return [{"id": f"{prefix}{number}", **record} for number, (_, record) in enumerate(ordered, 1)]


def _events_in(data, document, finder):
    events = []
    for item in data["events"]:
        words = item["words"].strip()
        anchored, pages = _anchor(words, finder)
        events.append({"date": item["date"].strip(), "kind": item["kind"], "what": item["what"].strip(),
                       "said_by": item["said_by"].strip(), "document": document["name"], "source": document["source"],
                       "pages": pages, "words": words, "anchored": anchored})
    return events


#: v13 (AN.28, D1-D3): the chronology of one paper, read with the whole file in view.
CHRONOLOGY_V13 = """Message: You receive an advocate's messages to us about a client's matter, the documents they sent, and the pages of one paper you read for now: the rest of the file comes first, page by page under each paper's name, and the pages you read for last, under "The pages you read for". A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. A page read from a scan may carry [illegible] and square-bracket notes about stamps, signatures and handwriting; those are the reader's, not the document's. The rest of the file is there so that you know what the matter is about and who is who: list only what the pages you read for record.

Purpose: Set out that paper's own chronology for the advocate and for our research assistant: every event, order, direction, filing, transaction and proceeding it records or reports, so that nothing in it is overlooked when the matter's history is told. You are not judging which account is right, and you are not answering any legal question.

Look for:
- Each event the paper records, whatever its date: a sale, partition or other deed, a mutation or entry in a revenue or other record, an order or direction of a court or authority, an appeal, revision, petition, suit, complaint, FIR or charge sheet, a notice, a hearing or listing, a payment, a death; and each proceeding it says is pending, with its stage.
- When the event happened, as the page gives it ("30-10-1985", "17 August 2019", "2008", "1961-62"). A sentence often names the date of an earlier order, deed or filing it mentions: that date is that earlier act's, not this event's. Where the page gives no date for this event, say undated. Do not work out, convert or guess a date.
- For an order or direction: what the authority found and what it directed, as the page records them. For a filing, appeal or proceeding: who brought it and who answers it, as the page names them.
- Who says it: the paper's own author, or the party or authority it reports; a party's allegation stays that party's.
- The figures and identifiers that belong to the event - extents, sums, and deed, case, file, account or survey numbers - exactly as the page gives them.
- One event for each act. A paper that recites the same act again - a party's account and its written arguments, an order's own recital - records one event: list it once. Do not merge events the paper keeps apart, and add nothing the page does not say. A register or list of many similar entries is one event for the whole list, naming its range and the figures that matter.
Work in a loop: list the events page by page, then read each page again against your list for any event you skipped or misread, or any date you gave to the wrong act, and correct the list before you answer.

Outcome: events, in the order of the pages. Each has: date; kind (transaction, order, filing, pending, or other); what (plain sentences saying what happened, with its figures and identifiers - what an order found and directed, who brought and who answers a proceeding); said_by (whose words they are: the document's own author, or the party or authority it reports); words (the exact words on a page that record it, copied exactly as the page gives them, without the reader's square-bracket notes - a sentence that runs over a page may be copied whole - or several passages joined with '...'; never reword)."""
#: v13 (AN.28, D2): one look again at a paper's events where code found what it could not check.
CHRONOLOGY_CHECK = """Message: You listed the events one paper an advocate sent records; you receive that paper's pages, each under its number, and what code found when it checked your list: events whose words it could not find on the pages, or whose date is in neither their words nor their pages (to_check, each with why and, where code found them, the page's own words nearest to yours), and dates that stand on the pages but in none of your events (not_carried). A page says what its document says; square-bracket notes are the reader's, not the document's.

Purpose: Look again so that every event the paper records is in the list, dated as the paper dates it, with words that stand on its pages.

For each event in to_check: give it again, corrected - its words copied exactly from the page as they stand, a misread letter included, its date the date the paper gives for this act - or leave it out if the paper does not record it as you listed it. For each date in not_carried: give the event the paper records with it, if it marks one; give nothing for a date that marks no event (a stamp's date, a reference to a printed form).
Work in a loop: read the pages again, decide each, check what you write against the page, and correct it.

Outcome: events: only those you give again or add, each as before - date; kind; what; said_by; words."""
#: A paper's dates code finds on its pages to ask about at most (v13): the rest are not asked about.
NOT_CARRIED_MOST = 20


def _numbers(words):
    """The numbers some words hold, a month written as a name counted as its number, a number written in words as its number (the
    twelfth day of June nineteen ninety one: extents.numbers_in_words), and a two-digit year as the years it may stand for: what a
    date's numbers must be found among (v13)."""
    found = {int(n) for n in re.findall(r"\d+", str(words))} | extents.numbers_in_words(words)
    found |= {_MONTHS[name] for name in re.findall(rf"\b({_MONTH})\b", str(words).casefold())}
    return found | {n % 100 for n in found if n >= 1000} | {2000 + n for n in found if n < 100} | {1900 + n for n in found if n < 100}


def _traceable(event, finder):
    """Whether an event's date stands in its own paper (v13, AN.28 D3): every number of the date, a month by name or number and a
    year by four digits or its last two, among its words and its paper's pages - a paper may give a date on another page than the
    passage it belongs to. A date no page of the paper gives was worked out or taken from elsewhere. An undated event is
    traceable; an event whose words are not found is not checked here (it is not anchored)."""
    if not read_date(event["date"], months=True) or not event["anchored"]:
        return True
    held = _numbers(event["words"])
    for page in finder.pages:
        held |= _numbers(_reading(page["text"]))
    return {n for n in _numbers(event["date"]) if n} - {0} <= held


#: Dates as a page writes them in full, day, month and year (v13): numbered, or with the month named.
_PAGE_DATE = re.compile(rf"(?<!\d)\d{{1,2}}\s*[-./]\s*\d{{1,2}}\s*[-./]\s*\d{{4}}(?!\d)|(?<!\d)\d{{1,2}}\s*(?:st|nd|rd|th)?\s*"
                        rf"(?:day\s+of\s+)?(?:{_MONTH})\b\.?,?\s*\d{{4}}(?!\d)|\b(?:{_MONTH})\b\.?\s+\d{{1,2}}\s*(?:st|nd|rd|th)?,?\s+\d{{4}}(?!\d)")


def _not_carried(document, events, unread=()):
    """The dates on a paper's pages, outside the reader's notes, that none of its events carries (v13): each once, as the page
    writes it, with its page, in the papers' order; NOT_CARRIED_MOST at most. unread: the pages whose reading failed, which a
    failure already names and which are not asked about again."""
    carried = {event["sort"] for event in events if event["source"] == document["source"]}
    found, seen = [], set()
    for page in document["pages"]:
        if page["page"] in unread:
            continue
        for match in _PAGE_DATE.finditer(_reading(page["text"]).casefold()):
            day = read_date(match.group(0), months=True)
            if day and len(day) == 10 and day not in carried and day not in seen:
                seen.add(day)
                found.append({"date": match.group(0), "page": page["page"]})
    return found[:NOT_CARRIED_MOST]


def _unread(failures, document):
    """The pages of a paper a failure names (v13): "3" or "1-4"."""
    pages = set()
    for failure in failures:
        if failure["document"] == document["name"]:
            first, _, last = str(failure["pages"]).partition("-")
            if first.isdigit() and (last or first).isdigit():
                pages |= set(range(int(first), int(last or first) + 1))
    return pages


def _checked(model, context, events, documents, finders, failures=()):
    """v13 (AN.28, D2 and D3): each paper's events checked by code - their words found, their dates traceable - and, for a paper
    where some are not or a date on its pages is carried by none, one check call that looks again; its events replace those
    that failed and add those it finds. An event still untraceable keeps its words and loses its date ("undated"); one whose
    words are still not found stays, marked not anchored."""
    out = []
    for document in documents:
        mine = [event for event in events if event["source"] == document["source"]]
        finder = finders[document["source"]]
        failing = [event for event in mine if not event["anchored"] or not _traceable(event, finder)]
        missing = _not_carried(document, [{**event, "sort": read_date(event["date"], months=True)} for event in mine],
                               _unread(failures, document))
        if failing or missing:
            to_check = [{"date": event["date"], "what": event["what"], "words": event["words"],
                         "why": "its words are not found on the pages" if not event["anchored"]
                         else "its date is in neither its words nor its pages",
                         **({"nearest_words": near["words"]} if not event["anchored"] and (near := finder.nearest(event["words"]))
                            else {})} for event in failing]
            user = (_window_text(document, document["pages"]) + "\n\n"
                    + json.dumps({"to_check": to_check, "not_carried": missing}, ensure_ascii=False))
            try:
                data = _call(model, "core_research_chronology", CHRONOLOGY_CHECK, user, CHRONOLOGY_SCHEMA, "chronology_check")
                kept = [event for event in mine if event not in failing]
                # A model that gives the paper's whole list again adds only what is new: an event already kept is not
                # kept twice.
                held = {(event["date"], event["kind"], event["words"]) for event in kept}
                mine = kept + [event for event in _events_in(data, document, finder)
                               if (event["date"], event["kind"], event["words"]) not in held]
            except UsageLimitReached:
                raise
            except (ModelError, SchemaViolation):
                pass
        for event in mine:
            if event["anchored"] and not _traceable(event, finder):
                event["date"] = "undated"
        out += mine
    return out


def chronology_of(model, context, *, wanted=None):
    """The chronology the documents of a turn record, as (events, failures) - plan AN.27, P8.

    The model says what a page records; code does the rest: finds the event's words in the document (the one finder), records the
    pages, reads the date, orders the events by it - the undated last, in the papers' order - and numbers them E1.... An event
    whose words are not found is kept, marked not anchored, never dropped and never to be cited as sourced."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], []
    events, failures = _read_stretches(model, context, None, "core_research_chronology", CHRONOLOGY_V13, CHRONOLOGY_SCHEMA,
                                       "chronology", _events_in, whole=_whole_file(context, documents))
    events = _checked(model, context, events, documents, {document["source"]: Pages(document["pages"])
                                                          for document in documents}, failures)
    return _numbered_by_date(events, "E", months=True), failures


#: How much of the shorter of two quotations the longer must hold, but for scan noise, for them to be one passage quoted to different
#: lengths (plan AN.27, P22). On the replay of the reviewed bundle the events that are the same passage hold 0.86 to 1.0 of it, and
#: those that are not - however near in day, kind and page - held no more than 0.37; the line is between, nearer the scan noise a
#: copy may carry than the likeness of two orders of one day.
SAME_PASSAGE = 0.75
#: A quotation of fewer words says too little about which event it is.
SAME_PASSAGE_WORDS = 4
_PASSAGE_WORD = re.compile(r"[^\W_]+")


def _held_in(left, right):
    """How much of the shorter quotation the longer holds, 0 to 1: the words of the shorter that stand in runs of two or more beside
    the same words of the longer, over the words of the shorter. A passage quoted to different lengths holds all of itself, a scan's
    noise costs a word or two, and two sentences that share only the words of any order hold little. 0 where the shorter has fewer
    than SAME_PASSAGE_WORDS words."""
    shorter, longer = sorted((_PASSAGE_WORD.findall(left.casefold()), _PASSAGE_WORD.findall(right.casefold())), key=len)
    if len(shorter) < SAME_PASSAGE_WORDS:
        return 0.0
    blocks = difflib.SequenceMatcher(None, shorter, longer, autojunk=False).get_matching_blocks()
    return sum(block.size for block in blocks if block.size >= 2) / len(shorter)


def events_once(events, copies):
    """The chronology's events with an event that several papers record counted once (plan AN.27, P22): what a paper that is a copy of
    another says again is the same event, and it is shown once with the other papers named. events: the plan's events, in its order.
    copies: the pairs of pages that are copies of one page, as copy_figures.copies finds them - {(a paper's key, a page), (a paper's
    key, a page)}. Returns [{"event": the one that stands for them, "also": the others}] in the order of the first of each.

    Two events are one when they have the same day as code reads it (or both are undated) and the same kind; are read in different
    papers, and not in a paper that already has one of the group; are on pages that are copies of one another; and the shorter
    quotation is, but for scan noise, wholly inside the longer. An event joins the group it is likeliest to belong to, and stands
    alone if it matches none - as does one whose words were not found on a page. The fullest quotation stands for the group. The
    plan is never changed: each paper's own reading stays as it was made."""
    copies = copies or ()
    groups, buckets = [], {}
    for event in events:
        places = {(event["source"], number) for number in event["pages"]} if event["anchored"] else set()
        joins, likeness = None, 0.0
        if places:
            for group in buckets.get((event["sort"], event["kind"]), ()):
                if event["source"] in group["sources"] or not any(frozenset({kept, new}) in copies for kept in group["places"] for new in places):
                    continue
                held = max(_held_in(event["words"], member["words"]) for member in group["members"])
                if held >= SAME_PASSAGE and held > likeness:
                    joins, likeness = group, held
        if joins is None:
            joins = {"members": [], "sources": set(), "places": set()}
            groups.append(joins)
            buckets.setdefault((event["sort"], event["kind"]), []).append(joins)
        joins["members"].append(event)
        joins["sources"].add(event["source"])
        joins["places"] |= places
    shown = []
    for group in groups:
        stands = max(group["members"], key=lambda member: len(member["words"]))
        shown.append({"event": stands, "also": [member for member in group["members"] if member is not stands]})
    return shown


def _transfers_in(data, document, finder):
    transfers = []
    for item in data["transfers"]:
        words = item["words"].strip()
        anchored, pages = _anchor(words, finder)
        transfers.append({"date": item["date"].strip(), "kind": item["kind"], "parcel": item["parcel"].strip(),
                          "extent": item["extent"].strip(), "total": item["total"].strip(), "from": item["from"].strip(),
                          "to": item["to"].strip(), "document": document["name"], "source": document["source"], "pages": pages,
                          "words": words, "anchored": anchored,
                          # v13 (AN.28): the model's plain reading of the figure and the document that records it.
                          "reading": item.get("reading", "").strip(), "instrument": item.get("instrument", "").strip()})
    return transfers


#: v13 (AN.28, D1, D3, D7, B16): the transactions of one paper, of any kind, read with the whole file in view.
TRANSACTIONS_V13 = """Message: You receive an advocate's messages to us about a client's matter, the documents they sent, and the pages of one paper you read for now: the rest of the file comes first, page by page under each paper's name, and the pages you read for last, under "The pages you read for". A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. Square-bracket notes are the reader's, not the document's. The rest of the file is there so that you know what the matter is about and who is who: list only what the pages you read for record.

Purpose: List the transactions those pages record or report - whatever moves property, money, shares, goods or a right from one person to another: a sale, partition, gift, settlement, decree, lease, mortgage, loan or payment - so that code can add the figures up for each property, account or subject and set them against any whole the papers state. You are not adding or working out anything yourself, and you are not judging which account is right.

Look for:
- Each transaction, whatever its date: who gave it up (from), who took it (to), what it concerns (parcel: the property, account or subject as the page names it - a survey, house or account number, with any sub-number), the figure transferred exactly as the page writes it (extent: an area, a sum, a share), the same figure in plain words with its unit, so that it reads only one way - acres and guntas, or acres and cents, as the paper means them (reading: for example "3 acres 12 guntas", "1 acre 18 cents", "Rs 200000", "a one-third share"), the number of the document that records it as the page writes it (instrument: a deed, agreement, cheque or order number, with its year; empty where none is given), and the date as the page gives it ("undated" where it gives none).
- The whole of what the transaction concerns, where the same passage states it (for example "out of Ac.8.00 in the plot", invented), exactly as written; otherwise leave it empty.
- The exact words on a page that record the transaction, copied exactly as the page gives them, without the reader's square-bracket notes - or several passages joined with '...'; never reword.
- One entry for each transaction. A paper that reports the same transaction again records one: give it once. Do not list a transaction that gives no figure, do not add or work out a figure the page does not give, and do not merge transactions the page keeps apart.
Work in a loop: list the transactions page by page, then read each page again against your list for any transaction, figure, document number or date you skipped or misread, and correct the list before you answer.

Outcome: transfers, in the order of the pages. Each has: date; kind (sale, partition, gift, settlement, decree, lease, mortgage, loan, payment, or other); parcel; extent; reading; total; from; to; instrument; words."""


#: v13 (AN.28, D2 and D3): one look again at a paper's transactions where code found what it could not use.
TRANSACTIONS_CHECK = """Message: You listed the transactions one paper an advocate sent records; you receive that paper's pages, each under its number, and what code found when it checked your list (to_check): transactions whose words it could not find on the pages, whose figure or whole is not in those words, whose figure code reads otherwise than your reading of it, or whose date is in neither their words nor their pages - each with why and, where code found them, the page's own words nearest to yours. A page says what its document says; square-bracket notes are the reader's, not the document's.

Purpose: Look again so that every transaction is listed as the paper records it, with words that stand on its pages and a figure and a whole that stand in those words.

For each transaction in to_check: give it again, corrected - its words copied exactly from the page as they stand, a misread letter included, and long enough to hold its figure and any whole it gives; its figure and whole exactly as those words write them, with your plain reading of the figure and its unit, so that it reads only one way; its date the date the paper gives for this transaction - or leave it out if the paper does not record it as you listed it.
Work in a loop: read the pages again, decide each, check what you write against the page, and correct it.

Outcome: transfers: only those you give again, each as before - date; kind; parcel; extent; reading; total; from; to; instrument; words."""


#: v13 (AN.28, D1, piece 3e): the papers read side by side for what matters to the client.
CONNECTIONS_V13 = """Message: You receive an advocate's messages to us about a client's matter and every paper they sent, page by page under each paper's name. A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. Square-bracket notes are the reader's, not the document's.

Purpose: Set the papers side by side and find what matters to the advocate's client only when two papers, or two parts of one, are read together, so that nothing that bears on the client is missed because it sits in another paper. You are not answering a legal question, and you are not judging which account is right.

Look for:
- Whom the advocate acts for, from their messages, and the client's people the papers name - members of the family, predecessors and successors in interest, partners, agents - each name exactly as a page writes it (client_people).
- Where the client or one of the client's people appears in another paper or in another proceeding than the one the advocate speaks of: as a party, an applicant or respondent, a buyer or seller, a witness.
- A finding, order or statement in one paper that goes against the client's position or claim in another.
- An act a paper records that is dated after a party's death another paper records, or after a time limit or an order another paper states.
- A property, account, contract, policy or proceeding a paper connects to the client that the advocate has not mentioned.
- Anything else that only reading two papers together shows and that a careful lawyer would want the advocate to know.
For each, the point in plain words, why it matters to the client, and the exact words on the pages that show it - each passage copied exactly as the page gives it, without the reader's notes, and passages from different pages or papers joined with '...'; never reword.
Work in a loop: read every paper, list the points, then read the papers again against your list for any point you missed or misread, and correct the list before you answer.

Outcome: client_people (names as the pages write them); connections, each with: kind (client_appears, against_client, after_death, after_time_limit, further_subject, or other); point; why_it_matters; words."""
#: v13: one look again at the points whose words code could not find.
CONNECTIONS_CHECK = """Message: You set the papers an advocate sent side by side and listed points that matter to the client; you receive the advocate's messages, the papers, and the points whose words code could not find on the pages (to_check), each with, where code found them, the page's own words nearest to yours. A page says what its document says; square-bracket notes are the reader's, not the document's.

Purpose: Look again so that each point rests on words that stand on the pages.

For each point in to_check: give it again with its words copied exactly from the pages as they stand, a misread letter included, passages from different pages joined with '...' - or leave it out if the papers do not show it.
Work in a loop: read the pages again, decide each, check what you write against the page, and correct it.

Outcome: client_people (as before); connections: only those you give again, each as before - kind; point; why_it_matters; words."""
#: How much of a name's letters a run of as many words must share to be offered as a near spelling of it (v13): a candidate, never
#: the name; and how many such candidates are offered for one name at most.
NEAR_NAME = 0.85
NEAR_MOST = 10
_NAME_WORD = re.compile(r"[^\W_]+")
#: What a failure of the connections step names in place of one paper: it reads them all.
ALL_PAPERS = "the papers together"


def _all_pages(documents):
    """Every page of every paper, as one finder reads them: each tagged with its paper's source, so two papers stay two."""
    return [{"document": document["source"], "name": document["name"], "page": page["page"], "text": page["text"]}
            for document in documents for page in document["pages"]]


def _papers_text(context, documents):
    """What the connections step is shown: the advocate's messages, oldest first, and every page of every paper under its name."""
    said = [row["text"] for row in context.get("conversation", ()) if row.get("record_role") == "original_account"]
    latest = (context.get("latest") or {}).get("text")
    lines = ["The advocate's messages, oldest first:", *(f"- {words}" for words in [*said, *([latest] if latest else [])]), "",
             "The papers:"]
    for document in documents:
        lines.append(f'\nPaper "{document["name"]}"' + (" (a recording, transcribed by AI)" if document["recording"] else ""))
        lines += [f"[{'Part' if document['recording'] else 'Page'} {page['page']}]\n{page['text']}" for page in document["pages"]]
    return "\n".join(lines)


def _anchor_across(words, finder):
    """Where a connection's words are, by the one finder (v13): whether every passage is on a page of some paper - a connection's
    passages may stand in different papers - and the places they are on, each once, in the order found."""
    held = [finder.holding(piece) for piece in fact_pieces(words)]
    anchored = bool(held) and all(found is not None for found in held)
    places = []
    for found in held if anchored else ():
        for page in found:
            place = {"document": page["name"], "source": page["document"], "page": page["page"]}
            if place not in places:
                places.append(place)
    return anchored, places


def _connections_in(data, finder):
    out = []
    for item in data["connections"]:
        words = item["words"].strip()
        anchored, places = _anchor_across(words, finder)
        out.append({"kind": item["kind"], "point": item["point"].strip(), "why_it_matters": item["why_it_matters"].strip(),
                    "words": words, "anchored": anchored, "places": places})
    return out


def _appearances(names, documents):
    """Where each of the client's people stands on the papers' pages, found by code (v13, AN.28 piece 3e): the name as a run of
    words, letter case and punctuation aside; and, for a name of two words or more, runs of as many words that read nearly as the
    name (NEAR_NAME of their letters alike) - candidates only, never taken to be the name, NEAR_MOST at most."""
    pages = [(document, page, _NAME_WORD.findall(page["text"])) for document in documents for page in document["pages"]]
    out = []
    for name in names:
        wanted = [word.casefold() for word in _NAME_WORD.findall(name)]
        if not wanted:
            continue
        joined, places, near = " ".join(wanted), [], []
        for document, page, words in pages:
            lowered = [word.casefold() for word in words]
            place = {"document": document["name"], "source": document["source"], "page": page["page"]}
            for start in range(len(words) - len(wanted) + 1):
                run = lowered[start:start + len(wanted)]
                if run == wanted:
                    if place not in places:
                        places.append(place)
                elif len(wanted) > 1 and len(near) < NEAR_MOST:
                    alike = difflib.SequenceMatcher(None, " ".join(run), joined)
                    if alike.real_quick_ratio() >= NEAR_NAME and alike.quick_ratio() >= NEAR_NAME and alike.ratio() >= NEAR_NAME:
                        near.append({"as_written": " ".join(words[start:start + len(wanted)]), **place})
        out.append({"name": name, "places": places, "near": near})
    return out


def connections_of(model, context, *, wanted=None):
    """What matters to the client only when the papers are read side by side, as (connections, client_people, appearances,
    failures) - research v13 (plan AN.28, D1-D3, piece 3e). One call reads every paper with the advocate's messages, within
    WHOLE_FILE_TOKENS; above that the papers are not read together and a failure says so. Code finds each point's words on the
    pages, and the points whose words it cannot find are looked at again once; one still not found is kept, marked not anchored.
    Code finds where each of the client's people the model names stands on the pages (_appearances). wanted: asked once, before any
    call; False and nothing is read."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], [], [], []
    if not _whole_file(context, documents):
        return [], [], [], [{"document": ALL_PAPERS, "pages": "all", "reason": "TooLongToReadTogether"}]
    finder = Pages(_all_pages(documents))
    user = _papers_text(context, documents)
    try:
        data = _call(model, "core_research_connections", CONNECTIONS_V13, user, CONNECTIONS_SCHEMA, "connections")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        return [], [], [], [{"document": ALL_PAPERS, "pages": "all", "reason": type(exc).__name__}]
    found = _connections_in(data, finder)
    failing = [item for item in found if not item["anchored"]]
    if failing:
        to_check = [{"kind": item["kind"], "point": item["point"], "words": item["words"],
                     **({"nearest_words": near["words"]} if (near := finder.nearest(item["words"])) else {})} for item in failing]
        try:
            again = _call(model, "core_research_connections", CONNECTIONS_CHECK,
                          user + "\n\n" + json.dumps({"to_check": to_check}, ensure_ascii=False), CONNECTIONS_SCHEMA,
                          "connections_check")
            kept = [item for item in found if item["anchored"]]
            held = {(item["kind"], item["point"], item["words"]) for item in kept}
            found = kept + [item for item in _connections_in(again, finder) if (item["kind"], item["point"], item["words"]) not in held]
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation):
            pass
    people = list(dict.fromkeys(" ".join(name.split()) for name in data["client_people"] if name.strip()))
    return ([{"id": f"C{number}", **item} for number, item in enumerate(found, 1)], people, _appearances(people, documents), [])


def _connection_issues(data, context):
    """What a v13 plan records of the papers read side by side, checked against the turn's documents (piece 3e): the points numbered
    C1... in order, each anchored and placed as the one finder finds its words, and the client's appearances as code finds their
    names; anything else raises SchemaViolation. A failure of the step is an issue: the papers were not read together."""
    documents = _documents(context)
    finder = Pages(_all_pages(documents))
    for number, item in enumerate(data["connections"], 1):
        if item["id"] != f"C{number}":
            raise SchemaViolation(f"Connection {number} is numbered {item['id']}, not C{number}")
        if (item["anchored"], item["places"]) != _anchor_across(item["words"], finder):
            raise SchemaViolation(f"Connection {item['id']} is not anchored as its words are found in the papers")
    if data.get("appearances", []) != _appearances(data.get("client_people", []), documents):
        raise SchemaViolation("The client's people are not where code finds their names on the pages")
    for failure in data.get("connections_failures", []):
        if failure["document"] != ALL_PAPERS:
            raise SchemaViolation("A failure of the papers read together names one paper")
    return [{"work_id": None, "mismatch": f"the papers read together unavailable: {failure['reason']}", "proposal": deepcopy(failure)}
            for failure in data.get("connections_failures", [])]


def _transfer_fault(transfer, finder):
    """Why code cannot use a v13 transaction as the model listed it, or None: its words not on the pages, its figure or whole as
    extents.fault finds them, or its date in neither its words nor its paper's pages."""
    if not transfer["anchored"]:
        return "its words are not found on the pages"
    return extents.fault(transfer) or (None if _traceable(transfer, finder) else "its date is in neither its words nor its pages")


def _checked_transfers(model, transfers, documents, finders):
    """v13 (AN.28, D2 and D3): each paper's transactions checked by code and, for a paper where some cannot be used as listed, one
    check call that looks again; what it gives replaces those at fault. One still at fault is kept as it is - the ledger lists it and
    never adds it - and one whose date is still not in its paper keeps its words and loses its date ("undated")."""
    out = []
    for document in documents:
        mine = [transfer for transfer in transfers if transfer["source"] == document["source"]]
        finder = finders[document["source"]]
        failing = [(transfer, why) for transfer in mine if (why := _transfer_fault(transfer, finder))]
        if failing:
            to_check = [{**{key: transfer[key] for key in ("date", "kind", "parcel", "extent", "reading", "total", "from", "to",
                                                          "instrument", "words")}, "why": why,
                         **({"nearest_words": near["words"]} if not transfer["anchored"]
                            and (near := finder.nearest(transfer["words"])) else {})} for transfer, why in failing]
            user = (_window_text(document, document["pages"]) + "\n\n"
                    + json.dumps({"to_check": to_check}, ensure_ascii=False))
            try:
                data = _call(model, "core_research_transfers", TRANSACTIONS_CHECK, user, TRANSACTIONS_SCHEMA, "transfers_check")
                kept = [transfer for transfer in mine if all(transfer is not wrong for wrong, _ in failing)]
                # A model that gives the paper's whole list again adds only what is new: one already kept is not kept twice.
                held = {_same_transfer(transfer) for transfer in kept}
                mine = kept + [transfer for transfer in _transfers_in(data, document, finder) if _same_transfer(transfer) not in held]
            except UsageLimitReached:
                raise
            except (ModelError, SchemaViolation):
                pass
        for transfer in mine:
            if transfer["anchored"] and not _traceable(transfer, finder):
                transfer["date"] = "undated"
        out += mine
    return out


def _same_transfer(transfer):
    return tuple(transfer[key] for key in ("date", "kind", "parcel", "extent", "words"))


def transfers_of(model, context, *, wanted=None):
    """The transactions the documents of a turn record, as (transfers, failures) - plan AN.27, P13d; from research v13 of any kind
    (AN.28, D7). Read, anchored, dated, ordered and numbered X1... exactly as the chronology's events are, each paper read with the
    whole file in view and looked at again once where code cannot use what it found (D2, D3); the figures are read and added by
    extents.py, never here."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], []
    transfers, failures = _read_stretches(model, context, None, "core_research_transfers", TRANSACTIONS_V13, TRANSACTIONS_SCHEMA,
                                          "transfers", _transfers_in, whole=_whole_file(context, documents))
    transfers = _checked_transfers(model, transfers, documents, {document["source"]: Pages(document["pages"])
                                                                 for document in documents})
    return _numbered_by_date(transfers, "X", months=True), failures


def _stretch_issues(items, failures, context, *, prefix, label, noun, unavailable, months=False):
    """What a v12 plan records of one kind that the papers were read for, checked against the documents of the turn (plan AN.27,
    P8c and P13d), and the issues it raises. It must be what the reading makes of those papers: the items numbered prefix1... in
    the order of their dates, the undated last, each of a document the turn holds, its date read as read_date reads it, and its
    words found on the pages recorded - or on none, and marked not anchored - as the one finder finds them in that document;
    anything else raises SchemaViolation. A stretch that could not be read is an issue, since part of a paper was not read; an item
    whose words are not found is marked not anchored and is not an issue."""
    documents = {document["source"]: document for document in _documents(context)}
    finders = {source: Pages(document["pages"]) for source, document in documents.items()}
    last = None
    for number, item in enumerate(items, 1):
        name = item["id"]
        if name != f"{prefix}{number}":
            raise SchemaViolation(f"{label} {number} is numbered {name}, not {prefix}{number}")
        document = documents.get(item["source"])
        if document is None or document["name"] != item["document"]:
            raise SchemaViolation(f"{label} {name} belongs to no document of this turn")
        if item["sort"] != read_date(item["date"], months=months):
            raise SchemaViolation(f"{label} {name} is dated otherwise than its date reads")
        key = (0, item["sort"]) if item["sort"] else (1, "")
        if last is not None and key < last:
            raise SchemaViolation(f"{label} {name} is out of the order of dates")
        last = key
        if (item["anchored"], item["pages"]) != _anchor(item["words"], finders[item["source"]]):
            raise SchemaViolation(f"{label} {name} is not anchored as its words are found in its document")
    names = {document["name"] for document in documents.values()}
    for failure in failures:
        if failure["document"] not in names:
            raise SchemaViolation(f"A {noun} failure names no document of this turn")
    return [{"work_id": None, "mismatch": f"{unavailable} unavailable for {failure['document']} (pages {failure['pages']}): "
                                          f"{failure['reason']}", "proposal": deepcopy(failure)} for failure in failures]


def _chronology_issues(events, failures, context, months=False):
    return _stretch_issues(events, failures, context, prefix="E", label="Chronology event", noun="chronology",
                           unavailable="chronology", months=months)


def _transfer_issues(transfers, failures, context, months=False):
    return _stretch_issues(transfers, failures, context, prefix="X", label="Transfer", noun="transfer", unavailable="transfers",
                           months=months)


def plan(model, context, interpretation=None, *, progress=None, wanted=None, restrictions=None):
    """The v7 reasoning loop. Expected model failures after the first understanding are
    recorded where they occur; independent work continues. The loop reads the
    conversation itself; the interpretation only spares it for a message that carries
    no information or request. wanted: asked before each step after the first, when the
    loop runs beside the interpretation (18 Oct 2026); it may wait for the interpretation,
    and once it answers False the loop stops there with the plan for no matter. restrictions: asked once, after wanted has
    let the loop go on, what the advocate restricted in their latest message as the interpretation found it (a list of their
    exact words) or None where that is not known; the check and the correction are told (plan AN.27, P4).
    The chronology of the documents, and the transfers of land they record (P13d), are read beside the loop (research v12, plan
    AN.27, P8c): each is started at once, asks wanted before any call, and its result is taken last; a stretch that could not be
    read is recorded, and a usage limit stops the turn."""
    if interpretation is not None and not carries_matter(interpretation):
        return _no_matter(context)
    still = wanted or (lambda: True)
    with ThreadPoolExecutor(max_workers=3) as reading:
        papers = reading.submit(chronology_of, model, context, wanted=still)
        moved = reading.submit(transfers_of, model, context, wanted=still)
        # v13 (AN.28, piece 3e): the papers read side by side, beside the rest.
        linked = reading.submit(connections_of, model, context, wanted=still)
        proposed = _proposal(model, context, still, progress, restrictions)
        if proposed is None:
            return _no_matter(context)
        events, unread = papers.result()
        transfers, unmoved = moved.result()
        connections, people, appearances, unlinked = linked.result()
    return accept({**proposed, "chronology": events, "chronology_failures": unread,
                   "transfers": transfers, "transfers_failures": unmoved,
                   "connections": connections, "connections_failures": unlinked, "client_people": people,
                   "appearances": appearances}, context)


def _proposal(model, context, still, progress, restrictions):
    """What the v7 loop proposes - the understanding, its review and the search phrases - or None where the loop stopped because
    there is no matter (still answered False)."""
    report = progress or (lambda stage, **detail: None)
    text = conversation_text(context)
    report("understanding_matter")
    understanding = _call(model, "core_research_understand", UNDERSTAND, text, UNDERSTANDING_V13, "understand")
    rounds, failures, phrasing, note = [], [], None, None
    with ThreadPoolExecutor(max_workers=1) as beside:
        for number in range(MAX_REVISIONS + 1):
            if not still():
                return None
            if note is None:
                note = _restrictions_note(restrictions() if restrictions is not None else None)
            mechanical = code_checks(understanding, context)
            report("checking_understanding", round=number + 1)
            if number == MAX_REVISIONS:
                # No revision can follow the last check, so the search phrases for this
                # understanding are written beside it (18 Oct 2026).
                phrasing = beside.submit(_phrases, model, understanding, report)
            try:
                review = _call(model, "core_research_check", CHECK, text + note + "\n\nYour colleague's understanding:\n"
                               + json.dumps(understanding, ensure_ascii=False, indent=1), CHECKED, "check")
            except (ModelError, SchemaViolation) as exc:
                rounds.append({"code_problems": mechanical, "verdict": "unavailable", "problems": []})
                failures.append({"step": "check", "scope": f"round {number + 1}", "reason": type(exc).__name__})
                break
            rounds.append({"code_problems": mechanical, **review})
            problems = mechanical + (review["problems"] if review["verdict"] == "revise" else [])
            if not problems or number == MAX_REVISIONS:
                break
            if not still():
                return None
            report("revising_understanding", round=number + 1)
            try:
                revised = _call(model, "core_research_revise", REVISE, text + note + "\n\nYour understanding:\n"
                                + json.dumps(understanding, ensure_ascii=False, indent=1)
                                + "\n\nProblems found:\n" + json.dumps(problems, ensure_ascii=False, indent=1),
                                REVISED_V13, "revise")
            except (ModelError, SchemaViolation) as exc:
                failures.append({"step": "revise", "scope": f"round {number + 1}", "reason": type(exc).__name__})
                break
            understanding = revised["understanding"]
        if phrasing is not None:
            statute, judgment, missed = phrasing.result()
        elif not still():
            return None
        else:
            statute, judgment, missed = _phrases(model, understanding, report)
    return {"understanding": understanding, "review_rounds": rounds, "statute_phrases": statute,
            "judgment_phrases": judgment, "failures": failures + missed}


def _accept_v7(proposal, context, schema=SCHEMA, contract=None):
    data = canonical_schema_data(proposal, schema)
    require_schema(data, schema)
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
    months = contract in WHOLE_FILE
    if "chronology" in data:
        issues.extend(_chronology_issues(data["chronology"], data["chronology_failures"], context, months))
    if "transfers" in data:
        issues.extend(_transfer_issues(data["transfers"], data.get("transfers_failures", []), context, months))
    if "connections" in data:
        issues.extend(_connection_issues(data, context))
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
        return _accept_v7(proposal, context, SCHEMA_V13 if contract in WHOLE_FILE else SCHEMA_V12 if contract in CHRONICLED
                          else SCHEMA if contract in (PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT)
                          else SCHEMA_V8, contract)
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


def _offered(search, kind):
    """What a pick chooses among: what search returned and, for provisions from search v9,
    the provisions connected to them (owner decision P32, 20 Oct 2026). A fallback keeps
    only what search returned."""
    return [*_of_kind(search, kind), *(search.get("connected", ()) if kind == "provision" else ())]


def _connections_said(search, shown):
    """How each offered provision connects to what search returned, in its Act's words."""
    returned, said = {c["id"] for c in _provisions(search)}, {}
    for edge in search.get("connections", ()):
        for here, there in ((edge["from"], edge["to"]), (edge["to"], edge["from"])):
            if there not in returned or here not in shown:
                continue
            if edge["how"] == "beside":
                text = f"beside {shown[there]} in its Act"
            elif here == edge["from"]:
                text = f'it names {shown[there]}: "{edge["words"]}"'
            else:
                text = f'{shown[there]} names it: "{edge["words"]}"'
            said.setdefault(here, []).append(text)
    return said


def _pick_text(plan, searches, labels):
    lines = [f"Matter: {plan['proposal']['understanding']['summary']}"]
    for work in plan["work"]:
        if work["id"] not in searches:
            continue
        label, search = labels[work["id"]], searches[work["id"]]
        lines.append(f"\n{label}: {work['question']}")
        offered, returned = _offered(search, "provision"), len(_provisions(search))
        shown = {candidate["id"]: f"{label}.{number}" for number, candidate in enumerate(offered, 1)}
        said = _connections_said(search, shown)
        for number, candidate in enumerate(offered, 1):
            if number == returned + 1:
                lines.append("  Read with them, as their Acts connect them:")
            source = candidate["source"]
            heading = re.sub(r"\s+", " ", source.get("section_title") or "")[:140]
            # P21 (19 Oct 2026): an Act India Code does not list as in force is said so.
            mark = f" [{in_force(source)}]" if in_force(source) else ""
            line = f"  {label}.{number} {candidate['title']}, section {candidate['locator']}{mark}: {heading}."
            if number <= returned:
                body = (source.get("full_text") or "").splitlines()
                line += " " + re.sub(r"\s+", " ", " ".join(body[1:] or body)).strip()[:220]
            if said.get(candidate["id"]):
                line += " (" + "; ".join(said[candidate["id"]]) + ")"
            counted = search.get("links", {}).get(candidate["id"])
            more = counted and counted["names"] + counted["named_by"] - sum(
                edge["how"] == "names" and candidate["id"] in (edge["from"], edge["to"])
                for edge in search.get("connections", ()))
            if more:
                line += f" (its Act connects {more} more provisions to it, not shown)"
            lines.append(line)
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
                candidate = _offered(searches[work_id], kind)[int(number) - 1]
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


#: Each pick's field in a research record.
_PICK_FIELDS = {"provision": "picks", "judgment": "judgment_picks"}


def dispute_work(plan):
    """The plan's work items by dispute, in the understanding's order: the parts of an answer
    written dispute by dispute (response_writer.parts groups them the same way)."""
    grouped = {}
    disputes = (plan["proposal"].get("understanding") or {}).get("disputes", []) if isinstance(
        plan.get("proposal"), dict) else []
    for dispute in disputes:
        items = [w for w in plan["work"] if w.get("dispute", {}).get("id") == dispute["id"]]
        if items and dispute["id"] not in grouped:
            grouped[dispute["id"]] = items
    return grouped


def _state(plan, searches, failures, picks):
    return "partial" if (plan["issues"] or failures or _picks_open(picks) or any(
        search["state"] == "partial" for search in searches.values())) else "evaluated"


def _part(plan, dispute_id, searches, failures, chosen, judgments, contract=CONTRACT):
    """One dispute's part of a v10 or v11 record: its questions' searches and gaps, its own
    picks and (v11) the judgments it reads."""
    ids = [w["id"] for w in dispute_work(plan)[dispute_id]]
    searches = {i: searches[i] for i in ids if i in searches}
    failures = {i: failures[i] for i in ids if i in failures}
    record = {"contract": contract, "plan": deepcopy(plan), "searches": deepcopy(searches),
              "failures": deepcopy(failures), "part": dispute_id,
              **{field: {dispute_id: deepcopy(chosen[kind])} for kind, field in _PICK_FIELDS.items()},
              **({"judgments": {dispute_id: deepcopy(judgments)}} if contract in JUDGMENTS_READ else {})}
    record["state"] = _state(plan, searches, failures, [chosen[kind] for kind in _PICK_FIELDS])
    return record


def _chosen_cases(plan, searches, pick):
    """The judgments a dispute's pick chose, in the order chosen, at most JUDGMENTS_PER_DISPUTE;
    with what search found of each and what the pick chose of each, by stored position."""
    returned = {c["id"]: c for search in searches.values() for c in _of_kind(search, "judgment")}
    found, chosen = {}, {}
    for candidate in returned.values():
        if candidate["source"].get("case_id"):
            found.setdefault(candidate["source"]["case_id"], set()).add(candidate["position"])
    order = []
    for work in plan["work"]:
        for identity in pick["chosen"].get(work["id"], []) if work["id"] in searches else []:
            candidate = returned.get(identity)
            # A paragraph with no judgment of its own to read is no judgment chosen.
            if candidate is not None and candidate["source"].get("case_id"):
                order.append(candidate["source"]["case_id"])
                chosen.setdefault(candidate["source"]["case_id"], set()).add(candidate["position"])
    cases = list(dict.fromkeys(order))[:JUDGMENTS_PER_DISPUTE]
    return [(case_id, found.get(case_id, set()), chosen.get(case_id, set())) for case_id in cases]


def _extract(paragraphs, found, chosen):
    """The paragraphs of a long judgment its extract keeps, each with why (P31)."""
    positions = [position for position, _ in paragraphs]
    rows = dict(paragraphs)
    why = {}

    def add(position, reason):
        if position in rows and reason not in why.setdefault(position, []):
            why[position].append(reason)
    add(positions[0], "opening")
    if len(rows[positions[0]]["full_text"]) < 400 and len(positions) > 1:
        add(positions[1], "opening")
    for position in positions[-2:]:
        add(position, "order")
    for position, row in paragraphs:
        if row.get("paragraph_type") == "order":
            add(position, "order")
    for reason, around, marked in (("chosen", AROUND_CHOSEN, chosen), ("found", AROUND_FOUND, found - chosen)):
        for position in marked:
            add(position, reason)
            at = positions.index(position) if position in rows else None
            for near in [] if at is None else positions[max(0, at - around):at + around + 1]:
                add(near, "beside")
    numbered = {str(row.get("paragraph_num") or "").strip(): position for position, row in paragraphs}
    for position in list(why):
        for named in _PARAGRAPH_NAMED.finditer(rows[position]["full_text"]):
            first, last = int(named.group(1)), int(named.group(2) or named.group(1))
            for number in range(first, min(last, first + 10) + 1):
                if str(number) in numbered and numbered[str(number)] != position:
                    add(numbered[str(number)], "named")
    for position, row in paragraphs:
        if _ISSUES.search(row["full_text"]):
            add(position, "issues")
    # Kept within the whole judgment's bound, the more necessary first; the opening, the order
    # and what the pick chose always stay.
    rank = {position: min(_WHY.index(reason) for reason in reasons) for position, reasons in why.items()}
    kept, size = set(), 0
    for position in sorted(why, key=lambda p: (rank[p], positions.index(p))):
        length = len(rows[position]["full_text"])
        if rank[position] <= _WHY.index("chosen") or size + length <= WHOLE_JUDGMENT_CHARACTERS:
            kept.add(position)
            size += length
    return {position: why[position] for position in positions if position in kept}


def _read_judgments(searcher, plan, searches, pick):
    """The judgments a dispute's answer reads (P31): each chosen judgment whole, or as an
    extract of a long one; one that cannot be read is said, with why."""
    read = []
    for case_id, found, chosen in _chosen_cases(plan, searches, pick):
        try:
            if searcher is None or not callable(getattr(searcher, "read_judgment", None)):
                raise SearchUnavailable("Held judgments cannot be read whole")
            held = searcher.read_judgment(case_id)
        except (SearchUnavailable, ValueError, OSError, RuntimeError) as exc:
            read.append({"case_id": case_id, "unread": str(exc) or type(exc).__name__})
            continue
        paragraphs = held["paragraphs"]
        size = sum(len(row["full_text"]) for _, row in paragraphs)
        whole = size <= WHOLE_JUDGMENT_CHARACTERS
        kept = ({position: [] for position, _ in paragraphs} if whole else _extract(paragraphs, found, chosen))
        read.append({"case_id": case_id, "corpus_revision": held["corpus_revision"], "paragraphs": len(paragraphs),
                     "first": paragraphs[0][0], "last": paragraphs[-1][0],
                     "characters": size, "whole": whole, "found": sorted(found), "chosen": sorted(chosen),
                     "read": [{"position": position, "row": deepcopy(row), "content_digest": _digest(row),
                               "why": kept[position]} for position, row in paragraphs if position in kept]})
    return read


def _picked(model, plan, searches, report):
    """A dispute's two picks, beside each other; without a model each keeps the first six."""
    if model is None:
        labels = _labels(plan, searches)
        return {kind: {"state": "unavailable", "proposal": None, "unknown": [], "reason": "No model for the pick",
                       "chosen": _fallback_picks(searches, labels, kind)} for kind in _PICK_FIELDS}
    if searches:
        report("choosing_provisions")
    with ThreadPoolExecutor(max_workers=len(_PICK_FIELDS)) as pool:
        return dict(zip(_PICK_FIELDS, pool.map(lambda kind: pick(model, plan, searches, kind), _PICK_FIELDS)))


def retrieve_parts(plan, searcher, context, model=None, *, progress=None):
    """v10: every question searched side by side in the answer's order (owner, 20 Oct 2026:
    step 1), and each dispute's provisions and judgment paragraphs picked as soon as its own
    questions are searched (21 Oct 2026: step 4). Returns each dispute's part as a future, in
    the answer's order; a part keeps what each of its questions found, or why it failed."""
    if accept(plan["proposal"], context) != plan:
        raise ValueError("Research plan differs from its original sources")
    report = progress or (lambda stage, **detail: None)
    asked, outcomes = [], {}
    for work in plan["work"]:
        queries = search_queries(work)
        if not queries:
            continue
        try:
            if searcher is None:
                raise SearchUnavailable("Held-law search is not configured")
            asked.append((work, queries, search_instruments(work)))
        except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            outcomes[work["id"]] = exc
    finished, lock = [len(plan["work"]) - len(asked)], threading.Lock()
    report("searching", done=finished[0], total=len(plan["work"]))

    def searched():
        with lock:  # counts are reported in order
            finished[0] += 1
            if finished[0] < len(plan["work"]):  # the last is followed by the next stage at once
                report("searching", done=finished[0], total=len(plan["work"]))
    futures = searcher.search_many([(queries, instruments) for _, queries, instruments in asked],
                                   results={"provision": PROVISIONS_FOR_PICK}, done=searched) if asked else []
    outcomes.update((work["id"], (future, queries, instruments))
                    for (work, queries, instruments), future in zip(asked, futures, strict=True))

    def researched(dispute_id, works):
        searches, failures = {}, {}
        for work in works:
            if work["id"] not in outcomes:
                continue
            try:
                outcome = outcomes[work["id"]]
                if isinstance(outcome, Exception):
                    raise outcome
                future, queries, instruments = outcome
                searches[work["id"]] = validate_search(future.result(), queries, instruments)
            except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
                # This independent read-only adapter/snapshot failed. It supplies no
                # admitted evidence; peers remain available and the failure stays explicit.
                failures[work["id"]] = {"stage": "search", "reason": str(exc) or type(exc).__name__}
        picks = _picked(model, plan, searches, report)
        return _part(plan, dispute_id, searches, failures, picks,
                     _read_judgments(searcher, plan, searches, picks["judgment"]))
    groups = dispute_work(plan)
    pool = ThreadPoolExecutor(max_workers=max(1, len(groups)), thread_name_prefix="dispute")
    parts = {dispute_id: pool.submit(researched, dispute_id, works) for dispute_id, works in groups.items()}
    pool.shutdown(wait=False)
    return parts


def assemble(plan, parts, *, unfinished=None):
    """The whole v10 record from its disputes' parts, in the answer's order. A dispute with no
    part is refused, unless `unfinished` says why (a turn that stopped part way): its questions
    then record that as their gap and its picks keep nothing."""
    done = {part["part"]: part for part in parts}
    searches, failures, chosen = {}, {}, {field: {} for field in _PICK_FIELDS.values()}
    judgments = {}
    for dispute_id, works in dispute_work(plan).items():
        part = done.get(dispute_id)
        if part is None:
            if unfinished is None:
                raise ValueError("A dispute's research is missing")
            failures.update((w["id"], {"stage": "search", "reason": unfinished}) for w in works if w["enquiries"])
            for field in _PICK_FIELDS.values():
                chosen[field][dispute_id] = {"state": "unavailable", "proposal": None, "chosen": {}, "unknown": [],
                                             "reason": unfinished}
            judgments[dispute_id] = []
            continue
        searches.update(deepcopy(part["searches"]))
        failures.update(deepcopy(part["failures"]))
        for field in _PICK_FIELDS.values():
            chosen[field][dispute_id] = deepcopy(part[field][dispute_id])
        judgments[dispute_id] = deepcopy(part["judgments"][dispute_id])
    order = [w["id"] for w in plan["work"]]
    record = {"contract": CONTRACT, "plan": deepcopy(plan),
              "searches": {i: searches[i] for i in order if i in searches},
              "failures": {i: failures[i] for i in order if i in failures}, **chosen, "judgments": judgments}
    record["state"] = _state(plan, record["searches"], record["failures"], picks_of(record))
    return record


def part_of(record, dispute_id):
    """A v10 or v11 record's part for one dispute, exactly as that dispute's section read it
    (once within a replay, P35)."""
    return once(("part", id(record), dispute_id), (record,), lambda: _part(
        record["plan"], dispute_id, record["searches"], record["failures"],
        {kind: record[field][dispute_id] for kind, field in _PICK_FIELDS.items()},
        (record.get("judgments") or {}).get(dispute_id, []), record["contract"]))


def picks_of(record, kind=None):
    """A record's picks as a list: each dispute's (v10), or the one pick of a kind (v7-v9)."""
    kinds = [kind] if kind else [k for k in _PICK_FIELDS if _PICK_FIELDS[k] in record]
    if record.get("contract") in BY_DISPUTE:
        return [pick for k in kinds for pick in record[_PICK_FIELDS[k]].values()]
    return [record[_PICK_FIELDS[k]] for k in kinds if _PICK_FIELDS[k] in record]


def chosen(record, kind="provision"):
    """What a record's picks of a kind chose, by work item."""
    return {work_id: ids for pick in picks_of(record, kind) for work_id, ids in pick["chosen"].items()}


def retrieve(plan, searcher, context, model=None, *, progress=None):
    """The whole v10 research: every dispute's part, assembled (retrieve_parts)."""
    parts = retrieve_parts(plan, searcher, context, model, progress=progress)
    return assemble(plan, [future.result() for future in parts.values()])


def execution(record):
    """Receipts describe what this code did, never whether the request is fulfilled; a v10
    dispute's part describes its own questions."""
    ids = ({w["id"] for w in dispute_work(record["plan"])[record["part"]]} if "part" in record else None)
    searches = []
    for work in record["plan"]["work"]:
        identity = work["id"]
        if ids is not None and identity not in ids:
            continue
        if identity in record["failures"]:
            state = "failed"
        elif identity in record["searches"]:
            state = "partial" if record["searches"][identity]["issues"] else "evaluated"
        else:
            state = "not_requested"
        searches.append({"work_id": identity, "state": state})
    return {"contract": EXECUTION, "operations": [], "record_changes": [],
            "external_actions": [], "searches": searches, "persistence": "not_yet_committed"}


def admitted_provisions(record):
    """The provision candidates the answer may use: v7 and later admit only the pick;
    earlier records admit every returned provision."""
    if record.get("contract") not in _QUESTION_PLANS:
        return None
    return {candidate_id for ids in chosen(record).values() for candidate_id in ids}


def picked_judgments(record):
    """The judgment paragraphs the v8 pick chose, which the answer reads with their
    neighbouring paragraphs; None for earlier records, which read every returned
    paragraph with its whole saved context."""
    if record.get("contract") not in JUDGMENT_PICKS:
        return None
    return {candidate_id for ids in chosen(record, "judgment").values() for candidate_id in ids}


def validate(record, plan, context):
    """A saved research record checked against its plan and original sources; once within a
    replay (P35, 21 Oct 2026), where every check of a saved turn validates the same record, and
    a record validated is its own validation."""
    checked = once(("research", id(record), id(plan), id(context)), (record, plan, context),
                   lambda: _validate(record, plan, context))
    known(("research", id(checked), id(checked["plan"]), id(context)), (checked, checked["plan"], context), checked)
    return checked


def _validate(record, plan, context):
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
              | ({"judgment_picks"} if contract in JUDGMENT_PICKS else set())
              | ({"judgments"} if contract in JUDGMENTS_READ else set())
              | ({"part"} if contract in BY_DISPUTE and "part" in record else set()))
    if (not isinstance(record, dict)
            or set(record) != fields
            or record.get("plan") != plan or not isinstance(record.get("searches"), dict)
            or not isinstance(record.get("failures"), dict)):
        raise ValueError("Research snapshot does not belong to its plan")
    groups = dispute_work(plan) if contract in BY_DISPUTE else {}
    if "part" in fields and record["part"] not in groups:
        raise ValueError("A research part names no dispute of its plan")
    for failure in record["failures"].values():
        if (not isinstance(failure, dict) or set(failure) != {"stage", "reason"}
                or failure["stage"] != "search" or not isinstance(failure["reason"], str)
                or not failure["reason"].strip()):
            raise ValueError("Research failure has no checked search disposition")
    required = {work["id"] for work in (groups[record["part"]] if "part" in fields else plan["work"])
                if work["enquiries"]}
    successes, failures = set(record["searches"]), set(record["failures"])
    if successes & failures or successes | failures != required:
        raise ValueError("Each research work item needs one execution disposition")
    for work in plan["work"]:
        if work["id"] in successes:
            validate_search(record["searches"][work["id"]], search_queries(work, contract=contract),
                            search_instruments(work, contract=contract))
    picks = []
    if contract in BY_DISPUTE:
        # v10: each dispute's picks, labelled within that dispute's own searched questions.
        disputes = [record["part"]] if "part" in fields else list(groups)
        for kind, field in _PICK_FIELDS.items():
            if not isinstance(record[field], dict) or set(record[field]) != set(disputes):
                raise ValueError(f"The {kind} picks are not one for each dispute")
            for dispute_id in disputes:
                ids = {w["id"] for w in groups[dispute_id]}
                own = {i: search for i, search in record["searches"].items() if i in ids}
                _validate_picks(record[field][dispute_id], plan, own, kind)
                picks.append(record[field][dispute_id])
                if kind == "judgment" and contract in JUDGMENTS_READ:
                    _validate_judgments(record["judgments"], dispute_id, plan, own, record[field][dispute_id])
        if contract in JUDGMENTS_READ and set(record["judgments"]) != set(disputes):
            raise ValueError("The judgments read are not one list for each dispute")
    else:
        if contract in _QUESTION_PLANS:
            _validate_picks(record["picks"], plan, record["searches"])
            picks.append(record["picks"])
        if contract in JUDGMENT_PICKS:
            _validate_picks(record["judgment_picks"], plan, record["searches"], "judgment")
            picks.append(record["judgment_picks"])
    expected = "partial" if (plan["issues"] or failures or _picks_open(picks) or any(
        search["state"] == "partial" for search in record["searches"].values())) else "evaluated"
    if record["state"] != expected:
        raise ValueError("Research status disagrees with actual search outcomes")
    return deepcopy(record)


def _validate_judgments(judgments, dispute_id, plan, searches, pick):
    """v11 (P31): the judgments a dispute reads are those its pick chose, in order and at most
    JUDGMENTS_PER_DISPUTE; each read whole when no longer than the bound, else as an extract
    keeping its opening, its order and what the pick chose; every paragraph kept exactly as
    stored, and what search found and the pick chose marked as found and chosen."""
    entries = judgments.get(dispute_id) if isinstance(judgments, dict) else None
    expected = _chosen_cases(plan, searches, pick)
    if not isinstance(entries, list) or [entry.get("case_id") for entry in entries] != [c for c, _, _ in expected]:
        raise ValueError("The judgments read are not the ones the pick chose")
    revisions = {search["corpus_revisions"].get("judgment") for search in searches.values()}
    for entry, (case_id, found, chosen) in zip(entries, expected, strict=True):
        if "unread" in entry:
            if set(entry) != {"case_id", "unread"} or not isinstance(entry["unread"], str) or not entry["unread"]:
                raise ValueError("A judgment not read says why")
            continue
        if (set(entry) != {"case_id", "corpus_revision", "paragraphs", "first", "last", "characters", "whole", "found",
                           "chosen", "read"}
                or entry["corpus_revision"] not in revisions or entry["found"] != sorted(found)
                or entry["chosen"] != sorted(chosen) or type(entry["paragraphs"]) is not int
                or type(entry["characters"]) is not int or type(entry["whole"]) is not bool
                or entry["whole"] != (entry["characters"] <= WHOLE_JUDGMENT_CHARACTERS)):
            raise ValueError("A judgment read differs from what its pick and search found")
        read = entry["read"]
        positions = [paragraph.get("position") for paragraph in read]
        if (not read or positions != sorted(set(positions)) or entry["whole"] and len(read) != entry["paragraphs"]
                or positions[0] != entry["first"] or positions[-1] != entry["last"]
                or not entry["whole"] and ("opening" not in read[0].get("why", []) or not chosen <= set(positions))
                or entry["whole"] and not set(entry["found"]) | set(entry["chosen"]) <= set(positions)):
            raise ValueError("A judgment's paragraphs are not read as P31 reads them")
        for paragraph in read:
            row = paragraph.get("row")
            if (not isinstance(paragraph, dict) or set(paragraph) != {"position", "row", "content_digest", "why"}
                    or not isinstance(row, dict) or row.get("case_id") != case_id
                    or row.get("doc_type", "case_law") != "case_law" or not row.get("full_text")
                    or paragraph["content_digest"] != _digest(row)
                    or not _valid_location("judgment", paragraph["position"], row)
                    or not isinstance(paragraph["why"], list)
                    or any(reason not in _WHY for reason in paragraph["why"])
                    or entry["whole"] and paragraph["why"]
                    or not entry["whole"] and not paragraph["why"]):
                raise ValueError("A judgment's paragraph is not held as stored")


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
