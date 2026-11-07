"""Usage as the Admin area reads it (plan AN.46, piece 46e; owner decision D119, 7 Nov 2026): balances, consumption and cost,
content-free; reading starts nobody's trial and changes nothing; a file that is not the usage store is unavailable, never zero.
Synthetic accounts and calls, written through the store's own methods."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive import store_usage
from nm.arrive.admin_port import GROUPINGS, AdminUnavailable
from nm.arrive.admin_usage import AdminUsage
from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import TRIAL_MICRO_USD

pytestmark = pytest.mark.class_a

ANITA, MEERA, NEW = "anita@example.test", "meera@example.test", "never-used@example.test"
DAY = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)  # 11:30 on 7 Nov in India


def digest(who):
    return hashlib.sha256(who.encode("utf8")).hexdigest()


def call(**changes):
    record = {"kind": "structured", "operation": "core_understanding", "tier": "routine", "model": "gpt-6-luna",
              "outcome": "ok", "attempts": 1, "tokens_in": 1000, "tokens_out": 200, "cached_tokens": 100,
              "cache_write_tokens": 50, "audio_seconds": None, "micro_usd": 270}
    record.update(changes)
    return record


@pytest.fixture
def usage(tmp_path, monkeypatch):
    store = FileUsage(tmp_path / "usage.sqlite")
    clock = {"at": DAY}
    monkeypatch.setattr(store_usage, "_now", lambda: clock["at"].isoformat(timespec="seconds"))
    store.clock = clock
    return store


@pytest.fixture
def reader(usage):
    return AdminUsage(usage.path)


def at(usage, when):
    usage.clock["at"] = when


def test_balances_are_the_percentage_the_advocate_is_shown_and_an_account_with_no_record_is_absent(usage, reader):
    usage.standing(ANITA)
    usage.record(ANITA, call(micro_usd=TRIAL_MICRO_USD // 4))
    usage.standing(MEERA)
    usage.grant(MEERA, 2_000_000, note="Development account")
    balances = reader.balances()
    assert set(balances) == {digest(ANITA), digest(MEERA)} and digest(NEW) not in balances
    anita, meera = balances[digest(ANITA)], balances[digest(MEERA)]
    assert (anita.granted, anita.spent, anita.left_percent) == (TRIAL_MICRO_USD, TRIAL_MICRO_USD // 4, 75)
    assert (meera.granted, meera.spent, meera.left_percent) == (TRIAL_MICRO_USD + 2_000_000, 0, 100)
    assert anita.left_percent == usage.standing(ANITA)["left"] and meera.left_percent == usage.standing(MEERA)["left"]


def test_looking_gives_nobody_a_trial_and_leaves_the_file_exactly_as_it_was(usage, reader):
    usage.standing(ANITA)
    usage.record(ANITA, call())
    before = (usage.path.read_bytes(), usage.path.stat().st_mtime_ns)
    reader.balances()
    reader.consumption(DAY - timedelta(days=1), DAY + timedelta(days=1), "day,model")
    reader.granted_since(DAY - timedelta(days=1), DAY + timedelta(days=1))
    assert (usage.path.read_bytes(), usage.path.stat().st_mtime_ns) == before
    assert digest(NEW) not in reader.balances()
    assert usage.standing(NEW)["granted"] == TRIAL_MICRO_USD  # the first use still gives its trial


def test_consumption_by_model_operation_and_outcome_counts_calls_tokens_and_cost_and_keeps_the_unestablished_apart(usage, reader):
    usage.standing(ANITA)
    usage.record(ANITA, call())
    usage.record(ANITA, call(micro_usd=None))
    usage.record(ANITA, call(model="gpt-6-1-sol", operation="response_writer", micro_usd=1500, tokens_in=4000))
    usage.record(ANITA, call(outcome="ProviderUnavailable", attempts=3, tokens_in=None, tokens_out=None,
                             cached_tokens=None, cache_write_tokens=None, micro_usd=0))
    usage.record(ANITA, call(kind="transcribe", operation="dictation", model="gpt-transcribe", tokens_in=None,
                             tokens_out=None, cached_tokens=None, cache_write_tokens=None, audio_seconds=12.5, micro_usd=40))
    period = (DAY - timedelta(hours=1), DAY + timedelta(hours=1))
    by_model = {row.group: row for row in reader.consumption(*period, "model")}
    luna = by_model[("gpt-6-luna",)]
    assert (luna.calls, luna.micro_usd, luna.cost_not_established) == (3, 270 + 0 + 0, 1)
    assert (luna.tokens_in, luna.tokens_out, luna.cached_tokens, luna.cache_write_tokens) == (2000, 400, 200, 100)
    assert by_model[("gpt-6-1-sol",)].micro_usd == 1500 and by_model[("gpt-transcribe",)].audio_seconds == 12.5
    by_outcome = {row.group: row.calls for row in reader.consumption(*period, "outcome")}
    assert by_outcome == {("ProviderUnavailable",): 1, ("ok",): 4}
    assert {row.group[0] for row in reader.consumption(*period, "operation")} == {"core_understanding", "response_writer", "dictation"}


def test_a_day_is_an_indian_day_and_the_period_is_half_open(usage, reader):
    usage.standing(ANITA)
    evening_before = datetime(2026, 11, 7, 18, 29, tzinfo=timezone.utc)  # 23:59 in India on the 7th
    after_midnight = datetime(2026, 11, 7, 18, 31, tzinfo=timezone.utc)   # 00:01 in India on the 8th
    for when in (evening_before, after_midnight):
        at(usage, when)
        usage.record(ANITA, call())
    wide = (datetime(2026, 11, 7, tzinfo=timezone.utc), datetime(2026, 11, 9, tzinfo=timezone.utc))
    assert [(row.group, row.calls) for row in reader.consumption(*wide, "day")] == [(("2026-11-07",), 1), (("2026-11-08",), 1)]
    assert [row.calls for row in reader.consumption(evening_before, after_midnight, "day")] == [1]       # `until` is not included
    assert reader.consumption(after_midnight, after_midnight, "day") == ()


def test_the_groupings_that_combine_keep_their_parts_in_order(usage, reader):
    usage.standing(ANITA)
    usage.standing(MEERA)
    usage.record(ANITA, call())
    at(usage, DAY + timedelta(days=1))
    usage.record(MEERA, call(model="gpt-6-1-sol"))
    wide = (DAY - timedelta(days=1), DAY + timedelta(days=3))
    assert [row.group for row in reader.consumption(*wide, "day,model")] == [("2026-11-07", "gpt-6-luna"), ("2026-11-08", "gpt-6-1-sol")]
    assert [row.group[0] for row in reader.consumption(*wide, "account,day")] == sorted([digest(ANITA), digest(MEERA)])
    assert all(len(row.group[0]) == 64 for row in reader.consumption(*wide, "account"))


def test_only_the_listed_groupings_are_accepted_and_nothing_a_caller_sends_reaches_a_statement(usage, reader):
    period = (DAY - timedelta(days=1), DAY + timedelta(days=1))
    for grouping in GROUPINGS:
        reader.consumption(*period, grouping)
    for bad in ("matter", "model; DROP TABLE calls", "at", "", None, "Day"):
        with pytest.raises(ValueError):
            reader.consumption(*period, bad)
    with pytest.raises(ValueError):
        reader.consumption(datetime(2026, 11, 7), DAY, "day")
    assert FileUsage(usage.path).totals()["calls"] == 0


def test_allowance_given_in_a_period_counts_trials_and_grants_alike(usage, reader):
    usage.standing(ANITA)
    at(usage, DAY + timedelta(days=2))
    usage.grant(ANITA, 1_000_000, note="Top-up")
    assert reader.granted_since(DAY - timedelta(hours=1), DAY + timedelta(days=1)) == TRIAL_MICRO_USD
    assert reader.granted_since(DAY, DAY + timedelta(days=3)) == TRIAL_MICRO_USD + 1_000_000


def test_a_store_not_yet_made_is_an_empty_one_and_a_file_that_is_not_the_store_is_unavailable_never_zero(tmp_path):
    absent = AdminUsage(tmp_path / "never-made.sqlite")
    period = (DAY, DAY + timedelta(days=1))
    assert absent.balances() == {} and absent.consumption(*period, "day") == () and absent.granted_since(*period) == 0
    for name, content in (("empty.sqlite", b""), ("text.sqlite", b"not a database")):
        (tmp_path / name).write_bytes(content)
        with pytest.raises(AdminUnavailable):
            AdminUsage(tmp_path / name).balances()
    foreign = tmp_path / "foreign.sqlite"
    with closing(sqlite3.connect(foreign)) as db, db:
        db.execute("CREATE TABLE calls (account TEXT, micro_usd INTEGER)")
    with pytest.raises(AdminUnavailable):
        AdminUsage(foreign).consumption(*period, "model")


def test_what_comes_back_names_no_address_and_no_content(usage, reader):
    usage.standing(ANITA)
    usage.record(ANITA, call())
    shown = repr(reader.balances()) + repr(reader.consumption(DAY - timedelta(days=1), DAY + timedelta(days=1), "account"))
    assert "@" not in shown and "example" not in shown
