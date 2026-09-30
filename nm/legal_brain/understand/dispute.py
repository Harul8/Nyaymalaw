"""Which disputes does this message describe, and which does it continue?

One prompt, one call, a short check (LB-109, owner, 30 September 2026: "keep the
code short and simple, if something goes wrong, lets tune the prompt better, but
not add a separate layer for each failed case").

The message is shown as numbered sentences, with the disputes already on the file.
The model returns the disputes directly -- the other side, what is contested, the
kind of wrong, new or which dispute on the file, and the numbers of its sentences --
and which sentences are shared background or only instructions. The code checks
that the answer is well formed and tied to the advocate's own words; it does not
second-guess the separation. A failed check gets ONE repair that says what failed;
if that fails too the advocate is shown what was found and asked, and the message
is never quietly filed as one dispute. The advocate sees the numbered list of
disputes and corrects it in a sentence.

A MISS IS FIXED IN THE PROMPT, and measured on the labelled briefs and their
variants before it is kept -- never by a check or a code path for the case that
failed.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.reason.requirements import ANSWER_ROWS, ANSWER_RULE
from nm.shared.text_contracts import clean, fold, refuses_blank_text, snippet


class Dispute(str, Enum):
    """THREE STATES. The third is what makes the other two safe to act on."""

    CONTINUES = "continues"
    OPENS = "opens"
    CANNOT_TELL = "cannot_tell"


#: Where a dispute sits on the file, besides the ID of a dispute already on it.
NEW = "new"
UNDECIDED = "cannot_tell"

#: THE KINDS OF WRONG (owner-agreed, 29 September 2026). Generic on purpose: they
#: name no Act, no section and no scenario.
KINDS: dict[str, str] = {
    "possession_of_property": "possession, occupation or title of property -- "
                              "encroachment, trespass, dispossession, eviction",
    "use_or_access": "a right to use or reach property -- a way, a gate, water, light",
    "agreement": "an agreement or contract -- its performance, breach or refund",
    "money_owed": "money owed -- a loan, a price, fees, rent, dues",
    "cheque": "a cheque or other instrument dishonoured",
    "bodily_harm": "harm, threat or force against a person",
    "family_or_succession": "family or inheritance -- heirship, partition, "
                            "maintenance, custody",
    "employment": "employment or service",
    "government_action": "an act or order of a government or public authority",
    "other": "anything else",
}

def _ids(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


DISPUTE_SCHEMA: dict = {
    "x-nm-read": "dispute",
    "type": "object",
    "properties": {
        "client": {"type": "string", "description":
                   "Whom the advocate acts for, by the name as written; empty if unnamed."},
        "disputes": {
            "type": "array",
            "description": "Every dispute the message describes, each once.",
            "items": {
                "type": "object",
                "properties": {
                    "other_side": {"type": "string", "description":
                                   "The party adverse to the client in this dispute, by "
                                   "the name as written; empty if none is named. Never "
                                   "the client."},
                    "contested": {"type": "string", "description":
                                  "What is contested, in a few words."},
                    "kind": {"type": "string", "enum": list(KINDS), "description":
                             "; ".join(f"{k}: {v}" for k, v in KINDS.items())},
                    "on_file": {"type": "string", "description":
                                "'new', the ID of the dispute already on the file that "
                                "this continues, or 'cannot_tell'."},
                    "sentences": _ids("Every sentence about this dispute: what "
                                      "happened, its facts and evidence, the other "
                                      "side's answer, the relief sought."),
                },
                "required": ["other_side", "contested", "kind", "on_file", "sentences"],
                "additionalProperties": False,
            },
        },
        "background": _ids("Sentences shared by EVERY dispute: whom we act for, "
                           "whether anything has been filed."),
        "instructions": _ids("Sentences that only ask for work to be done."),
        "why": {"type": "string",
                "description": "One clause. Shown to the advocate so they can correct it."},
        "focus_thread_id": {"type": "string", "description":
                            "Existing dispute expressly prioritised by the advocate, else empty."},
        "focus_quote": {"type": "string", "description":
                        "Exact current words instructing that focus, otherwise empty."},
        "advance_quote": {"type": "string", "description":
                          "Exact request to continue the whole-file review or the next dispute, "
                          "else empty. Not an acknowledgement, fact or request to stop."},
        "requirement_answers": ANSWER_ROWS,
    },
    "required": ["client", "disputes", "background", "instructions", "why",
                 "focus_thread_id", "focus_quote", "advance_quote", "requirement_answers"],
    # STRICT MODE REQUIRES IT: without it the provider cannot compile the grammar.
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate is briefing a matter. Separate the message into DISPUTES.\n\n"
    "A DISPUTE is one contest between the client and one other side over one right or "
    "obligation, or one wrongful incident, that could succeed or fail on its own.\n"
    "- Two rights, or two incidents, that could have different outcomes are two "
    "disputes, even against the same person and even if one happened during the other.\n"
    "- Each dispute has exactly ONE kind of wrong from the list. If what you would call "
    "one dispute involves two kinds of wrong, it is two disputes.\n"
    "- Each wrongful incident against a person or their property is its own dispute.\n"
    "- A dishonoured cheque is its own dispute, separate from the debt it was given for.\n"
    "- Everything that supports one contest stays in it: dates, payments, documents, "
    "evidence, what is not yet known, the other side's answer or excuse, and the relief "
    "sought (performance, refund, compensation). These never make a dispute of their "
    "own. The kind is chosen for the wrong, not for the remedy: money paid under an "
    "agreement, and a refund of it, are part of that agreement's dispute. A payment made "
    "under an agreement is a fact of that agreement's dispute, never a dispute of its "
    "own. Alternative "
    "remedies for one wrong (\"either ... or ...\") are one dispute. One agreement told "
    "in many sentences is one dispute.\n"
    "- The advocate's numbering or paragraphs group what they told together; they do "
    "not decide the disputes. One numbered item or paragraph can hold two disputes, and "
    "one dispute can run across several.\n"
    "- The other side is the party adverse to the client in that dispute, whether they "
    "claim or resist. It is never the client.\n\n"
    "SENTENCES. The message is given as numbered sentences. Put every sentence in "
    "exactly one of three places: in the dispute or disputes it is about (a sentence "
    "about two goes in both); or in BACKGROUND if it is shared by every dispute -- whom "
    "we act for, whether anything has been filed; or in INSTRUCTIONS if it only asks for "
    "work to be done. A sentence in background or instructions is never also in a "
    "dispute. A sentence that asks or tells you to do something, or not to do something, "
    "is an instruction wherever it appears in the message; background holds facts only. "
    "A question the advocate asks you is an instruction, even when it names the claim. "
    "A fact about one particular right or incident belongs to that dispute, not to "
    "background.\n\n"
    "THE FILE. You are told the disputes already on the file. A dispute this message "
    "adds to gives that dispute's ID as on_file; a dispute not on the file is 'new'; "
    "'cannot_tell' is for one that genuinely could be either -- the advocate will then "
    "be asked, which is better than a wrong answer. Never give one ID to two disputes. "
    "An explicit instruction to split a dispute on the file is a request to reorganise "
    "the board, not merely add detail: keep the existing ID only for the part that "
    "remains, give each part split off its own entry, and do not report the unchanged "
    "inventory as the split. That change does not establish facts or erase prior "
    "records.\n\n"
    "Only the advocate's own words are evidence. Earlier accounts still awaiting "
    "placement are evidence, not new commands. A statement that nothing has been filed "
    "is not a statement that the client has no claim. Record an explicit focus on an "
    "existing dispute, or an explicit request to move on to the next dispute, only from "
    "the current message; never infer either from an acknowledgement."
    + ANSWER_RULE
)


@refuses_blank_text("quoted", "label")
@dataclass(frozen=True)
class Described:
    """One dispute a message describes, in the advocate's own words."""

    quoted: str
    label: str
    thread_id: str = ""
    additional_quotes: tuple[str, ...] = ()
    opponent: str = ""
    """Whom the client is against in it, in the advocate's own characters, or empty."""
    related: tuple[tuple[int, str], ...] = ()
    """Other disputes of this reading it is LINKED to, by position and how: the same
    opponent or the same events. Linked, never merged."""
    allocation_unit_ids: tuple[str, ...] = ()
    """Its sentence numbers and the shared background, in source order: two
    sentences may have identical words, so the words alone cannot say which."""

    @property
    def spans(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.quoted, *self.additional_quotes)))


