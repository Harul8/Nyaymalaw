"""A provision's parts are found by its Act and section, and one exact readback checks the
corpus snapshot once (20 Oct 2026: each lookup walked every stored Act passage, and each
readback checked the snapshot at every read)."""
import sqlite3

import pytest

from nm.core_engine import retrieval
from tests.test_core_statute_readback import _local, _row

pytestmark = pytest.mark.class_a

#: The held Acts store's own secondary indexes (acts_v4.db, 20 Oct 2026).
STORE_INDEXES = ("create index idx_chunks_chunk_id on chunks(chunk_id)",
                 "create index idx_chunks_doc_act on chunks(doc_type, act_id, section_number)",
                 "create index idx_chunks_doc_parent on chunks(doc_type, parent_chunk_id)")


def _tree(tmp_path):
    originals = [_row("act-a", "4", "Main rule.", chunk_id="root"),
                 _row("act-a", "4", "Exception.", chunk_id="child", parent="root"),
                 _row("act-a", "4", "Exception to exception.", chunk_id="grandchild", parent="child"),
                 _row("act-b", "4", "Another Act's section 4.", chunk_id="other")]
    collection = _local(tmp_path, originals)
    with sqlite3.connect(tmp_path / "chunks.db") as connection:
        for statement in STORE_INDEXES:
            connection.execute(statement)
    connection.close()
    return collection, originals


def _recorded(monkeypatch):
    statements, connect = [], sqlite3.connect

    class Recording(sqlite3.Connection):
        def execute(self, sql, *args):
            statements.append(sql)
            return super().execute(sql, *args)
    monkeypatch.setattr(retrieval.sqlite3, "connect", lambda *a, **k: connect(*a, factory=Recording, **k))
    return statements


def test_a_provisions_parts_are_found_through_its_act_and_section_index(tmp_path, monkeypatch):
    collection, originals = _tree(tmp_path)
    statements = _recorded(monkeypatch)
    assert collection.read_provision("act-a", "section 4")["state"] == "found"
    context = collection.context(0, collection.read([0])[0])
    assert [segment["position"] for segment in context["segments"]] == [0, 1, 2]
    lookups = [sql for sql in statements if "section_number=?" in sql]
    assert lookups and set(lookups) == {retrieval.SECTION_PARTS}
    with sqlite3.connect(tmp_path / "chunks.db") as connection:
        plan = " ".join(str(step[-1]) for step in connection.execute(
            "explain query plan " + retrieval.SECTION_PARTS, ("bare_act", "act-a", "4", 501)))
        parts = [row[0] for row in connection.execute(retrieval.SECTION_PARTS, ("bare_act", "act-a", "4", 501))]
    connection.close()
    assert "idx_chunks_doc_act" in plan and "autoindex" not in plan
    assert parts == [0, 1, 2]  # the same parts in stored order


def _counted(collection, *, changes=False):
    collection._open()
    revisions, calls = [collection._revision, *(["changed"] if changes else [])], []

    def revision():
        calls.append(1)
        return revisions[min(len(calls), len(revisions)) - 1]
    collection.revision = revision
    return calls


def test_one_readback_checks_the_snapshot_on_first_use_and_at_its_end(tmp_path):
    collection, _ = _tree(tmp_path)
    calls = _counted(collection)
    result = collection.read_provision("act-a", "section 4")
    assert result["state"] == "found" and len(result["sources"]) == 3
    assert len(calls) == 2


def test_a_corpus_change_during_a_readback_leaves_it_unavailable(tmp_path):
    collection, _ = _tree(tmp_path)
    _counted(collection, changes=True)
    result = collection.read_provision("act-a", "section 4")
    assert result["state"] == "unavailable" and result["sources"] == []
    assert "corpus changed" in result["reason"]


def test_a_readback_inside_a_search_keeps_that_searchs_check(tmp_path):
    collection, _ = _tree(tmp_path)
    calls = _counted(collection)
    with collection.snapshot_scope():
        assert collection.read_provision("act-a", "section 4")["state"] == "found"
        assert collection._scope.active is True
    assert len(calls) == 2


def test_a_part_is_found_through_its_own_identity_index(tmp_path, monkeypatch):
    """20 Oct 2026 (P32): reading sections whole walks each part to its root; each step found
    its part by walking the whole Act's passages, 3.5 ms a step in the CPC."""
    collection, _ = _tree(tmp_path)
    statements = _recorded(monkeypatch)
    tree = collection.rank_context(2, collection.read([2])[2])
    assert [segment["position"] for segment in tree["segments"]] == [0, 1, 2]
    lookups = [sql for sql in statements if "chunk_id=?" in sql]
    assert lookups and set(lookups) == {retrieval.PART_BY_ID}
    with sqlite3.connect(tmp_path / "chunks.db") as connection:
        plan = " ".join(str(step[-1]) for step in connection.execute(
            "explain query plan " + retrieval.PART_BY_ID, ("bare_act", "act-a", "grandchild")))
    connection.close()
    assert "idx_chunks_chunk_id" in plan
