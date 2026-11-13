"""The store knows whose each saved matter is (plan AN.53, 53b, D217; the review's F-21).

Whose a saved file is was known only by opening it, so the history opened or read a line for every advocate's
file, and one that could not be opened - whoever's it was - was named to every advocate and marked every
advocate's history as partial. The store now keeps, beside each matter, a small record of its owner (a hash, no
address), written with the save. A listing for one advocate leaves out every file recorded as another's without
opening it; a load for one advocate gives nothing of another's matter; and a file that cannot be opened is said
only to the advocate it is recorded as belonging to.
"""
from __future__ import annotations

import json

import pytest

from nm.shared.store_file_store import FileMatterStore, _enc
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

FIRST, SECOND = "first@example.test", "second@example.test"


def _store(root):
    return FileMatterStore(root, key="owner-record-control-" + "k" * 24)


def _saved(store, matter_id, advocate_id):
    return store.commit(Matter(id=matter_id, advocate_id=advocate_id, title="Owner control", version=1),
                        expected_version=0)


def _legacy(store, root, matter_id, advocate_id):
    """A matter saved before there were owner records: its file, and nothing beside it."""
    saved = Matter(id=matter_id, advocate_id=advocate_id, title="Old matter", version=1)
    (root / "matters" / f"{matter_id}.nm").write_bytes(store._cipher.encrypt(json.dumps(_enc(saved)).encode("utf8")))
    return saved


def _corrupt(root, matter_id):
    (root / "matters" / f"{matter_id}.nm").write_bytes(b"not a saved matter")


def _ids(entries):
    return [entry[0] for entry in entries]


def test_a_listing_for_one_advocate_holds_only_what_is_recorded_as_theirs(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    _saved(store, "m_second", SECOND)
    mine = store.saved_files_for(SECOND)
    assert _ids(mine) == ["m_second"]
    assert mine[0][1] == store.signature("m_second") and mine[0][3] is True, "its signature, and known to be theirs"
    assert _ids(store.saved_files_for(FIRST)) == ["m_first"]
    assert _ids(store.saved_files()) == ["m_first", "m_second"], "the whole store's listing is as it was"


def test_anothers_file_that_cannot_be_opened_is_not_in_ones_listing_and_is_in_its_owners(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    _saved(store, "m_second", SECOND)
    _corrupt(tmp_path, "m_first")
    assert _ids(store.saved_files_for(SECOND)) == ["m_second"]
    assert _ids(store.saved_files_for(FIRST)) == ["m_first"], "its owner is still told of it"
    second, first = store.list_for(SECOND), store.list_for(FIRST)
    assert [m.id for m in second.matters] == ["m_second"] and second.complete, "the second's history is whole"
    assert first.unreadable == ("m_first",) and not first.complete, "and the first's says which file"


def test_a_fresh_store_object_reads_the_records_from_disk(tmp_path):
    _saved(_store(tmp_path), "m_first", FIRST)
    again = _store(tmp_path)
    assert _ids(again.saved_files_for(FIRST)) == ["m_first"] and again.saved_files_for(SECOND) == ()


def test_the_owner_record_holds_no_address(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    record = (tmp_path / "matter-owners" / "m_first.json").read_bytes()
    assert FIRST.encode() not in record and b"example" not in record
    assert [p.name for p in (tmp_path / "matter-owners").iterdir()] == ["m_first.json"], "no temporary file is left"


def test_a_matter_with_no_owner_record_is_offered_as_not_known_and_recorded_once_it_is_read(tmp_path):
    store = _store(tmp_path)
    _legacy(store, tmp_path, "m_old", FIRST)
    for advocate in (FIRST, SECOND):
        (entry,) = store.saved_files_for(advocate)
        assert entry[0] == "m_old" and entry[3] is None, "not known: the caller opens it to learn whose it is"
    assert store.load("m_old").advocate_id == FIRST
    assert _ids(store.saved_files_for(FIRST)) == ["m_old"] and store.saved_files_for(FIRST)[0][3] is True
    assert store.saved_files_for(SECOND) == (), "once read, it is recorded and no longer offered to another"


def test_an_unreadable_matter_nobody_is_recorded_as_owning_is_named_to_no_advocate(tmp_path):
    store = _store(tmp_path)
    _legacy(store, tmp_path, "m_old", FIRST)
    _corrupt(tmp_path, "m_old")
    for advocate in (FIRST, SECOND):
        listed = store.list_for(advocate)
        assert listed.matters == () and listed.unreadable == (), "it cannot be said to be theirs, so it is not said"
    assert store.unowned_unreadable() == ("m_old",), "and it does not vanish: the operator's side can count it"


def test_an_owner_record_that_cannot_be_read_is_not_known_and_the_next_read_mends_it(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    (tmp_path / "matter-owners" / "m_first.json").write_text("{not json", encoding="utf8")
    fresh = _store(tmp_path)
    assert fresh.saved_files_for(SECOND)[0][3] is None
    fresh.load("m_first")
    assert fresh.saved_files_for(SECOND) == ()


def test_a_load_for_an_advocate_gives_nothing_of_anothers_matter(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    assert store.load_for("m_first", FIRST).id == "m_first"
    assert store.load_for("m_first", SECOND) is None
    assert store.load_for("m_absent", FIRST) is None
    _legacy(store, tmp_path, "m_old", FIRST)
    assert store.load_for("m_old", SECOND) is None, "with no record, the file itself says whose it is"


def test_anothers_matter_that_cannot_be_opened_is_simply_not_there_for_one_and_fails_for_its_owner(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_first", FIRST)
    _corrupt(tmp_path, "m_first")
    assert store.load_for("m_first", SECOND) is None, "never an error that says another's file exists and is damaged"
    with pytest.raises(Exception):
        store.load_for("m_first", FIRST)


def test_a_later_save_keeps_the_record_and_a_record_that_cannot_be_written_never_fails_a_save(tmp_path, monkeypatch):
    from dataclasses import replace
    store = _store(tmp_path)
    saved = _saved(store, "m_first", FIRST)
    record = tmp_path / "matter-owners" / "m_first.json"
    before = (record.read_bytes(), record.stat().st_mtime_ns)
    store.commit(replace(saved, title="Changed", version=2), expected_version=1)
    assert (record.read_bytes(), record.stat().st_mtime_ns) == before, "written once; a later save does not write it again"

    other = _store(tmp_path / "other")
    monkeypatch.setattr(other, "_owner_path", lambda matter_id: tmp_path / "other" / "matters" / "m_x.nm" / "no.json")
    assert _saved(other, "m_x", FIRST).id == "m_x", "the save happened; its owner record is derived again on a read"
    assert other.saved_files_for(SECOND)[0][3] is None
