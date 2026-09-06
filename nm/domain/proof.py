"""D5's PRODUCES contract: what an element NEEDS and whether the file HOLDS it.

THE TYPES ARE THE FRAME, AND THAT IS THE MECHANISM
----------------------------------------------------
D5.1 is the delicate part of this product and it is explicit that it needs a
RULE, NOT A TONE INSTRUCTION: *if NM consistently speaks about what can be
established rather than what is true, the accusatory problem disappears by
construction — and a politeness layer bolted onto a truth-judging system would
be exactly the kind of patch this document forbids.*

So the frame is these types. A `ProofPosition` says what an element NEEDS and
whether the file HOLDS it. There is no field in which a credibility finding
could be expressed, and none in which one could be hidden.

NM also has no business judging honesty at all. Facts arrive by briefing — it
has not met the client, has not seen them answer a question, and holds no
material on which a credibility finding could rest. And note who is listening:
NM speaks to the ADVOCATE, not the client. *"Your client is not being
truthful"* is not merely tactless, it is misdirected. The text tripwire in
`nm.core.proof` is a backstop against model prose and is NOT the mechanism.

THE BOUND, WHICH MATTERS MORE THAN THE RULE IT BOUNDS
-------------------------------------------------------
*Do not accuse the client. State the facts plainly and strongly, exactly as
they are.* None of that licenses hedging. NM softens the ATTRIBUTION; it never
softens the FINDING.

**The drift runs one way and must be designed against.** A model instructed to
be careful with a client will not stop at withholding the character judgement —
it will quietly soften the weakness, hedge the adverse finding, and bury the
exposure in qualifications. That is the failure that loses cases, and it is the
MORE LIKELY of the two, because agreeable language is the path of least
resistance.

So there is no confidence adjective and no hedging field here. A position is
HELD, OBTAINABLE or ABSENT, and ABSENT is stated as absent whoever it hurts.

WHY THESE LIVE IN `domain` AND THE LOGIC LIVES IN `core`
----------------------------------------------------------
The same split every other PRODUCES contract already uses — `Fact` beside
`nm.core.intake`, `Issue` beside `nm.core.issues`. Proof was the exception
until 6 September 2026, and what exposed it was `nm/knowledge/elements.py`:
the curated element table is KNOWLEDGE, knowledge may not import core, and the
table needs `Standard` and `Side` to say what a cause requires and to what
standard it is proved.

`nm.core.proof` re-exports all four, so every existing import still works.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import Side
from nm.domain.text import blank, refuses_blank_text


class ProofStatus(str, Enum):
    """What the FILE can do about this element. Never what is true."""

    HELD = "held"
    """The material is on the file."""

    OBTAINABLE = "obtainable"
    """Not held, and something identifiable would get it."""

    ABSENT = "absent"
    """Nothing identified would establish it. STATED AS SUCH, whoever it hurts.

    This is the member the drift attacks. A model being careful with a client
    reaches for `obtainable` when the honest answer is `absent`, because
    `obtainable` sounds like progress. `ProofPosition` therefore requires an
    ABSENT position to name the dead end -- which cannot be written vaguely and
    stay meaningful."""

    NOT_ASSESSED = "not_assessed"
    """Nobody worked it out. NOT "nothing would establish it".

    E-070's counterexample is a conclusion where two of five elements have no
    proof position at all, and the difference between this member and ABSENT is
    exactly the difference between "we looked and there is nothing" and "we did
    not look"."""


class Standard(str, Enum):
    BALANCE_OF_PROBABILITIES = "balance_of_probabilities"
    BEYOND_REASONABLE_DOUBT = "beyond_reasonable_doubt"
    PRIMA_FACIE = "prima_facie"
    NOT_ESTABLISHED = "not_established"


