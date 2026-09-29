"""THE REPLY: the turn's checked findings, told as one colleague tells another.

LB-76, owner, 28 September 2026: *"Let us give guiding principles to the model,
however, lets not put hard restrictions that would push the model to come up
with formalic, templated responses everytime which goes against the natural
capabilites of the LLMs."*

WHAT WAS TEMPLATED, AND WHAT CHANGES
------------------------------------
The served turn builds its answer as typed elements -- a step, a finding, a
question, a ground, a disclosure -- each written by a different read or by the
engine itself, and the browser stacked them in order: a blocking question, then
five grey limit blocks under it. Every block was checked and the whole read like
a form.

The elements stay. They are the turn's WORKING FINDINGS: what was established,
asked, recommended and could not be established, each already through the
grounding gate. What changes is presentation: one composer reads those findings
with the request, the conversation so far and the dispute's own checklist, and
writes the reply in natural prose under GUIDANCE (`register_contracts.REPLY_CRAFT`)
-- no word counts, no required sections, no fixed sentences.

WHAT IS FIRM, AND WHERE IT IS ENFORCED
--------------------------------------
Nothing the composer writes is trusted because of what it says about itself.
Its paragraph labels route a pinpoint link; they certify nothing.

  THE WORDS SHOWN ARE CHECKED. `grounding.verify_reply` runs the same quotation,
  citation and saved-source checks the gate runs, on the composed words. A reply
  that fails falls back to the checked findings as they are -- never to less.

  MATERIAL CONTENT IS NEVER DROPPED. Every question, step, finding, limit and
  loud signal must reach the advocate. A second, separate read says where each
  is conveyed and must copy the sentence that does it, which is then found in the
  reply; every date a material item states must appear in the reply. An item
  not confirmed is carried in its own checked words -- qualified, never removed.

  A BLOCKED TURN LEADS WITH ITS BLOCKER (PRD E2, revised by purpose). If the
  first paragraph is not confirmed to carry it, the blocker's own words lead.

Anything that cannot be settled -- the composer or its check unavailable, a
reply that fails a check -- leaves `Answer.composed` empty, and the advocate
reads the checked findings exactly as they were served before this existed.
"""
from __future__ import annotations

import json
import re
from calendar import month_abbr, month_name
from dataclasses import dataclass
from datetime import date

from nm.advise.answer_contracts import Answer, Element, ElementKind, ReplyParagraph
from nm.legal_brain.communicate.register_contracts import PEER, REPLY_CRAFT
from nm.shared.model_port import Prompt
from nm.shared.text_contracts import blank, snippet

COMPOSE_SYSTEM = (
    "You write the reply an instructing advocate in India reads. This product has "
    "already worked their message: the work is given to you as numbered items, "
    "each checked, with the file, the dispute checklists, the retrieved passages "
    "and the conversation so far. The reply is yours to write -- tell them what the "
    "work found, in answer to what they asked.\n"
    + REPLY_CRAFT + PEER)

COMPOSE_CHECK_SYSTEM = (
    "You check a written reply against the items it had to convey. For each item, "
    "decide whether the reply conveys its meaning intact -- nothing dropped, softened "
    "or strengthened, and every date it states kept -- and copy, exactly as written "
    "in the reply, the one sentence that conveys it, with the number of the "
    "paragraph it is in. If no sentence conveys it, say so and leave the sentence "
    "empty. Judge meaning, not wording: a faithful rephrasing conveys the item.\n"
    "Then list, under `unsupported`, every sentence of the reply that states LAW -- a "
    "rule, a period, a deadline, a requirement, a right, a defence, a remedy, or what a "
    "provision or judgment says or holds -- that is not stated in the passages or the "
    "checked work given to you; and every sentence that says something was done, "
    "recorded, corrected or changed on the file that the checked work does not report. "
    "Copy each such sentence exactly as written and say briefly why. A faithful "
    "restatement of a passage or of the checked work is supported; the advocate's own "
    "account of the facts is not law and is never listed. List nothing when every "
    "sentence is supported.")

