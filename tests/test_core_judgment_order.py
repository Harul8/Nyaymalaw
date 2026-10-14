"""Judgment order (owner decision, 14 Oct 2026; search contract v7).

The reranker scores almost every on-topic judgment paragraph near its maximum, so its
order among them carries little information. Paragraphs in the court's own words come
before those that report facts, arguments or the order or mostly quote; within each,
the reranker's order is blended by reciprocal ranks with the judgment's citation
standing among held judgments of its court and year. Court-years whose citations are
mostly unrecorded take a neutral standing. An unreadable standing table costs only the
citation part, with an explicit gap. Provisions are unaffected; saved v6 records replay.
"""
from copy import deepcopy
import json
import sqlite3

import pytest

from nm.core_engine import retrieval
from nm.core_engine.retrieval import (
    DIMENSIONS, EMBED_MODEL, HybridSearcher, LocalCollection, SearchUnavailable,
    _judgment_order, validate_search,
)
from tests.test_current_brain_retrieval import Collection, QUERIES


def paragraph(case_id, number, text, kind="reasoning", **extra):
    return {"chunk_id": f"{case_id}:{number}", "case_id": case_id, "case_name": f"Held {case_id}",
            "paragraph_num": str(number), "paragraph_type": kind, "full_text": text,
            "court": "Supreme Court of India", "year": "2010", **extra}


class Judgments:
    """A judgment corpus whose reranker scores each paragraph by its words."""

    def __init__(self, rows, scores, standing=None, failing=False):
        self.rows, self.scores, self.standing, self.failing = dict(enumerate(rows)), scores, standing or {}, failing

    def revision(self): return "checked-judgments"
    def lexical(self, query, depth): return list(self.rows)
    def semantic(self, query, depth): return list(self.rows)
    def read(self, positions): return {p: deepcopy(self.rows[p]) for p in positions if p in self.rows}
    def rerank(self, pairs, *, anchors=None): return [self.scores[text] for _, text in pairs]
    def context(self, position, source):
        return {"scope": "selected_indexed_segment", "bounded": False, "unread_positions": [],
                "segments": [{"position": position, "row": source}]}
    def case_standing(self):
        if self.failing:
            raise SearchUnavailable("Judgment citation standing cannot be read")
        return self.standing


def search(judgments, queries=QUERIES):
    return HybridSearcher({"provision": Collection(), "judgment": judgments}).search(queries)


def judgment_order(result):
    return [c["source"]["chunk_id"] for c in result["candidates"] if c["kind"] == "judgment"]


def test_the_courts_own_words_come_before_reported_or_quoted_paragraphs():
    rows = [paragraph("a", 1, "The plaintiff says the cheque was given as security.", "facts"),
            paragraph("b", 2, "We hold that the presumption is rebuttable on a preponderance of probabilities."),
            paragraph("c", 3, "Counsel for the appellant submits that no debt was proved.", "arguments"),
            paragraph("d", 4, 'Section 139 reads: "It shall be presumed, unless the contrary is proved, that the holder '
                              'of a cheque received the cheque for the discharge of any debt or other liability."'),
            paragraph("e", 5, "The burden shifts to the accused once execution is admitted.", "ratio")]
    scores = {row["full_text"]: score for row, score in zip(rows, (0.99, 0.90, 0.98, 0.995, 0.85))}
    result = search(Judgments(rows, scores))
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v8"
    assert judgment_order(result) == ["b:2", "e:5", "d:4", "a:1", "c:3"]
    assert {c["source"]["chunk_id"]: c["score"] for c in result["candidates"] if c["kind"] == "judgment"} == {
        "a:1": 0.99, "b:2": 0.90, "c:3": 0.98, "d:4": 0.995, "e:5": 0.85}  # each keeps the reranker's own score
    assert result["state"] == "ready"
    assert validate_search(result, QUERIES) == result


def test_citation_standing_breaks_near_ties_within_the_courts_own_words():
    rows = [paragraph("first", 1, "A settled possessor may be evicted only in due course of law."),
            paragraph("leading", 2, "Possession, once settled, is protected against the true owner too."),
            paragraph("third", 3, "An owner may not take the law into his own hands.")]
    scores = {rows[0]["full_text"]: 0.97, rows[1]["full_text"]: 0.96, rows[2]["full_text"]: 0.95}
    standing = {"first": 0.2, "leading": 0.99, "third": 0.6}
    assert judgment_order(search(Judgments(rows, scores, standing))) == ["leading:2", "first:1", "third:3"]
    assert judgment_order(search(Judgments(rows, scores))) == ["first:1", "leading:2", "third:3"]


