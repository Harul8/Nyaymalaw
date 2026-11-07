"""The turn record's store (plan AN.46, piece 46h; owner decision D120, 7 Nov 2026): one content-free line per finished turn, in its own
file, naming the account only by digest; nothing but times, names and numbers can be written; a file that is not the store is refused."""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive.store_turn_events import FileTurnEvents
from nm.arrive.turn_event_port import OUTCOMES, TurnEventPort, TurnEventRefused

pytestmark = pytest.mark.class_a

ACCOUNT = "Advocate@Chambers.test"
START = datetime(2026, 11, 7, 10, 0, 5, 700000, tzinfo=timezone.utc)


def line(**changes):
    event = {"started_at": START, "ended_at": START + timedelta(seconds=94, microseconds=100000), "outcome": "answered",
             "model": "gpt-6-luna", "effort": "medium", "calls": 13, "micro_usd": 183_000, "documents": 2}
    event.update(changes)
    return event


@pytest.fixture
def events(tmp_path):
    return FileTurnEvents(tmp_path / "turn-events.sqlite")


def rows(events):
    with closing(sqlite3.connect(events.path)) as db:
        return db.execute("SELECT account,started_at,ended_at,seconds,outcome,model,effort,calls,micro_usd,documents FROM turns "
                          "ORDER BY id").fetchall()


def test_it_is_the_turn_event_port(events):
    assert isinstance(events, FileTurnEvents) and hasattr(TurnEventPort, "record")


def test_a_line_keeps_the_times_in_whole_seconds_the_seconds_taken_and_the_account_only_as_a_digest(events, tmp_path):
    events.record(ACCOUNT, line())
    (row,) = rows(events)
    digest = hashlib.sha256(b"advocate@chambers.test").hexdigest()
    assert row == (digest, "2026-11-07T10:00:05+00:00", "2026-11-07T10:01:39+00:00", 94, "answered", "gpt-6-luna", "medium", 13,
                   183_000, 2)
    assert b"chambers" not in events.path.read_bytes().lower() and b"advocate" not in events.path.read_bytes().lower()
    assert hashlib.sha256(b"ADVOCATE@chambers.test").hexdigest() != digest  # the id is folded first, so spellings agree
    events.record("advocate@chambers.test ", line())
    assert {r[0] for r in rows(events)} == {digest}


def test_a_turn_may_end_four_ways_and_may_not_have_established_its_calls_or_cost(events):
    for outcome in OUTCOMES:
        events.record(ACCOUNT, line(outcome=outcome, calls=None, micro_usd=None))
    assert [r[4] for r in rows(events)] == list(OUTCOMES) and all(r[7] is None and r[8] is None for r in rows(events))


def test_nothing_that_is_not_a_time_a_short_name_or_a_whole_number_can_be_written(events):
    bad = [line(outcome="done"), line(model="the tenant refused the notice"), line(effort=""), line(model=None),
           line(calls=-1), line(calls=1.5), line(calls=True), line(micro_usd="12"), line(documents=-2), line(documents=None),
           line(started_at=START.replace(tzinfo=None)), line(started_at="2026-11-07T10:00:00+00:00"),
           line(ended_at=START - timedelta(seconds=1)), {**line(), "message": "hello"},
           {key: value for key, value in line().items() if key != "documents"}, "not a line", None]
    for event in bad:
        with pytest.raises(ValueError):
            events.record(ACCOUNT, event)
    for account in ("", "   ", None, 7):
        with pytest.raises(ValueError):
            events.record(account, line())
    assert rows(events) == []


def test_lines_written_together_are_all_kept(events):
    barrier = threading.Barrier(6)

    def writer():
        barrier.wait()
        for _ in range(5):
            events.record(ACCOUNT, line())

    threads = [threading.Thread(target=writer) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(rows(events)) == 30


def test_the_file_has_no_column_that_could_hold_a_word_of_the_turn(events):
    with closing(sqlite3.connect(events.path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(turns)")}
    assert columns == {"id", "account", "started_at", "ended_at", "seconds", "outcome", "model", "effort", "calls", "micro_usd",
                       "documents"}


def test_a_file_that_is_not_the_store_is_refused_and_a_lost_one_is_not_started_again_from_nothing(tmp_path):
    foreign = tmp_path / "foreign.sqlite"
    with closing(sqlite3.connect(foreign)) as db, db:
        db.execute("CREATE TABLE turns (id INTEGER, what TEXT)")
    empty = tmp_path / "empty.sqlite"
    empty.write_bytes(b"")
    for path in (foreign, empty):
        with pytest.raises(TurnEventRefused):
            FileTurnEvents(path)
    made = FileTurnEvents(tmp_path / "made.sqlite")
    made.path.unlink()
    with pytest.raises(TurnEventRefused):
        made.record(ACCOUNT, line())
    assert not made.path.exists()
