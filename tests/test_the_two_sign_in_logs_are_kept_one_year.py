"""The two sign-in logs are kept one year, then their older lines go (plan AN.53, 53h4g; D241: the two sign-in logs, one year).

The directory keeps two plain-text logs beside the accounts: the limiter's log of failed attempts (attempts.log - a time with its
offset, the folded account and the address it came from), and the log of why each sign-in failed or happened (auth.log - a time,
the account, the event). Both were appended to for ever. The directory's daily sweep now removes each line a year old or more from
both. A line whose time cannot be read is kept: its age cannot be known. Both logs are written by appending, with no lock, and a
trim rewrites the whole file, so a line written while the trim worked would be lost - in the limiter's log, a failed attempt the
limiter must count. So each writer now takes the log's lock (waiting a moment for a trim in progress, then writing all the same
rather than lose its line or refuse a sign-in), and the trim runs only with the lock; held by another, it waits for the next day.

Offline: a directory in a temporary folder and stand-in moments; no model call; the people and addresses are invented.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive import store_directory
from nm.arrive.store_directory import SIGN_IN_LOGS_KEPT_DAYS, FileDirectory
from nm.shared.store_file_store import claim
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
OLD, RECENT = NOW - timedelta(days=SIGN_IN_LOGS_KEPT_DAYS + 3), NOW - timedelta(days=SIGN_IN_LOGS_KEPT_DAYS - 3)


def _lines(path):
    return path.read_text(encoding="utf8").split("\n")


def _attempts(directory):
    return directory._root / "attempts.log"


def _auth(directory):
    return directory._root / "auth.log"


def test_the_period_is_a_year():
    assert SIGN_IN_LOGS_KEPT_DAYS == 365


def test_a_failed_attempt_a_year_old_goes_and_a_recent_one_and_an_unreadable_line_stay(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    directory.note_failure("old@example.test", "203.0.113.1", OLD)
    _attempts(directory).write_text(_attempts(directory).read_text(encoding="utf8") + "a line that is no line\n",
                                    encoding="utf8")
    directory.note_failure("recent@example.test", "203.0.113.2", RECENT)
    assert directory.sweep_expired(NOW)["log_lines"] == 1
    kept = _lines(_attempts(directory))
    assert len(kept) == 3 and kept[-1] == "" and "a line that is no line" in kept, "the unreadable line kept, and the end"
    assert not any("old@example.test" in line for line in kept) and any("recent@example.test" in line for line in kept)
    mine, here = directory.failures_since("recent@example.test", "203.0.113.2", RECENT - timedelta(minutes=1))
    assert len(mine) == 1 and len(here) == 1, "the limiter still counts what was kept"
    assert directory.skipped_attempt_lines() == 1


def test_the_reason_log_is_trimmed_too_its_local_times_read_as_local(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    local = lambda moment: moment.astimezone().replace(tzinfo=None).isoformat()  # noqa: E731 - as _note writes them
    _auth(directory).write_text(f"{local(OLD)}\told@example.test\twrong password\n"
                                f"{local(RECENT)}\trecent@example.test\tsigned in\n"
                                "no time here\tx\ty\n", encoding="utf8")
    assert directory.sweep_expired(NOW)["log_lines"] == 1
    kept = _auth(directory).read_text(encoding="utf8")
    assert "old@example.test" not in kept and "recent@example.test" in kept and "no time here" in kept


def test_a_last_line_cut_short_stays_cut_and_the_next_failure_still_begins_a_line_of_its_own(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    directory.note_failure("old@example.test", "203.0.113.1", OLD)
    directory.note_failure("recent@example.test", "203.0.113.2", RECENT)
    with _attempts(directory).open("a", encoding="utf8") as handle:
        handle.write("2026-11-15T08:59:00+00:00\tcut")  # the server stopped part-way through a line
    assert directory.sweep_expired(NOW)["log_lines"] == 1
    assert _attempts(directory).read_text(encoding="utf8").endswith("\tcut")
    directory.note_failure("next@example.test", "203.0.113.3", NOW)
    assert _lines(_attempts(directory))[-2].startswith(NOW.isoformat()), "a line of its own, and counted"


def test_nothing_old_leaves_the_file_as_it_was(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    directory.note_failure("recent@example.test", "203.0.113.2", RECENT)
    before = _attempts(directory).stat()
    assert directory.sweep_expired(NOW)["log_lines"] == 0
    after = _attempts(directory).stat()
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns), "not rewritten"


def test_a_log_that_cannot_be_read_is_kept_as_it_is_said_and_tried_again_tomorrow(tmp_path, caplog):
    import logging

    directory = FileDirectory(tmp_path, KEY)
    _auth(directory).mkdir()  # there, and not a file that can be read
    directory.note_failure("old@example.test", "203.0.113.1", OLD)
    with caplog.at_level(logging.WARNING, logger="nm.arrive"):
        assert directory.sweep_expired(NOW)["log_lines"] == 1, "the other log is trimmed all the same"
    assert "could not be read to be trimmed (auth.log)" in caplog.text and _auth(directory).is_dir()


def test_the_trim_runs_only_with_the_lock_and_waits_for_the_next_day_when_another_holds_it(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    directory.note_failure("old@example.test", "203.0.113.1", OLD)
    held = claim(directory._sign_in_logs_lock)
    try:
        assert held is not None
        assert directory.sweep_expired(NOW)["log_lines"] == 0
        assert "old@example.test" in _attempts(directory).read_text(encoding="utf8"), "left as it was"
    finally:
        held.release()
    assert directory.sweep_expired(NOW)["log_lines"] == 1


def test_a_writer_waits_for_a_trim_in_progress_and_its_line_is_not_lost(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    held = claim(directory._sign_in_logs_lock)
    written = threading.Event()

    def write():
        directory.note_failure("during@example.test", "203.0.113.9", NOW)
        written.set()
    writer = threading.Thread(target=write)
    writer.start()
    assert not written.wait(0.3), "it waits while the lock is held"
    held.release()
    assert written.wait(10)
    writer.join(10)
    assert "during@example.test" in _attempts(directory).read_text(encoding="utf8")


def test_a_writer_that_cannot_have_the_lock_writes_all_the_same_after_a_moment(tmp_path, monkeypatch):
    """A failed attempt is never left uncounted, nor a sign-in refused, because the lock was not to be had."""
    monkeypatch.setattr(store_directory, "SIGN_IN_LOG_WAIT", 0.2)
    directory = FileDirectory(tmp_path, KEY)
    held = claim(directory._sign_in_logs_lock)
    try:
        began = time.monotonic()
        directory.note_failure("anyway@example.test", "203.0.113.4", NOW)
        directory._note("anyway@example.test", "wrong password")
        assert time.monotonic() - began >= 0.2
    finally:
        held.release()
    assert "anyway@example.test" in _attempts(directory).read_text(encoding="utf8")
    assert "anyway@example.test" in _auth(directory).read_text(encoding="utf8")


def test_the_daily_step_says_how_many_lines_went(capsys):
    from types import SimpleNamespace

    from nm.app import main
    application = SimpleNamespace(directory=SimpleNamespace(sweep_expired=lambda now: {
        "registrations": 0, "resets": 0, "sign_ins": 0, "log_lines": 7}))
    main._sweep_expired(application, NOW)
    assert "7 line(s) of the sign-in logs a year old or more were removed." in capsys.readouterr().err
