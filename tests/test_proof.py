"""S7 — proof and burden. D5, D5.1, and the three NEVER clauses.

D5.1 IS TWO RULES AND THE SECOND IS THE DANGEROUS ONE. *Do not accuse the
client. State the facts plainly and strongly, exactly as they are.* None of it
licenses hedging: NM softens the ATTRIBUTION and never the FINDING, and the
drift runs one way — a model told to be careful with a client will not stop at
withholding the character judgement, it will soften the weakness and bury the
exposure in qualifications. That is the failure that loses cases and it is the
more likely of the two, because agreeable language is the path of least
resistance.

So every test here that checks the restraint also checks the bound.
"""
from __future__ import annotations

import pytest

from nm.core.proof import (
    Burden,
    ProofPosition,
    ProofStatus,
    Standard,
    characterises_the_client,
    unclosed,
    uncovered,
)
from nm.domain.matter import Basis, Posture, Role, Side
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

CAUSE = ("the loan was advanced", "the sum is due", "demand was made",
         "the suit is in time", "the defendant received the money")


def _held(element: str) -> ProofPosition:
    return ProofPosition(
        element=element, burden=Burden(on=Side.MOVING),
        standard=Standard.BALANCE_OF_PROBABILITIES,
        status=ProofStatus.HELD, material=("the bank statement for March",))


# ============ D5.0 — no element without burden, standard and status =========


@refuses("D5", 0)
@pytest.mark.eval_id("E-070")
def test_no_element_exists_without_a_burden_a_standard_and_a_status():
    """E-070's counterexample: *a conclusion where two of five elements have no
    proof position at all.*

    The conclusion looked complete. Three elements were worked through
    carefully and two were never mentioned, so nothing in the output was wrong
    — it was short, and short is invisible.
    """
    positions = tuple(_held(e) for e in CAUSE[:3])

    missing = uncovered(CAUSE, positions)
    assert len(missing) == 2, "the two unworked elements were not reported"
    assert "the suit is in time" in missing
    assert "the defendant received the money" in missing

    # COMPLETE COVERAGE REPORTS NOTHING, so the check is not simply noisy.
    assert uncovered(CAUSE, tuple(_held(e) for e in CAUSE)) == ()


@refuses("D5", 0)
@pytest.mark.eval_id("E-070")
def test_the_coverage_gate_cannot_certify_itself():
    """D5: *never let the proof-coverage gate certify itself.*

    THE POPULATION IS THE ELEMENTS. Asked the other way round — do all the
    positions have elements — it reports complete coverage of whatever happened
    to be there and cannot fail, which is what B-049 was.
    """
    positions = tuple(_held(e) for e in CAUSE[:1])

    # One position covering one of five elements is 80% uncovered, and the
    # check says so. A self-certifying version would return () here.
    assert len(uncovered(CAUSE, positions)) == 4

    # AND WITH NO POSITIONS AT ALL it reports every element, rather than
    # reporting nothing because there was nothing to iterate.
    assert len(uncovered(CAUSE, ())) == len(CAUSE)


@refuses("D5", 0)
@pytest.mark.eval_id("E-070")
def test_a_status_without_a_standard_cannot_be_constructed():
    """*To what standard* is half of whether the material is enough. An element
    HELD to the wrong standard is not held."""
    with pytest.raises(ValueError) as exc:
        ProofPosition(element="the loan was advanced",
                      burden=Burden(on=Side.MOVING),
                      status=ProofStatus.HELD,
                      material=("the ledger",))
    assert "no standard" in str(exc.value)

    # HELD WITH NOTHING UNDER IT is refused too: held by what?
    with pytest.raises(ValueError) as exc2:
        ProofPosition(element="the loan was advanced",
                      burden=Burden(on=Side.MOVING),
                      standard=Standard.BALANCE_OF_PROBABILITIES,
                      status=ProofStatus.HELD)
    assert "no material behind it" in str(exc2.value)


@pytest.mark.eval_id("E-070")
def test_a_presumption_that_shifts_the_burden_names_its_provision():
    """D5: *state the burden as it actually falls, including where a
    presumption shifts it.*

    A presumption is a section. One asserted from memory is the same defect as
    an extending provision asserted from memory, and it decides who loses when
    the evidence is silent.
    """
    with pytest.raises(ValueError) as exc:
        Burden(on=Side.DEFENDING,
               shifted_by="the holder in due course presumption")
    assert "provision that shifts it" in str(exc.value)

    ok = Burden(on=Side.DEFENDING,
                shifted_by="the presumption of consideration",
                shift_provision="Negotiable Instruments Act, 1881 s.118")
    assert ok.shift_provision