@refuses_blank_text("quoted", "why")
@dataclass(frozen=True)
class DisputeRead:
    verdict: Dispute
    quoted: str = ""
    why: str = ""
    refused: str | None = None
    described: tuple[Described, ...] = ()
    """EVERY dispute this message describes. EMPTY IS NOT ZERO DISPUTES: it is also
    what a read that did not run leaves behind. The caller asks whether it RAN."""
    focus_thread_id: str = ""
    advance: bool = False
    requirement_answers: tuple[dict, ...] = ()
    instructions: tuple[str, ...] = ()
    """Sentences that only asked for work to be done: never a fact of any dispute."""
    found: tuple[str, ...] = ()
    """What a REFUSED reading found, one line per dispute, to be shown and asked."""

    @property
    def opens(self) -> bool:
        return self.verdict is Dispute.OPENS

    @property
    def continues(self) -> bool:
        return self.verdict is Dispute.CONTINUES


UNREAD = DisputeRead(Dispute.CANNOT_TELL, why="the dispute read did not run")


def build_prompt(quotable: Quotable):
    """What is on the file, and what was just said, sentence by sentence."""
    from nm.shared.model_port import Prompt

    units = source_units(quotable.words)
    return Prompt(
        system=SYSTEM,
        user=(f"{quotable.block()}\n\n"
              "SOURCE UNITS (current message, then any earlier account still awaiting "
              "placement; IDs are not quotation):\n"
              + "\n".join(f"{key}: {text}" for key, text in units.items())
              + "\n\nList the disputes and place every sentence. Then record any "
                "explicit focus or request to move on, and any checklist answers."))


