"""The new brain searches both held corpora without turning rank into support."""
from __future__ import annotations

import json
from datetime import date

import pytest

from nm.brain.retrieval import HybridSearcher, LocalCollection, SearchUnavailable


def test_corpus_revision_tracks_real_artifacts_and_refuses_a_stale_loaded_snapshot(tmp_path):
    (tmp_path / "words").mkdir()
    for name in ("vectors", "passages", "words/params.index.json", "words/data.npy"):
        (tmp_path / name).write_bytes(b"original")
    lineage = tmp_path / "lineage.json"
    lineage.write_text(json.dumps({
        "vector_index": {"path": "vectors"}, "passage_store": {"path": "passages"},
        "bm25": {"path": "words"}}))
    collection = LocalCollection(corpus_dir=tmp_path, lineage=lineage,
                                 doc_type="bare_act", models=None)
    first = collection.revision()
    assert first is not None
    collection._revision = first
    collection._loaded = (object(), object(), tmp_path / "passages", 1)
    collection._open()
    (tmp_path / "words/data.npy").write_bytes(b"changed-array-content")
    assert collection.revision() != first
    with pytest.raises(SearchUnavailable, match="loaded corpus changed"):
        collection._open()


def test_unknown_collection_revision_never_claims_a_reusable_snapshot():
    assert HybridSearcher({}).revision() is None


class FakeCollection:
    def __init__(self, rows, lexical, semantic, scores):
        self.rows = rows
        self.lexical_hits = lexical
        self.semantic_hits = semantic
        self.scores = scores
        self.asked = []
        self.reranked = []

    def lexical(self, query, depth):
        self.asked.append(("lexical", query, depth))
        return list(self.lexical_hits.get(query, []))

    def semantic(self, query, depth):
        self.asked.append(("semantic", query, depth))
        return list(self.semantic_hits.get(query, []))

    def read(self, positions):
        return {position: self.rows[position] for position in positions
                if position in self.rows}

    def rerank(self, pairs):
        self.reranked.extend(pairs)
        return [self.scores.get((query, text), self.scores.get(text))
                for query, text in pairs]


def _row(chunk, text, **metadata):
    return {"chunk_id": chunk, "full_text": text, **metadata}


def test_every_query_searches_both_corpora_and_keeps_exact_read_passages():
    queries = ("dispute words", "legal condition", "remedy words")
    sections = FakeCollection({
        1: _row("act-1", "Exact provision text.\nSecond line.", act_id="act-a",
                act_name="Act A", section_number="4"),
        2: _row("act-2", "Another exact provision.", act_id="act-a",
                act_name="Act A", section_number="5"),
        3: _row("act-3", "Third exact provision.", act_id="act-b",
                act_name="Act B", section_number="7"),
    }, {queries[0]: [1], queries[1]: [2], queries[2]: [3]},
       {queries[0]: [], queries[1]: [2], queries[2]: []},
       {"Exact provision text.\nSecond line.": 0.9,
        "Another exact provision.": 0.8, "Third exact provision.": 0.7})
    judgments = FakeCollection({
        10: _row("case-10", "The court's exact holding.", case_id="c10",
                 case_name="A v B", paragraph_num="10", paragraph_type="ratio",
                 court="Supreme Court", year="2020"),
        11: _row("case-11", "Counsel argued this.", case_id="c11",
                 paragraph_type="arguments", year="2019"),
        12: _row("case-12", "Later decision.", case_id="c12",
                 paragraph_type="reasoning", year="2030"),
    }, {queries[0]: [10, 11], queries[1]: [], queries[2]: [12]},
       {queries[0]: [10], queries[1]: [11], queries[2]: []},
       {"The court's exact holding.": 0.6})
    search = HybridSearcher({"provision": sections, "judgment": judgments},
                            source_paths={"provision": "held/chunks.db",
                                          "judgment": "held/chunks.db"})

    result = search.search_dispute({"id": "d1"}, queries, as_of=date(2026, 10, 2))

    assert result["state"] == "ok"
    assert [item["source_chunk_id"] for item in result["candidates"]] == [
        "act-1", "act-2", "act-3", "case-10"]
    assert len({item["id"] for item in result["candidates"]}) == 4
    assert result["candidates"][0]["text"] == "Exact provision text.\nSecond line."
    assert result["candidates"][-1]["locator"] == "A v B, paragraph 10"
    assert result["candidates"][-1]["source_path"] == "held/chunks.db"
    assert judgments.reranked == [(queries[0], "The court's exact holding.")]
    assert [question for leg, question, _ in sections.asked if leg == "lexical"] == list(queries)
    assert [question for leg, question, _ in judgments.asked if leg == "semantic"] == list(queries)
    assert any("excluded 2" in note for note in result["diagnostics"])
    json.dumps(result)


def test_repeated_chunk_ids_cannot_merge_distinct_source_passages():
    sections = FakeCollection({
        1: _row("repeated", "First exact section.", act_id="act-a",
                act_name="Act A", section_number="1"),
        2: _row("repeated", "Second exact section.", act_id="act-b",
                act_name="Act B", section_number="2"),
    }, {"words": [1, 2]}, {"words": []},
       {"First exact section.": 0.8, "Second exact section.": 0.7})
    judgments = FakeCollection({}, {"words": []}, {"words": []}, {})
    result = HybridSearcher({"provision": sections, "judgment": judgments}).search_dispute(
        {}, ("words",))
    assert result["state"] == "ok"
    assert len(result["candidates"]) == 2
    assert len({item["id"] for item in result["candidates"]}) == 2


