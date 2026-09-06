"""What each cause of action REQUIRES. Curated, never generated. D5.

WHY THIS IS A TABLE AND NOT A READ
------------------------------------
D5 says every element carries who must prove it, to what standard, and with
what material. The STATUS is a question about this file and a model answers it;
the ELEMENT LIST is a question about the law and a model must not.

A model asked for "the elements of specific performance" returns four or five
plausible items, most of them right, in an order and a wording that changes
between calls. Every proof position downstream then rests on a list nobody
authored, `uncovered` reports complete coverage of whatever the model happened
to produce, and D5's third NEVER -- the coverage gate may not certify itself --
is defeated one layer above where it looks.

It is CLAUDE.md §5 in a place the rule does not obviously reach: fuzzy matching
may rank, never identify. A generated element list is identification by
plausibility, and the thing being identified is what the advocate has to prove.

CURATED CONSERVATIVELY, THE SAME WAY `LIMITATION_ARTICLE` IS
--------------------------------------------------------------
A cause whose elements are genuinely arguable is LEFT OUT rather than guessed.
An absent entry produces `ProofStatus.NOT_ASSESSED` against a named reason,
which is a worse answer and an honest one; a wrong list is a confident answer
and nothing downstream catches it. `POSSESSION_ON_PREVIOUS_POSSESSION` is out
for exactly that reason -- see its note below.

`curated_from` IS REQUIRED BY THE TYPE, as it is on `Edge`. A legal decision
that cannot say where it came from is one somebody remembered, and this file is
precisely where remembering would be invisible.

THE BURDEN IS PART OF THE CURATION, THE SIDE IS NOT
-----------------------------------------------------
Each element records which SIDE bears it -- moving or defending -- which is a
fact about the element. Whether that side is US is `Burden.falls_on_us`, which
takes the posture. D9's rule about `effect`, applied here for the same reason:
"this is a problem for us" baked into the table would be wrong for half the
advocates who ever read it.
"""
from __future__ import annotations

from nm.domain.matter import CauseOfAction, Side
from nm.domain.proof import Standard
from nm.domain.traceability import implements
from nm.ports.elements import Elements, Ingredient

