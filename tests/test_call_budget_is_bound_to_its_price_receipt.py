"""A shared approval budget is not interchangeable pricing authority."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from nm.shared.model_call_budget import MODEL, CallBudget
from nm.shared.model_port import ConfigurationError, ProviderUnavailable

pytestmark = pytest.mark.class_a


def _response(model=MODEL, incoming=100, outgoing=20):
    return SimpleNamespace(
        model=model,
        id="receipt",
        usage=SimpleNamespace(prompt_tokens=incoming, completion_tokens=outgoing),
    )


def _row(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT charge,state,model FROM attempts ORDER BY at").fetchall()


@pytest.mark.parametrize(
    "terms",
    [
        {"model": "other-approved-snapshot"},
        {"price_per_million": ("3", "12")},
        {"reservation_micro_usd": 40000},
    ],
)
def test_a_second_model_or_price_cannot_settle_someone_elses_reservation(tmp_path, terms):
    path = tmp_path / "budget.db"
    original = CallBudget(path, "5")
    token = original.reserve(MODEL)
    different = CallBudget(path, "5", **terms)
    with pytest.raises(ConfigurationError, match="captured model/prices"):
        different.settle(token, _response())
    assert _row(path) == [(30000, "reserved_or_unknown", MODEL)]
    original.settle(token, _response())
    assert _row(path) == [(27, "measured", MODEL)]


def test_distinct_models_can_share_one_cap_but_only_settle_their_own_calls(tmp_path):
    path = tmp_path / "budget.db"
    cheap = CallBudget(path, "5")
    costly = CallBudget(
        path,
        "5",
        model="second-approved-snapshot",
        price_per_million=("3", "12"),
        reservation_micro_usd=500000,
    )
    first, second = cheap.reserve(MODEL), costly.reserve(costly.model)
    cheap.settle(first, _response())
    costly.settle(second, _response(costly.model))
    assert _row(path) == [(27, "measured", MODEL), (540, "measured", costly.model)]


def test_a_wrong_snapshot_in_the_provider_receipt_leaves_the_reservation_held(tmp_path):
    path = tmp_path / "budget.db"
    budget = CallBudget(path, "5")
    token = budget.reserve(MODEL)
    with pytest.raises(ConfigurationError, match="model identity"):
        budget.settle(token, _response("different-snapshot"))
    assert _row(path) == [(30000, "reserved_or_unknown", MODEL)]


@pytest.mark.parametrize(
    "prices", [("NaN", "1"), ("1", "Infinity"), ("-1", "1"), ("1", "-2"), ("oops", "1")]
)
def test_nonfinite_negative_or_malformed_prices_fail_before_any_reservation(tmp_path, prices):
    path = tmp_path / "budget.db"
    with pytest.raises(ConfigurationError):
        CallBudget(path, "5", price_per_million=prices)
    assert not path.exists()


@pytest.mark.parametrize("reservation", [True, 1.5, "30000", 0, -1])
def test_fractional_or_unestablished_per_call_bounds_cannot_be_truncated(tmp_path, reservation):
    with pytest.raises(ConfigurationError):
        CallBudget(tmp_path / "budget.db", "5", reservation_micro_usd=reservation)


def test_known_over_bound_usage_is_recorded_not_rolled_back_to_a_smaller_estimate(tmp_path):
    path = tmp_path / "budget.db"
    budget = CallBudget(path, "5", reservation_micro_usd=10)
    token = budget.reserve(MODEL)
    with pytest.raises(ProviderUnavailable, match="exceeded") as observed:
        budget.settle(token, _response())
    assert observed.value.usage.cost_usd == 27 / 1_000_000
    assert _row(path) == [(27, "measured_over_bound", MODEL)]
    with pytest.raises(ProviderUnavailable, match="needs review"):
        CallBudget(path, "5").reserve(MODEL)


def test_legacy_unknown_attempt_is_preserved_but_cannot_be_repriced_after_restart(tmp_path):
    path = tmp_path / "budget.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE attempts (id TEXT PRIMARY KEY, at TEXT NOT NULL, "
            "charge INTEGER NOT NULL, state TEXT NOT NULL, model TEXT NOT NULL, "
            "response_id TEXT,tokens_in INTEGER,tokens_out INTEGER)"
        )
        db.execute(
            "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)",
            ("legacy", "then", 30000, "reserved_or_unknown", MODEL, None, None, None),
        )
    budget = CallBudget(path, "5")
    with pytest.raises(ConfigurationError, match="captured model/prices"):
        budget.settle("legacy", _response())
    assert _row(path) == [(30000, "reserved_or_unknown", MODEL)]


def test_unknown_usage_does_not_allow_an_absent_or_already_settled_receipt(tmp_path):
    budget = CallBudget(tmp_path / "budget.db", "5")
    with pytest.raises(ProviderUnavailable, match="absent"):
        budget.settle("missing", SimpleNamespace(usage=None))
    token = budget.reserve(MODEL)
    budget.settle(token, _response())
    with pytest.raises(ProviderUnavailable, match="already settled"):
        budget.settle(token, SimpleNamespace(usage=None))
