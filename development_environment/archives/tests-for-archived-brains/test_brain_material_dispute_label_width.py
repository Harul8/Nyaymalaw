"""Owned dispute labels preserve meaningful scope regardless of display width."""

from copy import deepcopy

import pytest

from nm.brain.material import parse_material
from nm.shared.model_port import SchemaViolation

WORDS = "The supplier withheld delivery after receiving payment, and the agreed date is disputed."
LABEL = (
    "Supplier's reported withholding of the delivery after receiving payment, including the "
    "disputed agreed delivery date and the advocate's unresolved account of that sequence"
)
assert len(LABEL) > 140


def proposal():
    return {
        "kind": "dispute",
        "label": LABEL,
        "statement": WORDS,
        "quoted": WORDS,
        "relation": "new",
        "prior_references": [],
        "matter_scope": "proposed",
        "basis": "stated",
        "importance": "central",
        "why_material": "The reported withholding and disputed delivery date need examination.",
        "identification": "identified",
        "clarification": "",
        "related_dispute_ids": [],
    }


def test_long_owned_dispute_label_is_preserved_with_exact_attribution_without_trimming():
    row = proposal()
    before = deepcopy(row)
    (result,) = parse_material([row], latest=WORDS, earlier=(), current_matter_id=None)
    assert result.label == LABEL
    assert result.quoted == WORDS
    assert result.statement == WORDS
    assert row == before


@pytest.mark.parametrize("label", ["", "   "])
def test_blank_dispute_label_remains_invalid(label):
    row = proposal()
    row["label"] = label
    with pytest.raises(SchemaViolation, match="nonempty label"):
        parse_material([row], latest=WORDS, earlier=(), current_matter_id=None)


def test_long_label_cannot_substitute_foreign_source_words():
    row = proposal()
    row["quoted"] = "A different party demands an unrelated payment."
    with pytest.raises(SchemaViolation, match="selected latest source is absent"):
        parse_material([row], latest=WORDS, earlier=(), current_matter_id=None)


def test_long_new_dispute_label_cannot_authorise_an_unowned_target_link():
    row = proposal()
    row["related_dispute_ids"] = ["foreign-record"]
    with pytest.raises(SchemaViolation, match="new dispute must have empty"):
        parse_material([row], latest=WORDS, earlier=(), current_matter_id=None)
