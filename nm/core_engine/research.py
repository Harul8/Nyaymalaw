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
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import date

from nm.core_engine import figures, reasoning
from nm.core_engine.replay_scope import known, once
from nm.core_engine.retrieval import SearchUnavailable, _digest, _valid_location, in_force, validate_search
from nm.core_engine.understanding import REFERENCE, TEXT, TYPOGRAPHY, advocate_messages, select, source_catalogue
from nm.shared import clock_contracts
from nm.core_engine.citations import IndexUnavailable, held_judgments
from nm.shared.citation_contracts import find_reporter_citations, judgment_place, provision_references
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
WHOLE_FILE_CONTRACT = "core_research_v13"
#: v14 (plan AN.33, D18 and D22; owner, 1 Nov 2026: "pass these to model and let model decide whether this is a clerical error or a
#: genuine failed test in which can model can decide to drop only that failed portion"): the papers' events, transactions and points
#: read side by side, and the understanding's quotations, are checked with the tolerant finder, and what is found is kept in the
#: page's own words; what code still cannot check is settled by a model shown code's evidence, one call for each paper with failures,
#: whose answer code checks again - a slip in copying is corrected from the page, only a part the papers do not hold goes, an item
#: they do not record is withdrawn and listed, and what stays unchecked is kept and marked so. No date is erased: code records where
#: it found a date's numbers - in the item's words, on its paper, elsewhere in the file - or that it found them nowhere. v13 and
#: earlier records replay unchanged. In development until AN.33 is applied to the running server: no v14 record is saved before then.
SETTLED_CONTRACT = "core_research_v14"
#: v15 (plan AN.35, D30; piece 35a; owner, 2 Nov 2026): no fixed count on the relevant law kept and read -
#: every judgment a dispute's pick chooses is read, none cut to JUDGMENTS_PER_DISPUTE, and each question is offered
#: JUDGMENTS_FOR_PICK judgment paragraphs, as many as provisions, ranked by relevance; the picks choose by relevance
#: alone ("we are only retrieving the relevant passages and reading only the relevant judgments"). v14 and earlier
#: records replay under their own rule.
NAMED_CONTRACT = "core_research_v15"
#: v16 (plan AN.35, D30 A3; piece 35d, 2 Nov 2026): v15 with, once per dispute after its two picks, the law still missing named and
#: searched for once (further): one call is shown each searched question with what the picks chose for it and what they said was
#: missing, and names for each question whose governing law is still missing the sections to read by their number and the phrases
#: to search; code searches once for those, the two picks choose among only what was not already offered for that question, and
#: the judgments chosen are read with the rest, each judgment once. A question with nothing missing searches nothing; there is no
#: second round, and a reading never starts a search (D30, the owner's relevance gates).
FURTHER_CONTRACT = "core_research_v16"
#: v17 (plan AN.36, D34; piece 36a, 2 Nov 2026; owner: "let the model decide those top 2, 3, 4, or 5 judgments which are most
#: relevant, and then the model can read the full judgment of only those"): v16 whose judgment picks also name, for the dispute, the
#: judgments a lawyer would read in full; each dispute reads in full at most IN_FULL of them - the first pick's, then the further
#: pick's, then the cited judgments the further call chose - and every other judgment chosen stands by its chosen paragraphs, each
#: read with the stored paragraph either side (as research v8 read them). v16 and earlier records replay under their own rule.
FEW_CONTRACT = "core_research_v17"
#: v18 (plan AN.36, D36; piece 36e, 3 Nov 2026; owner: "for a given dispute and a paricular part of that dispute there won't be
#: more than lets say 2-5 relevants section"): v17 whose provision pick chooses the two to five provisions that govern each question
#: - the rule and what qualifies or completes it - and keeps at most SECTIONS_A_QUESTION of them, the further pick only what is left
#: of them; sections named by number and those linked by their Acts count within them. v17 and earlier records replay as they were.
CONTRACT = "core_research_v18"
#: v18: at most this many provisions a question are chosen (D36: "2-5 relevants section").
SECTIONS_A_QUESTION = 5
#: v17: at most this many judgments a dispute are read in full (the owner, D34: "top 2, 3, 4, or 5").
IN_FULL = 5
#: The plans that set out the matter as disputes and legal questions (v7 on).
QUESTION_PLANS = (PICKED_CONTRACT, JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
                  CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
_QUESTION_PLANS = QUESTION_PLANS
#: The records that pick judgment paragraphs and answer in parts per dispute (v8 on).
JUDGMENT_PICKS = (JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
                  CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The records that keep each dispute's picks apart (v10 on).
BY_DISPUTE = (PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT, CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT,
              NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The records that read the chosen judgments whole or as extracts (v11 on).
JUDGMENTS_READ = (JUDGMENTS_READ_CONTRACT, CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT,
                  FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The records that also keep the chronology of the documents (v12 on).
CHRONICLED = (CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The records whose papers are read with the whole file in view, their dates checked by code (v13 on).
WHOLE_FILE = (WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The records checked with the tolerant finder, whose failed checks a model settles (v14 on).
SETTLED = (SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: v15 and v16: every judgment a dispute's pick chose is read (piece 35a); v17 reads in full only the few chosen so (36a).
EVERY_CHOSEN = (NAMED_CONTRACT, FURTHER_CONTRACT)
#: v17 (piece 36a): the judgments read in full are the few the picks name, at most IN_FULL a dispute.
FEW_IN_FULL = (FEW_CONTRACT, CONTRACT)
#: v18 (piece 36e): each question chooses at most SECTIONS_A_QUESTION provisions.
FEW_SECTIONS = (CONTRACT,)
#: v15 (plan AN.35, piece 35b): each question's plan names the sections to read first, each read by its number (search v11).
NAMED_LAW = (NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: v16 (piece 35d): each dispute's law still missing is searched for once.
FURTHER_LAW = (FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
CONTRACTS = (LEGACY_CONTRACT, PREVIOUS_CONTRACT, WINDOWED_CONTRACT, ACCOUNT_CONTRACT, INSTRUMENTED_CONTRACT,
             PICKED_CONTRACT, JUDGMENT_PICKED_CONTRACT, PURPOSED_CONTRACT, PER_DISPUTE_CONTRACT, JUDGMENTS_READ_CONTRACT,
             CHRONICLED_CONTRACT, WHOLE_FILE_CONTRACT, SETTLED_CONTRACT, NAMED_CONTRACT, FURTHER_CONTRACT, FEW_CONTRACT, CONTRACT)
#: The papers a record step sees whole (D1, the owner: "a safe fixed limit like 100k tokens"): above it, each call sees the paper
#: it answers for, with the advocate's messages.
WHOLE_FILE_TOKENS = 100_000
#: P31 (owner, 21 Oct 2026): four to five judgments a dispute; a judgment is read whole up to about
#: 8,000 tokens; an extract keeps one or two paragraphs either side of each one found.
JUDGMENTS_PER_DISPUTE = 5  # records before v15 only (piece 35a)
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
#: v15 (plan AN.35, piece 35a): the pick chooses from each question's first JUDGMENTS_FOR_PICK judgment paragraphs, ranked by
#: relevance, as it does from twenty provisions - the breadth of what the model looks at, never a cut of what it keeps.
JUDGMENTS_FOR_PICK = 20
#: Answer limits per step. Calls in flight are budgeted at their limit.
#: From research v13 (plan AN.28, D4) the steps that reason at medium or high spend output on their reasoning too, so their limits
#: make room for it (the first paid probe of 31 Oct 2026 stopped the understanding at its old 12,000).
#: D27 (plan AN.33; owner, 2 Nov 2026: no hard limits): each step may write as much as its model can, within the room its input
#: leaves (reasoning.room); no step has an allowance of its own.
MAX_OUTPUT = dict.fromkeys(("understand", "check", "revise", "phrases", "judgment_phrases", "pick", "judgment_pick", "chronology",
                            "transfers", "chronology_check", "transfers_check", "connections", "connections_check",
                            "chronology_second", "weigh", "weigh_check", "further"), reasoning.MOST_OUTPUT)

# The prompts below were developed and measured in outputs/decomposition-scratch
# (13-14 Oct 2026). They state the purpose and the needed outcome in plain language
# and leave understanding to the model; code makes the mechanical checks afterwards.
UNDERSTAND = """You are a senior Indian litigation lawyer working with a colleague, the advocate, who practises in Telangana. You receive the conversation so far: the advocate's messages, any documents they sent and any earlier notes from our research assistant. The last message is the one we are acting on now.

Advocates bring matters to us so that we can find the law that governs them. Your job in this step is to understand the matter well enough that the right law can be researched. You are not answering the legal questions yet. Read the whole conversation, think about what has happened, who is involved, what the advocate wants now and why, and then set out your understanding.

What we need from you:

- What the advocate wants from us now. Often they say so. When they only tell us what has happened, they want to know where the law stands on those events: the legal questions a lawyer would need answered to advise on them. Also note, in the advocate's own words, anything they have told us not to do (for example to pause research or not to contact anyone) in ruled_out, and where they have told us nothing of the kind leave ruled_out empty. What the papers leave open or unproved is not something the advocate ruled out: it belongs in the facts as uncertain and in the facts we would still need.
- The people involved and their roles: whether each is the advocate's client or one of the client's people (client), and, for each proceeding the papers name - a suit, appeal, revision, petition, complaint or other case - each person's part in it (who brought it, who answers it, who else is joined), with the page's own words (parts). A person the papers name in a proceeding is listed even when the advocate did not mention them.
- Every subject of the matter the papers identify - an asset, an account, a contract, a policy, a case or a document - by the number or name the page identifies it by, exactly as the page writes it, what it is, and the page's own words (subjects). List a subject the papers name even where it seems not to bear on what the advocate asked, so that none is overlooked.
- The facts, each kept exactly as certain as the advocate put it: confirmed, reported by someone, uncertain, or disputed. Give the advocate's own words for each fact, or, for a fact that comes from a document they sent, the document's own words. What the advocate reports is their account, and what a document says is what its author wrote; neither is proven fact, and we never add facts they did not give.
- The separate disputes. A dispute is one set of events between particular parties that needs its own legal answer. Events that call for different kinds of law, such as a civil wrong and a crime, or that concern different transactions, are separate disputes, even when they happen together or involve the same people.
- For each dispute, think through every legal consequence the events may have, civil, criminal and under any special statute, and for each: the right or liability, the remedy, how and where it is pursued and within what time, and, where the case turns on particular evidence, how that evidence is proved. Ask as legal questions those that bear on what the advocate wants; put the rest in related points.
- For each dispute, the legal questions we must research to do what the advocate wants. A legal question is about one legal point: a right, an obligation, a remedy, a defence, a procedure, a time limit, a presumption or an offence. If answering it would need two different rules, such as what a right is and how it is enforced, it is two questions. Write each so that a lawyer could answer it from one or two provisions of law, and say briefly why we need it. Where the facts leave open something that changes the governing law (for example when the events happened, or which personal law applies), say what is open.
- For each legal question, the law you would check first: the Indian Acts, and sections if you know them, that you believe govern it, and every provision the advocate's messages or the papers cite that bears on it, as they cite it. This is your recollection to guide the search; it will be checked against the statutes we hold, so say only what you believe and do not guess.
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
- Is anyone's part in a proceeding the papers name, or a subject the papers identify, missed or misread? The papers' chronology is set out by another step, from the papers themselves: the understanding need not set it out, and its absence is no problem.
- Are the related points genuinely useful to the advocate, and kept separate from what we research now?
- Is research being started when the advocate has ruled it out, or skipped when it is needed? Our purpose with every matter is to find where the law stands for each dispute in it, so that the advocate can see what the case needs. They do not have to ask for that: when they only tell us what has happened, or ask us to understand, summarise or set out the events, they still want to know where the law stands on them. Skipping research is a problem unless the advocate has told us not to research or the message needs none (thanks, or a request to tidy or transcribe text); starting it is a problem only when they have ruled it out. Where we could find instructions from the advocate limiting our work in their latest message, they are listed after the conversation; the conversation itself may hold earlier ones. Do not report research as a problem because the advocate's words did not literally ask for advice.

Counting is code's work for figures as it is for days: do not add, subtract or convert any amount or quantity yourself, and do not report that figures disagree because they do not seem to add up. Where two papers give different figures for the same thing, say so with each figure as it is given; where figures might or might not add up, say that they have not been added up.

Report only problems that matter: ones that would change what we research, or would leave us misunderstanding the matter or the advocate's instructions. Small differences of wording or emphasis do not matter. Give each real problem precisely, with what should change. If the understanding is sound, say so plainly. Do not invent problems to have something to say.
"""
REVISE = """You are a senior Indian litigation lawyer. You wrote an understanding of a matter, and a reviewing colleague (and our mechanical checks) found problems with it. You receive the conversation, your understanding and the problems.

Think about each problem against the conversation. Correct what is genuinely wrong and keep everything that was right. If you believe a reported problem is mistaken, keep your original and explain why in your notes. Then give the complete corrected understanding.
"""
PHRASES = """You are a senior Indian litigation lawyer about to search a library of Indian statutes, central Acts and Telangana State Acts, for the provisions that answer a set of legal questions. You receive the matter as a colleague has understood it: its disputes and, for each, the legal questions with the law your colleague would check first.

Statutes rarely use everyday words. They use terms of art and frame rules in their own way, so a search in plain English often misses the provision that answers the question. Use your knowledge of Indian law to write, for each legal question, the language the statutes themselves are likely to use:

- Heading terms: the words a section heading for this rule would use, in the statute's own terms of art rather than the everyday words of the facts.
- Alternative terms: other terms of art the law uses for the same idea, such as the term another Act uses, the term of an older or newer enactment on the subject, or the closely related concept a lawyer would also look under.
- A rule statement: one sentence framing the governing rule the way a provision would, in your own words. Do not try to recite a section from memory; this is only a search probe, and the actual words will be read from the statutes we hold.

For each question give the search phrases that will best find the governing provision, as many as the question needs - each a different way in, none a repeat of another - choosing the kinds that will find it. Keep heading and alternative terms to a few words each, and the rule statement to one sentence.

Also name the Acts to search in: the Indian Acts you believe govern the question, by short title and year. When the date of the events decides which law applies, include both the Act in force then and the Act that replaced it or that it replaced.

And name the sections to read first: each provision the law your colleague would check names for the question, and any other you know governs it, each on its own, by its Act's short title and year and its number as the Act numbers it (a section, an article, an order and rule). Each is read by its number from the Acts we hold, whole, beside what the search finds; one we do not hold is said, never replaced by another.
"""
JUDGMENT_PHRASES = """You are a senior Indian litigation lawyer about to search a library of Indian judgments, the Supreme Court of India and the High Court of Telangana (the High Court of Andhra Pradesh before the State was divided), for the authorities that answer a set of legal questions. You receive the matter as a colleague has understood it: its disputes and, for each, the legal questions, with the law your colleague would check first.

Judgments do not read like statutes. Courts frame the point in issue in their own way, name doctrines and tests, discuss the provision by its section number and Act, and state the principle they decide in a sentence of their own. A search phrased in the words of the statute mostly finds paragraphs that merely quote it. Use your knowledge of how Indian courts write to give, for each legal question, the language a judgment deciding it is likely to use:

- The issue as a court frames it: the question of law it asks, in a court's own words.
- The holding: one sentence stating the principle the way a court would hold it, in your own words. Do not try to recite a judgment from memory; this is only a search probe, and the actual words will be read from the judgments we hold.
- The doctrine or test: the name courts give the principle, tied to the provision where courts usually discuss it that way.

For each question give the search phrases that will best find a judgment that decides the point, as many as the question needs - each a different way in, none a repeat of another - choosing the kinds that will find it.
"""
PICK = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for each question a search of the statutes we hold has returned up to twenty provisions, each shown with its Act, section, heading and opening words.

After each question's search results come the provisions their Acts connect to them: provisions a result names in its own words, provisions that name a result, and the provisions printed beside a result, each shown with its heading and the words that connect them. A lawyer reads a rule with what its Act reads it with: its exceptions and provisos, the defences, presumptions and conditions that bear on it, its time limits and the procedure for enforcing it.

For each question, choose the provisions a lawyer must read to answer it: the ones that state the governing rule, right, liability, remedy, procedure, time limit, presumption or offence the question asks about, and the connected provisions that qualify or complete them in a way the answer needs. Choose only what is needed, and put the most necessary first. Whatever you choose is read whole.

Judge each provision by what it actually says, not by whether it shares words with the question. A provision whose Act India Code, the government's record of the Acts in force, no longer lists is marked not in force; weigh that as a lawyer would. If no shown provision answers a question, choose none for it and say what is missing.
"""
JUDGMENT_PICK = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for each question a search of the judgments we hold, the Supreme Court of India and the High Court of Telangana (the High Court of Andhra Pradesh before the State was divided), has returned up to twenty paragraphs, the most relevant first, each shown with its judgment, court, year, how many later judgments cite it, and the paragraph's words.

For each question, choose every paragraph a lawyer would rely on to answer it, and no other: those where a court decides or authoritatively explains the point the question asks about. A paragraph that does not decide or explain that point is not chosen, however near its words are to the question's. Put the most useful first. Each judgment whose paragraph you choose is then read whole, or, when it is long, as an extract around what was found, so choose the judgments a lawyer would rely on as much as the paragraphs.

Judge each paragraph by what the court is doing in it. A paragraph that only quotes the statute, recites the facts of that case or reports a party's argument is rarely what a lawyer cites, unless the court adopts it as its own view. Weigh the court and the judgment's standing as a lawyer would, without passing over a recent judgment merely because few have cited it yet. If no shown paragraph answers a question, choose none for it and say what is missing.
"""


#: v17 (plan AN.36, D34; piece 36a): the judgment pick as v16's, with only the few judgments that matter most read in full.
_READ_WHOLE_SAID = ("Each judgment whose paragraph you choose is then read whole, or, when it is long, as an extract around what was "
                    "found, so choose the judgments a lawyer would rely on as much as the paragraphs.")
if JUDGMENT_PICK.count(_READ_WHOLE_SAID) != 1:
    raise RuntimeError("The v17 judgment pick cannot be made from v16's")
JUDGMENT_PICK_V17 = JUDGMENT_PICK.replace(_READ_WHOLE_SAID, (
    "Each paragraph you choose is read with the paragraph either side of it. Then, for the dispute as a whole, name in "
    "read_in_full the judgments a lawyer would read in full before advising on it - the two to five that matter most to its "
    "central questions - each by the ID of one of its paragraphs you chose; only those are read whole (a long one as an extract "
    "around what you chose), and every other judgment stands by the paragraphs you chose."))

#: v18 (plan AN.36, D36; piece 36e): the provision pick as v17's, choosing the two to five provisions that govern each question.
_ALL_NEEDED_SAID = ("For each question, choose the provisions a lawyer must read to answer it: the ones that state the governing rule, "
                    "right, liability, remedy, procedure, time limit, presumption or offence the question asks about, and the "
                    "connected provisions that qualify or complete them in a way the answer needs. Choose only what is needed, and put "
                    "the most necessary first.")
if PICK.count(_ALL_NEEDED_SAID) != 1:
    raise RuntimeError("The v18 provision pick cannot be made from v17's")
PICK_V18 = PICK.replace(_ALL_NEEDED_SAID, (
    "For each question, choose the two to five provisions that govern it: the provision that states the rule, right, liability, "
    "remedy, procedure, time limit, presumption or offence the question asks about, and those that qualify or complete it in a way "
    "the answer needs - its exceptions, conditions, time limit and procedure - whether search found them, their Act links them or "
    "they were named. Put the most necessary first; no more than five are read for a question."))


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
#: v15 (plan AN.35, piece 35b): a section to read first, by its Act's name and its number as the Act numbers it.
NAMED_SECTION = _object({"act": STRING, "section": STRING})
STATUTE_PHRASES_V15 = _object({"questions": {"type": "array", "items": _object({
    **STATUTE_PHRASES["properties"]["questions"]["items"]["properties"],
    "sections": {"type": "array", "items": NAMED_SECTION}})}})
JUDGMENT_PHRASE_SCHEMA = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "phrases": {"type": "array", "items": _phrase(("issue", "holding", "doctrine"))}})}})
CHOICE = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "chosen": STRINGS, "note": STRING})}})
#: v17 (piece 36a): the judgment pick also names, for the dispute, the judgments to read in full, each by one of its paragraphs' IDs.
CHOICE_V17 = _object({"questions": CHOICE["properties"]["questions"], "read_in_full": STRINGS})
FAILURE = _object({"step": STRING, "scope": STRING, "reason": STRING})


#: The chronology of each document (plan AN.27, P8; invariants I4, I5): what the papers record, event by event, so that nothing in
#: them is overlooked when the matter's history is told. Never an answer to a legal question, and never a judgment of which account
#: is right. A window is at most this many characters of one document's pages.
CHRONOLOGY_WINDOW = 40000
EVENT_KINDS = ("transaction", "order", "filing", "pending", "other")
CHRONOLOGY = """Message: You receive one document an advocate sent about a client's matter, or one stretch of its pages, each page under its number, with the document's name. A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. A page read from a scan may carry [illegible] and square-bracket notes about stamps, signatures and handwriting; those are the reader's, not the document's.

Purpose: Set out the document's own chronology for the advocate and for our research assistant: every event, order, direction, filing, transaction and proceeding it records or reports, with its date, so that nothing in the paper is overlooked when the matter's history is told. You are not judging which account is right, and you are not answering any legal question.

Look for:
- Each event the document records, whatever its date: a sale, partition or other deed, an entry in an official record, an order or direction of a court or authority, an appeal, revision, petition, suit, complaint, FIR or charge sheet, a notice, a hearing or listing, a payment, a death; and each proceeding it says is pending, with what it says of its stage.
- Who says it. A document may record an event itself (an order's own date and directions) or report it (a recital of an earlier order, a party's account or pleading). Give the authority or party whose words they are, and keep a party's allegation as that party's.
- The date as the page gives it, in the page's own form ("30-10-1985", "17 August 2019", "2008", "1961-62"); where the page gives none, say undated. Do not work out, convert or guess a date.
- The figures and identifiers that belong to the event, such as amounts, quantities and the numbers that identify a document, case, file, account or item, exactly as the page gives them.
- One event for each act and date. Do not merge events the page keeps apart, do not repeat an event the same page says twice, and do not add anything the page does not say. A register or list of many similar entries (a line for each item, say) is one event for the whole list, naming its range and the figures that matter, with the words of its first entries.
Work in a loop: list the events page by page, then read each page again against your list for any event or date you skipped or misread, and correct the list before you answer.

Outcome: events, in the order of the pages. Each has: date; kind (transaction, order, filing, pending, or other); what (one plain sentence saying what happened, with its figures and identifiers); said_by (whose words they are: the document's own author, or the party or authority it reports); words (the exact words on a page that record it, copied exactly as the page gives them, without the reader's square-bracket notes - a sentence that runs over a page may be copied whole - or several passages joined with '...'; never reword)."""
EVENT = _object({"date": STRING, "kind": {"type": "string", "enum": list(EVENT_KINDS)}, "what": STRING, "said_by": STRING,
                 "words": STRING})
