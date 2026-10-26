"""The first use of a new turn-attempt store is safe when callers arrive together (plan AN.24; owner decision O30).

It was made the way the usage store was - the file first, its tables afterwards - so a second caller could find a file that
exists and is empty and refuse it as a lost store. It is made whole before anyone can find it now; a store that exists and is
empty or damaged is still refused and left alone, and a refusal says what kind of fault it was, and no more.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from contextlib import closing

import pytest

from nm.shared.turn_attempt_port import AttemptRefused
from nm.shared.turn_attempt_store import FileTurnAttempts

pytestmark = pytest.mark.class_a

REQUEST = hashlib.sha256(b"a request").hexdigest()


def identity(number):
    return hashlib.sha256(f"owner/chat/turn-{number}".encode()).hexdigest()


def together(path, callers=4):
    """`callers` first uses of the store at `path`, at the same moment, each claiming a turn of its own; returns how many
    were refused for the store's sake (a claim refused as busy or in conflict is the store working)."""
    refused, barrier = [], threading.Barrier(callers)

    def first_use(number):
        barrier.wait()
        try:
            FileTurnAttempts(path).claim(identity(number), REQUEST)
        except AttemptRefused as exc:
            if exc.code == "storage":
                refused.append(True)

    pool = [threading.Thread(target=first_use, args=(n,)) for n in range(callers)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()
    return len(refused)


def test_four_first_uses_arriving_together_are_none_of_them_refused(tmp_path):
    refused = sum(together(tmp_path / f"attempts{round_number}.sqlite3") for round_number in range(150))
    assert refused == 0, f"{refused} of 600 first uses were refused"


def test_every_claim_made_at_the_first_use_is_kept(tmp_path):
    path = tmp_path / "attempts.sqlite3"
    assert together(path, callers=6) == 0
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM turn_attempts").fetchone()[0] == 6


@pytest.mark.parametrize("content", [b"", b"damaged database"])
def test_a_file_that_exists_and_is_empty_or_damaged_is_still_refused_and_never_filled(tmp_path, content):
    path = tmp_path / "attempts.sqlite3"
    path.write_bytes(content)
    with pytest.raises(AttemptRefused) as caught:
        FileTurnAttempts(path)
    assert caught.value.code == "storage" and path.read_bytes() == content


def test_a_new_store_is_made_whole_and_no_temporary_file_is_left(tmp_path):
    path = tmp_path / "attempts.sqlite3"
    FileTurnAttempts(path)
    assert [p.name for p in tmp_path.iterdir()] == ["attempts.sqlite3"]


def test_a_store_that_holds_something_it_did_not_make_says_so_without_naming_it(tmp_path, caplog):
    path = tmp_path / "client name Privileged words" / "attempts.sqlite3"
    path.parent.mkdir()
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE turn_attempts (note TEXT)")
    with caplog.at_level(logging.WARNING, logger="nm.attempts"):
        with pytest.raises(AttemptRefused):
            FileTurnAttempts(path)
    assert "did not make" in caplog.text
    assert "Privileged" not in caplog.text and str(tmp_path) not in caplog.text


def test_a_call_the_store_cannot_make_says_the_kind_of_fault(tmp_path, caplog):
    store = FileTurnAttempts(tmp_path / "attempts.sqlite3")
    (tmp_path / "attempts.sqlite3").unlink()      # a store lost after it was opened is not remade
    with caplog.at_level(logging.WARNING, logger="nm.attempts"):
        with pytest.raises(AttemptRefused):
            store.claim(identity(0), REQUEST)
    assert "OperationalError" in caplog.text and str(tmp_path) not in caplog.text


def test_an_ordinary_refusal_is_not_logged_as_a_fault(tmp_path, caplog):
    store = FileTurnAttempts(tmp_path / "attempts.sqlite3")
    store.claim(identity(0), REQUEST)
    with caplog.at_level(logging.WARNING, logger="nm.attempts"):
        with pytest.raises(AttemptRefused) as caught:
            store.claim(identity(0), REQUEST)
    assert caught.value.code == "busy" and caplog.text == ""


def test_a_store_that_cannot_be_opened_says_the_kind_of_fault_and_not_the_path(tmp_path, caplog):
    folder = tmp_path / "client name Privileged words"
    folder.mkdir()          # a folder where the store should be: the system, not the store, is what refuses
    with caplog.at_level(logging.WARNING, logger="nm.attempts"):
        with pytest.raises(AttemptRefused) as caught:
            FileTurnAttempts(folder)
    assert caught.value.code == "storage"
    assert "OperationalError" in caplog.text
    assert "Privileged" not in caplog.text and str(tmp_path) not in caplog.text
