"""Owned conversation context and atomic receipts; no model or legal decisions.

The existing sealed store owns persistence. This version owns the exact transcript,
its chain and replay, independently of future prompt or renderer implementations.
Stage results passed to commit_turn must already have passed their admission owner.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from nm.core_engine import questions, reasoning, steps as stepwise
from nm.core_engine.documents import checked_material
from nm.shared.model_config import DEFAULT_TURN_MODEL, TURN_CHOICES
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

CONTRACT = "core_conversation_v1"
HEADER = "core_conversation"
#: What a turn has shown of its answer while it works, sealed with the conversation as each
#: part passes (owner decision P27, 19 Oct 2026: each section is saved when it is shown).
#: The turn's commit replaces it in the same write; a turn that stopped after showing part
#: of its answer is saved later with what it showed (turn.recover). It is never a turn of
#: the conversation itself; base_version is the conversation's version before the turn first
#: saved what it showed, which the advocate's page still knows.
SHOWN = "core_shown"
_SHOWN_FIELDS = {"turn_id", "request", "message", "documents", "activity", "elements", "metrics", "at",
                 "base_version"}
#: From plan AN.41 (D66-D67, 5 Nov 2026) the same record is the turn being worked on, written when Send is pressed - its message
#: and files - before any AI work, so that the conversation is in the history from that moment; each step's result is kept in it
#: as the step finishes (STEPS), and why it stopped where it stopped part-way (D69). Its activity is never kept beside its steps:
#: it is derived from them (turn.activity_of), so nothing is saved twice. A record of the earlier form is read as it was saved.
_SENT_FIELDS = (_SHOWN_FIELDS - {"activity"}) | {"steps", "stopped", "steers"}
#: From plan AN.48 (48a2, 9 Nov 2026) a matter worked step by step also keeps its go-ahead (steps.valid): which steps the run may
#: take, the step's number and, where it waits for the advocate, after which step. A record without it is read as before.
_STEPPED_FIELDS = _SENT_FIELDS | {"go"}
#: Each step's result, as it finished: the understanding of the matter and the research plan ({"interpretation", "plan"}), the time
#: limits, each dispute's research by its id, each dispute's case by the index of its section, and what the answer has shown - its
#: sections done, the check across them and the overview (the answering's own state). None, or empty, until the step finishes.
STEPS = ("understood", "limits", "parts", "cases", "answered")
#: Why a turn stopped part-way (D69), by code's own name for it; turn.STOPS owns the words said for each.
_STOP_CODE = re.compile(r"[a-z][a-z_]{0,40}\Z")
#: What a turn has asked the advocate while it works (plan AN.37, D37-D40), sealed with the conversation as it is asked and as
#: each answer is taken: the turn, and its questions and answers (questions.Asking.state). Read by the page; a retry of the same
#: message reuses it; the turn's commit replaces it, the turn keeping it as "asked". Never a turn of the conversation itself.
ASKING = "core_asking"


class ConversationRefused(Exception):
    def __init__(self, why, *, status=409, code="history_unavailable",
                 committed="not_committed", retryable=False):
        super().__init__(why)
        self.why, self.status, self.code = why, status, code
        self.committed, self.retryable = committed, retryable


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def chat_matter_id(advocate_id, chat_id):
    return "chat_" + digest([advocate_id, chat_id])


def _nonempty(value):
    return type(value) is str and bool(value.strip())


def _request(advocate_id, chat_id, turn_id, message, documents, choice=()):
    """A turn's request; the documents sent with it are named by their exact references; and, from plan AN.33 (D23), the model and
    the effort the advocate chose for it where they are not the defaults (choice: (name, value) pairs), so that a request with the
    defaults is what it was before."""
    request = {"advocate_id": advocate_id, "chat_id": chat_id, "turn_id": turn_id, "message": message}
    if documents:
        request["document_refs"] = [document["document_ref"] for document in documents]
    request.update(dict(choice))
    return request


#: What a saved request may say the advocate chose for its turn (plan AN.33, D23): a model or an effort other than the default.
_CHOSEN = {"model": frozenset(model for model, _, _ in TURN_CHOICES) - {DEFAULT_TURN_MODEL},
           "effort": frozenset(reasoning.CHOICES) - {reasoning.DEFAULT_CHOICE}}


def _choice_of(request):
    """What a saved request says the advocate chose for its turn, as (name, value) pairs - each one the server offers and not the
    default - or ValueError."""
    choice = tuple((name, request[name]) for name in _CHOSEN if name in request)
    if any(value not in _CHOSEN[name] for name, value in choice):
        raise ValueError("conversation request choice")
    return choice


def document_sources(turn_id, documents):
    """Each read page of the documents sent with a turn, as material the advocate supplied:
    what the document says, not the advocate's own words (owner decisions, 15 Oct 2026)."""
    rows = []
    for index, document in enumerate(documents, 1):
        for page in document["pages"]:
            about = {"name": document["name"], "page": page["number"], "read_by": page["read_by"]}
            about.update({key: page[key] for key in ("legible", "note") if key in page})
            if document.get("recording"):
                about["recording"] = True
            rows.append({"source_id": f"{turn_id}:d{index}p{page['number']}", "turn_id": turn_id,
                         "speaker": "document", "record_role": "supplied_document",
                         "text": page["text"], "document": about})
    return rows


