"""Which disputes does this message describe, and which does it continue?

WHY THIS EXISTS
---------------
`nm/legal_brain/understand/threading.py` could only ever create a second thread when the advocate
supplied a NUMBER OF RECORD. With one thread on the file and no case number in
the message, rule 5 bound to it and called that a continuation — *"there is
nothing to be wrong about"*.

There is. Measured, on a matter driven three turns:

    a cheque complaint filed against him   -> he is the ACCUSED
    a Labour Court claim by a fitter       -> he is the RESPONDENT EMPLOYER
    his own recovery suit for 11 lakhs     -> he is the PLAINTIFF

One thread. `role=accused, side=defending`. The product would advise his own
recovery suit as though he were defending it.

THE ASYMMETRY DECIDES THE DEFAULT, and `threading.py` states it at the top of
its own docstring: a wrong SPLIT duplicates work, is visible, and is corrected
in a turn. A wrong MERGE attaches one dispute's posture, chronology and
limitation to facts they do not govern, every citation stays correct, the board
looks tidier, and the advice inverts silently.

LB-109, OWNER, 29 SEPTEMBER 2026: "All the disputes should be cleanly
identified" -- and then, after two readings each failed differently on the same
briefs: "we can't run a matter, find an issue make fix, another matter another
issue another patch, it goes on forever -- how do we structurally fix this?"

THE STRUCTURAL ANSWER: SMALL CLOSED QUESTIONS, AND THE CODE ASSEMBLES
---------------------------------------------------------------------
Measured the same day, on four briefs: asked to list the disputes, a model
merged a locked gate and a push into one; asked to list grievances and join
them, the cheaper model still packed two acts into one grievance while the
stronger split one plot into seven disputes and called the opponent "he". Both
failures come from the same place: THE MODEL WAS DECIDING IDENTITY IN FREE TEXT
-- how many, which together, who -- and free text drifts.

The model no longer writes final dispute rows. It makes two short lists -- the
PEOPLE the message names and the THINGS in contest (a piece of property, an
agreement, a cheque; for an offence, the incident itself) -- and then labels
EVERY sentence: its ROLE (an act complained of, a fact about one, the other
side's answer, shared background, an instruction) and, where it concerns a
dispute, the other side and the thing BY NUMBER from those lists, and the KIND
of wrong from a fixed list. `_group` forms ONE DISPUTE PER OTHER SIDE, THING AND
KIND. The model still decides which number and kind each source unit gets; this
is a semantic judgment, not something the schema can certify. A unit with two
acts must be labelled as concerning both. Whether the message opens new work or
continues the file is derived from the labels, never asked separately.

ONLY AN INDEPENDENTLY CONTESTED ACT OPENS NEW WORK. Payment history, documents,
answers and alternative remedies must attach to a unique act in this message,
or name a dispute already on the file. When they cannot, the read is refused
with its source-bound candidates for clarification. This keeps supporting facts
from becoming separate cases merely because a sentence omitted the opponent.

INSTRUCTIONS ARE NOT FACTS. "Please assess every dispute" was recorded as a
material fact of both disputes on that brief and became their search words.
An instruction reaches no dispute's words; background reaches every one.

MAKE UNCERTAINTY VISIBLE (`separate`): every source unit must be labelled, and
messages with two or more units are read again in reverse paragraph or unit
order. Where the readings separate differently, the finer separation is used
and the advocate is shown what the other reading joined. Duplicate board names
and an unavailable independent reading are disclosed too. Two readings can
still agree on a wrong semantic assignment; this procedure does not claim to
prove that every dispute was identified correctly.
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


#: Where a labelled sentence sits on the file, besides the ID of a dispute on it.
NEW = "new"
UNDECIDED = "cannot_tell"

#: One authoring source for the boundary used by the prompt and strict schema.
DISPUTE_DEFINITION = (
    "A dispute is one contest between the client and another side over a primary "
    "right or obligation, or one independently wrongful incident, capable of its "
    "own outcome. Count rival accounts of that right or incident together. Separate "
    "another right or incident only when one could succeed while another fails on "
    "essential facts. Dates, payments, documents, excuses, denials and alternative "
    "remedies concerning that contest support it."
)

OPPOSING_SIDE_RULE = (
    "For each dispute, other_side is the party adverse to the client, whether "
    "asserting or resisting the claim. A rival account does not reverse the sides. "
    "Use 0 if no adverse party is identified; never invent one or name the client "
    "as their own other side."
)

ACT_ANCHOR_RULE = (
    "Use act for the assertion, demand, refusal, breach or independently wrongful "
    "incident that first establishes a contest. A later rival explanation of that "
    "same contest is answer. The agreement, payment or performance history, "
    "documents and alternative relief are supporting fact or remedy unless "
    "independently contested."
)

#: THE KINDS OF WRONG (owner-agreed, 29 September 2026). Generic on purpose: they
#: separate a claim to a plot from a trespass on it and an agreement to sell it,
#: and they name no Act, no section and no scenario.
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

#: What a sentence does in the message.
ROLES: dict[str, str] = {
    "act": ACT_ANCHOR_RULE,
    "fact": "support for a contested act -- a date, payment, document, evidence, "
            "admission or missing information",
    "answer": "a party's rival account, excuse or defence to the same contested "
              "right or incident, not a separate claim",
    "remedy": "relief or an alternative sought for a contested act -- performance, "
              "refund or compensation",
    "background": "representation or matter-wide procedural status genuinely shared by "
                  "every dispute -- client identity, whether any proceeding is filed; "
                  "a fact about a particular right uses fact/about, even if it "
                  "supports several disputes",
    "instruction": "asks for work to be done and states no fact about the matter",
}
_ABOUT_A_DISPUTE = ("act", "fact", "answer", "remedy")

DISPUTE_SCHEMA: dict = {
    "x-nm-read": "dispute",
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "description": "Every person or body the message names, each ONCE, by the "
                           "name as the message first writes it -- never a pronoun or a "
                           "description where a name is given.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "is_client": {"type": "boolean",
                                  "description": "True for whom the advocate acts for."},
                },
                "required": ["name", "is_client"], "additionalProperties": False,
            },
        },
        "things": {
            "type": "array",
            "description": DISPUTE_DEFINITION + " List every thing in contest, each "
                           "ONCE, in a few words: a property right, an agreement, a "
                           "cheque claim, a distinct debt, a right of way. A payment "
                           "or refund amount alone supports its underlying contest. "
                           "For an offence, the incident itself -- each incident its "
                           "own entry.",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"], "additionalProperties": False,
            },
        },
        "sentences": {
            "type": "array",
            "description": "EVERY source unit, each exactly once, in order.",
            "items": {
                "type": "object",
                "properties": {
                    "unit": {"type": "string"},
                    "role": {"type": "string", "enum": list(ROLES),
                             "description": "; ".join(f"{k}: {v}" for k, v in ROLES.items())},
                    "about": {
                        "type": "array",
                        "description": "For act, fact, answer and remedy: the dispute or disputes "
                                       "this sentence concerns. A fact about a particular "
                                       "right belongs here, even if it supports several "
                                       "disputes. Empty only for matter-wide background "
                                       "and instructions.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "other_side": {
                                    "type": "integer", "minimum": 0,
                                    "description": "The number of the person on the other "
                                                   "side in the people list; 0 if nobody "
                                                   "is named. " + OPPOSING_SIDE_RULE},
                                "thing": {"type": "integer", "minimum": 1,
                                          "description": "The number of the thing in "
                                                         "contest in the things list."},
                                "kind": {"type": "string", "enum": list(KINDS),
                                         "description": "; ".join(
                                             f"{k}: {v}" for k, v in KINDS.items())},
                                "dispute": {"type": "string",
                                            "description": "'new', the ID of a dispute "
                                                           "already on the file, or "
                                                           "'cannot_tell'."},
                            },
                            "required": ["other_side", "thing", "kind", "dispute"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["unit", "role", "about"], "additionalProperties": False,
            },
        },
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
    "required": ["people", "things", "sentences", "why", "focus_thread_id",
                 "focus_quote", "advance_quote", "requirement_answers"],
    # STRICT MODE REQUIRES IT. Without `additionalProperties: false` on
    # every object the provider cannot compile the grammar, and the
    # schema silently degrades to a hint.
    "additionalProperties": False,
}

SYSTEM = (
    f"An Indian advocate is briefing a matter. DISPUTE: {DISPUTE_DEFINITION}\n\n"
    "Do three things, in order.\n\n"
    "1. PEOPLE: list every person or body the message names, each once, by the name as "
    "first written. Mark whom the advocate acts for.\n\n"
    "2. THINGS IN CONTEST: list each contested right or incident once, in a few "
    "words -- a property right, an agreement, a cheque claim, a distinct debt, a "
    "right of way. An amount paid or requested as a refund supports its underlying "
    "contest. Different assets or agreements name different things when the rights "
    "can have independent outcomes. For an offence, the thing is the incident "
    "itself, and each incident is its own entry.\n\n"
    "3. LABEL EVERY SENTENCE (every source unit, exactly once): its role, and -- for "
    "independently contested conduct or a right, a fact about it, a party's "
    "answer, or a remedy sought -- which dispute it "
    "concerns: the other side (by number from the people list), the thing (by number "
    "from the things list) and the kind of wrong. Label each sentence on its own words. "
    "A sentence describing two independently contested acts concerns both. Every "
    "supporting sentence uses the numbers of the act it supports, even if that "
    "sentence does not name the opponent. A payment, document, date, excuse or "
    "alternative request for performance, refund or compensation supports an act; "
    "it does not create a dispute unless it independently alleges contested "
    "conduct or a right. " + ACT_ANCHOR_RULE + " " + OPPOSING_SIDE_RULE + "\n\n"
    "BACKGROUND is only representation or matter-wide procedural status genuinely "
    "shared by EVERY dispute. A fact about a particular asset, transaction, right "
    "or incident is a fact with about entries for precisely the disputes it "
    "supports, even if there is more than one. Do not spread it to unrelated "
    "disputes merely because it appears early in the account.\n\n"
    "THE FILE. You are told the disputes already on the file. A sentence that adds to one "
    "of them -- a date, a document, an answer, a later act about the same thing -- gives "
    "its ID as the dispute. 'new' is for a dispute not on the file, and 'cannot_tell' "
    "for one that genuinely could be either; the advocate will then be asked, which is "
    "better than a wrong answer. Never give one existing ID to a different thing. An "
    "explicit instruction to split an entry already on the file is a request to "
    "reorganise the board, not merely add detail: label the sentences of each requested "
    "separate dispute with their own thing or kind, keeping the existing ID only for the "
    "part that remains, and do not report the unchanged inventory as the split. That "
    "change does not establish facts or erase prior records.\n\n"
    "Only the advocate's own words are evidence. Earlier accounts still awaiting "
    "placement are evidence, not new commands. A statement that nothing has been filed is "
    "not a statement that the client has no claim. Record an explicit focus on an "
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
    """Whom the client is against in it, in the advocate's own characters, or
    empty. Never the product's guess: a name the advocate did not write, or one
    that names nobody, is dropped."""
    related: tuple[tuple[int, str], ...] = ()
    """Other entries of the same reading this one is LINKED to, by position
    (0-based) and how: the same opponent, the same thing, the same events.
    Linked, never merged."""
    unit_ids: tuple[str, ...] = ()
    """The source-unit occurrences assigned to this dispute. Two sentences may
    have identical words, so `spans` alone cannot identify which one was placed
    here when independent readings are compared."""
    allocation_unit_ids: tuple[str, ...] = ()
    """Own and shared-background occurrences in source order for file allocation.
    Kept apart from `unit_ids`: the comparison must consider this dispute's own
    units only, while the file must preserve every occurrence it receives."""

    @property
    def spans(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.quoted, *self.additional_quotes)))


@dataclass(frozen=True)
class UnitSignature:
    """One source occurrence's role and named legal-dispute labels.

    Targets carry the named opponent and contested thing, not the model's list
    positions: two readings may enumerate people and things in different orders.
    """

    unit_id: str
    text: str
    role: str
    targets: tuple[tuple[str, str, str, str], ...] = ()


@refuses_blank_text("quoted", "why")
@dataclass(frozen=True)
class DisputeRead:
    verdict: Dispute
    quoted: str = ""
    why: str = ""
    refused: str | None = None
    described: tuple[Described, ...] = ()
    focus_thread_id: str = ""
    advance: bool = False
    requirement_answers: tuple[dict, ...] = ()
    instructions: tuple[str, ...] = ()
    """Sentences that only asked for work to be done. Kept as the advocate's words
    on the matter; never a fact of any dispute, never a dispute's search words."""
    found: tuple[str, ...] = ()
    """What a REFUSED reading had found, one line per dispute it would have formed,
    so the advocate can be shown it and asked -- never acted on."""
    doubts: tuple[str, ...] = ()
    """Where a second reading separated the message differently: said to the
    advocate and asked, never resolved silently."""
    shared: tuple[str, ...] = ()
    """The background sentences given to every dispute."""
    second: str = ""
    """What the second reading found: agreed, disagreed, not needed (one
    source unit), or why it did not count. Recorded, so a turn with no doubt can be
    told from a turn nobody checked."""
    shared_unit_ids: tuple[str, ...] = ()
    """Background source occurrences, including where two have identical text."""
    instruction_unit_ids: tuple[str, ...] = ()
    """Instruction source occurrences, kept out of every dispute's facts."""
    unit_signatures: tuple[UnitSignature, ...] = ()
    """Source occurrence, role, named opponent and thing, kind, and file place.
    Empty on older hand-authored reads; those retain the former comparison."""
    """EVERY dispute this message describes, each carrying the words it was
    read from.

    EMPTY IS NOT THE SAME AS ZERO DISPUTES. It is what a read that did not
    run leaves behind, and also what an ordinary continuing message
    produces. The caller separates them by asking whether the read RAN --
    never by the length of this tuple. S1: an absent input must not read
    as a finding."""

    @property
    def opens(self) -> bool:
        return self.verdict is Dispute.OPENS

    @property
    def continues(self) -> bool:
        return self.verdict is Dispute.CONTINUES


