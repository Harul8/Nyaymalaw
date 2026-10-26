"""The conversation history's line for each saved file is kept sealed beside the file (plan AN.23; owner decisions
P35, O29).

Whose a saved file is, and what the history shows of it, is known only by opening it, and a long conversation is
tens of megabytes. The store keeps one small line per file, for the version of the file it was derived from (its
write time and size), sealed as the matter is. A line that is missing, stale, damaged or for another matter is no
line, never an error; a matter whose key has been erased gets no line under the installation seal.
"""
from __future__ import annotations

import json

import pytest

from nm.shared import store_file_store
from nm.shared.store_envelope import KeyUnavailable
from nm.shared.store_file_store import FileMatterStore, _enc
from nm.shared.store_sealing import is_envelope
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

WORDS = "Privileged first message about the cheque"
LINE = {"owner": "owner@example.test", "chat": {"chat_id": "c1", "preview": WORDS, "turn_count": 2}}


def _store(root):
    return FileMatterStore(root, key="kept-line-control-" + "k" * 24)


def _saved(store, matter_id="m_line"):
    return store.commit(Matter(id=matter_id, advocate_id="owner@example.test", title="Line control", version=1),
                        expected_version=0)


def _legacy(store, root, matter_id="m_old"):
    """A matter saved before there were keys of their own: sealed by the installation seal alone."""
    saved = Matter(id=matter_id, advocate_id="owner@example.test", title="Old matter", version=1)
    (root / "matters").mkdir(parents=True, exist_ok=True)
    (root / "matters" / f"{matter_id}.nm").write_bytes(
        store._cipher.encrypt(json.dumps(_enc(saved)).encode("utf8")))
    return saved


