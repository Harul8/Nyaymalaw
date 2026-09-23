"""Does this message continue the dispute on the file, or open another one?

WHY THIS EXISTS
---------------
`backend/nm/core/threading.py` could only ever create a second thread when the advocate
supplied a NUMBER OF RECORD. With one thread on the file and no case number in
the message, rule 5 bound to it and called that a continuation — *"there is
nothing to be wrong about"*.

There is. Measured, on a matter driven three turns:

    a cheque complaint filed against him   -> he is the ACCUSED
    a Labour Court claim by a fitter       -> he is the RESPONDENT EMPLOYER
    his own recovery suit for 11 lakhs     -> he is the PLAINTIFF

One thread. `role=accused, side=defending`. The product would advise his own
recovery suit as though he were defending it — which is the measured original
defect, arriving through the binder instead of through the posture reader.

And it was unreachable any other way: since only an identifier could open a
second thread, a matter could not hold two disputes unless the advocate typed a
case number. The golden set calls multi-thread files *the normal case*.

THE ASYMMETRY DECIDES THE DEFAULT, and `threading.py` states it at the top of
its own docstring: a wrong SPLIT duplicates work, is visible, and is corrected
in a turn. A wrong MERGE attaches one thread's posture, chronology and
limitation to facts they do not govern, every citation stays correct, the board
looks tidier, and the advice inverts silently.

So this never guesses toward merging. Three answers, and the third is not a
failure state:

    CONTINUES    bind, as before
    OPENS        a new thread, stated so the advocate can correct it
    CANNOT TELL  ASK — which is what rule 6 already does when several threads
                 are open and nothing is decisive. The question is the answer.

WHAT KEEPS IT HONEST
--------------------
The same two guards the posture read uses, for the same reason. The model must
QUOTE the words that make this a different dispute, and the span is checked
against what the ADVOCATE wrote — never against the prompt, which carries this
product's own questions and would otherwise let it quote itself.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from nm.core.requirements import ANSWER_ROWS, ANSWER_RULE
from nm.domain.quotable import Quotable
from nm.domain.text import fold, refuses_blank_text


class Dispute(str, Enum):
    """THREE STATES. The third is what makes the other two safe to act on."""

    CONTINUES = "continues"
    OPENS = "opens"
    CANNOT_TELL = "cannot_tell"


DISPUTE_SCHEMA: dict = {
    "x-nm-read": "dispute",
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [d.value for d in Dispute],
            "description": "'continues' if this message adds to the dispute "
                           "already on the file. 'opens' if it describes a "
                           "DIFFERENT dispute — a different proceeding, a "
                           "different opponent, or a different subject matter. "
                           "'cannot_tell' if it genuinely could be either.",
        },
        "quoted": {
            "type": "string",
            "description": "For 'opens', the EXACT words from the message that "
                           "show this is a different dispute. Must appear "
                           "verbatim. Empty for the other answers.",
        },
        "why": {
            "type": "string",
            "description": "One clause. Shown to the advocate so they can "
                           "correct it.",
        },
        # HOW MANY, NOT WHETHER. `verdict` answers a question that only
        # exists once the file holds something: does this add to THAT
        # dispute. On the first turn there is no THAT, so the read was
        # never made -- and one thread was created however many disputes
        # the advocate had just described.
        #
        # A brief that opens `first ... second ... third ...` is the
        # ordinary way a file is handed over, not an edge case.
        "disputes": {
            "type": "array",
            "description": "EVERY distinct dispute this message describes, "
                           "in the order they appear. A different "
                           "proceeding, a different opponent or a different "
                           "subject matter is a different dispute. One item "
                           "may be appropriate. Include existing disputes receiving "
                           "new facts, answers or instructions, with their thread IDs. "
                           "Empty only for pure navigation with no substantive update.",
            "items": {
                "type": "object",
                "properties": {
                    "quoted": {
                        "type": "string",
                        "description": "The EXACT words from the message "
                                       "that describe THIS dispute. Must "
                                       "appear verbatim. Prefer span_ids and leave this empty.",
                    },
                    "label": {
                        "type": "string",
                        "description": "A few words naming it, as an "
                                       "advocate would on a file cover.",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": ("Existing dispute ID when these instructions belong to it; "
                                        "empty only for a genuinely new dispute. Never merge IDs."),
                    },
                    "additional_quotes": {
                        "type": "array", "items": {"type": "string"},
                        "description": ("Other exact spans belonging to THIS dispute, including "
                                        "facts, corrections and requests. Shared instructions "
                                        "must apply to this dispute."),
                    },
                    "span_ids": {
                        "type": "array", "items": {"type": "string"},
                        "description": "IDs of ALL source units relevant to this dispute, "
                                       "including shared representation and task instructions. "
                                       "Use these rather than recopying long quotations.",
                    },
                },
                "required": ["quoted", "label", "thread_id", "additional_quotes", "span_ids"],
                "additionalProperties": False,
            },
        },
        "focus_thread_id": {"type": "string", "description":
                            "Existing dispute expressly prioritised by the advocate, else empty."},
        "focus_quote": {"type": "string", "description":
                        "Exact current words instructing that focus, otherwise empty."},
        "advance_quote": {"type": "string", "description":
                          "Exact request to continue the whole-file review or the next dispute, "
                          "else empty. Not an acknowledgement, fact or request to stop."},
        "requirement_answers": ANSWER_ROWS,
    },
    "required": ["verdict", "quoted", "why", "disputes", "focus_thread_id", "focus_quote",
                 "advance_quote", "requirement_answers"],
    # STRICT MODE REQUIRES IT. Without `additionalProperties: false` on
    # every object the provider cannot compile the grammar, and the
    # schema silently degrades to a hint.
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate is briefing a matter. You are told what is already on "
    "the file and what they have just said. First inventory the ENTIRE current "
    "message, including its opening, middle and final subjects. Only then "
    "decide which entries continue existing disputes and which open new ones. "
    "Different subjects within the current message are not existing file records. "
    "An empty existing inventory means none is already recorded.\n\n"
    "A different dispute means a different proceeding, a different opponent, "
    "or a different subject matter, assessed in context. Do not equate additional "
    "facts or legal issues within one dispute with another dispute.\n\n"
    "Adding detail to what is already there — a date, a name, a document, an "
    "answer to a question — CONTINUES. So does asking what to do about it.\n\n"
    "Answer 'cannot_tell' where it genuinely could be either. That is a real "
    "answer and it is better than a wrong one: the advocate will be asked, and "
    "they know.\n\n"
    "Map all substantive instructions in this message to the existing dispute "
    "IDs supplied in context, or identify genuinely new disputes. A clarification, "
    "correction, renamed description or new argument is not by itself a new dispute. "
    "A single dispute can contain several remedies, defences and evidential issues. "
    "An explicit instruction to split independently contested rights out of an "
    "existing entry is a request to reorganise the board, not merely add detail. "
    "Represent each requested separate working dispute, using the existing ID only "
    "for the entry that remains; do not report the unchanged inventory as the split. "
    "This organisational change does not establish facts or erase prior records. "
    "Never silently merge existing disputes. Where allocation is genuinely unclear, "
    "return cannot_tell rather than create a duplicate to avoid the question.\n\n"
    "An advocate handing over a file commonly describes several disputes "
    "at once. Keep independently described disputes distinct while recognising "
    "shared parties, evidence and events. Enumeration alone is not proof that "
    "the underlying disputes are separate.\n\n"
    "Only supplied verbatim advocate words may support allocation, including "
    "explicitly labelled earlier accounts still awaiting placement. Never use "
    "a paraphrase, generated summary or file label as factual evidence.\n\n"
    "Include continuing disputes when assigning a date, correction or answer; "
    "collect all exact relevant spans, not just a label-sized fragment. Preserve "
    "different chronologies and positions. Map explicitly shared instructions to "
    "each affected dispute, never copy unrelated facts across them. For a pure "
    "navigation instruction leave disputes empty and quote the requested focus or "
    "advance. The agenda is a suggestion, not permission to override the advocate. "
    "Account for every paragraph in the message through its relevant exact spans. "
    "Include shared representation, proposed-claim or defence instructions, limits "
    "on authority and the immediate question in the allocation for each affected "
    "dispute. Do not discard those instructions when separating factual accounts. "
    "A statement that nothing has been filed is not a statement that the client "
    "has no prospective claim. Do not add unrelated parties or events to make "
    "an allocation appear complete. Source units below have stable IDs for THIS "
    "message only. Allocate their IDs; the application copies the original text. "
    "Account for every source unit, allocating shared instructions to every "
    "affected dispute. Source-unit boundaries do not determine dispute boundaries: "
    "organise by independent subject, contested right, opponent and timeline."
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
    focus_thread_id: str = ""
    advance: bool = False
    requirement_answers: tuple[dict, ...] = ()
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


def build_prompt(quotable: Quotable):
    """What is on the file, and what was just said.

    THE FILE IS CONTEXT AND THE MESSAGE IS THE EVIDENCE (B-108). Opening a
    thread is the answer that creates something, so it carries a quotation --
    and a span lifted out of the file would let an old dispute open a new
    thread. The guard has always said so; the prompt now does too.
    """
    from nm.ports.model import Prompt

    # BOTH QUESTIONS ARE ASKED, and the closing line is the last thing the
    # model reads. It used to close on the binary one alone -- "does this
    # continue that dispute, or open a different one?" -- and against the
    # brief that found BK-27 the model answered exactly that and returned
    # an EMPTY list of disputes. The schema and the system text both
    # described the second question; nothing at the point of asking did.
    return Prompt(
        system=(SYSTEM + "\nFor this structured read, source_allocations is the authoritative "
                "allocation: for EVERY source unit give the 1-based positions of the disputes "
                "it belongs to. Shared representation and questions can belong to several. "
                "Do not reproduce quotations. Leave the top-level quoted field empty; source "
                "allocations supply the exact evidence. Every substantive unit needs an "
                "allocation. Do not combine independently contested rights just because the "
                "opponent is the same; their subject and chronology can differ."),
        user=(f"{quotable.block()}\n\n"
              "SOURCE UNITS (current message, then unallocated earlier account; "
              "IDs are not quotation):\n"
              + "\n".join(f"{key}: {value}" for key, value in source_units(quotable.words).items())
              + "\n\n"
              "1. Inventory the whole current message. Allocate each substantive "
              "instruction to its existing dispute ID "
              "or a genuinely new dispute, with all relevant exact spans. "
              "Include shared instructions on every affected entry.\n"
              "2. Then classify its relationship to the existing file, not "
              "between subjects within the message. Distinguish clarification "
              "from new work. Record explicit focus or "
              "a request to advance separately; never infer either from an acknowledgement. "
              "Earlier unallocated accounts are evidence awaiting placement, NOT new commands. "
              "Only the current message controls focus, advance and checklist answers. "
              "Resolve earlier accounts against the current clarification without opening "
              "duplicates of the existing disputes."))


def schema_for(quotable: Quotable, *,
               thread_ids: frozenset[str] = frozenset()) -> dict:
    """Make omission of a source unit a schema error, without dictating its meaning.

    AN ENTRY MAY NAME ONLY A DISPUTE THIS MATTER HOLDS. `interpret` refuses
    one that does not ("a dispute ID is not on this matter"); naming the
    permitted values here means the model is never shown an ID it could offer
    wrongly. Empty always belongs: it is how a genuinely new dispute says so.

    THE VERDICT IS DELIBERATELY NOT NARROWED, and the reason is worth keeping.
    On 22 September 2026 a four-dispute brief was refused with "the inventory
    marks new disputes but the verdict denies new work", and removing
    `continues` from the enum on a file with no disputes looked like the fix.
    It is not: `continues` with NO described entries is how an ordinary
    single-dispute matter opens -- the message adds detail, nothing is
    separated out, and `bind` creates the first thread. Narrowing the enum
    broke that path and six tests with it.

    What is actually contradictory is `continues` TOGETHER WITH entries that
    carry no thread_id, which is a cross-field condition a JSON enum cannot
    state. `interpret` owns it and keeps owning it.

    THE GUARDS IN `interpret` STAY REGARDLESS. A schema is the model's
    contract, not a proof about its output -- a provider that does not enforce
    enums, a repaired payload, a future caller. The schema stops inviting an
    answer; the guard still refuses it.
    """
    schema = deepcopy(DISPUTE_SCHEMA)
    props = schema['properties']
    props['verdict']['description'] = (
        "opens if ANY inventory entry is genuinely new (empty thread_id), even when other "
        "entries continue existing disputes. continues only when ALL entries match existing "
        "thread IDs. cannot_tell if the distinction remains genuinely uncertain.")
    props['quoted'] = {'type': 'string', 'enum': [''],
                       'description': 'Exact evidence comes from source_allocations.'}
    item = props['disputes']['items']
    item['properties'] = {k: v for k, v in item['properties'].items()
                          if k in ('label', 'thread_id')}
    # AN ID THAT IS NOT ON THIS MATTER IS NOT AN ID. `interpret` refuses one
    # ("a dispute ID is not on this matter"); naming the permitted values here
    # means the model cannot offer one in the first place. Empty always
    # belongs: it is how a genuinely new dispute says so.
    item['properties']['thread_id'] = {
        **item['properties'].get('thread_id', {'type': 'string'}),
        'enum': ['', *sorted(thread_ids)]}
    item['required'] = ['label', 'thread_id']
    props['source_allocations'] = {
        'type': 'object', 'additionalProperties': False,
        'properties': {key: {'type': 'array', 'items': {'type': 'integer', 'minimum': 1},
                             'description': text}
                       for key, text in source_units(quotable.words).items()},
        'required': list(source_units(quotable.words)),
    }
    schema['required'].append('source_allocations')
    return schema


def fixed_allocation_repair(quotable: Quotable, data: dict, threads):
    """Repair links over known targets plus the reader's proposed new entries.

    The model no longer has to invent an array and index that changing array in
    the same answer. This does not invent disputes or relax source coverage.
    """
    from nm.ports.model import Prompt

    ids = {t.id for t in threads}
    rows = data.get('disputes', [])
    if (not rows or not isinstance(rows, list)
            or any(not isinstance(r, dict) or not isinstance(r.get('label'), str)
                   or not r['label'].strip() or r.get('thread_id') not in {'', *ids}
                   for r in rows)):
        return None
    existing = [r['thread_id'] for r in rows if r['thread_id']]
    new = [r for r in rows if not r['thread_id']]
    # A DUPLICATED EXISTING ID MAKES THE TABLE ITSELF WRONG, so there is
    # nothing to constrain against and this still declines.
    if len(existing) != len(set(existing)):
        return None
    # A VERDICT MAY BE CORRECTED WHERE IT UNDER-CLAIMS, NEVER WHERE IT
    # OVER-CLAIMS, and the asymmetry is the whole rule.
    #
    # This used to require `verdict == ('opens' if new else 'continues')`
    # outright, so a first answer that got the verdict wrong AS WELL AS the
    # allocation fell through to the unconstrained schema and the model
    # repeated the same class of mistake -- the repair declining in exactly
    # the case that needed it. Measured 22 September 2026 on one four-dispute
    # brief: "the inventory marks new disputes but the verdict denies new
    # work", then "the allocation for S1 names dispute 6, and this inventory
    # has 5", which is the failure this function's own docstring describes.
    #
    # UNDER-CLAIMING IS RECOVERABLE: rows carrying new work and a verdict of
    # `continues` disagree, and the rows are the evidence -- repairing adds
    # nothing and drops nothing, and `apply_fixed_allocation` derives `opens`
    # from the table.
    #
    # OVER-CLAIMING IS NOT. `opens` with no new row means the model says there
    # is new work its own inventory does not show, and the likeliest reading
    # is that a dispute was OMITTED. Deriving `continues` there would silently
    # drop it -- the wrong-merge defect, which is the worst outcome in this
    # module and what `test_repair_keeps_source_supported_new_work_and_refuses
    # _to_drop_it` exists for. So that one still declines, and the read is
    # refused rather than quietly reconciled.
    if not new and data.get('verdict') == Dispute.OPENS.value:
        return None
    table = [{'label': t.label, 'thread_id': t.id} for t in threads]
    table.extend({'label': r['label'], 'thread_id': ''} for r in new)
    schema = schema_for(quotable)
    alloc = schema['properties']['source_allocations']
    for value in alloc['properties'].values():
        value['items'] = {'type': 'integer', 'enum': list(range(1, len(table) + 1))}
        value['minItems'] = 1
    schema['properties'] = {
        'source_allocations': alloc,
        'focus_thread_id': {'type': 'string', 'enum': ['', *[t.id for t in threads]]},
        'focus_quote': {'type': 'string', 'enum': ['', *source_units(quotable.turn).values()]},
    }
    schema['required'] = list(schema['properties'])
    schema['x-nm-fixed-inventory'] = table
    prompt = build_prompt(quotable)
    prompt = Prompt(system=prompt.system + "\nThis is a link repair over a FIXED inventory. "
                    "Return allocations and current explicit focus. Copy a full current "
                    "source unit for focus_quote, or leave BOTH focus fields empty. "
                    "Use only the fixed numbered targets; no new rows. The proposed new "
                    "entries are NOT established facts. Every proposed new entry must have "
                    "support in the advocate's actual words or this repair must fail. "
                    "Read each source unit against EVERY target, not only target 1. "
                    "A unit may contain several disputes; allocate it to each affected target. "
                    "Shared representation or authority instructions reach all affected entries.",
                    user=prompt.user + "\nFIXED TARGETS:\n" + "\n".join(
                        f"{i}: {r['label']} ({r['thread_id']})" for i, r in enumerate(table, 1)))
    return prompt, schema, table


def apply_fixed_allocation(data: dict, repaired: dict, table: list) -> dict:
    """Keep targeted rows; never silently discard proposed new work in repair."""
    allocation = repaired.get('source_allocations', {})
    if (not isinstance(allocation, dict)
            or any(not isinstance(v, list) or not v
                   or any(type(i) is not int or not 1 <= i <= len(table) for i in v)
                   for v in allocation.values())):
        return {**data, 'source_allocations': {}}
    used = sorted({i for values in allocation.values() for i in values})
    if any(i not in used for i, row in enumerate(table, 1) if not row['thread_id']):
        return {**data, 'source_allocations': {}}
    new_index = {old: n for n, old in enumerate(used, 1)}
    kept = [table[i - 1] for i in used]
    # DERIVED, NOT CARRIED. The verdict is a function of the rows that
    # survived the repair -- anything without a thread_id is new work -- and
    # carrying the first answer's verdict through was how a repaired
    # allocation kept the contradiction that sent it for repair. Asking a
    # model for a value determined by its own other answers is asking it to
    # contradict itself; here the table is known, so nobody needs to ask.
    verdict = 'opens' if any(not row['thread_id'] for row in kept) else 'continues'
    return {**data, 'disputes': kept, 'quoted': '', 'verdict': verdict,
            'focus_thread_id': repaired.get('focus_thread_id', ''),
            'focus_quote': repaired.get('focus_quote', ''),
            'source_allocations': {key: [new_index[i] for i in values]
                                   for key, values in allocation.items()}}


def _allocation_refusal(rows: object, allocations: object,
                        units: dict) -> str | None:
    """WHICH allocation rule failed, or None. Never "one of five things".

    THE OLD MESSAGE WAS ONE SENTENCE FOR FIVE CONDITIONS -- *each source unit
    must have a valid dispute allocation* -- and a refusal that names its
    family instead of its member cannot be diagnosed from the record it
    leaves. Measured 22 September 2026: a four-dispute brief failed here,
    twice, through the bounded repair; the transcript said only that sentence,
    and the next session had to re-run a live matter to find out which rule
    had fired. A check that knows exactly what is wrong and reports a
    category is spending the diagnosis it already computed.

    IT IS ALSO WHAT THE REPAIR READS. The feedback prompt quotes
    `read.refused` back to the model, so "one of these five" is the
    instruction the model gets; naming the member makes the second attempt
    address the thing that actually failed.
    """
    if not isinstance(rows, list):
        return "the dispute inventory is not a list of entries"
    if not isinstance(allocations, dict):
        return "the source allocation is not a mapping of source unit to disputes"
    missing = sorted(set(units) - set(allocations))
    unknown = sorted(set(allocations) - set(units))
    if missing or unknown:
        said = []
        if missing:
            said.append("no allocation for " + ", ".join(missing))
        if unknown:
            said.append("allocated a source unit that is not in the message: "
                        + ", ".join(unknown))
        return "; ".join(said)
    for key in sorted(allocations):
        targets = allocations[key]
        if not isinstance(targets, list):
            return f"the allocation for {key} is not a list of dispute numbers"
        if rows and not targets:
            return f"{key} was allocated to no dispute"
        for i in targets:
            # `type(i) is not int` and NOT `isinstance`: `True` is an `int`
            # and a bool here would index row 1 on every truthy answer.
            if type(i) is not int:
                return (f"the allocation for {key} names {i!r}, which is not a "
                        f"dispute number")
            if not 1 <= i <= len(rows):
                return (f"the allocation for {key} names dispute {i}, and this "
                        f"inventory has {len(rows)}")
    return None


def interpret(quotable: Quotable, data: dict, *,
              thread_ids: frozenset[str] = frozenset()) -> DisputeRead:
    """Turn the model's answer into a verdict, or REFUSE it.

    A refusal lands on CANNOT_TELL, never on CONTINUES. Falling back to
    "continues" would make every failed read a silent merge, which is the
    defect this module exists to close.
    """
    if not isinstance(data, dict):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the dispute read returned nothing usable")

    raw = (data.get("verdict") or "").strip().lower()
    try:
        verdict = Dispute(raw)
    except ValueError:
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused=f"the model answered {raw!r}, which is not "
                                   f"an answer to this question")

    why = (data.get("why") or "").strip()
    quoted = (data.get("quoted") or "").strip()

    # THE COUNT IS READ ON EVERY VERDICT, because the two answers are
    # about different things: `verdict` is this message against the FILE,
    # `described` is this message against ITSELF. A brief that opens three
    # disputes on an empty matter has no verdict worth having and three
    # threads to create.
    rows = data.get("disputes")
    allocations = data.get('source_allocations')
    if allocations is not None:
        wrong = _allocation_refusal(rows, allocations, source_units(quotable.words))
        if wrong:
            return DisputeRead(Dispute.CANNOT_TELL, refused=wrong)
    described = _described(quotable, data)
    if not isinstance(rows, list):
        return DisputeRead(Dispute.CANNOT_TELL, described=described,
                           refused="the dispute inventory is not a list of entries")
    if len(described) != len(rows):
        return DisputeRead(Dispute.CANNOT_TELL, described=described,
                           refused=f"{len(rows) - len(described)} of {len(rows)} dispute "
                                   f"entries were unreadable or unsupported by the source")
    if any(d.thread_id and d.thread_id not in thread_ids for d in described):
        return DisputeRead(Dispute.CANNOT_TELL, refused="a dispute ID is not on this matter")
    existing = [d.thread_id for d in described if d.thread_id]
    if len(existing) != len(set(existing)):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the inventory repeats one existing dispute as separate rows")
    if (allocations is not None and verdict is Dispute.CONTINUES
            and any(not d.thread_id for d in described)):
        return DisputeRead(Dispute.CANNOT_TELL, described=described,
                           refused="the inventory marks new disputes but the verdict denies "
                                   "new work; distinguish genuinely new entries from existing IDs")
    if described and (allocations is not None or any(row.get("span_ids") for row in rows)):
        allocated = {fold(s) for d in described for s in d.spans}
        missing = [key for key, text in source_units(quotable.words).items()
                   if not any(fold(text) in span for span in allocated)]
        if missing:
            return DisputeRead(Dispute.CANNOT_TELL, described=described,
                               refused="unallocated source units: " + ", ".join(missing))
    focus = data.get("focus_thread_id") or ""
    if focus and (focus not in thread_ids
                  or not Quotable(turn=quotable.turn).accepts(data.get("focus_quote") or "")):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the requested focus is not source-bound to this matter")
    advance = bool(data.get("advance_quote")
                   and Quotable(turn=quotable.turn).accepts(data["advance_quote"]))
    answers = data.get("requirement_answers", [])
    answers = tuple(answers) if isinstance(answers, list) else ()

    if verdict is not Dispute.OPENS:
        return DisputeRead(verdict, quoted, why, described=described,
                           focus_thread_id=focus, advance=advance, requirement_answers=answers)

    # OPENING A THREAD IS THE ANSWER THAT CREATES SOMETHING, so it carries the
    # evidence. `continues` and `cannot_tell` both leave the file as it was.
    if not quotable.accepts(quoted):
        if not quoted and (allocations is not None
                           or any(row.get("span_ids") for row in rows)) and described:
            # IDs select exact current-message text. This records organisation,
            # not a fact or an established procedural position.
            return DisputeRead(verdict, described[0].quoted, why, described=described,
                               focus_thread_id=focus, advance=advance,
                               requirement_answers=answers)
        # The span must be the ADVOCATE'S words. The file is CONTEXT on this
        # read and not quotable, because a span lifted from there would let an
        # old dispute open a new thread.
        return DisputeRead(Dispute.CANNOT_TELL, quoted, why,
                           refused=(f"the model said this opens a new dispute "
                                    f"and {quotable.refusal(quoted)}"))
    return DisputeRead(Dispute.OPENS, quoted, why, described=described,
                       focus_thread_id=focus, advance=advance, requirement_answers=answers)


def _described(quotable: Quotable, data: dict) -> tuple[Described, ...]:
    """The disputes the message describes, each checked against the
    advocate's own words.

    THE SAME GUARD AS THE SINGULAR ANSWER, applied per item and for the
    same reason: a span the advocate did not write settles nothing, and a
    span lifted out of the file would let an old dispute open a new
    thread. An item that fails the guard is DROPPED rather than kept with
    a warning -- a thread is created from these, and a thread created
    from words nobody wrote is worse than one not created.
    """
    rows = data.get("disputes")
    if not isinstance(rows, list):
        return ()
    out: list[Described] = []
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        allocations = data.get('source_allocations')
        ids = ([key for key, targets in allocations.items() if position in targets]
               if allocations is not None else row.get("span_ids", []))
        if not isinstance(ids, list):
            continue
        units = source_units(quotable.words)
        if ids:
            if any(not isinstance(key, str) or key not in units for key in ids):
                continue
            selected = tuple(dict.fromkeys(units[key] for key in ids))
            span, extra = selected[0], list(selected[1:])
        else:
            span = (row.get("quoted") or "").strip()
            extra = row.get("additional_quotes", [])
        label = (row.get("label") or "").strip()
        if not span or not label or not quotable.accepts(span):
            continue
        if not isinstance(extra, list) or any(
                not isinstance(s, str) or not quotable.accepts(s) for s in extra):
            continue
        target = row.get("thread_id", "")
        if not isinstance(target, str):
            continue
        out.append(Described(span, label, target, tuple(extra)))
    return tuple(out)


def source_units(message: str) -> dict[str, str]:
    """Literal addressable spans; splitting does not classify their substance."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", message) if p.strip()]
    return {f"S{i}": value for i, value in enumerate(parts, 1)}


