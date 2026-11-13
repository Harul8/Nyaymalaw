"""Plan AN.48, owner decision D175 (10 Nov 2026, "Yes, build it"): a follow-up starts from NM's last understanding of the matter.

A message sent step by step after an answer is saved is read against the matter as that answer understood it - its facts, the
timeline of its papers, its disputes and the legal questions each dispute's research asked. NM's follow-up reader, a small model
step working in a loop of its own, says what the message is: a question or instruction on the same matter, facts and papers (with
the legal questions it raises that the research has not asked); one that adds or corrects facts, or changes or limits what is
asked; another matter; or unclear. Code admits only what is mechanical: the kind is one given, each new question names one of the
matter's disputes and has words, at most MOST of them.

On the same matter (the kept route) the turn keeps that understanding and the papers' reading and weighing in it, admitted again
against this conversation by research's own acceptance, with the follow-up's questions added to their disputes (research v19,
plan AN.48 48i); each dispute the follow-up adds nothing to keeps its research, renumbered as this turn numbers the same questions
and kept only where research's own check of saved research passes. Everything else is read again as before: papers sent with the
message, any other judgement, a reader that cannot be reached, an earlier understanding that does not admit again exactly as it
was, or questions that cannot be added without a check failing. The advocate is told which, in code's words. Nothing here changes
the research, the understanding, the citations or the checks (D143): it chooses what the turn starts from.
"""
from __future__ import annotations

import json
import logging

from nm.core_engine import message_reader, reasoning, replay_scope, research, shown_words, understanding
from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data

log = logging.getLogger(__name__)

OPERATION = "core_follow_up_reader"
#: What a follow-up is.
KINDS = ("same_matter", "changes_matter", "another_matter", "unclear")
#: The routes a follow-up takes: its understanding kept, or the whole matter read again.
KEPT, AFRESH = "kept", "afresh"
#: The most legal questions a follow-up may add (as many as the message reader may propose for what is new, 48i).
MOST = 20
#: What NM says of a follow-up, by kind: code's own words, which always stand. The reader's wording is shown after them as NM's
#: reading, where it may be shown at all (plan AN.51, 51b, D196: shown_words).
SAID = {"same_matter": "Taken as a question on the matter as NM understood it.",
        "changes_matter": "Your message adds to or changes the matter as NM understood it.",
        "another_matter": "Your message is about another matter.",
        "unclear": "NM could not tell whether your message changes the matter."}
#: Code's words, by why the whole matter was read again.
AGAIN = "NM read the whole matter again from the start"
AGAIN_SAID = {"papers": AGAIN + ", because papers came with your message.",
              "unread": AGAIN + ": it could not tell just now whether your message changes the matter.",
              "not_added": AGAIN + ": what your message asks could not be added to its earlier understanding."}
ASK_AGAIN = "To have NM read the whole matter again from the start, say so here."