def test_a_kept_line_is_read_back_for_the_version_it_was_kept_for(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    assert store.kept_line("m_line", signature) is None, "nothing is kept until it is kept"
    store.keep_line("m_line", signature, LINE)
    assert store.kept_line("m_line", signature) == LINE


def test_a_line_kept_for_one_version_is_not_given_for_the_next(tmp_path):
    store = _store(tmp_path)
    saved = _saved(store)
    first = store.signature("m_line")
    store.keep_line("m_line", first, LINE)
    from dataclasses import replace
    store.commit(replace(saved, title="Changed title, so a different file"), expected_version=saved.version)
    second = store.signature("m_line")
    assert second != first
    assert store.kept_line("m_line", second) is None, "a changed file's old line must never be shown"


def test_a_kept_line_is_sealed_under_the_matters_own_key_and_holds_no_words_in_the_clear(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    store.keep_line("m_line", store.signature("m_line"), LINE)
    blob = (tmp_path / "history-lines" / "m_line.nm").read_bytes()
    assert is_envelope(blob) and b'"matter_id": "m_line"' in blob
    for clear in (WORDS.encode(), b"owner@example.test", b"preview", b"turn_count"):
        assert clear not in blob, clear
    assert [p.name for p in (tmp_path / "history-lines").iterdir()] == ["m_line.nm"], "no temporary file is left"


def test_a_line_is_kept_beside_the_file_and_leaves_the_file_alone(tmp_path):
    store = _store(tmp_path)
    saved = _saved(store)
    before = (store.signature("m_line"), (tmp_path / "matters" / "m_line.nm").read_bytes())
    store.keep_line("m_line", before[0], LINE)
    assert (store.signature("m_line"), (tmp_path / "matters" / "m_line.nm").read_bytes()) == before
    assert store.load("m_line") == saved
    assert not list((tmp_path / "matters").glob("*.tmp"))


def test_a_matter_saved_before_keys_got_a_line_sealed_as_its_file_is_and_no_key_is_made(tmp_path):
    store = _store(tmp_path)
    _legacy(store, tmp_path)
    signature = store.signature("m_old")
    store.keep_line("m_old", signature, {"owner": "owner@example.test", "matter": {"matter": "Old matter"}})
    assert store.kept_line("m_old", signature) == {"owner": "owner@example.test", "matter": {"matter": "Old matter"}}
    assert not is_envelope((tmp_path / "history-lines" / "m_old.nm").read_bytes())
    assert not (tmp_path / "keys" / "m_old.key").exists(), "keeping a line must never mint a key"
    assert store.signature("m_old") == signature


def test_an_erased_matter_gets_no_line_under_the_installation_seal(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    (tmp_path / "keys" / "m_line.key").unlink()   # this test's own controlled key: the matter is erased
    with pytest.raises(KeyUnavailable):
        store.keep_line("m_line", signature, LINE)
    assert not (tmp_path / "history-lines").exists() or not list((tmp_path / "history-lines").iterdir())
    assert store.kept_line("m_line", signature) is None


def test_a_line_kept_before_the_matter_was_erased_can_no_longer_be_opened(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    store.keep_line("m_line", signature, LINE)
    (tmp_path / "keys" / "m_line.key").unlink()
    assert store.kept_line("m_line", signature) is None


@pytest.mark.parametrize("damage", ["garbage", "empty", "another matter's line", "another format", "not a mapping"])
def test_a_line_that_will_not_open_or_is_not_what_it_should_be_is_no_line(tmp_path, damage, monkeypatch):
    store = _store(tmp_path)
    _saved(store)
    _saved(store, "m_other")
    signature = store.signature("m_line")
    store.keep_line("m_line", signature, LINE)
    store.keep_line("m_other", store.signature("m_other"), {"owner": "owner@example.test", "chat": None})
    path = tmp_path / "history-lines" / "m_line.nm"
    if damage == "garbage":
        path.write_bytes(b"{ not a sealed record")
    elif damage == "empty":
        path.write_bytes(b"")
    elif damage == "another matter's line":
        path.write_bytes((tmp_path / "history-lines" / "m_other.nm").read_bytes())
    elif damage == "another format":
        monkeypatch.setattr(store_file_store, "_LINE_FORMAT", 2)
    else:
        path.write_bytes(store._seal("m_line", json.dumps(["not", "a", "mapping"]).encode()))
    assert store.kept_line("m_line", signature) is None


def test_a_record_that_is_not_for_this_file_or_this_version_is_no_line(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    for wrong in ({"format": 1, "matter_id": "m_other", "signature": list(signature), "line": LINE},
                  {"format": 1, "matter_id": "m_line", "signature": [signature[0], signature[1] + 1], "line": LINE},
                  {"format": 1, "matter_id": "m_line", "signature": list(signature), "line": "text"},
                  {"format": 1, "matter_id": "m_line", "signature": list(signature)}):
        (tmp_path / "history-lines").mkdir(exist_ok=True)
        (tmp_path / "history-lines" / "m_line.nm").write_bytes(store._seal("m_line", json.dumps(wrong).encode()))
        assert store.kept_line("m_line", signature) is None, wrong


def test_a_line_kept_again_replaces_the_old_one_whole(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    store.keep_line("m_line", signature, LINE)
    newer = {**LINE, "chat": {**LINE["chat"], "turn_count": 3}}
    store.keep_line("m_line", signature, newer)
    assert store.kept_line("m_line", signature) == newer
    assert [p.name for p in (tmp_path / "history-lines").iterdir()] == ["m_line.nm"]


@pytest.mark.parametrize("bad", ["../outside", "..\\outside", "/absolute", "other*", "has space", ""])
def test_a_line_is_named_by_an_opaque_identifier_never_a_path(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.kept_line(bad, (1, 1))
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.keep_line(bad, (1, 1), LINE)
    assert not (tmp_path / "history-lines").exists()


def test_a_write_that_fails_says_so_and_leaves_no_temporary_file_and_the_old_line(tmp_path, monkeypatch):
    """The caller does not fail a request over a line that could not be kept, so it has to be told."""
    store = _store(tmp_path)
    _saved(store)
    signature = store.signature("m_line")
    store.keep_line("m_line", signature, LINE)

    def refused(*_args, **_kwargs):
        raise PermissionError("the line is being read just now")

    monkeypatch.setattr(store_file_store.os, "replace", refused)
    with pytest.raises(PermissionError):
        store.keep_line("m_line", signature, {**LINE, "owner": "someone-else@example.test"})
    monkeypatch.undo()
    assert [p.name for p in (tmp_path / "history-lines").iterdir()] == ["m_line.nm"], "a temporary file was left"
    assert store.kept_line("m_line", signature) == LINE, "the old line must survive a failed replacement"
