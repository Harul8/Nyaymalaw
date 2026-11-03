"""NM asks the advocate in the middle of a turn, in a window, when only their answer can settle something that changes the work
(plan AN.37, D37-D40 and D44; owner, 3 Nov 2026: "whenever NM needs a clarification in the middle of a conversation, it should ask
a question to the user as a pop up with MCQs, radial buttons, multicheck or optional free text -- same as Claude").

WHAT A QUESTION IS. One to four in a window. Each has a short heading, the question, one line on what depends on the answer, two to
four choices (one, or several ticked), the default NM goes on with where it is not answered, and what of the answer waits for it.
The advocate may always answer in their own words instead. A question that changes nothing is never built: it must say what
depends on it (the rule of the declared gate G-GAP).

WHO DECIDES. The model proposes questions (37d); code decides whether one is shown (admit): well-formed, saying what depends on it,
not asked before in the conversation, no link, never asking for a password, a code or a card. Code also checks every answer
against its choices (answer).

WAITING (D39). Work that does not depend on the answer goes on. Work that does waits WAIT seconds; then the default is applied and
the work moves on. The window stays open OPEN seconds from when it was asked, and an answer given in that time is taken: while the
turn runs, what depended on a default the answer differs from is redone once (D44); once the turn has finished, the page sends the
answer as the next message.

Nothing here is model content of its own: the questions are the model's, the answers the advocate's, and both are sealed with the
conversation (conversation.hold_asking) and saved with the turn.
"""
from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone

#: How long the work that depends on an answer waits for it before the default is applied, and how long the window stays open
#: (owner, 3 Nov 2026: "after a 2 min break, NM should assume defaults and move on, however, let the questions stay on for 10
#: mins").
WAIT = 120
OPEN = 600
MOST_QUESTIONS = 4
CHOICES = (2, 4)
#: The lengths a question's parts may have, in characters.
LONGEST = {"header": 40, "question": 500, "why": 300, "label": 120, "description": 300, "other": 2000}
_LINK = re.compile(r"https?://|www\.", re.I)
#: What NM never asks an advocate for, whatever a document it read may say.
_SECRET = re.compile(r"\b(pass(word|code)|one[- ]time (code|password)|otp|pin( number)?|cvv|card number|verification code|"
                     r"login details|sign[- ]in details)\b", re.I)
#: How an answer came to stand: given within the wait, given after the default was applied, or the default, never answered.
HOW = ("answered", "late", "assumed")


class Refused(ValueError):
    """An answer code cannot take: why, in plain words."""


def _text(value, limit, *, empty=False):
    return isinstance(value, str) and (empty or value.strip()) and len(value) <= limit


