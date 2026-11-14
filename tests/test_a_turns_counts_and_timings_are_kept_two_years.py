"""The counts and timings of turns are kept two years (plan AN.53, D241's retention: the turn record's sweep).

D241: 'the counts and timings of turns, which hold no content, two years'. The turn record (AN.46, 46h) keeps one content-free
line for each finished turn - which account, when, how long, how it ended, the model, the effort, the calls, the cost, how many
documents - and kept every line for ever. Now its sweep removes each line of a turn that ended before a given moment, and the
daily sweep asks it for those that ended KEPT_DAYS (two years, a leap day included) or more ago.

Offline: a record in a temporary folder and stand-in moments; no model call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive.store_turn_events import KEPT_DAYS, FileTurnEvents
from tests.test_core_served import served  # noqa: F401 - served is a fixture
from tests.test_the_turn_record_keeps_a_content_free_line_for_each_finished_turn import ACCOUNT, line, rows

pytestmark = pytest.mark.class_a

NOW = datetime(2028, 11, 14, 9, 0, tzinfo=timezone.utc)


def _ended(days_ago):
    end = NOW - timedelta(days=days_ago)
    return line(started_at=end - timedelta(seconds=90), ended_at=end)


def test_the_lines_of_turns_that_ended_two_years_ago_or_more_go_and_the_rest_stay(tmp_path):
    events = FileTurnEvents(tmp_path / "turn-events.sqlite")
    for days in (3 * 365, KEPT_DAYS + 1, KEPT_DAYS - 1, 30, 0):
        events.record(ACCOUNT, _ended(days))
    assert events.sweep(NOW - timedelta(days=KEPT_DAYS)) == 2
    kept = [row[2] for row in rows(events)]
    assert kept == [(NOW - timedelta(days=days)).isoformat() for days in (KEPT_DAYS - 1, 30, 0)]
    assert events.sweep(NOW - timedelta(days=KEPT_DAYS)) == 0, "a second sweep finds nothing more"


def test_the_moment_is_a_time_with_its_zone(tmp_path):
    events = FileTurnEvents(tmp_path / "turn-events.sqlite")
    events.record(ACCOUNT, _ended(KEPT_DAYS + 1))
    with pytest.raises(ValueError):
        events.sweep(datetime(2026, 11, 14, 9, 0))
    assert len(rows(events)) == 1, "nothing went"


def test_two_years_is_at_least_two_calendar_years():
    assert KEPT_DAYS >= 2 * 365 + 1


def test_the_sweep_has_a_narrow_port_of_its_own_and_the_turn_paths_can_still_only_add_a_line(served):
    from nm.arrive.turn_event_port import TurnEventPort, TurnRecordSweepPort
    from nm.shared.policed_port_adapter import port_methods
    assert port_methods(TurnRecordSweepPort) == {"sweep"} and port_methods(TurnEventPort) == {"record"}
    assert served.app.turn_record_sweep.port is TurnRecordSweepPort and served.app.turn_events.port is TurnEventPort
    assert served.app.turn_record_sweep.inner is served.app.turn_events.inner, "one record, two narrow doors"


# ------------------------------------------------------------------------------- swept daily (53h4c2) ---

def test_the_daily_sweep_removes_the_old_lines_from_the_served_record_and_says_how_many(served, capsys):
    """Plan AN.53, D241 (53h4c2): every day, with the other records' sweeps."""
    from nm.app import main
    now = datetime.now(timezone.utc)
    for days in (KEPT_DAYS + 3, KEPT_DAYS + 1, 10):
        end = now - timedelta(days=days)
        served.app.turn_events.record(ACCOUNT, line(started_at=end - timedelta(seconds=90), ended_at=end))
    main._sweep_turn_lines(served.app, now)
    assert capsys.readouterr().err == "2 line(s) of turns that ended two years ago or more were removed from the turn record.\n"
    main._sweep_turn_lines(served.app, now)
    assert capsys.readouterr().err == "", "nothing more to say"


def test_a_record_that_cannot_be_swept_is_said(served, monkeypatch, capsys):
    from nm.app import main
    from nm.arrive.turn_event_port import TurnEventRefused

    def refuses(before):
        raise TurnEventRefused("storage")
    monkeypatch.setattr(served.app.turn_record_sweep, "sweep", refuses)
    main._sweep_turn_lines(served.app, datetime.now(timezone.utc))
    assert capsys.readouterr().err == "The turn record could not be swept now.\n"


def test_the_daily_loop_sweeps_the_turn_record_with_the_others():
    import inspect

    from nm.app import main
    loop = inspect.getsource(main._keep_deleted)
    assert loop.index("_sweep_expired(application, now)") < loop.index("_sweep_turn_lines(application, now)")
