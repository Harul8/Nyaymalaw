"""A saved file that will not open is said in the store's own words (plan AN.53, 53j1; D225 - found beside its first item).

The store has one error for a stored record that cannot be read (StoredObjectUnreadable). A file sealed under its matter's own
key raised it; a file that is not such an envelope - an empty file, one overwritten, one sealed the earlier way and damaged -
is opened by the installation's cipher, and what that library raises escaped as it was. No caller names a cipher library's
error, so the same damage was one error or another by how the file happened to be damaged. Every file that will not open now
raises the store's own error, with the cipher's as its cause.
"""
from __future__ import annotations

import json

import pytest

from nm.shared.storage_errors_port import StoredObjectUnreadable
from nm.shared.store_file_store import FileMatterStore, _enc
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
WHO = "unreadable@example.test"


def _store(root):
    return FileMatterStore(root, key="unreadable-control-" + "k" * 24)


def _saved(store, matter_id="m_one"):
    store.commit(Matter(id=matter_id, advocate_id=WHO, title="Unreadable control", version=1), expected_version=0)
    return store._matters / f"{matter_id}.nm"


DAMAGE = {
    "overwritten with other bytes": lambda blob: b"not a saved matter, and longer than the file was",
    "emptied": lambda blob: b"",
    "cut short": lambda blob: blob[: len(blob) // 2],
    "one byte of the earlier sealing changed": None,
}


@pytest.mark.parametrize("how", sorted(DAMAGE))
def test_a_file_that_will_not_open_raises_the_stores_own_error_however_it_was_damaged(tmp_path, how):
    store = _store(tmp_path)
    path = _saved(store)
    if DAMAGE[how] is None:   # a matter sealed the earlier way, by the installation's cipher alone, with one byte changed
        sealed = bytearray(store._cipher.encrypt(json.dumps(_enc(store.load("m_one"))).encode("utf8")))
        sealed[len(sealed) // 2] ^= 1
        path.write_bytes(bytes(sealed))
    else:
        path.write_bytes(DAMAGE[how](path.read_bytes()))
    with pytest.raises(StoredObjectUnreadable) as said:
        store.load("m_one")
    assert said.value.__cause__ is not None or "unreadable" in str(said.value), "what the cipher said is kept as the cause"
    with pytest.raises(StoredObjectUnreadable):
        store.load_for("m_one", WHO)


def test_a_matter_sealed_the_earlier_way_and_whole_still_opens(tmp_path):
    store = _store(tmp_path)
    earlier = Matter(id="m_earlier", advocate_id=WHO, title="Sealed the earlier way", version=1)
    (store._matters / "m_earlier.nm").write_bytes(store._cipher.encrypt(json.dumps(_enc(earlier)).encode("utf8")))
    assert store.load("m_earlier").title == "Sealed the earlier way"


def test_a_file_that_opens_and_is_not_a_matter_is_still_a_value_error(tmp_path):
    """What opens and then does not read as a saved matter was a ValueError and stays one: it is not the cipher's refusal."""
    store = _store(tmp_path)
    (store._matters / "m_words.nm").write_bytes(store._cipher.encrypt(b"these are words, not a saved matter"))
    with pytest.raises(ValueError):
        store.load("m_words")
