"""Every day the serving process sweeps the usage ledger of what is eight years old, carried so that no balance changes (plan
AN.53, 53h4h2; D241: the usage ledger, eight years as a billing record (confirm)).

53h4h1 gave the usage store its sweep, which carries the sums of what it removes so that no balance changes, and keeps each
trial. Here it is called: through a narrow port of its own that only the daily step is given (the turn path's port reads a
standing and records a call, and removes nothing), over the same store, by the daily sweep of the serving process, eight years
back on the calendar. It says what went, by counts only, and says so where the store refuses.

Offline: the served application with stand-in models; no model call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from nm.app import main
from nm.arrive.store_usage import USAGE_KEPT_YEARS, years_before
from nm.arrive.usage_port import UsageRefused, UsageSweepPort
from tests.served_application import OWNER
from tests.test_usage_store import call

pytestmark = pytest.mark.class_a


def test_the_sweep_has_a_narrow_door_of_its_own_over_the_same_store(served):
    """Narrow as this codebase's ports are: what the port declares is what is gated (nm/shared/policed_port_adapter.py)."""
    from nm.shared.policed_port_adapter import port_methods

    sweep = served.app.usage_sweep
    assert sweep.inner is served.app.usage.inner, "one store, two narrow doors"
    assert sweep.port is UsageSweepPort and port_methods(UsageSweepPort) == {"sweep"}


def test_the_daily_step_sweeps_eight_years_back_and_no_balance_changes(served, capsys):
    usage = served.app.usage
    usage.record(OWNER, call(micro_usd=1_500))
    before = usage.standing(OWNER)
    then = datetime.now(timezone.utc) + timedelta(days=8 * 366)  # every row written today is then more than eight years old
    main._sweep_usage(served.app, then)
    after = usage.standing(OWNER)
    assert {k: after[k] for k in ("granted", "spent", "left")} == {k: before[k] for k in ("granted", "spent", "left")}
    totals = usage.totals()
    assert totals["carried"]["calls"] >= 1 and totals["by_outcome"] == [], "the calls went, carried"
    said = capsys.readouterr().err
    assert f"of the usage ledger written {USAGE_KEPT_YEARS} years ago or more were removed" in said
    assert "no balance changes" in said


def test_it_asks_the_store_for_the_day_eight_years_before_on_the_calendar():
    asked = []
    application = SimpleNamespace(usage_sweep=SimpleNamespace(sweep=lambda before: asked.append(before) or
                                                              {"calls": 0, "grants": 0}))
    now = datetime(2034, 11, 15, 9, 0, tzinfo=timezone.utc)
    main._sweep_usage(application, now)
    assert asked == [years_before(now, USAGE_KEPT_YEARS)] == [datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)]


def test_nothing_gone_says_nothing_and_a_store_that_refuses_is_said_and_tried_tomorrow(capsys):
    quiet = SimpleNamespace(usage_sweep=SimpleNamespace(sweep=lambda before: {"calls": 0, "grants": 0}))
    main._sweep_usage(quiet, datetime.now(timezone.utc))
    assert capsys.readouterr().err == ""

    def refusing(before):
        raise UsageRefused("storage")
    main._sweep_usage(SimpleNamespace(usage_sweep=SimpleNamespace(sweep=refusing)), datetime.now(timezone.utc))
    assert "The usage ledger could not be swept now (UsageRefused)." in capsys.readouterr().err


def test_the_daily_loop_sweeps_it(monkeypatch):
    """The one daily loop of the serving process calls it, after the others."""
    import inspect

    loop = inspect.getsource(main._keep_deleted)
    assert "_sweep_usage(application, now)" in loop