def _unread_pages(turn_id, documents):
    return [{"turn_id": turn_id, "name": document["name"], "page": page["number"], "reason": page["reason"],
             **({"recording": True} if document.get("recording") else {})}
            for document in documents for page in document["unread"]]


def checked_rows(matter, advocate_id, *, copied=True):
    """The conversation's turns, each receipt and the digest chain checked. copied=False
    (P35, 21 Oct 2026) returns the matter's own turns, for a caller that only reads them or
    only wants them checked: copying a long conversation took longer than checking it."""
    if matter.advocate_id != advocate_id:
        raise ConversationRefused("Conversation not available.", status=404)
    header = matter.intake_answers.get(HEADER)
    if not isinstance(header, dict) or header.get("contract") != CONTRACT:
        raise ConversationRefused(
            "This historical conversation is preserved but cannot be continued by this engine.",
            code="historical_conversation", committed="previously_committed")
    previous = None
    last_version = 0
    try:
        if (not _nonempty(header["chat_id"])
                or chat_matter_id(advocate_id, header["chat_id"]) != matter.id
                or type(header["turn_count"]) is not int
                or header["turn_count"] != len(matter.brain_chat)):
            raise ValueError("conversation header")
        for sequence, row in enumerate(matter.brain_chat, 1):
            body = {k: v for k, v in row.items() if k != "digest"}
            request = row["request"]
            response = row["response"]
            documents = checked_material(row["documents"]) if "documents" in row else ()
            if "asked" in row:
                questions.check_asked(row["asked"])
            if "steers" in row and (not row["steers"] or not _steers_valid(row["steers"])):
                raise ValueError("conversation steers")
            if (row["contract"] != CONTRACT or type(row["sequence"]) is not int
                    or row["sequence"] != sequence
                    or row["previous"] != previous or row["digest"] != digest(body)
                    or row["matter_id"] != matter.id or row["advocate_id"] != advocate_id
                    or row["chat_id"] != header["chat_id"]
                    or request != _request(advocate_id, header["chat_id"], row["turn_id"],
                                           row["message"], documents, _choice_of(request))
                    or not _nonempty(row["message"]) or not _nonempty(row["turn_id"])
                    or type(row["state_version"]) is not int
                    or not last_version < row["state_version"] <= matter.version
                    or response["turn_id"] != row["turn_id"]
                    or response["chat_id"] != header["chat_id"]
                    or response["matter_id"] is not None
                    or response["matter_version"] != row["state_version"]
                    or response["committed"] != "committed"
                    or response["input_admitted"] is not True
                    or response["replayed"] is not False
                    or type(response["elements"]) is not list
                    or any(type(e) is not dict or type(e.get("text")) is not str
                           for e in response["elements"])
                    or response.get("service_status") is not None
                    and type(response["service_status"]) is not str
                    or type(row["records"]) is not dict or type(row["work"]) is not list
                    or type(row["activities"]) is not dict):
                raise ValueError("conversation receipt")
            previous, last_version = row["digest"], row["state_version"]
        if header["tail_digest"] != previous:
            raise ValueError("conversation tail")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConversationRefused(
            "The saved conversation could not be read reliably. Its records are unchanged.",
            committed="previously_committed") from exc
    return deepcopy(matter.brain_chat) if copied else list(matter.brain_chat)


