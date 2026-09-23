"""THE EVALUATION LEDGER ADMITS ONE MODEL, AND THE DEFAULT IS THE PIN.

Widened on 23 September 2026 so the owner could authorise ONE measurement of
G-CONSISTENT on gpt-5.1 (PRD 7.4.1), which the pin had correctly refused. The
widening must not reach any server path: nothing that names no model may spend
on anything but GPT-4o mini, and a named model is admitted only with its price
and a reservation bounding its worst case.
"""
from __future__ import annotations

import pytest

from nm.adapters.model.call_budget import MODEL, CallBudget
from nm.ports.model import ConfigurationError

pytestmark = pytest.mark.class_a


def test_the_default_is_the_pin(tmp_path):
    budget = CallBudget(tmp_path / "l.sqlite", "1")
    assert budget.model == MODEL == "gpt-4o-mini-2024-07-18"
    with pytest.raises(ConfigurationError):
        budget.reserve("gpt-5.1")


def test_a_named_model_is_admitted_and_nothing_else(tmp_path):
    budget = CallBudget(tmp_path / "l.sqlite", "1", model="gpt-5.1",
                        price_per_million=("1.25", "10"), reservation_micro_usd=110_000)
    assert budget.reserve("gpt-5.1")
    with pytest.raises(ConfigurationError):
        budget.reserve(MODEL)


def test_a_reservation_that_bounds_nothing_is_refused(tmp_path):
    with pytest.raises(ConfigurationError):
        CallBudget(tmp_path / "l.sqlite", "1", model="gpt-5.1",
                   price_per_million=("1.25", "10"), reservation_micro_usd=0)