CHRONOLOGY_SCHEMA = _object({"events": {"type": "array", "items": EVENT}})
#: v14 (AN.33, D17): a paper is read for every legally significant point it records, not its events alone - what an authority found, what
#: a party asserts, admits, denies or alleges, a document's particulars, who is related to whom or acts for whom, and what it says
#: stands, is done or remains to be done - each one point, kept as the events are.
EVENT_KINDS_V14 = ("transaction", "order", "finding", "filing", "pending", "statement", "document", "relationship", "status", "other")
EVENT_V14 = _object({**EVENT["properties"], "kind": {"type": "string", "enum": list(EVENT_KINDS_V14)}})
CHRONOLOGY_SCHEMA_V14 = _object({"events": {"type": "array", "items": EVENT_V14}})
#: An event as the plan records it (v12): what the model said, and what code made of it - the sort date, the document and the
#: turn's source it belongs to, the pages its words are on and whether they are found there, and its number.
EVENT_RECORD = _object({"id": STRING, "date": STRING, "sort": STRING, "kind": EVENT["properties"]["kind"], "what": STRING,
                        "said_by": STRING, "document": STRING, "source": STRING,
                        "pages": {"type": "array", "items": {"type": "integer"}}, "words": STRING,
                        "anchored": {"type": "boolean"}})
CHRONOLOGY_FAILURE = _object({"document": STRING, "pages": STRING, "reason": STRING})


TRANSFER_KINDS = ("sale", "partition", "gift", "settlement", "decree", "other")
#: v13 (AN.28, D7): the transactions of any matter - whatever passes from one person to another.
TRANSACTION_KINDS = (*TRANSFER_KINDS[:-1], "lease", "mortgage", "loan", "payment", "other")
#: The shape of a transfer in a plan saved by research v12, kept to validate such a plan (it is never read through again; see
#: figures_v12.py): the extent and the whole as the page wrote them, with no reading of them.
TRANSFER = _object({"date": STRING, "kind": {"type": "string", "enum": list(TRANSFER_KINDS)}, "parcel": STRING, "extent": STRING,
                    "total": STRING, "from": STRING, "to": STRING, "words": STRING})
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
# The transfers (P13d) are optional in v12: a plan saved before them has none and validates as it did.
SCHEMA_V12["properties"]["transfers"] = {"type": "array", "items": TRANSFER_RECORD}
SCHEMA_V12["properties"]["transfers_failures"] = {"type": "array", "items": CHRONOLOGY_FAILURE}
#: v13 (AN.28, D3, D7, B16; AN.29, D9): a transaction of any kind - whatever passes from one person to another. The model reads the
#: figure the page records into a quantity: its kind - an amount of money, an area, a length, a mass or a volume, or a share, a rate, a
#: period or no figure - and, for an amount, its parts, each a number as the page writes it, the unit it stands against (named in plain
#: words, which code resolves by its table of units: one it does not know is a figure it lists and never adds) and that unit as the
#: page writes it. Code checks the numbers and the unit against the words and does the sums.
QUANTITY = _object({"dimension": {"type": "string", "enum": list(figures.FIGURE_KINDS)},
                    "parts": {"type": "array", "items": _object({"number": STRING, "unit": STRING, "written": STRING})}})
QUANTITY_RECORD = _object({"dimension": STRING, "parts": {"type": "array", "items": _object({
    "number": STRING, "unit": STRING, "written": STRING})}})
TRANSACTION = _object({"date": STRING, "kind": {"type": "string", "enum": list(TRANSACTION_KINDS)}, "subject": STRING,
                       "figure": STRING, "quantity": QUANTITY, "whole": STRING, "whole_quantity": QUANTITY, "from": STRING,
                       "to": STRING, "instrument": STRING, "giver_died": STRING, "words": STRING})
TRANSACTIONS_SCHEMA = _object({"transfers": {"type": "array", "items": TRANSACTION}})
#: A transaction as the plan records it: what the model said, and what code made of it - the sort dates, the paper and the turn's source
#: it belongs to, the pages its words are on and whether they are found there, and its number.
TRANSACTION_RECORD = _object({"id": STRING, "date": STRING, "sort": STRING, "kind": TRANSACTION["properties"]["kind"],
                              "subject": STRING, "figure": STRING, "quantity": QUANTITY_RECORD, "whole": STRING,
                              "whole_quantity": QUANTITY_RECORD, "from": STRING, "to": STRING, "instrument": STRING,
                              "giver_died": STRING, "giver_died_sort": STRING, "document": STRING, "source": STRING,
                              "pages": {"type": "array", "items": {"type": "integer"}}, "words": STRING,
                              "anchored": {"type": "boolean"}})
SCHEMA_V13 = _record_schema(UNDERSTANDING_V13_RECORD, chronology=True)
#: v13 (AN.28, piece 3e): what matters to the client only when the papers are read side by side, each point with the pages' words.
CONNECTION_KINDS = ("client_appears", "against_client", "after_death", "after_time_limit", "further_subject", "other")
CONNECTION = _object({"kind": {"type": "string", "enum": list(CONNECTION_KINDS)}, "point": STRING, "why_it_matters": STRING,
                      "words": STRING})
CONNECTIONS_SCHEMA = _object({"client_people": STRINGS, "connections": {"type": "array", "items": CONNECTION}})
#: v14 (AN.33, D17 and D18; piece 33f): a difference between papers on one act or matter is a point of its own.
CONNECTION_KINDS_V14 = (*CONNECTION_KINDS[:-1], "papers_differ", "other")
CONNECTION_V14 = _object({**CONNECTION["properties"], "kind": {"type": "string", "enum": list(CONNECTION_KINDS_V14)}})
CONNECTIONS_SCHEMA_V14 = _object({"client_people": STRINGS, "connections": {"type": "array", "items": CONNECTION_V14}})
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

#: v14 (AN.33, D18 and D22): what settling a failed check decided for an item - "" where no check failed; the model's verdict
#: (clerical, elsewhere, part, scan_misread, as_listed); unanswered where its answer named no verdict for the item; unavailable
#: where the settling call failed. An item a model found the papers do not record is withdrawn and listed apart (WITHDRAWN).
VERDICTS = ("clerical", "elsewhere", "part", "scan_misread", "as_listed", "not_in_papers")
SETTLED_AS = ("", *VERDICTS[:-1], "unanswered", "unavailable")
#: v14: where code found the numbers of an item's date - in its words, on its paper's pages, on another paper of the file, nowhere;
#: none where the item is undated. A date is never erased.
DATE_FOUND = ("words", "paper", "file", "nowhere", "none")
_SETTLE_RECORD = {"quoted": STRING, "settled": {"type": "string", "enum": list(SETTLED_AS)}, "settled_why": STRING}
#: v14 (AN.33, piece 33g): second_pass - the event was given by the second pass over its paper, for what the reading left out.
EVENT_RECORD_V14 = _object({**EVENT_RECORD["properties"], "kind": EVENT_V14["properties"]["kind"], **_SETTLE_RECORD,
                            "date_found": {"type": "string", "enum": list(DATE_FOUND)}, "second_pass": {"type": "boolean"}})
TRANSACTION_RECORD_V14 = _object({**TRANSACTION_RECORD["properties"], **_SETTLE_RECORD,
                                  "date_found": {"type": "string", "enum": list(DATE_FOUND)},
                                  "giver_died_found": {"type": "boolean"}})
CONNECTION_RECORD_V14 = _object({**CONNECTION_RECORD["properties"], "kind": CONNECTION_V14["properties"]["kind"], **_SETTLE_RECORD})
WITHDRAWN = _object({"kind": {"type": "string", "enum": ["event", "transaction", "point"]}, "document": STRING, "what": STRING,
                     "words": STRING, "why": STRING})
SCHEMA_V14 = deepcopy(SCHEMA_V13)
SCHEMA_V14["properties"]["chronology"] = {"type": "array", "items": EVENT_RECORD_V14}
SCHEMA_V14["properties"]["transfers"] = {"type": "array", "items": TRANSACTION_RECORD_V14}
SCHEMA_V14["properties"]["connections"] = {"type": "array", "items": CONNECTION_RECORD_V14}
SCHEMA_V14["properties"]["withdrawn"] = {"type": "array", "items": WITHDRAWN}
#: v14 (AN.33, D19; piece 33h): each point that matters to the advice, weighed - the dispute it bears on, whether it helps or hurts
#: the client, how much (critical, material; a point not weighed is background), why, the legal question a critical point raises that
#: no question of its dispute covers, or that it is a matter for the advocate - and what the check made of it (kept, changed, added).
EFFECTS = ("helps", "hurts", "both", "unclear")
WEIGHTS = ("critical", "material")
WEIGHT = _object({"id": STRING, "dispute": STRING, "effect": {"type": "string", "enum": list(EFFECTS)},
                  "weight": {"type": "string", "enum": list(WEIGHTS)}, "why": STRING, "question": STRING,
                  "for_advocate": {"type": "boolean"}})
WEIGH_SCHEMA = _object({"weights": {"type": "array", "items": WEIGHT}})
WEIGH_CHECK_SCHEMA = _object({"corrections": {"type": "array", "items": _object({
    **WEIGHT["properties"], "weight": {"type": "string", "enum": [*WEIGHTS, "background"]}})}})
#: question_id: the legal question the point's own question became, researched with the rest; "" where it raised none.
WEIGHT_RECORD = _object({**WEIGHT["properties"], "checked": {"type": "string", "enum": ["kept", "changed", "added", "unchecked"]},
                         "question_id": STRING})
WEIGHING_FAILURE = _object({"step": STRING, "reason": STRING})
SCHEMA_V14["properties"]["weights"] = {"type": "array", "items": WEIGHT_RECORD}
SCHEMA_V14["properties"]["weighing_failures"] = {"type": "array", "items": WEIGHING_FAILURE}
#: v14 (AN.33, piece 33g): each second pass over a stretch of a paper - how many events it added, or why it could not be made.
SECOND_PASS_RECORD = _object({"document": STRING, "pages": STRING, "added": {"type": "integer"}, "reason": STRING})
SCHEMA_V14["properties"]["chronology_second_pass"] = {"type": "array", "items": SECOND_PASS_RECORD}
#: v15 (plan AN.35, piece 35b): the statute phrases keep the sections each question names; phrases kept without them name none.
SCHEMA_V15 = deepcopy(SCHEMA_V14)
_NAMING_QUESTION = STATUTE_PHRASES_V15["properties"]["questions"]["items"]
SCHEMA_V15["properties"]["statute_phrases"] = {"type": "array", "items": _object({
    "dispute_id": STRING, "questions": {"type": "array", "items": {
        **_NAMING_QUESTION, "required": [key for key in _NAMING_QUESTION["required"] if key != "sections"]}}})}


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
    if context.get("added"):
        # Plan AN.48 (D159; register item 6): what the advocate added after it while the matter waited, as their own words.
        lines += ["", "Added by the advocate after that message, while the matter waited for them (their own words, oldest "
                      "first):", *(f"- {row['text']}" for row in context["added"])]
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


#: The versions of the one finder (plan AN.33, D18). The exact finder is the one every record saved before research v14 was checked
#: and is shown with, and stays so (P46: a saved conversation reads back as it was made). The tolerant finder also finds words that
#: differ from a page only in what cannot change their meaning.
EXACT_FINDER, TOLERANT_FINDER = 1, 2
#: The fewest letters and digits words must hold for the tolerant finder to place them: shorter words could stand almost anywhere.
TOLERANT_MINIMUM = 12
#: A reader's note that transcribes handwriting - "[Handwritten: 812]", "[handwritten note at the foot, partly illegible: ...]" -
#: holds the page's own words after its first colon.
_HANDWRITING = re.compile(r"\[\s*hand\s*-?\s*written[^:\[\]]*:", re.I)


def _significant(char):
    """A letter, a mark that belongs to a letter, or a digit, in any script: what words are made of."""
    return unicodedata.category(char)[0] in "LMN"


def _bounded(text, start, end):
    """Whether a stretch of a text begins and ends where its words do: never inside a longer word or number."""
    return (not start or not _significant(text[start - 1])) and (end == len(text) or not _significant(text[end]))


def _tolerant(text):
    """A text as the tolerant finder compares it (plan AN.33, D18), with the place in the text of each character kept. Set aside,
    as what cannot change what the words say: the reader's own square-bracket notes (a stamp, a signature, [illegible]) - but not
    the handwriting a note transcribes, which is the page's; spacing, a word a scan split included; case; quotation marks and the
    other marks between words. A mark or a space between two digits is kept as it stands, so that 2.75 is never 27.5, "20 16" is
    never 2016 and 14-08-1993 keeps its dashes: a number that differs is never taken for another."""
    kept, work = [True] * len(text), text
    while True:  # innermost notes first, as _reading takes them
        spans = [match.span() for match in _MARKS.finditer(work)]
        if not spans:
            break
        blank = list(work)
        for start, end in spans:
            handwriting = _HANDWRITING.match(work, start)
            for index in range(start, end):
                if handwriting is None or index < handwriting.end() or index == end - 1:
                    kept[index] = False
                blank[index] = " "
        work = "".join(blank)
    visible = [index for index, char in enumerate(text) if kept[index] and not char.isspace()]
    letters, where = [], []
    for position, index in enumerate(visible):
        char = text[index]
        before = text[visible[position - 1]] if position else ""
        after = text[visible[position + 1]] if position + 1 < len(visible) else ""
        if position and index - visible[position - 1] > 1 and before.isdigit() and char.isdigit():
            letters.append(" ")
            where.append(visible[position - 1] + 1)
        if _significant(char):
            for folded in char.casefold():
                letters.append(folded)
                where.append(index)
        elif before.isdigit() and after.isdigit():
            letters.append(char.translate(TYPOGRAPHY))
            where.append(index)
    return "".join(letters), where


class Pages:
    """The pages of the documents the advocate sent, in reading order, and where quoted words are found in them. A page is
    {"document": name, "page": number, "text": text, ...}. Words are found on one page, or run over a page break onto the next
    page of the same document past what a page's foot and head hold; never across two documents, or across pages that are
    not next to each other. One finder for every check of where a fact's words come from (plan AN.27, P1).

    version: EXACT_FINDER, or TOLERANT_FINDER (plan AN.33, D18), which finds whatever the exact finder finds and also words that
    stand on one page, or run over a page break onto the next page of the same document, but for what _tolerant sets aside, at the
    boundaries of the page's own words."""

    def __init__(self, pages, version=EXACT_FINDER):
        if version not in (EXACT_FINDER, TOLERANT_FINDER):
            raise ValueError("Unknown finder version")
        self.pages, self.version = list(pages), version
        self._plain = [_bare(page["text"]) for page in self.pages]
        self._read = [_reading(page["text"]) for page in self.pages]
        self._tolerant = [_tolerant(page["text"]) for page in self.pages] if version == TOLERANT_FINDER else None

    @classmethod
    def of_context(cls, context, version=EXACT_FINDER):
        """The pages of a turn's context: each row is one page of one document the advocate sent."""
        return cls(({"document": row["document"]["name"], "page": row["document"].get("page"), "text": row["text"]}
                    for row in context.get("documents", ())), version)

    def holding(self, piece):
        """The page, or the two pages the words run over, that hold these words (a piece as fact_pieces gives it); or None."""
        held = self._exactly(piece)
        if held is not None or self.version == EXACT_FINDER:
            return held
        found = self._tolerantly(piece)
        return [self.pages[index] for index, _, _ in found] if found else None

    def located(self, piece):
        """Where these words stand, with the page's own words for them (tolerant finder): (the page or the two pages, their words as
        they stand there - two passages joined with ' ... ' where the words run over a page break); (the pages, None) where only the
        exact finder finds them; None where they are not found. What a check keeps as a quotation is then the page's own words,
        never the words as they were quoted."""
        if self.version != TOLERANT_FINDER:
            raise ValueError("Only the tolerant finder gives the page's own words")
        found = self._tolerantly(piece)
        if found:
            return ([self.pages[index] for index, _, _ in found],
                    " ... ".join(self.pages[index]["text"][start:end] for index, start, end in found))
        held = self._exactly(piece)
        return (held, None) if held is not None else None

    def _tolerantly(self, piece, over=True):
        """Where the pages read as the words do, but for what _tolerant sets aside, beginning and ending where the page's own words
        do: [(page index, start, end)] for a stretch of one page, or two such for words that end one page and go on at the start of
        the next page of the same document, past no more than PAGE_FURNITURE characters of its foot and head; or None. Words with
        fewer than TOLERANT_MINIMUM letters and digits are not placed so. over: False and only one page is looked at for them."""
        target = _tolerant(piece)[0]
        if sum(1 for char in target if _significant(char)) < TOLERANT_MINIMUM:
            return None
        for index, (letters, where) in enumerate(self._tolerant):
            text, at = self.pages[index]["text"], letters.find(target)
            while at >= 0:
                start, end = where[at], where[at + len(target) - 1] + 1
                if _bounded(text, start, end):
                    return [(index, start, end)]
                at = letters.find(target, at + 1)
        words = piece.split(" ") if over else ()
        for index in range(len(self.pages) - 1 if words else 0):
            first, second = self.pages[index], self.pages[index + 1]
            if (first["document"] == second["document"] and type(first["page"]) is int and type(second["page"]) is int
                    and second["page"] == first["page"] + 1 and (spans := self._tolerant_over(words, index))):
                return spans
        return None

    def _tolerant_over(self, words, index):
        """The words cut at one of their spaces, the first part ending the foot of page `index` and the rest beginning the head of
        the next page, each where the page's own words begin and end, as _tolerantly gives them; or None."""
        (foot, foot_at), (head, head_at) = self._tolerant[index], self._tolerant[index + 1]
        foot_text, head_text = self.pages[index]["text"], self.pages[index + 1]["text"]
        for cut in range(1, len(words)):
            ending, going = _tolerant(" ".join(words[:cut]))[0], _tolerant(" ".join(words[cut:]))[0]
            at, begin = foot.rfind(ending) if ending else -1, head.find(going) if going else -1
            if at < 0 or begin < 0:
                continue
            first = (index, foot_at[at], foot_at[at + len(ending) - 1] + 1)
            second = (index + 1, head_at[begin], head_at[begin + len(going) - 1] + 1)
            # The foot and the head beside the words are measured as the exact finder measures them: the page's words as they read,
            # the reader's notes aside.
            if (len(_reading(foot_text[first[2]:])) <= PAGE_FURNITURE and len(_reading(head_text[:second[1]])) <= PAGE_FURNITURE
                    and _bounded(foot_text, *first[1:]) and _bounded(head_text, *second[1:])):
                return [first, second]
        return None

    def _exactly(self, piece):
        """The exact finder: the page, or the two pages the words run over, that hold these words; or None."""
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
                index = self._one_page(run)
                if index is not None:
                    plain, quoted = self._plain[index], run
                    if run not in plain:
                        plain, run = self._read[index], _reading(run)
                    if run not in plain:  # placed by the tolerant finder: the page's own words for the run, among the page's words
                        _, begins, ends = self._tolerantly(quoted, over=False)[0]
                        text = self.pages[index]["text"]
                        run = _bare(text[begins:ends])
                        plain = " ".join(part for part in (_bare(text[:begins]), run, _bare(text[ends:])) if part)
                    at = plain.find(run)
                    first, last = plain[:at].count(" "), plain[:at + len(run)].count(" ") + 1
                    around = " ".join(plain.split(" ")[max(0, first - NEAREST_AROUND):last + NEAREST_AROUND])
                    return {"document": self.pages[index]["document"], "page": self.pages[index]["page"], "run": run,
                            "words": around}
        return None

    def _one_page(self, piece):
        """The index of the first page that holds these words by itself - as the exact finder reads them, then, for the tolerant
        finder, but for what _tolerant sets aside - or None. Words that hold only over a page break are not looked for: nearest
        shows the longest run one page holds."""
        for index, plain in enumerate(self._plain):
            if piece in plain:
                return index
        words = _reading(piece)
        for index, read in enumerate(self._read):
            if words and words in read:
                return index
        found = self._tolerantly(piece, over=False) if self.version == TOLERANT_FINDER else None
        return found[0][0] if found else None

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
#: What the model is told when its understanding states a figure that none of the advocate's messages and none of the documents give.
FIGURE_FIX = ("Do not work out a figure yourself: use one the advocate or a paper gives, copied as it stands, or say that it has not "
              "been worked out. Code adds up the figures of the papers' transactions.")


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


