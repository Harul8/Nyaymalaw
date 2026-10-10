"""Exact statute readback binds one held Act and provision, never legal currency.

These fixtures use the production passage-store columns. They need neither
embedding/reranking weights nor a provider: a named-source read is mechanical.
"""
from copy import deepcopy
import json
import sqlite3

import pytest

from nm.core_engine.retrieval import DIMENSIONS, EMBED_MODEL, LocalCollection


class _NoModels:
    def __getattr__(self, name):
        raise AssertionError(f"Exact provision readback must not load a model: {name}")


def _row(act_id, key, text="A duty applies, except where the stated exception applies.",
         *, chunk_id=None, parent=""):
    return {
        "doc_type": "bare_act", "act_id": act_id, "act_name": f"Held {act_id}",
        "chunk_id": chunk_id or f"{act_id}:{key}", "section_number": key,
        "section_title": "Duty and exception", "full_text": text,
        "parent_chunk_id": parent, "atom_type": "section_head", "year": "2026",
    }


def _local(tmp_path, rows, *, indexed=None):
    indexed = indexed or {}
    database = tmp_path / "chunks.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table chunks (doc_type text not null, pos integer not null, "
            "chunk_id text not null, act_id text, case_id text, parent_chunk_id text, "
            "atom_type text, section_number text, blob text not null, "
            "primary key (doc_type, pos))"
        )
        for position, row in enumerate(rows):
            columns = {
                "doc_type": row["doc_type"], "chunk_id": row["chunk_id"],
                "act_id": row["act_id"], "case_id": None,
                "parent_chunk_id": row.get("parent_chunk_id") or None,
                "atom_type": row["atom_type"], "section_number": row["section_number"],
                **indexed.get(position, {}),
            }
            connection.execute(
                "insert into chunks values (?,?,?,?,?,?,?,?,?)",
                (columns["doc_type"], position, columns["chunk_id"], columns["act_id"],
                 columns["case_id"], columns["parent_chunk_id"], columns["atom_type"],
                 columns["section_number"], json.dumps(row)),
            )
    connection.close()
    lineage = tmp_path / "lineage.json"
    lineage.write_text(json.dumps({
        "schema": 1, "doc_type": "bare_act", "model": EMBED_MODEL,
        "dimensions": DIMENSIONS, "passages": len(rows),
        "vector_index": {"path": "not-needed.index"},
        "bm25": {"path": "not-needed-bm25"},
        "passage_store": {"path": "chunks.db"},
    }), encoding="utf-8")
    return LocalCollection(corpus_dir=tmp_path, lineage=lineage, doc_type="bare_act",
                           models=_NoModels())


@pytest.mark.parametrize("key,reference", [
    ("4", "section 4"),
    ("Article_4", "Article 4"),
    ("Order_IX_Rule_4", "Order IX Rule 4"),
])
def test_found_source_preserves_exact_words_owned_key_and_unassessed_legal_version(
    tmp_path, key, reference,
):
    text = "  First condition.\n" + "A qualification remains. " * 100 + "\nFinal exception.  "
    original = _row("act-a", key, text)
    collection = _local(tmp_path, [original, _row("act-b", key, "Different Act words.")])

    result = collection.read_provision("act-a", reference)

    assert result["state"] == "found"
    assert result["act_id"] == "act-a" and result["reference"] == reference
    assert result["provision_key"] == key and result["candidates"] == [key]
    assert result["legal_version"] == "not_assessed"
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["text"] == text and source["source"] == original
    assert source["corpus_revision"] and source["content_digest"]
    assert source["legal_status"] == "candidate_unassessed"


def test_a_section_in_another_act_is_not_a_match_or_a_neighbour_fallback(tmp_path):
    collection = _local(tmp_path, [_row("act-a", "3"), _row("act-b", "4")])

    result = collection.read_provision("act-a", "section 4")

    assert result["state"] == "not_held" and result["act_id"] == "act-a"
    assert result["provision_key"] is None
    assert result["sources"] == [] and result["candidates"] == []
    assert result["legal_version"] == "not_assessed" and result["reason"]


def test_equivalent_held_keys_remain_ambiguous_instead_of_picking_first(tmp_path):
    collection = _local(tmp_path, [_row("act-a", "4"), _row("act-a", "Section_4")])

    result = collection.read_provision("act-a", "section 4")

    assert result["state"] == "ambiguous"
    assert result["provision_key"] is None and result["sources"] == []
    assert set(result["candidates"]) == {"4", "Section_4"}
    assert result["legal_version"] == "not_assessed" and result["reason"]


@pytest.mark.parametrize("column,value", [
    ("act_id", "different-act"),
    ("section_number", "different-section"),
    ("parent_chunk_id", "different-parent"),
])
def test_indexed_identity_mismatch_never_admits_the_blob_and_preserves_valid_peers(
    tmp_path, column, value,
):
    invalid, valid = _row("act-a", "4"), _row("act-b", "9")
    collection = _local(tmp_path, [invalid, valid], indexed={0: {column: value}})

    assert collection.read([0, 1]) == {1: valid}


def test_unavailable_passage_store_is_not_reported_as_a_missing_provision(tmp_path):
    collection = _local(tmp_path, [_row("act-a", "4")])
    (tmp_path / "chunks.db").unlink()

    result = collection.read_provision("act-a", "section 4")

    assert result["state"] == "unavailable"
    assert result["sources"] == [] and result["provision_key"] is None
    assert result["legal_version"] == "not_assessed" and result["reason"]


def test_an_unread_segment_cannot_make_the_section_look_completely_read(tmp_path):
    parent = _row("act-a", "4", chunk_id="section-root")
    child = _row("act-a", "4", "", chunk_id="section-exception", parent="section-root")
    collection = _local(tmp_path, [parent, child])

    result = collection.read_provision("act-a", "section 4")

    assert result["state"] == "unavailable"
    assert result["sources"] == [] and result["reason"]
    assert result["legal_version"] == "not_assessed"


def test_a_foreign_parent_cannot_supply_a_selected_provisions_context(tmp_path):
    child = _row("act-a", "4", chunk_id="child", parent="parent")
    foreign = _row("act-b", "4", chunk_id="parent")
    collection = _local(tmp_path, [child, foreign])

    result = collection.read_provision("act-a", "section 4")

    assert result["state"] == "unavailable"
    assert result["sources"] == [] and result["reason"]


def test_source_change_during_readback_releases_no_snapshot(tmp_path, monkeypatch):
    original = _row("act-a", "4")
    collection = _local(tmp_path, [original])
    read = collection.read
    changed = False

    def change_after_read(positions):
        nonlocal changed
        result = read(positions)
        if not changed:
            changed = True
            replacement = deepcopy(original)
            replacement["full_text"] = "Different source text after readback."
            with sqlite3.connect(tmp_path / "chunks.db") as connection:
                connection.execute("update chunks set blob=? where doc_type=? and pos=0",
                                   (json.dumps(replacement), "bare_act"))
        return result

    monkeypatch.setattr(collection, "read", change_after_read)

    result = collection.read_provision("act-a", "section 4")

    assert changed
    assert result["state"] == "unavailable"
    assert result["sources"] == [] and result["reason"]
