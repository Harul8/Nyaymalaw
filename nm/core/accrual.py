"""WHICH dated event starts the period? BK-35, the second half.

THE DEFECT THIS COMPLETES THE FIX FOR
---------------------------------------
`_limitation` chose the accrual like this:

    accrual = next((f for f in chart if f.date is not None), None)

The earliest dated fact, whatever the cause. So Article 54 -- whose period
runs from the date fixed for performance, or from notice that performance is
refused -- ran from a 2023 agreement on a file that supplied a 2024 written
refusal and no date for performance. The expiry was declared, and every
citation on the turn was correct.

The first half curated the trigger onto the Article (`Edge.accrues_on`) and
made the engine REFUSE rather than guess where the chronology offered a
choice. Refusing is honest and it is not an answer. This reads which entry
satisfies the trigger, so the ordinary case is answered again.

WHY THE VOCABULARY IS CLOSED WITHOUT ANYBODY CURATING IT
----------------------------------------------------------
The answer is a FACT ID from this thread's own chronology. That is a closed
set, generated per turn, and the guard is exact membership -- not a quotation
check, not a similarity score. A model that names an id not on the chart has
not identified an entry, and no amount of reading its prose would make it one.

This is the one read in the product whose vocabulary needs no curation and
admits no fuzzy matching, which is why the guard is a single `in`.

THE LIMB IS ANSWERED TOO, AND IT IS NOT DECORATION
----------------------------------------------------
Article 54 has two limbs and they give different dates. So does Article 14
(delivery, or a fixed date for payment) and Article 19 (the loan, or a fixed
time for repayment). An accrual that names the entry without naming the limb
cannot be checked by the advocate: `2024-06-10` tells them nothing, and `the
refusal on 2024-06-10, no date having been fixed for performance` is a
sentence they can agree or disagree with in four words.

WHICH DIRECTION IT FAILS
--------------------------
Toward NOT COMPUTING. A wrong accrual produces a confident date with real
statutory text behind it and nothing downstream that catches it -- the defect
that produced this module. An absent accrual produces a gap that says what it
was looking for. The second is recoverable in one turn; the first is not
recoverable at all, because nobody knows to look.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.text import refuses_blank_text

ACCRUAL_SCHEMA: dict = {
    "x-nm-read": "accrual",
    "type": "object",
    "properties": {
        "fact_id": {
            "type": "string",
            "description": (
                "The id of the ONE chronology entry the period runs from, "
                "copied exactly from the list. Empty if no entry on this "
                "chronology is that event."),
        },
        "limb": {
            "type": "string",
            "description": (
                "WHICH limb of the trigger this entry satisfies, in the "
                "trigger's own words -- Article 54 runs from the date fixed "
                "for performance OR from notice of refusal, and they give "
                "different dates. One clause."),
        },
        "why": {
            "type": "string",
            "description": (
                "One clause naming what makes this entry that event. Shown to "
                "the advocate so they can correct it."),
        },
    },
    "required": ["fact_id", "limb", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate's chronology is below, and the statutory trigger that "
    "starts the limitation period for their cause of action.\n\n"
    "Name the ONE entry the period runs from.\n\n"
    "THE TRIGGER IS THE QUESTION, NOT THE DATES. The earliest entry is very "
    "often NOT the answer: a suit for specific performance runs from the date "
    "fixed for performance, or from notice that performance was refused, and "
    "not from the agreement -- which is usually the earliest thing on the "
    "file. Read the trigger and find the entry that satisfies it.\n\n"
    "WHERE THE TRIGGER HAS LIMBS, SAY WHICH ONE. If a date was fixed for "
    "performance, that is the limb. If none was fixed and performance was "
    "refused, the refusal is the limb. They give different dates and the "
    "advocate needs to know which you used.\n\n"
    "ANSWER WITH AN EMPTY `fact_id` IF NO ENTRY IS THAT EVENT. That is a real "
    "answer and the right one: the period will not be computed, the advocate "
    "will be told what was being looked for, and they can supply it. A wrong "
    "entry produces a confident expiry date with correct statutory text "
    "behind it and nothing that catches it."
)


@refuses_blank_text("limb", "why")
@dataclass(frozen=True)
class Accrual:
    """The entry the period runs from, or nothing.

    `fact_id` EMPTY IS THE ORDINARY REFUSAL and carries no `refused` -- the
    chronology simply does not hold the trigger. `refused` is set only where a
    guard rejected something the model returned, which is a different fact and
    the only one worth telling the advocate about.
    """

    fact_id: str = ""
    limb: str = ""
    why: str = ""
    refused: str | None = None

    @property
    def identified(self) -> bool:
        return bool(self.fact_id)


#: What a read that did not run leaves behind.
UNREAD = Accrual(why="the accrual read did not run", limb="not read")


def build_prompt(trigger: str, chronology):
    """The trigger, and the dated entries it might name.

    ONLY DATED ENTRIES ARE OFFERED. An undated fact cannot start a period, so
    including it would invite an answer the arithmetic cannot use -- and the
    guard would then reject a choice the model was invited to make.
    """
    from nm.ports.model import Prompt

    rows = "\n".join(
        f"  {f.id}\t{f.date.isoformat()}\t{f.statement}"
        for f in chronology if getattr(f, "date", None) is not None)
    return Prompt(
        system=SYSTEM,
        user=(f"THE PERIOD RUNS FROM: {trigger}\n\n"
              f"THE DATED ENTRIES ON THIS CHRONOLOGY:\n{rows or '  (none)'}\n\n"
              f"Which entry is that event?"))


def interpret(data: dict, offered: frozenset[str]) -> Accrual:
    """The model's answer, checked against the ids actually offered.

    EXACT MEMBERSHIP, and it is the whole guard. The answer space is this
    thread's own fact ids -- a closed set the turn generated -- so an id that
    is not in it names nothing, and there is no reading of the prose that
    would make it name something. CLAUDE.md §5's rule reaches its easiest
    case here: an exact key exists, so nothing is ranked.
    """
    if not isinstance(data, dict):
        return Accrual(refused="the accrual read returned nothing usable",
                       limb="not read", why="the accrual read returned nothing")

    fact_id = (data.get("fact_id") or "").strip()
    limb = " ".join((data.get("limb") or "").split())[:160]
    why = " ".join((data.get("why") or "").split())[:200]

    if not fact_id:
        # THE ORDINARY REFUSAL. The chronology does not hold the trigger.
        return Accrual(limb=limb or "no limb identified",
                       why=why or "no entry on this chronology is that event")

    if fact_id not in offered:
        return Accrual(
            limb=limb or "not identified",
            why=why or "the read named an entry that is not on this chronology",
            refused=(f"the accrual read named {fact_id!r}, which is not one of "
                     f"the dated entries it was shown"))

    if not limb:
        # A LIMB IS REQUIRED WHERE ONE WAS ASKED FOR. An accrual the advocate
        # cannot check is one they cannot correct.
        limb = "the trigger, limb not stated"
    return Accrual(fact_id=fact_id, limb=limb,
                   why=why or "named as the event the period runs from")