def _figure_problems(understanding, context):
    """The figures the understanding states that none of the advocate's messages and none of the documents they sent give (plan
    AN.27, P23; AN.29, D9; invariant I6). Counting is code's work (figures.py adds the papers' transactions): a total, a difference or
    an estimate that a model worked out is refused to it, in words, and left out when it revises. A figure is a number with a unit
    beside it (figures.quantities_in); it is the papers' own if the same number stands against the same unit, or the same amount of
    the same kind, in a message or a paper. One problem for each figure, naming every place it is stated. What an earlier note of
    ours or a record of the matter holds is not a message or a paper."""
    sources = [row["text"] for row in advocate_messages(context)] + [row["text"] for row in context.get("documents", ())]
    pairs, amounts = set(), set()
    for text in sources:
        for _, number, unit in figures.quantities_in(" ".join(text.split())):
            value = figures.number_of(number)
            if value is not None:
                pairs.add((unit, value))
                amounts.add((figures.UNITS[unit].dimension, value * figures.UNITS[unit].size))
    stated = {}
    for name, item in understanding.items():
        for place, text in _words_of(item, _PLACES.get(name, f"the {name.replace('_', ' ')}"), name):
            for words, number, unit in figures.quantities_in(" ".join(text.split())):
                value = figures.number_of(number)
                if value is None or (unit, value) in pairs or (figures.UNITS[unit].dimension, value * figures.UNITS[unit].size) in amounts:
                    continue
                kept = stated.setdefault((unit, value), {"words": words, "places": []})
                if place not in kept["places"]:
                    kept["places"].append(place)
    return [{"problem": f"The understanding states the figure {kept['words']!r} ({', '.join(kept['places'])}), which is in none of the "
                        "advocate's messages or the documents they sent; it reads as a total, a difference or an estimate that was "
                        "worked out.", "fix": FIGURE_FIX} for kept in stated.values()]


#: What the model that revises an understanding is told when code cannot find the words something rests on (research v14, AN.33,
#: D18): decide whether the failure is a slip in copying or a real one, and correct only what fails.
SLIP_FIX = ("Decide whether the words were copied with a slip - a letter or digit a scan misread, a space inside a word or a number, "
            "a name spelt otherwise, a word added or left out, passages joined without '...' - or whether the papers do not say this. "
            "For a slip, copy the words from the page exactly as they stand there, the slip included, keeping what you add yourself "
            "outside the quotation marks (separate passages joined with '...'); where only part of {what} is in the papers, keep {what} "
            "to that part; leave {what} out only where the advocate's messages and the papers do not give it at all.")


def code_checks(understanding, context):
    """Mechanical checks only; meaning is the model's work."""
    problems = []
    advocate = _bare(" ".join(row["text"] for row in advocate_messages(context)))
    # A fact may rest on a document the advocate sent; where its words appear is the
    # code's to establish (owner decisions, 15 Oct 2026). From research v14 (AN.33, D18) the tolerant finder: a slip in copying
    # that cannot change the meaning is no problem, and what is a problem is settled by the model that revises, from the page's
    # own words code shows it - a fact is never lost for a slip in its quotation.
    pages = Pages.of_context(context, TOLERANT_FINDER)
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
                             "fix": SLIP_FIX.format(what="this fact")})
    # v13 (AN.28): each party's part in a proceeding and each subject rest on the page's own words, found by code as a fact's are.
    said = [(f"{party['who']}'s part in {part['proceeding']}", part["words"]) for party in understanding.get("parties", ())
            for part in party.get("parts", ())]
    said += [(f"the subject {subject['identifier']}", subject["words"]) for subject in understanding.get("subjects", ())]
    for place, quoted in said:
        missing = [piece for piece in fact_pieces(quoted) if piece not in advocate and pages.holding(piece) is None]
        if missing:
            problems.append({"problem": f"For {place}, the quoted words do not appear in the advocate's messages or the documents "
                                        f"they sent ({quoted!r}); {pages.stops(missing[0])}.",
                             "fix": SLIP_FIX.format(what="it")})
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
    return problems + _figure_problems(understanding, context)


def _matter_text(understanding, disputes):
    lines = [f"Matter: {understanding['summary']}", "Asked: " + "; ".join(understanding["asked"])]
    for dispute in disputes:
        lines.append(f"\nDispute {dispute['id']}: {dispute['name']} (between {', '.join(dispute['between'])})")
        for q in dispute["legal_questions"]:
            law = "; ".join(q["law_to_check"]) or "none named"
            lines.append(f"- {q['id']}: {q['question']} [law your colleague would check first: {law}]")
    return "\n".join(lines)


def _effort(step, user, again=False):
    """How hard a research step reasons: reasoning.py owns the policy (plan AN.30) - by the step, by what it reads, and by whether it
    looks again at work already done (again)."""
    return reasoning.effort(step, tokens=estimate_tokens(user), again=again)


def _call(model, operation, system, user, schema, step, again=False, marks=()):
    """One research step's call. marks (v14, plan AN.34): the places in user where material other calls carry alike ends - the
    opening every call shown the file shares - each kept by the cache for them to read. A call reads it only where its effort, its
    answer's schema and its instructions are those of the call that wrote it (the probe of 2 Nov 2026): the calls of one step."""
    receipt = model.structured(Prompt(system=system, user=user, operation=operation, effort=_effort(step, user, again),
                                      cache_through=marks[0] if marks else 0, cache_also=tuple(marks[1:])),
                               schema, Tier.ROUTINE, max_tokens=min(MAX_OUTPUT[step], reasoning.room(
                                   model, Tier.ROUTINE, system, user, json.dumps(schema))))
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
                                   _matter_text(understanding, [dispute]), STATUTE_PHRASES_V15, "phrases"), None
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


def _placed(words, finder):
    """Where an item's words stand, by the tolerant finder (research v14, AN.33 D18): (anchored, the numbers of the pages they are on,
    the words to keep). The words kept are the page's own where every passage stands on a page - each as the page has it, joined
    with ' ... ' - so that what is kept as a quotation is the page's text; else the words as given."""
    pieces = fact_pieces(words)
    found = [finder.located(piece) for piece in pieces]
    if not pieces or not all(found):
        return False, [], words
    own = [text for _, text in found]
    return (True, sorted({page["page"] for held, _ in found for page in held}),
            " ... ".join(own) if all(text is not None for text in own) else words)


def _file_context(context, documents, whole):
    """What a v13 record step is shown before the pages it reads for (plan AN.28, D1): the advocate's messages, oldest first, and,
    where the file is within WHOLE_FILE_TOKENS, every page of it under its paper's name - so that the step knows what the matter is
    about and who is who while it answers for its own pages. From plan AN.34 (piece 34b) the whole file, its own pages among them,
    so that every call shown it opens with the same text and the cache keeps it once for the rest."""
    lines = ["The advocate's messages, oldest first:", *(f"- {row['text']}" for row in advocate_messages(context))]
    if whole:
        lines += ["", "The whole file, for context - the pages you read for among them:"]
        lines += [f'Paper "{other["name"]}", {"part" if other["recording"] else "page"} {page["page"]}: {page["text"]}'
                  for other in documents for page in other["pages"]]
    return "\n".join(lines)


def _reading_text(context, documents, document, window, whole):
    """A stretch's reading as its call reads it, and the place the cache keeps (plan AN.34, piece 34b): (user, the end of the opening
    every call shown the file shares - 0 where the file is not shown)."""
    opening = "" if whole is None else _file_context(context, documents, whole) + "\n\nThe pages you read for:\n"
    return opening + _window_text(document, window), len(opening) if whole else 0


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
    finders = {document["source"]: Pages(document["pages"], TOLERANT_FINDER) for document in documents}

    def read(task, depth=0):
        document, window = task
        first, last = window[0]["page"], window[-1]["page"]
        user, opening = _reading_text(context, documents, document, window, whole)
        try:
            data = _call(model, operation, system, user, schema, step, marks=(opening,) if opening else ())
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
    """The events one answer gives (v14): each placed by the tolerant finder and kept in the page's own words, with the words as
    quoted beside them where they differ; where its date stands is code's, after (_date_found)."""
    events = []
    for item in data["events"]:
        given = item["words"].strip()
        anchored, pages, words = _placed(given, finder)
        events.append({"date": item["date"].strip(), "kind": item["kind"], "what": item["what"].strip(),
                       "said_by": item["said_by"].strip(), "document": document["name"], "source": document["source"],
                       "pages": pages, "words": words, "anchored": anchored, "quoted": "" if words == given else given,
                       "settled": "", "settled_why": "", "date_found": "none", "second_pass": False})
    return events


#: v14 (AN.33, D17 and D25; piece 33g; owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important
#: details are extracted"): after a paper's reading, a second pass over each stretch of it, shown what was read from the paper and
#: asked only what that leaves out. It is the reading's own call - its prompt and the same file before the pages - with this after
#: them, so that it reads as the reading did; what it gives is placed, checked and settled with the rest. In AN.31 two readings of
#: the same papers made blind each found points the other missed.
SECOND_PASS = """What the reading already set out from this paper, point by point (date, kind, what, said_by):
{listed}

Read the pages you read for again, now only for what that list leaves out: any point there that a careful lawyer would need - an event, an order or a thing it found, a filing or a matter pending, what a party says, a document's particulars, who is related to whom, where matters stand. Give each as an event, as the reading would have; give none where the list holds them all. Do not give again a point the list holds, in whatever words it is put."""


def _same_point(one, other):
    """Whether a point the second pass gives is one its paper's list holds already, word for word (v14): the same kind and the same
    date and what, or the same words placed on the same pages. Any other likeness is the model's to judge, as it is told."""
    if one["kind"] != other["kind"]:
        return False
    if (one["date"], " ".join(one["what"].split()).casefold()) == (other["date"], " ".join(other["what"].split()).casefold()):
        return True
    return bool(one["anchored"] and other["anchored"] and one["words"] and one["words"] == other["words"]
                and one["pages"] == other["pages"])


def _second_pass(model, context, documents, events, failures, whole):
    """The second pass over each stretch of each paper (v14, AN.33 piece 33g), all at once: one call for each stretch whose reading
    did not fail, shown the file as its reading was and the points read from its paper, asked only what they leave out. Returns (the
    events it adds - placed as the reading's are, each marked second_pass, none the paper's list holds word for word - and a record of
    each pass: how many it added, or why it could not be made). A pass that fails adds nothing and leaves the reading as it was; a
    usage limit still stops the turn."""
    finders = {document["source"]: Pages(document["pages"], TOLERANT_FINDER) for document in documents}
    tasks = [(document, window) for document in documents for window in _windows(document["pages"])
             if not {page["page"] for page in window} <= _unread(failures, document)]
    if not tasks:
        return [], []

    def look(task):
        document, window = task
        first, last = window[0]["page"], window[-1]["page"]
        label = f"{first}-{last}" if first != last else f"{first}"
        held = [event for event in events if event["source"] == document["source"]]
        listed = "\n".join(json.dumps({key: event[key] for key in ("date", "kind", "what", "said_by")}, ensure_ascii=False)
                           for event in held) or "(none)"
        read, opening = _reading_text(context, documents, document, window, whole)
        user = read + "\n\n" + SECOND_PASS.format(listed=listed)
        try:
            data = _call(model, "core_research_chronology", CHRONOLOGY_V14, user, CHRONOLOGY_SCHEMA_V14, "chronology_second",
                         marks=(opening,) if opening else ())
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation) as exc:
            return [], {"document": document["name"], "pages": label, "added": 0, "reason": type(exc).__name__}
        added = []
        for event in _events_in(data, document, finders[document["source"]]):
            if not any(_same_point(event, other) for other in (*held, *added)):
                added.append({**event, "second_pass": True})
        return added, {"document": document["name"], "pages": label, "added": len(added), "reason": ""}

    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
        done = list(pool.map(look, tasks))
    return [event for added, _ in done for event in added], [record for _, record in done]


#: v14 (AN.33, D17; owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details are extracted"):
#: one paper read, with the whole file in view as from v13, for every legally significant point it records - its events in time, and
#: what its authorities found, what its parties assert, admit, deny or allege, the particulars of the documents it describes, who is
#: related to whom, and what it says stands, is done or remains to be done.
CHRONOLOGY_V14 = """Message: You receive an advocate's messages to us about a client's matter, the documents they sent, and the pages of one paper you read for now: the whole file comes first, page by page under each paper's name - the pages you read for among them - and the pages you read for again last, under "The pages you read for". A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. A page read from a scan may carry [illegible] and square-bracket notes about stamps, signatures and handwriting; those are the page reader's, except the handwriting a note transcribes, which is the page's. The file is there so that you know what the matter is about and who is who: list only what the pages you read for record.

Purpose: Set out everything that paper records which a careful lawyer would need in order to understand the matter and advise the client, so that nothing in it is overlooked: what happened and when, and also what its authorities found, what its parties say, the particulars of the documents it describes, who is related to whom, and where it says matters stand. You are not judging which account is right, and you are not answering any legal question.

Look for:
- Each event the paper records, whatever its date: a sale, partition or other deed, an entry in an official record, an order or direction of a court or authority, an appeal, revision, petition, suit, complaint, FIR or charge sheet, a notice, a hearing or listing, a payment, a death; and each proceeding it says is pending, with its stage.
- When the event happened, as the page gives it ("14-08-1993", "3 February 2011", "1996", "1979-80"). A sentence often names the date of an earlier order, deed or filing it mentions: that date is that earlier act's, not this event's. Where the page gives no date for this event, say undated. Do not work out, convert or guess a date. A case or document number carries the year it was filed or registered: where that year is all the page gives of when the case was filed or the document registered, give it as the date of that filing or registration, not "undated".
- For an order or direction: what the authority directed, and, as points of their own, each thing it found - of fact or of law - that its directions rest on or that bears on the parties (kind finding), each saying in what it stands which order it is in. For a filing, appeal or proceeding: who brought it and who answers it, as the page names them.
- What each party or witness says - asserts, admits, denies, alleges or offers - where it bears on the matter, as that party's own (kind statement), with whose words they are.
- The particulars of a document the paper records or describes that could matter: its number, its dates of execution, presentation or registration, who signed or attested it, what it is said to be, an endorsement or stamp a page records on it (kind document).
- Who is related to whom, or acts for whom - an heir, a son or daughter, a guardian, an agent under a power of attorney, a legal representative - as the paper says it (kind relationship).
- Where the paper says matters stand: what is pending (kind pending), and what it says is done, settled, outstanding or still to be done, and by whom (kind status).
- Who says it: the paper's own author, or the party or authority it reports; a party's allegation stays that party's.
- The figures and identifiers that belong to each point - amounts, quantities and the numbers that identify a document, case, file, account or item - exactly as the page gives them.
- An order, decree or judgment that a later proceeding enforces, challenges, reviews or relies on is an event of its own at its own date, even where the page only recites it: list it once, and let the later proceeding refer to it.
- One point for each act, finding, statement, particular or relationship. A paper that says the same thing again - a party's account and its written arguments, an order's own recital - records it once: list it once. Do not merge what the paper keeps apart, and add nothing the page does not say. A register or list of many similar entries is one point for the whole list, naming its range and the entries that matter.
Work in a loop: list the points page by page, then read each page again against your list for anything you skipped or misread, or any date you gave to the wrong act, and correct the list before you answer.

Outcome: events, in the order of the pages. Each has: date; kind (transaction, order, finding, filing, pending, statement, document, relationship, status, or other); what (plain sentences saying what the point is, with its figures and identifiers - what an order found and directed, who brought and who answers a proceeding, which order a finding is in, whose a statement is); said_by (whose words they are: the document's own author, or the party or authority it reports); words (the exact words on a page that record it, copied exactly as the page gives them, without the reader's square-bracket notes - a sentence that runs over a page may be copied whole - or several passages joined with '...'; never reword)."""
#: v14 (AN.33, D18 and D22; owner, 1 Nov 2026: "let model decide whether this is a clerical error or a genuine failed test"): one call
#: settles what code could not check, for one paper (or, for the points read side by side, the papers together), shown code's
#: evidence; code checks what it gives. One prompt for every kind of item, said for each.
SETTLE = """Message: You {listed}. Code then checked each against the papers: that its words stand on {where}, word for word{checks}. You receive the advocate's messages and the papers, {focus}and what code could not check (to_check): each {noun} as you listed it, by its index, with why code could not check it and, where code found them, the page's own words nearest to yours. A page says what its document says; square-bracket notes are the page reader's, except the handwriting a note transcribes, which is the page's.

Purpose: For each {noun} in to_check, decide whether the check failed because of a slip in copying or because the {noun} is not as the papers record it, and give what code can check - so that nothing the papers record is lost for a slip, and nothing they do not record is kept.

Look for:
- A slip in copying: the page holds the same words with a difference - a letter or digit a scan misread, a space inside a word or a number, a name spelt otherwise, a word added or left out, passages joined without '...'. Give the {noun} again with its words copied from the page exactly as they stand there, the slip included (verdict clerical).
- Words, or a date, that stand on another page or in another paper: give the {noun} with them as they stand there (verdict elsewhere).
- Only part of the {noun} in the papers: give it again within what the papers hold, so that only the part they do not hold goes (verdict part).
- A page whose text seems itself misread from its scan, so that its right words cannot be copied: keep the {noun} as you read it and say in reason what seems misread (verdict scan_misread).
- A {noun} you still find recorded as you listed it, though code cannot find it: keep it and say in reason why (verdict as_listed).
- A {noun} the papers do not record: say so in reason (verdict not_in_papers); it is withdrawn.{extra}
Never work out a date or a figure the papers do not give. Work in a loop: decide each, check what you give against the page, and correct it before you answer.

Outcome: settled, one entry for each {noun} in to_check: index (its index in to_check); verdict (clerical, elsewhere, part, scan_misread, as_listed or not_in_papers); reason (one sentence); {key} (the {noun} as it should stand, every field as before{fields}).{outcome}"""
#: v14: a paper's events settled.
SETTLE_EVENTS = SETTLE.format(
    listed="listed the events one paper an advocate sent records", noun="event", key="event", where="the pages of its paper",
    checks=", and that the numbers of its date stand in its words or in the papers",
    focus="the pages of the paper being checked last, under \"The pages of the paper being checked\", ",
    extra="\n- Dates that stand on the paper's pages but in none of its events (not_carried): for each, give in added the event the "
          "paper records with it, if it marks one; give nothing for a date that marks no event (a stamp's date, a printed form's).\n"
          "- Identifiers - numbers of documents, cases, files or items - that stand on the paper's pages but in none of its events "
          "(identifiers_not_carried), and pages none of its events is on (pages_without_points): for each, give in added what the "
          "paper records there that a careful lawyer would need, each as an event; give nothing where it records nothing of the kind "
          "(a house number, a printed form's number, a page of signatures or stamps).",
    fields=": date; kind; what; said_by; words",
    outcome=" added: the events you give for not_carried, identifiers_not_carried and pages_without_points, each as an event.")


def _settle_schema(key, item):
    """What a settling call answers (v14): for each item code could not check, its index, verdict, reason and the item as it should
    stand; for a paper's events, also those it adds for the dates no event carried."""
    entry = _object({"index": {"type": "integer"}, "verdict": {"type": "string", "enum": list(VERDICTS)}, "reason": STRING,
                     key: item})
    return _object({"settled": {"type": "array", "items": entry},
                    **({"added": {"type": "array", "items": item}} if key == "event" else {})})


SETTLE_EVENTS_SCHEMA = _settle_schema("event", EVENT_V14)
#: A paper's dates code finds on its pages to ask about at most (v13): the rest are not asked about.
NOT_CARRIED_MOST = 20


def _numbers(words):
    """The numbers some words hold, a month written as a name counted as its number, a number written in words as its number (the
    twelfth day of the month, the year in words: figures.numbers_in_words), and a two-digit year as the years it may stand for: what a
    date's numbers must be found among (v13)."""
    found = {int(n) for n in re.findall(r"\d+", str(words))} | figures.numbers_in_words(words)
    found |= {_MONTHS[name] for name in re.findall(rf"\b({_MONTH})\b", str(words).casefold())}
    return found | {n % 100 for n in found if n >= 1000} | {2000 + n for n in found if n < 100} | {1900 + n for n in found if n < 100}


def _paper_numbers(pages):
    """Every number the pages of one paper hold (as _numbers reads them), the reader's notes aside."""
    held = set()
    for page in pages:
        held |= _numbers(_reading(page["text"]))
    return held


def _date_found(item, paper_numbers, file_numbers):
    """Where code finds the numbers of an item's date (research v14, AN.33 D18): every number of the date - a month by name or number,
    a year by four digits or its last two - among its words ("words"), else among its words and its paper's pages ("paper": a paper
    may give a date on another page than the passage it belongs to), else among those of any page of the file ("file": an order a
    note mentions may be dated by another paper), else "nowhere"; "none" where it gives no date code reads. A date is kept whatever
    is found: code says where it stands, and a model settles one found nowhere."""
    if not read_date(item["date"], months=True):
        return "none"
    wanted, said = {n for n in _numbers(item["date"]) if n} - {0}, _numbers(item["words"])
    if wanted <= said:
        return "words"
    if wanted <= said | paper_numbers:
        return "paper"
    return "file" if wanted <= said | paper_numbers | file_numbers else "nowhere"


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


#: v14 (AN.33, D17; piece 33e): an identifier as a page writes one - a number of a document, case, file or item with a stroke in it
#: ("715/92", "K/2257/2012", "C.R.P. 88/2020"), or "No. 58 of 2014" - read for the numbers it holds, which a point must carry.
_IDENTIFIER = re.compile(r"(?<![\w/])(?:[^\W\d_]{1,6}\d?[./]?\s*)?\d{1,6}(?:\s*/\s*[^\W_]{1,6}){1,3}(?![\w/])"
                         r"|\b(?:No\.?\s*)?(\d{2,6})\s+of\s+(\d{4})\b", re.I)
#: A paper's identifiers and pages that no point carries are all asked about (v14; D27, owner 2 Nov 2026: no list cut to a number).
#: The letters and digits a page must hold for its holding no point to be asked about (v14): a cover or a stamp page holds fewer.
PAGE_LETTERS = 200


