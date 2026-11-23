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

Plan AN.58 (D287, 17 Nov 2026; the owner's D269: "everything should be step by step, unless user explicilty says do it end to end,
or user asks for anythinig specific"): a message sent step by step is read once more, as its work begins, for how it asks to be
worked (way). Step by step is the default; a message that plainly asks for the work end to end, or asks for one specific thing
rather than a matter to be worked through, is worked straight through. The model reads the words - never a list of keywords - and
code says what NM does, with the model's reading after it, marked. A reading that fails or is unclear leaves the message step by
step, which stops before any research is paid for.
"""
from __future__ import annotations

import json
import logging

from nm.core_engine import reasoning, shown_words, steps as stepwise

log = logging.getLogger(__name__)

OPERATION = "core_message_reader"
#: What a message is (48c).
KINDS = ("go", "information", "correction", "rethink", "question", "unclear")
#: Distinguish an explicit batch in a message from a targeted action missing its targets.
BATCH_CHOICES = {"research_all": "research", "write_all": "write"}
CHOICES = (*stepwise.GOS, *BATCH_CHOICES)
#: The words NM says of a message where the reader gave none code can show, by kind.
SAID = {"go": "Taken as your go-ahead.", "information": "Taken as new information for the matter.",
        "correction": "Taken as a correction of what NM read.", "rethink": "Taken as a request to rethink the matter.",
        "question": "Taken as a new question; it waits until you finish this matter.",
        "unclear": "NM could not tell how you meant this message."}
ASK = "Should NM take this as information for the matter, as your go-ahead, or as a new question?"

PROMPT = """Message: The advocate has sent a message while an Indian matter waits for them. You receive their new words and earlier words from the waiting turn, the disputes and work at the stop, server-offered go-aheads, and NM's derived reading by item ID.

Purpose: Propose how to take the new message at this stop, preserving the advocate's scope and words.

Look for: What the advocate authorises now, which dispute or step their words refer to, and whether the offered go-ahead matches. Use research or write for the selected disputes, and next for the next step when it is clear. Use research_all or write_all only when the advocate expressly asks for that step for all eligible disputes. An instruction to research all disputes, even if it says to research them end to end, authorises research alone. Use end_to_end only for explicit authority to run every remaining step of the whole matter. Use search_again for a failed search the advocate wants made again, draft when they ask for the draft the stop offers, and done when they ask to finish. Keep a named target where it controls the scope. If the target or action is unresolved, or the stop offers no matching action, ask for the distinction that would settle it. Treat reported or quoted directions as someone else's words unless adopted by the advocate. Identify new facts and corrections from the advocate's account. A correction may refer to NM's reading as its target, while its factual basis comes from the advocate or their original sources.

Outcome: Return one judgement with kind, choice, disputes, critical, corrects, item, value, new_questions, said and ask. The kind is go for an offered go-ahead, information for facts or papers added to the matter, correction for a change to NM's reading, rethink for a new understanding or change of task, question for a new question outside the matter, or unclear. With go return its choice and the owned IDs of the disputes it selects, or an empty list for a whole-matter or explicit batch action. For information or correction give the disputes touched and whether the change is critical because it affects work done or about to be done. With correction give what is corrected, the ID of the item if identified, and the advocate's exact corrected words if supplied. With information or correction list any new_questions, each with its dispute ID, legal question, why it matters and law to check first. Use empty fields where inapplicable. In said explain your reading briefly. In ask give a single question only when the meaning is unclear."""
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
    go-aheads offered), the advocate's earlier messages in it, any saved exchanges while waiting, and the new message."""
    card = stepwise.card(held) or {}
    earlier = [held.get("message") or "", *(steer.get("text") or "" for steer in held.get("steers") or ())]
    exchanges = [{"advocate": entry["text"], "nm": entry["said"]} for entry in (held.get("go") or {}).get("heard", ())]
    return {"where_the_matter_stands": {"done": card.get("done_said"), "next": card.get("next_said"),
                                        "disputes": card.get("disputes") or [],
                                        # 48i: the legal questions each dispute's research asks, so that a new one can be told.
                                        "questions_each_dispute_asks": asked_questions(held),
                                        "can_be_asked_for": _offered(card)},
            "earlier_messages": [text for text in earlier if text.strip()],
            **({"waiting_exchanges": exchanges} if exchanges else {}),
            # 48g: what NM read of the matter, by id, so that a correction can name what it changes.
            "what_we_read": read_items(held),
            "new_message": message}


def _offered(card):
    batch = {action: choice for choice, action in BATCH_CHOICES.items()}
    return [{"choice": batch.get(go["choice"], go["choice"])
             if card.get("disputes") and go.get("disputes") is None else go["choice"],
             "disputes": go.get("disputes"), "said": go["said"]} for go in card.get("gos") or ()]


def _go_scope(choice, named, held, state):
    """Resolve only a scope that the server's saved stop makes unique."""
    if choice in (*BATCH_CHOICES, "end_to_end", "done") and named:
        raise ValueError("A named dispute cannot authorise a whole-matter action")
    if state["whole"] and named:
        eligible = {item["dispute"] for item in asked_questions(held) if item["questions"]}
        if len(named) != 1 or named[0] not in eligible:
            raise ValueError("The named dispute is not the scope of this answer")
        return choice, None
    if choice in BATCH_CHOICES:
        if not any(go["choice"] == choice for go in _offered(stepwise.card(held) or {})):
            raise ValueError("This stop does not offer that batch action")
        return BATCH_CHOICES[choice], None
    if choice in ("research", "write", "draft") and not state["whole"] and not named:
        targets = [go["disputes"] for go in _offered(stepwise.card(held) or {})
                   if go["choice"] == choice]
        if len(targets) != 1:
            raise ValueError("Choose the dispute or an explicitly requested batch action")
        return choice, targets[0]
    return choice, named or None


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
        try:
            choice, disputes = _go_scope(data.get("choice"), named, held, state)
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


WAY_OPERATION = "core_message_way"
#: How a message may ask to be worked (D287): step by step, the default; end to end; one specific thing.
WAYS = ("steps", *stepwise.WAYS)
#: Code's words where a message is worked straight through: NM's status, said as the work begins; the model's reading after them.
WAY_SAID = {"end_to_end": "NM read your message as asking for the work end to end, so it is working straight through without "
                          "stopping for your go-ahead. Press Stop to stop it.",
            "specific": "NM read your message as asking for one specific thing, so it is answering straight through without "
                        "stopping for your go-ahead. Press Stop to stop it."}

WAY_PROMPT = """You are an Indian advocate's junior. The advocate has just sent you a message. You work a message with the advocate step by step, as a junior works with a senior: first you read the papers and understand the matter, then you stop so that the advocate sees what you understood before any research is done, and you research and write only when the advocate says so.

Purpose: tell whether the advocate wants this message worked otherwise - straight through - so that they are not stopped where they did not want to be, and are stopped wherever they may want to see the work first.

Outcome: way - end_to_end where the advocate plainly asks for the work to be done straight through, end to end, without stopping; specific where the message asks for one specific thing - a question answered, a document drafted, a point looked up - rather than a matter to be worked through with them; steps otherwise, and wherever you are not sure. Then said: in a sentence, to the advocate, how you read the message, so that they can correct you.

Work in a loop: read the message with what came before it in the conversation, decide, check your reading against the advocate's exact words, correct it, then answer."""
WAY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["way", "said"],
              "properties": {"way": {"type": "string", "enum": list(WAYS)}, "said": {"type": "string"}}}


