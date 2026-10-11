"""Search keeps one copy of each instrument (owner decision, 10-11 Oct 2026).

A copy the register does not keep never takes a search slot; a section only a copy
holds stays searchable; a missing or unusable register suppresses nothing and says why;
the register is part of what the collection serves, so changing it under a running
server is refused until reload; saved v4 records still replay.
"""
from copy import deepcopy
import json
import logging

import pytest

from nm.core_engine import retrieval
from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable, validate_search
from tests.test_core_parent_sources import declare
from tests.test_core_retrieval_context import _search
from tests.test_core_statute_readback import _local, _row
from tests.test_current_brain_retrieval import Collection, QUERIES

pytestmark = pytest.mark.class_a

ROWS = [_row("kept-act", "1", "Kept words of section one."),
        _row("kept-act", "2", "Kept words of section two."),
        _row("copy-act", "1", "Copy words of section one."),
        _row("copy-act", "2", "Copy words of section two."),
        _row("copy-act", "3", "Only the copy holds section three.")]
DOCUMENTS = {"kept-act": {"role": "kept", "shown_title": "Kept Act"},
             "copy-act": {"role": "copy", "shown_title": "Kept Act", "kept_sections": ["3"]}}


def with_register(tmp_path, documents=DOCUMENTS, schema=1):
    collection = _local(tmp_path, ROWS)
    path = tmp_path / "instrument_copies.json"
    path.write_text(json.dumps({"schema": schema, "documents": documents}), encoding="utf-8")
    collection.copies = path
    return collection, path


def test_copies_are_hidden_except_the_sections_only_they_hold(tmp_path):
    collection, _ = with_register(tmp_path)
    assert collection.suppressed_positions() == frozenset({2, 3})


def test_an_excluded_instrument_is_hidden_in_every_copy(tmp_path):
    """Owner decision, 11 Oct 2026: Andhra-area laws and two named Acts leave search."""
    documents = {"kept-act": {"role": "excluded", "kept_sections": []},
                 "copy-act": {"role": "excluded", "kept_sections": []}}
    collection, _ = with_register(tmp_path, documents)
    assert collection.suppressed_positions() == frozenset({0, 1, 2, 3, 4})


def test_a_hidden_copy_never_takes_a_search_slot_and_each_leg_looks_deeper(tmp_path, monkeypatch):
    collection, _ = with_register(tmp_path)
    depths = []
    monkeypatch.setattr(collection, "lexical", lambda query, depth: depths.append(depth) or [2, 0, 3, 4, 1])
    monkeypatch.setattr(collection, "semantic", lambda query, depth: depths.append(depth) or [3, 2, 1, 0, 4])
    monkeypatch.setattr(collection, "rerank", lambda pairs, *, anchors=None: [1.0] * len(pairs))
    result = HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES[:1])
    assert {c["position"] for c in result["candidates"] if c["kind"] == "provision"} == {0, 1, 4}
    assert depths and set(depths) == {retrieval.LEG_DEPTH * 2}
    assert result["contract"] == "hybrid_retrieval_v5"
    assert validate_search(result, QUERIES[:1]) == result


def test_without_a_register_every_copy_stays_searchable_and_the_cause_is_logged(tmp_path, caplog):
    collection = _local(tmp_path, ROWS)
    collection.copies = tmp_path / "absent.json"
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        assert collection.suppressed_positions() == frozenset()
    assert any("register is absent" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("schema,documents", [(99, DOCUMENTS), (1, ["not", "a", "map"])])
def test_an_unusable_register_suppresses_nothing(tmp_path, caplog, schema, documents):
    collection, _ = with_register(tmp_path, documents, schema)
    with caplog.at_level(logging.ERROR, logger="nm.core_engine.retrieval"):
        assert collection.suppressed_positions() == frozenset()
    assert any("cannot be applied" in r.getMessage() for r in caplog.records)


def test_the_register_is_part_of_what_the_collection_serves(tmp_path):
    (tmp_path / "plain").mkdir()
    plain = _local(tmp_path / "plain", ROWS)
    collection, path = with_register(tmp_path)
    assert collection.revision() != plain.revision()
    collection.suppressed_positions()
    before = collection.revision()
    path.write_text(json.dumps({"schema": 1, "documents": {}}), encoding="utf-8")
    assert collection.revision() != before
    with pytest.raises(SearchUnavailable, match="changed"):
        collection.suppressed_positions()


def test_saved_v4_records_with_parent_sources_still_replay(tmp_path, monkeypatch):
    parent = _row("act-a", "4", "The full rule, conditions and exception.", chunk_id="root")
    child = _row("act-a", "4", "Only this condition.", chunk_id="clause", parent="root")
    collection = _local(tmp_path, [child])
    declare(collection, {"root": parent})
    result = _search(collection, monkeypatch, [0])
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v5"
    saved_v4 = deepcopy(result)
    saved_v4["contract"] = retrieval.PARENT_STORE_CONTRACT
    assert validate_search(saved_v4, saved_v4["queries"]) == saved_v4