def _cores(text):
    """The numbers the identifiers in some words hold, each as its digits joined by strokes ("88/2020"), "No. 88 of 2020" read
    the same: what an identifier on a page is matched by in the points (v14)."""
    found = set()
    for match in _IDENTIFIER.finditer(" ".join(str(text).split())):
        core = (f"{match.group(1)}/{match.group(2)}" if match.group(1) else
                "/".join(part for part in re.split(r"\s*/\s*", re.sub(r"^[^\d]*", "", match.group(0))) if part))
        if sum(char.isdigit() for char in core) >= 3 and not read_date(core.replace("/", "-")).count("-") == 2:
            found.add(core.casefold())
    return found


def _uncovered(document, events, unread=()):
    """What of a paper's pages no point of it carries (v14, AN.33 piece 33e), to be asked about once in its settling call: the
    identifiers on its pages, outside the reader's notes, whose numbers no point's words or account hold - each once, as the page
    writes it, with its page - and the pages no point is placed on that hold at least PAGE_LETTERS letters and digits; from D27
    (piece 33p) every one of them, none cut to a number. unread: the pages not to ask about - those whose reading failed, which a
    failure already names, and those read already as copies (_read_as_copies)."""
    mine = [event for event in events if event["source"] == document["source"]]
    carried = set()
    for event in mine:
        carried |= _cores(event["words"]) | _cores(event["what"])
    identifiers, seen = [], set()
    for page in document["pages"]:
        if page["page"] in unread:
            continue
        for match in _IDENTIFIER.finditer(" ".join(_MARKS.sub(" ", page["text"]).split())):
            for core in _cores(match.group(0)):
                if core not in carried and core not in seen:
                    seen.add(core)
                    identifiers.append({"identifier": match.group(0), "page": page["page"]})
    named = {(event["source"], number) for event in events for number in event["pages"]}
    pages = [page["page"] for page in document["pages"]
             if page["page"] not in unread and (document["source"], page["page"]) not in named
             and sum(1 for char in _reading(page["text"]) if char.isalnum()) >= PAGE_LETTERS]
    return {"identifiers": identifiers, "pages": pages}


def _read_as_copies(document, events, copied, earlier):
    """The pages of a paper that are copies of a page of an earlier paper (earlier: their sources) some point is placed on (v14, AN.33
    piece 33e; copied: the pairs copy_figures finds): read already, so neither their dates, nor their identifiers, nor they themselves
    are asked about again - the first paper of a set of copies is the one asked about."""
    named = {(event["source"], number) for event in events for number in event["pages"]}
    return {page for pair in copied for (source, page), other in (tuple(pair), tuple(pair)[::-1])
            if source == document["source"] and other[0] in earlier and other in named}


def _unread(failures, document):
    """The pages of a paper a failure names (v13): "3" or "1-4"."""
    pages = set()
    for failure in failures:
        if failure["document"] == document["name"]:
            first, _, last = str(failure["pages"]).partition("-")
            if first.isdigit() and (last or first).isdigit():
                pages |= set(range(int(first), int(last or first) + 1))
    return pages


#: Why code could not check an item, as the model that settles it is told (v14).
_NOT_FOUND = "its words are not found, word for word, on {where}"
_NO_DATE = "the numbers of its date stand neither in its words nor anywhere in the papers"


def _to_check(index, given, why, words, finder):
    """One item a settling call is shown (v14): its index, the item as the model gave it, why code could not check it, and the page's
    own words nearest to its words where code finds them."""
    near = finder.nearest(fact_pieces(words)[0]) if fact_pieces(words) else None
    return {"index": index, **given, "why": why, **({"nearest_words": near["words"]} if near else {})}


def _settle_text(context, documents, document, whole, shown):
    """What a settling call for one paper reads (v14), and the place the cache keeps (plan AN.34, piece 34b): (the advocate's messages
    and the file as the reading of that paper was shown them, the paper's own pages last, then what code could not check; the end
    of the opening every call shown the file shares)."""
    opening = _file_context(context, documents, whole) + "\n\nThe pages of the paper being checked:\n"
    return opening + _window_text(document, document["pages"]) + "\n\n" + json.dumps(shown, ensure_ascii=False), len(opening)


def _settled(entries, failing, key, shape, document_name, what):
    """What a settling call's answer does to the items that failed a check (v14): the first entry for each index counts. An item the
    model finds the papers do not record is withdrawn - listed apart, with its words and why, never kept; any other is kept as the
    model gives it, placed again by code (shape), with the verdict and why beside it, whether code can now check it or not; an item
    the answer names no verdict for stays as it was, marked unanswered. Returns (kept, withdrawn)."""
    by_index = {}
    for entry in entries:
        if type(entry["index"]) is int and 0 <= entry["index"] < len(failing):
            by_index.setdefault(entry["index"], entry)
    kept, withdrawn = [], []
    for index, item in enumerate(failing):
        entry = by_index.get(index)
        if entry is None:
            kept.append({**item, "settled": "unanswered", "settled_why": ""})
        elif entry["verdict"] == "not_in_papers":
            withdrawn.append({"kind": {"transfer": "transaction", "connection": "point"}.get(key, key), "document": document_name,
                              "what": what(item), "words": item["words"], "why": entry["reason"].strip()})
        else:
            # Where the item came from stays with it: an event the second pass gave is still the second pass's (piece 33g).
            came = {"second_pass": item["second_pass"]} if "second_pass" in item else {}
            kept.append({**shape(entry[key]), **came, "settled": entry["verdict"], "settled_why": entry["reason"].strip()})
    return kept, withdrawn


def _checked(model, context, events, documents, finders, failures=(), whole=True, withdrawn=None):
    """v14 (AN.33, D18 and D22): each paper's events checked by code - their words placed by the tolerant finder and kept in the
    page's own words, the numbers of their dates looked for in their words, their paper and the file - and, for a paper where an
    event's words are not found or its date is found nowhere, or a date on its pages is carried by no event, one call that settles
    them, shown code's evidence; code places what it gives again. No date is erased; an event still unchecked stays, marked so. An
    event the model finds the papers do not record goes to withdrawn (a list), with why. The papers are settled all at once."""
    file_numbers = _file_numbers(documents)
    from nm.core_engine import copy_figures  # it reads research's own finder; imported here, where it is used
    copied = copy_figures.copies([{"document": document["name"], "key": document["source"], "page": page["page"],
                                   "id": f'{document["source"]}p{page["page"]}', "text": page["text"]}
                                  for document in documents for page in document["pages"]])
    earlier = {document["source"]: {other["source"] for other in documents[:index]} for index, document in enumerate(documents)}

    def one(document):
        mine = [event for event in events if event["source"] == document["source"]]
        finder, paper = finders[document["source"]], _paper_numbers(document["pages"])
        for event in mine:
            event["date_found"] = _date_found(event, paper, file_numbers)
        failing = [event for event in mine if not event["anchored"] or event["date_found"] == "nowhere"]
        # v14 (AN.33, piece 33e): a page that is a copy of one a point is placed on is read already; the identifiers and the pages of
        # the paper no point carries are asked about in the same call as its dates no point carries.
        skip = _unread(failures, document) | _read_as_copies(document, events, copied, earlier[document["source"]])
        missing = _not_carried(document, [{**event, "sort": read_date(event["date"], months=True)} for event in mine], skip)
        uncovered = _uncovered(document, events, skip)
        if not (failing or missing or uncovered["identifiers"] or uncovered["pages"]):
            return mine, []
        to_check = [_to_check(index, {key: event[key] for key in EVENT["properties"]},
                              _NOT_FOUND.format(where="the pages of its paper") if not event["anchored"] else _NO_DATE,
                              event["words"], finder) for index, event in enumerate(failing)]
        user, opening = _settle_text(context, documents, document, whole, {"to_check": to_check, "not_carried": missing,
                                                                  "identifiers_not_carried": uncovered["identifiers"],
                                                                  "pages_without_points": uncovered["pages"]})
        kept = [event for event in mine if all(event is not wrong for wrong in failing)]
        try:
            data = _call(model, "core_research_chronology", SETTLE_EVENTS, user, SETTLE_EVENTS_SCHEMA, "chronology_check",
                         marks=(opening,) if whole else ())
            require_schema(data, SETTLE_EVENTS_SCHEMA)
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation):
            return kept + [{**event, "settled": "unavailable"} for event in failing], []
        settled, gone = _settled(data["settled"], failing, "event", lambda given: _events_in({"events": [given]}, document, finder)[0],
                                 document["name"], lambda event: event["what"])
        # An event added for a date no event carried counts once, beside those already kept.
        held = {(event["date"], event["kind"], event["words"]) for event in kept + settled}
        added = [event for event in _events_in({"events": data["added"]}, document, finder)
                 if (event["date"], event["kind"], event["words"]) not in held]
        for event in settled + added:
            event["date_found"] = _date_found(event, paper, file_numbers)
        return kept + settled + added, gone
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(documents)))) as pool:
        done = list(pool.map(one, documents))
    if withdrawn is not None:
        withdrawn.extend(item for _, gone in done for item in gone)
    return [event for mine, _ in done for event in mine]


def chronology_of(model, context, *, wanted=None, withdrawn=None, passes=None):
    """The chronology the documents of a turn record, as (events, failures) - plan AN.27, P8.

    The model says what a page records; code does the rest: finds the event's words in the document (the one finder), records the
    pages, reads the date, orders the events by it - the undated last, in the papers' order - and numbers them E1.... An event
    whose words are not found is kept, marked not anchored, never dropped and never to be cited as sourced. withdrawn: a list that
    receives the events a settling call found the papers do not record (v14). passes: a list that receives the record of each second
    pass over a stretch of a paper, made after its reading for what it left out (v14, piece 33g)."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], []
    whole = _whole_file(context, documents)
    events, failures = _read_stretches(model, context, None, "core_research_chronology", CHRONOLOGY_V14, CHRONOLOGY_SCHEMA_V14,
                                       "chronology", _events_in, whole=whole)
    if wanted is None or wanted():
        added, made = _second_pass(model, context, documents, events, failures, whole)
        events = events + added
        if passes is not None:
            passes.extend(made)
    events = _checked(model, context, events, documents, {document["source"]: Pages(document["pages"], TOLERANT_FINDER)
                                                          for document in documents}, failures, whole, withdrawn)
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


def _quantity(given):
    """A quantity as the plan keeps it: the model's reading of a figure, with every field present."""
    given = given if isinstance(given, dict) else {}
    parts = [{key: str(part.get(key, "")).strip() for key in ("number", "unit", "written")}
             for part in given.get("parts") or () if isinstance(part, dict)]
    return {"dimension": str(given.get("dimension") or "none").strip(), "parts": parts}


def _transfers_in(data, document, finder):
    """The transactions one answer gives (v14): placed and kept in the page's own words as events are (_events_in)."""
    transfers = []
    for item in data["transfers"]:
        given = item["words"].strip()
        anchored, pages, words = _placed(given, finder)
        transfers.append({"date": item["date"].strip(), "kind": item["kind"], "subject": item["subject"].strip(),
                          "figure": item["figure"].strip(), "quantity": _quantity(item.get("quantity")),
                          "whole": item["whole"].strip(), "whole_quantity": _quantity(item.get("whole_quantity")),
                          "from": item["from"].strip(), "to": item["to"].strip(), "instrument": item.get("instrument", "").strip(),
                          "giver_died": item.get("giver_died", "").strip(), "giver_died_sort": "", "document": document["name"],
                          "source": document["source"], "pages": pages, "words": words, "anchored": anchored,
                          "quoted": "" if words == given else given, "settled": "", "settled_why": "", "date_found": "none",
                          "giver_died_found": False})
    return transfers


#: v13 (AN.28, D1, D3, D7, B16): the transactions of one paper, of any kind, read with the whole file in view.
TRANSACTIONS_V13 = """Message: You receive an advocate's messages to us about a client's matter, the documents they sent, and the pages of one paper you read for now: the whole file comes first, page by page under each paper's name - the pages you read for among them - and the pages you read for again last, under "The pages you read for". A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. Square-bracket notes are the reader's, not the document's. The file is there so that you know what the matter is about and who is who: list only what the pages you read for record.

Purpose: List the transactions those pages record or report - whatever passes from one person to another: a sale, partition, gift, settlement, decree, lease, mortgage, loan or payment of anything - so that code can add the figures up for each subject and set them against any whole the papers state. You are not adding or working out anything yourself, and you are not judging which account is right.

Look for:
- Each transaction, whatever its date: who gave it up (from), who took it (to), what it concerns (subject: the asset, account, contract or case, named as the papers most commonly name it - give the same subject the same name wherever it stands in the file), the figure transferred exactly as the page writes it (figure), the number that identifies the document recording it, as the page writes it (instrument; empty where none is given), the date as the page gives it ("undated" where it gives none), and, where the papers record that the giver had died by then, the date of that death as the papers give it (giver_died; empty where none is recorded).
- What the figure is (quantity), read from the page's own words and never worked out: its dimension - money, area, length, mass or volume where it is an amount of that; share where it is a part of a whole; rate where it is a price or charge for a period or a measure; period where it is a length of time; none where the passage gives no figure - and, for an amount, its parts: each number exactly as the page writes it, in digits, with the unit it stands against, named in plain words (unit), and that unit exactly as the page writes it (written). A figure written in two units has two parts. You convert and add nothing.
- The whole the transaction is out of, where the same passage states one (whole, exactly as written, with its quantity read the same way); otherwise leave both empty.
- The exact words on a page that record the transaction, long enough to hold its figure and any whole it states, copied exactly as the page gives them, without the reader's square-bracket notes - or several passages joined with '...'; never reword.
- One entry for each transaction. A paper that reports the same transaction again records one: give it once. Do not list a transaction that gives no figure, do not add or work out a figure the page does not give, and do not merge transactions the page keeps apart.
Work in a loop: list the transactions page by page, then read each page again against your list for any transaction, figure, number or date you skipped or misread, and correct the list before you answer.

Outcome: transfers, in the order of the pages. Each has: date; kind (sale, partition, gift, settlement, decree, lease, mortgage, loan, payment, or other); subject; figure; quantity; whole; whole_quantity; from; to; instrument; giver_died; words."""


#: v14: a paper's transactions settled (AN.33, D18 and D22), as its events are.
SETTLE_TRANSFERS = SETTLE.format(
    listed="listed the transactions one paper an advocate sent records", noun="transaction", key="transfer",
    where="the pages of its paper",
    checks=", that its figure and any whole it states can be checked against those words, that the death it records of the giver "
           "stands in the papers, and that the numbers of its date stand in its words or in the papers",
    focus="the pages of the paper being checked last, under \"The pages of the paper being checked\", ",
    extra="\n- For a figure or a whole: give it exactly as its words write it, with its quantity read from them - every number as the "
          "page writes it, in digits, the unit it stands against and that unit as written - so that every number you give is in the "
          "words; give the death of the giver only where the papers record one.",
    fields=": date; kind; subject; figure; quantity; whole; whole_quantity; from; to; instrument; giver_died; words", outcome="")
SETTLE_TRANSFERS_SCHEMA = _settle_schema("transfer", TRANSACTION)


#: v13 (AN.28, D1, piece 3e): the papers read side by side for what matters to the client.
CONNECTIONS_V13 = """Message: You receive an advocate's messages to us about a client's matter and every paper they sent, page by page under each paper's name. A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. Square-bracket notes are the reader's, not the document's.

Purpose: Set the papers side by side and find what matters to the advocate's client only when two papers, or two parts of one, are read together, so that nothing that bears on the client is missed because it sits in another paper. You are not answering a legal question, and you are not judging which account is right.

Look for:
- Whom the advocate acts for, from their messages, and the client's people the papers name - members of the family, predecessors and successors in interest, partners, agents - each name exactly as a page writes it (client_people).
- Where the client or one of the client's people appears in another paper or in another proceeding than the one the advocate speaks of: as a party, an applicant or respondent, a witness, or a giver or receiver in a transaction.
- A finding, order or statement in one paper that goes against the client's position or claim in another.
- An act a paper records that is dated after a party's death another paper records, or after a time limit or an order another paper states.
- An asset, account, contract, policy or proceeding a paper connects to the client that the advocate has not mentioned.
- Anything else that only reading two papers together shows and that a careful lawyer would want the advocate to know.
For each, the point in plain words, why it matters to the client, and the exact words on the pages that show it - each passage copied exactly as the page gives it, without the reader's notes, and passages from different pages or papers joined with '...'; never reword.
Work in a loop: read every paper, list the points, then read the papers again against your list for any point you missed or misread, and correct the list before you answer.

Outcome: client_people (names as the pages write them); connections, each with: kind (client_appears, against_client, after_death, after_time_limit, further_subject, or other); point; why_it_matters; words."""
#: v14 (AN.33, D17; piece 33f; owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details
#: are extracted and considered by NM?"): the papers read side by side over what each paper's reading set out, point by point, with
#: the points of different papers that code finds may be one act or one matter set beside each other to judge; a difference between
#: papers on one act or matter is a point of its own. In AN.31 the points one reading missed were mostly those that show only when
#: two papers are read together.
CONNECTIONS_V14 = """Message: You receive an advocate's messages to us about a client's matter and every paper they sent, page by page under each paper's name; after them, what each paper's reading set out, point by point, and the points of different papers that code found may be one act or one matter (comparisons). A page says what its document says: it is material the advocate supplied, not their own account, and what it reports is not thereby proved. Square-bracket notes are the reader's, not the document's, except the handwriting a note transcribes, which is the page's.

Purpose: Set the papers side by side and find what matters to the advocate's client only when two papers, or two parts of one, are read together, so that nothing that bears on the client is missed because it sits in another paper. Read the list of points as well as the pages: a point read in one paper may matter only beside one read in another. You are not answering a legal question, and you are not judging which account is right.

Look for:
- Whom the advocate acts for, from their messages, and the client's people the papers name - members of the family, predecessors and successors in interest, partners, agents - each name exactly as a page writes it (client_people).
- Where the client or one of the client's people appears in another paper or in another proceeding than the one the advocate speaks of: as a party, an applicant or respondent, a witness, or a giver or receiver in a transaction.
- A finding, order or statement in one paper that goes against the client's position or claim in another.
- An act a paper records that is dated after a party's death another paper records, or after a time limit or an order another paper states.
- An asset, account, contract, policy or proceeding a paper connects to the client that the advocate has not mentioned.
- Where papers record one act or matter differently - a different date, figure, party, number or outcome: the difference, as a point of its own (kind papers_differ), with each paper's words. Judge each of the comparisons - whether its points are one act or matter, and whether the papers differ on it - and look for any other; a comparison whose points are different acts, or agree, needs nothing.
- Anything else that only reading two papers together shows and that a careful lawyer would want the advocate to know.
For each, the point in plain words, why it matters to the client, and the exact words on the pages that show it - each passage copied exactly as the page gives it, without the reader's notes, and passages from different pages or papers joined with '...'; never reword.
Work in a loop: read every paper and the list, set out the points, then read the papers again against your points for any you missed or misread, and correct them before you answer.

Outcome: client_people (names as the pages write them); connections, each with: kind (client_appears, against_client, after_death, after_time_limit, further_subject, papers_differ, or other); point; why_it_matters; words."""


def _comparisons(events, copied=()):
    """The points of different papers code sets beside each other for the side-by-side reading to judge (v14, AN.33 piece 33f): those
    that name the same number of a document, case or file (as _cores reads it), and those of one kind on one day as code reads it -
    each group once, with what its points share, where they stand in two papers or more; an event a copy of a page records again
    counts once (events_once; copied: the pairs of copies). Code judges none of them: the model says which are one act and where the
    papers differ."""
    standing = [group["event"] for group in events_once(events, copied)]
    order = {event["id"]: position for position, event in enumerate(standing)}
    groups, seen = [], set()

    def add(members, because):
        points = tuple(sorted({event["id"] for event in members}, key=order.get))
        if len({event["source"] for event in members}) >= 2 and points not in seen:
            seen.add(points)
            groups.append({"points": list(points), "because": because})

    named = {}
    for event in standing:
        for core in sorted(_cores(event["words"]) | _cores(event["what"])):
            named.setdefault(core, []).append(event)
    for core, members in named.items():
        add(members, f"each names {core}")
    days = {}
    for event in standing:
        if event.get("sort"):
            days.setdefault((event["sort"], event["kind"]), []).append(event)
    for (day, kind), members in days.items():
        add(members, f"each is a point of kind {kind} of {day}")
    return groups


def _record_text(events, comparisons):
    """What the side-by-side reading is shown after the papers from research v14 (piece 33f): each point the papers' reading set out,
    by its ID, and code's comparisons."""
    lines = ["", "What each paper's reading set out, point by point (id, paper, date, kind, what, said_by):"]
    lines += [json.dumps({"id": event["id"], "paper": event["document"], "date": event["date"], "kind": event["kind"],
                          "what": event["what"], "said_by": event["said_by"]}, ensure_ascii=False) for event in events] or ["(none)"]
    lines += ["", "Points of different papers that code found may be one act or one matter (comparisons):"]
    lines += [json.dumps(group, ensure_ascii=False) for group in comparisons] or ["(none)"]
    return "\n".join(lines)


#: v14: the points read side by side settled (AN.33, D18 and D22), the papers together.
SETTLE_POINTS = SETTLE.format(
    listed="set the papers an advocate sent side by side and listed the points that matter to the client", noun="point",
    key="connection",
    where="the pages of the papers (a point's passages may stand in different papers)", checks="", focus="", extra="",
    fields=": kind; point; why_it_matters; words", outcome="")
