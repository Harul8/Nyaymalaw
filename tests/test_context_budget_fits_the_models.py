"""The step budget fits the configured models' verified windows (owner decision, 15 Oct 2026).

A step may build to 1,000,000 tokens; with its largest answer reserved it must still
fit every published model the tiers may select, or a prompt the port accepts would be
refused by the provider instead of by the typed guard.
"""
from nm.core_engine import research, response_review, response_writer, understanding
from nm.shared.model_config import BILLING_CONTEXT, CONTEXT_BUDGET, PUBLISHED_RELEASES
from nm.shared.model_port import Tier


def test_each_text_step_may_build_to_one_million_tokens():
    assert {tier: CONTEXT_BUDGET[tier] for tier in (Tier.ROUTINE, Tier.HARD, Tier.JUDGE)} == {
        Tier.ROUTINE: 1_000_000, Tier.HARD: 1_000_000, Tier.JUDGE: 1_000_000}


def test_the_budget_and_the_largest_answer_fit_every_published_model():
    largest = max(response_writer.MAX_OUTPUT, response_review.MAX_OUTPUT,
                  understanding.MAX_OUTPUT, *research.MAX_OUTPUT.values())
    for model in PUBLISHED_RELEASES:
        for tier in (Tier.ROUTINE, Tier.HARD, Tier.JUDGE):
            assert CONTEXT_BUDGET[tier] + largest <= BILLING_CONTEXT[model], (model, tier)