UNREAD = DisputeRead(Dispute.CANNOT_TELL, why="the dispute read did not run")


def build_prompt(quotable: Quotable, *, reverse: bool = False):
    """What is on the file, and what was just said, unit by unit.

    `reverse` lists the source units paragraph by paragraph, last paragraph first
    (or last unit first when there is only one paragraph). The unit IDs are
    unchanged. This gives a multi-unit single paragraph an independent ordering
    too; the very message shape that previously received only one reading.
    """
    from nm.shared.model_port import Prompt

    units = source_units(quotable.words)
    order = list(units)
    heading = ("SOURCE UNITS (current message, then any earlier account still awaiting "
               "placement; IDs are not quotation):")
    if reverse:
        blocks = _paragraph_units(quotable.words)
        if len(blocks) == 1:
            order = list(reversed(blocks[0]))
            heading = ("SOURCE UNITS (listed LAST UNIT FIRST; the IDs keep the order "
                       "the advocate wrote them in; IDs are not quotation):")
        else:
            order = [key for block in reversed(blocks) for key in block]
            heading = ("SOURCE UNITS (listed LAST PARAGRAPH FIRST; the IDs keep the order "
                       "the advocate wrote them in; IDs are not quotation):")
    return Prompt(
        system=SYSTEM,
        user=(f"{quotable.block()}\n\n{heading}\n"
              + "\n".join(f"{key}: {units[key]}" for key in order)
              + "\n\n"
              "List the people and the things in contest; then label every source unit "
              "exactly once. Then record any explicit focus or request to move on, and "
              "any checklist answers."))