PROMPT = """You are an Indian advocate's junior. You and the advocate have already worked on a matter, and our last answer is saved. You receive how we understood the matter - its facts, the timeline of its papers, its disputes and the legal questions each dispute's research asked - the advocate's earlier messages, and the new message they sent after our answer.

Purpose: answer the new message quickly without answering it any less well. Where our understanding of the matter still holds for it, we keep that understanding and our reading of the papers, and research only the legal questions the message adds; where the message changes the matter, we read and understand the whole matter again.

Outcome: kind - same_matter where the message asks a question or gives an instruction about this matter on the same facts and papers, so that our understanding still holds (it may raise legal questions our research has not asked); changes_matter where it adds or corrects facts, changes or limits what the advocate wants from us, or needs the matter understood differently - a question that belongs to none of the disputes we understood is one; another_matter where it is about a different matter; unclear where you cannot tell. For same_matter, new_questions: the legal questions the message raises that a dispute's research has not asked - each with the dispute's id, the question as a lawyer would put it, why it is needed and the law to check first - none where it raises none. Then said: in a sentence or two, to the advocate, how you took the message, so that they can correct you.

Work in a loop: read the message against the matter as we understood it, decide, check your decision against the advocate's exact words - does it state a fact we do not hold, or ask for something our understanding cannot answer? - correct it, then answer."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["kind", "new_questions", "said"],
          "properties": {"kind": {"type": "string", "enum": list(KINDS)},
                         "new_questions": message_reader.SCHEMA["properties"]["new_questions"],
                         "said": {"type": "string"}}}


def earlier(rows):
    """The last saved answer's understanding of the matter - {"turn_id", "plan", "parts"}: its research plan and the research of each
    dispute it finished, as saved - or None where it holds none to keep: no matter, no dispute with questions to research, a research
    record of another version than today's, or one that cannot be read so. Only the last answer is read."""
    if not rows:
        return None
    row = rows[-1]
    try:
        record = row["activities"]["research"]
        if record.get("contract") not in (research.CONTRACT, research.ADDED_CONTRACT):
            return None
        plan = record["plan"]
        work = research.dispute_work(plan)
        if not plan["proposal"]["understanding"].get("needs_research") or not work:
            return None
        parts = {dispute_id: research.part_of(record, dispute_id) for dispute_id in work
                 if (record.get("picks") or {}).get(dispute_id, {}).get("reason") != research.UNFINISHED}
        return {"turn_id": row["turn_id"], "plan": plan, "parts": parts}
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def _held(before):
    """The earlier understanding in the form the message reader reads one (its plan as a turn's steps keep it)."""
    return {"steps": {"understood": {"plan": before["plan"]}}}


def material(before, context):
    """What the reader reads: the matter as we understood it, the advocate's earlier messages, and the new message. Nothing else."""
    held = _held(before)
    disputes = before["plan"]["proposal"]["understanding"]["disputes"]
    asked = {entry["dispute"]: entry["questions"] for entry in message_reader.asked_questions(held)}
    return {"the_matter_as_we_understood_it": {
                **message_reader.read_items(held),
                "disputes": [{"id": dispute["id"], "name": dispute.get("name", ""), "between": dispute.get("between", []),
                              "legal_questions": asked.get(dispute["id"], [])} for dispute in disputes]},
            "earlier_messages": [row["text"] for row in context["conversation"]
                                 if row.get("record_role") == "original_account" and row.get("text", "").strip()],
            "new_message": context["latest"]["text"]}


def admitted(data, before):
    """The reader's judgement as code admits it - {"kind", "new_questions", "said", "reading"} - or (None, why) where it cannot
    be. said: code's fixed sentence for the kind. reading: the reader's own wording as it may be shown, or "" (shown_words)."""
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        return None, "the kind is not one of the kinds given"
    kind = data["kind"]
    questions = []
    if kind == "same_matter":
        ids = {entry["dispute"] for entry in message_reader.asked_questions(_held(before)) if entry["questions"]}
        given = data.get("new_questions") or []
        unknown = [str(entry.get("dispute")) for entry in given if not isinstance(entry, dict) or entry.get("dispute") not in ids]
        if unknown:
            return None, f"these are not disputes of the matter as we understood it: {', '.join(unknown)}"
        if any(not isinstance(entry.get("question"), str) or not entry["question"].strip() for entry in given):
            return None, "a new question has no words"
        if len(given) > MOST:
            return None, f"more than {MOST} new questions"
        questions = [{"dispute": entry["dispute"], "question": " ".join(entry["question"].split()),
                      "why_needed": " ".join(str(entry.get("why_needed") or "").split()),
                      "law_to_check": [" ".join(law.split()) for law in entry.get("law_to_check") or ()
                                       if isinstance(law, str) and law.strip()]} for entry in given]
    return {"kind": kind, "new_questions": questions, "said": SAID[kind], "reading": shown_words.reading(data.get("said"))}, None