def repair_prompt(prompt, refused: str):
    """The ONE repair, told what the first answer got wrong."""
    return replace(prompt, user=prompt.user + "\n\nYour previous answer was refused: "
                   + refused + ". Re-read the whole message and answer again, placing "
                   "every sentence.")


def schema_for(quotable: Quotable, *, thread_ids: frozenset[str] = frozenset()) -> dict:
    """The contract, with the sentence numbers and the file's dispute IDs closed."""
    schema = deepcopy(DISPUTE_SCHEMA)
    ids = list(source_units(quotable.words)) or ["S1"]
    props = schema["properties"]
    row = props["disputes"]["items"]["properties"]
    for field in (row["sentences"], props["background"], props["instructions"]):
        field["items"]["enum"] = ids
    row["on_file"]["enum"] = [NEW, UNDECIDED, *sorted(thread_ids)]
    return schema


def separate(read, quotable: Quotable, *,
             thread_ids: frozenset[str] = frozenset()) -> DisputeRead:
    """Read, and repair once. `read(prompt, schema)` returns the model's answer as a
    dict; the served turn and its measurement both call this, so they cannot differ.
    A model failure propagates to the caller."""
    prompt = build_prompt(quotable)
    schema = schema_for(quotable, thread_ids=thread_ids)
    first = interpret(quotable, read(prompt, schema), thread_ids=thread_ids)
    if not first.refused:
        return first
    again = interpret(quotable, read(repair_prompt(prompt, first.refused), schema),
                      thread_ids=thread_ids)
    return replace(again, found=again.found or first.found) if again.refused else again


def interpret(quotable: Quotable, data: dict, *,
              thread_ids: frozenset[str] = frozenset()) -> DisputeRead:
    """The model's disputes, checked -- or REFUSED, naming what failed.

    A refusal is CANNOT_TELL, never CONTINUES: falling back to "continues" would
    make every failed read a silent merge.
    """
    rows = data.get("disputes") if isinstance(data, dict) else None
    background, instructions = ((data.get(k) for k in ("background", "instructions"))
                                if isinstance(data, dict) else (None, None))
    if not all(isinstance(x, list) for x in (rows, background, instructions)) or not all(
            isinstance(r, dict) and isinstance(r.get("sentences"), list) for r in rows):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the answer is not a list of disputes and sentences")
    units = source_units(quotable.words)
    client = _name(data.get("client"), quotable)
    found = tuple(dict.fromkeys(_found_line(r, quotable) for r in rows if r["sentences"]
                                and all(s in units for s in r["sentences"])))

    def refuse(why: str) -> DisputeRead:
        return DisputeRead(Dispute.CANNOT_TELL, refused=why, found=found)

    in_dispute = {s for r in rows for s in r["sentences"] if isinstance(s, str)}
    placed = [*(s for r in rows for s in r["sentences"]), *background, *instructions]
    unknown = sorted({str(s) for s in placed if not isinstance(s, str) or s not in units})
    if unknown:
        return refuse("sentences not in the message: " + ", ".join(unknown))
    missing = [k for k in units if k not in placed]
    if missing:
        return refuse("sentences not placed: " + ", ".join(missing))
    twice = [k for k in units
             if (k in in_dispute) + (k in background) + (k in instructions) > 1]
    if twice:
        return refuse("placed in more than one of a dispute, background and "
                      "instructions: " + ", ".join(twice))
    on_file = [r.get("on_file") for r in rows]
    if any(not r["sentences"] for r in rows):
        return refuse("a dispute has no sentences")
    if any(f not in (NEW, UNDECIDED, *thread_ids) for f in on_file):
        return refuse("a dispute names an ID that is not on this matter")
    named = [f for f in on_file if f not in (NEW, UNDECIDED)]
    if len(named) != len(set(named)):
        return refuse("two disputes name the same dispute on the file")

    focus = data.get("focus_thread_id") or ""
    if focus and (focus not in thread_ids
                  or not Quotable(turn=quotable.turn).accepts(data.get("focus_quote") or "")):
        return refuse("the requested focus is not source-bound to this matter")
    answers = data.get("requirement_answers")

    described = tuple(_described(r, units, background, client, quotable) for r in rows)
    described = tuple(replace(d, related=_related(n, rows, described))
                      for n, d in enumerate(described))
    if thread_ids and UNDECIDED in on_file:
        verdict = Dispute.CANNOT_TELL
    elif any(f in (NEW, UNDECIDED) for f in on_file):
        verdict = Dispute.OPENS
    else:
        verdict = Dispute.CONTINUES
    return DisputeRead(
        verdict, described[0].quoted if described else "", clean(data.get("why")),
        described=described, focus_thread_id=focus,
        advance=bool(data.get("advance_quote")
                     and Quotable(turn=quotable.turn).accepts(data["advance_quote"])),
        requirement_answers=tuple(answers) if isinstance(answers, list) else (),
        instructions=tuple(units[k] for k in units if k in instructions))


