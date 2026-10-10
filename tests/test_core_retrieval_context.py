"""Provision context follows unique owned links, not repeated printed numbers."""
from copy import deepcopy

import pytest

from nm.core_engine.retrieval import (
    CONTRACT, HybridSearcher, SearchUnavailable, _candidate, validate_search,
)
from tests.test_core_statute_readback import _local, _row
from tests.test_current_brain_retrieval import Collection, QUERIES


def _search(collection, monkeypatch, positions):
    monkeypatch.setattr(collection, "lexical", lambda query, depth: positions)
    monkeypatch.setattr(collection, "semantic", lambda query, depth: positions)
    monkeypatch.setattr(collection, "rerank", lambda pairs, *, anchors=None: [1.0] * len(pairs))
    return HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES[:1])


def test_repeated_root_id_cannot_turn_different_sections_or_forms_into_neighbours(tmp_path, monkeypatch):
    originals = [_row("act-a", "4", "First distinct root.", chunk_id="reused-root"),
                 _row("act-a", "4", "Another distinct root.", chunk_id="reused-root")]
    collection = _local(tmp_path, originals)
    result = _search(collection, monkeypatch, [0, 1])
    provisions = [row for row in result["candidates"] if row["kind"] == "provision"]
    assert len(provisions) == 2
    assert result["state"] == "partial"
    for source in provisions:
        assert source["text"] == originals[source["position"]]["full_text"]
        assert source["context"]["scope"] == "selected_indexed_segment"
        assert source["context"]["bounded"] is True
        assert [s["position"] for s in source["context"]["segments"]] == [source["position"]]
    assert any("ambiguous" in gap["reason"].lower() for gap in result["issues"])
    assert validate_search(result, QUERIES[:1]) == result


def test_same_number_unique_unrelated_roots_remain_separate_and_keep_connected_children(tmp_path, monkeypatch):
    originals = [_row("act-a", "4", "Root one with its own conditions.", chunk_id="root-one"),
                 _row("act-a", "4", "Root one's exception.", chunk_id="child-one", parent="root-one"),
                 _row("act-a", "4", "Unrelated root two.", chunk_id="root-two"),
                 _row("act-a", "4", "Root two's qualification.", chunk_id="child-two", parent="root-two")]
    result = _search(_local(tmp_path, originals), monkeypatch, [0, 2])
    provisions = [row for row in result["candidates"] if row["kind"] == "provision"]
    assert len(provisions) == 2
    groups = {row["position"]: {part["position"] for part in row["context"]["segments"]} for row in provisions}
    assert groups == {0: {0, 1}, 2: {2, 3}}
    assert all(row["context"]["bounded"] for row in provisions)
    assert validate_search(result, QUERIES[:1]) == result


@pytest.mark.parametrize("hits", [[0], [0, 1, 2], [2]])
def test_legitimate_tree_preserves_all_exact_words_and_deduplicates_hits_by_owned_root(tmp_path, monkeypatch, hits):
    originals = [_row("act-a", "4", "  Main rule\nwith qualifications.  ", chunk_id="root"),
                 _row("act-a", "4", "Exception " * 2000, chunk_id="child", parent="root"),
                 _row("act-a", "4", "Exception to exception.", chunk_id="grandchild", parent="child")]
    collection = _local(tmp_path, originals)
    result = _search(collection, monkeypatch, hits)
    provisions = [row for row in result["candidates"] if row["kind"] == "provision"]
    assert len(provisions) == 1 and provisions[0]["position"] == 0
    assert result["state"] == "ready"
    assert {s["position"]: s["row"] for s in provisions[0]["context"]["segments"]} == dict(enumerate(originals))
    assert validate_search(result, QUERIES[:1]) == result
    assert collection.read_provision("act-a", "section 4")["state"] == "found"


def test_ambiguous_or_unread_child_keeps_unrelated_good_tree_members(tmp_path, monkeypatch):
    originals = [_row("act-a", "4", chunk_id="root"),
                 _row("act-a", "4", "Clear exception.", chunk_id="good", parent="root"),
                 _row("act-a", "4", "Ambiguous first.", chunk_id="collision", parent="root"),
                 _row("act-a", "4", "Ambiguous second.", chunk_id="collision", parent="root"),
                 _row("act-a", "4", "", chunk_id="unread", parent="root")]
    result = _search(_local(tmp_path, originals), monkeypatch, [0])
    source = next(row for row in result["candidates"] if row["kind"] == "provision")
    assert {s["position"] for s in source["context"]["segments"]} == {0, 1}
    assert source["context"]["bounded"]
    assert source["context"]["unread_positions"] == [4]
    assert result["state"] == "partial"
    assert validate_search(result, QUERIES[:1]) == result


