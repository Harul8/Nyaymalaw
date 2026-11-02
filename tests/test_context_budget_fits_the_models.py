"""The step budget fits the configured models' verified windows (owner decision, 15 Oct 2026).

A step may build to 1,000,000 tokens. From D27 (plan AN.33, 2 Nov 2026; piece 33p) its answer
is not reserved beside the budget but written within it - a call may write what its input
leaves of the budget, up to the most its model writes - so the budget, input and answer
together, must fit every published model the tiers may select, or a prompt the port accepts
would be refused by the provider instead of by the typed guard.
"""
import pytest

from nm.core_engine import calculation, page_reading, reasoning, research, response_review, response_writer, understanding
from nm.shared.model_config import BILLING_CONTEXT, CONTEXT_BUDGET, PUBLISHED_RELEASES
from nm.shared.model_port import ContextOverflow, Tier, estimate_tokens


def test_each_text_step_may_build_to_one_million_tokens():
    assert {tier: CONTEXT_BUDGET[tier] for tier in (Tier.ROUTINE, Tier.HARD, Tier.JUDGE)} == {
        Tier.ROUTINE: 1_000_000, Tier.HARD: 1_000_000, Tier.JUDGE: 1_000_000}


def test_the_budget_with_its_answer_fits_every_published_model():
    for model in PUBLISHED_RELEASES:
        for tier in (Tier.ROUTINE, Tier.HARD, Tier.JUDGE):
            assert CONTEXT_BUDGET[tier] <= BILLING_CONTEXT[model], (model, tier)


def test_every_step_may_write_the_most_its_model_writes_within_what_its_input_leaves():
    assert {response_writer.MAX_OUTPUT, response_writer.OVERVIEW_OUTPUT, response_writer.REPAIR_OUTPUT,
            response_writer.TAKE_UP_OUTPUT, response_review.MAX_OUTPUT, response_review.CROSS_OUTPUT, understanding.MAX_OUTPUT,
            calculation.MAX_OUTPUT, page_reading.MAX_OUTPUT, page_reading.RELOOK_OUTPUT,
            *research.MAX_OUTPUT.values()} == {reasoning.MOST_OUTPUT}

    class Given:
        def context_budget(self, tier):
            return CONTEXT_BUDGET[tier]
    words = "word " * 380_000
    assert reasoning.room(Given(), Tier.ROUTINE, "short") == reasoning.MOST_OUTPUT
    assert reasoning.room(Given(), Tier.ROUTINE, words, words) == CONTEXT_BUDGET[Tier.ROUTINE] - estimate_tokens(words * 2) < reasoning.MOST_OUTPUT
    with pytest.raises(ContextOverflow):
        reasoning.room(Given(), Tier.ROUTINE, words, words, "word " * 200_000)