def read(model, before, context):
    """The reader's judgement of a follow-up, as code admits it - asked once more, told why, where its first cannot be admitted - or
    an unclear judgement where it still cannot. A failure of the model raises, for the caller to read the matter again."""
    given = material(before, context)
    asked = dict(given)
    for _ in range(2):
        user = json.dumps(asked, ensure_ascii=False)
        receipt = model.structured(Prompt(system=PROMPT, user=user, operation=OPERATION,
                                          effort=reasoning.effort("message_reader")),
                                   SCHEMA, Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, PROMPT, user,
                                                                                   json.dumps(SCHEMA)))
        data = canonical_schema_data(receipt.data, SCHEMA) if receipt.usable and receipt.data is not None else None
        judgement, why = admitted(data, before)
        if judgement is not None:
            return judgement
        log.info("The follow-up reader's judgement was not admitted: %s", why)
        asked = {**given, "your_last_judgement": data, "why_it_cannot_be_taken": why}
    return {"kind": "unclear", "new_questions": [], "said": SAID["unclear"], "reading": ""}


def _asks(work):
    """What a research work item asks and searches, apart from its identities and its sources."""
    return {**{key: value for key, value in work.items() if key not in ("id", "sources", "enquiries")},
            "enquiries": [{key: value for key, value in enquiry.items() if key != "query_id"} for enquiry in work["enquiries"]]}


def _name(text, names):
    """An identity renamed - one of names, or one made from one of them ('<work>:q1' ...) - or the text as it was."""
    if text in names:
        return names[text]
    head = text
    while ":" in head:
        head = head.rsplit(":", 1)[0]
        if head in names:
            return names[head] + text[len(head):]
    return text


def _renamed(value, names):
    if isinstance(value, dict):
        return {(_name(key, names) if isinstance(key, str) else key): _renamed(item, names) for key, item in value.items()}
    if isinstance(value, list):
        return [_renamed(item, names) for item in value]
    if isinstance(value, str):
        return _name(value, names)
    return value


def carried(part, before, plan):
    """A dispute's research saved with an earlier answer, as part of this turn's plan: its work renumbered as this plan numbers the
    same questions, and moved onto the plan (research.rebased) - for research's own check of saved research to decide whether it is
    kept. ValueError where the dispute's questions are not asked exactly as before."""
    dispute_id = part["part"]
    old, new = research.dispute_work(before).get(dispute_id) or [], research.dispute_work(plan).get(dispute_id) or []
    if not old or [work["question_id"] for work in old] != [work["question_id"] for work in new] or any(
            len(one["enquiries"]) != len(other["enquiries"]) or _asks(one) != _asks(other) for one, other in zip(old, new)):
        raise ValueError("The dispute's questions are not asked as they were")
    names = {}
    for one, other in zip(old, new):
        names[one["id"]] = other["id"]
        names.update((asked["query_id"], made["query_id"]) for asked, made in zip(one["enquiries"], other["enquiries"]))
    return research.rebased({key: _renamed(value, names) for key, value in part.items() if key != "plan"}, plan)


def _papers_now(context):
    """Whether papers came with the latest message."""
    turn = context["latest"]["turn_id"]
    return any(page.get("turn_id") == turn for page in [*context.get("documents", ()), *context.get("unread_document_pages", ())])


def _again(why, interpretation=None):
    return {"route": AFRESH, "said": AGAIN_SAID[why], "interpretation": interpretation}


