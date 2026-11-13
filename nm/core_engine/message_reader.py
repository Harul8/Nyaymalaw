"""Plan AN.48, piece 48c: a message sent while a matter waits for the advocate, read for what it is (owner decisions D146, D158,
D161, 9 Nov 2026: "Let the model decide what this new information is, what would be its impact"; "ask only unclear ones").

The model reads the message against where the matter stands - its disputes, what is done for each, what the stop offers - and says
what it is: a go-ahead for the work, information added to the matter, a correction of what NM read or understood, a request to
rethink the matter, a new question that is not about this matter, or unclear; which disputes it touches, how critical new information
is, and in a sentence or two how it took the message, so that the advocate can correct it. It works in a loop of its own: think,
judge, check against the advocate's words and the matter, correct. Code admits only what is mechanical: a go-ahead is one the stop
offers, for disputes the matter has (steps.given decides); the disputes named are the matter's; the words are there. What code
cannot admit, after one more look told why, is taken as unclear. A reader that cannot be reached loses no message: its caller keeps
the words and says so.
"""
from __future__ import annotations

import json
import logging

from nm.core_engine import reasoning, shown_words, steps as stepwise

log = logging.getLogger(__name__)

OPERATION = "core_message_reader"
#: What a message is (48c).
KINDS = ("go", "information", "correction", "rethink", "question", "unclear")
#: The go-aheads the reader may give, as a stop offers them (steps.GOS).
CHOICES = ("research", "write", "next", "end_to_end", "done")
#: The words NM says of a message where the reader gave none code can show, by kind.
SAID = {"go": "Taken as your go-ahead.", "information": "Taken as new information for the matter.",
        "correction": "Taken as a correction of what NM read.", "rethink": "Taken as a request to rethink the matter.",
        "question": "Taken as a new question; it waits until you finish this matter.",
        "unclear": "NM could not tell how you meant this message."}
ASK = "Should NM take this as information for the matter, as your go-ahead, or as a new question?"

PROMPT = """You are an Indian advocate's junior, working through a matter with them step by step. The matter is waiting for the advocate: you receive where it stands - its disputes, what has been done for each, and what the advocate can ask for next - the advocate's earlier messages in it, and the advocate's new message.

Purpose: take the message the way the advocate meant it, so that the work goes on as they want and nothing they said is lost.

Outcome: kind - what the message is: go (a go-ahead for the work: research or the analysis for disputes it names, the next step, everything remaining end to end, or that the matter is done); information (facts or papers added to the matter); correction (it corrects something we read from the papers or understood of the matter); rethink (it asks us to understand the matter again, or changes what is asked); question (a new question that is not about this matter); or unclear, where you cannot tell. For a go-ahead, the choice and the disputes it names, by their ids, from what can be asked for next. For information or a correction, the disputes it touches by their ids (none where it touches the matter as a whole), whether it is critical - whether work already done or about to be done would be wrong or incomplete without it - and for a correction what it corrects, in a few words, and new_questions - the legal questions it raises that a dispute's research has not asked (each with the dispute's id, the question as a lawyer would put it, why it is needed and the law to check first), none where it raises none - with item - the id of what we read that it corrects, from what we read
of the matter (a fact or an event of the papers' timeline), or empty where it corrects none of them - and value, the corrected
value in the advocate's words. Then said: in a sentence or two, to the advocate, how you took the message, so that they can correct you. Where it is unclear, ask: the one short question that would settle it.

Work in a loop: read the message against where the matter stands, decide what it is, check your reading against the advocate's exact words and the disputes as named, correct it, then answer."""
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["kind", "choice", "disputes", "critical", "corrects", "item", "value", "new_questions", "said", "ask"],
          "properties": {"kind": {"type": "string", "enum": list(KINDS)},
                         "choice": {"type": ["string", "null"], "enum": [*CHOICES, None]},
                         "disputes": {"type": "array", "items": {"type": "string"}},
                         "critical": {"type": "boolean"},
                         "corrects": {"type": "string"},
                         "item": {"type": "string"},
                         "value": {"type": "string"},
                         "new_questions": {"type": "array", "items": {
                             "type": "object", "additionalProperties": False,
                             "required": ["dispute", "question", "why_needed", "law_to_check"],
                             "properties": {"dispute": {"type": "string"}, "question": {"type": "string"},
                                            "why_needed": {"type": "string"},
                                            "law_to_check": {"type": "array", "items": {"type": "string"}}}}},
                         "said": {"type": "string"},
                         "ask": {"type": "string"}}}


