"""The startup warm-up loads what a first search would wait for, exactly once."""
import hashlib
import json
import threading
import time
from types import SimpleNamespace

import pytest

from nm.core_engine import retrieval

pytestmark = pytest.mark.class_a


def collection(tmp_path, **changes):
    return retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
                                     doc_type="bare_act", models=changes.pop("models", None), **changes)


def test_warm_loads_indices_hidden_copies_models_and_probes_once(tmp_path, monkeypatch):
    calls = []
    item = collection(tmp_path, models=SimpleNamespace(load=lambda: calls.append("models")),
                      copies=tmp_path / "copies.json")
    for name in ("_open", "_word_index", "_vector_index", "suppressed_positions"):
        monkeypatch.setattr(item, name, lambda name=name: calls.append(name))
    monkeypatch.setattr(item, "semantic_many", lambda queries, depth: calls.append(("probe", depth)) or [[]])
    monkeypatch.setattr(item, "rerank", lambda pairs, **kwargs: calls.append(("score", len(pairs))) or [0.0])
    item.warm()
    assert calls == ["_open", "_word_index", "_vector_index", "suppressed_positions", "models",
                     ("probe", 1), ("score", 1)]


def test_collection_without_a_copy_register_skips_hidden_positions(tmp_path, monkeypatch):
    calls = []
    item = collection(tmp_path, models=SimpleNamespace(load=lambda: None))
    for name in ("_open", "_word_index", "_vector_index", "suppressed_positions"):
        monkeypatch.setattr(item, name, lambda name=name: calls.append(name))
    monkeypatch.setattr(item, "semantic_many", lambda queries, depth: [[]])
    monkeypatch.setattr(item, "rerank", lambda pairs, **kwargs: [0.0])
    item.warm()
    assert "suppressed_positions" not in calls


def test_a_search_racing_the_warm_up_loads_the_word_index_once(tmp_path, monkeypatch):
    params = json.dumps({"num_docs": 3}).encode()
    (tmp_path / "words").mkdir()
    (tmp_path / "words" / "params.index.json").write_bytes(params)
    record = {"bm25": {"path": "words", "num_docs": 3, "params_sha256": hashlib.sha256(params).hexdigest()}}
    item = collection(tmp_path)
    monkeypatch.setattr(item, "_open", lambda: (record, None, 3))
    loads = []
    bm25s = pytest.importorskip("bm25s")

    def slow_load(path, mmap):
        loads.append(path)
        time.sleep(0.2)
        return SimpleNamespace(path=path)

    monkeypatch.setattr(bm25s.BM25, "load", staticmethod(slow_load))
    results = []
    threads = [threading.Thread(target=lambda: results.append(item._word_index())) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(loads) == 1 and len({id(result) for result in results}) == 1
