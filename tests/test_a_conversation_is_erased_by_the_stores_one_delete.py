"""A conversation is erased by the store's one delete, its own key destroyed first (plan AN.53, D241's first piece).

Nothing in NM could delete anything (D223; the review's F-35). D241, the owner's policy, sets what an advocate may delete and
the order to build it in; this is the first piece: the store's one delete. It erases a conversation and every record the store
keeps of it - the conversation itself, its turns' records, its ratings, its line in the history, the record of its last save
and of its owner. ITS OWN KEY IS DESTROYED FIRST, so that whatever is left of it anywhere - a copy, a backup, a file that could
not be removed - cannot be read. It erases only the advocate's own: another's conversation is not there for them. Nothing asks
for it yet (the mark, Put back and the 30-day sweep, and the route and the page, are the next pieces).

Offline: a store in a temporary folder; no model call.
"""
from __future__ import annotations

import json
import shutil

import pytest

from nm.shared.store_envelope import KeyUnavailable
from nm.shared.store_file_store import ErasureRefused, FileMatterStore, _enc
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

KEY = "erasure-control-" + "k" * 32
OWNER, OTHER = "owner@example.test", "other@example.test"


def _store(root):
    return FileMatterStore(root, key=KEY)


def _saved(store, matter_id="m_one", advocate=OWNER):
    saved = store.commit(Matter(id=matter_id, advocate_id=advocate, title="Erase me", version=1), expected_version=0)
    store.keep_line(matter_id, store.signature(matter_id), {"owner": advocate, "chat": {"chat_id": "c", "preview": "words"}})
    store.record_turn({"matter_id": matter_id, "turn_id": "turn-1", "at": "2026-11-14T09:00:00", "words": "privileged"})
    store.record_feedback({"matter_id": matter_id, "turn_id": "turn-1", "rating": "up"})
    return saved


def _files(root, matter_id):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and matter_id in str(p.relative_to(root)))


def test_every_record_the_store_keeps_of_the_conversation_is_erased_and_another_conversation_is_untouched(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    _saved(store, "m_two")
    two_before = _files(tmp_path, "m_two")
    assert len(_files(tmp_path, "m_one")) >= 6, _files(tmp_path, "m_one")
    receipt = store.erase("m_one", OWNER)
    assert receipt["key_destroyed"] is True and receipt["left"] == []
    assert [name for name in _files(tmp_path, "m_one") if not name.endswith(".lock")] == [], "nothing of it is left"
    assert store.load("m_one") is None and store.transcripts_for("m_one") == () and store.feedback_for("m_one") == ()
    assert [entry[0] for entry in store.saved_files()] == ["m_two"]
    assert _files(tmp_path, "m_two") == two_before and store.load("m_two").title == "Erase me"


def test_its_own_key_is_destroyed_first_so_a_copy_kept_anywhere_cannot_be_read(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    kept = tmp_path / "a-backup"
    shutil.copytree(tmp_path / "matters", kept)
    store.erase("m_one", OWNER)
    shutil.copy(kept / "m_one.nm", tmp_path / "matters" / "m_one.nm")  # the copy put back
    with pytest.raises(KeyUnavailable):
        _store(tmp_path).load("m_one")


def test_the_key_goes_before_any_file_and_a_key_that_cannot_be_destroyed_erases_nothing(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _saved(store)
    order = []
    destroying = store._sealer.destroy
    monkeypatch.setattr(store._sealer, "destroy", lambda matter_id: (order.append("key"), destroying(matter_id))[1])
    removing = store._remove
    monkeypatch.setattr(store, "_remove", lambda path: (order.append("file"), removing(path))[1])
    store.erase("m_one", OWNER)
    assert order[0] == "key" and set(order[1:]) == {"file"}

    other = _store(tmp_path / "second")
    _saved(other)

    def refuse(matter_id):
        raise PermissionError("the key's folder refuses")
    monkeypatch.setattr(other._sealer, "destroy", refuse)
    before = _files(tmp_path / "second", "m_one")
    with pytest.raises(PermissionError):
        other.erase("m_one", OWNER)
    assert _files(tmp_path / "second", "m_one") == before, "with the key still there, nothing was removed"


def test_another_advocates_conversation_is_not_there_for_them_and_nothing_changes(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    before = _files(tmp_path, "m_one")
    assert store.erase("m_one", OTHER) is None
    assert _files(tmp_path, "m_one") == before and store.load("m_one").title == "Erase me"


def test_an_owners_conversation_that_cannot_be_opened_is_erased_by_its_owner(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    (tmp_path / "matters" / "m_one.nm").write_bytes(b"damaged beyond reading")
    receipt = store.erase("m_one", OWNER)
    assert receipt["key_destroyed"] is True
    assert [name for name in _files(tmp_path, "m_one") if not name.endswith(".lock")] == []


def test_a_damaged_conversation_nobody_is_recorded_as_owning_is_refused(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    (tmp_path / "matter-owners" / "m_one.json").unlink()
    (tmp_path / "matters" / "m_one.nm").write_bytes(b"damaged beyond reading")
    with pytest.raises(ErasureRefused):
        _store(tmp_path).erase("m_one", OWNER)
    assert (tmp_path / "keys" / "m_one.key").exists(), "nothing was destroyed on a guess"


def test_what_is_not_there_is_not_erased(tmp_path):
    assert _store(tmp_path).erase("m_absent", OWNER) is None


def test_a_save_that_expected_the_erased_conversation_is_refused_and_does_not_bring_it_back(tmp_path):
    store = _store(tmp_path)
    saved = _saved(store)
    store.erase("m_one", OWNER)
    with pytest.raises(StaleWrite):
        store.commit(Matter(id="m_one", advocate_id=OWNER, title="Brought back?", version=2), expected_version=saved.version)
    assert store.load("m_one") is None


def test_a_conversation_from_before_there_were_keys_of_its_own_is_erased_and_says_it_had_none(tmp_path):
    store = _store(tmp_path)
    old = Matter(id="m_old", advocate_id=OWNER, title="Old", version=1)
    (tmp_path / "matters" / "m_old.nm").write_bytes(store._cipher.encrypt(json.dumps(_enc(old)).encode("utf8")))
    receipt = store.erase("m_old", OWNER)
    assert receipt["key_destroyed"] is False and receipt["own_key"] is False
    assert store.load("m_old") is None


def test_the_store_port_declares_the_one_delete_so_the_policed_wrapper_gates_it():
    from nm.shared.policed_port_adapter import port_methods
    from nm.shared.store_port import StorePort
    assert "erase" in port_methods(StorePort)