def pending_accounts(matter, current_turn: str) -> tuple:
    """Original accounts not yet fully allocated, never generated summaries.

    Repeated failed submissions are one recovery population. Superseded accounts
    and fully placed accounts do not return. This does not decide their meaning.
    """
    scoped_ids = {fid for thread in matter.threads for fid in thread.chronology}
    # Superseded scoped facts were placed too; their original account must not
    # resurrect them merely because they no longer appear in a live chart.
    placed = [f for f in matter.facts if f.id in scoped_ids]
    seen, pending = set(), []
    for fact in matter.facts:
        if (fact.provenance.kind != "advocate_statement" or fact.provenance.span
                or fact.provenance.turn == current_turn or fact.superseded_by is not None):
            continue
        key = fold(fact.statement)
        spans = [fold(f.statement) for f in placed]
        if key in seen or all(any(fold(unit) in span for span in spans)
                              for unit in source_units(fact.statement).values()):
            continue
        seen.add(key)
        pending.append(fact)
    return tuple(pending)


def uncovered_paragraphs(message: str, read: DisputeRead) -> tuple[str, ...]:
    """Structural omission check, not a claim that semantic allocation is correct.

    Never manufacture a dispute from punctuation. A paragraph with no admitted
    span must be reconsidered by the same reader before its inventory is used.
    Pure navigation has no described inventory and is handled by its own fields.
    """
    if not read.described:
        return ()
    spans = [fold(s) for d in read.described for s in d.spans]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", message) if p.strip()]
    return tuple(p for p in paragraphs
                 if not any(s in fold(p) or fold(p) in s for s in spans))
