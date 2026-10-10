"""Synthetic accounting cases only; no provider, browser or existing ledger use."""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from nm.shared import model_config as config
from nm.shared.model_call_budget import CallBudget, SessionCallBudget
from nm.shared.model_port import ConfigurationError, ProviderUnavailable

MODEL = "synthetic-bounded-priced-model"
pytestmark = pytest.mark.class_a


@pytest.fixture
def pricing(monkeypatch):
    terms = config.TokenPricing(input_rate=D("1"), output_rate=D("4"),
        cached_rate=D("0.1"), write_rate=D("1.25"), long_context_threshold=100000,
        input_multiplier=D("2"), output_multiplier=D("1.5"))
    original = config.token_pricing
    monkeypatch.setattr(config, "token_pricing", lambda model: terms if model == MODEL else original(model))
    monkeypatch.setitem(config.BILLING_CONTEXT, MODEL, 1000000)
    monkeypatch.setitem(config.MAX_OUTPUT, MODEL, 8192)
    return terms


def receipt(incoming=500, outgoing=40, *, cached=100, written=50):
    return NS(model=MODEL, id="synthetic-usage",
        usage=NS(prompt_tokens=incoming, completion_tokens=outgoing,
                 prompt_tokens_details=NS(cached_tokens=cached, cache_write_tokens=written)))


def row(path):
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM attempts ORDER BY at DESC LIMIT 1").fetchone())


def request(tmp_path, pricing, *, incoming=600, output=100):
    session = SessionCallBudget(tmp_path / "test-only.sqlite", "5", models=(MODEL,))
    budget, limit = session.for_request(MODEL, output, input_upper_bound=incoming)
    assert limit == output
    return session, budget


def test_exact_count_narrows_reserve_and_captures_immutable_terms(tmp_path, pricing):
    session, budget = request(tmp_path, pricing)
    assert budget.reservation == 1150  # all 600 input tokens may incur write price
    token = budget.reserve(MODEL)
    saved = row(session.path)
    assert saved["input_token_bound"] == 600 and saved["output_token_bound"] == 100
    assert json.loads(saved["pricing_policy"]) == pricing.as_dict()
    budget.settle(token, receipt())
    saved = row(session.path)
    assert saved["charge"] == 583  # ceil(350 ordinary + 10 cached + 62.5 written + 160 output)
    assert saved["state"] == "measured"
    assert (saved["cached_tokens"], saved["cache_write_tokens"]) == (100, 50)
    assert saved["bound_violation"] is None


def test_omitted_input_count_keeps_full_context_and_long_price(tmp_path, pricing):
    session = SessionCallBudget(tmp_path / "test-only.sqlite", "5", models=(MODEL,))
    budget, _ = session.for_request(MODEL, 100)
    assert budget.input_token_bound == 1000000
    assert budget.reservation == 2500600
    assert session.status()["attempts"] == 0


@pytest.mark.parametrize("count,expected", [(100000,125400), (100001,250603)])
def test_reservation_changes_at_actual_long_context_threshold(tmp_path, pricing, count, expected):
    _, budget = request(tmp_path, pricing, incoming=count)
    assert budget.reservation == expected


def test_long_context_actual_buckets_settle_at_captured_tariff(tmp_path, pricing):
    session, budget = request(tmp_path, pricing, incoming=100001)
    token = budget.reserve(MODEL)
    budget.settle(token, receipt(100001, 100, cached=1, written=1))
    assert row(session.path)["charge"] == 200601


@pytest.mark.parametrize("count", [True, -1, 1000001, 1.5, "600"])
def test_unestablished_or_excessive_count_cannot_reserve(tmp_path, pricing, count):
    session = SessionCallBudget(tmp_path / "test-only.sqlite", "5", models=(MODEL,))
    with pytest.raises(ConfigurationError, match="counted input"):
        session.for_request(MODEL, 100, input_upper_bound=count)
    assert session.status()["attempts"] == 0


