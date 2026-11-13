"""The rename that puts a saved file in its place (plan AN.50, piece 50h; D194; the review's F-36).

On Windows a rename onto a file is refused while any reader has that file open, so a save that met a reader was reported as not
made. It is now tried again for a bounded moment; a file still held after it refuses the save as before and nothing is left
behind. Elsewhere the folder is flushed after the rename, so the name a save is published under survives a power loss - that
half is exercised here with the operating system's calls stood in for, and has not been run on Linux. Offline: a temporary store
and invented matters.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from nm.shared import store_file_store
from nm.shared.store_file_store import FileMatterStore, publish
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
KEY = "publishing-rename-control-" + "k" * 24
on_windows = pytest.mark.skipif(os.name != "nt", reason="only Windows refuses a rename onto a file a reader has open")


def save(store, title, version):
    return store.commit(Matter(id="matter-1", advocate_id="adv", title=title, version=version), expected_version=version - 1)


@pytest.fixture
def store(tmp_path):
    kept = FileMatterStore(tmp_path / "store", key=KEY)
    save(kept, "First", 1)
    return kept


def reading(path, seconds):
    """A reader that has `path` open for `seconds`; returns once it has it open."""
    has_it = threading.Event()

    def hold():
        with open(path, "rb"):
            has_it.set()
            time.sleep(seconds)
    reader = threading.Thread(target=hold, daemon=True)
    reader.start()
    assert has_it.wait(10)
    return reader


@on_windows
def test_a_reader_holding_the_matter_for_a_moment_does_not_fail_its_save(store):
    reader = reading(store._matters / "matter-1.nm", 0.4)
    started = time.monotonic()
    save(store, "Second", 2)
    assert time.monotonic() - started >= 0.2, "the save met the reader and waited for it"
    reader.join(10)
    assert store.load("matter-1").title == "Second"
    assert not list(store._matters.glob("*.tmp"))


@on_windows
def test_a_matter_still_held_after_the_bound_refuses_the_save_and_leaves_what_was_saved(store, monkeypatch):
    monkeypatch.setattr(store_file_store, "_PUBLISH_WAIT", 0.2)
    reader = reading(store._matters / "matter-1.nm", 1.5)
    with pytest.raises(PermissionError):
        save(store, "Second", 2)
    reader.join(10)
    assert store.load("matter-1").title == "First", "what was saved is as it was"
    assert not list(store._matters.glob("*.tmp")), "and nothing of the refused save is left behind"
    save(store, "Second", 2)  # the same save, once the reader has let go
    assert store.load("matter-1").title == "Second"


def test_a_finished_file_replaces_the_old_one_whole(tmp_path):
    old, new = tmp_path / "kept.json", tmp_path / "kept.json.tmp"
    old.write_text("old", encoding="utf8")
    new.write_text("new", encoding="utf8")
    publish(new, old)
    assert old.read_text(encoding="utf8") == "new" and not new.exists()


def test_elsewhere_the_folder_is_flushed_after_the_rename(tmp_path, monkeypatch):
    """The operating system's calls are stood in for: Windows cannot open a folder to flush it."""
    old, new = tmp_path / "kept.json", tmp_path / "kept.json.tmp"
    old.write_text("old", encoding="utf8")
    new.write_text("new", encoding="utf8")
    calls = []
    monkeypatch.setattr(store_file_store, "_WINDOWS", False)
    monkeypatch.setattr(store_file_store.os, "open", lambda path, flags: calls.append(("open", Path(path), flags)) or 99)
    monkeypatch.setattr(store_file_store.os, "fsync", lambda fd: calls.append(("flush", fd, old.read_text(encoding="utf8"))))
    monkeypatch.setattr(store_file_store.os, "close", lambda fd: calls.append(("close", fd)))
    try:
        publish(new, old)
    finally:
        monkeypatch.undo()
    assert calls == [("open", tmp_path, os.O_RDONLY), ("flush", 99, "new"), ("close", 99)], (
        "the folder that holds the name, flushed once the new file is under it, and let go")


def test_elsewhere_a_folder_that_cannot_be_flushed_is_said_and_still_let_go(tmp_path, monkeypatch):
    old, new = tmp_path / "kept.json", tmp_path / "kept.json.tmp"
    old.write_text("old", encoding="utf8")
    new.write_text("new", encoding="utf8")
    closed = []

    def refusing(fd):
        raise OSError("the folder could not be flushed")
    monkeypatch.setattr(store_file_store, "_WINDOWS", False)
    monkeypatch.setattr(store_file_store.os, "open", lambda path, flags: 99)
    monkeypatch.setattr(store_file_store.os, "fsync", refusing)
    monkeypatch.setattr(store_file_store.os, "close", closed.append)
    try:
        with pytest.raises(OSError, match="could not be flushed"):
            publish(new, old)
    finally:
        monkeypatch.undo()
    assert closed == [99], "a save not known to be durable is not reported as made"


# ---- the reader's side (50h3) ----

@on_windows
def test_a_read_that_meets_a_save_being_put_in_place_is_tried_again_and_reads_the_matter(store, monkeypatch):
    real, refused = Path.read_bytes, []

    def meeting_the_rename(self):
        if self.suffix == ".nm" and len(refused) < 3:
            refused.append(self.name)
            raise PermissionError(13, "Permission denied")
        return real(self)
    monkeypatch.setattr(Path, "read_bytes", meeting_the_rename)
    assert store.load("matter-1").title == "First" and len(refused) == 3


@on_windows
def test_a_matter_that_stays_refused_past_the_bound_is_still_an_error_and_never_an_absent_matter(store, monkeypatch):
    monkeypatch.setattr(store_file_store, "_PUBLISH_WAIT", 0.2)

    def refused(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(Path, "read_bytes", refused)
    with pytest.raises(PermissionError):
        store.load("matter-1")


@on_windows
def test_many_reads_beside_many_saves_of_one_matter_all_read_a_whole_matter(store):
    stop, failed, read = threading.Event(), [], [0]

    def reading_it():
        while not stop.is_set():
            try:
                assert store.load("matter-1").title.startswith(("First", "Save"))
                read[0] += 1
            except Exception as exc:  # noqa: BLE001 - reported below
                failed.append(repr(exc))
    readers = [threading.Thread(target=reading_it) for _ in range(3)]
    for each in readers:
        each.start()
    try:
        for version in range(2, 42):
            save(store, f"Save {version}", version)
    finally:
        stop.set()
        for each in readers:
            each.join(30)
    assert not failed and read[0] > 40, failed[:3]