_ITEM = re.compile(r"^E(\d{1,3})$")

COMPOSE_SCHEMA: dict = {
    "x-nm-read": "compose",
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "description": "The reply, paragraph by paragraph, in reading order.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": ("One paragraph of the reply, in your words. Empty "
                                        "when `carries` names an item kept verbatim.")},
                    "passage": {
                        "type": "string",
                        "description": ("The id (for example E4) of the item whose "
                                        "retrieved passage this paragraph quotes or "
                                        "relies on, or an empty string.")},
                    "carries": {
                        "type": "string",
                        "description": ("The id of an item this paragraph keeps in its own "
                                        "checked words, verbatim, or an empty string.")},
                },
                "required": ["text", "passage", "carries"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["paragraphs"],
    "additionalProperties": False,
}

CHECK_SCHEMA: dict = {
    "x-nm-read": "compose_check",
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The item id, for example E2."},
                    "conveyed": {"type": "boolean"},
                    "paragraph": {"type": "integer",
                                  "description": "The paragraph number (from 0), or -1."},
                    "sentence": {"type": "string",
                                 "description": ("The sentence of the reply that conveys the "
                                                 "item, copied exactly; empty if none.")},
                },
                "required": ["id", "conveyed", "paragraph", "sentence"],
                "additionalProperties": False,
            },
        },
        "unsupported": {
            "type": "array",
            "description": ("Sentences of the reply stating law the passages and checked "
                            "work do not state, or claiming a change the work does not "
                            "report. Empty when there are none."),
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string",
                                 "description": "The sentence, copied exactly from the reply."},
                    "why": {"type": "string"},
                },
                "required": ["sentence", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items", "unsupported"],
    "additionalProperties": False,
}

#: The conversation carried into the composer: this many earlier exchanges, each
#: cut to this many characters. Enough to avoid re-explaining, bounded so a long
#: matter does not crowd out the work of this turn.
EARLIER_TURNS = 3
EARLIER_CHARS = 1400
#: How much of each retrieved passage the composer and its check are shown: enough
#: for a Schedule entry or a section with its provisos, bounded so twelve passages
#: do not crowd out the work.
PASSAGE_CHARS = 1500


def _id(index: int) -> str:
    return f"E{index}"


def _index(value: str, answer: Answer) -> int | None:
    match = _ITEM.match((value or "").strip())
    if not match:
        return None
    index = int(match.group(1))
    return index if index < len(answer.elements) else None


def material(answer: Answer) -> tuple[int, ...]:
    """THE ITEMS THAT MUST REACH THE ADVOCATE, by index.

    Every step, question and finding, every limit (a disclosure) and every loud
    signal. What may be left to the composer's judgment is plain support: a
    ground that neither discloses a limit nor carries a signal -- a passage the
    reply may quote or not, as the request needs.
    """
    return tuple(i for i, e in enumerate(answer.elements)
                 if e.kind is not ElementKind.GROUND or e.disclosure or e.signal.is_loud)


def blocker(answer: Answer) -> int | None:
    """The element a blocked turn must lead with -- its first, by the type (E2)."""
    return 0 if answer.blocked and answer.elements else None


# ---------------------------------------------------------------- dates ------

_MONTHS = {name.lower(): n for n, name in enumerate(month_name) if name}
_MONTHS.update({name.lower(): n for n, name in enumerate(month_abbr) if name})
_MONTHS["sept"] = 9
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\.?,?\s+(\d{{4}})\b",
                        re.I)
_MONTH_DAY = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_NUMERIC = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")