@dataclass(frozen=True)
class TurnContext:
    matter: Matter
    chat_id: str
    turn_id: str
    message: str
    rows: tuple[dict, ...]
    replay: dict | None = None
    #: The documents sent with this message, page by page (owner decisions, 15 Oct 2026).
    documents: tuple[dict, ...] = ()
    #: What the advocate chose for this turn that is not the default - ("model", ...), ("effort", ...) - (plan AN.33, D23).
    choice: tuple[tuple[str, str], ...] = ()
    #: What the turn asked the advocate and the answers as they stand (plan AN.37): questions.Asking.state(), or None.
    asked: dict | None = None
    #: What the advocate steered the answer with while it was worked on (plan AN.42, D79), in the order it came.
    steers: tuple[dict, ...] = ()

    @property
    def request(self):
        return _request(self.matter.advocate_id, self.chat_id, self.turn_id, self.message, self.documents, self.choice)

    def payload(self):
        conversation, pages, unread = [], [], []
        for row in self.rows:
            steered = row.get("steers", ())
            pages += document_sources(row["turn_id"], _with_steered(row.get("documents", ()), steered))
            unread += _unread_pages(row["turn_id"], _with_steered(row.get("documents", ()), steered))
            conversation.append({"source_id": row["turn_id"] + ":advocate",
                                 "turn_id": row["turn_id"], "speaker": "advocate",
                                 "record_role": "original_account", "text": said(row["message"], steered)})
            response = row["response"]
            text = "\n\n".join(e["text"] for e in response["elements"])
            conversation.append({"source_id": row["turn_id"] + ":nm",
                                 "turn_id": row["turn_id"], "speaker": "nm",
                                 "record_role": "nm_interpretation", "text": text})
            if response.get("service_status"):
                conversation.append({"source_id": row["turn_id"] + ":service",
                                     "turn_id": row["turn_id"], "speaker": "service",
                                     "record_role": "service_status",
                                     "text": response["service_status"]})
            # Plan AN.37: what an earlier turn asked, and the answers - the advocate's own words, or the default NM went on with.
            if "asked" in row:
                conversation.extend(questions.conversation_rows(row["turn_id"], row["asked"]))
        latest = {"source_id": self.turn_id + ":advocate", "turn_id": self.turn_id,
                  "speaker": "advocate", "record_role": "original_account", "text": said(self.message, self.steers)}
        pages += document_sources(self.turn_id, _with_steered(self.documents, self.steers))
        unread += _unread_pages(self.turn_id, _with_steered(self.documents, self.steers))
        context = {"position": "follow_up" if self.rows else "first", "latest": latest,
                   "conversation": conversation,
                   "current_records": deepcopy(self.rows[-1]["records"]) if self.rows else {},
                   "saved_work": deepcopy(self.rows[-1]["work"]) if self.rows else []}
        # Only a conversation with documents carries these, so every earlier context,
        # and the saved answers checked against it, stays exactly as it was.
        if pages or unread:
            context["documents"] = pages
            context["unread_document_pages"] = unread
        # Only a turn that asked carries what it asked (plan AN.37), so every other context stays exactly as it was. The research
        # and the understanding were made before the asking and read none of it; the writing, the review and the case read it.
        if self.asked is not None:
            context["answers"] = questions.context_answers(self.asked["questions"], self.asked["answers"])
        return context


def said(message, steers=()):
    """The advocate's words a turn answers: its message and, from plan AN.42 (D79), what steered it while it was worked on, each
    after a blank line, in the order it came. A turn never steered is answered on its message alone, exactly as before."""
    return "\n\n".join([message, *(steer["text"] for steer in steers)])


def _with_steered(documents, steers):
    """A turn's documents and, after them, those that came with what steered it (D79): numbered on from the message's own."""
    return [*documents, *(document for steer in steers for document in steer["documents"])]


def stored_chat(advocate_id, chat_id, turn_id):
    """The conversation a turn belongs to: the one named, or the one its first message opens."""
    return chat_id or "new_" + digest([advocate_id, turn_id])[:32]


def committed_version(rows):
    """The conversation's version as its last committed turn left it."""
    return rows[-1]["state_version"] if rows else 0


