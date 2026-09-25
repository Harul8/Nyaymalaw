"""THE CURATED INTERIM TESTS. LB-123.

The shapes and the reasoning about them are in `backend/nm/ports/interim_relief.py`.
This module is the curation: what each interim relief must SHOW, and under
which rule. Nothing here asserts current law -- every row points at the
provision or decision that must be RETRIEVED AND READ BACK before it is relied
on, the same discipline `nm.knowledge.institution` keeps.

CURATED CONSERVATIVELY. A relief whose test is genuinely contested is left OUT
rather than guessed. An absent row leaves the interim position reading NOT
ASSESSED and naming the gap, which is a worse answer and an honest one; a
wrong row measures an application against the wrong threshold, which is the
defect this row exists to refuse.

NOT COUNSEL-REVIEWED. Every row below is to be retrieved and verified before
release; LB-123 records that a practising Telangana advocate signs off these
entries on the BK-85-AC3 pattern.
"""
from __future__ import annotations

from nm.domain.traceability import implements
from nm.ports.interim_relief import (
    Assessment,
    InterimRelief,
    Limb,
    LimbState,
    Test,
)

#: The three limbs an application for a temporary injunction is measured on.
#: Held once, because the prohibitory and mandatory tests share them and a
#: second copy would let one be hardened and the other not (CLAUDE.md §4).
#: The MANDATORY test does not restate them -- it adds a threshold note.
_INJUNCTION_LIMBS: tuple[Limb, ...] = (
    Limb(name="a prima facie case",
         what_would_answer_it="the document or pleading that shows there is a "
                              "serious question to be tried on the right "
                              "asserted"),
    Limb(name="the balance of convenience",
         what_would_answer_it="what each side loses if the order is made and "
                              "if it is refused, on the file rather than in "
                              "argument"),
    Limb(name="irreparable injury",
         what_would_answer_it="what the applicant loses that an award of "
                              "damages at the end of the suit would not "
                              "restore"),
)

#: EVERY INTERIM TEST THIS PRODUCT KNOWS, by the relief sought. One table, so
#: the test read when the advocate states the relief and the test read when a
#: step names it cannot drift apart.
TESTS: dict[InterimRelief, Test] = {
    InterimRelief.PROHIBITORY_INJUNCTION: Test(
        relief=InterimRelief.PROHIBITORY_INJUNCTION,
        source="Code of Civil Procedure, 1908, Order XXXIX rules 1 and 2",
        curated_from="Code of Civil Procedure, 1908, Order XXXIX rr.1-2 for "
                     "the grounds, r.3 for notice and r.3A for the time within "
                     "which an ex parte order is to be disposed of; the three "
                     "limbs as stated in Dalpat Kumar v Prahlad Singh (1992) "
                     "1 SCC 719",
        limbs=_INJUNCTION_LIMBS,
        bar="Specific Relief Act, 1963, s.41 lists the cases in which an "
            "injunction cannot be granted at all -- read it before the limbs, "
            "because a barred injunction is refused however well the limbs are "
            "made out"),
    InterimRelief.MANDATORY_INJUNCTION: Test(
        relief=InterimRelief.MANDATORY_INJUNCTION,
        source="Code of Civil Procedure, 1908, Order XXXIX rules 1 and 2",
        curated_from="Code of Civil Procedure, 1908, Order XXXIX rr.1-2, read "
                     "with Dorab Cawasji Warden v Coomi Sorab Warden (1990) 2 "
                     "SCC 117 for the higher threshold on an interlocutory "
                     "mandatory injunction",
        limbs=_INJUNCTION_LIMBS,
        threshold_note="an interlocutory MANDATORY injunction is not granted "
                       "on the showing that carries a prohibitory one -- a "
                       "higher standard than a prima facie case is required, "
                       "and the relief is granted to restore a status quo "
                       "that was disturbed rather than to alter one",
        bar="Specific Relief Act, 1963, s.41 -- read it before the limbs"),
    InterimRelief.ATTACHMENT_BEFORE_JUDGMENT: Test(
        relief=InterimRelief.ATTACHMENT_BEFORE_JUDGMENT,
        source="Code of Civil Procedure, 1908, Order XXXVIII rule 5",
        curated_from="Code of Civil Procedure, 1908, Order XXXVIII r.5 -- the "
                     "court must be satisfied that the defendant is about to "
                     "dispose of or remove property with intent to obstruct or "
                     "delay execution of a decree; rr.5(4) and 6 on the "
                     "consequence of an attachment made without compliance",
        limbs=(
            Limb(name="the defendant's intent to obstruct or delay execution",
                 what_would_answer_it="what on the file shows the disposal or "
                                      "removal, and what connects it to the "
                                      "claim rather than to ordinary dealing"),
            Limb(name="the property to be attached, identified",
                 what_would_answer_it="the particulars of the property and "
                                      "the applicant's basis for saying it is "
                                      "the defendant's"),
        ),
        threshold_note="an attachment before judgment is an extraordinary "
                       "order; a bare apprehension of non-payment is not the "
                       "intent r.5 requires"),
    InterimRelief.RECEIVER: Test(
        relief=InterimRelief.RECEIVER,
        source="Code of Civil Procedure, 1908, Order XL rule 1",
        curated_from="Code of Civil Procedure, 1908, Order XL r.1 -- "
                     "appointment of a receiver where it appears just and "
                     "convenient, and r.1(2) on what powers may not be "
                     "conferred",
        limbs=(
            Limb(name="that it is just and convenient to appoint a receiver",
                 what_would_answer_it="what on the file shows the property is "
                                      "at risk in the hands of the person "
                                      "holding it, and that no lesser order "
                                      "meets that risk"),
        ),
        threshold_note="a receiver dispossesses a party before trial, so it "
                       "is not ordered where an injunction would meet the same "
                       "risk"),
}


@implements("D1")
def test_for(relief: InterimRelief) -> Test | None:
    """The curated test, or None where none is held.

    None is a GAP and not a finding that no test applies -- `assess` is what
    says which, and no caller reads the None directly.
    """
    return TESTS.get(relief)


@implements("D1")
def assess(relief: InterimRelief) -> Assessment:
    """Where the interim application stands, on what this product can see.

    EVERY LIMB COMES BACK NOT_ASSESSED, and that is the finding. Nothing in
    this slice reads the advocate's material -- their affidavit, the documents
    on the file -- so no limb can be called made out or wanting. What the
    advocate is given is the TEST, named limb by limb with what would answer
    each, which is the thing that was missing: an application measured against
    the merits of the suit instead of against its own rule.

    A relief nobody stated is not an application that failed. It produces an
    assessment with no test and a `because` saying so, never an empty one.
    """
    if relief is InterimRelief.NOT_STATED:
        return Assessment(
            relief=relief,
            because="no interim relief has been stated, so no interim test "
                    "has been read -- say which order is sought and the test "
                    "for it is set out")
    test = TESTS.get(relief)
    if test is None:
        return Assessment(
            relief=relief,
            because=f"no interim test is held for "
                    f"{relief.value.replace('_', ' ')}; this product holds "
                    f"tests for "
                    f"{', '.join(sorted(r.value.replace('_', ' ') for r in TESTS))}"
                    f" and does not infer one from a neighbouring relief")
    return Assessment(
        relief=relief, test=test,
        states=tuple((limb.name, LimbState.NOT_ASSESSED)
                     for limb in test.limbs),
        because="the test is set out; whether each limb is made out is read "
                "from the affidavit and the documents on the file, which "
                "nothing here has seen")


__all__ = ["TESTS", "test_for", "assess"]