def _name(value: object, quotable: Quotable) -> str:
    """A name in the advocate's own characters -- never one they did not write, and
    never one that names nobody ("he", "the other side")."""
    from nm.legal_brain.understand.posture import names_nobody

    name = clean(value if isinstance(value, str) else "")
    if not name or names_nobody(name):
        return ""
    return snippet(quotable.verbatim(name), 60)


def _described(row: dict, units: dict[str, str], background: list, client: str,
               quotable: Quotable) -> Described:
    """One dispute: its sentences and the shared background, in the order written."""
    ids = tuple(k for k in units if k in row["sentences"] or k in background)
    words = list(dict.fromkeys(units[k] for k in ids))
    opponent = _name(row.get("other_side"), quotable)
    if opponent and fold(opponent) == fold(client):
        opponent = ""   # the client is never their own other side
    thing = snippet(clean(row.get("contested") if isinstance(row.get("contested"), str)
                          else ""), 70) or snippet(units[row["sentences"][0]], 70)
    on_file = row.get("on_file")
    return Described(words[0], _label(client, opponent, thing),
                     on_file if on_file not in (NEW, UNDECIDED) else "",
                     tuple(words[1:]), opponent, allocation_unit_ids=ids)


def _label(client: str, opponent: str, thing: str) -> str:
    """A file-cover name: "<client> v. <opponent> -- <thing contested>"."""
    if client and opponent:
        return f"{client} v. {opponent} — {thing}"
    if opponent:
        return f"Against {opponent} — {thing}"
    return f"{client} — {thing}" if client else thing


def _related(n: int, rows: list[dict], described: tuple[Described, ...]
             ) -> tuple[tuple[int, str], ...]:
    """LINKED, NEVER MERGED: disputes sharing a sentence or an opponent."""
    out = []
    for m, other in enumerate(rows):
        if m == n:
            continue
        if set(rows[n]["sentences"]) & set(other["sentences"]):
            out.append((m, "the same events"))
        elif described[n].opponent and fold(described[n].opponent) == fold(
                described[m].opponent):
            out.append((m, "the same opponent"))
    return tuple(out)


def _found_line(row: dict, quotable: Quotable) -> str:
    """One line for a dispute a refused reading found, to show the advocate."""
    thing = snippet(clean(row.get("contested") if isinstance(row.get("contested"), str)
                          else ""), 70) or "a dispute"
    who = _name(row.get("other_side"), quotable)
    return f"{thing} (against {who})" if who else thing


def source_units(message: str) -> dict[str, str]:
    """Literal addressable spans; splitting does not classify their substance."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", message) if p.strip()]
    return {f"S{i}": value for i, value in enumerate(parts, 1)}


def pending_accounts(matter, current_turn: str) -> tuple:
    """Original accounts not yet fully allocated, never generated summaries.

    Repeated failed submissions are one recovery population. Superseded accounts
    and fully placed accounts do not return. AN ACCOUNT WHOSE READING PLACED IT IS
    PLACED, even where some of its sentences were instructions charted nowhere --
    judged by its words alone it would be offered back on every later turn.
    """
    scoped_ids = {fid for thread in matter.threads for fid in thread.chronology}
    placed = [f for f in matter.facts if f.id in scoped_ids]
    read_turns = {f.provenance.turn for f in placed}
    seen, pending = set(), []
    for fact in matter.facts:
        if (fact.provenance.kind != "advocate_statement" or fact.provenance.span
                or fact.provenance.turn == current_turn or fact.superseded_by is not None
                or fact.provenance.turn in read_turns):
            continue
        key = fold(fact.statement)
        spans = [fold(f.statement) for f in placed]
        if key in seen or all(any(fold(unit) in span for span in spans)
                              for unit in source_units(fact.statement).values()):
            continue
        seen.add(key)
        pending.append(fact)
    return tuple(pending)