def shown_of(matter, *, copied=True):
    """What a turn not yet committed has shown of its answer, as it was saved, or None. From plan AN.41 the turn being worked on:
    its message and files from Send, its steps as they finished (STEPS) and why it stopped, if it did (sent). copied=False returns
    the record itself, for a caller that only reads it."""
    held = (matter.intake_answers or {}).get(SHOWN) if matter is not None else None
    if held is None:
        return None
    if (not isinstance(held, dict) or set(held) not in (_SHOWN_FIELDS, _SENT_FIELDS, _STEPPED_FIELDS)
            or not _nonempty(held["turn_id"])
            or not isinstance(held["request"], dict) or not isinstance(held["elements"], list)
            or type(held["base_version"]) is not int or held["base_version"] < 0
            or any(type(e) is not dict or type(e.get("text")) is not str for e in held["elements"])
            or "steps" in held and not _sent_valid(held)):
        raise ValueError("What a turn has shown could not be read reliably")
    return deepcopy(held) if copied else held


def _sent_valid(held):
    """The form of a turn being worked on (AN.41): each step present, empty until it finishes, and why it stopped by its code."""
    steps, stopped = held["steps"], held["stopped"]
    return (isinstance(steps, dict) and tuple(steps) == STEPS
            and (steps["understood"] is None or isinstance(steps["understood"], dict)
                 and set(steps["understood"]) == {"interpretation", "plan"} and isinstance(steps["understood"]["plan"], dict))
            and (steps["limits"] is None or isinstance(steps["limits"], dict))
            and isinstance(steps["parts"], dict) and all(isinstance(part, dict) for part in steps["parts"].values())
            and isinstance(steps["cases"], dict) and all(key.isdigit() for key in steps["cases"])
            and (steps["answered"] is None or isinstance(steps["answered"], dict)
                 and set(steps["answered"]) == {"sections", "cross_check", "overview"})
            and (steps["understood"] is not None or not steps["parts"] and steps["answered"] is None)
            and (stopped is None or isinstance(stopped, dict) and set(stopped) == {"code", "at"}
                 and isinstance(stopped["code"], str) and _STOP_CODE.match(stopped["code"]) is not None
                 and _nonempty(stopped["at"]))
            and _steers_valid(held["steers"])
            and ("go" not in held or stepwise.valid(held["go"])))


def _steers_valid(steers):
    """What the advocate steered the answer with while it was worked on (plan AN.42, D79): each message's words, the documents
    that came with it as they were read, and when it came."""
    try:
        return isinstance(steers, list) and all(
            isinstance(steer, dict) and set(steer) == {"text", "documents", "at"} and _nonempty(steer["text"])
            and _nonempty(steer["at"]) and isinstance(steer["documents"], list)
            and (not steer["documents"] or checked_material(steer["documents"]) is not None) for steer in steers)
    except (KeyError, TypeError, ValueError):
        return False


def sent(turn_id, request, message, documents, base_version, *, at, steps=None, steers=(), go=None):
    """A turn being worked on as it is saved when Send is pressed (plan AN.41, D66): its message and files, nothing done yet - or,
    where the same message continues where it stopped, the steps it had finished (D70) and what steered it (D79). go (plan AN.48,
    48a2): the go-ahead of a matter worked step by step; None (end to end) keeps the record exactly as before."""
    return {"turn_id": turn_id, "request": deepcopy(request), "message": message, "documents": deepcopy(list(documents)),
            "elements": [], "metrics": {}, "at": at, "base_version": base_version,
            "steps": deepcopy(steps) if steps is not None else {name: {} if name in ("parts", "cases") else None for name in STEPS},
            "stopped": None, "steers": deepcopy(list(steers)), **({"go": deepcopy(go)} if go is not None else {})}