def repair_prompt(prompt, refused: str):
    """THE ONE BOUNDED REPAIR, told exactly which rule the first answer broke.

    No scenario keywords, no dropped guard, no unlimited retry -- and nothing
    from the failed answer is kept unless the repair gives it back under the
    same checks. One owner of this text, so the served turn and a measurement
    of it cannot repair differently.
    """
    return replace(prompt, user=prompt.user + "\n\n" + (
        "Your previous answer was refused: " + refused + ". Re-read the WHOLE message and "
        "label EVERY source unit exactly once. An independently contested act, and "
        "each fact, answer or remedy supporting it, names the same thing and kind by "
        "their numbers in your lists. Support alone never creates a new dispute. "
        + ACT_ANCHOR_RULE + " " + OPPOSING_SIDE_RULE + " "
        "Background is limited to client identity and genuinely matter-wide "
        "procedural status; scope every right-specific fact with about entries."))


def schema_for(quotable: Quotable, *,
               thread_ids: frozenset[str] = frozenset()) -> dict:
    """The contract, with every closed answer space named.

    A UNIT ID THAT IS NOT IN THE MESSAGE IS NOT A UNIT, and an ID that is not
    on this matter is not a dispute: both are enums, so the answer cannot be
    formed. `interpret` refuses them anyway -- a schema is the model's
    contract, not a proof about its output.
    """
    schema = deepcopy(DISPUTE_SCHEMA)
    sentence = schema["properties"]["sentences"]["items"]["properties"]
    sentence["unit"]["enum"] = list(source_units(quotable.words)) or ["S1"]
    about = sentence["about"]["items"]["properties"]
    about["dispute"]["enum"] = [NEW, UNDECIDED, *sorted(thread_ids)]
    return schema


