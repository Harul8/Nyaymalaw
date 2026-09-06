"""B-073 / D2 — what MOVED the clock, read from the account and cited to a section.

THE DEFECT THIS CLOSES
-----------------------
`nm/core/limitation.py` has carried `Factor` since slice 4, with `finding`
required so one cannot be asserted from memory, and `compute` applies restarts
and extensions correctly. Nothing ever built one. So no acknowledgment, part
payment, exclusion or disability had ever moved a limitation date.

Measured on a served turn, GS-14: invoices of 14 March 2023, then *"the
defendant wrote to us on 12 June 2024 admitting the amount was outstanding"*.
The product answered "limitation runs to 2026-03-14" — unchanged, expired, and
the claim reported dead when it is alive to June 2027. The acknowledgment was
on the file, was repeated back to the advocate, and never reached the
arithmetic.

WHAT IS READ AND WHAT IS COMPUTED, AND WHY THE LINE IS THERE
--------------------------------------------------------------
The MODEL reads one question about words: does the advocate's account describe
a signed writing that admits the liability, or a payment on account of it, and
which chronology entry is it? That is a question about what was written, and
the answer is quoted back verbatim or refused.

Everything with a legal consequence is COMPUTED here:

  * s.18 and s.19 both require the acknowledgment or payment to be made
    BEFORE THE PERIOD EXPIRED. That is arithmetic against the un-extended
    expiry, and it is checked mechanically. A model saying "this restarts it"
    about a letter written after the bar cannot make it so.
  * the fact must be ON THE CHRONOLOGY. A factor attached to a fact the file
    does not hold is refused.
  * the section must have been RETRIEVED, and be the right one: s.18 for an
    acknowledgment, s.19 for a part payment. `Factor.finding` is required by
    the type, and what fills it here is the span that came back from the
    corpus — never a summary of it.

B-077 IS WHY THE SPLIT MATTERS
--------------------------------
With nothing producing factors, the recommendation was left to guess, and it
guessed ASYMMETRICALLY: acting for the debtor, "the acknowledgment does not
operate to restart the limitation period" — flat; acting for the creditor on
the same facts, "to POTENTIALLY revive" — hedged. The same unfounded question,
stated firmly where the answer hurt the opponent and softened where it hurt
our own client. That is D5.1's drift arriving from the direction the PRD
predicted, and no mechanical check saw it; the differential judge did.

A computed factor removes the guess. There is nothing left to lean on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nm.core.limitation import Factor, FactorKind
from nm.domain.matter import Fact, FactId
from nm.domain.quotable import Quotable
from nm.domain.traceability import implements

#: The two this reads. Exclusion, disability, fraud, notice periods and
#: continuing breach are each their own section and their own question, and a
#: producer that guessed at all seven would be a producer nobody could check.
#: They stay NOT_ASSESSED and are SAID to be, rather than read as absent.
READS = (FactorKind.ACKNOWLEDGMENT, FactorKind.PART_PAYMENT)

#: Which section has to have been retrieved before each kind may be built.
SECTION_FOR: dict[FactorKind, str] = {
    FactorKind.ACKNOWLEDGMENT: "18",
    FactorKind.PART_PAYMENT: "19",
}

FACTOR_SCHEMA: dict = {
    "x-nm-read": "factors",
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            # `none` IS A REQUIRED MEMBER. A schema whose every value is a
            # finding forces one, and the product then restarts a limitation
            # period on a letter that admits nothing. Same reason
            # `cannot_tell` is in the cause schema.
            "enum": [*(k.value for k in READS), "none"],
        },
        "fact_id": {
            "type": "string",
            "description": "The id of the chronology entry this is, exactly as "
                           "given. Empty when `kind` is `none`.",
        },
        "quoted": {
            "type": "string",
            "description": "The advocate's OWN words describing the writing or "
                           "the payment, verbatim. Empty when `kind` is `none`.",
        },
        "in_writing": {
            "type": "boolean",
            "description": "True only if the account says it was WRITTEN. A "
                           "spoken admission is not an acknowledgment under "
                           "s.18, however clear it was.",
        },
        "why": {
            "type": "string",
            "description": "One clause, shown to the advocate so they can "
                           "correct it.",
        },
    },
    "required": ["kind", "fact_id", "quoted", "in_writing", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read an Indian advocate's account of a matter and decide ONE thing: "
    "does it describe a WRITING that admits the liability, or a PAYMENT made "
    "on account of it — and which entry in the chronology is it.\n\n"
    "You are not deciding whether the claim is in time and you are not "
    "computing any date. Both of those are done for you from what you "
    "return.\n\n"
    "Answer `none` unless the account plainly describes one. `in_writing` is "
    "true only where the account says it was written; an admission made on the "
    "telephone is not an acknowledgment under s.18 however clear it was.\n\n"
    "`quoted` must be the advocate's own words, copied exactly. Never quote "
    "the questions put to them and never paraphrase."
)


@dataclass(frozen=True)
class ReadFactors:
    """THREE STATES, and the third is the one that was missing.

    `factors` empty with `examined=True` means the account was read and
    describes none — an ordinary silence. `examined=False` means nothing read
    it, which is NOT the same and must never render as the same: it is the
    difference between "no acknowledgment on this file" and "nobody looked".
    """

    factors: tuple[Factor, ...] = ()
    examined: bool = False
    why_not: str = "nothing has read this account for acknowledgments"
    refused: str | None = None
    quoted: str = ""

    @property
    def state(self) -> str:
        """FOUR values, and the fourth was collapsed into a wrong one.

        This returned `none_found` for a REFUSED read, because `refused` sets
        `examined=True` and carries no factors — so a model output the product
        declined rendered identically to an account that genuinely describes
        no acknowledgment. Written into this module's own docstring as the
        distinction it exists to make, and then not made.

        Caught by its own test on the first run.
        """
        if not self.examined:
            return "not_assessed"
        if self.refused:
            return "refused"
        return "found" if self.factors else "none_found"


UNREAD = ReadFactors()


def not_assessed(why: str) -> ReadFactors:
    """An explicit NOT ASSESSED. The reason is a VALUE, not a null."""
    return ReadFactors(examined=False, why_not=why)


@implements("D2")
def build_prompt(quotable: Quotable, chronology: tuple[Fact, ...]):
    """This turn, read against the file AND against the dated entries.

    The chronology is included because the model must name WHICH entry it
    means, and a free-text date would have to be matched back by parsing —
    which is a second place for the date to be wrong.
    """
    from nm.ports.model import Prompt

    entries = "\n".join(
        f"  {f.id}\t{f.date.isoformat() if f.date else 'undated'}\t{f.statement}"
        for f in chronology) or "  (no dated entries)"
    # THE SCHEMA GOES TO `structured`, NOT ONTO THE PROMPT. `system` is the
    # cacheable prefix and matter-specific content belongs in `user`, which is
    # why `Prompt` holds only those two fields.
    return Prompt(
        system=SYSTEM,
        user=(f"THE CHRONOLOGY (id, date, what it says). Name an id from here "
              f"in `entry`; the statements are shown so you know which entry "
              f"is which:\n{entries}\n\n{quotable.block()}"),
    )


@implements("D2")
def read(said: dict, chronology: tuple[Fact, ...], quotable: Quotable,
         provisions: dict[str, str], unextended_expiry: date | None,
         ) -> ReadFactors:
    """Turn what the model said into a Factor, or refuse it and say why.

    `provisions` maps a section number to the RETRIEVED SPAN for it. A section
    that was not retrieved cannot support a factor: `Factor.finding` is
    required by the type precisely so that an extending provision asserted
    from memory cannot be constructed, and filling it with a summary of the
    section would defeat the type while satisfying it.
    """
    kind_said = str(said.get("kind") or "none")
    if kind_said == "none":
        return ReadFactors(examined=True, why_not=str(said.get("why") or ""),
                           quoted="")

    try:
        kind = FactorKind(kind_said)
    except ValueError:
        return _refused(f"the model returned a kind outside the schema: "
                        f"{kind_said!r}")
    if kind not in READS:
        return _refused(f"{kind.value} is not one of the two this reads")

    # THE ENTRY MUST BE ON THE FILE. A factor hanging off a fact the
    # chronology does not hold moves a date from nothing.
    fact_id = str(said.get("fact_id") or "").strip()
    entry = next((f for f in chronology if f.id == fact_id), None)
    if entry is None:
        return _refused(
            f"the model named fact {fact_id!r}, which is not on this "
            f"chronology. A factor must attach to an entry the file holds.")
    if entry.date is None:
        return _refused(
            f"fact {fact_id} carries no date, so nothing can run from it")

    # THE WORDS MUST BE THE ADVOCATE'S. Same guard as the cause read: a
    # paraphrase that reads as a quotation is how a finding acquires evidence
    # it does not have.
    quoted = str(said.get("quoted") or "")
    if not quoted.strip():
        return _refused("the model gave no quotation for the writing")
    # THE ENTRY IS ADDED TO WHAT MAY BE QUOTED, not checked separately.
    # The prompt SHOWS the entry's statement in the chronology table, and the
    # account it was also shown may have been cut by the budget while the
    # entry itself is whole -- so a quotation from it is exactly what the
    # prompt invited, and refusing it would be B-108 in miniature.
    if not quotable.plus(entry.statement).accepts(quoted):
        return _refused(
            "the quoted words are not in the advocate's account. A paraphrase "
            "presented as a quotation is a finding with evidence it does not "
            "have.")

    # s.18 REQUIRES A WRITING, IN TERMS. A spoken admission does not restart.
    if kind is FactorKind.ACKNOWLEDGMENT and not said.get("in_writing"):
        return ReadFactors(
            examined=True, quoted=quoted,
            why_not=("the account describes an admission that was not in "
                     "writing; s.18 requires a signed writing, so it does not "
                     "restart the period"))

    # AND IT MUST PRE-DATE THE BAR. Both sections apply only where the
    # acknowledgment or payment was made BEFORE the period expired -- one made
    # after it revives nothing. This is arithmetic, so it is decided here and
    # not by whatever the model believed.
    if unextended_expiry is not None and entry.date > unextended_expiry:
        return ReadFactors(
            examined=True, quoted=quoted,
            why_not=(f"the {kind.value.replace('_', ' ')} is dated "
                     f"{entry.date.isoformat()}, after the period expired on "
                     f"{unextended_expiry.isoformat()}. Section "
                     f"{SECTION_FOR[kind]} applies only to one made before "
                     f"expiry, so it does not revive the claim."))

    # AND THE SECTION MUST HAVE BEEN RETRIEVED.
    span = provisions.get(SECTION_FOR[kind])
    if not (span or "").strip():
        return not_assessed(
            f"the account describes a {kind.value.replace('_', ' ')}, and "
            f"section {SECTION_FOR[kind]} of the Limitation Act was not "
            f"retrieved on this turn. I will not move a date on a provision I "
            f"have not read.")

    return ReadFactors(
        factors=(Factor(kind=kind, fact=FactId(entry.id), finding=span,
                        restarts_from=entry.date),),
        examined=True, quoted=quoted,
        why_not=str(said.get("why") or ""))


def _refused(why: str) -> ReadFactors:
    """A model output this product DECLINED, which is worth saying.

    Distinct from `examined=True, factors=()`: that is the account genuinely
    describing none. This is the account possibly describing one and the
    product refusing what came back — an ordinary silence and a rejected
    answer must not render alike.
    """
    return ReadFactors(examined=True, refused=why, why_not=why)
