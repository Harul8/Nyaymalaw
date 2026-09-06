"""Elements, burden and proof. D5 and D5.1.

SAY WHAT CAN BE ESTABLISHED, NEVER WHAT IS TRUE
-------------------------------------------------
D5.1 is the delicate part of the product and it is explicit that it needs a
RULE, NOT A TONE INSTRUCTION: *the generalised fix is the frame, not the
politeness. If NM consistently speaks about what can be established rather than
what is true, the accusatory problem disappears by construction — and a
politeness layer bolted onto a truth-judging system would be exactly the kind
of patch this document forbids.*

So the frame is this module's types. A `ProofPosition` says what an element
NEEDS and whether the file HOLDS it. There is no field on it in which a
credibility finding could be expressed, and none in which one could be hidden.
That is what "by construction" means here; the text tripwire further down is a
backstop against model prose and is NOT the mechanism.

NM also has no business judging honesty at all. Facts arrive by briefing — it
has not met the client, has not seen them answer a question, and holds no
material on which a credibility finding could rest. And note who is listening:
NM speaks to the ADVOCATE, not the client. *"Your client is not being truthful"*
is not merely tactless, it is misdirected.

THE BOUND, WHICH MATTERS MORE THAN THE RULE IT BOUNDS
-------------------------------------------------------
*Do not accuse the client. State the facts plainly and strongly, exactly as
they are.* None of the above licenses hedging. NM softens the ATTRIBUTION; it
never softens the FINDING.

**The drift runs one way and must be designed against.** A model instructed to
be careful with a client will not stop at withholding the character judgement —
it will quietly soften the weakness, hedge the adverse finding, and bury the
exposure in qualifications. That is the failure that loses cases, and it is the
MORE LIKELY of the two, because agreeable language is the path of least
resistance.

So the types here carry no confidence adjective and no hedging field. A
position is HELD, OBTAINABLE or ABSENT, and ABSENT is stated as absent whoever
it hurts.

THE COVERAGE GATE MAY NOT CERTIFY ITSELF
------------------------------------------
D5's third NEVER. `uncovered` draws its population from the ELEMENTS and asks
what has no position, which is the only direction that can fail. Counting
positions against positions would report complete coverage of whatever happened
to be there — the shape B-049 was, and the same reason
`Limitation.accounts_for_every_entry` reads from the chronology rather than
from the record.
"""
from __future__ import annotations

import re

from nm.domain.proof import (
    Burden,
    ProofPosition,
    ProofStatus,
    Standard,
)
from nm.domain.text import blank
from nm.domain.traceability import implements

#: RE-EXPORTED, not redefined. The four PRODUCES types moved to
#: `nm.domain.proof` on 6 September 2026 so the curated element table --
#: which is knowledge, and may not import core -- could name them. Every
#: existing `from nm.core.proof import ProofPosition` keeps working, and a
#: re-export is one definition with a second NAME rather than a second
#: copy: there is nowhere for the two to drift apart.
__all__ = [
    "Burden",
    "ProofPosition",
    "ProofStatus",
    "Standard",
    "characterises_the_client",
    "uncovered",
    "unclosed",
]


@implements("D5")
def uncovered(elements: tuple[str, ...],
              positions: tuple[ProofPosition, ...]) -> tuple[str, ...]:
    """E-070'S INVARIANT. Elements with no proof position at all.

    THE POPULATION IS THE ELEMENTS, and that is the whole of D5's third NEVER:
    *never let the proof-coverage gate certify itself.* Counting positions
    against positions reports complete coverage of whatever happened to be
    there and cannot fail — the shape B-049 was.

    E-070's counterexample is a conclusion that a cause succeeds where two of
    its five elements have no proof position, so this returns WHICH ones rather
    than how many.
    """
    have = {p.element.strip().lower() for p in positions}
    return tuple(e for e in elements if e.strip().lower() not in have)


@implements("D5")
def unclosed(positions: tuple[ProofPosition, ...]) -> tuple[str, ...]:
    """E-071. Gaps carrying neither closing material nor an express dead end.

    Should always be empty, because `ProofPosition` refuses one at
    construction. It is computed anyway: a type guard proves nothing about
    positions built before the guard existed or decoded from an older store,
    and NOT_ASSESSED is a legitimate state that still owes the advocate an
    account of itself.
    """
    return tuple(
        p.element for p in positions
        if p.status is ProofStatus.NOT_ASSESSED
        or (p.is_gap and blank(p.closing_material) and blank(p.dead_end)))


# ----------------------------------------------- D5.1, the text tripwire ---

#: Words that predicate a state of MIND or CHARACTER rather than a state of the
#: EVIDENCE. A tripwire on model prose, and DELIBERATELY NOT THE MECHANISM.
#:
#: The mechanism is the frame above: a `ProofPosition` has no field in which a
#: credibility finding could be expressed. This catches the free text a model
#: writes around it, and it is incomplete by construction -- every list of
#: words is. This project has twice paid for treating a phrase list as a
#: mechanism (the posture phrases, the Act keywords), and the distinction is
#: that those were IDENTIFYING something and this is only raising a hand.
_CHARACTER = re.compile(
    r"\b(?:"
    r"lying|lies|liar|dishonest|dishonesty|untruthful|not\s+(?:being\s+)?truthful|"
    r"concealing|conceal(?:ed|s)?|hiding|hid(?:ing|den)|"
    r"not\s+credible|lacks?\s+credibility|incredible|"
    r"implausible|far-?fetched|evasive|shifty|unreliable\s+witness|"
    r"fabricat(?:ed|ing)|invented\s+this|made\s+(?:this\s+)?up|"
    r"bad\s+faith|malafide|mala\s+fide"
    r")\b", re.I)

#: Who the characterisation has to be ABOUT for it to breach D5.1.
#:
#: D5.1 governs what NM says about THE CLIENT. Saying the opponent's account is
#: not credible is advocacy, and refusing it would be the hedging the bound
#: forbids -- the drift this rule is most at risk from is softening, not
#: accusing, so a check that fired on both would push exactly the wrong way.
_OURS = re.compile(
    r"\b(?:your\s+client|our\s+client|the\s+client|your\s+own\s+client)\b", re.I)


@implements("D5")
def characterises_the_client(text: str) -> tuple[str, ...]:
    """D5.1, mechanically. Sentences that judge the client rather than the file.

    Returns the offending sentences so the caller can report them, never a
    boolean: an advocate told their answer was withheld learns nothing, and an
    operator needs the sentence to fix the prompt.

    A CHARACTERISATION OF THE OPPONENT IS NOT CAUGHT, deliberately. See
    `_OURS`: the drift this rule is most at risk from is softening a weakness,
    not accusing, and a check firing on both sides would push the wrong way.
    """
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        if _CHARACTER.search(sentence) and _OURS.search(sentence):
            out.append(" ".join(sentence.split())[:160])
    return tuple(out)
