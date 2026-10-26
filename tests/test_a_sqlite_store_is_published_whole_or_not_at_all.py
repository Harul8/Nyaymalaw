"""A SQLite store file is published whole or not at all (plan AN.24; owner decision O30).

Nobody, at any moment, can find an empty or half-made file where a store is meant to be: it is made complete beside the
path and linked into place only if none exists yet. This is the mechanism the usage store and the turn-attempt store use.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

import pytest

from nm.shared import sqlite_creation
from nm.shared.sqlite_creation import create_if_absent, why

pytestmark = pytest.mark.class_a


def build(db):
    db.execute("CREATE TABLE things (id INTEGER PRIMARY KEY, note TEXT)")
    db.execute("PRAGMA user_version=7")


def tables(path):
    with closing(sqlite3.connect(path)) as db:
        return [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")], db.execute(
            "PRAGMA user_version").fetchone()[0]


def test_a_new_store_is_made_complete_and_nothing_else_is_left(tmp_path):
    path = tmp_path / "nested" / "store.sqlite"
    create_if_absent(path, build)
    assert tables(path) == (["things"], 7)
    assert [p.name for p in path.parent.iterdir()] == ["store.sqlite"], "no temporary file is left"


def test_a_store_that_is_there_is_left_exactly_as_it_is_and_is_not_built_again(tmp_path):
    path = tmp_path / "store.sqlite"
    path.write_bytes(b"")
    called = []
    create_if_absent(path, lambda db: called.append(True))
    assert called == [] and path.read_bytes() == b"", "an empty file that exists is the store's to refuse, not ours to fill"
    other = tmp_path / "other.sqlite"
    create_if_absent(other, build)
    before = other.read_bytes()
    create_if_absent(other, lambda db: called.append(True))
    assert called == [] and other.read_bytes() == before


def test_a_build_that_fails_leaves_nothing_where_the_store_is_meant_to_be_and_nothing_beside_it(tmp_path):
    path = tmp_path / "store.sqlite"

    def failing(db):
        db.execute("CREATE TABLE half (id INTEGER)")
        raise RuntimeError("the build went wrong")

    with pytest.raises(RuntimeError):
        create_if_absent(path, failing)
    assert list(tmp_path.iterdir()) == []
    create_if_absent(path, build)
    assert tables(path) == (["things"], 7), "a later caller can still make it"


def test_a_creator_that_loses_the_race_uses_the_winners_store_and_removes_its_own_copy(tmp_path, monkeypatch):
    path = tmp_path / "store.sqlite"
    winner_built = []

    def winner(db):
        winner_built.append(True)
        db.execute("CREATE TABLE winners (id INTEGER)")
        db.execute("PRAGMA user_version=1")

    real_link = sqlite_creation.os.link

    def link_after_a_rival_published(source, target):
        monkeypatch.setattr(sqlite_creation.os, "link", real_link)  # the rival, and then this caller, link for real
        create_if_absent(target, winner)  # the rival publishes between this caller's build and its link
        return real_link(source, target)

    monkeypatch.setattr(sqlite_creation.os, "link", link_after_a_rival_published)
    create_if_absent(path, build)
    assert winner_built == [True]
    assert tables(path) == (["winners"], 1), "the store is the winner's, whole"
    assert [p.name for p in tmp_path.iterdir()] == ["store.sqlite"], "the loser's copy is removed"


def test_nobody_ever_finds_an_empty_or_half_made_file_where_the_store_is_meant_to_be(tmp_path):
    """Several creators, slow builds and an observer that looks as often as it can: each file it can open is complete."""
    seen_empty, seen_complete = [], []
    for round_number in range(25):
        path = tmp_path / f"store{round_number}.sqlite"
        done = threading.Event()

        def slow(db):
            db.execute("CREATE TABLE things (id INTEGER PRIMARY KEY)")
            time.sleep(0.01)
            db.execute("PRAGMA user_version=3")

        def observe():
            while not done.is_set():
                if path.exists():
                    with closing(sqlite3.connect(path)) as db:
                        found = db.execute("SELECT name FROM sqlite_master").fetchall()
                        version = db.execute("PRAGMA user_version").fetchone()[0]
                    (seen_complete if found and version == 3 else seen_empty).append(round_number)

        watcher = threading.Thread(target=observe)
        watcher.start()
        creators = [threading.Thread(target=create_if_absent, args=(path, slow)) for _ in range(4)]
        for creator in creators:
            creator.start()
        for creator in creators:
            creator.join()
        done.set()
        watcher.join()
    assert seen_empty == [], f"an empty or half-made store was visible in rounds {sorted(set(seen_empty))}"
    assert seen_complete, "the observer never saw a store at all, so it proved nothing"


def test_the_observer_can_see_the_defect_it_guards_against(tmp_path):
    """The positive control: made the old way - the file first, its tables afterwards - the same observer sees it empty."""
    path = tmp_path / "old-way.sqlite"
    seen = []
    done = threading.Event()

    def observe():
        while not done.is_set():
            if path.exists():
                with closing(sqlite3.connect(path)) as db:
                    seen.append(bool(db.execute("SELECT name FROM sqlite_master").fetchall()))

    watcher = threading.Thread(target=observe)
    watcher.start()
    with closing(sqlite3.connect(path)) as db, db:     # the old way: the file exists from here ...
        db.execute("PRAGMA synchronous=FULL")
        time.sleep(0.05)
        db.execute("BEGIN IMMEDIATE")
        build(db)                                        # ... and has its tables only from here
    time.sleep(0.02)
    done.set()
    watcher.join()
    assert False in seen, "an observer that cannot see the old defect cannot show it fixed"


def test_why_says_the_kind_of_fault_and_never_its_message():
    locked = sqlite3.OperationalError("database is locked: C:/private/matters/client.sqlite")
    locked.sqlite_errorname = "SQLITE_BUSY"
    denied = PermissionError(13, "Permission denied", "C:/private/client name/usage.sqlite")
    assert why(locked) == "OperationalError SQLITE_BUSY"
    assert why(denied) == "PermissionError errno 13"
    assert why(ValueError("the usage store has a schema it did not make; Privileged words")) == "ValueError"
    for text in (why(locked), why(denied), why(ValueError("Privileged words"))):
        assert "private" not in text and "Privileged" not in text and "client" not in text