@pytest.mark.eval_id("E-070")
def test_the_same_presumption_is_a_gift_or_a_problem_depending_on_the_side():
    """D5 says it in those words, and it is D9's rule about `effect` in a
    different place — so it gets the same treatment rather than a second one.
    """
    burden = Burden(on=Side.DEFENDING,
                    shifted_by="the presumption of consideration",
                    shift_provision="Negotiable Instruments Act, 1881 s.118")

    defending = Posture(role=Role.DEFENDANT, basis=Basis.STATED)
    moving = Posture(role=Role.PLAINTIFF, basis=Basis.STATED)
    assert burden.falls_on_us(defending) is True
    assert burden.falls_on_us(moving) is False

    # UNRESOLVED IS `None`, NEVER `False`. `False` reads as "the opponent must
    # prove it", which is the comfortable answer and one nobody established.
    assert burden.falls_on_us(Posture()) is None


# ============ D5.1 — a proof gap is never reported as a verdict =============


@refuses("D5", 1)
@pytest.mark.eval_id("E-071")
def test_a_proof_gap_is_never_a_verdict():
    """D5: *never report a proof gap as a verdict. "You cannot prove the loan"
    fails. "The loan needs the bank statement for that month and the ledger
    entry; both are ordinarily with the client" is the requirement.*

    The type refuses the verdict, so it is not a thing a reviewer has to catch.
    """
    with pytest.raises(ValueError) as exc:
        ProofPosition(element="the loan was advanced",
                      burden=Burden(on=Side.MOVING),
                      standard=Standard.BALANCE_OF_PROBABILITIES,
                      status=ProofStatus.OBTAINABLE)
    assert "what would obtain it" in str(exc.value)

    # ABSENT MUST NAME THE DEAD END. An advocate told a thing cannot be proved,
    # with no reason, cannot tell whether to look harder or change the case.
    with pytest.raises(ValueError) as exc2:
        ProofPosition(element="the oral agreement",
                      burden=Burden(on=Side.MOVING),
                      standard=Standard.BALANCE_OF_PROBABILITIES,
                      status=ProofStatus.ABSENT)
    assert "express dead end" in str(exc2.value)

    # THE REQUIREMENT, in D5's own words, constructs.
    ok = ProofPosition(
        element="the loan was advanced", burden=Burden(on=Side.MOVING),
        standard=Standard.BALANCE_OF_PROBABILITIES,
        status=ProofStatus.OBTAINABLE,
        closing_material=("the bank statement for that month and the ledger "
                          "entry; both are ordinarily with the client"))
    assert ok.is_gap and unclosed((ok,)) == ()


@refuses("D5", 1)
@pytest.mark.eval_id("E-071")
def test_an_unassessed_element_still_owes_the_advocate_an_account():
    """NOT_ASSESSED is legitimate and is still a gap.

    `unclosed` is computed even though the type guard exists, because a guard
    proves nothing about positions decoded from an older store — and because
    "we did not look" is exactly the state that reads as "there is nothing".
    """
    not_looked = ProofPosition(element="the suit is in time",
                               burden=Burden(on=Side.MOVING))
    assert not_looked.status is ProofStatus.NOT_ASSESSED
    assert not_looked.is_gap
    assert unclosed((not_looked,)) == ("the suit is in time",)


# ============ D5.1 — proof, never honesty; AND never softened ==============


@refuses("D5", 2)
@pytest.mark.eval_id("E-072")
def test_no_output_characterises_the_clients_honesty_or_character():
    """E-072's counterexample: *"Your client is concealing the payment."*

    NM has not met the client, has not seen them answer a question, and holds
    no material on which a credibility finding could rest. The judgement is
    outside its competence, not merely impolite — and it is MISDIRECTED, since
    NM speaks to the advocate, not the client.
    """
    for bad in ("Your client is concealing the payment.",
                "This account is not credible, and your client is lying.",
                "The client fabricated this and the story is implausible."):
        assert characterises_the_client(bad), f"not caught: {bad!r}"

    # D5.1's OWN REPLACEMENTS pass. A check that failed these would be a check
    # against saying anything.
    for good in (
            "Nothing in the file supports this account, and the other side "
            "holds the cheque.",
            "If the payment was made, what evidences it? Without something, "
            "the payment cannot be put to the court.",
            "This will not survive cross-examination on these materials. "
            "Here is what would change that."):
        assert characterises_the_client(good) == (), f"wrongly caught: {good!r}"


