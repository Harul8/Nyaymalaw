"""Lineage regeneration retains contextual sources without inventing vectors."""
import hashlib
import json
import sqlite3

import pytest

from pipeline import record_retrieval_lineage as job

pytestmark = pytest.mark.class_a


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "VECTOR_STORE", tmp_path / "corpus")
    monkeypatch.setattr(job, "LINEAGE", tmp_path / "lineage")
    job.VECTOR_STORE.mkdir()
    job.LINEAGE.mkdir()
    return job.COLLECTIONS["bare_acts"]


def test_new_lineage_binds_existing_parent_artifact_with_no_vector_claim(tmp_path, monkeypatch):
    collection = setup(tmp_path, monkeypatch)
    data = b'{"source":{"full_text":"exact original words"}}'
    (job.VECTOR_STORE / collection.context_store).write_bytes(data)
    assert job.context_store(collection) == {"path": collection.context_store,
        "format": "parent_map_v1", "sha256": hashlib.sha256(data).hexdigest()}
    assert not collection.out.exists()


def test_regeneration_preserves_the_declared_store_path_and_updates_its_hash(tmp_path, monkeypatch):
    collection = setup(tmp_path, monkeypatch)
    declaration = {"path": "versioned-parents.json", "format": "parent_map_v1", "sha256": "0" * 64}
    collection.out.write_text(json.dumps({"context_store": declaration}), encoding="utf-8")
    data = b'{"root":"new controlled generation"}'
    (job.VECTOR_STORE / declaration["path"]).write_bytes(data)
    assert job.context_store(collection) == {**declaration, "sha256": hashlib.sha256(data).hexdigest()}


def test_missing_declared_store_is_not_silently_removed(tmp_path, monkeypatch):
    collection = setup(tmp_path, monkeypatch)
    original = json.dumps({"context_store": {"path": "missing.json", "format": "parent_map_v1", "sha256": "0" * 64}})
    collection.out.write_text(original, encoding="utf-8")
    assert job.record_one(collection, samples=1, check=False) == 1
    assert collection.out.read_text(encoding="utf-8") == original


def test_collection_without_a_context_store_remains_supported(tmp_path, monkeypatch):
    collection = setup(tmp_path, monkeypatch)
    assert job.context_store(collection) is None
    assert job.context_store(job.COLLECTIONS["judgments"]) is None


@pytest.mark.parametrize("declaration", [
    {"path": "../another-owner.json", "format": "parent_map_v1"},
    {"path": "parents.json", "format": "unknown"},
    {"path": "", "format": "parent_map_v1"},
])
def test_unknown_or_foreign_context_declaration_is_rejected(tmp_path, monkeypatch, declaration):
    collection = setup(tmp_path, monkeypatch)
    collection.out.write_text(json.dumps({"context_store": declaration}), encoding="utf-8")
    with pytest.raises(ValueError):
        job.context_store(collection)


@pytest.mark.parametrize("check,mutate", [(False, False), (True, False), (False, True)])
def test_record_writer_carries_context_identity_and_refuses_mid_run_changes(tmp_path, monkeypatch, check, mutate):
    collection = setup(tmp_path, monkeypatch)
    parent = job.VECTOR_STORE / collection.context_store
    parent.write_bytes(b'{"root":"original"}')
    expected = job.context_store(collection)
    (job.VECTOR_STORE / collection.index).write_bytes(b"synthetic-index")
    folder = job.VECTOR_STORE / collection.bm25
    folder.mkdir()
    (folder / "params.index.json").write_text('{"num_docs":1}', encoding="utf-8")
    with sqlite3.connect(job.VECTOR_STORE / job.STORE) as db:
        db.execute("create table chunks (doc_type text, pos integer)")
        db.execute("insert into chunks values ('bare_act',0)")
    monkeypatch.setattr(job, "faiss_header", lambda _: (None, job.DIMENSIONS, 1))
    def vectors(*args):
        if mutate:
            parent.write_bytes(b'{"root":"changed"}')
        return {"same_vector":1,"sampled":1,"cut_at":[512],"lowest_similarity":1,
                "mean_similarity":1,"device":"synthetic"}
    monkeypatch.setattr(job, "verify_vectors", vectors)
    monkeypatch.setattr(job, "verify_words", lambda *args: {"own_position":1,"sampled":1,"no_indexed_words":0})
    monkeypatch.setattr(job, "check_lineage", lambda *args, **kwargs: [])
    assert job.record_one(collection, samples=1, check=check) == (1 if mutate else 0)
    assert collection.out.exists() is (not check and not mutate)
    if collection.out.exists():
        saved = json.loads(collection.out.read_text(encoding="utf-8"))
        assert saved["context_store"] == expected
        assert saved["passages"] == saved["vector_index"]["vectors"] == 1