SETTLE_POINTS_SCHEMA = _settle_schema("connection", CONNECTION_V14)
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
    lines = ["The advocate's messages, oldest first:", *(f"- {row['text']}" for row in advocate_messages(context)), "",
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


def _placed_across(words, finder):
    """Where a point's words stand, by the tolerant finder over every paper (v14): (anchored, the places, each once in the order
    found, the words to keep - the pages' own, as _placed keeps them)."""
    pieces = fact_pieces(words)
    found = [finder.located(piece) for piece in pieces]
    if not pieces or not all(found):
        return False, [], words
    places = []
    for held, _ in found:
        for page in held:
            place = {"document": page["name"], "source": page["document"], "page": page["page"]}
            if place not in places:
                places.append(place)
    own = [text for _, text in found]
    return True, places, " ... ".join(own) if all(text is not None for text in own) else words


def _connections_in(data, finder):
    """The points one answer of the side-by-side reading gives (v14): placed over every paper by the tolerant finder and kept in the
    pages' own words, with the words as quoted beside them where they differ."""
    out = []
    for item in data["connections"]:
        given = item["words"].strip()
        anchored, places, words = _placed_across(given, finder)
        out.append({"kind": item["kind"], "point": item["point"].strip(), "why_it_matters": item["why_it_matters"].strip(),
                    "words": words, "anchored": anchored, "places": places, "quoted": "" if words == given else given,
                    "settled": "", "settled_why": ""})
    return out


def _appearances(names, documents):
    """Where each of the client's people stands on the papers' pages, found by code (v13, AN.28 piece 3e): the name as a run of
    words, letter case and punctuation aside; and, for a name of two words or more, runs of as many words that read nearly as the
    name (NEAR_NAME of their letters alike) - candidates only, never taken to be the name, NEAR_MOST at most."""
    pages = [(document, page, _NAME_WORD.findall(page["text"])) for document in documents for page in document["pages"]]
    listed = [[word.casefold() for word in _NAME_WORD.findall(name)] for name in names]

    def holds_a_listed_name(run):
        return any(run[start:start + len(other)] == other for other in listed if other
                   for start in range(len(run) - len(other) + 1))
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
                elif len(wanted) > 1 and len(near) < NEAR_MOST and not holds_a_listed_name(run):
                    alike = difflib.SequenceMatcher(None, " ".join(run), joined)
                    if alike.real_quick_ratio() >= NEAR_NAME and alike.quick_ratio() >= NEAR_NAME and alike.ratio() >= NEAR_NAME:
                        near.append({"as_written": " ".join(words[start:start + len(wanted)]), **place})
        out.append({"name": name, "places": places, "near": near})
    return out


def connections_of(model, context, *, wanted=None, withdrawn=None, events=()):
    """What matters to the client only when the papers are read side by side, as (connections, client_people, appearances,
    failures) - research v13 (plan AN.28, D1-D3, piece 3e). One call reads every paper with the advocate's messages, within
    WHOLE_FILE_TOKENS; above that the papers are not read together and a failure says so. From v14 (piece 33f) it is shown after
    the papers what each paper's reading set out (events: the chronology, numbered) and the points of different papers code finds
    may be one act or one matter (_comparisons), and a difference between papers on one act is a point of its own. Code finds each
    point's words on the pages with the tolerant finder (v14), and one call settles the points whose words it cannot find, shown
    code's evidence; code places what it gives again; a point still not found is kept, marked so; one the model finds the papers
    do not show goes to withdrawn (a list), with why. Code finds where each of the client's people the model names stands on the
    pages (_appearances). wanted: asked once, before any call; False and nothing is read."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], [], [], []
    if not _whole_file(context, documents):
        return [], [], [], [{"document": ALL_PAPERS, "pages": "all", "reason": "TooLongToReadTogether"}]
    finder = Pages(_all_pages(documents), TOLERANT_FINDER)
    from nm.core_engine import copy_figures  # it reads research's own finder; imported here, where it is used
    copied = copy_figures.copies([{"document": document["name"], "key": document["source"], "page": page["page"],
                                   "id": f'{document["source"]}p{page["page"]}', "text": page["text"]}
                                  for document in documents for page in document["pages"]])
    user = _papers_text(context, documents) + "\n" + _record_text(events, _comparisons(events, copied))
    try:
        data = _call(model, "core_research_connections", CONNECTIONS_V14, user, CONNECTIONS_SCHEMA_V14, "connections")
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        return [], [], [], [{"document": ALL_PAPERS, "pages": "all", "reason": type(exc).__name__}]
    found = _connections_in(data, finder)
    failing = [item for item in found if not item["anchored"]]
    if failing:
        to_check = [_to_check(index, {key: item[key] for key in CONNECTION["properties"]},
                              _NOT_FOUND.format(where="the pages of the papers"), item["words"], finder)
                    for index, item in enumerate(failing)]
        kept = [item for item in found if item["anchored"]]
        try:
            again = _call(model, "core_research_connections", SETTLE_POINTS,
                          user + "\n\n" + json.dumps({"to_check": to_check}, ensure_ascii=False), SETTLE_POINTS_SCHEMA,
                          "connections_check")
            require_schema(again, SETTLE_POINTS_SCHEMA)
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation):
            found = kept + [{**item, "settled": "unavailable"} for item in failing]
        else:
            settled, gone = _settled(again["settled"], failing, "connection",
                                     lambda given: _connections_in({"connections": [given]}, finder)[0], ALL_PAPERS,
                                     lambda item: item["point"])
            found = kept + settled
            if withdrawn is not None:
                withdrawn.extend(gone)
    # Each of the client's people once, letter case and spacing aside, as the papers first write the name.
    people = {}
    for name in data["client_people"]:
        if name.strip():
            people.setdefault(" ".join(name.split()).casefold(), " ".join(name.split()))
    people = list(people.values())
    return ([{"id": f"C{number}", **item} for number, item in enumerate(found, 1)], people, _appearances(people, documents), [])


def _connection_issues(data, context, version=EXACT_FINDER):
    """What a v13 plan records of the papers read side by side, checked against the turn's documents (piece 3e): the points numbered
    C1... in order, each anchored and placed as the one finder finds its words - with the finder the record was made under
    (version) - and the client's appearances as code finds their names; anything else raises SchemaViolation. A failure of the step
    is an issue: the papers were not read together."""
    documents = _documents(context)
    finder = Pages(_all_pages(documents), version)
    for number, item in enumerate(data["connections"], 1):
        if item["id"] != f"C{number}":
            raise SchemaViolation(f"Connection {number} is numbered {item['id']}, not C{number}")
        placed = (_placed_across(item["quoted"] or item["words"], finder) if version == TOLERANT_FINDER else None)
        if (placed is not None and (item["anchored"], item["places"], item["words"]) != placed) or (
                placed is None and (item["anchored"], item["places"]) != _anchor_across(item["words"], finder)):
            raise SchemaViolation(f"Connection {item['id']} is not anchored as its words are found in the papers")
    if data.get("appearances", []) != _appearances(data.get("client_people", []), documents):
        raise SchemaViolation("The client's people are not where code finds their names on the pages")
    for failure in data.get("connections_failures", []):
        if failure["document"] != ALL_PAPERS:
            raise SchemaViolation("A failure of the papers read together names one paper")
    return [{"work_id": None, "mismatch": f"the papers read together unavailable: {failure['reason']}", "proposal": deepcopy(failure)}
            for failure in data.get("connections_failures", [])]


def _file_numbers(documents):
    """Every number the pages of the whole file hold (as _numbers reads them): what a date given from another paper is traced to."""
    held = set()
    for document in documents:
        for page in document["pages"]:
            held |= _numbers(_reading(page["text"]))
    return held


def _died_ok(died, file_numbers):
    """Whether the death a transaction records for its giver stands in the file: a date code reads, every number of which is on some
    page of some paper (a death is often recorded in another paper than the transaction)."""
    return bool(read_date(died, months=True)) and {n for n in _numbers(died) if n} <= file_numbers


def _transfer_fault(transfer, file_numbers):
    """Why code cannot use a transaction as the model listed it, or None (v14): its words not on its paper's pages, its figure or
    whole as figures.fault finds them, the death it records for the giver on no page of the file, or the numbers of its date found
    nowhere in the papers (date_found, set first)."""
    if not transfer["anchored"]:
        return _NOT_FOUND.format(where="the pages of its paper")
    if why := figures.fault(transfer):
        return why
    if transfer["giver_died"] and not _died_ok(transfer["giver_died"], file_numbers):
        return "the death it records for the giver stands on no page of the papers"
    return _NO_DATE if transfer["date_found"] == "nowhere" else None


def _died(transfer, file_numbers):
    """The death a transaction records for its giver, as code may use it (v14): kept as the papers' reading whatever is found, its
    date read for use only where it stands in the file - a death found nowhere is listed, never used to judge what came after it."""
    transfer["giver_died_found"] = bool(transfer["giver_died"]) and _died_ok(transfer["giver_died"], file_numbers)
    transfer["giver_died_sort"] = read_date(transfer["giver_died"], months=True) if transfer["giver_died_found"] else ""
    return transfer


def _checked_transfers(model, context, transfers, documents, finders, whole=True, withdrawn=None):
    """v14 (AN.33, D18 and D22): each paper's transactions checked by code as its events are (_checked), and for a paper where some
    cannot be used as listed, one call that settles them, shown code's evidence; code places what it gives again. One still at fault
    is kept as the model last gave it - the ledger lists it and never adds it; no date is erased; a giver's death not found in the
    papers is kept, never used. One the model finds the papers do not record goes to withdrawn, with why."""
    file_numbers = _file_numbers(documents)

    def one(document):
        mine = [transfer for transfer in transfers if transfer["source"] == document["source"]]
        finder, paper = finders[document["source"]], _paper_numbers(document["pages"])
        for transfer in mine:
            transfer["date_found"] = _date_found(transfer, paper, file_numbers)
        failing = [(transfer, why) for transfer in mine if (why := _transfer_fault(transfer, file_numbers))]
        if not failing:
            return [_died(transfer, file_numbers) for transfer in mine], []
        to_check = [_to_check(index, {key: transfer[key] for key in TRANSACTION["properties"]}, why, transfer["words"], finder)
                    for index, (transfer, why) in enumerate(failing)]
        user, opening = _settle_text(context, documents, document, whole, {"to_check": to_check})
        kept = [transfer for transfer in mine if all(transfer is not wrong for wrong, _ in failing)]
        try:
            data = _call(model, "core_research_transfers", SETTLE_TRANSFERS, user, SETTLE_TRANSFERS_SCHEMA, "transfers_check",
                         marks=(opening,) if whole else ())
            require_schema(data, SETTLE_TRANSFERS_SCHEMA)
        except UsageLimitReached:
            raise
        except (ModelError, SchemaViolation):
            return [_died(transfer, file_numbers) for transfer in kept + [{**wrong, "settled": "unavailable"} for wrong, _ in failing]], []
        settled, gone = _settled(data["settled"], [wrong for wrong, _ in failing], "transfer",
                                 lambda given: _transfers_in({"transfers": [given]}, document, finder)[0], document["name"],
                                 lambda transfer: f"{transfer['kind']} of {transfer['figure'] or 'no stated figure'} ({transfer['subject']})")
        for transfer in settled:
            transfer["date_found"] = _date_found(transfer, paper, file_numbers)
        return [_died(transfer, file_numbers) for transfer in kept + settled], gone
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(documents)))) as pool:
        done = list(pool.map(one, documents))
    if withdrawn is not None:
        withdrawn.extend(item for _, gone in done for item in gone)
    return [transfer for mine, _ in done for transfer in mine]


def transfers_of(model, context, *, wanted=None, withdrawn=None):
    """The transactions the documents of a turn record, as (transfers, failures) - plan AN.27, P13d; from research v13 of any kind
    (AN.28, D7). Read, anchored, dated, ordered and numbered X1... exactly as the chronology's events are, each paper read with the
    whole file in view and settled where code cannot use what it found (v14); the figures are checked and added by figures.py,
    never here. withdrawn: a list that receives the transactions a settling call found the papers do not record."""
    documents = _documents(context)
    if not documents or (wanted is not None and not wanted()):
        return [], []
    whole = _whole_file(context, documents)
    transfers, failures = _read_stretches(model, context, None, "core_research_transfers", TRANSACTIONS_V13, TRANSACTIONS_SCHEMA,
                                          "transfers", _transfers_in, whole=whole)
    transfers = _checked_transfers(model, context, transfers, documents, {
        document["source"]: Pages(document["pages"], TOLERANT_FINDER) for document in documents}, whole, withdrawn)
    return _numbered_by_date(transfers, "X", months=True), failures


def _stretch_issues(items, failures, context, *, prefix, label, noun, unavailable, months=False, version=EXACT_FINDER):
    """What a v12 plan records of one kind that the papers were read for, checked against the documents of the turn (plan AN.27,
    P8c and P13d), and the issues it raises. It must be what the reading makes of those papers: the items numbered prefix1... in
    the order of their dates, the undated last, each of a document the turn holds, its date read as read_date reads it, and its
    words found on the pages recorded - or on none, and marked not anchored - as the one finder finds them in that document, with
    the finder the record was made under (version); from v14 (the tolerant finder) also where code finds the numbers of its date;
    anything else raises SchemaViolation. A stretch that could not be read is an issue, since part of a paper was not read; an item
    whose words are not found is marked not anchored and is not an issue."""
    documents = {document["source"]: document for document in _documents(context)}
    finders = {source: Pages(document["pages"], version) for source, document in documents.items()}
    numbers = ({source: _paper_numbers(document["pages"]) for source, document in documents.items()}
               if version == TOLERANT_FINDER else {})
    file_numbers = _file_numbers(documents.values()) if version == TOLERANT_FINDER else set()
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
        if version == TOLERANT_FINDER:
            # v14 (AN.33, D18): placed as it was made - from the words the model gave, by the tolerant finder - and so checked; the
            # page's own words found again could split at the page's own dots (a form's leader, an ellipsis) and stand elsewhere too.
            if (item["anchored"], item["pages"], item["words"]) != _placed(item["quoted"] or item["words"], finders[item["source"]]):
                raise SchemaViolation(f"{label} {name} is not anchored as its words are found in its document")
        elif (item["anchored"], item["pages"]) != _anchor(item["words"], finders[item["source"]]):
            raise SchemaViolation(f"{label} {name} is not anchored as its words are found in its document")
        if version == TOLERANT_FINDER and item["date_found"] != _date_found(item, numbers[item["source"]], file_numbers):
            raise SchemaViolation(f"{label} {name} says otherwise than code finds where its date stands")
    names = {document["name"] for document in documents.values()}
    for failure in failures:
        if failure["document"] not in names:
            raise SchemaViolation(f"A {noun} failure names no document of this turn")
    return [{"work_id": None, "mismatch": f"{unavailable} unavailable for {failure['document']} (pages {failure['pages']}): "
                                          f"{failure['reason']}", "proposal": deepcopy(failure)} for failure in failures]


def _chronology_issues(events, failures, context, months=False, version=EXACT_FINDER):
    return _stretch_issues(events, failures, context, prefix="E", label="Chronology event", noun="chronology",
                           unavailable="chronology", months=months, version=version)


def _transfer_issues(transfers, failures, context, months=False, version=EXACT_FINDER):
    file_numbers = _file_numbers(_documents(context)) if version == TOLERANT_FINDER else set()
    for item in transfers:
        found = item.get("giver_died_found", bool(item["giver_died"]))
        if version == TOLERANT_FINDER and found != (bool(item["giver_died"]) and _died_ok(item["giver_died"], file_numbers)):
            raise SchemaViolation(f"Transfer {item['id']} says otherwise than code finds of its giver's recorded death")
        if "giver_died_sort" in item and item["giver_died_sort"] != (read_date(item["giver_died"], months=months)
                                                                    if item["giver_died"] and found else ""):
            raise SchemaViolation(f"Transfer {item['id']} is dated otherwise than its giver's recorded death reads")
    return _stretch_issues(transfers, failures, context, prefix="X", label="Transfer", noun="transfer", unavailable="transfers",
                           months=months, version=version)


def _second_pass_issues(passes, events, context):
    """What a v14 plan lists of its second passes (piece 33g), checked against the plan: each names a paper of the turn, says why it
    failed only where it added nothing, and no paper has more events marked second_pass than its passes added (settling may withdraw
    some, never add any as the second pass's)."""
    names = {document["name"] for document in _documents(context)}
    added = {}
    for item in passes:
        if item["document"] not in names or item["added"] < 0 or (item["reason"] and item["added"]):
            raise SchemaViolation("A second pass names no paper of this turn, or says otherwise than it did")
        added[item["document"]] = added.get(item["document"], 0) + item["added"]
    for event in events:
        if event.get("second_pass"):
            added[event["document"]] = added.get(event["document"], 0) - 1
            if added[event["document"]] < 0:
                raise SchemaViolation(f"Chronology event {event['id']} is marked as the second pass's, which added no more")
    return []


def _withdrawn_issues(withdrawn, context):
    """What a v14 plan lists as withdrawn, checked for what it may name: a paper of the turn, or the papers read together."""
    names = {document["name"] for document in _documents(context)} | {ALL_PAPERS}
    for item in withdrawn:
        if item["document"] not in names:
            raise SchemaViolation("A withdrawn item names no paper of this turn")
    return []


#: v14 (AN.33, D19; piece 33h; owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details are
#: extracted and considered by NM?"): the points read, weighed for the advice as a step of their own, after the papers are read and
#: the matter understood; and the weighing checked by a second call.
WEIGH = """Message: You receive an advocate's messages to us about a client's matter, our understanding of it - its disputes, each with the legal questions we will research - and every point the papers the advocate sent were read for, each by its ID: what each paper records (E1, E2...) and what shows only when the papers are read side by side (C1, C2...). A point says what its paper says: it is material the advocate supplied, not proved.

Purpose: Weigh the points for the advice, so that the answer is built on the ones that matter and none of those is missed. For each point that matters to a dispute, say which dispute it bears on, whether it helps the client, hurts the client or cuts both ways, why, and how much: critical - the advice would be wrong or incomplete without it - or material - it changes what the advocate should do or know. A point you do not name is background: it still stands in the table of what the papers record, shown with the answer. You are not answering the legal questions.

Look for:
- Each point that bears on a dispute's rights, relief, time limits, proof or procedure, and how.
- Points that matter only together - an act after a death, a finding in one paper against a claim in another: weigh each point that carries the matter, and say in why which other points it rests on.
- A critical point that none of its dispute's legal questions covers: give the legal question it raises (question), so that it is researched; or, where it is a matter of fact for the advocate to act on rather than of law, say so (for_advocate). Otherwise give no question.
Work in a loop: weigh the points, then read them again against the disputes for any you missed or weighed wrongly, and correct the weighing before you answer.

Outcome: weights, each with: id (the point's ID); dispute (its ID); effect (helps, hurts, both or unclear); weight (critical or material); why; question (or empty); for_advocate (true or false)."""
WEIGH_CHECK = """Message: You receive an advocate's messages to us about a client's matter, our understanding of it, every point the papers were read for, each by its ID, and how a colleague weighed the points for the advice (weights): for each point that matters to a dispute, its dispute, whether it helps or hurts the client, how much (critical or material) and why; a point not weighed is background.

Purpose: Check the weighing independently, so that no point that matters is left as background and none is weighed for more or less than it is worth. You are not answering the legal questions.

Look for: a point weighed wrongly - the wrong dispute, effect or weight, or a why the points do not bear out; a point left as background that is critical or material; a point weighed that is background; a critical point whose legal question no question of its dispute covers and the weighing gave none. For each point you would weigh otherwise, give it as you would weigh it (weight background takes it out of the weighing); give nothing for a point weighed as you would weigh it.
Work in a loop: read the weighing against the points and the disputes, decide, then read your corrections again before you answer.

Outcome: corrections, each with: id; dispute; effect; weight (critical, material or background); why; question (or empty); for_advocate."""


def _points_text(context, understanding, events, connections):
    """What the weighing is shown (v14, piece 33h): the advocate's messages, the understanding's disputes with their legal questions,
    and every point read by its ID - each event with its paper, date, kind, what, who says it and the page's words; each point read
    side by side with its kind, point and why it matters."""
    lines = ["The advocate's messages, oldest first:", *(f"- {row['text']}" for row in advocate_messages(context)), "",
             _matter_text(understanding, understanding["disputes"]), "", "The points the papers were read for:"]
    lines += [json.dumps({"id": event["id"], "paper": event["document"], "date": event["date"], "kind": event["kind"],
                          "what": event["what"], "said_by": event["said_by"], "words": event["words"]}, ensure_ascii=False)
              for event in events]
    lines += [json.dumps({"id": item["id"], "kind": item["kind"], "point": item["point"], "why_it_matters": item["why_it_matters"]},
                         ensure_ascii=False) for item in connections]
    return "\n".join(lines)


def _weighed(given, points, disputes, aside, source):
    """The entries of a weighing or its check that code can use (v14): each naming a point and a dispute of the plan, the first for a
    point counting; the rest set aside, with why (source: which call gave it)."""
    kept = {}
    for number, entry in enumerate(given, 1):
        if entry["id"] not in points or entry["dispute"] not in disputes:
            aside.append({"step": source, "reason": f"entry {number} names no point or no dispute of the plan"})
        elif entry["id"] not in kept:
            kept[entry["id"]] = {key: entry[key].strip() if isinstance(entry[key], str) else entry[key] for key in WEIGHT["properties"]}
    return kept


def weigh(model, context, understanding, events, connections):
    """The points read, weighed for the advice (v14, AN.33 D19, piece 33h): one call weighs every point that matters - its dispute,
    whether it helps or hurts the client, how much, why, and the legal question a critical point raises that no question covers, or
    that it is a matter for the advocate - and a second call checks the weighing and gives what it would weigh otherwise, which code
    applies (a point it gives as background leaves the weighing). Code keeps only entries that name a point and a dispute of the plan.
    Returns (weights, failures): each weight marked kept, changed or added by the check, or unchecked where the check failed; a failed
    weighing leaves every point unweighed - background - and says so. A usage limit still stops the turn."""
    points = {item["id"] for item in [*events, *connections]}
    disputes = {dispute["id"] for dispute in understanding["disputes"]}
    if not points or not disputes:
        return [], []
    user = _points_text(context, understanding, events, connections)
    failures = []
    try:
        data = _call(model, "core_research_weigh", WEIGH, user, WEIGH_SCHEMA, "weigh")
        require_schema(data, WEIGH_SCHEMA)
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        return [], [{"step": "weigh", "reason": type(exc).__name__}]
    weights = _weighed(data["weights"], points, disputes, failures, "weigh")
    shown = json.dumps({"weights": list(weights.values())}, ensure_ascii=False)
    try:
        again = _call(model, "core_research_weigh_check", WEIGH_CHECK, user + "\n\n" + shown, WEIGH_CHECK_SCHEMA, "weigh_check")
        require_schema(again, WEIGH_CHECK_SCHEMA)
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        failures.append({"step": "weigh_check", "reason": type(exc).__name__})
        return [{**entry, "checked": "unchecked", "question_id": ""} for entry in weights.values()], failures
    corrected = _weighed(again["corrections"], points, disputes, failures, "weigh_check")
    out = {}
    for identity, entry in weights.items():
        if identity not in corrected:
            out[identity] = {**entry, "checked": "kept", "question_id": ""}
    for identity, entry in corrected.items():
        if entry["weight"] != "background":
            out[identity] = {**entry, "checked": "changed" if identity in weights else "added", "question_id": ""}
    order = {item["id"]: position for position, item in enumerate([*events, *connections])}
    return sorted(out.values(), key=lambda entry: order[entry["id"]]), failures


def _raise_questions(model, proposed, weights, report):
    """The legal questions critical points raise that no question of their dispute covers (v14, AN.33 D19, piece 33h): each joins its
    dispute, numbered after that dispute's own (D1Q4...), with the point's why as why it is needed, and is given search phrases as the
    others are, so that it is researched in the held law. One that is a matter of fact for the advocate raises none. Returns the
    proposal with them and the weights, each naming the question its point raised. A phrase step that fails is a failure the plan
    records, and its question is then researched by none - an issue, as for any question."""
    raised = {entry["id"] for entry in weights if entry["weight"] == "critical" and entry["question"] and not entry["for_advocate"]}
    if not raised or not proposed["understanding"]["needs_research"]:
        return proposed, weights
    understanding = deepcopy(proposed["understanding"])
    disputes = {dispute["id"]: dispute for dispute in understanding["disputes"]}
    taken = {question["id"] for dispute in understanding["disputes"] for question in dispute["legal_questions"]}
    added, out = set(), []
    for entry in weights:
        if entry["id"] not in raised:
            out.append(entry)
            continue
        dispute = disputes[entry["dispute"]]
        numbers = [int(match.group(1)) for question in dispute["legal_questions"]
                   if (match := re.fullmatch(re.escape(dispute["id"]) + r"Q(\d+)", question["id"]))]
        number = max(numbers, default=len(dispute["legal_questions"])) + 1
        while f"{dispute['id']}Q{number}" in taken:
            number += 1
        identity = f"{dispute['id']}Q{number}"
        taken.add(identity)
        added.add(identity)
        dispute["legal_questions"].append({"id": identity, "question": entry["question"], "why_needed": entry["why"],
                                           "open_alternative": "", "law_to_check": []})
        out.append({**entry, "question_id": identity})
    fresh = {**understanding, "disputes": [{**dispute, "legal_questions": [question for question in dispute["legal_questions"]
                                                                            if question["id"] in added]}
                                           for dispute in understanding["disputes"]]}
    statute, judgment, missed = _phrases(model, fresh, report)
    return ({**proposed, "understanding": understanding, "statute_phrases": [*proposed["statute_phrases"], *statute],
             "judgment_phrases": [*proposed["judgment_phrases"], *judgment], "failures": [*proposed["failures"], *missed]}, out)


def _weight_issues(data):
    """What a v14 plan keeps of its weighing, checked against the plan (piece 33h): each weight names a point and a dispute of the
    plan, once; a failure of the weighing is an issue the plan says - its points were not weighed."""
    points = {item["id"] for item in [*data.get("chronology", ()), *data.get("connections", ())]}
    disputes = {dispute["id"] for dispute in data["understanding"]["disputes"]}
    seen = set()
    for entry in data.get("weights", ()):
        if entry["id"] not in points or entry["dispute"] not in disputes or entry["id"] in seen:
            raise SchemaViolation(f"Weight for {entry['id']} names no point or dispute of the plan, or weighs it twice")
        if entry["question_id"] and entry["question_id"] not in {question["id"] for dispute in data["understanding"]["disputes"]
                                                                 if dispute["id"] == entry["dispute"]
                                                                 for question in dispute["legal_questions"]}:
            raise SchemaViolation(f"Weight for {entry['id']} names a question its dispute does not hold")
        seen.add(entry["id"])
    return [{"work_id": None, "mismatch": f"the weighing of the points unavailable: {failure['step']} {failure['reason']}",
             "proposal": deepcopy(failure)} for failure in data.get("weighing_failures", ()) if failure["step"] == "weigh"]


def plan(model, context, interpretation=None, *, progress=None, wanted=None, restrictions=None, early=None):
    """The v7 reasoning loop. Expected model failures after the first understanding are
    recorded where they occur; independent work continues. The loop reads the
    conversation itself; the interpretation only spares it for a message that carries
    no information or request. wanted: asked before each step after the first, when the
    loop runs beside the interpretation (18 Oct 2026); it may wait for the interpretation,
    and once it answers False the loop stops there with the plan for no matter. restrictions: asked once, after wanted has
    let the loop go on, what the advocate restricted in their latest message as the interpretation found it (a list of their
    exact words) or None where that is not known; the check and the correction are told (plan AN.27, P4).
    The chronology of the documents, and the transactions they record (P13d), are read beside the loop (research v12, plan
    AN.27, P8c): each is started at once, asks wanted before any call, and its result is taken last; a stretch that could not be
    read is recorded, and a usage limit stops the turn."""
    if interpretation is not None and not carries_matter(interpretation):
        return _no_matter(context)
    still = wanted or (lambda: True)
    # v14 (AN.33, D18): what settling a failed check finds the papers do not record, from each reading, listed with why.
    withdrawn = {"events": [], "transfers": [], "points": []}
    # v14 (AN.33, piece 33g): each second pass over a stretch of a paper, with what it added.
    passes = []
    with ThreadPoolExecutor(max_workers=3) as reading:
        papers = reading.submit(chronology_of, model, context, wanted=still, withdrawn=withdrawn["events"], passes=passes)
        moved = reading.submit(transfers_of, model, context, wanted=still, withdrawn=withdrawn["transfers"])
        # v13 (AN.28, piece 3e): the papers read side by side, beside the rest; from v14 (AN.33, piece 33f) over what each paper's
        # reading set out, once that reading is made.
        linked = reading.submit(lambda: connections_of(model, context, wanted=still, withdrawn=withdrawn["points"],
                                                       events=papers.result()[0]))
        proposed = _proposal(model, context, still, progress, restrictions)
        if proposed is None:
            return _no_matter(context)
        if early is not None and still():
            # v14 (AN.33, D28; piece 33q): the research work the understanding and its search phrases give, for its search to start
            # now, beside the side-by-side reading and the weighing. A proposal the plan's check refuses starts none.
            try:
                early(accept({**proposed, "chronology": [], "chronology_failures": []}, context)["work"])
            except SchemaViolation:
                pass
        events, unread = papers.result()
        transfers, unmoved = moved.result()
        connections, people, appearances, unlinked = linked.result()
    # v14 (AN.33, D19; piece 33h): the points read, weighed for the advice, and the weighing checked.
    weights, weighing = weigh(model, context, proposed["understanding"], events, connections) if still() else ([], [])
    if weights and still():
        proposed, weights = _raise_questions(model, proposed, weights, progress or (lambda stage, **detail: None))
    return accept({**proposed, "chronology": events, "chronology_failures": unread,
                   "transfers": transfers, "transfers_failures": unmoved,
                   "connections": connections, "connections_failures": unlinked, "client_people": people,
                   "appearances": appearances, "withdrawn": [*withdrawn["events"], *withdrawn["transfers"], *withdrawn["points"]],
                   "chronology_second_pass": passes, "weights": weights, "weighing_failures": weighing},
                  context)


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
                # The check of a revision looks again at what the first check found (plan AN.30).
                review = _call(model, "core_research_check", CHECK, text + note + "\n\nYour colleague's understanding:\n"
                               + json.dumps(understanding, ensure_ascii=False, indent=1), CHECKED, "check", again=number > 0)
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
        if (not understanding["needs_research"] and not understanding["ruled_out"]
                and any(dispute["legal_questions"] for dispute in understanding["disputes"])):
            # The owner's standing purpose (the check is told it): every matter is researched for where the law stands on each
            # dispute unless the advocate rules it out. An understanding that lists legal questions, with nothing ruled out, is
            # researched even where its last revision said none was needed (the second paid replay of 31 Oct 2026).
            understanding = {**understanding, "needs_research": True, "no_research_reason": ""}
            if phrasing is not None:
                phrasing.result()
                phrasing = None
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
    # v14 (AN.33, D18): a record is checked with the finder it was made under.
    version = TOLERANT_FINDER if contract in SETTLED else EXACT_FINDER
    if "chronology" in data:
        issues.extend(_chronology_issues(data["chronology"], data["chronology_failures"], context, months, version))
    if "transfers" in data:
        issues.extend(_transfer_issues(data["transfers"], data.get("transfers_failures", []), context, months, version))
    if "connections" in data:
        issues.extend(_connection_issues(data, context, version))
    if "withdrawn" in data:
        issues.extend(_withdrawn_issues(data["withdrawn"], context))
    if "chronology_second_pass" in data:
        issues.extend(_second_pass_issues(data["chronology_second_pass"], data.get("chronology", []), context))
    if "weights" in data:
        issues.extend(_weight_issues(data))
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
            # v15 (plan AN.35, piece 35b): the sections to read first, each once, as the phrases step named them - a reference naming
            # several provisions read as each it names (provision_references), one naming none kept as it was said.
            named = {(" ".join(item["act"].split()), reference): None
                     for item in statute.get(question_id, {}).get("sections", []) if item["act"].strip() and item["section"].strip()
                     for reference in (provision_references(item["section"]) or (" ".join(item["section"].split()),))}
            work.append({"id": identity, "sources": [deepcopy(latest)], "search_account": [],
                         "dispute": {"id": dispute["id"], "name": dispute["name"], "between": list(dispute["between"])},
                         "question_id": question_id, "question": question["question"],
                         "why_needed": question["why_needed"], "law_to_check": list(question["law_to_check"]),
                         "instruments": acts,
                         **({"named": [{"act": act, "section": section} for act, section in named]}
                            if contract in NAMED_LAW and named else {}),
                         "enquiries": [{"text": p["text"].strip(), "purpose": p["kind"], "basis": "conditional",
                                        "query_id": f"{identity}:q{i}"} for i, p in enumerate(texts, 1)]})
    return {"proposal": data, "work": work, "issues": issues, "semantic_review": "pending"}


def accept(proposal, context, *, contract=CONTRACT):
    """A research plan's proposal admitted against the conversation it was made from. Once within a turn or a replay (plan AN.41,
    step 1; P35): each dispute's research, and the research continuing where it stopped, is checked against the same plan, and
    admitting it again for each found nothing new - about 5 s a dispute on the 4 Nov 2026 matter."""
    return once(("plan", id(proposal), id(context), contract), (proposal, context),
                lambda: _accept(proposal, context, contract=contract))


def _accept(proposal, context, *, contract=CONTRACT):
    if contract not in CONTRACTS:
        raise ValueError("Unknown research contract")
    if contract in _QUESTION_PLANS:
        return _accept_v7(proposal, context, SCHEMA_V15 if contract in NAMED_LAW else SCHEMA_V14 if contract in SETTLED
                          else SCHEMA_V13 if contract in WHOLE_FILE
                          else SCHEMA_V12 if contract in CHRONICLED
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


def search_named(work, *, contract=CONTRACT):
    """The sections a v15 work item names to read first, each {"act", "section"} (plan AN.35, piece 35b); None where it names
    none, or before v15 - its search is then a search of v10's shape."""
    return [dict(item) for item in work["named"]] if contract in NAMED_LAW and work.get("named") else None


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
    the provisions connected to them (owner decision P32, 20 Oct 2026), and from search v11 the
    sections the plan named, read by their number (plan AN.35, piece 35b). A fallback keeps
    only what search returned."""
    return [*_of_kind(search, kind),
            *((*search.get("connected", ()), *search.get("named_found", ())) if kind == "provision" else ())]


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


def _pick_text(plan, searches, labels, meant=()):
    lines = [f"Matter: {plan['proposal']['understanding']['summary']}"]
    # Plan AN.37 (D87): which Act the advocate said a name means, by the name as written.
    means = {(item["act"], work_id): item for item in meant or () if item["meant"] for work_id in item["work_ids"]}
    for work in plan["work"]:
        if work["id"] not in searches:
            continue
        label, search = labels[work["id"]], searches[work["id"]]
        lines.append(f"\n{label}: {work['question']}")
        offered, returned = _offered(search, "provision"), len(_provisions(search))
        linked = returned + len(search.get("connected", ()))
        shown = {candidate["id"]: f"{label}.{number}" for number, candidate in enumerate(offered, 1)}
        said = _connections_said(search, shown)
        for number, candidate in enumerate(offered, 1):
            if number == returned + 1 and search.get("connected"):
                lines.append("  Read with them, as their Acts connect them:")
            if number == linked + 1:
                lines.append("  Named for this question, read by their number:")
            source = candidate["source"]
            heading = re.sub(r"\s+", " ", source.get("section_title") or "")[:140]
            # P21 (19 Oct 2026): an Act India Code does not list as in force is said so.
            mark = f" [{in_force(source)}]" if in_force(source) else ""
            line = f"  {label}.{number} {candidate['title']}, section {candidate['locator']}{mark}: {heading}."
            if number <= returned or number > linked:  # what search returned, and a section named for the question
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
        # v15 (plan AN.35, piece 35b): what became of each section the plan named.
        for entry in search.get("named", ()):
            places = ", ".join(shown[identity] for identity in entry["found"] if identity in shown)
            said_of = {"read": f"read as {places}", "ambiguous": f"may be {places}" if places else "held more than once, not read",
                       "not_held": "not held in our library", "unavailable": "could not be read"}[entry["state"]]
            item = means.get((entry["act"], work["id"])) if entry["state"] == "ambiguous" else None
            if item is not None:
                kept = ", ".join(shown[identity] for identity in entry["found"] if identity in shown
                                 and _act_of(search, identity) == item["meant"])
                said_of = f"the advocate means {act_label(item['meant'], item['titles'][item['acts'].index(item['meant'])])}: read as {kept}"
            lines.append(f"  Named: {entry['act']}, {entry['section']} - {said_of}.")
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
            at = judgment_place(candidate["locator"])
            lines.append(f"  {label}.{number} {candidate['title']} ({where}){', ' + at if at else ''}: {words}")
    return "\n".join(lines)


#: Each pick's operation, prompt, output step and shown text.
PICKS = {"provision": ("core_research_pick", PICK_V18, "pick", _pick_text),
         "judgment": ("core_research_judgment_pick", JUDGMENT_PICK_V17, "judgment_pick", _judgment_pick_text)}
#: Each pick's answer shape as the current version asks for it (v17: the judgment pick names the judgments to read in full).
PICK_SCHEMAS = {"provision": CHOICE, "judgment": CHOICE_V17}


def _resolve_picks(choice, plan, searches, labels, kind="provision", room=None):
    """Only shown IDs count; the code owns the mapping from a shown ID to a candidate. room (v18, piece 36e): for provisions, how
    many each question may keep, in the order chosen."""
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
    if room is not None and kind == "provision":
        chosen = {work_id: ids[:max(0, room.get(work_id, SECTIONS_A_QUESTION))] for work_id, ids in chosen.items()}
    return chosen, unknown


def _fallback_picks(searches, labels, kind="provision", room=None):
    """When the pick is unavailable each question keeps the search's own first six - from v18 (piece 36e) no more provisions than
    the question's room."""
    def kept(work_id):
        return 6 if room is None or kind != "provision" else min(6, max(0, room.get(work_id, SECTIONS_A_QUESTION)))
    return {work_id: [c["id"] for c in _of_kind(searches[work_id], kind)[:kept(work_id)]] for work_id in labels}


def _labels(plan, searches):
    return {work["id"]: f"Q{number}" for number, work in
            enumerate((w for w in plan["work"] if w["id"] in searches), 1)}


def pick(model, plan, searches, kind="provision", room=None, meant=()):
    """meant (plan AN.37, D87): which Act the advocate said a name means - the pick is told, and keeps no reading of another Act
    for that name."""
    labels = _labels(plan, searches)
    if kind == "provision" and room is None:
        # v18 (piece 36e): each question keeps at most SECTIONS_A_QUESTION provisions.
        room = {work_id: SECTIONS_A_QUESTION for work_id in labels}
    if not any(_of_kind(searches[work_id], kind) for work_id in labels):
        return {"state": "not_needed", "proposal": None, "chosen": {w: [] for w in labels}, "unknown": [],
                "reason": None}
    operation, system, step, text = PICKS[kind]
    shown = text(plan, searches, labels, meant) if kind == "provision" and meant else text(plan, searches, labels)
    try:
        choice = _call(model, operation, system, shown, PICK_SCHEMAS[kind], step)
    except (ModelError, SchemaViolation) as exc:
        return {"state": "unavailable", "proposal": None,
                "chosen": _keep_meant(_fallback_picks(searches, labels, kind, room), searches, meant if kind == "provision" else ()),
                "unknown": [], "reason": type(exc).__name__}
    chosen, unknown = _resolve_picks(choice, plan, searches, labels, kind, room)
    return {"state": "evaluated", "proposal": choice, "chosen": _keep_meant(chosen, searches, meant if kind == "provision" else ()),
            "unknown": unknown, "reason": None}


# --- plan AN.37, D87: which Act or judgment a name means, asked of the advocate by code ---------------------------------------

#: The choice that leaves a name to NM's own judgement (the default), and the one that goes on without a judgment cited ambiguously.
NM_JUDGES = "Let NM judge from the papers"
WITHOUT_IT = "Go on without it"
#: How many held Acts or judgments a question offers by name; the rest are left to NM's judgement.
NAMED_CHOICES = 3
_JURISDICTION_PREFIX = re.compile(r"^(?:[A-Za-z]+(?: [A-Za-z]+)*?) \d{4} \d+ ")


def act_label(act_id, title):
    """A held Act as the advocate reads it: its title without the store's prefix, and where it is not a central Act, whose."""
    shown = _JURISDICTION_PREFIX.sub("", title or act_id or "").strip()
    whose = (act_id or "").split("_", 1)[0].title()
    return (shown if whose in ("", "Union Of India") else f"{shown} ({whose})")[:120]


def _act_of(search, identity):
    candidate = next((c for c in _offered(search, "provision") if c["id"] == identity), None)
    return (candidate or {}).get("source", {}).get("act_id")


def named_ambiguities(plan, searches):
    """The names a dispute's searched questions read as more than one held Act, once each (D87): {"act": the name as written,
    "work_ids", "acts": their ids in the order read, "titles"}. A number held twice in one Act is not one: the pick judges it."""
    found = {}
    for work in plan["work"]:
        search = searches.get(work["id"])
        for entry in (search or {}).get("named", ()):
            if entry["state"] != "ambiguous":
                continue
            acts = {}
            for identity in entry["found"]:
                candidate = next((c for c in _offered(search, "provision") if c["id"] == identity), None)
                if candidate is not None and candidate["source"].get("act_id"):
                    acts.setdefault(candidate["source"]["act_id"], candidate.get("title") or candidate["source"]["act_id"])
            if len(acts) < 2:
                continue
            item = found.setdefault((entry["act"], tuple(acts)), {"act": entry["act"], "work_ids": [], "acts": list(acts),
                                                                  "titles": list(acts.values())})
            if work["id"] not in item["work_ids"]:
                item["work_ids"].append(work["id"])
    return list(found.values())


def named_question(item, dispute):
    """What code asks of one name read as more than one held Act (D87): each Act a choice, NM's judgement the default."""
    choices = [{"label": act_label(act_id, title), "description": ""}
               for act_id, title in list(zip(item["acts"], item["titles"]))[:NAMED_CHOICES]]
    return {"header": "Which Act is meant", "question": f"Which Act do you mean by \"{item['act']}\"? We hold more than one by that name.",
            "why": f"The law read for {dispute.get('name') or 'this dispute'} turns on which Act it is.",
            "choices": [*choices, {"label": NM_JUDGES, "description": "NM reads each and goes by what your papers show."}],
            "multiple": False, "default": [NM_JUDGES], "depends": [dispute["id"]], "asked_by": "code"}


def cited_question(entry, disputes):
    """What code asks of a citation under which more than one judgment is held (D87): each judgment a choice; going on without
    it, as before, the default."""
    choices = [{"label": f"{held['title']} ({', '.join(str(v) for v in (held.get('court'), held.get('year')) if v)})"[:120],
                "description": ""} for held in entry["held"][:NAMED_CHOICES]]
    return {"header": "Which judgment is meant", "question": f"Your papers cite {entry['citation']}. We hold more than one judgment "
            "under that citation: which do you mean?", "why": "Only the judgment you mean is read for the answer.",
            "choices": [*choices, {"label": WITHOUT_IT, "description": "NM goes on without reading a judgment under this citation."}],
            "multiple": False, "default": [WITHOUT_IT], "depends": list(disputes), "asked_by": "code"}


def _chosen_index(question, answer):
    """Which offered choice an answer took, by its place among the choices; None for the default or the advocate's own words."""
    labels = [choice["label"] for choice in question["choices"][:-1]]
    chosen = (answer or {}).get("chosen") or []
    return labels.index(chosen[0]) if len(chosen) == 1 and chosen[0] in labels else None


def _keep_meant(chosen, searches, meant):
    """A pick's choice without the readings of a name's other Acts, where the advocate said which Act it means (D87)."""
    if not meant:
        return chosen
    kept = {work_id: list(ids) for work_id, ids in chosen.items()}
    for item in meant:
        if not item["meant"]:
            continue
        for work_id in item["work_ids"]:
            search = searches.get(work_id)
            if search is None or work_id not in kept:
                continue
            other = {identity for entry in search.get("named", ()) if entry["state"] == "ambiguous" and entry["act"] == item["act"]
                     for identity in entry["found"] if _act_of(search, identity) != item["meant"]}
            kept[work_id] = [identity for identity in kept[work_id] if identity not in other]
    return kept


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


def _part(plan, dispute_id, searches, failures, chosen, judgments, contract=CONTRACT, further=None, meant=None):
    """One dispute's part of a v10 or v11 record: its questions' searches and gaps, its own
    picks, (v11) the judgments it reads, (v16) its further search and (plan AN.37, D87) the names read as more than one held Act,
    each with the Act the advocate said it means (None: NM's judgement) - only where there were any."""
    ids = [w["id"] for w in dispute_work(plan)[dispute_id]]
    searches = {i: searches[i] for i in ids if i in searches}
    failures = {i: failures[i] for i in ids if i in failures}
    record = {"contract": contract, "plan": deepcopy(plan), "searches": deepcopy(searches),
              "failures": deepcopy(failures), "part": dispute_id,
              **{field: {dispute_id: deepcopy(chosen[kind])} for kind, field in _PICK_FIELDS.items()},
              **({"judgments": {dispute_id: deepcopy(judgments)}} if contract in JUDGMENTS_READ else {}),
              **({"further": {dispute_id: deepcopy(further)}} if contract in FURTHER_LAW else {}),
              **({"meant": {dispute_id: deepcopy(meant)}} if meant else {})}
    record["state"] = _state(plan, searches, failures, [chosen[kind] for kind in _PICK_FIELDS])
    return record


def _in_full(plan, searches, pick):
    """The judgments a v17 pick named to read in full, in the order named (piece 36a): each named by one of its shown paragraphs' IDs,
    only a judgment the pick chose a paragraph of, each once. A pick that could not be made names none."""
    labels = _labels(plan, searches)
    by_label = {label: work_id for work_id, label in labels.items()}
    chosen = set()
    for work_id, ids in pick["chosen"].items():
        offered = {c["id"]: c for c in _of_kind(searches.get(work_id) or {"candidates": []}, "judgment")}
        chosen |= {offered[identity]["source"].get("case_id") for identity in ids if identity in offered}
    named = []
    for shown in (pick.get("proposal") or {}).get("read_in_full") or ():
        label, _, number = str(shown).rpartition(".")
        work_id = by_label.get(label)
        offered = _of_kind(searches[work_id], "judgment") if work_id is not None else []
        if not number.isdigit() or not 1 <= int(number) <= len(offered):
            continue
        case_id = offered[int(number) - 1]["source"].get("case_id")
        if case_id and case_id in chosen and case_id not in named:
            named.append(case_id)
    return named


def _chosen_cases(plan, searches, pick, contract=CONTRACT, skip=frozenset(), limit=None):
    """The judgments a dispute's pick chose, in the order chosen - every one from v15 (piece 35a), at most JUDGMENTS_PER_DISPUTE
    before; with what search found of each and what the pick chose of each, by stored position. skip (v16): judgments the dispute
    already reads, read once."""
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
            if candidate is not None and candidate["source"].get("case_id") and candidate["source"]["case_id"] not in skip:
                order.append(candidate["source"]["case_id"])
                chosen.setdefault(candidate["source"]["case_id"], set()).add(candidate["position"])
    cases = list(dict.fromkeys(order))
    if contract in FEW_IN_FULL:
        # v17 (piece 36a): only those the pick named to read in full, at most IN_FULL a dispute (limit: what is left of them).
        cases = [case_id for case_id in _in_full(plan, searches, pick) if case_id in cases][:IN_FULL if limit is None else
                                                                                           max(0, limit)]
    elif contract not in EVERY_CHOSEN:
        cases = cases[:JUDGMENTS_PER_DISPUTE]
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
    # A paragraph cut into parts (plan AN.45) is several positions under one number: naming it names them all.
    numbered: dict[str, list[int]] = {}
    for position, row in paragraphs:
        numbered.setdefault(str(row.get("paragraph_num") or "").strip(), []).append(position)
    for position in list(why):
        for named in _PARAGRAPH_NAMED.finditer(rows[position]["full_text"]):
            first, last = int(named.group(1)), int(named.group(2) or named.group(1))
            for number in range(first, min(last, first + 10) + 1):
                for other in numbered.get(str(number), ()):
                    if other != position:
                        add(other, "named")
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


def _read_judgments(searcher, plan, searches, pick, skip=frozenset(), cases=None, limit=None):
    """The judgments a dispute's answer reads (P31): each chosen judgment whole, or as an
    extract of a long one; one that cannot be read is said, with why. skip (v16): those already read. cases (v16, piece 35e):
    the judgments to read, as (case ID, found, chosen), where they are not the pick's."""
    read = []
    for case_id, found, chosen in (_chosen_cases(plan, searches, pick, skip=skip, limit=limit) if cases is None else cases):
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


def _picked(model, plan, searches, report, room=None, meant=()):
    """A dispute's two picks, beside each other; without a model each keeps the first six. room (v18): how many provisions each
    question may still keep (the further pick's); every question SECTIONS_A_QUESTION where it is not given."""
    labels = _labels(plan, searches)
    room = {work_id: SECTIONS_A_QUESTION for work_id in labels} if room is None else room
    if model is None:
        return {kind: {"state": "unavailable", "proposal": None, "unknown": [], "reason": "No model for the pick",
                       "chosen": _keep_meant(_fallback_picks(searches, labels, kind, room), searches,
                                             meant if kind == "provision" else ())} for kind in _PICK_FIELDS}
    if searches:
        report("choosing_provisions")
    with ThreadPoolExecutor(max_workers=len(_PICK_FIELDS)) as pool:
        return dict(zip(_PICK_FIELDS, pool.map(lambda kind: pick(model, plan, searches, kind, room if kind == "provision" else None,
                                                                 meant if kind == "provision" else ()), _PICK_FIELDS)))


#: What each question's search returns of each kind for its picks (v15: as many judgment paragraphs as provisions).
FOR_PICK = {"provision": PROVISIONS_FOR_PICK, "judgment": JUDGMENTS_FOR_PICK}


def _search_key(work, queries, instruments, named=None):
    """What makes two searches one (v14, piece 33q): the research work they are made for and exactly what each searches."""
    return json.dumps([work["id"], queries, instruments, named], sort_keys=True, ensure_ascii=False)


def _searched(asked):
    """The searches search_many is asked for: (queries, instruments) and, from v15, the sections named."""
    return [(queries, instruments) if named is None else (queries, instruments, named) for _, queries, instruments, named in asked]


def start_search(searcher, work):
    """The searches of some research work started at once (v14, AN.33 D28, piece 33q), as retrieve_parts would start them, keyed by
    what each searches (_search_key): {} where there is no searcher. A work item without queries starts none, and one whose Acts
    code cannot list starts none either - retrieve_parts records why, as before."""
    if searcher is None:
        return {}
    asked = []
    for item in work:
        queries = search_queries(item)
        if not queries:
            continue
        try:
            asked.append((item, queries, search_instruments(item), search_named(item)))
        except (ValueError, KeyError, TypeError):
            continue
    futures = searcher.search_many(_searched(asked), results=FOR_PICK) if asked else []
    return {_search_key(item, queries, instruments, named): future
            for (item, queries, instruments, named), future in zip(asked, futures, strict=True)}


def retrieve_parts(plan, searcher, context, model=None, *, progress=None, started=None, case_index=None, done=None,
                   settle=None, only=None):
    """v10: every question searched side by side in the answer's order (owner, 20 Oct 2026:
    step 1), and each dispute's provisions and judgment paragraphs picked as soon as its own
    questions are searched (21 Oct 2026: step 4). Returns each dispute's part as a future, in
    the answer's order; a part keeps what each of its questions found, or why it failed.
    started (v14, AN.33 piece 33q): the searches start_search began while the plan was finished, by what each searches; one is
    used for the work item it was made for where that item still searches exactly so, once, and every other item is searched now;
    one begun for nothing the plan keeps is cancelled where it has not started, giving way to those needed.
    done (plan AN.41, D70): the parts of disputes already researched by an answer continuing where it stopped, each checked by the
    caller as saved research is checked (validate); each is used as it is and its questions are not searched again.
    settle (plan AN.37, D87): asks the advocate code's questions and waits for the answers - settle(questions) gives each
    question's answer, by its place - which Act a name read as more than one held Act means, before the dispute's pick, and which
    judgment a citation held more than once means, once for the turn, before the judgments cited are read. None asks nothing.
    only (plan AN.48, piece 48b; its register of exceptions, item 1): the disputes researched now - those the advocate named, with
    those done; the plan's other disputes are not searched and have no part. None: every dispute, as before."""
    if accept(plan["proposal"], context) != plan:
        raise ValueError("Research plan differs from its original sources")
    report = progress or (lambda stage, **detail: None)
    started = dict(started or {})
    groups = dispute_work(plan)
    done = {dispute_id: part for dispute_id, part in (done or {}).items() if dispute_id in groups}
    kept = {work["id"] for dispute_id in done for work in groups[dispute_id]}
    if only is not None:
        # 48b: the questions of a dispute not named now are not searched.
        kept |= {work["id"] for dispute_id, works in groups.items() if dispute_id not in only for work in works}
    asked, outcomes, early = [], {}, []
    for work in plan["work"]:
        queries = search_queries(work)
        if not queries or work["id"] in kept:
            continue
        try:
            if searcher is None:
                raise SearchUnavailable("Held-law search is not configured")
            instruments, named = search_instruments(work), search_named(work)
            begun = started.pop(_search_key(work, queries, instruments, named), None)
            if begun is not None:
                early.append((work, queries, instruments, named, begun))
            else:
                asked.append((work, queries, instruments, named))
        except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            outcomes[work["id"]] = exc
    for future in started.values():
        future.cancel()
    finished, lock = [len(plan["work"]) - len(asked) - len(early)], threading.Lock()
    report("searching", done=finished[0], total=len(plan["work"]))

    def searched(*_):
        with lock:  # counts are reported in order
            finished[0] += 1
            if finished[0] < len(plan["work"]):  # the last is followed by the next stage at once
                report("searching", done=finished[0], total=len(plan["work"]))
    futures = searcher.search_many(_searched(asked), results=FOR_PICK, done=searched) if asked else []
    outcomes.update((work["id"], (future, queries, instruments, named))
                    for (work, queries, instruments, named), future in zip(asked, futures, strict=True))
    for work, queries, instruments, named, future in early:
        outcomes[work["id"]] = (future, queries, instruments, named)
        future.add_done_callback(searched)

    def researched(dispute_id, works):
        searches, failures = {}, {}
        for work in works:
            if work["id"] not in outcomes:
                continue
            try:
                outcome = outcomes[work["id"]]
                if isinstance(outcome, Exception):
                    raise outcome
                future, queries, instruments, named = outcome
                searches[work["id"]] = validate_search(future.result(), queries, instruments, named)
            except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
                # This independent read-only adapter/snapshot failed. It supplies no
                # admitted evidence; peers remain available and the failure stays explicit.
                failures[work["id"]] = {"stage": "search", "reason": str(exc) or type(exc).__name__}
        # Plan AN.37 (D87): which Act a name read as more than one held Act means, asked before the pick.
        meant = named_ambiguities(plan, searches) if settle is not None else []
        if meant:
            answers = settle([named_question(item, disputes[dispute_id]) for item in meant])
            for item, (question, answer) in zip(meant, answers):
                at = _chosen_index(question, answer)
                item["meant"] = item["acts"][at] if at is not None else None
        picks = _picked(model, plan, searches, report, meant=meant)
        # v16 (plan AN.35, piece 35d): once, the law still missing for the dispute's questions, and (piece 35e) the judgments the
        # papers cite that its questions need; from v17 (plan AN.36, D35) made before any judgment is read in full, so that the
        # cited ones have first claim on the five.
        further, judgments = _further(model, searcher, plan, searches, picks, report, cited_now(), context)
        return _part(plan, dispute_id, searches, failures, picks, judgments, further=further, meant=meant)
    # Piece 35e: the judgments the papers and messages cite, looked up once for every dispute.
    cited = cited_judgments(context, case_index) if any(
        dispute_id not in done and (only is None or dispute_id in only) for dispute_id in groups) else []
    disputes = {d["id"]: d for d in (plan["proposal"].get("understanding") or {}).get("disputes", [])}
    asked_cited, cited_lock = {}, threading.Lock()

    def cited_now():
        """D87: the judgments cited, with which one the advocate means of a citation held more than once - asked once for the
        turn, by the first dispute to need them; the others wait for that answer."""
        with cited_lock:
            if "cited" not in asked_cited:
                asked_cited["cited"] = _cited_meant(cited, settle, list(groups))
            return asked_cited["cited"]
    pool = ThreadPoolExecutor(max_workers=max(1, len(groups) - len(done)), thread_name_prefix="dispute")
    parts = {}
    for dispute_id, works in groups.items():
        if dispute_id in done:
            parts[dispute_id] = Future()
            parts[dispute_id].set_result(done[dispute_id])
        elif only is None or dispute_id in only:
            parts[dispute_id] = pool.submit(researched, dispute_id, works)
    pool.shutdown(wait=False)
    return parts



# --- v16: the law still missing, named and searched for once per dispute (plan AN.35, D30 A3; piece 35d) ---------------

FURTHER = """You are a senior Indian litigation lawyer. A matter has been broken into legal questions, and for one of its disputes our research has searched the statutes and the judgments we hold for each question and chosen what answers it. You receive the dispute's questions, each with the provisions and the judgment paragraphs chosen for it, what those who chose them said was missing, and any section named for it that we could not read.

Purpose: before the dispute is answered, its law should be complete. For each question, judge as a lawyer would whether what was chosen answers it: the provision that states the governing rule, its exceptions and conditions, the time limit and the procedure where they matter, and the judgments that decide the point.

Outcome: for each question whose governing law is still missing, say in missing what is missing, and name it: in sections, the sections to read by their number, each on its own, by its Act's short title and year and its number as the Act numbers it (a section, an article, an order and rule); in phrases, the words a statute or a court would use for what is missing, each a different way in. Leave out a question whose law is already there; ask only for law the question needs, not for what would merely add to it. This is the one further search for the dispute: what it finds is chosen from as before, and nothing is searched again.

The judgments the papers and the advocate's messages cite come after the questions, each under its number (CJ1, CJ2 ...) with where it is cited and how our library stands on it: held, held more than once, not held, or not checked. For each question, name in cited the held ones a lawyer must read to answer it; each is then read whole, or as an extract when it is long. Name none that does not bear on the question, and none we do not hold.

Work in a loop: read each question and what was chosen, decide what is missing, check that each section you name and each phrase you give would find law the question needs that is not already chosen, and that each judgment you name in cited bears on it, correct what does not, then give the whole."""
FURTHER_SCHEMA = _object({"questions": {"type": "array", "items": _object({
    "question_id": STRING, "missing": STRING, "sections": {"type": "array", "items": NAMED_SECTION}, "phrases": STRINGS,
    "cited": STRINGS})}})
#: The fields of a dispute's further search as its record keeps it; from piece 35e the judgments the papers cite, as the case
#: index found them, and those of them read.
_FURTHER_FIELDS = {"state", "proposal", "reason", "searches", "failures", "picks", "judgments", "cited", "cited_read"}
#: How the held case index stands on a citation (piece 35e), as citations.check_citations says it.
CITED_STATES = ("found", "ambiguous", "not_held", "unavailable")
CITED_SAID = {"found": "held", "ambiguous": "held more than once, not read", "not_held": "not held in our library",
               "unavailable": "not checked: the case index could not be read"}


def _citations_in(context):
    """Each case citation the advocate's messages and the papers make, once by its exact keys, with each place it is made (v16,
    piece 35e). Code reads them (citation_contracts); nothing here decides which judgment a citation names."""
    found = {}
    for identity, row in source_catalogue(context).items():
        if row.get("record_role") not in ("original_account", "supplied_document"):
            continue
        for citation in find_reporter_citations(row["text"]):
            keys = tuple(citation.keys)
            if not keys:
                continue
            entry = found.setdefault(keys, {"citation": " ".join(citation.text.split()), "keys": list(keys), "where": []})
            if identity not in entry["where"]:
                entry["where"].append(identity)
    return [{"id": f"CJ{number}", **entry} for number, entry in enumerate(found.values(), 1)]


def _cited_meant(cited, settle, disputes):
    """The judgments cited, each held more than once with the one the advocate means (D87); as they were where nothing is asked."""
    unsure = [entry for entry in cited if entry["state"] == "ambiguous" and len(entry.get("held") or ()) >= 2]
    if settle is None or not unsure:
        return cited
    answers = settle([cited_question(entry, disputes) for entry in unsure])
    meant = {}
    for entry, (question, answer) in zip(unsure, answers):
        at = _chosen_index(question, answer)
        meant[entry["id"]] = entry["held"][at]["case_id"] if at is not None else None
    return [{**entry, "meant": meant[entry["id"]]} if entry["id"] in meant else entry for entry in cited]


def cited_judgments(context, case_index):
    """The judgments the papers and the messages cite, each looked up in the held case index by its exact keys only (v16, piece
    35e): found (one held judgment), ambiguous (more than one), not held, or unavailable (the index could not be read). Made once
    per turn and kept with the research; never made again on reopening, where the index may have changed."""
    cited = []
    for entry in _citations_in(context):
        try:
            if case_index is None:
                raise IndexUnavailable("the case index is not configured")
            held = held_judgments(entry["keys"], case_index)
        except (IndexUnavailable, OSError) as exc:
            cited.append({**entry, "state": "unavailable", "judgment": None, "reason": str(exc) or type(exc).__name__})
            continue
        state = "found" if len(held) == 1 else "ambiguous" if held else "not_held"
        judgment = ({key: held[0].get(key) for key in ("case_id", "title", "court", "year")} if state == "found" else None)
        # Plan AN.37 (D87): a citation held more than once keeps the judgments it may be, for the advocate to say which is meant.
        unsure = ({"held": [{key: one.get(key) for key in ("case_id", "title", "court", "year")} for one in held], "meant": None}
                  if state == "ambiguous" else {})
        cited.append({**entry, "state": state, "judgment": judgment, "reason": None, **unsure})
    return cited


def _cited_text(cited, context):
    """The cited judgments as the further call reads them: each with how the library stands on it and where it is cited."""
    catalogue = source_catalogue(context)

    def place(identity):
        row = catalogue.get(identity) or {}
        about = row.get("document") if row.get("record_role") == "supplied_document" else None
        return f"{about['name']}, page {about['page']}" if about else "the advocate's message"
    lines = ["\nJudgments the papers and the advocate's messages cite:"]
    for entry in cited:
        held = entry["judgment"] or next((one for one in entry.get("held") or () if one["case_id"] == entry.get("meant")), None)
        named = f" - {held['title']} ({', '.join(str(v) for v in (held.get('court'), held.get('year')) if v)})" if held else ""
        said = "held more than once; the advocate means this one" if entry.get("meant") else CITED_SAID[entry["state"]]
        lines.append(f"  {entry['id']} {entry['citation']}{named}: {said}; cited in "
                     + "; ".join(dict.fromkeys(place(identity) for identity in entry["where"])) + ".")
    return "\n".join(lines)


def _cited_cases(asked, labels, cited, skip):
    """The held cited judgments the further call chose to read (v16, piece 35e), each once, in the order named: only one held as
    one judgment, and none the dispute already reads."""
    by_id = {entry["id"]: entry for entry in cited if entry["state"] == "found" or entry.get("meant")}
    order = []
    for item in asked["questions"]:
        if item["question_id"] not in labels.values():
            continue
        for identity in item.get("cited", ()):
            entry = by_id.get(identity)
            # D87: of a citation held more than once, the judgment the advocate means.
            case_id = (entry["judgment"]["case_id"] if entry["state"] == "found" else entry["meant"]) if entry else None
            if case_id and case_id not in skip and case_id not in order:
                order.append(case_id)
    return order


def _further_text(plan, searches, labels, picks):
    """Each searched question of a dispute with what its picks chose and said, as the further search's call reads it."""
    lines = [f"Matter: {plan['proposal']['understanding']['summary']}"]
    for work in plan["work"]:
        if work["id"] not in labels:
            continue
        label, search = labels[work["id"]], searches[work["id"]]
        lines.append(f"\n{label}: {work['question']}")
        for kind, title in (("provision", "Provisions chosen"), ("judgment", "Judgment paragraphs chosen")):
            offered = {candidate["id"]: candidate for candidate in _offered(search, kind)}
            chosen = [offered[identity] for identity in picks[kind]["chosen"].get(work["id"], []) if identity in offered]
            lines.append(f"  {title}:" + ("" if chosen else " none"))
            for candidate in chosen:
                source = candidate["source"]
                if kind == "provision":
                    heading = re.sub(r"\s+", " ", source.get("section_title") or "")[:140]
                    lines.append(f"    {candidate['title']}, section {candidate['locator']}: {heading}.")
                else:
                    words = re.sub(r"\s+", " ", source.get("full_text") or "").strip()[:300]
                    at = judgment_place(candidate["locator"])
                    lines.append(f"    {candidate['title']}{', ' + at if at else ''}: {words}")
            note = next((item["note"] for item in (picks[kind]["proposal"] or {}).get("questions", ())
                         if item["question_id"] == label), "")
            if note.strip():
                lines.append(f"  What was said of them: {' '.join(note.split())}")
        for entry in search.get("named", ()):
            if entry["state"] != "read":
                lines.append(f"  Named and not read: {entry['act']}, {entry['section']} ("
                             + {"ambiguous": "held more than once", "not_held": "not held in our library",
                                "unavailable": "could not be read"}[entry["state"]] + ").")
    return "\n".join(lines)


def _further_wanted(asked, plan, labels):
    """What a dispute's further search asks of each question (v16), as work items made from its answer: its phrases, and the
    sections it names, each read by its number (a reference naming several read as each it names) - a question named twice keeps
    its first entry, and one that names nothing is searched for nothing. Where it names sections and no phrase, the words it gave
    for what is missing are searched beside them. Deterministic in its inputs, so that replay re-derives it."""
    by_label = {label: work_id for work_id, label in labels.items()}
    works = {work["id"]: work for work in plan["work"]}
    wanted = {}
    for item in asked["questions"]:
        work_id = by_label.get(item["question_id"])
        if work_id is None or work_id in wanted:
            continue
        named = {(" ".join(entry["act"].split()), reference): None
                 for entry in item["sections"] if entry["act"].strip() and entry["section"].strip()
                 for reference in (provision_references(entry["section"]) or (" ".join(entry["section"].split()),))}
        phrases = list(dict.fromkeys(" ".join(phrase.split()) for phrase in item["phrases"] if phrase.strip()))
        if not phrases and named and item["missing"].strip():
            phrases = [" ".join(item["missing"].split())]
        if not phrases:
            continue
        wanted[work_id] = {**works[work_id], "enquiries": [{"query_id": f"{work_id}:further{number}", "text": text}
                                                           for number, text in enumerate(phrases, 1)],
                           "named": [{"act": act, "section": section} for act, section in named]}
    return wanted


def _fresh(search, before):
    """A further search as its picks are shown it (v16): only what was not already offered for its question."""
    seen = {candidate["id"] for kind in _PICK_FIELDS for candidate in _offered(before, kind)} if before else set()
    return {**search, "candidates": [c for c in search["candidates"] if c["id"] not in seen],
            **({"connected": [c for c in search["connected"] if c["id"] not in seen]} if "connected" in search else {}),
            **({"named_found": [c for c in search["named_found"] if c["id"] not in seen]} if "named_found" in search else {})}


def _no_further(state, reason=None):
    return {"state": state, "proposal": None, "reason": reason, "searches": {}, "failures": {},
            "picks": {kind: pick(None, {"work": [], "proposal": {}}, {}, kind) for kind in _PICK_FIELDS}, "judgments": [],
            "cited": [], "cited_read": []}


def _further(model, searcher, plan, searches, picks, report, cited=(), context=None):
    """A dispute's further search (v16, piece 35d): one call names the law still missing for each question; code searches once for
    what it names, the two picks choose among only what is new to each question, and the judgments chosen are read, each judgment
    once. A failed call leaves it unavailable, said; a failed search is kept as that question's failure; nothing is searched again.
    From v17 (plan AN.36, D35) the judgments are read here, after the call, within the dispute's five read in full: the cited ones it
    chose first, then the first pick's, then the further pick's. Returns (the further search, the first pick's judgments read)."""
    labels = _labels(plan, searches)

    def first(skip=frozenset(), limit=None):
        return _read_judgments(searcher, plan, searches, picks["judgment"], skip=skip, limit=limit)
    if not labels:
        return _no_further("not_needed"), first()
    if model is None:
        return _no_further("unavailable", "No model for the further search"), first()
    try:
        asked = _call(model, "core_research_further", FURTHER, _further_text(plan, searches, labels, picks)
                      + (_cited_text(cited, context) if cited else ""), FURTHER_SCHEMA, "further")
    except (ModelError, SchemaViolation) as exc:
        return _no_further("unavailable", type(exc).__name__), first()
    wanted = _further_wanted(asked, plan, labels)
    found, failures = {}, {}
    planned = [(work, search_queries(work), search_instruments(work), search_named(work)) for work in wanted.values()]
    if planned and searcher is None:
        failures = {work["id"]: {"stage": "search", "reason": "Held-law search is not configured"} for work, *_ in planned}
    elif planned:
        try:
            futures = searcher.search_many(_searched(planned), results=FOR_PICK)
        except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            futures = [exc] * len(planned)
        for (work, queries, instruments, named), future in zip(planned, futures, strict=True):
            try:
                if isinstance(future, Exception):
                    raise future
                found[work["id"]] = validate_search(future.result(), queries, instruments, named)
            except (SearchUnavailable, ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
                failures[work["id"]] = {"stage": "search", "reason": str(exc) or type(exc).__name__}
    fresh = {work_id: _fresh(search, searches.get(work_id)) for work_id, search in found.items()}
    # The picks of what is new say no stage of their own: the turn is still choosing the dispute's law.
    # v18 (piece 36e): the further pick keeps only what is left of each question's five provisions.
    room = {work_id: max(0, SECTIONS_A_QUESTION - len(picks["provision"]["chosen"].get(work_id, ()))) for work_id in fresh}
    chosen = (_picked(model, plan, fresh, lambda *_, **__: None, room) if fresh
              else {kind: pick(None, plan, {}, kind) for kind in _PICK_FIELDS})
    # Piece 35e, and D35: the held judgments the papers cite that the call chose come first, each once, within the five.
    claimed = _cited_cases(asked, labels, cited, set())[:IN_FULL]
    cited_read = _read_judgments(searcher, plan, {}, None, cases=[(case_id, set(), set()) for case_id in claimed])
    judgments = first(skip=set(claimed), limit=IN_FULL - len(cited_read))
    read = _read_judgments(searcher, plan, fresh, chosen["judgment"],
                           skip=set(claimed) | {entry["case_id"] for entry in judgments},
                           limit=IN_FULL - len(cited_read) - len(judgments))
    return ({"state": "evaluated", "proposal": asked, "reason": None, "searches": found, "failures": failures, "picks": chosen,
             "judgments": read, "cited": deepcopy(list(cited)), "cited_read": cited_read}, judgments)


def _validate_further(further, plan, searches, judgments, dispute_id, contract, context=None, first_pick=None,
                      first_provisions=None):
    """A dispute's saved further search (v16) checked against its own answer and the dispute's first searches (P46). From v17 (D35)
    the first pick's judgments read are checked here too, after the cited ones that had first claim (first_pick: that pick)."""
    few = contract in FEW_IN_FULL
    if not isinstance(further, dict) or set(further) != _FURTHER_FIELDS or further["state"] not in ("evaluated", "not_needed",
                                                                                                      "unavailable"):
        raise ValueError("A dispute's further search has no checked disposition")
    labels = _labels(plan, searches)
    if further["state"] != "evaluated":
        if (further["proposal"] is not None or further["searches"] or further["failures"] or further["judgments"]
                or further["cited"] != [] or further["cited_read"] != []
                or further["state"] == "not_needed" and labels
                or (further["reason"] is None) != (further["state"] == "not_needed")
                or further["reason"] is not None and (not isinstance(further["reason"], str) or not further["reason"])
                or not isinstance(further["picks"], dict) or set(further["picks"]) != set(_PICK_FIELDS)):
            raise ValueError("A further search not made says why, and holds nothing")
        for kind in _PICK_FIELDS:
            _validate_picks(further["picks"][kind], plan, {}, kind, contract)
        if few:
            _validate_judgments({dispute_id: judgments}, dispute_id, plan, searches, first_pick, contract)
        return
    asked = canonical_schema_data(further["proposal"], FURTHER_SCHEMA)
    require_schema(asked, FURTHER_SCHEMA)
    if asked != further["proposal"] or further["reason"] is not None or not labels:
        raise ValueError("A saved further search differs from its answer")
    wanted = _further_wanted(asked, plan, labels)
    if (not isinstance(further["searches"], dict) or not isinstance(further["failures"], dict)
            or set(further["searches"]) & set(further["failures"])
            or set(further["searches"]) | set(further["failures"]) != set(wanted)):
        raise ValueError("Each question a further search names needs one execution disposition")
    for failure in further["failures"].values():
        if (not isinstance(failure, dict) or set(failure) != {"stage", "reason"} or failure["stage"] != "search"
                or not isinstance(failure["reason"], str) or not failure["reason"].strip()):
            raise ValueError("A further search's failure has no checked disposition")
    for work_id, search in further["searches"].items():
        work = wanted[work_id]
        validate_search(search, search_queries(work), search_instruments(work), search_named(work))
    fresh = {work_id: _fresh(search, searches.get(work_id)) for work_id, search in further["searches"].items()}
    if not isinstance(further["picks"], dict) or set(further["picks"]) != set(_PICK_FIELDS):
        raise ValueError("A further search's picks are not one of each kind")
    # v18 (piece 36e): the further provision pick kept only what was left of each question's five.
    room = ({work_id: max(0, SECTIONS_A_QUESTION - len((first_provisions or {}).get("chosen", {}).get(work_id, ())))
             for work_id in fresh} if contract in FEW_SECTIONS else None)
    for kind in _PICK_FIELDS:
        _validate_picks(further["picks"][kind], plan, fresh, kind, contract, room if kind == "provision" else None)
    if not few:
        _validate_judgments({dispute_id: further["judgments"]}, dispute_id, plan, fresh, further["picks"]["judgment"], contract,
                            skip={entry["case_id"] for entry in judgments})
    # Piece 35e: the cited judgments are the citations the papers and messages make, each as the index stood on it then.
    cited = further["cited"]
    made = _citations_in(context) if context is not None else None
    if (not isinstance(cited, list) or made is None
            or [{key: entry.get(key) for key in ("id", "citation", "keys", "where")} for entry in cited if isinstance(entry, dict)]
            != made
            or any(set(entry) - {"held", "meant"} != {"id", "citation", "keys", "where", "state", "judgment", "reason"}
                   or not _cited_unsure_kept(entry)
                   or entry["state"] not in CITED_STATES
                   or (entry["judgment"] is not None) != (entry["state"] == "found")
                   or entry["judgment"] is not None and (set(entry["judgment"]) != {"case_id", "title", "court", "year"}
                                                         or not isinstance(entry["judgment"]["case_id"], str)
                                                         or not entry["judgment"]["case_id"])
                   or (entry["reason"] is not None) != (entry["state"] == "unavailable") for entry in cited)):
        raise ValueError("The judgments the papers cite are not as the further search kept them")
    if not few:
        wanted = _cited_cases(asked, labels, cited, {entry["case_id"] for entry in [*judgments, *further["judgments"]]})
        _validate_judgments({dispute_id: further["cited_read"]}, dispute_id, plan, {**searches, **further["searches"]}, None,
                            contract, expected=[(case_id, set(), set()) for case_id in wanted])
        return
    # v17 (D35): the cited judgments chosen first, then the first pick's, then the further pick's, within the five.
    claimed = _cited_cases(asked, labels, cited, set())[:IN_FULL]
    _validate_judgments({dispute_id: further["cited_read"]}, dispute_id, plan, {**searches, **further["searches"]}, None,
                        contract, expected=[(case_id, set(), set()) for case_id in claimed])
    _validate_judgments({dispute_id: judgments}, dispute_id, plan, searches, first_pick, contract, skip=set(claimed),
                        limit=IN_FULL - len(further["cited_read"]))
    _validate_judgments({dispute_id: further["judgments"]}, dispute_id, plan, fresh, further["picks"]["judgment"], contract,
                        skip=set(claimed) | {entry["case_id"] for entry in judgments},
                        limit=IN_FULL - len(further["cited_read"]) - len(judgments))


def _cited_unsure_kept(entry):
    """D87: a citation held more than once keeps the judgments it may be and which the advocate means (None: not said), or neither
    (a record made before); no other citation keeps either."""
    if "held" not in entry and "meant" not in entry:
        return True
    held = entry.get("held")
    return (entry.get("state") == "ambiguous" and isinstance(held, list) and len(held) >= 2
            and all(isinstance(one, dict) and set(one) == {"case_id", "title", "court", "year"}
                    and isinstance(one["case_id"], str) and one["case_id"] for one in held)
            and "meant" in entry and (entry["meant"] is None or entry["meant"] in [one["case_id"] for one in held]))


def _validate_meant(meant, plan, searches, dispute_id):
    """D87: a dispute's names read as more than one held Act, as its searches read them, each with an Act it may be or None."""
    expected = named_ambiguities(plan, searches)
    if (not isinstance(meant, list) or not meant or len(meant) != len(expected)
            or any(not isinstance(item, dict) or "meant" not in item
                   or {key: value for key, value in item.items() if key != "meant"} != want
                   or item["meant"] is not None and item["meant"] not in want["acts"] for item, want in zip(meant, expected))):
        raise ValueError("The names a dispute read as more than one Act are not as its searches read them")
    return meant


def further_searches(record):
    """Each further search of a v16 record, as (its question's work id, the search as its picks were shown it), in the plan's
    order: what it found that was new to its question (piece 35d). [] for earlier records."""
    further = record.get("further") or {}
    order = [work["id"] for work in record["plan"]["work"]]
    found = {work_id: search for entry in further.values() for work_id, search in entry["searches"].items()}
    return [(work_id, _fresh(found[work_id], record["searches"].get(work_id))) for work_id in order if work_id in found]


def judgments_read(record):
    """The judgments each dispute of a record reads: those its picks chose and, from v16, those its further picks chose and the
    judgments the papers cite that it chose to read (piece 35e)."""
    further = record.get("further") or {}
    return {dispute_id: [*entries, *(further.get(dispute_id) or {}).get("judgments", ()),
                         *(further.get(dispute_id) or {}).get("cited_read", ())]
            for dispute_id, entries in (record.get("judgments") or {}).items()}


def assemble(plan, parts, *, unfinished=None):
    """The whole v10 record from its disputes' parts, in the answer's order. A dispute with no
    part is refused, unless `unfinished` says why (a turn that stopped part way): its questions
    then record that as their gap and its picks keep nothing."""
    done = {part["part"]: part for part in parts}
    searches, failures, chosen = {}, {}, {field: {} for field in _PICK_FIELDS.values()}
    judgments, further, meant = {}, {}, {}
    for dispute_id, works in dispute_work(plan).items():
        part = done.get(dispute_id)
        if part is None:
            if unfinished is None:
                raise ValueError("A dispute's research is missing")
            further[dispute_id] = _no_further("unavailable", unfinished)
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
        further[dispute_id] = deepcopy(part["further"][dispute_id])
        if (part.get("meant") or {}).get(dispute_id):
            meant[dispute_id] = deepcopy(part["meant"][dispute_id])
    order = [w["id"] for w in plan["work"]]
    record = {"contract": CONTRACT, "plan": deepcopy(plan),
              "searches": {i: searches[i] for i in order if i in searches},
              "failures": {i: failures[i] for i in order if i in failures}, **chosen, "judgments": judgments,
              "further": further, **({"meant": meant} if meant else {})}
    record["state"] = _state(plan, record["searches"], record["failures"], picks_of(record))
    return record


def part_of(record, dispute_id):
    """A v10 or v11 record's part for one dispute, exactly as that dispute's section read it
    (once within a replay, P35)."""
    return once(("part", id(record), dispute_id), (record,), lambda: _part(
        record["plan"], dispute_id, record["searches"], record["failures"],
        {kind: record[field][dispute_id] for kind, field in _PICK_FIELDS.items()},
        (record.get("judgments") or {}).get(dispute_id, []), record["contract"],
        (record.get("further") or {}).get(dispute_id), (record.get("meant") or {}).get(dispute_id)))


def picks_of(record, kind=None):
    """A record's picks as a list: each dispute's (v10), or the one pick of a kind (v7-v9)."""
    kinds = [kind] if kind else [k for k in _PICK_FIELDS if _PICK_FIELDS[k] in record]
    if record.get("contract") in BY_DISPUTE:
        return [pick for k in kinds for pick in record[_PICK_FIELDS[k]].values()]
    return [record[_PICK_FIELDS[k]] for k in kinds if _PICK_FIELDS[k] in record]


def chosen(record, kind="provision"):
    """What a record's picks of a kind chose, by work item - from v16 with what its further picks chose, after."""
    out = {}
    further = [entry["picks"][kind] for entry in (record.get("further") or {}).values()]
    for pick in [*picks_of(record, kind), *further]:
        for work_id, ids in pick["chosen"].items():
            kept = out.setdefault(work_id, [])
            kept.extend(identity for identity in ids if identity not in kept)
    return out


def retrieve(plan, searcher, context, model=None, *, progress=None, case_index=None):
    """The whole v10 research: every dispute's part, assembled (retrieve_parts)."""
    parts = retrieve_parts(plan, searcher, context, model, progress=progress, case_index=case_index)
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
              | ({"further"} if contract in FURTHER_LAW else set())
              | ({"part"} if contract in BY_DISPUTE and "part" in record else set())
              | ({"meant"} if contract in BY_DISPUTE and "meant" in record else set()))
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
                            search_instruments(work, contract=contract), search_named(work, contract=contract))
    picks = []
    if contract in BY_DISPUTE:
        # v10: each dispute's picks, labelled within that dispute's own searched questions.
        disputes = [record["part"]] if "part" in fields else list(groups)
        meant = record.get("meant", {})
        if not isinstance(meant, dict) or set(meant) - set(disputes):
            raise ValueError("The names read as more than one Act name no dispute of the record")
        for dispute_id, items in meant.items():
            ids = {w["id"] for w in groups[dispute_id]}
            _validate_meant(items, plan, {i: s for i, s in record["searches"].items() if i in ids}, dispute_id)
        for kind, field in _PICK_FIELDS.items():
            if not isinstance(record[field], dict) or set(record[field]) != set(disputes):
                raise ValueError(f"The {kind} picks are not one for each dispute")
            for dispute_id in disputes:
                ids = {w["id"] for w in groups[dispute_id]}
                own = {i: search for i, search in record["searches"].items() if i in ids}
                _validate_picks(record[field][dispute_id], plan, own, kind, contract, meant=meant.get(dispute_id, ()))
                picks.append(record[field][dispute_id])
                if kind == "judgment" and contract in JUDGMENTS_READ and contract not in FEW_IN_FULL:
                    # From v17 (D35) a dispute's first judgments read are checked with its further search, after the cited ones.
                    _validate_judgments(record["judgments"], dispute_id, plan, own, record[field][dispute_id], contract)
        if contract in JUDGMENTS_READ and set(record["judgments"]) != set(disputes):
            raise ValueError("The judgments read are not one list for each dispute")
        if contract in FURTHER_LAW:
            # v16 (piece 35d): each dispute's further search, against its own answer and the dispute's first searches.
            if not isinstance(record["further"], dict) or set(record["further"]) != set(disputes):
                raise ValueError("The further searches are not one for each dispute")
            for dispute_id in disputes:
                ids = {w["id"] for w in groups[dispute_id]}
                own = {i: search for i, search in record["searches"].items() if i in ids}
                _validate_further(record["further"][dispute_id], plan, own, record["judgments"][dispute_id], dispute_id, contract,
                                  context, record["judgment_picks"][dispute_id], record["picks"][dispute_id])
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


def _validate_judgments(judgments, dispute_id, plan, searches, pick, contract=CONTRACT, skip=frozenset(), expected=None,
                        limit=None):
    """v11 (P31): the judgments a dispute reads are those its pick chose, in order - every one from v15, at most
    JUDGMENTS_PER_DISPUTE before; each read whole when no longer than the bound, else as an extract
    keeping its opening, its order and what the pick chose; every paragraph kept exactly as
    stored, and what search found and the pick chose marked as found and chosen."""
    entries = judgments.get(dispute_id) if isinstance(judgments, dict) else None
    expected = _chosen_cases(plan, searches, pick, contract, skip, limit) if expected is None else expected
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


def _validate_picks(picks, plan, searches, kind="provision", contract=None, room=None, meant=()):
    labels = _labels(plan, searches)
    meant = meant if kind == "provision" else ()
    if kind == "provision" and contract in FEW_SECTIONS and room is None:
        room = {work_id: SECTIONS_A_QUESTION for work_id in labels}
    elif kind != "provision" or contract not in FEW_SECTIONS:
        room = None
    if (not isinstance(picks, dict) or set(picks) != {"state", "proposal", "chosen", "unknown", "reason"}
            or picks["state"] not in ("evaluated", "unavailable", "not_needed")):
        raise ValueError(f"The {kind} pick has no checked disposition")
    if picks["state"] == "evaluated":
        # v17 (piece 36a): a judgment pick also names the judgments to read in full.
        schema = CHOICE_V17 if kind == "judgment" and contract in FEW_IN_FULL else CHOICE
        choice = canonical_schema_data(picks["proposal"], schema)
        require_schema(choice, schema)
        resolved, unknown = _resolve_picks(choice, plan, searches, labels, kind, room)
        if (picks["proposal"] != choice or picks["reason"] is not None
                or (picks["chosen"], picks["unknown"]) != (_keep_meant(resolved, searches, meant), unknown)):
            raise ValueError(f"The saved {kind} pick differs from its proposal")
    elif picks["state"] == "unavailable":
        if (picks["proposal"] is not None or picks["unknown"] or not isinstance(picks["reason"], str)
                or not picks["reason"]
                or picks["chosen"] != _keep_meant(_fallback_picks(searches, labels, kind, room), searches, meant)):
            raise ValueError(f"An unavailable {kind} pick keeps each question's first six")
    elif (picks["proposal"] is not None or picks["unknown"] or picks["reason"] is not None
          or picks["chosen"] != {w: [] for w in labels} or any(_of_kind(searches[w], kind) for w in labels)):
        raise ValueError(f"A {kind} pick is not needed only when none was returned")