def _key(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def admit(proposed, *, asked_before=(), disputes=()):
    """The questions code lets the window show, each given its ID (q1, q2...) and who asked; and why each other one was
    refused. proposed: the model's (or code's) questions; asked_before: the questions already asked in this conversation, by
    their words; disputes: the IDs a question may say depend on it."""
    admitted, refused, seen = [], [], {_key(text) for text in asked_before}
    for number, item in enumerate(proposed if isinstance(proposed, list) else [], 1):
        why = _why_refused(item, seen, set(disputes))
        if why:
            refused.append({"position": number, "why": why})
            continue
        if len(admitted) == MOST_QUESTIONS:
            refused.append({"position": number, "why": f"a window asks at most {MOST_QUESTIONS} questions"})
            continue
        seen.add(_key(item["question"]))
        admitted.append({"id": f"q{len(admitted) + 1}", "header": item["header"].strip(), "question": item["question"].strip(),
                         "why": item["why"].strip(),
                         "choices": [{"label": c["label"].strip(), "description": c.get("description", "").strip()}
                                     for c in item["choices"]],
                         "multiple": item["multiple"], "default": [label.strip() for label in item["default"]],
                         "depends": list(dict.fromkeys(item.get("depends") or [])),
                         "asked_by": item.get("asked_by", "model")})
    return admitted, refused


def _why_refused(item, seen, disputes):
    if not isinstance(item, dict):
        return "not a question"
    for field in ("header", "question", "why"):
        if not _text(item.get(field), LONGEST[field]):
            return f"its {field} is missing or too long"
    choices = item.get("choices")
    if not isinstance(choices, list) or not CHOICES[0] <= len(choices) <= CHOICES[1]:
        return f"it needs {CHOICES[0]} to {CHOICES[1]} choices"
    labels = []
    for choice in choices:
        if not isinstance(choice, dict) or not _text(choice.get("label"), LONGEST["label"]) or not _text(
                choice.get("description", ""), LONGEST["description"], empty=True):
            return "a choice is missing its label or is too long"
        labels.append(choice["label"].strip())
    if len({_key(label) for label in labels}) != len(labels):
        return "two of its choices are the same"
    if type(item.get("multiple")) is not bool:
        return "it does not say whether several choices may be ticked"
    default = item.get("default")
    if (not isinstance(default, list) or not default or any(not isinstance(label, str) or label.strip() not in labels
                                                             for label in default)
            or (not item["multiple"] and len(default) != 1)):
        return "its default is not one of its choices"
    depends = item.get("depends") or []
    if not isinstance(depends, list) or any(dispute not in disputes for dispute in depends):
        return "it names something it depends on that this answer does not have"
    words = " ".join([item["header"], item["question"], item["why"], *labels,
                      *(choice.get("description", "") for choice in choices)])
    if _LINK.search(words):
        return "it carries a link"
    if _SECRET.search(words):
        return "it asks for a password, a code or a card"
    if _key(item["question"]) in seen:
        return "it was asked before in this conversation"
    return None


def answer(question, given):
    """One question's answer as code takes it: {"chosen": labels, "other": words}, checked against its choices. Refused, with
    why, where it is not one of them or says nothing."""
    if not isinstance(given, dict):
        raise Refused("An answer is a choice, or your own words.")
    chosen, other = given.get("chosen") or [], given.get("other") or ""
    labels = [choice["label"] for choice in question["choices"]]
    if not isinstance(chosen, list) or any(label not in labels for label in chosen) or len(set(chosen)) != len(chosen):
        raise Refused("Choose from the choices offered.")
    if not question["multiple"] and len(chosen) > 1:
        raise Refused("Choose one.")
    if not isinstance(other, str) or len(other) > LONGEST["other"]:
        raise Refused(f"Your own words can be at most {LONGEST['other']} characters.")
    if not chosen and not other.strip():
        raise Refused("Choose an answer or write your own.")
    return {"chosen": list(chosen), "other": other.strip()}


def said(question, settled):
    """An answer in words: the choices, then the advocate's own words."""
    return "; ".join([*settled["chosen"], *([settled["other"]] if settled["other"] else [])])


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Asking:
    """One turn's window: its questions, the answers taken and how each stands. hold(state) seals the state beside the
    conversation each time it changes; report(stage) tells the progress. Thread-safe: the turn waits on it while the page's
    answer arrives on another thread."""

    def __init__(self, questions, *, hold=lambda state: None, report=lambda stage, **detail: None, clock=time.monotonic,
                 wait=None, open_for=None):
        self.questions = deepcopy(questions)
        self._hold, self._report, self._clock = hold, report, clock
        self._wait, self._open_for = WAIT if wait is None else wait, OPEN if open_for is None else open_for
        self._lock, self._answered = threading.Lock(), threading.Event()
        self._answers, self.version, self._started, self._applied = {}, 0, None, False
        #: The version at which each answer that came after the defaults changed one (D44).
        self._changed = {}

    def state(self):
        """What is sealed and saved: the questions, each answer and how it stands."""
        with self._lock:
            return {"questions": deepcopy(self.questions), "answers": deepcopy(list(self._answers.values()))}

    def open(self):
        """Whether an answer can still be taken."""
        with self._lock:
            return self._started is not None and self._clock() - self._started <= self._open_for

    def ask(self, given=None):
        """Show the window, and wait up to WAIT seconds for its answers. Returns the answers as they then stand: those given,
        and for each question not answered its default, as assumed. The window stays open after. given: answers the advocate
        gave this same message's window before (a retry, D40), taken first."""
        with self._lock:
            self._started = self._clock()
        if given:
            self.receive(given, hold=False)
        self._hold(self.state())
        self._report("waiting_for_answer")
        self._answered.wait(self._wait)
        with self._lock:
            self._applied = True
            for question in self.questions:
                self._answers.setdefault(question["id"], {"id": question["id"], "chosen": list(question["default"]),
                                                          "other": "", "how": "assumed", "at": _now()})
            self.version += 1
        self._hold(self.state())
        return self.answers()

    def answers(self):
        with self._lock:
            return deepcopy(self._answers)

    def view(self):
        """What the page shows of the window: the questions, the answers taken, and whether the defaults now stand."""
        with self._lock:
            return {"questions": deepcopy(self.questions), "answers": deepcopy(list(self._answers.values())),
                    "defaults_applied": self._applied}

    def receive(self, given, *, hold=True):
        """The advocate's answers from the window, by question ID. Returns "taken", or "closed" where the window has closed;
        raises Refused for an answer code cannot take (nothing is kept from it)."""
        if not isinstance(given, dict) or not given:
            raise Refused("Answer at least one question.")
        known = {question["id"]: question for question in self.questions}
        if any(identity not in known for identity in given):
            raise Refused("An answer names a question this window does not ask.")
        settled = {identity: answer(known[identity], value) for identity, value in given.items()}
        with self._lock:
            if self._started is None or self._clock() - self._started > self._open_for:
                return "closed"
            how = "late" if self._applied else "answered"
            changed = False
            for identity, value in settled.items():
                before = self._answers.get(identity)
                if before is not None and before["how"] in ("answered", "late"):
                    continue  # the first answer counts
                changed = changed or before is None or (before["chosen"], before["other"]) != (value["chosen"], value["other"])
                self._answers[identity] = {"id": identity, **value, "how": how, "at": _now()}
            if changed and self._applied:
                self.version += 1
                for identity in settled:
                    self._changed[identity] = self.version
            done = all(question["id"] in self._answers for question in self.questions)
        if hold:
            self._hold(self.state())
        if done:
            self._answered.set()
        return "taken"

    def changed_since(self, version):
        """The questions whose answer, taken since version, differs from the default the work then went on with (D44)."""
        with self._lock:
            return {identity for identity, at in self._changed.items() if at > version}


def context_answers(questions, answers):
    """The answers as the writer, the review and the case read them in the turn's context: each question in its words and the
    answer as it stands - the advocate's, or the default NM went on with."""
    by_id = {entry["id"]: entry for entry in answers}
    out = []
    for question in questions:
        settled = by_id.get(question["id"])
        if settled is None:
            continue
        out.append({"question": question["question"], "answer": said(question, settled),
                    "given_by": "NM, as an assumption: the advocate did not answer" if settled["how"] == "assumed"
                    else "the advocate"})
    return out


def check_asked(asked):
    """A saved turn's questions and answers, checked for their shape; ValueError where they are not."""
    if not isinstance(asked, dict) or set(asked) != {"questions", "answers"}:
        raise ValueError("asked")
    questions, answers = asked["questions"], asked["answers"]
    if not isinstance(questions, list) or not 1 <= len(questions) <= MOST_QUESTIONS:
        raise ValueError("asked questions")
    ids = set()
    for question in questions:
        if (not isinstance(question, dict) or not isinstance(question.get("id"), str) or question["id"] in ids
                or not isinstance(question.get("question"), str) or not isinstance(question.get("choices"), list)):
            raise ValueError("asked question")
        ids.add(question["id"])
    if not isinstance(answers, list):
        raise ValueError("asked answers")
    for entry in answers:
        if (not isinstance(entry, dict) or entry.get("id") not in ids or entry.get("how") not in HOW
                or not isinstance(entry.get("chosen"), list) or not isinstance(entry.get("other"), str)):
            raise ValueError("asked answer")
    return asked


def conversation_rows(turn_id, asked):
    """An earlier turn's questions and answers as later turns read them in the conversation: an answer the advocate gave, as
    their own words; a default NM went on with, as NM's."""
    by_id = {entry["id"]: entry for entry in asked["answers"]}
    rows = []
    for question in asked["questions"]:
        settled = by_id.get(question["id"])
        if settled is None:
            continue
        mine = settled["how"] != "assumed"
        text = (f"NM asked: {question['question']}\n" + (f"My answer: {said(question, settled)}" if mine else
                                                         f"No answer came; NM went on assuming: {said(question, settled)}"))
        rows.append({"source_id": f"{turn_id}:{question['id']}", "turn_id": turn_id,
                     "speaker": "advocate" if mine else "nm",
                     "record_role": "original_account" if mine else "nm_interpretation", "text": text})
    return rows


# --- what the model would ask (plan AN.37, piece 37d) ------------------------------------------------------------------------

OPERATION = "core_questions"
_STRING = {"type": "string"}


def _object(fields):
    return {"type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}


CHOICE = _object({"label": _STRING, "description": _STRING})
QUESTION = _object({"header": _STRING, "question": _STRING, "why": _STRING, "choices": {"type": "array", "items": CHOICE},
                    "multiple": {"type": "boolean"}, "default": {"type": "array", "items": _STRING},
                    "depends": {"type": "array", "items": _STRING}})
SCHEMA = _object({"questions": {"type": "array", "items": QUESTION}})

PROPOSE = """Message: You receive an advocate's own messages to us about a client's matter, and our understanding of it as our research has set it out: each dispute with its ID, who is on each side, its legal questions, the rights at stake, the relief sought and the facts we found missing; and the questions already put to the advocate in this conversation. We are about to research the law and write our answer. Before we write it, we can put a few questions to the advocate in a short window; they answer by picking a choice or in their own words, and if they do not answer within two minutes we go on with the answer we name.

Purpose: Ask only what the advocate alone can settle and what would change the answer we write - for example whom they act for, where their messages do not say and the matter has parties on opposite sides; what they want from us, where their message could mean quite different work; which of several disputes to take up now, where their words suggest they want only some; a fact only they can know that changes the law that applies or a time limit, such as the date their client received a notice. Do not ask what their messages already settle, what our research can find, or a question of law that is ours to answer, and never ask again what was asked before. Most messages need no question: asking nothing is the usual outcome.

For each question: header, a few words naming it; question, in plain words; why, one line on what in our answer depends on it; choices, two to four likely answers, each with a label and, where it helps, a short description; multiple, whether more than one may be chosen; default, the choice we will go on with if they do not answer - the likeliest on what they have said; and depends, the IDs of the disputes whose part of the answer turns on it (none where the whole answer does).

Work in a loop: list what is unclear, check each item against their messages and our understanding, drop what is settled or would not change the answer, then give at most the few questions that truly matter.

Outcome: questions - possibly none."""


def propose(calls, context, interpreted, plan, asked_before):
    """The questions the model would put to the advocate once the plan is known (37d), for code to admit. None where the plan
    has no dispute to ask about; nothing where the step fails - a turn is never refused for want of a question. A usage limit or
    a refused permission stops the turn as anywhere else."""
    import json

    from nm.core_engine import reasoning
    from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data

    understanding = (plan.get("proposal") or {}).get("understanding") or {}
    disputes = [{key: deepcopy(dispute.get(key)) for key in ("id", "name", "between", "legal_questions", "rights_at_stake",
                                                             "relief_sought", "missing_facts")}
                for dispute in understanding.get("disputes") or []]
    if not disputes:
        return []
    said = [row["text"] for row in context.get("conversation", ()) if row.get("record_role") == "original_account"]
    latest = (context.get("latest") or {}).get("text")
    user = json.dumps({"advocate_messages": [*said, *([latest] if latest else [])], "disputes": disputes,
                       "asked_before": list(asked_before)}, ensure_ascii=False)
    try:
        receipt = calls.structured(Prompt(system=PROPOSE, user=user, operation=OPERATION, effort=reasoning.effort("questions")),
                                   SCHEMA, Tier.ROUTINE, max_tokens=reasoning.room(calls, Tier.ROUTINE, PROPOSE, user,
                                                                                    json.dumps(SCHEMA)))
        if not receipt.usable or receipt.data is None:
            return []
        return [{**item, "asked_by": "model"} for item in canonical_schema_data(receipt.data, SCHEMA)["questions"]]
    except UsageLimitReached:
        raise
    except (ModelError, SchemaViolation) as exc:
        import logging
        logging.getLogger(__name__).warning("No questions were proposed: %s", type(exc).__name__)
        return []
