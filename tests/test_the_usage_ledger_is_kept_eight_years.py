"""The usage ledger is kept eight years, and what goes is carried so that no balance changes (plan AN.53, 53h4h1; D241: the usage
ledger, eight years as a billing record (confirm)).

The usage store keeps what each account was given (its trial, once, and what an operator adds) and what each call cost, and an
account's balance is summed from them: removing old rows would change it. Worse, the store gives an account its trial whenever it
has no trial row, so a trial row swept away would be given again. So the store carries what a sweep removes: its own small table
holds, for each account, the sums of the calls and the grants removed - what was given, what was spent, how many calls, how many
whose cost was not established - and every reader of a balance or a total counts it. The trial row is kept whatever its age.
A store of the first version is carried to the second in place, with nothing in it changed; the Admin area, which only reads,
reads either.

Offline: the store in a temporary folder; no model call.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive import store_usage
from nm.arrive.admin_usage import AdminUsage
from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import TRIAL_MICRO_USD, UsageRefused
from tests.test_usage_store import ADVOCATE, call

pytestmark = pytest.mark.class_a
OTHER = "other@chambers.in"
NOW = datetime(2034, 11, 15, 9, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=8 * 365 + 2)
LONG_AGO = (CUTOFF - timedelta(days=40)).isoformat(timespec="seconds")
LATELY = (NOW - timedelta(days=40)).isoformat(timespec="seconds")


def _age(path, table, when, where="1=1"):
    with sqlite3.connect(path) as db:
        db.execute(f"UPDATE {table} SET at=? WHERE {where}", (when,))


def _counted(usage):
    """What every reader of a balance or a total says: each account's standing and the operator's totals."""
    totals = usage.totals()
    return ({who: {k: v for k, v in usage.standing(who).items() if k != "noticed"} for who in (ADVOCATE, OTHER)},
            {k: totals[k] for k in ("accounts", "granted", "calls", "micro_usd", "not_established")})


def _rows(path, table):
    with sqlite3.connect(path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def ledger(tmp_path):
    """Two accounts, each with its trial; old and recent calls, one of them with no cost established; an old operator grant."""
    path = tmp_path / "usage.sqlite"
    usage = FileUsage(path)
    for who in (ADVOCATE, OTHER):
        usage.standing(who)  # its trial
    usage.grant(ADVOCATE, 500_000, note="Operator top-up, long ago")
    for who, cost in ((ADVOCATE, 1_000), (ADVOCATE, None), (OTHER, 2_500)):
        usage.record(who, call(micro_usd=cost, outcome="ok" if cost is not None else "ProviderUnavailable"))
    _age(path, "calls", LONG_AGO)
    _age(path, "grants", LONG_AGO)
    usage.record(ADVOCATE, call(micro_usd=700))
    _age(path, "calls", LATELY, "micro_usd=700")
    return path, usage


def test_the_period_is_eight_years_and_its_day_is_found_on_the_calendar():
    assert store_usage.USAGE_KEPT_YEARS == 8
    assert store_usage.years_before(datetime(2034, 2, 28, tzinfo=timezone.utc), 8) == datetime(2026, 2, 28, tzinfo=timezone.utc)
    assert store_usage.years_before(datetime(2032, 2, 29, tzinfo=timezone.utc), 8) == datetime(2024, 2, 29, tzinfo=timezone.utc)
    assert store_usage.years_before(datetime(2033, 2, 28, tzinfo=timezone.utc), 1) == datetime(2032, 2, 28, tzinfo=timezone.utc)
    assert store_usage.years_before(datetime(2028, 2, 29, tzinfo=timezone.utc), 1) == datetime(2027, 2, 28, tzinfo=timezone.utc)


def test_a_sweep_carries_what_it_removes_so_no_balance_or_total_changes(ledger):
    path, usage = ledger
    before = _counted(usage)
    gone = usage.sweep(CUTOFF)
    assert gone == {"calls": 3, "grants": 1}
    assert _counted(usage) == before, "every balance and every total as it was"
    assert _rows(path, "calls") == 1, "the recent call kept as itself"
    assert usage.totals()["carried"] == {"accounts": 2, "calls": 3, "micro_usd": 3_500, "not_established": 1,
                                         "granted": 500_000}
    assert {row["outcome"]: row["calls"] for row in usage.totals()["by_outcome"]} == {"ok": 1}, "of the calls kept"


def test_a_second_sweep_carries_more_and_changes_nothing_else(ledger):
    path, usage = ledger
    usage.sweep(CUTOFF)
    before = _counted(usage)
    assert usage.sweep(CUTOFF) == {"calls": 0, "grants": 0}, "nothing more to carry"
    assert usage.sweep(NOW) == {"calls": 1, "grants": 0}
    assert _counted(usage) == before and _rows(path, "calls") == 0
    assert usage.totals()["carried"]["calls"] == 4


def test_each_trial_is_kept_whatever_its_age_so_none_is_given_twice(ledger):
    path, usage = ledger
    usage.sweep(NOW + timedelta(days=1))
    with sqlite3.connect(path) as db:
        trials = db.execute("SELECT COUNT(*) FROM grants WHERE kind='trial'").fetchone()[0]
    assert trials == 2
    assert usage.standing(OTHER)["granted"] == TRIAL_MICRO_USD, "its trial once, not again"


def test_the_admin_area_reads_the_carried_sums_and_a_store_of_the_first_version_alike(ledger, tmp_path):
    path, usage = ledger
    admin = AdminUsage(path)
    before = admin.balances()
    usage.sweep(CUTOFF)
    assert admin.balances() == before, "the Admin area's balances as they were"
    first = tmp_path / "first.sqlite"
    with sqlite3.connect(first) as db:
        for sql in store_usage._SQL_V1.values():
            db.execute(sql)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO grants (account,kind,micro_usd,at,note) VALUES (?,'trial',?,?,'')", ("a" * 64, 300_000, LATELY))
        db.execute("INSERT INTO calls (account,at,kind,operation,tier,model,outcome,attempts,micro_usd) "
                   "VALUES (?,?,'structured','core_understanding','routine','m','ok',1,?)", ("a" * 64, LATELY, 1_200))
    assert AdminUsage(first).balances()["a" * 64].spent == 1_200, "read as it is, not first carried to the second version"
    with sqlite3.connect(first) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1, "the Admin area only reads: it does not carry it"


def test_a_store_of_the_first_version_is_carried_to_the_second_in_place_with_nothing_in_it_changed(tmp_path):
    first = tmp_path / "usage.sqlite"
    with sqlite3.connect(first) as db:
        for sql in store_usage._SQL_V1.values():
            db.execute(sql)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO grants (account,kind,micro_usd,at,note) VALUES (?,'trial',?,?,'')", ("b" * 64, 300_000, LATELY))
        db.execute("INSERT INTO calls (account,at,kind,operation,tier,model,outcome,attempts,micro_usd) "
                   "VALUES (?,?,'structured','core_understanding','routine','m','ok',1,?)", ("b" * 64, LATELY, 9_000))
    usage = FileUsage(first)
    with sqlite3.connect(first) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == store_usage.VERSION == 2
        assert db.execute("SELECT COUNT(*) FROM carried").fetchone()[0] == 0
    assert usage.totals()["calls"] == 1 and usage.totals()["micro_usd"] == 9_000 and usage.totals()["granted"] == 300_000
    assert usage.totals()["carried"] == {"accounts": 0, "calls": 0, "micro_usd": 0, "not_established": 0, "granted": 0}


@pytest.mark.parametrize("version", [0, 3])
def test_a_store_of_a_version_it_does_not_know_is_still_refused(tmp_path, version):
    odd = tmp_path / "usage.sqlite"
    with sqlite3.connect(odd) as db:
        for sql in store_usage._SQL.values():
            db.execute(sql)
        db.execute(f"PRAGMA user_version={version}")
    with pytest.raises(UsageRefused):
        FileUsage(odd)


def test_a_first_version_store_with_something_more_in_it_is_refused_not_carried(tmp_path):
    odd = tmp_path / "usage.sqlite"
    with sqlite3.connect(odd) as db:
        for sql in store_usage._SQL_V1.values():
            db.execute(sql)
        db.execute("CREATE TABLE something_else (x TEXT)")
        db.execute("PRAGMA user_version=1")
    with pytest.raises(UsageRefused):
        FileUsage(odd)
    with sqlite3.connect(odd) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1, "left as it was"