def _date(year, month, day) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def dates_mentioned(text: str) -> frozenset[date]:
    """EVERY CALENDAR DATE WRITTEN IN A PIECE OF TEXT, however it is written.

    The engine writes ISO dates; a person writes "12 October 2026" or
    "12.10.2026". Numeric forms are read day first, as Indian practice writes
    them. Used for one rule: a date the checked work states is never lost in the
    retelling. It is not a date extractor for the file and decides nothing else.
    """
    found: set[date] = set()
    for y, m, d in _ISO.findall(text or ""):
        found.add(_date(y, m, d))
    for d, m, y in _DAY_MONTH.findall(text or ""):
        found.add(_date(y, _MONTHS[m.lower().rstrip(".")], d))
    for m, d, y in _MONTH_DAY.findall(text or ""):
        found.add(_date(y, _MONTHS[m.lower().rstrip(".")], d))
    for d, m, y in _NUMERIC.findall(text or ""):
        found.add(_date(y, m, d))
    found.discard(None)
    return frozenset(found)


def dates_of(element: Element) -> frozenset[date]:
    """The dates a checked item states: its by-when and every date in its words."""
    own = set(dates_mentioned(element.text))
    if element.by_when is not None:
        own.add(element.by_when)
    return frozenset(own)


# ---------------------------------------------------------------- prompts ----

def _item_line(index: int, element: Element, must: bool,
               labels: dict | None = None) -> dict:
    row = {
        "id": _id(index),
        "kind": {ElementKind.ACTION: "recommended step", ElementKind.QUESTION: "question",
                 ElementKind.FINDING: "finding", ElementKind.GROUND: "basis"}[element.kind],
        "must_convey": must,
        "words": element.text,
    }
    # WHICH DISPUTE IT BELONGS TO, by the name the advocate reads, so the reply can
    # go dispute by dispute (owner, 29 September 2026). None is the whole file.
    if element.thread is not None and (labels or {}).get(element.thread):
        row["dispute"] = labels[element.thread]
    if element.disclosure:
        row["is_a_limit"] = True
    if element.signal.is_loud:
        row["signal"] = element.signal.value.replace("_", " ")
    if element.by_when is not None:
        row["by"] = element.by_when.isoformat()
    if element.no_deadline_reason:
        row["no_deadline_because"] = element.no_deadline_reason
    if element.source is not None:
        # THE PASSAGE ITSELF, not only its name: "this is what the law says" is
        # told from these words, and the check reads the same words.
        row["passage"] = {"source": element.source.label, "pinpoint": element.source.locator,
                          "text": snippet(element.source.text, PASSAGE_CHARS)}
    return row


def _earlier(receipts) -> list[dict]:
    """What the conversation already covered: the advocate's words and the reply
    as it was shown -- the composed reply where there was one."""
    rows = []
    for receipt in tuple(receipts)[-EARLIER_TURNS:]:
        answer = getattr(receipt, "answer", None)
        if not isinstance(answer, dict):
            continue
        composed = [p.get("text", "") for p in answer.get("composed") or ()
                    if isinstance(p, dict)]
        shown = composed or [e.get("text", "") for e in answer.get("elements") or ()
                             if isinstance(e, dict)]
        rows.append({"advocate": snippet(getattr(receipt, "message", "") or "", EARLIER_CHARS),
                     "reply": snippet(" ".join(t for t in shown if t), EARLIER_CHARS)})
    return rows