def test_zero_count_is_not_replaced_by_full_context(tmp_path, pricing):
    _, budget = request(tmp_path, pricing, incoming=0)
    assert budget.input_token_bound == 0 and budget.reservation == 400


@pytest.mark.parametrize("details", [
    None, NS(), NS(cached_tokens=0), NS(cache_write_tokens=0),
    NS(cached_tokens=True, cache_write_tokens=0), NS(cached_tokens=-1, cache_write_tokens=0),
    NS(cached_tokens=0, cache_write_tokens=-1), NS(cached_tokens=0, cache_write_tokens="10"),
    NS(cached_tokens=300, cache_write_tokens=300),
])
def test_missing_or_invalid_billing_buckets_keep_whole_reservation(tmp_path, pricing, details):
    session, budget = request(tmp_path, pricing)
    token = budget.reserve(MODEL)
    response = receipt()
    response.usage.prompt_tokens_details = details
    budget.settle(token, response)
    saved = row(session.path)
    assert saved["state"] == "reserved_or_unknown" and saved["charge"] == 1150


@pytest.mark.parametrize("incoming,outgoing,expected", [
    (601,1,["input_token_bound"]), (600,101,["output_token_bound"]),
    (601,101,["input_token_bound","output_token_bound"]),
])
def test_token_bound_breach_is_recorded_even_when_cache_makes_cost_lower(tmp_path, pricing,
                                                                     incoming,outgoing,expected):
    session, budget = request(tmp_path, pricing)
    token = budget.reserve(MODEL)
    with pytest.raises(ProviderUnavailable, match="token bound") as failure:
        budget.settle(token, receipt(incoming,outgoing,cached=incoming,written=0))
    saved = row(session.path)
    assert saved["charge"] < saved["reservation"]
    assert saved["state"] == "measured_over_bound"
    assert json.loads(saved["bound_violation"]) == expected
    assert failure.value.usage.cost_usd == saved["charge"] / 1000000
    with pytest.raises(ProviderUnavailable, match="needs review"):
        budget.reserve(MODEL)


def test_changed_cache_price_cannot_reprice_an_existing_reservation(tmp_path, pricing):
    session, budget = request(tmp_path, pricing)
    token = budget.reserve(MODEL)
    changed = config.TokenPricing(input_rate=D("1"),output_rate=D("4"),cached_rate=D("0.2"),
        write_rate=D("1.25"),long_context_threshold=100000,input_multiplier=D("2"),output_multiplier=D("1.5"))
    other = CallBudget(session.path, "5", model=MODEL, price_per_million=("1","4"),
        reservation_micro_usd=1150, require_returned_model=True, pricing=changed,
        input_token_bound=600, output_token_bound=100)
    with pytest.raises(ConfigurationError, match="captured"):
        other.settle(token, receipt())
    assert row(session.path)["state"] == "reserved_or_unknown"
    budget.settle(token, receipt())


def test_changed_bound_cannot_settle_even_with_same_manual_reservation(tmp_path, pricing):
    session, budget = request(tmp_path, pricing)
    token = budget.reserve(MODEL)
    other = CallBudget(session.path, "5", model=MODEL, price_per_million=("1","4"),
        reservation_micro_usd=1150, require_returned_model=True, pricing=pricing,
        input_token_bound=601, output_token_bound=100)
    with pytest.raises(ConfigurationError, match="captured"):
        other.settle(token, receipt())
    assert row(session.path)["state"] == "reserved_or_unknown"


def test_restarted_same_request_can_settle_but_legacy_budget_cannot(tmp_path, pricing):
    session,budget = request(tmp_path,pricing)
    token=budget.reserve(MODEL)
    legacy=CallBudget(session.path,"5",model=MODEL,price_per_million=("1","4"),
                     reservation_micro_usd=1150,require_returned_model=True)
    with pytest.raises(ConfigurationError,match="captured"):
        legacy.settle(token,receipt())
    restarted=SessionCallBudget(session.path,"5",models=(MODEL,))
    same,_=restarted.for_request(MODEL,100,input_upper_bound=600)
    same.settle(token,receipt())
    assert row(session.path)["charge"]==583
