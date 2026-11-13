"""An older copy of a matter put in its place is noticed (plan AN.50, piece 50e; D191; the review's F-13).

The only evidence of which save a matter file is was the version number inside it, so an older copy put back in its place - by
a restore of some files and not others, a copying tool, a hand - loaded cleanly as the current conversation and accepted new
saves on top. Each save now leaves a small record beside the matter, inside the save's own lock: the version saved and a hash of
what was saved. A file below its record is refused: not loaded, not saved over, and listed as one that could not be read. A
matter with no record, or ahead of it, loads as before. Offline: a temporary store and invented matters.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace

import pytest

from nm.shared import store_file_store
from nm.shared.store_file_store import FileMatterStore, RolledBack
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
KEY = "older-copy-control-" + "k" * 24


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path / "store", key=KEY)


def save(store, title, version):
    """One more save of the one matter, at `version`."""
    return store.commit(Matter(id="matter-1", advocate_id="adv", title=title, version=version), expected_version=version - 1)


def the_file(store):
    return store._matters / "matter-1.nm"


def the_record(store):
    return store._root / store_file_store._SAVED / "matter-1.json"


def test_an_older_copy_put_back_is_not_loaded_not_saved_over_and_listed_as_unreadable(store, tmp_path):
    save(store, "First", 1)
    shutil.copy2(the_file(store), tmp_path / "older.nm")
    second = save(store, "Second", 2)
    shutil.copy2(tmp_path / "older.nm", the_file(store))  # the older copy, put back in its place

    with pytest.raises(RolledBack, match="last saved at version 2 and the file in its place is version 1"):
        store.load("matter-1")
    with pytest.raises(RolledBack):
        store.commit(replace(second, title="On top of the older copy", version=2), expected_version=1)
    listed = store.list_for("adv")
    assert listed.matters == () and listed.unreadable == ("matter-1",), "it does not vanish and is not shown as current"
    # A fresh process on the same folder says the same: the record is on disk, not in memory.
    with pytest.raises(RolledBack):
        FileMatterStore(store._root, key=KEY).load("matter-1")


def test_another_file_at_the_saved_version_is_refused_too(store, tmp_path):
    save(store, "First", 1)
    shutil.copy2(the_file(store), tmp_path / "other.nm")
    store.commit(Matter(id="matter-1", advocate_id="adv", title="Saved over it", version=1), expected_version=1)
    shutil.copy2(tmp_path / "other.nm", the_file(store))
    with pytest.raises(RolledBack, match="is not the file that was saved"):
        store.load("matter-1")


def test_the_saved_file_loads_and_each_save_moves_the_record_on(store):
    save(store, "First", 1)
    assert json.loads(the_record(store).read_text(encoding="utf8"))["version"] == 1
    save(store, "Second", 2)
    assert json.loads(the_record(store).read_text(encoding="utf8"))["version"] == 2
    assert store.load("matter-1").title == "Second"
    assert [m.title for m in store.list_for("adv")] == ["Second"]
    assert not list(the_record(store).parent.glob("*.tmp")), "no half-written record is left"


def test_the_record_holds_no_word_of_the_matter(store):
    save(store, "A title the advocate typed", 1)
    record = the_record(store).read_text(encoding="utf8")
    assert set(json.loads(record)) == {"format", "version", "sha256"} and "advocate" not in record


def test_a_matter_saved_before_there_were_records_loads_and_its_next_save_writes_one(store):
    save(store, "First", 1)
    the_record(store).unlink()  # as a matter saved by the code before this piece is
    assert store.load("matter-1").title == "First"
    save(store, "Second", 2)
    assert json.loads(the_record(store).read_text(encoding="utf8"))["version"] == 2


def test_a_file_ahead_of_its_record_loads_and_the_next_save_mends_the_record(store, tmp_path):
    """A save whose record was not written: the process ended between the two, or code from before the records saved it."""
    save(store, "First", 1)
    shutil.copy2(the_record(store), tmp_path / "earlier.json")
    save(store, "Second", 2)
    shutil.copy2(tmp_path / "earlier.json", the_record(store))
    assert store.load("matter-1").title == "Second"
    save(store, "Third", 3)
    assert json.loads(the_record(store).read_text(encoding="utf8"))["version"] == 3


@pytest.mark.parametrize("damaged", ["", "not json", "[1, 2]", '{"format": 99, "version": 9, "sha256": "x"}',
                                     '{"format": 1, "version": "9", "sha256": "x"}'])
def test_a_record_that_cannot_be_read_does_not_make_the_matter_unreadable(store, damaged):
    save(store, "First", 1)
    the_record(store).write_text(damaged, encoding="utf8")
    assert store.load("matter-1").title == "First", "not assessed, and it loads as it did"
    save(store, "Second", 2)
    assert json.loads(the_record(store).read_text(encoding="utf8")) == {
        "format": 1, "version": 2, "sha256": json.loads(the_record(store).read_text(encoding="utf8"))["sha256"]}


def test_a_record_that_could_not_be_written_does_not_fail_the_save_that_happened(store, monkeypatch):
    save(store, "First", 1)
    real = os.replace

    def refusing(source, target):
        if os.fspath(target).endswith(".json"):
            raise PermissionError("the record's folder refuses the write")
        return real(source, target)
    monkeypatch.setattr(store_file_store.os, "replace", refusing)
    save(store, "Second", 2)  # the matter is saved; only its record was refused
    monkeypatch.undo()
    assert store.load("matter-1").title == "Second", "ahead of its record, which is never a rollback"
    assert not list(the_record(store).parent.glob("*.tmp"))
    save(store, "Third", 3)
    assert json.loads(the_record(store).read_text(encoding="utf8"))["version"] == 3


def test_the_same_matter_sealed_again_is_still_the_file_that_was_saved(store):
    """The key rotation seals again what the installation's secret sealed whole (50d): the record is of what was saved, not of
    its sealed bytes, so a matter sealed again still loads."""
    save(store, "First", 1)
    before = the_file(store).read_bytes()
    the_file(store).write_bytes(store._seal("matter-1", store._open("matter-1", before)))
    assert the_file(store).read_bytes() != before, "sealed again: other bytes"
    assert store.load("matter-1").title == "First"


def test_a_matter_removed_and_begun_again_is_not_taken_for_an_older_copy(store):
    save(store, "First", 1)
    save(store, "Second", 2)
    the_file(store).unlink()
    assert store.load("matter-1") is None
    save(store, "Begun again", 1)
    assert store.load("matter-1").title == "Begun again"
