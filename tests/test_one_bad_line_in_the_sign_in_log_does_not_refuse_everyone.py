"""One bad line in the sign-in limiter's log does not refuse sign-in for everyone (plan AN.53, 53c1, D218; the
review's F-28).

The limiter reads its log of failed attempts on every sign-in. One line it could not read - a line cut short when
the server stopped, a stray byte - made the whole log unreadable, and an unreadable limiter refuses every sign-in
until someone mends the file by hand. A line that cannot be read is now skipped and counted; the lines that can be
read still limit; a line is always begun on a line of its own; and a log that cannot be opened at all is still 'the
limiter cannot run'.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive import attempts_contracts as attempts
from nm.arrive.store_directory import FileDirectory

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
WHO, WHERE = "advocate@example.test", "203.0.113.7"
SINCE = NOW - attempts.WINDOW


def _directory(root):
    return FileDirectory(root, key="limiter-log-control-" + "k" * 24)


def _fail(directory, times, who=WHO, where=WHERE):
    for minutes in range(times):
        directory.note_failure(who, where, NOW - timedelta(minutes=minutes + 1))


@pytest.mark.parametrize("bad", [
    b"not a line of the log\n",
    b"2026-11-13T11:58:00+00:00\tonly-two-fields\n",
    b"2026-11-13T11:58:00\tadvocate@example.test\t203.0.113.7\n",   # a time with no offset cannot be placed
    b"not-a-time\tadvocate@example.test\t203.0.113.7\n",
    b"2026-11-13T11:58:00+00:00\t\xff\xfe\x80\t203.0.113.7\textra\n",  # bytes that are no text
    b"\n",
], ids=["words", "two fields", "no offset", "no time", "not text", "empty line"])
def test_a_line_that_cannot_be_read_is_skipped_and_counted_and_the_rest_still_count(tmp_path, bad):
    directory = _directory(tmp_path)
    _fail(directory, 2)
    with (tmp_path / "attempts.log").open("ab") as log:
        log.write(bad)
    _fail(directory, 1)
    counts = directory.failures_since(WHO, WHERE, SINCE)
    assert counts is not None, "one bad line must not stop the limiter for everyone"
    assert len(counts[0]) == 3 and len(counts[1]) == 3
    assert directory.skipped_attempt_lines() == 1
    assert directory.limiter_available()


def test_the_limit_still_holds_beside_a_bad_line(tmp_path):
    directory = _directory(tmp_path)
    _fail(directory, attempts.PER_ADVOCATE)
    with (tmp_path / "attempts.log").open("ab") as log:
        log.write(b"\x00\x00 a torn write\n")
    mine, here = directory.failures_since(WHO, WHERE, SINCE)
    assert not attempts.verdict(mine, here, NOW).allowed
    other = directory.failures_since("someone-else@example.test", "198.51.100.9", SINCE)
    assert attempts.verdict(*other, NOW).allowed, "and nobody else is paused by it"


def test_a_line_cut_short_does_not_swallow_the_next_failure(tmp_path):
    directory = _directory(tmp_path)
    _fail(directory, 1)
    with (tmp_path / "attempts.log").open("ab") as log:
        log.write(b"2026-11-13T11:5")  # the server stopped mid-line: no end of line
    _fail(directory, 1)
    mine, _here = directory.failures_since(WHO, WHERE, SINCE)
    assert len(mine) == 2, "the failure written after the cut line is on a line of its own, and counts"
    assert directory.skipped_attempt_lines() == 1


def test_a_clean_log_skips_nothing_and_an_absent_one_is_empty(tmp_path):
    directory = _directory(tmp_path)
    assert directory.failures_since(WHO, WHERE, SINCE) == ((), ()) and directory.skipped_attempt_lines() == 0
    _fail(directory, 3)
    assert directory.skipped_attempt_lines() == 0
    assert (tmp_path / "attempts.log").read_text(encoding="utf8").count("\n") == 3, "one line a failure, as before"


def test_a_log_that_cannot_be_opened_is_still_the_limiter_cannot_run(tmp_path):
    directory = _directory(tmp_path)
    (tmp_path / "attempts.log").mkdir()
    assert directory.failures_since(WHO, WHERE, SINCE) is None
    assert directory.skipped_attempt_lines() is None
    assert not directory.limiter_available()


def test_the_operator_is_told_once_of_lines_skipped_and_never_what_they_held(tmp_path, caplog):
    import logging
    directory = _directory(tmp_path)
    with (tmp_path / "attempts.log").open("ab") as log:
        log.write(b"secret-looking words that are no line\n")
    with caplog.at_level(logging.WARNING, logger="nm.arrive"):
        for _ in range(3):
            directory.failures_since(WHO, WHERE, SINCE)
    said = [record.getMessage() for record in caplog.records]
    assert len(said) == 1 and "1" in said[0] and "secret-looking" not in said[0]


# ----- the count on the Admin diagnostics (plan AN.53, 53c4): the operator sees it on a page, not only in the server's log -----

def test_the_admin_checks_count_the_skipped_lines_by_the_directorys_own_rule(tmp_path):
    from nm.arrive.admin_checks import AdminChecks
    directory = _directory(tmp_path)
    checks = AdminChecks(storage=tmp_path, root=tmp_path, settings={})
    assert checks.limiter_log() == {"lines_skipped": 0}, "no log yet: nothing skipped"
    _fail(directory, 2)
    with (tmp_path / "attempts.log").open("ab") as log:
        log.write(b"not a line of the log\n2026-11-13T11:58:00\tno-offset@example.test\t203.0.113.7\n")
    assert checks.limiter_log() == {"lines_skipped": 2} and directory.skipped_attempt_lines() == 2, "one rule, read by both"


def test_the_admin_checks_say_a_limiter_log_that_cannot_be_opened_as_not_readable(tmp_path):
    from nm.arrive.admin_checks import AdminChecks
    (tmp_path / "attempts.log").mkdir()
    assert AdminChecks(storage=tmp_path, root=tmp_path, settings={}).limiter_log() is None


@pytest.mark.parametrize("skipped, state", [({"lines_skipped": 0}, "ok"), ({"lines_skipped": 3}, "attention"), (None, "unavailable")])
def test_the_diagnostics_show_the_skipped_lines_and_call_for_attention(skipped, state):
    from tests.test_the_diagnostics_say_what_is_well_from_counts_and_sizes_and_never_from_anyones_work import Checks, view
    shown = view(Checks(limiter_log=skipped))
    check, = [c for c in shown["checks"] if c["id"] == "limiter_log"]
    assert check["state"] == state and check["facts"] == (skipped or {})
