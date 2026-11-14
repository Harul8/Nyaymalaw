"""A turn's attempt is kept ninety days after the turn finished or stopped (plan AN.53, D241's retention: the turn attempts).

D241: 'a turn's attempt record, 90 days after the turn finished or stopped (it exists so that a repeated send returns the saved
answer, which the conversation itself holds)'. The attempt store recorded no time at all, so nothing could say when an attempt
ended, and every one was kept for ever. Version 4 records when each attempt stopped running - set as it stops, never while it runs,
which the table itself holds - and carries a version 3 store over with every record, an attempt already ended taken as ending at
the carrying over. The sweep removes what ended before a moment and never a claim still running: that recovery has an owner, the
server's start, never elapsed time. A message sent again after its attempt is gone is answered from the conversation, with no
model call. The sweep is on a narrow port of its own that only the daily sweep is given.

Offline: a store in a temporary folder with a stand-in clock, and the served application with stand-in models.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from nm.shared import turn_attempt_store
from nm.shared.turn_attempt_port import AttemptRefused
from nm.shared.turn_attempt_store import _SQL_V3, ENDED_KEPT_DAYS, VERSION, FileTurnAttempts
from tests.test_core_served import served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
REQUEST = "e" * 64
NOW = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)


def _at(monkeypatch, moment):
    monkeypatch.setattr(turn_attempt_store, "_now", lambda: moment.isoformat(timespec="seconds"))


def _rows(path):
    with sqlite3.connect(path) as db:
        return dict(db.execute("SELECT identity, ended_at FROM turn_attempts").fetchall())


def test_an_attempt_records_when_it_ended_and_a_running_one_has_no_end(tmp_path, monkeypatch):
    path = tmp_path / "turn-attempts.sqlite"
    store = FileTurnAttempts(path)
    _at(monkeypatch, NOW)
    claim = store.claim(A, REQUEST)
    store.claim(B, REQUEST)
    store.finish(A, claim["token"], "finished")
    assert _rows(path) == {A: NOW.isoformat(timespec="seconds"), B: None}


def test_the_sweep_removes_what_ended_ninety_days_ago_and_never_a_running_claim(tmp_path, monkeypatch):
    path = tmp_path / "turn-attempts.sqlite"
    store = FileTurnAttempts(path)
    _at(monkeypatch, NOW - timedelta(days=ENDED_KEPT_DAYS + 5))
    old = store.claim(A, REQUEST)
    store.finish(A, old["token"], "terminal", "G-GROUND")
    store.claim(B, REQUEST)  # running since then, never released: a crash's claim
    stopped = store.claim(C, REQUEST)
    store.finish(C, stopped["token"], "retryable", "stopped")
    _at(monkeypatch, NOW - timedelta(days=10))
    young = store.claim(D, REQUEST)
    store.finish(D, young["token"], "finished")
    assert store.sweep(NOW - timedelta(days=ENDED_KEPT_DAYS)) == 2
    assert set(_rows(path)) == {B, D}, "the running claim and the young attempt stay"
    assert store.sweep(NOW - timedelta(days=ENDED_KEPT_DAYS)) == 0


def test_an_attempt_taken_up_again_runs_without_an_end_and_the_start_ends_what_it_releases(tmp_path, monkeypatch):
    path = tmp_path / "turn-attempts.sqlite"
    store = FileTurnAttempts(path)
    _at(monkeypatch, NOW)
    first = store.claim(A, REQUEST)
    store.finish(A, first["token"], "retryable", "stopped")
    store.claim(A, REQUEST)
    assert _rows(path)[A] is None, "running again"
    _at(monkeypatch, NOW + timedelta(hours=1))
    assert store.release_ended() == 1
    assert _rows(path)[A] == (NOW + timedelta(hours=1)).isoformat(timespec="seconds")


def test_the_table_itself_refuses_a_running_attempt_with_an_end_or_an_ended_one_without(tmp_path):
    path = tmp_path / "turn-attempts.sqlite"
    FileTurnAttempts(path)
    with sqlite3.connect(path) as db:
        for state, ended in (("running", "2027-01-01T00:00:00+00:00"), ("finished", None)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO turn_attempts VALUES (?,?,?,0,?,NULL,?)", (A, REQUEST, B, state, ended))


def test_a_version_three_store_is_carried_over_and_kept_its_full_ninety_days_from_then(tmp_path, monkeypatch):
    path = tmp_path / "turn-attempts.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(_SQL_V3)
        db.execute("PRAGMA user_version=3")
        db.execute("INSERT INTO turn_attempts VALUES (?,?,?,2,'finished',NULL)", (A, REQUEST, B))
        db.execute("INSERT INTO turn_attempts VALUES (?,?,?,1,'running',NULL)", (B, REQUEST, A))
    _at(monkeypatch, NOW)
    store = FileTurnAttempts(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION
    assert _rows(path) == {A: NOW.isoformat(timespec="seconds"), B: None}
    assert store.sweep(NOW - timedelta(days=1)) == 0, "nothing carried over goes before its ninety days"
    assert store.sweep(NOW + timedelta(days=ENDED_KEPT_DAYS, seconds=1)) == 1


def test_the_moment_carries_its_zone(tmp_path):
    with pytest.raises(AttemptRefused):
        FileTurnAttempts(tmp_path / "turn-attempts.sqlite").sweep(datetime(2027, 3, 1))


def test_the_sweep_has_a_narrow_port_of_its_own(served):
    from nm.shared.policed_port_adapter import port_methods
    from nm.shared.turn_attempt_port import TurnAttemptPort, TurnAttemptSweepPort
    assert port_methods(TurnAttemptSweepPort) == {"sweep"} and "sweep" not in port_methods(TurnAttemptPort)
    assert served.app.turn_attempt_sweep.inner is served.app.turn_attempts.inner, "one store, two narrow doors"


def test_a_message_sent_again_after_its_attempt_is_gone_is_answered_from_the_conversation(served, capsys):
    from nm.app import main
    reply = successful(served)
    calls = len(served.model.calls)
    main._sweep_attempts(served.app, datetime.now(timezone.utc) + timedelta(days=ENDED_KEPT_DAYS + 1))
    assert "1 attempt(s) of turns that ended" in capsys.readouterr().err
    again = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1",
                                                  "chat_id": reply["chat_id"]})
    assert again.status_code == 200, again.text
    assert again.json()["elements"] == reply["elements"], "the saved answer, as it was"
    assert len(served.model.calls) == calls, "no model was asked again"
