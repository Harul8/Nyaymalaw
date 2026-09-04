"""B-073 / D2 — something now produces a `Factor`, and it is cited or refused.

THE MEASURED DEFECT, stated once so every test below can point at it:

    GS-14, served. Invoices of 14 March 2023; then "the defendant wrote to us
    on 12 June 2024 admitting the amount was outstanding". The product
    answered "limitation runs to 2026-03-14" — unchanged, expired, the claim
    reported DEAD when it is alive to June 2027. The acknowledgment was on the
    file, was repeated back to the advocate, and never reached the arithmetic.

`Factor` had existed since slice 4 with `finding` required so one could not be
asserted from memory, and `compute` applied restarts correctly. Nothing ever
built one.

WHY THESE ARE RULES AND NOT THE SCENARIO
------------------------------------------
Each states a property of ANY account, and each is written so that removing
the mechanism turns it red. The one test that does use GS-14's facts uses them
as a worked example of the rule above it, not as the rule.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import factors
from nm.core.limitation import FactorKind
from nm.domain.matter import Fact, Provenance

pytestmark = pytest.mark.class_a

#: A real span, shortened. What matters is that it is TEXT THAT CAME BACK,
#: not that it is complete: `Factor.finding` exists to make the difference
#: between a retrieved provision and a remembered one unfakeable.
S18 = ("18. Effect of acknowledgment in writing.—(1) Where, before the "
       "expiration of the prescribed period for a suit or application in "
       "respect of any property or right, an acknowledgment of liability in "
       "respect of such property or right has been made in writing signed by "
       "the party against whom such property or right is claimed...")
S19 = ("19. Effect of payment on account of debt or of interest on legacy.—"
       "Where payment on account of a debt or of interest on a legacy is made "
       "before the expiration of the prescribed period by the person liable "
       "to pay the debt or legacy...")

PROV = Provenance(kind="advocate_statement", turn="t1")


def _fact(fid: str, statement: str, on: date | None) -> Fact:
    return Fact(id=fid, statement=statement, provenance=PROV, date=on)


SUPPLY = _fact("f1", "Goods were supplied against invoices", date(2023, 3, 14))
LETTER = _fact("f2", "the defendant wrote to us on 12 June 2024 admitting "
                     "the amount was outstanding", date(2024, 6, 12))
CHRON = (SUPPLY, LETTER)
ACCOUNT = "\n".join(f.statement for f in CHRON)

SAID = {
    "kind": "acknowledgment",
    "fact_id": "f2",
    "quoted": "admitting the amount was outstanding",
    "in_writing": True,
    "why": "a signed letter admitting the debt",
}


def _read(said=None, provisions=None, expiry=date(2026, 3, 14), chron=CHRON):
    return factors.read(said if said is not None else SAID, chron, ACCOUNT,
                        provisions if provisions is not None else {"18": S18},
                        expiry)


# ======================= the defect itself, closed ========================

def test_an_acknowledgment_on_the_file_reaches_the_arithmetic():
    """THE WHOLE OF B-073, as a worked example of the rule beneath it.

    A `Factor` is produced, it names the entry it rests on, and it restarts
    from that entry's date — so `compute` has something to apply. Before this,
    `factors=()` on every computation the product ever made.
    """
    read = _read()
    assert read.state == "found"
    (factor,) = read.factors
    assert factor.kind is FactorKind.ACKNOWLEDGMENT
    assert factor.fact == "f2"
    assert factor.restarts_from == date(2024, 6, 12)


def test_the_finding_is_the_retrieved_span_and_not_a_summary_of_it():
    """`Factor.finding` is required BY THE TYPE so an extending provision
    asserted from memory cannot be constructed. Filling it with the product's
    own description of s.18 would satisfy the type and defeat it."""
    (factor,) = _read().factors
    assert factor.finding == S18


# ================= the third state, which was the defect ==================

def test_an_unretrieved_section_is_not_assessed_and_never_none_found():
    """THE S1 SHAPE, at the point it would do most damage.

    "Nothing on this file restarts the period" and "nobody looked" are
    different sentences, and only one of them is a reason not to file.
    """
    read = _read(provisions={})
    assert read.state == "not_assessed"
    assert read.factors == ()
    assert "not retrieved" in read.why_not


def test_nothing_having_read_the_account_is_a_different_state_from_finding_none():
    none_found = _read(said={"kind": "none", "fact_id": "", "quoted": "",
                             "in_writing": False, "why": "nothing admits it"})
    assert none_found.state == "none_found"
    assert factors.UNREAD.state == "not_assessed"
    assert none_found.state != factors.UNREAD.state


def test_an_undated_entry_cannot_carry_a_factor():
    """Nothing can run FROM an undated event. Refused, and named as refused —
    not returned as an account that describes no acknowledgment."""
    undated = (_fact("f2", "he admitted it in writing at some point", None),)
    read = factors.read(SAID, undated, ACCOUNT, {"18": S18}, date(2026, 3, 14))
    assert read.state == "refused"
    assert "carries no date" in read.refused


def test_a_chronology_with_no_dated_entry_at_all_is_not_assessed():
    """The turn refuses earlier, before the model is called: there is nothing
    an acknowledgment could attach to, so nothing is asked."""
    assert factors.not_assessed("no dated entry").state == "not_assessed"


# ===================== what the law requires, computed ====================

def test_a_spoken_admission_does_not_restart_the_period():
    """s.18 requires a signed WRITING, in terms. An admission on the telephone
    is not an acknowledgment however clear it was — and this is decided here,
    not by whatever the model believed about it."""
    read = _read(said={**SAID, "in_writing": False})
    assert read.state == "none_found"
    assert read.factors == ()
    assert "not in writing" in read.why_not


def test_an_acknowledgment_after_the_bar_revives_nothing():
    """BOTH SECTIONS SAY "before the expiration of the prescribed period".

    This is ARITHMETIC against the un-extended expiry, so it is settled
    mechanically. A model asserting that a letter written after the bar
    restarts the clock cannot make it so — which is exactly the kind of
    assertion B-077 caught the recommendation making, in both directions.
    """
    read = _read(expiry=date(2024, 1, 1))
    assert read.factors == ()
    assert "after the period expired" in read.why_not
    assert "2024-01-01" in read.why_not, (
        "the refusal must name the date it was tested against, or the "
        "advocate cannot check it")


def test_a_part_payment_needs_section_19_and_not_section_18():
    """Each kind is tied to ITS OWN section. Accepting s.18's text as the
    finding for a part payment would put a citation on a conclusion it does
    not support — which reads, to an advocate, exactly like one that does."""
    payment = {**SAID, "kind": "part_payment",
               "quoted": "admitting the amount was outstanding"}
    assert factors.read(payment, CHRON, ACCOUNT, {"18": S18},
                        date(2026, 3, 14)).state == "not_assessed"
    assert factors.read(payment, CHRON, ACCOUNT, {"19": S19},
                        date(2026, 3, 14)).state == "found"


# ========================= what the model may not do ======================

def test_a_factor_cannot_attach_to_a_fact_the_file_does_not_hold():
    read = _read(said={**SAID, "fact_id": "f_invented"})
    assert read.refused and "not on this chronology" in read.refused


def test_a_paraphrase_presented_as_a_quotation_is_refused():
    """The same guard the cause read uses. A finding that carries a quotation
    the advocate never wrote has evidence it does not have."""
    read = _read(said={**SAID, "quoted": "he admitted the whole debt to us"})
    assert read.refused and "not in the advocate's account" in read.refused


def test_a_kind_outside_the_schema_is_refused_rather_than_coerced():
    read = _read(said={**SAID, "kind": "estoppel"})
    assert read.refused and "outside the schema" in read.refused


def test_a_kind_this_producer_does_not_read_is_refused():
    """Exclusion, disability, fraud, notice periods and continuing breach are
    each their own section and their own question. A producer that guessed at
    all seven would be one nobody could check — so they stay NOT_ASSESSED and
    are SAID to be, rather than read as absent."""
    read = _read(said={**SAID, "kind": "disability"})
    assert read.refused is not None


def test_a_refusal_is_not_the_same_state_as_finding_none():
    """A model output this product DECLINED and an account that genuinely
    describes no acknowledgment must not render alike: only the first is worth
    telling the advocate about, and only the second is a finding."""
    refused = _read(said={**SAID, "fact_id": "nope"})
    none_found = _read(said={"kind": "none", "fact_id": "", "quoted": "",
                             "in_writing": False, "why": "nothing admits it"})
    assert refused.refused is not None
    assert none_found.refused is None
    # AND THE STATES DIFFER. Asserting only on `.refused` was what let the
    # collapse survive: `state` returned `none_found` for both, so anything
    # rendering from `state` would have shown a declined read as a finding.
    assert refused.state == "refused"
    assert none_found.state == "none_found"


# ============================== the schema ================================

def test_the_schema_offers_a_way_to_say_nothing_applies():
    """A schema whose every value is a finding forces one, and the product
    then restarts a limitation period on a letter that admits nothing. Same
    reason `cannot_tell` is a required member of the cause schema."""
    assert "none" in factors.FACTOR_SCHEMA["properties"]["kind"]["enum"]


def test_every_kind_the_schema_offers_names_the_section_it_needs():
    """A kind the producer can return with no section mapped would fall
    through to `provisions.get(None)` and build a factor on nothing."""
    for value in factors.FACTOR_SCHEMA["properties"]["kind"]["enum"]:
        if value == "none":
            continue
        assert FactorKind(value) in factors.SECTION_FOR


def test_the_prompt_carries_the_chronology_ids_the_answer_must_name():
    """The model has to name WHICH entry. A free-text date would have to be
    matched back by parsing, which is a second place for the date to be wrong
    — and the date is what the period restarts from."""
    prompt = factors.build_prompt("is it in time?", ACCOUNT, CHRON)
    assert "f2" in prompt.user
    assert "2024-06-12" in prompt.user