@pytest.mark.parametrize("different_ids", [False, True])
def test_named_provision_is_ambiguous_when_the_locator_has_distinct_roots(tmp_path, different_ids):
    collection = _local(tmp_path, [_row("act-a", "4", "First root.", chunk_id="first"),
        _row("act-a", "4", "Another root.", chunk_id="second" if different_ids else "first")])
    result = collection.read_provision("act-a", "section 4")
    assert result["state"] == "ambiguous"
    assert result["sources"] == [] and result["provision_key"] is None
    assert result["reason"]


def test_rank_context_rejects_ambiguous_leaf_identity_as_well_as_ambiguous_parent(tmp_path):
    originals = [_row("act-a", "4", chunk_id="root"),
                 _row("act-a", "4", "First leaf.", chunk_id="leaf", parent="root"),
                 _row("act-a", "4", "Another leaf.", chunk_id="leaf", parent="root")]
    collection = _local(tmp_path, originals)
    with pytest.raises(SearchUnavailable, match="ambiguous"):
        collection.rank_context(1, originals[1])


def test_missing_parent_is_a_bounded_selected_source_not_an_invented_numeric_group(tmp_path, monkeypatch):
    originals = [_row("act-a", "4", "Child with unavailable parent.", chunk_id="child", parent="missing"),
                 _row("act-a", "4", "Unrelated root.", chunk_id="other")]
    result = _search(_local(tmp_path, originals), monkeypatch, [0])
    source = next(row for row in result["candidates"] if row["kind"] == "provision")
    assert source["position"] == 0 and source["context"]["bounded"]
    assert [s["position"] for s in source["context"]["segments"]] == [0]
    assert result["state"] == "partial" and validate_search(result, QUERIES[:1]) == result


def test_v3_rejects_disconnected_context_but_replays_unchanged_v1_v2_snapshots():
    collection = Collection()
    collection.rows[1]["section_number"] = collection.rows[0]["section_number"]
    result = HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    source = next(row for row in result["candidates"] if row["kind"] == "provision")
    invalid_window = {"scope": "indexed_section_segments", "bounded": False, "unread_positions": [],
                      "segments": [{"position": p, "row": row} for p, row in collection.rows.items()]}
    replacement = _candidate(source["kind"], source["position"], source["source"],
        source["corpus_revision"], source["score"], source["query_ids"], invalid_window)
    result["candidates"][result["candidates"].index(source)] = replacement
    assert result["contract"] == CONTRACT == "hybrid_retrieval_v4"
    with pytest.raises(ValueError, match="unique|connected|root"):
        validate_search(result, QUERIES)
    for version in ("hybrid_retrieval_v1", "hybrid_retrieval_v2"):
        old = deepcopy(result)
        old["contract"] = version
        assert validate_search(old, QUERIES) == old


def test_legacy_v2_exact_parent_tree_still_replays(tmp_path, monkeypatch):
    originals = [_row("act-a", "4", chunk_id="root"),
                 _row("act-a", "4", "Exception.", chunk_id="child", parent="root")]
    result = _search(_local(tmp_path, originals), monkeypatch, [1])
    assert next(row for row in result["candidates"] if row["kind"] == "provision")["context"]["scope"] == "exact_parent_tree"
    old = deepcopy(result)
    old["contract"] = "hybrid_retrieval_v2"
    assert validate_search(old, QUERIES[:1]) == old


def test_context_resource_bound_keeps_complete_selected_words_and_explicit_gap(tmp_path, monkeypatch):
    monkeypatch.setattr("nm.core_engine.retrieval.MAX_CONTEXT_SEGMENTS", 3)
    originals = [_row("act-a", "4", "Complete source with final qualification.", chunk_id="root"),
        *[_row("act-a", "4", f"Complete connected child {n}.", chunk_id=f"child-{n}", parent="root")
          for n in range(4)]]
    collection = _local(tmp_path, originals)
    result = _search(collection, monkeypatch, [0])
    source = next(row for row in result["candidates"] if row["kind"] == "provision")
    assert [s["position"] for s in source["context"]["segments"]] == [0, 1, 2]
    assert source["text"] == originals[0]["full_text"] and source["context"]["bounded"]
    assert any("resource bound reached: True" in issue["reason"] for issue in result["issues"])
    assert validate_search(result, QUERIES[:1]) == result
    named = collection.read_provision("act-a", "section 4")
    assert named["state"] == "unavailable" and named["sources"] == []
    assert "resource bound" in named["reason"]
