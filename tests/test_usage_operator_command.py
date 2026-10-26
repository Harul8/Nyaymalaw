"""The operator's usage command (plan AN.17): read an account's usage, add to its allowance from the
operator host only, and total every call's cost. Offline, against a temporary usage store."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from nm.arrive.store_usage import FileUsage
from operations import usage as command

pytestmark = pytest.mark.class_a

ACCOUNT = "advocate@chambers.in"


@pytest.fixture
def store(tmp_path, monkeypatch):
    usage = FileUsage(tmp_path / "usage.sqlite")
    monkeypatch.setattr("nm.app.composition.Application", lambda: SimpleNamespace(usage=usage))
    return usage


def run(capsys, *argv):
    assert command.main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_status_shows_the_trial_in_dollars_and_the_percentage_left(store, capsys):
    assert run(capsys, "status", "--account", ACCOUNT) == {
        "granted": "USD 0.300000", "spent": "USD 0.000000", "left": "100%", "last_notice_shown": None}


def test_a_grant_adds_to_the_allowance_and_says_who_and_why(store, capsys, tmp_path):
    shown = run(capsys, "grant", "--account", ACCOUNT, "--usd", "4.70", "--operator", "rahul",
                "--reason", "development past the trial")
    assert shown["granted"] == "USD 5.000000" and shown["left"] == "100%"
    import sqlite3
    with sqlite3.connect(tmp_path / "usage.sqlite") as db:
        assert db.execute("SELECT note FROM grants WHERE kind='operator'").fetchone() == (
            "rahul: development past the trial",)


@pytest.mark.parametrize("amount", ["0", "-1", "five", "0.0000001", "5000"])
def test_an_amount_that_is_not_exact_positive_and_bounded_changes_nothing(store, capsys, amount):
    with pytest.raises(SystemExit) as stopped:
        command.main(["grant", "--account", ACCOUNT, "--usd", amount, "--operator", "rahul", "--reason", "x"])
    assert stopped.value.code == 2 and "Nothing was changed" in capsys.readouterr().err
    assert store.standing(ACCOUNT)["granted"] == 300_000


def test_totals_give_every_calls_cost_in_dollars(store, capsys):
    store.record(ACCOUNT, {"kind": "structured", "operation": "core_understanding", "tier": "routine",
                           "model": "gpt-6-luna", "outcome": "ok", "attempts": 1, "tokens_in": 10,
                           "tokens_out": 5, "cached_tokens": 0, "cache_write_tokens": 0,
                           "audio_seconds": None, "micro_usd": 1_250})
    totals = run(capsys, "totals")
    assert totals["calls"] == 1 and totals["cost"] == "USD 0.001250" and totals["not_established"] == 0
    assert totals["by_model"] == [{"model": "gpt-6-luna", "calls": 1, "not_established": 0, "cost": "USD 0.001250"}]