@dataclass(frozen=True)
class _Entry:
    """One labelled sentence's claim that it concerns one dispute."""

    unit: str
    role: str
    other_side: int
    thing: int
    kind: str
    dispute: str

    @property
    def key(self) -> tuple:
        # ONE DISPUTE PER OTHER SIDE, THING AND KIND -- or the dispute on the file
        # the sentence names. Numbers from the reading's own lists, never text.
        if self.dispute not in (NEW, UNDECIDED):
            return ("file", self.dispute)
        return ("new", self.other_side, self.thing, self.kind)


def interpret(quotable: Quotable, data: dict, *,
              thread_ids: frozenset[str] = frozenset()) -> DisputeRead:
    """Turn the sentence labels into disputes, or REFUSE them.

    A refusal lands on CANNOT_TELL, never on CONTINUES. Falling back to
    "continues" would make every failed read a silent merge, which is the
    defect this module exists to close. A refusal names WHICH rule failed --
    the repair quotes it back to the model.
    """
    if not isinstance(data, dict):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the dispute read returned nothing usable")
    units = source_units(quotable.words)
    people = _people(data.get("people"), quotable)
    things = _things(data.get("things"))
    rows = data.get("sentences")
    if people is None or things is None or not isinstance(rows, list):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the people, things or sentences are not lists")

    entries: list[_Entry] = []
    roles: dict[str, str] = {}
    for position, row in enumerate(rows, 1):
        wrong = _sentence_refusal(position, row, units, roles, people, len(things),
                                  thread_ids)
        if wrong:
            return DisputeRead(Dispute.CANNOT_TELL, refused=wrong,
                               found=_found(entries, people, things))
        roles[row["unit"]] = row["role"]
        if row["role"] in _ABOUT_A_DISPUTE:
            for about in row["about"]:
                dispute = about["dispute"]
                if dispute == UNDECIDED and not thread_ids:
                    dispute = NEW   # nothing on the file to be undecided about
                entries.append(_Entry(row["unit"], row["role"], about["other_side"],
                                      about["thing"], about["kind"], dispute))
    missing = [key for key in units if key not in roles]
    if missing:
        return DisputeRead(Dispute.CANNOT_TELL, found=_found(entries, people, things),
                           refused="source units not labelled: " + ", ".join(missing))
    inconsistent = _placement_refusal(entries)
    if inconsistent:
        return DisputeRead(Dispute.CANNOT_TELL, found=_found(entries, people, things),
                           refused=inconsistent)

    focus = data.get("focus_thread_id") or ""
    if focus and (focus not in thread_ids
                  or not Quotable(turn=quotable.turn).accepts(data.get("focus_quote") or "")):
        return DisputeRead(Dispute.CANNOT_TELL, found=_found(entries, people, things),
                           refused="the requested focus is not source-bound to this matter")
    advance = bool(data.get("advance_quote")
                   and Quotable(turn=quotable.turn).accepts(data["advance_quote"]))
    answers = data.get("requirement_answers", [])
    answers = tuple(answers) if isinstance(answers, list) else ()

    background = tuple(units[k] for k in units if roles[k] == "background")
    background_ids = tuple(k for k in units if roles[k] == "background")
    instructions = tuple(units[k] for k in units if roles[k] == "instruction")
    instruction_ids = tuple(k for k in units if roles[k] == "instruction")
    groups, unanchored = _group(entries)
    if unanchored:
        return DisputeRead(Dispute.CANNOT_TELL, found=_found(entries, people, things),
                           refused=unanchored)
    client = next((p["name"] for p in people if p["is_client"] and p["name"]), "")
    described = _linked(tuple(_described(group, units, background_ids, client, people, things)
                              for group in groups), groups)
    doubts = _identity_doubts(described)
    if any(e.dispute == UNDECIDED for e in entries):
        verdict = Dispute.CANNOT_TELL
    elif any(group[0].key[0] == "new" for group in groups):
        verdict = Dispute.OPENS
    else:
        verdict = Dispute.CONTINUES
    return DisputeRead(verdict, described[0].quoted if described else "",
                       clean(data.get("why")), described=described,
                       focus_thread_id=focus, advance=advance,
                       requirement_answers=answers, instructions=instructions,
                       doubts=doubts, shared=background,
                       shared_unit_ids=background_ids,
                       instruction_unit_ids=instruction_ids,
                       unit_signatures=_unit_signatures(units, roles, entries,
                                                       people, things))


