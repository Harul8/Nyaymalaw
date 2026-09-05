"""The date chart. C5.

WHAT IT IS FOR
--------------
A limitation position is arithmetic, and arithmetic on a guessed date is worse
than no arithmetic at all: it produces a number the advocate can act on, and
nothing downstream distinguishes it from one that was computed. The counter-
example C5 records is exactly that — *a client who said "yesterday" being asked
for the date twice, and a chart completed by guessing.*

Both halves are defects. The first is the repeat-question failure the matter
memory already refuses; the second is this module's whole subject.

THREE STATES, AND THE THIRD IS THE POINT
-----------------------------------------
    RESOLVED    the advocate's words fix a date, against a stated reference
    UNDATED     they name an event and no date. RECORDED AS UNDATED.
    CONFLICTED  two accounts give the event different dates, and BOTH are kept

`UNDATED` is not a failure path. An undated event is an ordinary thing on a
real file, and the chart says so rather than filling the gap — because a chart
with no holes in it reads as complete, and the hole is the thing the advocate
needs to see.

WHY A MODEL READS THE DATES, AND WHAT KEEPS THAT SAFE
------------------------------------------------------
"Yesterday", "28th August", "last Deepavali", "the Monday after the notice" —
there is no list of these. The same argument that removed the posture phrase
list applies, and so do the same two guards:

  1. THE SPAN MUST BE VERBATIM in what the ADVOCATE wrote. Checked against
     their words, never against the prompt — the prompt carries the file and
     this product's own questions, and a span lifted from there would let the
     product date an event out of its own text (B-035).

  2. THE REFERENCE DATE IS STATED, never implicit. "Yesterday" is meaningless
     without it, and a resolution that cannot name what it counted from is a
     guess wearing a date's clothes. `EvidenceNeed` already refuses a query
     with no governing date for the same reason.

A resolution the model cannot support with a span lands on UNDATED. It never
lands on a date, because the one thing this module exists to prevent is a
number nobody can trace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.matter import Certainty, Fact, FactId
from nm.domain.text import refuses_blank_text

_WORDS = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


class DateState(str, Enum):
    """THREE STATES. `UNDATED` is an ordinary outcome, not a failure."""

    RESOLVED = "resolved"
    UNDATED = "undated"
    CONFLICTED = "conflicted"


DATE_SCHEMA: dict = {
    "x-nm-read": "dates",
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "description": "Every EVENT the advocate describes, in the order "
                           "they appear. An event with no date is still an "
                           "event and is still listed.",
            "items": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "What happened, in a short phrase. The "
                                       "advocate's own words where possible.",
                    },
                    "date_expression": {
                        "type": "string",
                        "description": "The EXACT words that give the date — "
                                       "'yesterday', '15 April', 'last "
                                       "Deepavali'. Copied character for "
                                       "character from the message. EMPTY if "
                                       "they gave no date for this event.",
                    },
                    "resolved": {
                        "type": "string",
                        "description": "The date as YYYY-MM-DD, worked out "
                                       "against the reference date given to "
                                       "you. EMPTY if the words do not fix a "
                                       "date — do NOT estimate, do NOT pick "
                                       "the middle of a range, and do not "
                                       "guess a year that was never said.",
                    },
                    "documented": {
                        "type": "boolean",
                        "description": "True only if the advocate says the "
                                       "date comes from a DOCUMENT. Their "
                                       "recollection is not a document.",
                    },
                    "corrects": {
                        "type": "string",
                        "description": "If this event REPLACES one already on "
                                       "the file, its id, copied exactly from "
                                       "the chronology you were given. Empty "
                                       "otherwise, which is the ordinary "
                                       "answer. Use it when they say the "
                                       "earlier entry was wrong — 'sorry, that "
                                       "is wrong', 'I meant', 'it is actually' "
                                       "— or when they give the same event a "
                                       "different date. A NEW event on a "
                                       "different day is NOT a correction.",
                    },
                },
                "required": ["event", "date_expression", "resolved",
                             "documented", "corrects"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    # STRICT MODE REQUIRES IT. Without `additionalProperties: false` on
    # every object the provider cannot compile the grammar, and the
    # schema silently degrades to a hint.
    "additionalProperties": False,
}

SYSTEM = (
    "You read an Indian advocate's account and list the EVENTS in it, with "
    "their dates where dates were given.\n\n"
    "NEVER ESTIMATE A DATE. If the words do not fix one, leave `resolved` "
    "empty and the event is recorded as undated — which is an ordinary thing "
    "on a real file. An invented date produces a limitation calculation the "
    "advocate will act on, and nothing downstream can tell it from a real one. "
    "'Some time last year', 'a few months ago' and 'around Diwali' do NOT fix "
    "a date. 'Last Deepavali' does, if you know the year's festival date; if "
    "you do not, leave it empty.\n\n"
    "`date_expression` is copied CHARACTER FOR CHARACTER from the message. It "
    "is what lets the advocate see what you read the date from.\n\n"
    "`documented` is true only where they say it comes from a document — a "
    "notice dated the 15th, a receipt, an order sheet. What they remember is "
    "asserted, however confidently they say it."
)


@refuses_blank_text("date_expression", "reference")
@dataclass(frozen=True)
class DatedEvent:
    """One row of the chart. The span is what makes the date auditable."""

    event: str
    state: DateState
    on: date | None = None
    date_expression: str = ""
    reference: str = ""
    certainty: Certainty = Certainty.ASSERTED
    refused: str | None = None
    corrects: str = ""
    """The id of the entry this REPLACES, or empty.

    On the row rather than in a separate read, because the sentence that
    identifies a correction is the same sentence the date was read out of. A
    second read had to rebuild that relationship from two ids without it, and
    returned nothing on one run of GS-15 — the answer then computed correctly
    from a date the advocate had withdrawn (B-088)."""

    @property
    def dated(self) -> bool:
        return self.state is DateState.RESOLVED and self.on is not None


@refuses_blank_text()
@dataclass(frozen=True)
class DateConflict:
    """One event, two dates, BOTH KEPT.

    C5 forbids resolving a conflict silently, and C1 forbids resolving one
    inside the account at all: keep both. A conflict is not a data problem to
    be cleaned up before the advocate sees it — it is frequently the most
    important thing on the file, because whichever date is right decides
    whether the claim is alive.
    """

    event: str
    left: date
    right: date
    left_fact: FactId
    right_fact: FactId

    def as_text(self) -> str:
        return (f"Two dates are on the file for {self.event!r}: "
                f"{self.left.isoformat()} and {self.right.isoformat()}. I have "
                f"kept both — which one is right decides the limitation "
                f"position, so it is not mine to pick.")


#: What an advocate writes when they are REPLACING something, not adding to it.
#:
#: This list DETECTS AN ATTEMPT. It never decides which entry is meant — that
#: is the read's job, and where the read comes back with nothing the product
#: ASKS. CLAUDE.md §5 forbids fuzzy matching that IDENTIFIES; putting a
#: question to the advocate identifies nothing, and four words from them
#: settles what no amount of scoring could.
#:
#: B-088: the read fires on one run and not the next on identical input, and a
#: miss was SILENT — both dates stayed live and the period ran from the
#: earlier one. A miss is a question now.
CORRECTING = (
    "sorry, that is wrong", "that is wrong", "that's wrong", "i meant",
    "it is actually", "it's actually", "correction:", "i was wrong",
    "not right", "should be", "rather than", "instead of", "my mistake",
    "apologies", "scratch that",
)


def looks_like_a_correction(message: str) -> str | None:
    """The phrase that says one is being made, or `None`.

    Returns the PHRASE rather than a boolean, so the question put to the
    advocate can quote their own words back — "you said 'sorry, that is
    wrong'" is answerable and "a correction was detected" is not.
    """
    lower = (message or "").lower()
    return next((p for p in CORRECTING if p in lower), None)


def build_prompt(message: str, reference: date, account: str = "",
                 existing: tuple = ()):
    """The message, the reference date, and what was already said.

    The reference is passed EXPLICITLY and appears in the prompt. "Yesterday"
    has no meaning without it, and a resolution that cannot say what it counted
    from is a guess with a date's confidence.
    """
    from nm.ports.model import Prompt

    user = (f"Today is {reference.isoformat()}. Resolve every relative date "
            f"against that.\n\n")
    if account.strip():
        user += (f"Already on the file:\n{account.strip()[:1500]}\n\n")
    if existing:
        # THE IDS, so `corrects` has something to name. Without them the field
        # cannot be filled and the read degrades to what it was before.
        rows = "\n".join(
            f"  {f.id}\t{f.date.isoformat() if f.date else 'undated'}\t"
            f"{f.statement[:70]}" for f in existing)
        user += (f"The chronology so far — if anything below is being "
                 f"REPLACED, name its id in `corrects`:\n{rows}\n\n")
    user += f"The advocate has just said:\n{message.strip()[:1500]}"
    return Prompt(system=SYSTEM, user=user)


def interpret(message: str, reference: date, data: dict,
              known: frozenset[str] = frozenset(),
              ) -> tuple[DatedEvent, ...]:
    """Turn the model's answer into chart rows, REFUSING what it cannot support.

    Every refusal lands on UNDATED, never on a date. That asymmetry is the
    whole module: an event wrongly recorded as undated costs a question, and an
    event wrongly dated costs a limitation calculation the advocate acts on.
    """
    if not isinstance(data, dict):
        return ()
    out: list[DatedEvent] = []
    for raw in data.get("events") or ():
        if not isinstance(raw, dict):
            continue
        event = (raw.get("event") or "").strip()
        if not event:
            continue
        expr = (raw.get("date_expression") or "").strip()
        iso = (raw.get("resolved") or "").strip()
        certainty = (Certainty.DOCUMENTED if raw.get("documented")
                     else Certainty.ASSERTED)

        # AN ID THE FILE DOES NOT HOLD IS DROPPED, not carried. A correction
        # pointing at nothing would supersede nothing and read as one that
        # had — the silent direction.
        corrects = str(raw.get("corrects") or "").strip()
        if corrects and corrects not in known:
            corrects = ""

        if not iso:
            # NO DATE IS AN ANSWER. The event is on the chart, undated.
            out.append(DatedEvent(event=event, state=DateState.UNDATED,
                                  certainty=certainty,
                                  corrects=corrects))
            continue

        if not expr:
            out.append(DatedEvent(
                event=event, state=DateState.UNDATED, certainty=certainty,
                refused="a date was given with no words to support it"))
            continue

        # GUARD 1 -- the span must be the ADVOCATE'S words, not the prompt's.
        if _fold(expr) not in _fold(message):
            out.append(DatedEvent(
                event=event, state=DateState.UNDATED, certainty=certainty,
                refused=f"the date was read from {expr!r}, which is not in "
                        f"what the advocate wrote"))
            continue

        try:
            on = date.fromisoformat(iso)
        except ValueError:
            out.append(DatedEvent(
                event=event, state=DateState.UNDATED, certainty=certainty,
                refused=f"{iso!r} is not a date"))
            continue

        out.append(DatedEvent(
            event=event, state=DateState.RESOLVED, on=on,
            date_expression=expr, reference=reference.isoformat(),
            certainty=certainty, corrects=corrects))
    return tuple(out)


def conflicts(facts: tuple[Fact, ...]) -> tuple[DateConflict, ...]:
    """Events on the file that carry more than one date.

    Matched on the event text, folded — the advocate describing the same event
    twice will not phrase it identically, and requiring them to would find no
    conflicts at all, which is the failure mode that looks like success.

    NOTHING IS RESOLVED HERE. Both dates are returned, and the caller surfaces
    them. Picking one would be the silent resolution C5 forbids and C1 forbids
    twice over.
    """
    seen: dict[str, Fact] = {}
    out: list[DateConflict] = []
    for f in facts:
        if f.date is None:
            continue
        key = _fold(f.statement)[:90]
        if not key:
            continue
        prior = seen.get(key)
        if prior is None:
            seen[key] = f
            continue
        if prior.date != f.date:
            out.append(DateConflict(
                event=f.statement[:90], left=prior.date, right=f.date,
                left_fact=prior.id, right_fact=f.id))
    return tuple(out)


def chart(facts: tuple[Fact, ...], chronology: tuple[FactId, ...]) -> tuple[Fact, ...]:
    """The thread's chart: ITS facts, dated first in order, then the undated.

    Undated events come LAST and they come — they are not dropped. A chart that
    silently omits what it could not date is the same defect as one that
    guesses, arriving as an absence rather than as a wrong number.
    """
    # A SUPERSEDED FACT LEAVES THE CHART AND STAYS ON THE FILE.
    #
    # This is the ONE place the arithmetic stops reading a corrected entry,
    # and it is one place on purpose: the limitation, the coverage record, the
    # adverse-fact read and the theory all take their facts from here, so a
    # correction applied in four places is a correction that will be applied
    # in three of them next month.
    #
    # Measured on GS-15: "the agreement is dated 15-4-1984" then "sorry, that
    # is wrong. It is dated 15-4-2024" left BOTH on the chart, and the period
    # ran from the earlier — reporting a claim that expired in 1987 for an
    # agreement dated 2024. Nothing was deleted then and nothing is deleted
    # now; `superseded_by` marks it, and §5.4 needs the prior value to still
    # exist so a change can be reported WITH what it was before.
    live = [f for f in facts
            if f.id in set(chronology) and f.superseded_by is None]
    dated = sorted((f for f in live if f.date is not None), key=lambda f: f.date)
    undated = [f for f in live if f.date is None]
    return tuple(dated + undated)