#: Cause of action to what it requires. TASK T-052's sibling.
#:
#: EVERY ENTRY IS CIVIL AND PROVED ON THE BALANCE OF PROBABILITIES except the
#: s.138 offence, which is criminal and is not in this table at all -- see the
#: note under CHEQUE_DISHONOUR below.
ELEMENTS: dict[CauseOfAction, Elements] = {

    CauseOfAction.GOODS_SOLD_PRICE: Elements(
        cause=CauseOfAction.GOODS_SOLD_PRICE,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Sale of Goods Act, 1930 ss.4 and 55 — the price of "
                     "goods sold and delivered, where the property has passed "
                     "and the price is due",
        ingredients=(
            Ingredient(element="A contract of sale, and its terms as to price",
                       on=Side.MOVING,
                       serves="fixes what was owed and on what terms"),
            Ingredient(element="Delivery of the goods, or that property in "
                               "them passed to the buyer",
                       on=Side.MOVING,
                       serves="s.55 gives the action for the price only where "
                              "property has passed or the price is payable on "
                              "a day certain"),
            Ingredient(element="That the price has not been paid",
                       on=Side.MOVING,
                       serves="the claim itself"),
            Ingredient(element="Payment, in whole or in part",
                       on=Side.DEFENDING,
                       serves="a defendant who says it was paid must prove "
                              "the payment"),
        )),

    CauseOfAction.MONEY_LENT: Elements(
        cause=CauseOfAction.MONEY_LENT,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Indian Contract Act, 1872 s.2(d) and the common count "
                     "for money lent and advanced; Limitation Act Article 19 "
                     "treats the cause as arising when the loan is made",
        ingredients=(
            Ingredient(element="That the money was actually advanced to the "
                               "defendant",
                       on=Side.MOVING,
                       serves="a loan agreement without the advance is a "
                              "promise, not a debt"),
            Ingredient(element="That it was advanced as a LOAN and not as a "
                               "gift or in discharge of another obligation",
                       on=Side.MOVING,
                       serves="the character of the payment is what makes it "
                              "repayable"),
            Ingredient(element="The terms of repayment, including any agreed "
                               "date or demand",
                       on=Side.MOVING,
                       serves="fixes when the cause arose and what is due"),
            Ingredient(element="Repayment, in whole or in part",
                       on=Side.DEFENDING,
                       serves="a defendant who says it was repaid must prove "
                              "the repayment"),
        )),

    CauseOfAction.BREACH_OF_CONTRACT: Elements(
        cause=CauseOfAction.BREACH_OF_CONTRACT,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Indian Contract Act, 1872 ss.10, 37 and 73 — a "
                     "concluded contract, its breach, and compensation for "
                     "loss naturally arising",
        ingredients=(
            Ingredient(element="A concluded contract between these parties, "
                               "and its terms",
                       on=Side.MOVING,
                       serves="there is nothing to breach until the contract "
                              "and its terms are established"),
            Ingredient(element="Performance by the plaintiff, or readiness "
                               "and willingness to perform",
                       on=Side.MOVING,
                       serves="s.37: a party seeking performance must show "
                              "they were not themselves in default"),
            Ingredient(element="The breach relied on, as an act or omission "
                               "against a named term",
                       on=Side.MOVING,
                       serves="a breach pleaded generally cannot be met and "
                              "cannot be proved"),
            Ingredient(element="Loss flowing from the breach, and its "
                               "quantification",
                       on=Side.MOVING,
                       serves="s.73 gives compensation for loss naturally "
                              "arising; a breach with no proved loss carries "
                              "nominal damages"),
        )),

    CauseOfAction.SPECIFIC_PERFORMANCE: Elements(
        cause=CauseOfAction.SPECIFIC_PERFORMANCE,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Specific Relief Act, 1963 ss.10 and 16(c) as amended by "
                     "Act 18 of 2018 — performance is no longer discretionary, "
                     "and the plaintiff must plead and prove readiness and "
                     "willingness throughout",
        ingredients=(
            Ingredient(element="A concluded and enforceable agreement, and "
                               "its terms",
                       on=Side.MOVING,
                       serves="an agreement void or uncertain in its terms "
                              "cannot be specifically enforced"),
            Ingredient(element="Readiness and willingness to perform, "
                               "CONTINUOUSLY from the agreement to the suit",
                       on=Side.MOVING,
                       serves="s.16(c): it must be pleaded and proved for the "
                              "whole period, and this is where these suits "
                              "most often fail"),
            Ingredient(element="That the plaintiff performed, or was always "
                               "willing to perform, the essential terms",
                       on=Side.MOVING,
                       serves="s.16(c) again, on the acts as distinct from "
                              "the state of mind"),
            Ingredient(element="The defendant's refusal or failure to perform",
                       on=Side.MOVING,
                       serves="the cause of action, and the date it arose for "
                              "Article 54"),
            Ingredient(element="That the plaintiff is a subsequent transferee "
                               "for value without notice",
                       on=Side.DEFENDING,
                       serves="s.19(b): the defence that defeats the decree "
                              "against a bona fide purchaser, and it is theirs "
                              "to prove"),
        )),

    CauseOfAction.POSSESSION_ON_TITLE: Elements(
        cause=CauseOfAction.POSSESSION_ON_TITLE,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Limitation Act, 1963 Article 65 and the settled rule "
                     "that a plaintiff in ejectment succeeds on the strength "
                     "of their own title and not on the weakness of the "
                     "defendant's",
        ingredients=(
            Ingredient(element="The plaintiff's title to the suit property, "
                               "and its extent",
                       on=Side.MOVING,
                       serves="the whole basis of the suit: it succeeds on "
                              "the strength of this title alone"),
            Ingredient(element="Identity of the suit property, by boundaries "
                               "or survey number",
                       on=Side.MOVING,
                       serves="a decree for possession of land nobody can "
                              "identify cannot be executed"),
            Ingredient(element="That the defendant is in possession, and the "
                               "date it began",
                       on=Side.MOVING,
                       serves="fixes both the relief and the start of the "
                              "twelve years under Article 65"),
            Ingredient(element="Adverse possession for twelve years — "
                               "possession that is open, hostile to the true "
                               "owner, and to their knowledge",
                       on=Side.DEFENDING,
                       serves="Article 65 puts this on the defendant, and it "
                              "extinguishes the title under s.27 if proved"),
        )),

    CauseOfAction.DECLARATION: Elements(
        cause=CauseOfAction.DECLARATION,
        standard=Standard.BALANCE_OF_PROBABILITIES,
        curated_from="Specific Relief Act, 1963 s.34 — the plaintiff must be "
                     "entitled to a legal character or right to property, the "
                     "defendant must deny or be interested in denying it, and "
                     "the proviso bars a declaration where consequential "
                     "relief could be sought and was not",
        ingredients=(
            Ingredient(element="The legal character or right to property the "
                               "plaintiff claims",
                       on=Side.MOVING,
                       serves="s.34 gives the declaration only to a person "
                              "entitled to one of these"),
            Ingredient(element="The defendant's denial of it, or their "
                               "interest in denying it",
                       on=Side.MOVING,
                       serves="a declaration nobody disputes is an advisory "
                              "opinion, which the section does not authorise"),
            Ingredient(element="That no further relief beyond the declaration "
                               "could have been sought, or that it has been "
                               "sought",
                       on=Side.MOVING,
                       serves="the s.34 proviso is a bar the court applies of "
                              "its own motion, and it defeats the suit"),
        )),
}