def continued(calls, context, before, report):
    """How a follow-up's turn starts (D175). The kept route: {"route": KEPT, "interpretation", "plan", "parts", "said"} - the message's
    own reading, the earlier understanding admitted again against this conversation (with the follow-up's questions added), the
    research of each dispute kept, and code's words on what was kept and added. Otherwise the whole matter is read again: {"route":
    AFRESH, "said", "interpretation"} - the message's reading where it was made, so that it is not made twice - or, for a message
    that carries no matter (a courtesy), {"route": None, "interpretation"}: answered as today. calls: the turn's calls; the message's
    reading and the follow-up reader run side by side."""
    if _papers_now(context):
        return _again("papers")

    def judge():
        try:
            return read(calls, before, context)
        except UsageLimitReached:
            raise
        except ModelError as exc:  # SchemaViolation included: an outage or an unreadable answer reads the matter again
            log.warning("The follow-up reader could not be reached: %s", type(exc).__name__)
            return None
    # The message's own reading is made beside the reader, as the matter's first understanding is beside it (turn._interpreted).
    with replay_scope.Pool(max_workers=1) as beside:
        judging = beside.submit(judge)
        interpretation = calls.checked("core_understanding", lambda: understanding.understand(calls, context))
        judgement = judging.result()
    if not research.carries_matter(interpretation):
        return {"route": None, "interpretation": interpretation}
    if judgement is None:
        return _again("unread", interpretation)
    if judgement["kind"] != "same_matter":
        return {"route": AFRESH, "said": shown_words.after(f"{AGAIN}. {judgement['said']}", judgement["reading"]),
                "interpretation": interpretation}
    report("continuing")
    plan_before = before["plan"]
    try:
        base = research.accept(plan_before["proposal"], context)
        if base["issues"] != plan_before["issues"]:
            raise ValueError("The earlier understanding does not admit again exactly as it was")
        plan = base
        adding = [{"dispute_id": entry["dispute"], "question": entry["question"], "why_needed": entry["why_needed"],
                   "law_to_check": entry["law_to_check"], "source": context["latest"]["source_id"]}
                  for entry in judgement["new_questions"]]
        if adding:
            proposal = research.with_questions(calls, plan_before, adding, report)
            if proposal is plan_before["proposal"]:
                raise ValueError("No question could be added")
            plan = research.accept(proposal, context)
            if plan["issues"] != base["issues"]:
                raise ValueError("A question added does not pass the plan's checks")
    except UsageLimitReached:
        raise
    except (ValueError, KeyError, TypeError, IndexError, ModelError) as exc:  # a phrase step that failed outright included
        log.warning("A follow-up's earlier understanding was not kept: %s", type(exc).__name__)
        return _again("not_added", interpretation)
    touched = {entry["dispute_id"] for entry in adding}
    parts = {}
    for dispute_id, part in before["parts"].items():
        if dispute_id in touched:
            continue
        try:
            moved = carried(part, plan_before, plan)
            research.validate(moved, plan, context)
        except (ValueError, KeyError, TypeError, IndexError, SchemaViolation) as exc:
            log.warning("A dispute's earlier research was not kept for a follow-up: %s", type(exc).__name__)
            continue
        parts[dispute_id] = moved
    return {"route": KEPT, "interpretation": interpretation, "plan": plan, "parts": parts,
            "said": _kept_said(judgement, plan, adding, parts)}


def _kept_said(judgement, plan, adding, parts):
    """Code's words on the kept route: how the message was taken, what was kept and what is added for research - and, after all
    of them, the reader's own wording, marked as NM's reading, where it may be shown (plan AN.51, 51b)."""
    names = {dispute["id"]: dispute.get("name") or dispute["id"] for dispute in plan["proposal"]["understanding"]["disputes"]}
    added = "; ".join(f"{names.get(entry['dispute_id'], entry['dispute_id'])}: {entry['question']}" for entry in adding)
    kept = [names.get(dispute_id, dispute_id) for dispute_id in research.dispute_work(plan) if dispute_id in parts]
    return shown_words.after(" ".join(part for part in (
        judgement["said"],
        "NM kept its understanding of the matter and its reading of your papers"
        + (f", and adds for research - {added}" if added else "") + ".",
        f"The law found before for {', '.join(kept)} is kept." if kept else "",
        ASK_AGAIN) if part), judgement["reading"])
