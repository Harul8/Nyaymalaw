"""A CONTRADICTION NOBODY CAN POINT AT IS NOT ONE -- including an empty pointer.

`consistency.interpret` requires the quoted words of a contradiction to be IN
THE STEP. An EMPTY quotation passed that check, because the empty string is a
substring of every step. Measured 23 September 2026: two live verdicts named
`limitation`, quoted nothing, and withheld the advocate's next step -- one of
them with the reason "the step does not assert anything about a limitation
period".

The direction is the module's own: both guards fail toward CONSISTENT, because
refusing here deletes the advice.
"""
from __future__ import annotations

import pytest

from nm.core import consistency

pytestmark = pytest.mark.class_a

STEP = "Review the tenant's written statement for the grounds he relies on."
OFFERED = frozenset({"limitation", "register", "side"})


@pytest.mark.parametrize("quoted", ["", "   ", "--", "“”"])
def test_an_empty_quotation_withholds_nothing(quoted):
    verdict = consistency.interpret(
        {"claim_id": "limitation", "quoted": quoted,
         "why": "The step does not assert anything about a limitation period."},
        STEP, OFFERED)
    assert not verdict.contradicted, (
        "a verdict that pointed at nothing in the step withheld it")
    assert verdict.refused, "the refused pointer is not recorded as refused"


def test_a_real_pointer_into_the_step_still_withholds():
    """The other half: the guard must not open the gate it protects."""
    step = "File the suit before 14 March 2027, when your limitation period expires."
    verdict = consistency.interpret(
        {"claim_id": "limitation", "quoted": "when your limitation period expires",
         "why": "asserts an expiry date"}, step, OFFERED)
    assert verdict.contradicted