def _unit_signatures(units: dict[str, str], roles: dict[str, str],
                     entries: list[_Entry], people: list[dict],
                     things: list[str]) -> tuple[UnitSignature, ...]:
    """Compare meanings after resolving a model's local list numbers to names."""
    targets: dict[str, set[tuple[str, str, str, str]]] = {}
    for entry in entries:
        opponent = people[entry.other_side - 1]["name"] if entry.other_side else ""
        targets.setdefault(entry.unit, set()).add((
            fold(opponent), fold(things[entry.thing - 1]), entry.kind, entry.dispute))
    return tuple(UnitSignature(unit_id, text, roles[unit_id],
                               tuple(sorted(targets.get(unit_id, ()))))
                 for unit_id, text in units.items())


def _people(rows: object, quotable: Quotable) -> list[dict] | None:
    """The people list, each name in the advocate's own characters -- or blank.

    A name the advocate did not write, or one that names nobody ("he", "the
    other side"), is blanked rather than dropped: its NUMBER still identifies the
    same person across sentences, so the grouping holds; only the label loses a
    name nobody wrote.
    """
    from nm.legal_brain.understand.posture import names_nobody

    if not isinstance(rows, list):
        return None
    out = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        name = clean(row.get("name") if isinstance(row.get("name"), str) else "")
        if name and names_nobody(name):
            name = ""
        out.append({"name": snippet(quotable.verbatim(name), 60) if name else "",
                    "is_client": row.get("is_client") is True})
    return out


def _things(rows: object) -> list[str] | None:
    """What is contested, in the reading's words -- a label, not evidence: the
    evidence of each dispute is the advocate's sentences it holds."""
    if not isinstance(rows, list):
        return None
    return [snippet(clean(row.get("name") if isinstance(row, dict)
                          and isinstance(row.get("name"), str) else ""), 70)
            for row in rows]


def _sentence_refusal(position: int, row: object, units: dict[str, str],
                      seen: dict[str, str], people: list[dict], things: int,
                      thread_ids: frozenset[str]) -> str | None:
    """WHICH rule one labelled sentence breaks, or None."""
    if not isinstance(row, dict):
        return f"sentence entry {position} is not an entry"
    unit = row.get("unit")
    if not isinstance(unit, str) or unit not in units:
        return f"sentence entry {position} names a source unit that is not in the message"
    if unit in seen:
        return f"{unit} is labelled twice"
    if row.get("role") not in ROLES:
        return f"{unit} has no role this reading knows"
    about = row.get("about")
    if not isinstance(about, list):
        return f"{unit}: 'about' is not a list"
    if row["role"] in _ABOUT_A_DISPUTE and not about:
        return f"{unit} is labelled {row['role']} but names no dispute it concerns"
    if row["role"] not in _ABOUT_A_DISPUTE and about:
        return f"{unit} is {row['role']} but also names a dispute it concerns"
    for item in about if row["role"] in _ABOUT_A_DISPUTE else ():
        if not isinstance(item, dict):
            return f"{unit}: a dispute it concerns is not an entry"
        other, thing = item.get("other_side"), item.get("thing")
        if type(other) is not int or not 0 <= other <= len(people):
            return f"{unit} names a person who is not in the people list"
        if other and people[other - 1]["is_client"]:
            return f"{unit} names the client as the other side of their own dispute"
        if type(thing) is not int or not 1 <= thing <= things:
            return f"{unit} names a thing that is not in the things list"
        if item.get("kind") not in KINDS:
            return f"{unit} names a kind of wrong this reading does not know"
        dispute = item.get("dispute")
        if not isinstance(dispute, str) or (dispute not in (NEW, UNDECIDED)
                                            and dispute not in thread_ids):
            return f"{unit} names a dispute that is not on this matter"
    return None


def _placement_refusal(entries: list[_Entry]) -> str | None:
    """A file ID and a contested right must each identify only one dispute.

    Grouping by an existing ID is otherwise able to merge different opponents,
    things or kinds even though the labels describe distinct work. Conversely,
    placing one right both on and off the file duplicates it. Neither assignment
    can be repaired by choosing a convenient row after the fact.
    """
    right_by_id: dict[str, tuple[int, str]] = {}
    opponents_by_id: dict[str, set[int]] = {}
    id_by_right: dict[tuple[int, int, str], str] = {}
    for entry in entries:
        if entry.dispute in (NEW, UNDECIDED):
            continue
        right = (entry.thing, entry.kind)
        if right_by_id.setdefault(entry.dispute, right) != right:
            return f"the file dispute {entry.dispute} is assigned to different contested rights"
        if entry.other_side:
            opponents_by_id.setdefault(entry.dispute, set()).add(entry.other_side)
            if len(opponents_by_id[entry.dispute]) > 1:
                return f"the file dispute {entry.dispute} is assigned to different opponents"
        if entry.role != "act":
            continue
        full_right = (entry.other_side, entry.thing, entry.kind)
        if id_by_right.setdefault(full_right, entry.dispute) != entry.dispute:
            return "one contested right is assigned to different disputes on the file"
    for entry in entries:
        if (entry.role == "act" and entry.dispute == NEW
                and (entry.other_side, entry.thing, entry.kind) in id_by_right):
            return "one contested right is labelled both new and already on the file"
    return None