@refuses("D5", 2)
@pytest.mark.eval_id("E-072")
def test_the_restraint_does_not_extend_to_the_opponent_or_to_the_finding():
    """THE BOUND, AND IT MATTERS MORE THAN THE RULE IT BOUNDS.

    A check firing on both sides would push exactly the wrong way. The drift
    this rule is most at risk from is SOFTENING a weakness, not accusing — so
    saying the opponent's account is not credible is advocacy, and a guard that
    refused it would be teaching the product to hedge.
    """
    assert characterises_the_client(
        "The opponent's account is not credible and the defendant is lying "
        "about the cheque.") == ()

    # AND THE ADVERSE FINDING AGAINST OUR OWN SIDE IS STATED, not hedged. This
    # is the sentence the drift would soften, and nothing here objects to it.
    plain = ("The agreement is unregistered, so it cannot be received to prove "
             "the sale. That is fatal to the title claim as pleaded.")
    assert characterises_the_client(plain) == ()

    # THE TYPE CARRIES NO HEDGING FIELD. A confidence adjective on a proof
    # position is where a softened finding would live.
    assert not any(f in ProofPosition.__dataclass_fields__
                   for f in ("confidence", "hedge", "tone", "severity"))


# ============ C7 — existence, admissibility and weight are three ============


@pytest.mark.eval_id("E-070")
def test_existence_admissibility_and_weight_are_three_separate_questions():
    """C7. The original contract held two of the three, so *admissible* and
    *persuasive* had one field between them — and an advocate plans
    differently for each.

    A WhatsApp exchange EXISTS; whether it goes in depends on the
    electronic-records certificate; whether it moves a judge is a third
    question again. Collapsing any two produces an item that reads as settled
    when one was never asked.
    """
    from nm.core.evidence_item import (
        Admissibility,
        EvidenceItem,
        Existence,
        Form,
        Holder,
        Weight,
        unasked,
    )

    whatsapp = EvidenceItem(
        what="the WhatsApp exchange admitting the debt",
        holder=Holder.CLIENT, form=Form.ELECTRONIC,
        existence=Existence.HELD,
        admissibility=Admissibility.NEEDS,
        admissibility_needs=("a s.65B electronic-records certificate",),
        weight=Weight.STRONG,
        weight_reason="it is the debtor's own words, on his own number")

    assert whatsapp.existence is not whatsapp.admissibility
    assert (whatsapp.existence, whatsapp.admissibility, whatsapp.weight) == (
        Existence.HELD, Admissibility.NEEDS, Weight.STRONG)
    assert unasked((whatsapp,)) == (), "all three were answered"

    # AN ITEM WITH ONE QUESTION UNPUT IS NAMED, and names WHICH.
    half = EvidenceItem(what="the ledger", existence=Existence.HELD)
    reported = unasked((half,))
    assert reported and "admissibility" in reported[0] and "weight" in reported[0]

    # `needs` WITH NOTHING NAMED is a dead end dressed as a next step.
    with pytest.raises(ValueError) as exc:
        EvidenceItem(what="the ledger", admissibility=Admissibility.NEEDS)
    assert "dead end" in str(exc.value)

    # AND WEIGHT WITH NO REASON cannot be argued or challenged.
    with pytest.raises(ValueError):
        EvidenceItem(what="the ledger", weight=Weight.WEAK)


