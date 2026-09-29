"""Literal coverage cannot certify that independently contested rights were split.

A reading can account for every sentence and still put two claims with different
harm, evidence and relief in one working dispute. Since 29 September 2026
(LB-109) the reading does not group at all: it labels each sentence with the other
side, the thing contested (by number) and the kind of wrong, and the code forms one
dispute per other side, thing and kind. A harm during an encounter about another
right is a different kind of wrong, so it is its own dispute; the same encounter
told in two sentences is one thing, so it cannot be split.

The independent second reading that stood here for a day re-asked the same model
and kept its answer only when it found MORE disputes. What replaced it reads the
message twice as a check, and says where the two readings differ.
"""
from __future__ import annotations

import pytest

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.understand import dispute
from tests.test_every_dispute_is_cleanly_identified import labelled

pytestmark = pytest.mark.class_a

MESSAGE = ("We act for the claimant. First, the neighbour blocked her entrance. "
           "During that encounter he struck her and injured her arm. "
           "Second, a different seller refused to complete a sale. "
           "Please assess every separate claim.")
UNITS = dispute.source_units(MESSAGE)


def _read(disputes):
    return dispute.interpret(Quotable(turn=MESSAGE), labelled(
        MESSAGE, disputes, background=["We act"], instructions=["Please assess"]))


def test_a_harm_during_an_encounter_about_another_right_is_its_own_dispute():
    read = _read([("", "her entrance", "use_or_access", ["First,"]),
                  ("", "the blow during the encounter", "bodily_harm", ["During that"]),
                  ("", "the sale", "agreement", ["Second,"])])
    assert [d.label for d in read.described] == [
        "her entrance", "the blow during the encounter", "the sale"]
    spans = [set(d.spans) for d in read.described]
    assert UNITS["S2"] in spans[0] and UNITS["S3"] not in spans[0]
    assert UNITS["S3"] in spans[1] and UNITS["S2"] not in spans[1]


def test_the_same_encounter_told_in_two_sentences_is_one_dispute():
    """THE POSITIVE CONTROL: the rule joins what shares a thing and a kind, or it
    proves only that it never joins."""
    read = _read([("", "her entrance", "use_or_access", ["First,", "During that"]),
                  ("", "the sale", "agreement", ["Second,"])])
    assert len(read.described) == 2
    assert UNITS["S3"] in read.described[0].spans