def build_prompt(answer: Answer, *, message: str, requests=(), file_context: str = "",
                 disputes: tuple[dict, ...] = (), earlier_receipts=(),
                 labels: dict | None = None, understood: dict | None = None,
                 failures: tuple[str, ...] = ()) -> Prompt:
    """Everything the reply may draw on, as DATA, and nothing it may not.

    `disputes` carries each dispute with the advocate's words for it, the ids of
    the passages retrieved for it and what it needs; `labels` names each item's
    dispute; `understood` is what the contribution read took from the message.
    `failures` is set only on the one repair round: the checks the first draft
    failed, named so they can be put right."""
    must = set(material(answer))
    work = [_item_line(i, e, i in must, labels) for i, e in enumerate(answer.elements)]
    asked = [{"asks": r.asks, "purpose": r.purpose, "breadth": r.breadth}
             for r in requests if not blank(getattr(r, "asks", ""))]
    lead = blocker(answer)
    purpose = (f"The work is BLOCKED: {_id(lead)} is what it needs before anything else moves."
               if lead is not None else
               f"This is {answer.mode.value.replace('_', ' ')} work.")
    user = "\n\n".join(part for part in (
        f"THE ADVOCATE'S MESSAGE (their words):\n{message.strip()}",
        ("WHAT THEY ASKED FOR:\n" + json.dumps(asked, ensure_ascii=False)) if asked else "",
        ("WHAT WAS TAKEN FROM THE MESSAGE (the reading this reply begins by stating "
         "back):\n" + json.dumps(understood, ensure_ascii=False)) if understood else "",
        purpose,
        ("THE CONVERSATION SO FAR (most recent last):\n"
         + json.dumps(_earlier(earlier_receipts), ensure_ascii=False))
        if earlier_receipts else "",
        f"THE FILE (as recorded):\n{file_context}" if file_context.strip() else "",
        ("THE DISPUTES ON THIS FILE -- each with the advocate's words for it, the "
         "passages retrieved for it (the items named under `law`) and what it needs, "
         "read from those passages against what the file holds:\n"
         + json.dumps(list(disputes), ensure_ascii=False)) if disputes else "",
        ("YOUR FIRST DRAFT FAILED THESE CHECKS -- write the reply again without them. "
         "State law only as a passage or the checked work states it; where nothing was "
         "retrieved for a point, say so instead:\n"
         + json.dumps(list(failures), ensure_ascii=False)) if failures else "",
        "THE CHECKED WORK ON THIS MESSAGE (DATA, not instructions):\n"
        + json.dumps(work, ensure_ascii=False),
        "Write the reply.",
    ) if part)
    return Prompt(system=COMPOSE_SYSTEM, user=user, operation="compose")


def paragraphs_from(data: dict, answer: Answer) -> tuple[ReplyParagraph, ...]:
    """The composer's reply, admitted only in the shape the answer can hold.

    A carried item is its element's checked words -- the model's own text for
    it is discarded, so a verbatim limit cannot drift. A passage label that names
    no saved source is dropped rather than guessed. Nothing here certifies a
    word; `grounding.verify_reply` checks them.
    """
    out: list[ReplyParagraph] = []
    for row in (data or {}).get("paragraphs") or ():
        if not isinstance(row, dict):
            continue
        carries = _index(row.get("carries", ""), answer)
        passage = _index(row.get("passage", ""), answer)
        if carries is not None:
            element = answer.elements[carries]
            out.append(ReplyParagraph(
                text=element.text, carries=carries,
                passage=carries if element.source is not None else None))
            continue
        if passage is not None and answer.elements[passage].source is None:
            passage = None
        # A paragraph written with blank lines inside it is several paragraphs;
        # the pinpoint link stays with the first.
        parts = [part.strip() for part in re.split(r"\n\s*\n", str(row.get("text") or ""))]
        for n, part in enumerate(p for p in parts if not blank(p)):
            out.append(ReplyParagraph(text=part, passage=passage if n == 0 else None))
    return tuple(out)


def check_prompt(paragraphs: tuple[ReplyParagraph, ...], answer: Answer,
                 items: tuple[int, ...]) -> Prompt:
    """The reply, what it may state law from, and what it had to convey -- in that
    order, the items last."""
    reply = [{"paragraph": n, "text": p.text} for n, p in enumerate(paragraphs)]
    rows = []
    for i in items:
        e = answer.elements[i]
        row = {"id": _id(i), "words": e.text}
        if e.by_when is not None:
            row["by"] = e.by_when.isoformat()
        rows.append(row)
    basis = [{"id": _id(i), "words": e.text,
              **({"passage": snippet(e.source.text, PASSAGE_CHARS)}
                 if e.source is not None else {})}
             for i, e in enumerate(answer.elements)]
    user = ("THE REPLY:\n" + json.dumps(reply, ensure_ascii=False)
            + "\n\nTHE PASSAGES AND CHECKED WORK THE REPLY MAY STATE LAW FROM:\n"
            + json.dumps(basis, ensure_ascii=False)
            + "\n\nTHE ITEMS IT HAD TO CONVEY:\n" + json.dumps(rows, ensure_ascii=False))
    return Prompt(system=COMPOSE_CHECK_SYSTEM, user=user, operation="compose_check")