def material(held, message):
    """What the reader reads: where the matter stands (its stop - what was done, what comes next, each dispute's state, the
    go-aheads offered), the advocate's earlier messages in it, and the new message. Nothing else."""
    card = stepwise.card(held) or {}
    earlier = [held.get("message") or "", *(steer.get("text") or "" for steer in held.get("steers") or ())]
    return {"where_the_matter_stands": {"done": card.get("done_said"), "next": card.get("next_said"),
                                        "disputes": card.get("disputes") or [],
                                        # 48i: the legal questions each dispute's research asks, so that a new one can be told.
                                        "questions_each_dispute_asks": asked_questions(held),
                                        "can_be_asked_for": [{"choice": go["choice"], "disputes": go.get("disputes"),
                                                              "said": go["said"]} for go in card.get("gos") or ()]},
            "earlier_messages": [text for text in earlier if text.strip()],
            # 48g: what NM read of the matter, by id, so that a correction can name what it changes.
            "what_we_read": read_items(held),
            "new_message": message}


def asked_questions(held):
    """48i: each of the matter's disputes by id, with the legal questions its research asks."""
    plan = (((held or {}).get("steps") or {}).get("understood") or {}).get("plan") or {}
    disputes = (((plan.get("proposal") or {}).get("understanding") or {}).get("disputes")) or []
    return [{"dispute": dispute["id"], "questions": [question.get("question", "") for question in dispute.get("legal_questions") or ()]}
            for dispute in disputes if isinstance(dispute, dict) and dispute.get("id")]


def read_items(held):
    """48g: what NM read of the matter that a correction may change - the facts of its understanding and the events of the papers'
    timeline - each by its id, with the words the board shows."""
    plan = (((held or {}).get("steps") or {}).get("understood") or {}).get("plan") or {}
    proposal = plan.get("proposal") or {}
    facts = [{"id": fact["id"], "fact": fact.get("fact", "")} for fact in (proposal.get("understanding") or {}).get("facts") or ()
             if isinstance(fact, dict) and fact.get("id")]
    events = [{"id": event["id"], "date": event.get("date", ""), "what": event.get("what", "")}
              for event in proposal.get("chronology") or () if isinstance(event, dict) and event.get("id")]
    return {"facts": facts, "events": events}