def test_distinct_passages_from_one_authority_are_not_lost_at_document_deduplication():
    sections = FakeCollection({
        1: _row("a1", "The rule.", act_id="a", act_name="Act A", section_number="1"),
        2: _row("a2", "The rule's exception.", act_id="a", act_name="Act A",
                section_number="1"),
    }, {"question": [1, 2]}, {"question": [1, 2]},
        {"The rule.": 0.9, "The rule's exception.": 0.8})
    judgments = FakeCollection({
        1: _row("j1", "Supported holding.", case_id="c", case_name="A v B",
                paragraph_num="10", paragraph_type="ratio"),
        2: _row("j2", "Material limit.", case_id="c", case_name="A v B",
                paragraph_num="11", paragraph_type="reasoning"),
    }, {"question": [1, 2]}, {"question": [1, 2]},
        {"Supported holding.": 0.9, "Material limit.": 0.8})
    found = HybridSearcher({"provision": sections, "judgment": judgments}).search_subject(
        {}, ("question",))
    assert [row["source_chunk_id"] for row in found["candidates"]] == ["a1", "a2", "j1", "j2"]


def test_reranking_scores_only_queries_that_surfaced_each_candidate():
    first, second = "first route", "second route"
    sections = FakeCollection({
        1: _row("one", "First section.", act_id="act-a",
                act_name="Act A", section_number="1"),
        2: _row("shared", "Shared section.", act_id="act-b",
                act_name="Act B", section_number="2"),
        3: _row("three", "Third section.", act_id="act-c",
                act_name="Act C", section_number="3"),
    }, {first: [1, 2], second: [2, 3]}, {first: [], second: []}, {
        (first, "First section."): 0.6,
        (first, "Shared section."): 0.5,
        (second, "Shared section."): 0.95,
        (second, "Third section."): 0.8,
    })
    judgments = FakeCollection({}, {first: [], second: []},
                               {first: [], second: []}, {})

    result = HybridSearcher({"provision": sections,
                             "judgment": judgments}).search_dispute(
                                 {"id": "d"}, (first, second))

    assert result["state"] == "ok"
    assert [row["source_chunk_id"] for row in result["candidates"]] == [
        "shared", "three", "one"]
    assert set(sections.reranked) == {
        (first, "First section."),
        (first, "Shared section."),
        (second, "Shared section."),
        (second, "Third section."),
    }
    assert len(sections.reranked) == 4 < 3 * 2


def test_partial_corpus_failure_keeps_attributed_sources_and_marks_gap():
    class Missing:
        def semantic(self, query, depth):
            raise SearchUnavailable("lineage absent")

        def lexical(self, query, depth):
            raise SearchUnavailable("lineage absent")

    section = FakeCollection({1: _row("s", "Exact statute.", act_id="a",
                                      act_name="Act", section_number="1")},
                             {"words": [1]}, {"words": []}, {"Exact statute.": 1.0})
    result = HybridSearcher({"provision": section, "judgment": Missing()}).search_dispute(
        {}, ("words",))
    assert result["state"] == "partial"
    assert [row["text"] for row in result["candidates"]] == ["Exact statute."]
    assert any("judgment search unavailable: the local corpus could not be searched" == note
               for note in result["diagnostics"])


def test_broken_adapter_does_not_hide_other_corpus():
    class Broken:
        pass

    section = FakeCollection({1: _row("s", "Exact statute.", act_id="a",
                                      act_name="Act", section_number="1")},
                             {"words": [1]}, {"words": []}, {"Exact statute.": 1.0})
    result = HybridSearcher({"provision": section, "judgment": Broken()}).search_dispute(
        {}, ("words",))
    assert result["state"] == "partial"
    assert [row["text"] for row in result["candidates"]] == ["Exact statute."]
    assert "judgment search unavailable: local index failure" in result["diagnostics"]


def test_failure_after_query_search_keeps_other_corpus():
    class BrokenRead(FakeCollection):
        def read(self, positions):
            raise SearchUnavailable("passage store unreadable")

    section = FakeCollection({1: _row("s", "Exact statute.", act_id="a",
                                      act_name="Act", section_number="1")},
                             {"words": [1]}, {"words": []},
                             {"Exact statute.": 1.0})
    judgment = BrokenRead({}, {"words": [1]}, {"words": []}, {})
    result = HybridSearcher({"provision": section, "judgment": judgment}).search_dispute(
        {}, ("words",))
    assert result["state"] == "partial"
    assert [row["text"] for row in result["candidates"]] == ["Exact statute."]
    assert ("judgment search unavailable: the local corpus could not be searched"
            in result["diagnostics"])


def test_empty_search_formulations_do_not_search_or_invent_sources():
    result = HybridSearcher({}).search_dispute({}, ("", "  "))
    assert result["state"] == "unavailable"
    assert result["candidates"] == []


def test_no_available_corpus_has_no_candidates():
    result = HybridSearcher({}).search_dispute({}, ("words",))
    assert result["state"] == "unavailable"
    assert result["candidates"] == []
    assert len(result["diagnostics"]) == 2


def test_collection_refuses_missing_lineage_before_loading_native_dependencies(tmp_path):
    collection = LocalCollection(corpus_dir=tmp_path,
                                 lineage=tmp_path / "missing.json",
                                 doc_type="case_law", models=None)
    try:
        collection.lexical("query", 5)
    except SearchUnavailable as exc:
        assert "lineage" in str(exc)
    else:
        raise AssertionError("missing lineage was silently searched")