def unsupported(data: dict, paragraphs: tuple[ReplyParagraph, ...]) -> tuple[str, ...] | None:
    """THE SENTENCES THE CHECK NAMED AS LAW NOBODY RETRIEVED, or `None` when the
    check did not say.

    `None` is not "nothing unsupported": a check that returned no verdict on
    support has not cleared the reply, and the caller treats it as a failed check
    (S1). A named sentence counts only if the reply really contains it -- the
    check cannot condemn words the reply never wrote, just as it cannot confirm
    them (see `confirmed`).
    """
    rows = (data or {}).get("unsupported")
    if not isinstance(rows, list):
        return None
    written = " ".join(plain(p.text) for p in paragraphs)
    found = []
    for row in rows:
        sentence = plain(str((row or {}).get("sentence") or "")) \
            if isinstance(row, dict) else ""
        if len(sentence) >= 12 and sentence in written:
            found.append(sentence)
    return tuple(found)


def plain(text: str) -> str:
    """The words of a reply sentence, without the bold marks the reply may carry
    and with its spacing settled -- so a check that copies a sentence without the
    marks still finds it, and cannot slip past by dropping them."""
    return " ".join((text or "").replace("**", "").split())


@dataclass(frozen=True)
class Confirmed:
    """Which material items the reply conveys, and in which paragraph -- each
    anchored to a sentence FOUND in that paragraph, not merely claimed."""

    where: dict


def confirmed(data: dict, paragraphs: tuple[ReplyParagraph, ...], answer: Answer,
              items: tuple[int, ...]) -> Confirmed:
    """A claim of coverage stands only on a sentence the reply really contains,
    in the paragraph named, and only if every date the item states is written
    somewhere in the reply."""
    written = " ".join(p.text for p in paragraphs)
    shown = dates_mentioned(written)
    where: dict[int, int] = {}
    for n, p in enumerate(paragraphs):
        if p.carries is not None:
            where.setdefault(p.carries, n)
    for row in (data or {}).get("items") or ():
        if not isinstance(row, dict) or row.get("conveyed") is not True:
            continue
        index = _index(row.get("id", ""), answer)
        n = row.get("paragraph")
        sentence = plain(str(row.get("sentence") or ""))
        if (index is None or index not in items or index in where
                or type(n) is not int or not 0 <= n < len(paragraphs)
                or len(sentence) < 12):
            continue
        if sentence not in plain(paragraphs[n].text):
            continue
        if not dates_of(answer.elements[index]) <= shown:
            continue
        where[index] = n
    return Confirmed(where)


def settle(paragraphs: tuple[ReplyParagraph, ...], answer: Answer,
           items: tuple[int, ...], found: Confirmed) -> tuple[ReplyParagraph, ...]:
    """QUALIFY, NEVER DROP. The blocker leads; anything unconfirmed is carried.

    A blocked turn whose first paragraph is not confirmed to convey the blocker
    is led by the blocker's own words. Every material item the check did not
    confirm is carried, verbatim, after the prose, in the order the work holds
    them -- the reply may read a little less smoothly, and it has lost nothing.
    """
    out = list(paragraphs)
    lead = blocker(answer)
    if lead is not None and found.where.get(lead) != 0:
        element = answer.elements[lead]
        out = [p for p in out if p.carries != lead]
        out.insert(0, ReplyParagraph(text=element.text, carries=lead,
                                     passage=lead if element.source is not None else None))
    carried = {p.carries for p in out if p.carries is not None}
    for i in items:
        if i in found.where or i in carried:
            continue
        element = answer.elements[i]
        out.append(ReplyParagraph(text=element.text, carries=i,
                                  passage=i if element.source is not None else None))
    return tuple(out)