def admitted(data, held):
    """The reader's judgement as code admits it - {"kind", "choice", "disputes", "go" (steps.given's go-ahead, or None for Done
    before any analysis), "critical", "corrects", "said", "ask"} - or (None, why) where it cannot be."""
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        return None, "the kind is not one of the kinds given"
    kind = data["kind"]
    state = stepwise.state_of(held.get("steps"))
    named = [name for name in data.get("disputes") or () if isinstance(name, str)]
    unknown = [name for name in named if name not in state["order"]]
    if unknown and not state["whole"]:
        return None, f"these are not the matter's disputes: {', '.join(unknown)}"
    # Plan AN.51 (51b, D196): code's own sentence for the kind is NM's status; the reader's wording is added last, after
    # everything code says, marked as NM's reading, where it may be shown at all (shown_words).
    said, reading = SAID[kind], shown_words.reading(data.get("said"))
    judgement = {"kind": kind, "choice": None, "disputes": [], "go": None, "critical": data.get("critical") is True,
                 "corrects": (data.get("corrects") or "").strip() if isinstance(data.get("corrects"), str) else "",
                 "item": "", "value": "", "new_questions": [], "said": " ".join(said.split()), "ask": ""}
    if kind == "go":
        choice = data.get("choice")
        disputes = [name for name in named if name in state["order"]] or None
        if state["whole"] or choice not in ("research", "write"):
            disputes = None
        try:
            go = stepwise.given(held["go"], choice, held=held, disputes=disputes)
        except (ValueError, KeyError, TypeError) as exc:
            return None, f"that go-ahead is not one this stop offers ({exc})"
        judgement.update(choice=choice, disputes=disputes or [], go=go)
    elif kind in ("information", "correction"):
        judgement["disputes"] = [name for name in named if name in state["order"]]
        # 48i (D156): the questions it raises for what is new, each for one of the matter's disputes and in words.
        ids = {entry["dispute"] for entry in asked_questions(held) if entry["questions"]}
        judgement["new_questions"] = [
            {"dispute": entry["dispute"], "question": " ".join(entry["question"].split()),
             "why_needed": " ".join(str(entry.get("why_needed") or "").split()),
             "law_to_check": [" ".join(law.split()) for law in entry.get("law_to_check") or () if isinstance(law, str) and law.strip()]}
            for entry in data.get("new_questions") or () if isinstance(entry, dict) and entry.get("dispute") in ids
            and isinstance(entry.get("question"), str) and entry["question"].strip()][:stepwise.MOST_PROPOSED]
        if kind == "correction":
            # 48g (D148): the item it changes must be one NM read of this matter; otherwise none is marked, and NM says so.
            items = read_items(held)
            known = {entry["id"]: entry.get("fact") or " ".join(part for part in (entry.get("date"), entry.get("what")) if part)
                     for entry in [*items["facts"], *items["events"]]}
            item = data.get("item") if isinstance(data.get("item"), str) else ""
            value = " ".join((data.get("value") or "").split()) if isinstance(data.get("value"), str) else ""
            if item in known and value:
                # Code says what it marks (P10: a saved effect is code's to state), so that a wrong match can be put right.
                judgement.update(item=item, value=value, said=f"{judgement['said']} On the board, \"{' '.join(known[item].split())}\" "
                                                               f"is marked as corrected by you: {value}".strip())
            else:
                judgement["said"] = (judgement["said"] + " NM could not tell which item of what it read this corrects, so the "
                                     "board is not marked; say which, if it matters.").strip()
    elif kind == "unclear":
        judgement["ask"] = shown_words.asked(ASK, data.get("ask"))
    judgement["said"] = shown_words.after(judgement["said"], reading)
    return judgement, None


def read(model, held, message):
    """The reader's judgement of a message sent while a matter waits, as code admits it - asked once more, told why, where its first
    cannot be admitted - or an unclear judgement where it still cannot. A usage limit or a refused permission goes on to its owner;
    any other failure of the model raises ModelError, for its caller to keep the message and say so."""
    from nm.shared.model_port import Prompt, Tier, canonical_schema_data

    given = material(held, message)
    asked = dict(given)
    for _ in range(2):
        user = json.dumps(asked, ensure_ascii=False)
        receipt = model.structured(Prompt(system=PROMPT, user=user, operation=OPERATION,
                                          effort=reasoning.effort("message_reader")),
                                   SCHEMA, Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, PROMPT, user,
                                                                                   json.dumps(SCHEMA)))
        data = canonical_schema_data(receipt.data, SCHEMA) if receipt.usable and receipt.data is not None else None
        judgement, why = admitted(data, held)
        if judgement is not None:
            return judgement
        log.info("The message reader's judgement was not admitted: %s", why)
        asked = {**given, "your_last_judgement": data, "why_it_cannot_be_taken": why}
    return {"kind": "unclear", "choice": None, "disputes": [], "go": None, "critical": False, "corrects": "", "item": "",
            "value": "", "new_questions": [], "said": SAID["unclear"], "ask": ASK}
