"""The first use of a new usage store is safe when callers arrive together (plan AN.24; owner decision O30).

Measured on 26 Oct 2026: when four first uses of a store that did not exist yet arrived together, 12 of 600 callers were refused
("the usage store has a schema it did not make") - one had created the file, another found it empty and took it for a lost
store. It surfaced as a 503 "usage could not be checked" on the first turn of a new store about once in ten test runs. A store
that exists and is empty or foreign is still refused; the refusal now says what kind of fault it was, and no more.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import closing

import pytest

from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import TRIAL_MICRO_USD, UsageRefused

pytestmark = pytest.mark.class_a

ADVOCATE = "advocate@example.test"


def together(path, callers=4):
    """`callers` first uses of the store at `path`, started at the same moment; returns how many were refused."""
    refused, barrier = [], threading.Barrier(callers)

    def first_use():
        barrier.wait()
        try:
            FileUsage(path).standing(ADVOCATE)
        except UsageRefused:
            refused.append(True)

    pool = [threading.Thread(target=first_use) for _ in range(callers)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()
    return len(refused)


def test_four_first_uses_arriving_together_are_none_of_them_refused(tmp_path):
    refused = sum(together(tmp_path / f"usage{round_number}.sqlite") for round_number in range(150))
    assert refused == 0, f"{refused} of 600 first uses were refused (12 of 600 before the fix)"


def test_the_trial_is_given_once_however_many_callers_make_the_first_use(tmp_path):
    path = tmp_path / "usage.sqlite"
    assert together(path, callers=6) == 0
    assert FileUsage(path).standing(ADVOCATE)["granted"] == TRIAL_MICRO_USD, "a second trial was given"


def test_a_file_that_exists_and_is_empty_is_still_refused_and_never_filled(tmp_path):
    path = tmp_path / "usage.sqlite"
    path.write_bytes(b"")
    with pytest.raises(UsageRefused):
        FileUsage(path)
    assert path.read_bytes() == b"", "a lost or emptied store must not be quietly started again"


def test_a_file_that_is_not_a_store_is_still_refused_and_left_alone(tmp_path):
    path = tmp_path / "usage.sqlite"
    path.write_bytes(b"damaged database")
    with pytest.raises(UsageRefused):
        FileUsage(path)
    assert path.read_bytes() == b"damaged database"


def test_a_new_store_is_made_whole_and_no_temporary_file_is_left(tmp_path):
    path = tmp_path / "usage.sqlite"
    FileUsage(path)
    assert [p.name for p in tmp_path.iterdir()] == ["usage.sqlite"]
    with closing(sqlite3.connect(path)) as db:
        assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"grants", "calls", "notices"}


def test_a_refusal_says_the_kind_of_fault_and_nothing_a_log_must_not_hold(tmp_path, caplog):
    path = tmp_path / "client name Privileged words" / "usage.sqlite"
    path.parent.mkdir()
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE calls (account TEXT)")
    with caplog.at_level(logging.WARNING, logger="nm.usage"):
        with pytest.raises(UsageRefused):
            FileUsage(path)
    assert "ValueError" in caplog.text
    assert "Privileged" not in caplog.text and "schema it did not make" not in caplog.text and str(tmp_path) not in caplog.text


def test_a_call_the_store_refuses_says_the_kind_of_fault_too(tmp_path, caplog):
    usage = FileUsage(tmp_path / "usage.sqlite")
    (tmp_path / "usage.sqlite").unlink()          # a store that was lost after it was opened is not remade
    with caplog.at_level(logging.WARNING, logger="nm.usage"):
        with pytest.raises(UsageRefused):
            usage.standing(ADVOCATE)
    assert "OperationalError" in caplog.text and str(tmp_path) not in caplog.text
