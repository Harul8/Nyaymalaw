"""The offline dispute model must exercise the whole source-labelled brief."""

import json

import pytest

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.understand import dispute
from nm.shared.model_scripted import scripted_dispute


pytestmark = pytest.mark.class_a


def test_paragraphs_and_sentence_ends_survive_both_dispute_reading_orders():
    brief = ("I act for A. SOURCE UNITS appears in my note.\n\n"
             "First, B locked the gate. B kept it locked.\n\n"
             "Second, C withheld payment. C repeated the refusal.")
    quotable = Quotable(turn=brief, context="Third, another dispute was not reported.")

    for reverse in (False, True):
        prompt = dispute.build_prompt(quotable, reverse=reverse)
        result = dispute.interpret(quotable, json.loads(scripted_dispute(prompt.user)))

        assert not result.refused and len(result.described) == 2
        assert all("I act for A." in row.spans
                   and "SOURCE UNITS appears in my note." in row.spans
                   for row in result.described)
        assert "B kept it locked." in result.described[0].spans
        assert "C repeated the refusal." in result.described[1].spans
        assert all("another dispute was not reported" not in span
                   for row in result.described for span in row.spans)
