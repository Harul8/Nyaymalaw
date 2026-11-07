"""The Admin area reads the turn record (plan AN.46, piece 46r; owner decision D120, 7 Nov 2026): answers a day, how turns ended, how long
an answer took - counts and times, no account, no model, no word. Read-only; a record that has not begun is empty, one that will not open
is said to be unreadable and leaves the rest of the Usage page standing (D128). Synthetic lines through the real turn record."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from nm.app.admin_views import PERIODS, content_free, overview_view, usage_view
from nm.arrive.admin_access import SETTING, roster_from
from nm.arrive.admin_directory import AdminFileDirectory
from nm.arrive.admin_port import AdminTurnsPort, AdminUnavailable
from nm.arrive.admin_turns import AdminTurns, _rank
from nm.arrive.admin_usage import AdminUsage
from nm.arrive.store_turn_events import FileTurnEvents

pytestmark = pytest.mark.class_a

KEY = "Synthetic-turn-reading-key-46"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)  # 17:30 on 7 Nov in India
ROSTER = roster_from({SETTING: "boss@example.test:admin"})


def line(ended, seconds=60, outcome="answered", **changes):
    event = {"started_at": ended - timedelta(seconds=seconds), "ended_at": ended, "outcome": outcome, "model": "gpt-6-luna",
             "effort": "medium", "calls": 5, "micro_usd": 1000, "documents": 0}
    event.update(changes)
    return event


@pytest.fixture
def record(tmp_path):
    return FileTurnEvents(tmp_path / "turn-events.sqlite")


@pytest.fixture
def reader(record):
    return AdminTurns(record.path)


def test_it_is_the_turn_port(reader):
    assert isinstance(reader, AdminTurns) and hasattr(AdminTurnsPort, "summary")


def test_turns_are_counted_by_the_indian_day_they_ended_and_by_how_they_ended(record, reader):
    # 18:29 UTC on 6 Nov is 23:59 on 6 Nov in India; 18:30 UTC is 00:00 on 7 Nov.
    record.record("a@example.test", line(datetime(2026, 11, 6, 18, 29, tzinfo=timezone.utc)))
    record.record("a@example.test", line(datetime(2026, 11, 6, 18, 30, tzinfo=timezone.utc)))
    record.record("b@example.test", line(datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc), outcome="failed", calls=None, micro_usd=None))
    record.record("b@example.test", line(datetime(2026, 11, 7, 7, 0, tzinfo=timezone.utc), outcome="stopped"))
    record.record("b@example.test", line(datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc), outcome="refused"))
    found = reader.summary(NOW - timedelta(days=3), NOW + timedelta(days=1))
    assert [(d.day, d.answered, d.stopped, d.refused, d.failed) for d in found.by_day] == [
        ("2026-11-06", 1, 0, 0, 0), ("2026-11-07", 1, 1, 1, 1)]


def test_the_period_is_half_open_so_a_turn_is_counted_once(record, reader):
    at = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
    record.record("a@example.test", line(at))
    assert [d.answered for d in reader.summary(at, at + timedelta(days=1)).by_day] == [1]
    assert reader.summary(at - timedelta(days=1), at).by_day == ()


def test_the_middle_and_slow_ends_are_those_of_answered_turns_only(record, reader):
    for seconds in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        record.record("a@example.test", line(NOW - timedelta(hours=1), seconds=seconds))
    record.record("a@example.test", line(NOW - timedelta(hours=1), seconds=5000, outcome="failed"))
    found = reader.summary(NOW - timedelta(days=1), NOW)
    assert (found.answered_seconds_middle, found.answered_seconds_slow) == (50, 90)
    assert _rank([], 0.5) is None and _rank([7], 0.9) == 7


def test_the_summary_carries_no_account_model_or_word_and_says_when_the_record_began(record, reader):
    record.record("someone@example.test", line(NOW - timedelta(days=2), model="gpt-6-1-sol"))
    record.record("someone@example.test", line(NOW - timedelta(hours=3)))
    found = reader.summary(NOW - timedelta(days=5), NOW)
    assert found.first_at == NOW.replace(microsecond=0) - timedelta(days=2)
    shown = repr(found)
    for private in ("someone", hashlib.sha256(b"someone@example.test").hexdigest(), "sol", "luna"):
        assert private not in shown


def test_a_record_that_has_not_begun_is_empty_and_reading_does_not_make_it(tmp_path):
    reader = AdminTurns(tmp_path / "turn-events.sqlite")
    found = reader.summary(NOW - timedelta(days=7), NOW)
    assert (found.by_day, found.first_at, found.answered_seconds_middle) == ((), None, None)
    assert not (tmp_path / "turn-events.sqlite").exists()


def test_a_file_that_is_not_the_record_is_unreadable_never_empty(tmp_path):
    foreign = tmp_path / "turn-events.sqlite"
    with closing(sqlite3.connect(foreign)) as db, db:
        db.execute("CREATE TABLE turns (id INTEGER, what TEXT)")
    with pytest.raises(AdminUnavailable):
        AdminTurns(foreign).summary(NOW - timedelta(days=7), NOW)


def test_reading_writes_nothing(record, reader):
    record.record("a@example.test", line(NOW - timedelta(hours=1)))
    before = record.path.read_bytes()
    reader.summary(NOW - timedelta(days=7), NOW)
    assert record.path.read_bytes() == before


class Empty:
    def listing(self, now):
        from nm.arrive.admin_port import DirectoryListing
        return DirectoryListing((), ())


def pages(tmp_path, turns):
    directory = AdminFileDirectory(tmp_path, key=KEY)
    usage = AdminUsage(tmp_path / "usage.sqlite")
    return directory, usage, turns


def test_the_usage_page_has_a_row_for_every_day_with_quiet_days_as_zero_and_says_when_the_record_began(tmp_path, record, reader):
    record.record("a@example.test", line(NOW - timedelta(days=2), seconds=30))
    record.record("a@example.test", line(NOW - timedelta(days=2), outcome="refused"))
    directory, usage, turns = pages(tmp_path, reader)
    page = usage_view(ROSTER, directory, usage, NOW, 7, turns)
    answers = page["answers"]
    assert answers["available"] is True and len(answers["by_day"]) == 7
    assert answers["began"] == (NOW - timedelta(days=2)).replace(microsecond=0).isoformat()
    busy = [row for row in answers["by_day"] if row["answered"] or row["refused"]]
    assert busy == [{"day": "2026-11-05", "answered": 1, "stopped": 0, "refused": 1, "failed": 0}]
    assert answers["totals"] == {"answered": 1, "stopped": 0, "refused": 1, "failed": 0}
    assert answers["seconds_middle"] == 30 and content_free(page)


def test_without_a_turn_port_the_page_still_says_it_needs_the_record(tmp_path):
    directory, usage, _ = pages(tmp_path, None)
    assert usage_view(ROSTER, directory, usage, NOW, 30)["answers"] == {"available": False, "needs": "the turn record"}


def test_an_unreadable_record_leaves_the_rest_of_the_page_standing(tmp_path):
    foreign = tmp_path / "turn-events.sqlite"
    with closing(sqlite3.connect(foreign)) as db, db:
        db.execute("CREATE TABLE turns (id INTEGER, what TEXT)")
    directory, usage, turns = pages(tmp_path, AdminTurns(foreign))
    page = usage_view(ROSTER, directory, usage, NOW, 30, turns)
    assert page["answers"] == {"available": False, "unreadable": True}
    assert page["tiles"]["calls"] == 0 and len(page["by_day"]) == 30


def test_the_overview_carries_the_weeks_answers(tmp_path, record, reader):
    record.record("a@example.test", line(NOW - timedelta(hours=2)))
    directory, usage, turns = pages(tmp_path, reader)
    assert overview_view(ROSTER, directory, usage, NOW, turns)["answers"]["totals"]["answered"] == 1
    assert 7 in PERIODS
