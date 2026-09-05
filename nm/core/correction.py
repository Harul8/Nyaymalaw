"""B-086 / §5.4 — a turn that CORRECTS a fact already on the file.

THE DEFECT THIS CLOSES
-----------------------
`Fact.superseded_by` has existed since slice 1 and nothing in the product ever
set it. So a correction did not correct anything: it added a second event
beside the first.

Measured on GS-15, 4 September 2026. The advocate said the agreement is dated
15-4-1984, then *"sorry, that is wrong. It is dated 15-4-2024"* — and BOTH
dates sat on the chronology. The limitation runs from the earliest dated fact,
so the answer reported a period that expired on 1987-04-15 for an agreement the
advocate had corrected to 2024. Every citation on that turn was right.

WHAT IS READ AND WHAT IS COMPUTED
-----------------------------------
The model reads one question: does anything the advocate just said REPLACE
something already on the file, and which entry is it. That is a question about
what they meant, and the answer is a pair of ids.

Everything else is mechanical. Both ids must exist. The superseded one must
already be on the file and the replacement must be from THIS turn — a
correction that "supersedes" a fact from the same breath is not a correction,
and one that supersedes a fact the file does not hold moves nothing.

NOTHING IS DELETED, EVER
--------------------------
The superseded fact stays on the matter and stays on the thread's chronology.
It is marked, not removed: the advocate can see what they said and what
replaced it, and §5.4's report of "what it was before" needs the prior value to
still exist. What changes is that the ARITHMETIC stops reading it.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.matter import Fact, FactId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements

CORRECTION_SCHEMA: dict = {
    "x-nm-read": "correction",
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "supersedes": {
                        "type": "string",
                        "description": "The id of the EARLIER entry being "
                                       "replaced.",
                    },
                    "replaced_by": {
                        "type": "string",
                        "description": "The id of the entry from THIS turn "
                                       "that replaces it.",
                    },
                    "why": {
                        "type": "string",
                        "description": "One clause, shown to the advocate so "
                                       "they can correct the correction.",
                    },
                },
                "required": ["supersedes", "replaced_by", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["corrections"],
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate has just added something to a file. Decide ONE thing: "
    "does any of it REPLACE something already recorded, rather than adding to "
    "it?\n\n"
    "A correction says the earlier entry was wrong — \"sorry, that is wrong\", "
    "\"I meant\", \"it is actually\", or simply the same event given a "
    "different date. A NEW event on a different day is not a correction, and "
    "treating it as one would erase a real part of the chronology.\n\n"
    "Name both entries by their ids. Return an empty list unless something is "
    "plainly being replaced — that is the ordinary answer."
)


@refuses_blank_text()
@dataclass(frozen=True)
class Correction:
    """One entry replaced by another. Both ids verified against the file."""

    supersedes: FactId
    replaced_by: FactId
    why: str


@dataclass(frozen=True)
class ReadCorrections:
    """THREE STATES. Nothing corrected is not the same as nothing read."""

    corrections: tuple[Correction, ...] = ()
    examined: bool = False
    why_not: str = "nothing has read this turn for a correction"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        if self.refused and not self.corrections:
            return "refused"
        return "corrected" if self.corrections else "none_found"


UNREAD = ReadCorrections()


def not_assessed(why: str) -> ReadCorrections:
    return ReadCorrections(examined=False, why_not=why)


@implements("A3")
def build_prompt(message: str, existing: tuple[Fact, ...],
                 added: tuple[Fact, ...]):
    from nm.ports.model import Prompt

    def rows(facts):
        return "\n".join(
            f"  {f.id}\t{f.date.isoformat() if f.date else 'undated'}\t"
            f"{f.statement}" for f in facts) or "  (none)"

    return Prompt(
        system=SYSTEM,
        user=(f"ALREADY ON THE FILE:\n{rows(existing)}\n\n"
              f"ADDED BY THIS TURN:\n{rows(added)}\n\n"
              f"WHAT THEY SAID:\n{message}"))


@implements("A3")
def read(said: dict, existing: tuple[Fact, ...],
         added: tuple[Fact, ...]) -> ReadCorrections:
    """Pair up the ids, refusing every pair the file cannot support."""
    rows = said.get("corrections")
    if not isinstance(rows, list):
        return not_assessed("the correction read returned no list")

    on_file = {f.id: f for f in existing}
    from_turn = {f.id for f in added}
    out: list[Correction] = []
    refused: list[str] = []
    claimed: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        old = str(row.get("supersedes") or "").strip()
        new = str(row.get("replaced_by") or "").strip()

        if old not in on_file:
            refused.append(f"{old!r} is not on this file, so nothing of that "
                           f"name can be superseded")
            continue
        if new not in from_turn:
            # A CORRECTION HAS TO COME FROM THIS TURN. Pairing two entries
            # that were both already on the file is a re-reading of history,
            # not a correction — and the advocate said nothing to license it.
            refused.append(f"{new!r} was not added by this turn, so it is not "
                           f"a correction of anything")
            continue
        if old == new:
            refused.append("an entry cannot supersede itself")
            continue
        if on_file[old].superseded_by is not None:
            refused.append(f"{old!r} is already superseded")
            continue
        if old in claimed:
            refused.append(f"{old!r} was named twice")
            continue

        claimed.add(old)
        # A REASON THAT IS TRUE RATHER THAN ONE THAT IS INVENTED.
        #
        # `why` is required by the type — it is shown to the advocate so they
        # can correct the correction — and the model does not always give one.
        # The fallback states only what the product actually knows: this turn
        # replaced that entry. Composing a plausible reason here would be a
        # sentence nobody said, attached to a change to their file.
        out.append(Correction(
            supersedes=FactId(old), replaced_by=FactId(new),
            why=(str(row.get("why") or "").strip()
                 or "replaced by what you said on this turn")))

    return ReadCorrections(corrections=tuple(out), examined=True,
                           refused=tuple(refused),
                           why_not=("nothing on this turn replaces anything "
                                    "already recorded"
                                    if not out and not refused else ""))