def hold_shown(store, context, held, *, private=False):
    """Save what this turn has shown so far beside its conversation, sealed with it, before
    the turn is committed (P27). The conversation's turns are unchanged. Returns the turn's
    context at the version written. private: held is the caller's own copy, which nothing changes afterwards (plan AN.41: the
    record of a turn being worked on is written often, and copying it each time is work the write does not need)."""
    metadata = {**context.matter.intake_answers, SHOWN: held if private else deepcopy(held)}
    metadata.setdefault(HEADER, {"contract": CONTRACT, "chat_id": context.chat_id, "turn_count": 0,
                                 "tail_digest": None})
    candidate = replace(context.matter, intake_answers=metadata, version=context.matter.version + 1)
    # The turns were checked when the turn opened, and this write leaves them as they were: only a conversation this write begins
    # has its header checked here (plan AN.41: a long conversation's turns took about a second to check, on every write).
    if context.matter.version == 0:
        checked_rows(candidate, context.matter.advocate_id, copied=False)
    shown_of(candidate, copied=False)
    return replace(context, matter=_written(store, candidate, context.matter.version))


def _written(store, candidate, expected_version):
    """A write beside the conversation, confirmed: where its acknowledgement was lost, the
    store is read back and the write counts only if exactly it is there."""
    try:
        return store.commit(candidate, expected_version=expected_version)
    except (OSError, StaleWrite):
        try:
            current = store.load(candidate.id)
        except (OSError, ValueError):
            current = None
        if (current is None or current.version != candidate.version
                or digest(current.intake_answers) != digest(candidate.intake_answers)
                or current.brain_chat != candidate.brain_chat):
            raise
        return current


def asking_of(matter, turn_id=None):
    """What a turn not yet committed has asked, as it was sealed - {"turn_id", "state"} - or None; only that turn's where
    turn_id is given. ValueError where it cannot be read reliably."""
    held = (matter.intake_answers or {}).get(ASKING) if matter is not None else None
    if held is None:
        return None
    if not isinstance(held, dict) or set(held) != {"turn_id", "state"} or not _nonempty(held["turn_id"]):
        raise ValueError("What a turn has asked could not be read reliably")
    questions.check_asked(held["state"])
    if turn_id is not None and held["turn_id"] != turn_id:
        return None
    return deepcopy(held)


def hold_asking(store, context, state):
    """Seal what this turn has asked, and the answers as they stand, beside its conversation (plan AN.37, D40). The
    conversation's turns are unchanged. Returns the turn's context at the version written."""
    questions.check_asked(state)
    metadata = {**context.matter.intake_answers, ASKING: {"turn_id": context.turn_id, "state": deepcopy(state)}}
    metadata.setdefault(HEADER, {"contract": CONTRACT, "chat_id": context.chat_id, "turn_count": 0,
                                 "tail_digest": None})
    candidate = replace(context.matter, intake_answers=metadata, version=context.matter.version + 1)
    checked_rows(candidate, context.matter.advocate_id, copied=False)
    return replace(context, matter=_written(store, candidate, context.matter.version))


#: What the advocate wrote while a turn was worked on, waiting to go as the next message (plan AN.42, D77): each message's words
#: and the documents attached to it, by reference and name. Kept with the conversation, so that a reload keeps it; a turn's commit
#: leaves it as it is (it waits for that turn), and the page empties it as it sends, edits or discards what waits.
QUEUED = "core_queued"
_QUEUED_MOST = 20


#: The conversation's title in the history (plan AN.43, D81-D82): the model's words as code admitted them (titles.admitted), and
#: whether they were written from an understanding of the matter - a title written before any matter was understood (a greeting)
#: is written again, once, when one is. Kept with the conversation, which a turn's commit leaves as it is.
TITLE = "core_title"


def title_of(matter):
    """The conversation's title, as saved - {"text", "from_matter"} - or None where it has none. ValueError where it cannot be read
    reliably."""
    from nm.core_engine import titles
    held = (matter.intake_answers or {}).get(TITLE) if matter is not None else None
    if held is None:
        return None
    if (not isinstance(held, dict) or set(held) != {"text", "from_matter"} or type(held["from_matter"]) is not bool
            or titles.admitted(held["text"])[0] != held["text"]):
        raise ValueError("The conversation's title could not be read reliably")
    return dict(held)


def hold_title(store, context, title):
    """Save the conversation's title beside it, on the versions of its turn being worked on (D82). Returns the turn's context at the
    version written."""
    metadata = {**context.matter.intake_answers, TITLE: dict(title)}
    candidate = replace(context.matter, intake_answers=metadata, version=context.matter.version + 1)
    title_of(candidate)
    return replace(context, matter=_written(store, candidate, context.matter.version))