def _group(entries: list[_Entry]) -> tuple[list[list[_Entry]], str | None]:
    """Only contested acts open new work; support must attach unambiguously.

    A named file dispute may receive facts, answers or remedies without a new
    act this turn. A new dispute needs an act from the advocate's source units.
    Supporting rows that omit the opponent inherit it only when one anchored
    group matches their thing and kind; ambiguity is returned for repair.
    """
    groups: dict[tuple, list[_Entry]] = {}
    for entry in entries:
        if entry.role == "act" or entry.dispute not in (NEW, UNDECIDED):
            groups.setdefault(entry.key, []).append(entry)
    for entry in entries:
        if entry.role == "act" or entry.dispute not in (NEW, UNDECIDED):
            continue
        if entry.dispute == NEW and entry.key in groups:
            matches = [groups[entry.key]]
        else:
            matches = [group for group in groups.values()
                       if (entry.dispute == UNDECIDED or group[0].key[0] == "new")
                       and _representative(group).thing == entry.thing
                       and _representative(group).kind == entry.kind
                       and (entry.other_side == 0
                            or _representative(group).other_side == entry.other_side)]
        if len(matches) != 1:
            reason = ("has no independently contested act to support"
                      if not matches else "could support multiple contested acts")
            return list(groups.values()), f"{entry.unit} is {entry.role} but {reason}"
        matches[0].append(entry)
    positions = {id(entry): position for position, entry in enumerate(entries)}
    ordered = sorted(groups.values(), key=lambda group: min(positions[id(e)] for e in group))
    return ordered, None


def _representative(group: list[_Entry]) -> _Entry:
    """An act names a new dispute; otherwise prefer a named file opponent."""
    return next((e for e in group if e.role == "act" and e.other_side),
                next((e for e in group if e.role == "act"),
                     next((e for e in group if e.other_side), group[0])))


def _described(group: list[_Entry], units: dict[str, str], background_ids: tuple[str, ...],
               client: str, people: list[dict], things: list[str]) -> Described:
    """One dispute: its sentences and the shared background, in the order the
    advocate wrote them."""
    ids = {e.unit for e in group}
    unit_ids = tuple(key for key in units if key in ids)
    allocation_unit_ids = tuple(key for key in units if key in ids or key in background_ids)
    words = list(dict.fromkeys(text for key, text in units.items()
                               if key in ids or key in background_ids))
    first = _representative(group)
    opponent = people[first.other_side - 1]["name"] if first.other_side else ""
    thing = things[first.thing - 1] or snippet(units[first.unit], 70)
    return Described(words[0], _label(client, opponent, thing),
                     "" if first.key[0] == "new" else first.dispute,
                     tuple(words[1:]), opponent, unit_ids=unit_ids,
                     allocation_unit_ids=allocation_unit_ids)


def _label(client: str, opponent: str, thing: str) -> str:
    """A file-cover name: "<client> v. <opponent> -- <thing contested>"."""
    if client and opponent:
        return f"{client} v. {opponent} — {thing}"
    if opponent:
        return f"Against {opponent} — {thing}"
    if client:
        return f"{client} — {thing}"
    return thing


def _linked(described: tuple[Described, ...],
            groups: list[list[_Entry]]) -> tuple[Described, ...]:
    """LINKED, NEVER MERGED: the same events (a sentence in both), the same
    thing (by number), or the same opponent (by number)."""
    out = []
    for i, d in enumerate(described):
        mine = _representative(groups[i])
        units_i = {e.unit for e in groups[i]}
        related = []
        for j, other in enumerate(groups):
            if i == j:
                continue
            theirs = _representative(other)
            if units_i & {e.unit for e in other}:
                related.append((j, "the same events"))
            elif mine.key[0] == theirs.key[0] == "new" and mine.thing == theirs.thing:
                related.append((j, "the same thing"))
            elif (mine.key[0] == theirs.key[0] == "new" and mine.other_side
                  and mine.other_side == theirs.other_side):
                related.append((j, "the same opponent"))
        out.append(replace(d, related=tuple(related)))
    return tuple(out)


def _found(entries: list[_Entry], people: list[dict], things: list[str]) -> tuple[str, ...]:
    """The disputes a refused reading would have formed, as lines to show."""
    lines = []
    candidates: dict[tuple, _Entry] = {}
    for entry in entries:
        candidates.setdefault(entry.key, entry)
    for first in candidates.values():
        thing = things[first.thing - 1] if 0 < first.thing <= len(things) else ""
        who = (people[first.other_side - 1]["name"]
               if 0 < first.other_side <= len(people) else "")
        if thing:
            lines.append(f"{thing} (against {who})" if who else thing)
    return tuple(dict.fromkeys(lines))


def _identity_doubts(described: tuple[Described, ...]) -> tuple[str, ...]:
    """A board cannot silently certify two entries with the same visible name.

    The two rights may genuinely differ in kind, or a reading may have split one
    claim twice. Keep both source-bound entries and ask which it is; a duplicate
    label alone cannot settle that semantic question.
    """
    labels: dict[str, list[int]] = {}
    for position, entry in enumerate(described, 1):
        labels.setdefault(fold(entry.label), []).append(position)
    return tuple(
        f"entries {', '.join(map(str, positions))} have the same name "
        f"‘{described[positions[0] - 1].label}’; please confirm how they differ"
        for positions in labels.values() if len(positions) > 1)


