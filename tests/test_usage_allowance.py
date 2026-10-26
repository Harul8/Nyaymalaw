"""The usage allowance's rules, as code owns them (owner decisions O21-O24; plans P53, AN.17): the
percentage left, the notices the advocate is shown, the trial, and the refusal once nothing is left.
Offline; the store, the meter and the page have their own tests."""
from __future__ import annotations

import pytest

from nm.arrive.usage_port import (NOTICE_STEPS, SELF_CLOSING_SECONDS, SELF_CLOSING_STEPS, TRIAL_MICRO_USD,
                                  AllowanceUsedUp, due_notice, percent_left)
from nm.shared.model_port import USAGE_LIMIT_MESSAGE, UsageLimitReached

pytestmark = pytest.mark.class_a


def test_the_trial_is_thirty_cents():
    assert TRIAL_MICRO_USD == 300_000  # owner, O24: "Load 30 cents once per account"


@pytest.mark.parametrize(("spent", "left"), [
    (0, 100), (1, 100), (2_999, 100), (3_000, 99), (150_000, 50), (150_001, 50), (152_999, 50),
    (225_000, 25), (270_000, 10), (296_999, 2), (297_000, 1), (299_999, 1), (300_000, 0), (412_000, 0),
])
def test_the_percentage_left_is_rounded_up_so_none_left_is_the_only_zero(spent, left):
    assert percent_left(TRIAL_MICRO_USD, spent) == left


def test_an_allowance_of_nothing_has_nothing_left_and_counts_are_whole():
    assert percent_left(0, 0) == 0
    with pytest.raises(ValueError):
        percent_left(300_000, -1)
    with pytest.raises(ValueError):
        percent_left(300_000, 1.5)


def _walk(lefts):
    """The notices shown as the allowance falls through these percentages, one answer at a time."""
    noticed, shown = None, []
    for left in lefts:
        step = due_notice(left, noticed)
        if step is not None:
            shown.append(step)
            noticed = step
    return shown


def test_fifty_once_twenty_five_once_then_every_one_percent_from_ten():
    # O22: "50% once, 25% once ... then from 10% onwards show for every 1% reduction".
    assert _walk(range(100, -1, -1)) == list(NOTICE_STEPS)
    assert _walk([100, 80, 60, 51]) == []
    assert _walk([60, 50, 49, 40, 30, 26]) == [50]


def test_a_fall_past_several_steps_shows_only_the_step_reached():
    assert _walk([60, 5]) == [5]
    assert _walk([60, 20, 4]) == [25, 4]
    assert _walk([12, 11, 10, 10, 9]) == [25, 10, 9]


def test_nothing_left_shows_the_limit_state_not_a_notice():
    assert due_notice(0, None) is None and due_notice(0, 1) is None


def test_only_the_fifty_and_twenty_five_percent_notices_close_by_themselves_after_ten_minutes():
    assert SELF_CLOSING_STEPS == {50, 25} and SELF_CLOSING_SECONDS == 600  # O22, O23


def test_a_used_up_allowance_is_refused_as_the_usage_limit_in_the_owners_words():
    # Raised before any call; every place that names the provider's usage limit (P51) names it too.
    refusal = AllowanceUsedUp(USAGE_LIMIT_MESSAGE)
    assert isinstance(refusal, UsageLimitReached)
    assert refusal.usage is None and refusal.retries == 0