def save_title(store, matter, title):
    """Save the title of a conversation no turn is being worked on now (D83: the conversations saved before, titled once by the
    operator's run). Returns the conversation as written."""
    metadata = {**(matter.intake_answers or {}), TITLE: dict(title)}
    candidate = replace(matter, intake_answers=metadata, version=matter.version + 1)
    title_of(candidate)
    return _written(store, candidate, matter.version)


def queued_of(matter):
    """What waits to go as the next message of the conversation, as it was saved: a list, empty where nothing waits. ValueError
    where it cannot be read reliably."""
    queued = (matter.intake_answers or {}).get(QUEUED, []) if matter is not None else []
    if (not isinstance(queued, list) or len(queued) > _QUEUED_MOST
            or any(not isinstance(item, dict) or set(item) != {"text", "documents"} or not _nonempty(item["text"])
                   or not isinstance(item["documents"], list)
                   or any(not isinstance(document, dict) or set(document) != {"document_ref", "name"}
                          or not _nonempty(document["document_ref"]) or not isinstance(document["name"], str)
                          for document in item["documents"])
                   for item in queued)):
        raise ValueError("What waits to be sent could not be read reliably")
    return deepcopy(queued)


def with_queued(matter, queued):
    """The conversation with what waits to be sent replaced (D77), one version on; checked as it is read. Nothing waiting leaves
    no key behind."""
    metadata = {key: value for key, value in (matter.intake_answers or {}).items() if key != QUEUED}
    if queued:
        metadata[QUEUED] = deepcopy(list(queued))
    candidate = replace(matter, intake_answers=metadata, version=matter.version + 1)
    queued_of(candidate)
    return candidate


def hold_queued(store, context, queued):
    """Save what waits to be sent beside a conversation whose turn is being worked on, on that turn's own versions (D77). Returns the
    turn's context at the version written."""
    return replace(context, matter=_written(store, with_queued(context.matter, queued), context.matter.version))


def save_queued(store, matter, queued):
    """Save what waits to be sent beside a conversation no turn is being worked on now (D77). Returns the conversation as written."""
    return _written(store, with_queued(matter, queued), matter.version)


def drop_asking(store, matter):
    """Withdraw what a turn asked that was never saved with it - its turn stopped before showing anything, and another message
    came (plan AN.37, D40). Returns the conversation as written, or as it was where nothing was asked."""
    if ASKING not in (matter.intake_answers or {}):
        return matter
    metadata = {key: value for key, value in matter.intake_answers.items() if key != ASKING}
    candidate = replace(matter, intake_answers=metadata, version=matter.version + 1)
    return _written(store, candidate, matter.version)


def drop_shown(store, context):
    """Withdraw what this turn has shown, and what it asked, where the turn is withheld whole (G-CORE) or was
    not answered at all. Returns the turn's context at the version written, or as it was
    where nothing was held."""
    if SHOWN not in context.matter.intake_answers and ASKING not in context.matter.intake_answers:
        return context
    metadata = {key: value for key, value in context.matter.intake_answers.items() if key not in (SHOWN, ASKING)}
    candidate = replace(context.matter, intake_answers=metadata, version=context.matter.version + 1)
    return replace(context, matter=_written(store, candidate, context.matter.version))


def open_turn(store, *, advocate_id, message, turn_id, chat_id=None, matter_id=None,
              expected_version=None, documents=(), choice=()):
    if not all(_nonempty(v) for v in (advocate_id, message, turn_id)):
        raise ConversationRefused("A message and request identity are required.", status=422)
    if matter_id is not None:
        raise ConversationRefused("Reopen this conversation from My work before continuing.")
    if chat_id is not None and not _nonempty(chat_id):
        raise ConversationRefused("A valid conversation identity is required.", status=422)
    if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
        raise ConversationRefused("A valid conversation version is required.", status=422)
    identity = stored_chat(advocate_id, chat_id, turn_id)
    stored_id = chat_matter_id(advocate_id, identity)
    try:
        matter = store.load(stored_id)
    except (OSError, ValueError) as exc:
        raise ConversationRefused("The conversation could not be loaded reliably.") from exc
    if matter is None and chat_id is not None:
        raise ConversationRefused("The conversation could not be found. Reopen it before continuing.")
    rows = checked_rows(matter, advocate_id) if matter else ()
    matter = matter or Matter(id=stored_id, advocate_id=advocate_id,
                              title="Conversation", brain_ready=False)
    context = TurnContext(matter, identity, turn_id, message, rows,
                          documents=tuple(checked_material(list(documents))) if documents else (),
                          choice=tuple(choice))
    for row in rows:
        if row["turn_id"] == turn_id:
            if row["request"] != context.request:
                raise ConversationRefused("This request identity belongs to a different message.",
                                          code="request_conflict", committed="previously_committed")
            return replace(context, replay={**row["response"], "replayed": True})
    # What a turn has shown and saved beside the conversation (P27) does not change what the
    # advocate's page knew before it started.
    try:
        held = shown_of(matter) if rows or matter.version else None
    except ValueError:
        held = None
    if expected_version is not None and expected_version not in (
            matter.version, held["base_version"] if held else matter.version):
        raise ConversationRefused("The conversation changed. Reopen it before continuing.",
                                  code="stale_version")
    return context