# ============================ reading twice ==================================

def separate(read, quotable: Quotable, *,
             thread_ids: frozenset[str] = frozenset()) -> DisputeRead:
    """THE PROCEDURE, ONE OWNER: read, repair once, read again reversed, compare.

    `read(prompt, schema)` returns the model's answer as a dict. The served turn
    and the measurement of it both call this, so they cannot read differently.
    A model failure on the FIRST reading or its repair propagates to the caller;
    one on the second is recorded in `second`, because the first reading stands.

    The second reading runs wherever two or more source units can change order.
    Where both readings stand and separate the message
    differently, the FINER one is used -- a wrong split is one sentence to fix, a
    wrong merge is silent -- and the difference is carried as `doubts`, to be
    said and asked.
    """
    from nm.shared.model_port import ModelError

    prompt = build_prompt(quotable)
    schema = schema_for(quotable, thread_ids=thread_ids)
    first = interpret(quotable, read(prompt, schema), thread_ids=thread_ids)
    if first.refused:
        again = interpret(quotable, read(repair_prompt(prompt, first.refused), schema),
                          thread_ids=thread_ids)
        if again.refused:
            return replace(again, found=again.found or first.found)
        first = again
    if len(source_units(quotable.words)) < 2:
        return replace(first, second="not needed: one source unit")
    try:
        second = interpret(quotable, read(build_prompt(quotable, reverse=True), schema),
                           thread_ids=thread_ids)
    except ModelError as exc:
        return replace(first, second=f"could not run: {exc}", doubts=(*first.doubts,
                       "the independent dispute reading could not run; the separation remains unconfirmed"))
    if second.refused:
        return replace(first, second=f"refused: {second.refused}", doubts=(*first.doubts,
                       "the independent dispute reading was refused; the separation remains unconfirmed"))
    return compare(first, second)


def compare(first: DisputeRead, second: DisputeRead) -> DisputeRead:
    """The finer of two readings, with what the other one joined as doubts.

    A sentence called shared background by one reading and scoped to a dispute
    by the other changes which thread receives it. That disagreement must not
    vanish merely because the partitions of their remaining common units agree.
    """
    first_owned, second_owned = _own(first), _own(second)
    first_shared = _scope(first.shared_unit_ids, first.shared)
    second_shared = _scope(second.shared_unit_ids, second.shared)
    first_instructions = _scope(first.instruction_unit_ids, first.instructions)
    second_instructions = _scope(second.instruction_unit_ids, second.instructions)
    common = first_owned & second_owned
    a, b = _partition(first, common), _partition(second, common)
    semantic_doubts = _signature_doubts(first, second)
    same_partition = sorted(map(sorted, a)) == sorted(map(sorted, b))
    if (first_owned == second_owned and first_shared == second_shared
            and first_instructions == second_instructions
            and same_partition and not semantic_doubts):
        return replace(first, doubts=tuple(dict.fromkeys((*first.doubts, *second.doubts))),
                       second="agreed")
    if (len(first.described), len(first_owned), -len(first_shared)) >= (
            len(second.described), len(second_owned), -len(second_shared)):
        chosen, other = first, second
    else:
        chosen, other = second, first
    mine, theirs = _partition(chosen, common), _partition(other, common)
    doubts = (["one reading places part of your account on a particular "
               "dispute; the other leaves it outside that dispute"]
              if first_owned != second_owned else [])
    if first_shared != second_shared:
        doubts.append("one reading treats part of your account as shared "
                      "background; the other gives it a different role")
    if first_instructions != second_instructions:
        doubts.append("one reading treats part of your account as an "
                      "instruction; the other gives it a different role")
    doubts.extend(semantic_doubts)
    moved_support = _support_scope_doubt(first, second, first_owned, second_owned,
                                          same_partition)
    if moved_support:
        doubts.append(moved_support)
    else:
        for block in theirs:
            joined = sorted({n for n, mine_block in enumerate(mine) if block & mine_block})
            if len(joined) > 1:
                names = [chosen.described[n].label for n in joined]
                doubts.append("a second reading of your message treated "
                              + " and ".join(f"‘{name}’" for name in names)
                              + " as one dispute")
        for n, block in enumerate(mine):
            split = [b for b in theirs if b & block]
            if len(split) > 1:
                doubts.append(f"a second reading divided ‘{chosen.described[n].label}’ "
                              f"into {len(split)} disputes")
    return replace(chosen, doubts=tuple(dict.fromkeys((*first.doubts, *second.doubts,
                                                     *doubts))) or (
        "a second reading of your message separated it differently",), second="disagreed")