#: CAUSES DELIBERATELY LEFT OUT, with the reason. NOT an oversight, and stated
#: here rather than discovered as an absence.
#:
#: Read by `elements_for` so the refusal names the reason instead of returning
#: a bare None -- which would be indistinguishable from a cause nobody has got
#: to yet, and those are different facts about the product.
WITHHELD: dict[CauseOfAction, str] = {
    CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION:
        "the ingredients turn on which route is pleaded and they are not the "
        "same list. Specific Relief Act s.6 asks only about dispossession "
        "within six months and expressly forbids any question of title; "
        "Article 64 is a possessory suit where title is open. Curating one "
        "list for both would make the product ask an advocate for material "
        "the section they are on does not need, and miss the six-month bar "
        "that decides the s.6 route entirely.",
    CauseOfAction.CHEQUE_DISHONOUR:
        "s.138 of the Negotiable Instruments Act is a CRIMINAL offence proved "
        "beyond reasonable doubt, with statutory presumptions under ss.118 and "
        "139 that reverse the burden once the signature is admitted. Putting "
        "it in a table whose other entries are civil claims on the balance of "
        "probabilities is how a standard gets applied to the wrong case. It "
        "needs its own curation with the presumptions expressed as "
        "`Burden.shifted_by`, and that is work rather than a line here.",
}


@implements("D5")
def elements_for(cause: CauseOfAction) -> Elements | None:
    """The ingredients of a cause. EXACT, or `None`.

    `None` is not failure and must not be read as one. A cause this table does
    not hold produces NOT_ASSESSED against a named reason, which is what
    `ProofStatus.NOT_ASSESSED` exists to say: "we did not work it out" and not
    "nothing would establish it".
    """
    if cause is CauseOfAction.NOT_ESTABLISHED:
        return None
    return ELEMENTS.get(cause)


@implements("D5")
def why_not(cause: CauseOfAction) -> str:
    """Why this cause has no ingredients, in words for the advocate.

    THREE STATES, AND THIS IS THE THIRD SAID OUT LOUD. A cause deliberately
    withheld and a cause nobody has curated are different facts: the first is a
    decision with a reason, the second is a gap in the product. An advocate
    told only "not assessed" cannot tell which, and the two call for different
    things from them -- supply the missing route, or wait.
    """
    if cause is CauseOfAction.NOT_ESTABLISHED:
        return ("the cause of action on this thread has not been established, "
                "so there is no element list to work from")
    if cause in ELEMENTS:
        return ""
    if cause in WITHHELD:
        return WITHHELD[cause]
    return (f"the elements of {cause.value.replace('_', ' ')} are not curated "
            f"in this product yet. Nothing has been guessed in their place.")
