"""WHO IS IN THIS MATTER. BK-34, and the conflict screen's only input.

NOT `nm/core/intake.py`, WHICH IS C6 AND ABOUT DOCUMENTS. That module reads
what an uploaded page says; this one reads who the brief names. They were
briefly the same file for about a minute and the mistake is worth recording:
`intake` is an obvious name for both, and a module that answers two questions
is the shape S9 warns about even when both answers are right.

WHY A READ AND NOT A FIELD ALREADY ON THE POSTURE
---------------------------------------------------
`Posture.opponent` exists and is filled by the posture read, whose question is
which SIDE we act for. Asked to name the opponent as a by-product it produces
things like `invoices` -- measured on a served turn and rendered to the
advocate as *AGAINST: invoices*. That is not a defect in the posture read;
naming the parties is a different question and nobody was asking it.

It matters because THE CONFLICT SCREEN IS ONLY AS GOOD AS ITS PARTY SET. A
screen that runs against `invoices` and reports `clear` has cleared nothing,
and it is worse than one that admits it did not run: B3's own clause is that
an incomplete screen never clears, and a screen with a wrong party set is
incomplete while looking complete.

WHAT IT REFUSES TO GUESS
--------------------------
Every name is QUOTED from the advocate's own words. A conflict check built on
parties a model supplied is a check against people who are not in the matter,
and it comes back clear. The guard is the one six other reads here already
use, and it is the reason a screen can rely on this: if the name is not in the
brief, there is no party.

AN EMPTY ANSWER IS A REAL ANSWER and it is the ordinary one on a first turn
that says "we act for the plaintiff" and no more. It produces a conflict
screen that is NOT_ASSESSED and names what it wants -- never one that cleared
against the empty set.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.text import refuses_blank_text


@refuses_blank_text("why")
@dataclass(frozen=True)
class Party:
    """One named party, and which side of this matter they are on.

    `side` IS A CLOSED VOCABULARY OF THREE, because the conflict screen's
    question is directional: the same person as our client on one file and
    the party against on another IS the conflict. A party whose side is
    unknown cannot answer that question, so `related` is its own value rather
    than a blank one.
    """

    name: str
    side: str = "related"   # `client` | `adverse` | `related`
    why: str = ""

    @property
    def adverse(self) -> bool:
        return self.side == "adverse"


@refuses_blank_text("why")
@dataclass(frozen=True)
class Parties:
    """The parties this brief names, or nothing."""

    parties: tuple[Party, ...] = ()
    why: str = ""
    refused: str | None = None
    matter_id: str = ""

    @property
    def named(self) -> bool:
        return bool(self.parties)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(p.name.strip().lower() for p in self.parties
                         if p.name.strip())

    def side_of(self, name: str) -> str:
        for p in self.parties:
            if p.name.strip().lower() == name.strip().lower():
                return p.side
        return "related"


#: What a read that did not run leaves behind. NOT an empty party set: those
#: are opposite facts and the screen treats them differently.
UNREAD = Parties(why="the parties read did not run")

SIDES = ("client", "adverse", "related")

PARTIES_SCHEMA: dict = {
    "x-nm-read": "parties",
    "type": "object",
    "properties": {
        "parties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The party's name EXACTLY as the advocate wrote "
                            "it. Not a role and not a description -- a name a "
                            "conflict registry could be searched for."),
                    },
                    "side": {
                        "type": "string",
                        "enum": list(SIDES),
                        "description": (
                            "`client` for the party we act for, `adverse` for "
                            "the party against, `related` for anyone else "
                            "named: a guarantor, a co-defendant, a company in "
                            "the same group."),
                    },
                    "why": {
                        "type": "string",
                        "description": "One clause naming what makes them that.",
                    },
                },
                "required": ["name", "side", "why"],
                "additionalProperties": False,
            },
        },
        "why": {
            "type": "string",
            "description": (
                "One clause about the party set as a whole, or about there "
                "being none to name yet."),
        },
    },
    "required": ["parties", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate has briefed you on a matter. Name the PARTIES.\n\n"
    "A PARTY IS A PERSON OR AN ENTITY, not a role and not a thing. `the "
    "plaintiff` is a role and `invoices` is a document; neither is a party. "
    "If the brief says only `we act for the plaintiff`, there is no name to "
    "give and the right answer is an empty list.\n\n"
    "COPY THE NAME EXACTLY AS THEY WROTE IT. It goes into a conflict check, "
    "and a name nobody wrote is a check against somebody who is not in this "
    "matter -- which clears the file having examined nothing.\n\n"
    "NAME EVERYONE THE BRIEF NAMES, not only the two principals. A guarantor, "
    "a co-defendant, a director, a company in the same group: conflicts are "
    "found through exactly those, and the advocate has already told you about "
    "them.\n\n"
    "AN EMPTY LIST IS THE ORDINARY ANSWER on an early turn and it is not a "
    "failure. The screen will say it could not run and ask for the names, "
    "which is a question the advocate answers in one line."
)


def build_prompt(quotable):
    """The advocate's own words, and nothing else."""
    from nm.ports.model import Prompt

    return Prompt(
        system=SYSTEM,
        user=(f"{quotable.block()}\n\n"
              f"Who are the parties to this matter?"))


def interpret(quotable, data: dict) -> Parties:
    """The read's answer, with every name checked against the brief.

    THE QUOTATION GUARD IS WHAT MAKES THIS USABLE BY A SCREEN. A party set
    the model supplied is a check against people nobody mentioned, and it
    comes back clear. So a name that is not in the advocate's own words is
    DROPPED, and dropping every name leaves an empty result -- which produces
    a screen that says it could not run rather than one that cleared.

    IT DROPS RATHER THAN REFUSING THE WHOLE READ, and the asymmetry is
    deliberate: a brief naming four parties where one name was garbled should
    still screen the three and say so. `refused` records what went, so the
    advocate can see which name to repeat.
    """
    if not isinstance(data, dict):
        return Parties(why="the parties read returned nothing usable",
                       refused="the parties read returned nothing usable")

    kept: list[Party] = []
    dropped: list[str] = []
    for row in (data.get("parties") or []):
        if not isinstance(row, dict):
            continue
        name = " ".join((row.get("name") or "").split())
        side = (row.get("side") or "related").strip().lower()
        why = " ".join((row.get("why") or "").split())[:160]
        if not name:
            continue
        if side not in SIDES:
            # OUT OF VOCABULARY IS BLANKED, NOT COERCED. Guessing `related`
            # would put a party into the screen with a direction nobody
            # stated, and direction is the whole question.
            dropped.append(f"{name} (side {side!r} is not one of {SIDES})")
            continue
        if not quotable.accepts(name):
            dropped.append(f"{name}: {quotable.refusal(name)}")
            continue
        kept.append(Party(name=name, side=side,
                          why=why or "named in the brief"))

    why = " ".join((data.get("why") or "").split())[:200]
    return Parties(
        parties=tuple(kept),
        why=why or ("no party is named in the brief yet" if not kept
                    else f"{len(kept)} party(ies) named in the brief"),
        refused=("; ".join(dropped) if dropped else None))
