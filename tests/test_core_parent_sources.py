"""Contextual parents are source records; they are never vector positions."""
from copy import deepcopy
import hashlib
import json

import pytest

from nm.core_engine import retrieval
from tests.test_core_statute_readback import _local, _row
from tests.test_core_retrieval_context import _search

pytestmark = pytest.mark.class_a


def declare(collection, parents, *, raw=None):
    path = collection.corpus_dir / "parents.json"
    data = raw if raw is not None else json.dumps(parents).encode()
    path.write_bytes(data)
    manifest = json.loads(collection.lineage.read_text(encoding="utf-8"))
    manifest["context_store"] = {"path": path.name, "format": "parent_map_v1",
                                 "sha256": hashlib.sha256(data).hexdigest()}
    collection.lineage.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_exact_parent_words_are_ranked_and_selected_without_an_invented_vector_position(tmp_path, monkeypatch):
    parent = _row("act-a", "4", "The full rule, conditions and exception.", chunk_id="root")
    child = _row("act-a", "4", "Only this condition.", chunk_id="clause", parent="root")
    collection = _local(tmp_path, [child])
    declare(collection, {"root": parent})
    result = _search(collection, monkeypatch, [0])
    source = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert source["position"] == "parent:root"
    assert source["text"] == parent["full_text"] and source["source"] == parent
    assert {s["position"] for s in source["context"]["segments"]} == {"parent:root", 0}
    assert source["score"] == 1.0 and result["state"] == "ready"
    assert retrieval.validate_search(result, result["queries"]) == result
    for old in ("hybrid_retrieval_v1", "hybrid_retrieval_v2", "hybrid_retrieval_v3"):
        altered = deepcopy(result)
        altered["contract"] = old
        with pytest.raises(ValueError, match="Historical"):
            retrieval.validate_search(altered, altered["queries"])


def test_missing_context_does_not_relegate_readable_qualified_text_to_an_unranked_tail(tmp_path, monkeypatch):
    article = _row("act-a", "Article_8", "A complete article with a final exception.",
                   chunk_id="article", parent="unstored-container")
    collection = _local(tmp_path, [article])
    result = _search(collection, monkeypatch, [0])
    source = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert source["score"] == 1.0 and source["position"] == 0
    assert source["source"] == article
    assert source["context"]["bounded"] and source["context"]["scope"] == "selected_indexed_segment"
    assert result["state"] == "partial"
    assert retrieval.validate_search(result, result["queries"]) == result


@pytest.mark.parametrize("damage", ["foreign_act", "wrong_key", "wrong_section", "cycle", "duplicate", "undeclared", "wrong_hash"])
def test_untrusted_context_never_replaces_the_owned_readable_source(tmp_path, monkeypatch, damage):
    parent = _row("act-a", "4", "Exact parent words.", chunk_id="root")
    child = _row("act-a", "4", "Exact child words.", chunk_id="child", parent="root")
    collection = _local(tmp_path, [child])
    if damage == "foreign_act": parent["act_id"] = "other-act"
    if damage == "wrong_key": parent["chunk_id"] = "other-root"
    if damage == "wrong_section": parent["section_number"] = "8"
    if damage == "cycle": parent["parent_chunk_id"] = "child"
    if damage == "duplicate":
        encoded = json.dumps(parent)
        declare(collection, {}, raw=('{"root":' + encoded + ',"root":' + encoded + '}').encode())
    else:
        path = declare(collection, {"root": parent})
        if damage == "undeclared":
            manifest = json.loads(collection.lineage.read_text(encoding="utf-8"))
            manifest.pop("context_store")
            collection.lineage.write_text(json.dumps(manifest), encoding="utf-8")
        if damage == "wrong_hash": path.write_text(json.dumps({"root": {**parent, "full_text": "Changed words."}}), encoding="utf-8")
    result = _search(collection, monkeypatch, [0])
    source = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert source["position"] == 0 and source["source"] == child
    assert source["score"] == 1.0 and source["context"]["bounded"]
    assert retrieval.validate_search(result, result["queries"]) == result


def test_parent_store_change_invalidates_loaded_snapshot(tmp_path):
    parent = _row("act-a", "4", chunk_id="root")
    child = _row("act-a", "4", chunk_id="child", parent="root")
    collection = _local(tmp_path, [child])
    path = declare(collection, {"root": parent})
    collection.rank_context(0, child)
    path.write_text(json.dumps({"root": {**parent, "full_text": "Changed conditions."}}), encoding="utf-8")
    with pytest.raises(retrieval.SearchUnavailable, match="changed"):
        collection.rank_context(0, child)


def test_duplicate_parent_record_does_not_discard_an_independent_valid_parent(tmp_path):
    parent = _row("act-a", "4", chunk_id="root")
    child = _row("act-a", "4", chunk_id="child", parent="root")
    collection = _local(tmp_path, [child])
    raw = ('{"unrelated":{},"unrelated":{},"root":' + json.dumps(parent) + '}').encode()
    declare(collection, {}, raw=raw)
    assert collection.rank_context(0, child)["segments"][0]["row"] == parent


def test_repeated_printed_numbers_never_merge_unrelated_occurrences(tmp_path, monkeypatch):
    parent = _row("act-a", "4", "Full operative words.", chunk_id="operative-root")
    child = _row("act-a", "4", "Condition.", chunk_id="clause", parent="operative-root")
    heading = _row("act-a", "4", "Arrangement heading only.", chunk_id="arrangement")
    collection = _local(tmp_path, [child, heading])
    declare(collection, {parent["chunk_id"]: parent})
    result = _search(collection, monkeypatch, [0, 1])
    provisions = [c for c in result["candidates"] if c["kind"] == "provision"]
    assert len(provisions) == 2
    operative = next(c for c in provisions if c["position"] == "parent:operative-root")
    assert {s["position"] for s in operative["context"]["segments"]} == {"parent:operative-root", 0}
    assert collection.read_provision("act-a", "4")["state"] != "found"
    assert retrieval.validate_search(result, result["queries"]) == result