@refuses_blank_text("shifted_by", "shift_provision")
@dataclass(frozen=True)
class Burden:
    """WHO must prove it, and what moved it there.

    D5: *state the burden as it actually falls, including where a presumption
    shifts it — and note that the same presumption is a gift or a problem
    depending on which side the client is on.*

    That last clause is D9's rule about `effect` in a different place, so it
    gets the same treatment: the burden knows which SIDE it lies on, the
    posture knows which side we are, and `falls_on_us` combines them. Baking
    "this is a problem for us" into the burden would be wrong for half the
    advocates who read it.
    """

    on: Side
    shifted_by: str = ""
    """The presumption that moved it, in words the advocate can check."""
    shift_provision: str = ""
    """The provision that creates the presumption. RETRIEVED, never remembered.

    Same rule as `Factor.finding` and `Period.read_from`: a presumption is a
    section, and one asserted from memory is the defect those types exist to
    refuse."""

    def __post_init__(self) -> None:
        if self.shifted_by and not self.shift_provision.strip():
            raise ValueError(
                "a burden said to be SHIFTED must name the provision that "
                "shifts it. A presumption asserted from memory is the same "
                "defect as an extending provision asserted from memory, and "
                "it decides who loses when the evidence is silent.")

    def falls_on_us(self, posture) -> bool | None:
        """`None` where the posture is unresolved -- not `False`.

        `False` would read as "the opponent must prove it", which is the more
        comfortable answer and is not one anybody established.
        """
        if self.on is Side.UNKNOWN or not posture.resolved:
            return None
        return self.on is posture.side


@refuses_blank_text("closing_material", "dead_end", "shifted_by",
                    "shift_provision")
@dataclass(frozen=True)
class ProofPosition:
    """One element, and what the file can do about it. D5's PRODUCES.

    THE TYPE REFUSES THE COUNTEREXAMPLES rather than a reviewer catching them:
    an element with no burden or no standard cannot be built, and an ABSENT or
    OBTAINABLE position with neither closing material nor an express dead end
    cannot be built either.
    """

    element: str
    burden: Burden
    standard: Standard = Standard.NOT_ESTABLISHED
    status: ProofStatus = ProofStatus.NOT_ASSESSED
    material: tuple[str, ...] = ()
    """What is on the file, or what would close the gap."""
    closing_material: str = ""
    """For OBTAINABLE: what would get it, and where it ordinarily sits."""
    dead_end: str = ""
    """For ABSENT: why nothing would establish it."""
    serves: str = ""

    def __post_init__(self) -> None:
        if self.status is ProofStatus.OBTAINABLE and blank(self.closing_material):
            raise ValueError(
                f"element {self.element!r} is OBTAINABLE and does not say what "
                f"would obtain it. D5: never report a proof gap as a verdict — "
                f"'you cannot prove the loan' fails; 'the loan needs the bank "
                f"statement for that month and the ledger entry, both "
                f"ordinarily with the client' is the requirement.")
        if self.status is ProofStatus.ABSENT and blank(self.dead_end):
            raise ValueError(
                f"element {self.element!r} is ABSENT with no express dead end. "
                f"An advocate told a thing cannot be proved, with no reason, "
                f"cannot tell whether to look harder or to change the case.")
        if self.status is ProofStatus.HELD and not self.material:
            raise ValueError(
                f"element {self.element!r} is HELD with no material behind it. "
                f"Held by what? A status with nothing under it is the same "
                f"claim as a citation with no span.")
        if self.status is not ProofStatus.NOT_ASSESSED \
                and self.standard is Standard.NOT_ESTABLISHED:
            raise ValueError(
                f"element {self.element!r} carries a proof status and no "
                f"standard. D5: never state an element without its burden, its "
                f"standard, and what would establish it — to what standard is "
                f"half of whether the material is enough.")

    @property
    def is_gap(self) -> bool:
        return self.status in (ProofStatus.OBTAINABLE, ProofStatus.ABSENT,
                               ProofStatus.NOT_ASSESSED)
