"""D5 — asking the file what it can establish, element by element.

WHAT WAS MISSING
-----------------
`nm/domain/proof.py` has carried D5's whole contract since slice 7: a status
that cannot be HELD without material, cannot be OBTAINABLE without saying what
would obtain it, and cannot be ABSENT without naming the dead end. `uncovered`
draws its population from the ELEMENTS so the coverage gate cannot certify
itself. Every one of those refusals was correct and NOTHING EVER BUILT A
`ProofPosition`, so none of it ran on a served turn — the same shape as B-079,
where D9's issue register was complete and unreachable.

THE DIVISION OF LABOUR, WHICH IS THE WHOLE DESIGN
----------------------------------------------------
    the LAW      what a cause requires      `nm/knowledge/elements.py`, curated
    the FILE     what is held for each      this module, read and guarded

A model asked "what are the elements of specific performance" answers
plausibly and differently each time, and every position downstream would rest
on a list nobody authored. A model asked "does this file hold the agreement,
and if not what would get it" is answering about material it has in front of
it, which is a question it can be held to.

SO THE ELEMENT LIST IS NEVER READ FROM THE MODEL. The prompt names the
elements; the model reports a status against each. An element the model
invents is dropped, and an element it omits stays NOT_ASSESSED — which is what
`uncovered` then reports, rather than the list quietly shrinking to whatever
came back.

THE DRIFT RUNS ONE WAY AND THE PROMPT IS BUILT AGAINST IT
------------------------------------------------------------
D5.1: a model being careful with a client reaches for OBTAINABLE where the
honest answer is ABSENT, because obtainable sounds like progress. The type
already refuses an OBTAINABLE with no closing material, which turns the soft
answer into work rather than into a hedge; the prompt says the same thing in
words, because a schema the model satisfies by inventing a plausible document
is worse than one it declines.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.matter import Side
from nm.domain.proof import Burden, ProofPosition, ProofStatus, Standard
from nm.domain.quotable import Quotable
from nm.domain.text import blank
from nm.domain.traceability import implements
from nm.ports.elements import Elements, Ingredient

#: The most elements one read covers. Every curated cause is well inside this;
#: it exists so a table entry that grows by accident cannot produce a prompt
#: nobody sized.
MAX_ELEMENTS = 12

PROOF_SCHEMA: dict = {
    "x-nm-read": "proof",
    "type": "object",
    "properties": {
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {
                        "type": "string",
                        "description": "Copy the element EXACTLY as it was "
                                       "given to you. Do not reword it and do "
                                       "not add elements of your own.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["held", "obtainable", "absent",
                                 "not_assessed"],
                    },
                    "material": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For HELD: what on the file establishes "
                                       "this, in the advocate's own words. "
                                       "Empty for every other status.",
                    },
                    "closing_material": {
                        "type": "string",
                        "description": "For OBTAINABLE ONLY: the specific "
                                       "document or evidence that would "
                                       "establish this, and where it "
                                       "ordinarily sits. 'More evidence' is "
                                       "not an answer. If you cannot name "
                                       "one, the status is `absent`.",
                    },
                    "dead_end": {
                        "type": "string",
                        "description": "For ABSENT ONLY: why nothing "
                                       "identified would establish it.",
                    },
                },
                "required": ["element", "status", "material",
                             "closing_material", "dead_end"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["positions"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are given the ELEMENTS of a cause of action under Indian law and an "
    "advocate's file. For each element, say what THE FILE can do about it. "
    "You are never asked whether the element is true.\n\n"
    "  held        the file already carries material establishing it\n"
    "  obtainable  it is not held, and you can NAME what would get it\n"
    "  absent      nothing identified would establish it\n"
    "  not_assessed you cannot tell from what you were given\n\n"
    "OBTAINABLE REQUIRES A NAMED DOCUMENT. 'The bank statement for March and "
    "the ledger entry, both ordinarily with the client' is an answer; 'further "
    "evidence' is not. If you cannot name the material, the honest status is "
    "`absent` with the reason, and `absent` is what you must say however "
    "unwelcome it is. An element reported as obtainable because that sounds "
    "better than absent sends the advocate looking for a document that does "
    "not exist.\n\n"
    "Do not say anything about the client's honesty, reliability or "
    "character. You have not met them and hold nothing on which such a "
    "finding could rest, and you are speaking to their advocate.\n\n"
    "Copy each element exactly as given. Do not add elements."
)


@dataclass(frozen=True)
class ReadProof:
    """THREE STATES. `examined=False` is not an empty position list."""

    positions: tuple[ProofPosition, ...] = ()
    examined: bool = False
    why_not: str = "nothing has read this file for proof positions"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return "assessed" if self.positions else "none_established"


UNREAD = ReadProof()


def not_assessed(why: str) -> ReadProof:
    return ReadProof(examined=False, why_not=why)


@implements("D5")
def build_prompt(quotable: Quotable, elements: Elements):
    """The curated elements, and the file, and nothing else.

    THE ELEMENTS ARE IN THE PROMPT AND NOT IN THE ANSWER. The model is shown
    the list and reports against it; it is never asked what the list is.
    """
    from nm.ports.model import Prompt

    listed = "\n".join(
        f"  {i + 1}. {ing.element}"
        + (f"\n     (why it matters: {ing.serves})" if ing.serves else "")
        for i, ing in enumerate(elements.ingredients[:MAX_ELEMENTS]))

    return Prompt(
        system=SYSTEM,
        user=(f"THE ELEMENTS, to be proved on the "
              f"{elements.standard.value.replace('_', ' ')}:\n{listed}\n\n"
              f"{quotable.block()}"),
    )


@implements("D5")
def read(said: dict, elements: Elements, quotable: Quotable) -> ReadProof:
    """Build positions, refusing each one the file does not support.

    A REFUSAL IS PER ELEMENT. One unsupported position among five must not
    discard the other four -- the same rule the issue and inventory reads
    follow, and for the same reason: a filter with a good excuse is still a
    filter.

    AN ELEMENT NOT REPORTED ON IS NOT_ASSESSED, and it is CONSTRUCTED rather
    than left out. `uncovered` would catch a missing one either way; a
    position that exists and says "nobody worked this out" is what the
    advocate reads, and the difference between that and silence is the
    difference between a chart with a hole in it and a chart that looks
    complete.
    """
    rows = said.get("positions")
    if not isinstance(rows, list):
        return not_assessed("the proof read returned no list")

    by_element = {ing.element.strip().lower(): ing
                  for ing in elements.ingredients[:MAX_ELEMENTS]}
    seen: dict[str, ProofPosition] = {}
    refused: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            refused.append("a position that was not an object")
            continue
        named = str(row.get("element") or "").strip()
        ing = by_element.get(named.lower())
        if ing is None:
            # AN ELEMENT NOBODY CURATED IS DROPPED. The law is the table's to
            # state; a model adding a sixth element to specific performance
            # would put it in front of the advocate with the authority of the
            # other five behind it.
            refused.append(f"{named[:60]!r}: not an element of this cause. "
                           f"The element list is curated, not read.")
            continue
        if ing.element.lower() in seen:
            refused.append(f"{named[:60]!r}: reported twice")
            continue

        position = _position(row, ing, elements, quotable, refused)
        if position is not None:
            seen[ing.element.lower()] = position

    # EVERY CURATED ELEMENT GETS A POSITION, in the curated order.
    positions = tuple(
        seen.get(ing.element.lower())
        or ProofPosition(element=ing.element, burden=elements.burden(ing),
                         serves=ing.serves)
        for ing in elements.ingredients[:MAX_ELEMENTS])

    return ReadProof(positions=positions, examined=True,
                     refused=tuple(refused),
                     why_not="" if positions else
                             "this cause has no curated elements")


def _position(row: dict, ing: Ingredient, elements: Elements,
              quotable: Quotable, refused: list[str]) -> ProofPosition | None:
    """One row into a position, or None with the reason recorded."""
    raw = str(row.get("status") or "").strip().lower()
    try:
        status = ProofStatus(raw)
    except ValueError:
        refused.append(f"{ing.element[:50]}: {raw!r} is not a proof status")
        return None

    burden = elements.burden(ing)
    if status is ProofStatus.NOT_ASSESSED:
        return ProofPosition(element=ing.element, burden=burden,
                             serves=ing.serves)

    material = tuple(
        m for m in (str(x).strip() for x in (row.get("material") or []))
        if m)

    if status is ProofStatus.HELD:
        # HELD IS THE ONE STATUS THAT CLAIMS SOMETHING ABOUT THE FILE, so it
        # is the one whose material must actually be ON the file. The same
        # verbatim guard every other read applies, reached through the same
        # value the prompt was built from.
        grounded = tuple(m for m in material if quotable.accepts(m))
        if not grounded:
            refused.append(
                f"{ing.element[:50]}: reported as HELD and "
                f"{quotable.refusal(material[0] if material else '')}")
            return None
        return ProofPosition(element=ing.element, burden=burden,
                             standard=elements.standard, status=status,
                             material=grounded, serves=ing.serves)

    if status is ProofStatus.OBTAINABLE:
        closing = str(row.get("closing_material") or "").strip()
        if blank(closing):
            # THE TYPE WOULD RAISE. Refusing here keeps the read per-element
            # and turns the soft answer into a recorded refusal rather than an
            # exception that loses the other four positions.
            refused.append(
                f"{ing.element[:50]}: OBTAINABLE with nothing named that "
                f"would obtain it. D5: never report a proof gap as a verdict.")
            return None
        return ProofPosition(element=ing.element, burden=burden,
                             standard=elements.standard, status=status,
                             closing_material=closing, serves=ing.serves)

    dead_end = str(row.get("dead_end") or "").strip()
    if blank(dead_end):
        refused.append(
            f"{ing.element[:50]}: ABSENT with no express dead end. An "
            f"advocate told a thing cannot be proved, with no reason, cannot "
            f"tell whether to look harder or to change the case.")
        return None
    return ProofPosition(element=ing.element, burden=burden,
                         standard=elements.standard, status=status,
                         dead_end=dead_end, serves=ing.serves)


@implements("D5")
def against_us(positions: tuple[ProofPosition, ...], posture
               ) -> tuple[ProofPosition, ...]:
    """The gaps on OUR side of the burden. `falls_on_us` decides, not this.

    An unresolved posture returns nothing rather than everything: `None` from
    `falls_on_us` means nobody established which side we are, and listing
    every gap as ours would be the comfortable-looking guess that reads as an
    answer.
    """
    return tuple(p for p in positions
                 if p.is_gap and p.burden.falls_on_us(posture) is True)


__all__ = [
    "MAX_ELEMENTS",
    "PROOF_SCHEMA",
    "ReadProof",
    "UNREAD",
    "against_us",
    "build_prompt",
    "not_assessed",
    "read",
    # Re-exported for the turn, which builds a burden for nothing else.
    "Burden",
    "Side",
    "Standard",
]