@pytest.mark.eval_id("E-070")
def test_an_item_at_risk_with_no_preservation_step_is_reported():
    """C7's counterexample: *a file where the original agreement is with the
    opponent's brother and no preservation or production step exists.*

    The item is inventoried, its holder is recorded, and nothing was asked of
    anyone — so the file reads as worked and the document is gone by the time
    it is needed.
    """
    from datetime import date as _date

    from nm.core.evidence_item import (
        EvidenceItem,
        Existence,
        Form,
        Holder,
        Preservation,
        unpreserved,
    )

    exposed = EvidenceItem(
        what="the original agreement of sale", holder=Holder.THIRD_PARTY,
        form=Form.ORIGINAL, existence=Existence.OBTAINABLE)
    assert exposed.at_risk
    assert unpreserved((exposed,)) == ("the original agreement of sale",)

    # A PRESERVATION INSTRUCTION NEEDS AN OWNER AND A DATE. Without both it is
    # a wish, and the type is what stops a wish being recorded as an
    # instruction.
    with pytest.raises(TypeError):
        Preservation(owner="the instructing advocate")
    with pytest.raises(ValueError):
        Preservation(owner="   ", due=_date(2026, 9, 30))

    stepped = EvidenceItem(
        what="the original agreement of sale", holder=Holder.THIRD_PARTY,
        form=Form.ORIGINAL, existence=Existence.OBTAINABLE,
        preservation=Preservation(owner="the instructing advocate",
                                  due=_date(2026, 9, 30)))
    assert unpreserved((stepped,)) == ()

    # THE CLIENT'S OWN DOCUMENT IS NOT "AT RISK" in this sense — a check that
    # flagged everything would be ignored within a week.
    assert unpreserved((EvidenceItem(what="the client's ledger",
                                     holder=Holder.CLIENT),)) == ()

    # AND THE THIRD STATE: written, and never issued. `unpreserved` reports
    # nothing about it because there IS an instruction, so without a separate
    # check the two failures are indistinguishable to everyone except the
    # document, which is gone either way.
    from nm.core.evidence_item import undelivered
    assert undelivered((stepped,)) == ("the original agreement of sale",)
    assert undelivered((exposed,)) == (), "no instruction is not an unissued one"

    issued = EvidenceItem(
        what="the original agreement of sale", holder=Holder.THIRD_PARTY,
        form=Form.ORIGINAL, existence=Existence.OBTAINABLE,
        preservation=Preservation(owner="the instructing advocate",
                                  due=_date(2026, 9, 30),
                                  issued_at=_date(2026, 8, 31)))
    assert undelivered((issued,)) == ()


@pytest.mark.eval_id("E-070")
def test_a_photocopy_is_not_the_document():
    """C7. One `form` string that does not distinguish them makes the s.65
    secondary-evidence position invisible — and that position is the whole
    answer on a file where the original sits with the opponent's brother."""
    from nm.core.evidence_item import Form

    assert Form.ORIGINAL is not Form.PHOTOCOPY
    assert Form.CERTIFIED_COPY is not Form.PHOTOCOPY
    assert Form.NOT_ASSESSED in list(Form), (
        "there is no way to say the form was never established, so every item "
        "asserts one")


@pytest.mark.eval_id("E-070")
def test_a_thing_that_does_not_exist_carries_no_admissibility_position():
    """The collapse C7 separates the three questions to prevent. Admissibility
    of what?"""
    from nm.core.evidence_item import Admissibility, EvidenceItem, Existence

    with pytest.raises(ValueError) as exc:
        EvidenceItem(what="the missing receipt", existence=Existence.ABSENT,
                     admissibility=Admissibility.ADMISSIBLE_AS_HELD)
    assert "does not exist" in str(exc.value)


@pytest.mark.eval_id("E-072")
def test_the_served_turn_records_a_characterisation_of_the_client(tmp_path):
    """E-072 IS CLASS B, EVERY TURN — so it is asserted on the served path.

    The sentence that breaches D5.1 is model prose and the model writes it at
    the last moment, so a module-level check would prove only that the function
    works.
    """
    from datetime import date as _date

    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path, responses={
        "__default__": "Your client is concealing the payment; press them."})
    out = engine.run(TurnInput(
        advocate_id="adv", today=_date(2026, 8, 31),
        message=("we act for the plaintiff. the goods were supplied against "
                 "invoices dated 14 March 2023.")))

    breaches = [v for v in out.metrics.violations
                if v.rule == "D5" and "judges the client" in v.detail]
    assert breaches, (
        "the answer characterised the client and nothing recorded it:\n"
        + "\n".join(e.text for e in out.answer.elements))

    # THE SUBSTANCE STILL SHIPS. Withholding the turn over one bad sentence
    # would cost the advocate the analysis, and D5.1's bound says the drift to
    # design against is SOFTENING, not accusing.
    assert out.answer.elements
    assert not out.answer.blocked