def way_material(message, *, earlier=(), papers=0):
    """What the way is read from: the advocate's earlier messages in the conversation, how many papers came with this one, and its
    words. Nothing else."""
    return {"earlier_messages_in_this_conversation": [text for text in earlier if isinstance(text, str) and text.strip()],
            "papers_sent_with_it": papers, "new_message": message}


def way(model, message, *, earlier=(), papers=0):
    """How a message sent step by step asks to be worked (D287): {"how": "steps" | "end_to_end" | "specific", "said": code's words
    with the model's reading after them, marked where it may be shown at all ("" for steps)}. Asked once more, told why, where the
    first answer cannot be admitted; step by step where it still cannot. A failure of the model raises, for the caller to work the
    message step by step."""
    from nm.shared.model_port import Prompt, Tier, canonical_schema_data

    given = way_material(message, earlier=earlier, papers=papers)
    asked = dict(given)
    for _ in range(2):
        user = json.dumps(asked, ensure_ascii=False)
        receipt = model.structured(Prompt(system=WAY_PROMPT, user=user, operation=WAY_OPERATION,
                                          effort=reasoning.effort("message_way")),
                                   WAY_SCHEMA, Tier.ROUTINE, max_tokens=reasoning.room(model, Tier.ROUTINE, WAY_PROMPT, user,
                                                                                       json.dumps(WAY_SCHEMA)))
        data = canonical_schema_data(receipt.data, WAY_SCHEMA) if receipt.usable and receipt.data is not None else None
        how = data.get("way") if isinstance(data, dict) else None
        if how == "steps":
            return {"how": "steps", "said": ""}
        if how in WAY_SAID:
            return {"how": how, "said": shown_words.said(WAY_SAID[how], data.get("said"))}
        log.info("How the message asks to be worked was not admitted")
        asked = {**given, "your_last_answer": data, "why_it_cannot_be_taken": "way must be one of: " + ", ".join(WAYS)}
    return {"how": "steps", "said": ""}


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
