"""C7 — the evidence inventory, REACHED. E-070 on a served turn.

C7's counterexample is a sentence an advocate writes in a brief:

    *a file where the original agreement is with the opponent's brother and no
    preservation or production step exists.*

The item is inventoried, its holder is recorded, and nothing was ever asked of
anyone — so the file reads as WORKED and the document is gone by the time it
is needed. Every test here is about that sentence reaching an advocate as
something they must answer.

WHY THIS DID NOT NEED DOCUMENT INTAKE FIRST
---------------------------------------------
C7 reads as though it depends on C6 — documents in, items out — and it does
not. The counterexample above contains an inventory entry, a holder and a
missing instruction, all before anything is uploaded. Waiting for intake would
have left the one control that catches a document walking out of the file
unwired for another slice.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.evidence_item import (
    Admissibility,
    EvidenceItem,
    Existence,
    Form,
    Holder,
    Preservation,
    read_inventory,
    unasked,
    undelivered,
    unpreserved,
)
from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from nm.domain.quotable import Quotable
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

AT_RISK = ("We act for the plaintiff at Hyderabad. The original agreement is "
           "with the opponent brother and we hold only a photocopy.")


def _run(tmp_path, message=AT_RISK):
    engine, _ = build(tmp_path)
    return engine.run(TurnInput(advocate_id="adv_1", message=message,
                                today=date(2026, 9, 4)))


def _of(out, kind):
    return [e.text for e in out.answer.elements if e.kind is kind]


# ====================== the counterexample, on the wire ====================

@pytest.mark.eval_id("E-070")
def test_an_item_at_risk_with_no_preservation_step_becomes_a_question(tmp_path):
    """A QUESTION AND NOT A NOTE, deliberately.

    A question BLOCKS an action; a note does not. An advocate reading "no
    preservation step is recorded" at the foot of an answer has been told; one
    who cannot proceed until they say who is writing to whom has been stopped.
    """
    # THE QUESTION NOW COMES OUT OF THE GAP QUEUE (A3), batched with whatever
    # else is open on this thread — so this asserts the PROPERTY rather than
    # the sentence: the item is named, and a date is asked for.
    questions = " ".join(_of(_run(tmp_path), ElementKind.QUESTION)).lower()
    assert "preserv" in questions, (
        "an item held by someone with an interest in it not surviving reached "
        "the advocate with no preservation question:\n" + questions[:500])
    assert "original agreement" in questions, (
        "the question does not name the item it is about")
    assert "by when" in questions, (
        "a preservation instruction with no date is a wish; the question must "
        "ask for one")


@pytest.mark.eval_id("E-070")
def test_the_inventory_reaches_the_advocate_at_all(tmp_path):
    """The wiring, asserted separately. Everything above is meaningless if
    nothing was inventoried — and `nm/core/evidence_item.py` had a complete
    unit suite and no production caller for two slices (B-079)."""
    assert _of(_run(tmp_path), ElementKind.FINDING), "nothing was inventoried"


# =================== the three sweeps, as rules not cases ==================

def test_an_item_the_client_holds_raises_no_preservation_question():
    """`at_risk` is a fact about CUSTODY, not a judgement about anyone. The
    sweep must not fire on everything, or the advocate learns to skip it."""
    ours = EvidenceItem(what="our file copy", holder=Holder.CLIENT,
                        form=Form.PHOTOCOPY)
    assert unpreserved((ours,)) == ()


def test_a_written_but_unissued_instruction_is_its_own_failure():
    """THE THIRD STATE, and the one that reads best on a file review: the
    instruction exists, it has an owner and a date, and it is sitting in a
    draft. `unpreserved` reports nothing about it — so without `undelivered`
    the two failures are indistinguishable to everyone except the document,
    which is gone either way."""
    drafted = EvidenceItem(
        what="the original agreement", holder=Holder.OPPONENT,
        form=Form.ORIGINAL,
        # AN OWNER AND A DATE, both required by the type: C7 says an
        # instruction with neither is a wish, and `issued_at` of `None` is
        # what makes "written" and "sent" two different states.
        preservation=Preservation(owner="the instructing advocate",
                                  due=date(2026, 9, 30), issued_at=None))
    assert unpreserved((drafted,)) == (), (
        "an item WITH an instruction was reported as having none")
    assert undelivered((drafted,)) == ("the original agreement",)


def test_listing_an_item_answers_none_of_the_three_questions():
    """Existence, admissibility and weight are three questions and an
    inventory that lists ten items and answered two of the thirty reads as an
    inventory that was done."""
    listed = EvidenceItem(what="the WhatsApp exchange", holder=Holder.CLIENT,
                          form=Form.ELECTRONIC)
    (line,) = unasked((listed,))
    for question in ("existence", "admissibility", "weight"):
        assert question in line


def test_a_read_leaves_admissibility_and_weight_unasked():
    """THE READER DOES NOT FILL THEM, and that is the design.

    Answering all three from one read is the collapse this module keeps three
    enums apart to prevent — and it would silently empty `unasked`, so the
    sweep would pass having swept nothing.
    """
    account = "the original agreement is with the opponent brother"
    read = read_inventory({"items": [{
        "what": "the original agreement", "holder": "opponent",
        "form": "original",
        "quoted": "the original agreement is with the opponent brother"}]},
        Quotable(file=account))
    (item,) = read.items
    assert item.admissibility is Admissibility.NOT_ASSESSED
    assert item.existence is Existence.NOT_ASSESSED
    assert unasked(read.items), "the sweep found nothing to ask about"


def test_an_ungrounded_item_is_refused_and_the_rest_survive():
    """Per item, not per read. Losing four sound items because a fifth was
    unquotable is a filter with a good excuse."""
    account = "we hold the invoices and a photocopy of the agreement"
    read = read_inventory({"items": [
        {"what": "the invoices", "holder": "client", "form": "original",
         "quoted": "we hold the invoices"},
        {"what": "a fabrication", "holder": "client", "form": "original",
         "quoted": "words never written"},
    ]}, Quotable(file=account))
    assert len(read.items) == 1
    assert len(read.refused) == 1


def test_an_out_of_vocabulary_holder_becomes_unknown_not_an_invented_member():
    """A `Holder` nobody defined is a holder nothing can act on."""
    read = read_inventory({"items": [{
        "what": "a document", "holder": "the bank manager", "form": "invented",
        "quoted": ""}]}, Quotable(file="an account"))
    (item,) = read.items
    assert item.holder is Holder.UNKNOWN
    assert item.form is Form.NOT_ASSESSED


def test_nothing_mentioned_is_a_different_state_from_nothing_read():
    from nm.core.evidence_item import UNREAD_INVENTORY

    assert read_inventory({"items": []}, Quotable(file="an account")).state == "none_mentioned"
    assert UNREAD_INVENTORY.state == "not_assessed"
