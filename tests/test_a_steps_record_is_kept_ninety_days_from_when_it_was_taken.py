"""A step's record is kept ninety days from when the step was taken (plan AN.53, D241's retention, with the turns' attempts).

A step's record (48f3) holds whose step it is - the advocate's identifier in plain words - which conversation and turn, which route,
a go-ahead's choice and disputes, whether it had begun and the sign-in it was asked under by its fingerprint. It goes when its step
ends; but a step kept because its advocate's sign-in lapsed (52c4) waited for ever, with nothing to say how old it was. Version 2
records when each step was taken and carries a version 1 store over with every record, each taken as at the carrying over. The
daily sweep lets go of the records of steps taken ninety days ago or more, on a narrow port of its own; such a step's matter waits
for the go-ahead, as it always did.

Offline: a store in a temporary folder with a stand-in clock, and the served application with stand-in models.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from nm.shared import step_record_store
from nm.shared.step_record_store import _SQL_V1, TAKEN_KEPT_DAYS, VERSION, FileStepRecords
from tests.test_core_served import served  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a

NOW = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)
WHO = "a@example.test"


def _at(monkeypatch, moment):
    monkeypatch.setattr(step_record_store, "_now", lambda: moment.isoformat(timespec="seconds"))


def test_each_record_says_when_its_step_was_taken_and_the_sweep_lets_go_of_the_old_ones(tmp_path, monkeypatch):
    records = FileStepRecords(tmp_path / "step-records.sqlite")
    _at(monkeypatch, NOW - timedelta(days=TAKEN_KEPT_DAYS + 3))
    records.taken(WHO, "t-old", route="go", chat_id="c1", choice="research", disputes=["D1"], session="f" * 64)
    _at(monkeypatch, NOW - timedelta(days=2))
    records.taken(WHO, "t-young", route="send")
    assert {each["turn_id"]: each["taken_at"] for each in records.left()} == {
        "t-old": (NOW - timedelta(days=TAKEN_KEPT_DAYS + 3)).isoformat(timespec="seconds"),
        "t-young": (NOW - timedelta(days=2)).isoformat(timespec="seconds")}
    assert records.sweep(NOW - timedelta(days=TAKEN_KEPT_DAYS)) == 1
    assert [each["turn_id"] for each in records.left()] == ["t-young"]
    assert records.sweep(NOW - timedelta(days=TAKEN_KEPT_DAYS)) == 0


def test_a_version_one_store_is_carried_over_each_record_taken_as_at_the_carrying_over(tmp_path, monkeypatch):
    path = tmp_path / "step-records.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(_SQL_V1)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?)", (WHO, "t1", "c1", "go", "research", '["D1"]', "f" * 64, 1))
    _at(monkeypatch, NOW)
    records = FileStepRecords(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION
    (kept,) = records.left()
    assert kept["turn_id"] == "t1" and kept["begun"] is True and kept["disputes"] == ["D1"]
    assert kept["taken_at"] == NOW.isoformat(timespec="seconds")
    assert records.sweep(NOW - timedelta(days=1)) == 0, "nothing carried over goes before its ninety days"


def test_the_moment_carries_its_zone(tmp_path):
    with pytest.raises(ValueError):
        FileStepRecords(tmp_path / "step-records.sqlite").sweep(datetime(2027, 3, 1))


def test_the_sweep_has_a_narrow_port_of_its_own(served):
    from nm.shared.policed_port_adapter import port_methods
    from nm.shared.step_record_port import StepRecordPort, StepRecordSweepPort
    assert port_methods(StepRecordSweepPort) == {"sweep"} and "sweep" not in port_methods(StepRecordPort)
    assert served.app.step_record_sweep.inner is served.app.step_records.inner, "one store, two narrow doors"


def test_the_daily_sweep_lets_go_of_old_step_records_and_says_how_many(served, monkeypatch, capsys):
    from nm.app import main
    _at(monkeypatch, datetime.now(timezone.utc) - timedelta(days=TAKEN_KEPT_DAYS + 1))
    served.app.step_records.taken("owner@example.test", "turn-kept", route="go", chat_id="c1", choice="research",
                                  session="f" * 64)
    main._sweep_attempts(served.app, datetime.now(timezone.utc))
    assert f"1 record(s) of steps taken {TAKEN_KEPT_DAYS} days ago or more were let go." in capsys.readouterr().err
    assert served.app.step_records.left() == []