def _signature_doubts(first: DisputeRead, second: DisputeRead) -> list[str]:
    """A matching source partition does not establish matching legal labels.

    Older hand-authored readings have no source signatures and retain their
    original partition-only comparison. New readings resolve model list numbers
    to names before this check.
    """
    if not first.unit_signatures or not second.unit_signatures:
        return []
    left = {unit.unit_id: unit for unit in first.unit_signatures}
    right = {unit.unit_id: unit for unit in second.unit_signatures}
    if left.keys() != right.keys():
        return ["the readings do not account for the same source sentences"]
    doubts = []
    for unit_id, one in left.items():
        two = right[unit_id]
        quote = f"‘{snippet(one.text, 90)}’"
        if one.role != two.role:
            doubts.append(f"the readings give {quote} different roles: "
                          f"{_role_name(one.role)} versus {_role_name(two.role)}")
        if one.targets == two.targets:
            continue
        if not one.targets or not two.targets:
            continue  # role and background/instruction scope doubts explain this
        dimensions = (
            (0, "opposing parties"),
            (1, "things in contest"),
            (2, "kinds of wrong"),
            (3, "new or existing dispute placement"),
        )
        changed = False
        for index, name in dimensions:
            if {target[index] for target in one.targets} != {
                    target[index] for target in two.targets}:
                doubts.append(f"the readings assign different {name} to {quote}")
                changed = True
        if not changed:
            doubts.append(f"the readings associate {quote} with different disputes")
    return doubts


def _role_name(role: str) -> str:
    return {
        "act": "a contested act", "answer": "a party's answer",
        "fact": "a supporting fact", "remedy": "a requested remedy",
        "background": "shared background", "instruction": "an instruction",
    }.get(role, role)


def _support_scope_doubt(first: DisputeRead, second: DisputeRead,
                         first_owned: set[tuple[str, str]],
                         second_owned: set[tuple[str, str]],
                         same_partition: bool) -> str | None:
    """A support unit can move while the independently contested acts stay put.

    In that case a merge/split warning misstates the disagreement. Preserve the
    two dispute entries and ask which one receives the supporting material.
    """
    if (same_partition or first_owned != second_owned or not first.unit_signatures
            or not second.unit_signatures):
        return None
    first_acts = {("unit", unit.unit_id) for unit in first.unit_signatures
                  if unit.role == "act"}
    second_acts = {("unit", unit.unit_id) for unit in second.unit_signatures
                   if unit.role == "act"}
    if (not first_acts or first_acts != second_acts
            or sorted(map(sorted, _partition(first, first_acts)))
               != sorted(map(sorted, _partition(second, second_acts)))):
        return None

    def attachments(read: DisputeRead) -> dict[tuple[str, str], set[frozenset]]:
        out: dict[tuple[str, str], set[frozenset]] = {}
        for described in read.described:
            owned = _owned(read, described)
            anchors = frozenset(owned & first_acts)
            for source in owned - first_acts:
                out.setdefault(source, set()).add(anchors)
        return out

    left, right = attachments(first), attachments(second)
    moved = next((source for source in sorted(first_owned - first_acts)
                  if left.get(source) != right.get(source)), None)
    if moved:
        words = next((unit.text for unit in first.unit_signatures
                      if ("unit", unit.unit_id) == moved), "")
        if words:
            return (f"the readings place ‘{snippet(words, 90)}’ with different "
                    "disputes; please confirm which contest it supports")
    return ("the readings place supporting material with different disputes; "
            "please confirm which contest it supports")


def _owned(read: DisputeRead, described: Described) -> set[tuple[str, str]]:
    """Use occurrence IDs for read-generated rows; retain old callers' spans.

    Hand-authored `Described` values predate unit IDs and can still be compared
    by text. The two namespaces cannot accidentally equate an ID to its text.
    """
    if described.unit_ids:
        return {("unit", unit_id) for unit_id in described.unit_ids}
    return {("text", span) for span in described.spans if span not in read.shared}


def _scope(unit_ids: tuple[str, ...], words: tuple[str, ...]) -> set[tuple[str, str]]:
    """Occurrence identity for new reads; text fallback for older constructed reads."""
    if unit_ids:
        return {("unit", unit_id) for unit_id in unit_ids}
    return {("text", word) for word in words}


def _own(read: DisputeRead) -> set[tuple[str, str]]:
    return {source for d in read.described for source in _owned(read, d)}


def _partition(read: DisputeRead, keep: set[tuple[str, str]]) -> list[set[tuple[str, str]]]:
    """Each dispute's own source occurrences within `keep`, empty ones dropped."""
    blocks = [_owned(read, d) & keep for d in read.described]
    return [block for block in blocks if block]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _paragraph_units(words: str) -> list[list[str]]:
    """The source unit IDs of each paragraph of `words`, in order."""
    units = source_units(words)
    blocks, keys = [], iter(units)
    for paragraph in _paragraphs(words):
        count = len(source_units(paragraph))
        blocks.append([next(keys) for _ in range(count)])
    blocks.append(list(keys))   # anything left over (none, in practice)
    return [b for b in blocks if b]


def source_units(message: str) -> dict[str, str]:
    """Literal addressable spans; splitting does not classify their substance."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", message) if p.strip()]
    return {f"S{i}": value for i, value in enumerate(parts, 1)}


def pending_accounts(matter, current_turn: str) -> tuple:
    """Original accounts not yet fully allocated, never generated summaries.

    Repeated failed submissions are one recovery population. Superseded accounts
    and fully placed accounts do not return. This does not decide their meaning.

    AN ACCOUNT WHOSE READING PLACED IT IS PLACED, even where some of its units
    were deliberately charted nowhere -- an instruction ("please assess every
    dispute") is never a fact of any dispute, and a reading that succeeds has
    labelled every unit. Judged by its words alone, such an account would be
    offered back as unplaced on every later turn, and its sentences read again
    as new disputes.
    """
    scoped_ids = {fid for thread in matter.threads for fid in thread.chronology}
    # Superseded scoped facts were placed too; their original account must not
    # resurrect them merely because they no longer appear in a live chart.
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