def commit_turn(store, context, *, elements, activities, records=None, work=None,
                service_status=None, metrics=None, session_current=lambda: False):
    """Save already-admitted work and its exact public response in one CAS write."""
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
    if context.replay is not None:
        return deepcopy(context.replay)
    version = context.matter.version + 1
    response = {"turn_id": context.turn_id, "matter_id": None, "chat_id": context.chat_id,
                "route": "core_engine", "mode": "conversation", "mode_statement": "",
                "blocked": False, "blocked_reason": None, "elements": deepcopy(elements),
                "material": [], "material_coverage": {}, "briefing": {}, "board_changes": [],
                "composed": [], "continuation": {}, "metrics": deepcopy(metrics or {}),
                "replayed": False, "committed": "committed", "input_admitted": True,
                "matter_version": version, "at": datetime.now(timezone.utc).isoformat(),
                "service_status": service_status,
                # Plan AN.37: what NM asked while it worked on the message (below), or None - as the released answer says it.
                "questions_asked": None}
    previous = context.rows[-1] if context.rows else {}
    row = {"contract": CONTRACT, "sequence": len(context.rows) + 1,
           "previous": previous.get("digest"), "state_version": version,
           "turn_id": context.turn_id, "matter_id": context.matter.id,
           "advocate_id": context.matter.advocate_id, "chat_id": context.chat_id,
           "message": context.message, "request": context.request, "response": response,
           "activities": deepcopy(activities),
           "records": deepcopy(records if records is not None else previous.get("records", {})),
           "work": deepcopy(work if work is not None else previous.get("work", []))}
    if context.documents:
        row["documents"] = deepcopy(list(context.documents))
    if context.steers:
        row["steers"] = deepcopy(list(context.steers))
    if context.asked is not None:
        row["asked"] = questions.check_asked(deepcopy(context.asked))
        # The page shows what was asked, and how each answer came to stand, above the answer it shaped.
        response["questions_asked"] = deepcopy(row["asked"])
    row["digest"] = digest(row)
    # The turn's commit replaces what it showed and asked while it worked (P27; plan AN.37), in the same write.
    metadata = {**{key: value for key, value in context.matter.intake_answers.items() if key not in (SHOWN, ASKING)}, HEADER: {
        "contract": CONTRACT, "chat_id": context.chat_id,
        "turn_count": len(context.rows) + 1, "tail_digest": row["digest"]}}
    candidate = replace(context.matter, brain_chat=(*context.rows, row),
                        intake_answers=metadata, version=version)
    checked_rows(candidate, context.matter.advocate_id, copied=False)
    try:
        committed = store.commit(candidate, expected_version=context.matter.version)
    except (OSError, StaleWrite):
        try:
            committed = store.load(context.matter.id)
        except (OSError, ValueError):
            committed = None
    if committed is not None:
        for saved in checked_rows(committed, context.matter.advocate_id):
            if saved["turn_id"] == context.turn_id and saved["request"] == context.request:
                if not session_current():
                    raise ConversationRefused("Sign in again to reopen your saved conversation.",
                                              status=401, committed="committed")
                return deepcopy(saved["response"])
    raise ConversationRefused("The save could not be confirmed. Retry the same message safely.",
                              status=503, code="save_unconfirmed", committed="unconfirmed",
                              retryable=True)
