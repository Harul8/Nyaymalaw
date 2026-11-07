"""The Admin record: an audit that only grows and shows a change made to it, and the password check an admin's changes rest on
(plan AN.46, piece 46c; owner decisions D116 and D126, 7 Nov 2026). Synthetic admins, accounts and reasons."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive.admin_port import AdminUnavailable, AuditEntry
from nm.arrive.store_admin import _SQL, CONFIRMATION_MINUTES, READ_LIMIT, FileAdminRecord

pytestmark = pytest.mark.class_a

START = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
SESSION = "a" * 64


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def entry(**over):
    given = dict(at=START, actor="admin@example.test", action="allowance.add", target="advocate@example.test",
                 reason="Development account", outcome="done")
    given.update(over)
    return AuditEntry(**given)


@pytest.fixture
def record(tmp_path):
    return FileAdminRecord(tmp_path / "admin.sqlite", clock=Clock())


def raw(record):
    return closing(sqlite3.connect(record.path))


def tamper(record, *statements):
    """What someone with the file would do: take the triggers away, change the rows, put the triggers back exactly."""
    with raw(record) as db, db:
        db.execute("DROP TRIGGER audit_is_never_changed")
        db.execute("DROP TRIGGER audit_is_never_removed")
        for statement in statements:
            db.execute(statement)
        db.execute(_SQL[("trigger", "audit_is_never_changed")])
        db.execute(_SQL[("trigger", "audit_is_never_removed")])


def test_entries_are_numbered_from_one_and_each_fingerprint_includes_the_one_before(record):
    first, second = record.append(entry()), record.append(entry(action="session.end", target="b@example.test"))
    assert (first.id, second.id) == (1, 2)
    assert first.fingerprint != second.fingerprint and len(first.fingerprint) == 64
    assert first.at == START + timedelta(minutes=1) and second.at == START + timedelta(minutes=2)  # the store's own clock
    check = record.verify()
    assert check.ok and check.entries == 2 and check.first_bad_id is None and check.newest == second.fingerprint


def test_an_empty_record_is_a_whole_chain_with_nothing_to_compare(record):
    check = record.verify()
    assert check.ok and check.entries == 0 and check.newest == ""
    assert record.entries() == ()


def test_the_file_itself_refuses_to_change_or_remove_an_entry(record):
    record.append(entry())
    with raw(record) as db:
        with pytest.raises(sqlite3.DatabaseError, match="only grows"):
            db.execute("UPDATE audit SET reason='something else'")
        with pytest.raises(sqlite3.DatabaseError, match="only grows"):
            db.execute("DELETE FROM audit")
    assert record.verify().ok and len(record.entries()) == 1


def test_an_entry_changed_by_someone_with_the_file_is_shown_by_the_check(record):
    for number in range(4):
        record.append(entry(target=f"person{number}@example.test"))
    tamper(record, "UPDATE audit SET reason='quietly changed' WHERE id=3")
    check = record.verify()
    assert not check.ok and check.first_bad_id == 3 and check.entries == 4


def test_an_entry_removed_from_the_middle_is_shown_and_one_cut_from_the_end_is_not_so_the_newest_fingerprint_is_to_be_kept(record):
    kept = [record.append(entry(target=f"person{number}@example.test")) for number in range(4)]
    tamper(record, "DELETE FROM audit WHERE id=2")
    assert not record.verify().ok
    tamper(record, "DELETE FROM audit WHERE id IN (3, 4)")
    # Cutting the end leaves a chain that still follows: only the fingerprint written down elsewhere shows it.
    after = record.verify()
    assert after.entries == 1 and after.newest != kept[-1].fingerprint


def test_a_file_whose_guards_were_taken_away_and_not_put_back_is_refused_outright(record):
    record.append(entry())
    with raw(record) as db, db:
        db.execute("DROP TRIGGER audit_is_never_changed")
    for use in (record.verify, lambda: record.append(entry()), record.entries):
        with pytest.raises(AdminUnavailable):
            use()


def test_nothing_that_is_not_one_line_of_names_and_a_short_reason_is_accepted(record):
    for bad in (entry(reason="x" * 201), entry(reason="line one\nline two"), entry(actor=" "), entry(target=""),
                entry(action="Allowance Add"), entry(action="1st"), entry(outcome="DONE"), entry(outcome=""),
                entry(reason="tab\there"), "not an entry"):
        with pytest.raises(ValueError):
            record.append(bad)
    assert record.entries() == () and record.verify().entries == 0
    assert record.append(entry(reason="x" * 200)).reason == "x" * 200
    assert record.append(entry(reason="")).reason == ""


def test_entries_are_read_newest_first_in_pages_and_a_read_is_capped(record):
    for number in range(7):
        record.append(entry(target=f"person{number}@example.test"))
    page = record.entries(limit=3)
    assert [e.id for e in page] == [7, 6, 5]
    assert [e.id for e in record.entries(limit=3, before_id=5)] == [4, 3, 2]
    assert [e.id for e in record.entries(limit=50, before_id=3)] == [2, 1]
    assert len(record.entries(limit=10**6)) == 7 and READ_LIMIT == 500
    for bad in (0, -1, "3", 2.5):
        with pytest.raises(ValueError):
            record.entries(limit=bad)


def test_entries_made_together_are_all_kept_in_one_unbroken_chain(record):
    barrier = threading.Barrier(6)

    def writer(number):
        barrier.wait()
        for turn in range(4):
            record.append(entry(target=f"w{number}-{turn}@example.test"))

    threads = [threading.Thread(target=writer, args=(number,)) for number in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check = record.verify()
    assert check.ok and check.entries == 24
    assert sorted(e.id for e in record.entries(limit=100)) == list(range(1, 25))


def test_a_password_check_covers_ten_minutes_for_that_session_only(record):
    assert CONFIRMATION_MINUTES == 10
    assert not record.password_confirmed(SESSION, START)
    until = record.confirm_password(SESSION, START)
    assert until == START + timedelta(minutes=10)
    assert record.password_confirmed(SESSION, START + timedelta(minutes=9, seconds=59))
    assert not record.password_confirmed(SESSION, START + timedelta(minutes=10))
    assert not record.password_confirmed("b" * 64, START + timedelta(minutes=1))
    assert not record.password_confirmed("not a session", START)
    assert not record.password_confirmed(None, START)
    with pytest.raises(ValueError):
        record.confirm_password("not a session", START)


def test_a_second_check_extends_the_first_and_a_lapsed_one_is_cleared_with_the_next(record):
    record.confirm_password(SESSION, START)
    record.confirm_password("c" * 64, START)
    later = START + timedelta(minutes=30)
    record.confirm_password(SESSION, later)
    with raw(record) as db:
        assert [row[0] for row in db.execute("SELECT session FROM confirmations")] == [SESSION]
    assert record.password_confirmed(SESSION, later + timedelta(minutes=5))


def test_the_record_holds_no_password_and_no_session_text_beyond_the_session_s_own_fingerprint(record):
    record.confirm_password(SESSION, START)
    with raw(record) as db:
        columns = {row[1] for table in ("audit", "confirmations") for row in db.execute(f"PRAGMA table_info({table})")}
    assert columns.isdisjoint({"password", "token", "secret", "message", "matter", "document", "answer"})


def test_a_file_made_by_something_else_is_refused_and_a_lost_file_is_never_started_again_from_nothing(tmp_path):
    foreign = tmp_path / "foreign.sqlite"
    with closing(sqlite3.connect(foreign)) as db, db:
        db.execute("CREATE TABLE audit (id INTEGER, what TEXT)")
    with pytest.raises(AdminUnavailable):
        FileAdminRecord(foreign)
    empty = tmp_path / "empty.sqlite"
    empty.write_bytes(b"")
    with pytest.raises(AdminUnavailable):
        FileAdminRecord(empty)
    made = FileAdminRecord(tmp_path / "made.sqlite")
    made.path.unlink()
    with pytest.raises(AdminUnavailable):
        made.append(entry())
    assert not made.path.exists()
