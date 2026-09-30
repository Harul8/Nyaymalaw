"""Literal coverage cannot certify that independently contested rights were split.

A reading can account for every sentence and still put two claims with different
harm, evidence and relief in one working dispute. The separation is the model's,
told by the prompt that a harm during an encounter about another right is its own
dispute (LB-109); the code carries each dispute's own sentences and never moves a
sentence of one into another.
"""
from __future__ import annotations

import pytest

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.understand import dispute
from tests.test_every_dispute_is_cleanly_identified import listed

pytestmark = pytest.mark.class_a

MESSAGE = ("We act for the claimant. First, the neighbour blocked her entrance. "
           "During that encounter he struck her and injured her arm. "
           "Second, a different seller refused to complete a sale. "
           "Please assess every separate claim.")
UNITS = dispute.source_units(MESSAGE)


def _read(disputes):
    return dispute.interpret(Quotable(turn=MESSAGE), listed(
        MESSAGE, disputes, background=["We act"], instructions=["Please assess"]))


def test_a_harm_during_an_encounter_about_another_right_stays_its_own_dispute():
    read = _read([("", "her entrance", "use_or_access", ["First,"]),
                  ("", "the blow during the encounter", "bodily_harm", ["During that"]),
                  ("", "the sale", "agreement", ["Second,"])])
    assert [d.label for d in read.described] == [
        "her entrance", "the blow during the encounter", "the sale"]
    spans = [set(d.spans) for d in read.described]
    assert UNITS["S2"] in spans[0] and UNITS["S3"] not in spans[0]
    assert UNITS["S3"] in spans[1] and UNITS["S2"] not in spans[1]


def test_the_prompt_tells_the_model_to_keep_them_apart():
    assert "even if one happened during the other" in dispute.SYSTEM
    assert "Each wrongful incident" in dispute.SYSTEM