def test_a_court_year_without_recorded_citations_takes_the_middle_standing():
    rows = {position: paragraph(case, position, f"Paragraph {position} in the court's words.")
            for position, case in enumerate(["low", "recent", "middle", "high"])}
    scored = [(3, 0.9), (1, 0.8), (0, 0.7), (2, 0.6)]
    # 'recent' is unrecorded (None): it takes the middle of the others, not the bottom.
    standing = {"low": 0.05, "recent": None, "middle": 0.5, "high": 0.95}
    unrecorded = _judgment_order(scored, rows, standing)
    assert unrecorded == _judgment_order(scored, rows, {**standing, "recent": 0.5})
    assert unrecorded != _judgment_order(scored, rows, {**standing, "recent": 0.0})
    # A judgment absent from the table takes 0.5, so equal standing keeps the reranker's order.
    assert _judgment_order(scored, rows, {}) == scored


def test_an_unreadable_standing_table_costs_only_the_citation_order():
    rows = [paragraph("a", 1, "The facts as pleaded.", "facts"), paragraph("b", 2, "We hold the rule applies.")]
    scores = {rows[0]["full_text"]: 0.99, rows[1]["full_text"]: 0.5}
    result = search(Judgments(rows, scores, failing=True))
    assert judgment_order(result) == ["b:2", "a:1"]
    assert {(i["kind"], i["stage"]) for i in result["issues"]} == {("judgment", "standing")}
    assert result["state"] == "partial"
    assert validate_search(result, QUERIES) == result
    saved_v6 = deepcopy(result)
    saved_v6["contract"] = retrieval.NAMED_CONTRACT
    with pytest.raises(ValueError, match="gap"):
        validate_search(saved_v6, QUERIES)
    misplaced = deepcopy(result)
    misplaced["issues"][0]["kind"] = "provision"
    with pytest.raises(ValueError, match="gap"):
        validate_search(misplaced, QUERIES)


def test_provisions_keep_their_v6_order():
    result = search(Judgments([paragraph("b", 2, "We hold the rule applies.")], {"We hold the rule applies.": 0.5}))
    provisions = [c for c in result["candidates"] if c["kind"] == "provision"]
    saved = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}).search(QUERIES)
    assert [c["position"] for c in provisions] == [c["position"] for c in saved["candidates"] if c["kind"] == "provision"]


def _store(tmp_path, cases):
    database = tmp_path / "chunks.db"
    rows = [paragraph(case_id, n, f"Paragraph {n} of {case_id}.", court=court, year=year,
                      **({} if cited is None else {"cited_by_count": cited}))
            for case_id, court, year, cited in cases for n in (1, 2)]
    with sqlite3.connect(database) as connection:
        connection.execute("create table chunks (doc_type text not null, pos integer not null, chunk_id text not null, "
                           "act_id text, case_id text, parent_chunk_id text, atom_type text, section_number text, "
                           "blob text not null, primary key (doc_type, pos))")
        for position, row in enumerate(rows):
            connection.execute("insert into chunks values (?,?,?,?,?,?,?,?,?)",
                               ("case_law", position, row["chunk_id"], None, row["case_id"], None,
                                row["paragraph_type"], None, json.dumps({**row, "doc_type": "case_law"})))
    connection.close()
    lineage = tmp_path / "lineage.json"
    lineage.write_text(json.dumps({"schema": 1, "doc_type": "case_law", "model": EMBED_MODEL, "dimensions": DIMENSIONS,
                                   "passages": len(rows), "vector_index": {"path": "not-needed.index"},
                                   "bm25": {"path": "not-needed-bm25"}, "passage_store": {"path": "chunks.db"}}),
                       encoding="utf-8")
    return LocalCollection(corpus_dir=tmp_path, lineage=lineage, doc_type="case_law", models=None)


def test_standing_compares_each_judgment_with_its_own_court_and_year(tmp_path):
    collection = _store(tmp_path, [
        ("sc-a", "Supreme Court of India", "2010", 0), ("sc-b", "Supreme Court of India", "2010", 5),
        ("sc-c", "Supreme Court of India", "2010", 10),
        ("hc-a", "High Court of Andhra Pradesh", "2010", 3),
        ("new-a", "Supreme Court of India", "2025", 0), ("new-b", "Supreme Court of India", "2025", None),
        ("new-c", "Supreme Court of India", "2025", 7)])
    table = collection.case_standing()
    assert table["sc-a"] == pytest.approx(1 / 6) and table["sc-b"] == pytest.approx(0.5)
    assert table["sc-c"] == pytest.approx(5 / 6)
    assert table["hc-a"] == pytest.approx(0.5)  # alone in its court-year, not measured against the Supreme Court
    assert table["new-a"] is table["new-b"] is table["new-c"] is None  # most of 2025 has no recorded citations
    assert collection.case_standing() is table  # read once per corpus revision
