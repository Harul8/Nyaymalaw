"""Hybrid candidate search keeps exact text and independent failed search legs."""
from copy import deepcopy
import re
import json
import sqlite3
import struct
import sys
from types import SimpleNamespace

import pytest

from nm.brain.retrieval import (
    DIMENSIONS, EMBED_MODEL, HybridSearcher, LocalCollection, SearchUnavailable,
    _digest, bm25_tokens, token_windows, validate_search,
)


def row(kind="provision", text="Complete provision including its exception."):
    return {"chunk_id": "repeated", "full_text": text,
            **({"act_id": "act", "act_name": "Act", "section_number": "4"} if kind == "provision" else
               {"case_id": "case", "case_name": "Judgment", "paragraph_num": "12", "atom_type": "holding"})}


class Collection:
    def __init__(self, kind="provision", fail=None):
        self.kind, self.fail = kind, fail
        self.rows = {0: row(kind), 1: row(kind, "Different exact words using the same chunk ID.")}
        if kind == "provision": self.rows[1]["section_number"] = "5"
        self.calls = []

    def revision(self): return "checked-corpus"
    def lexical(self, query, depth):
        self.calls.append(("lexical", query))
        if self.fail == "lexical": raise SearchUnavailable("Unavailable word index")
        return [0, 1]
    def semantic(self, query, depth):
        self.calls.append(("semantic", query))
        if self.fail == "semantic": raise SearchUnavailable("Unavailable vectors")
        return [1, 0]
    def read(self, positions):
        if self.fail == "read": raise SearchUnavailable("Unread store")
        return {p: deepcopy(self.rows[p]) for p in positions if p in self.rows}
    def rerank(self, pairs):
        if self.fail == "rerank": raise SearchUnavailable("Unavailable reranker")
        return [float(i) for i in range(len(pairs))]
    def context(self, position, source):
        if self.fail == "context": raise SearchUnavailable("Unread context")
        return {"scope": "selected_indexed_segment", "bounded": False, "unread_positions": [],
                "segments": [{"position": position, "row": source}]}


QUERIES = [{"query_id": "dispute:1:q1", "text": "first legal route"},
           {"query_id": "dispute:1:q2", "text": "second legal route"}]


def search(fail=None):
    return HybridSearcher({"provision": Collection(fail=fail), "judgment": Collection("judgment")}).search(QUERIES)


def test_both_corpora_receive_every_query_and_same_chunk_id_never_joins_different_passages():
    collections = {"provision": Collection(), "judgment": Collection("judgment")}
    result = HybridSearcher(collections).search(QUERIES)
    assert result["state"] == "ready" and len(result["candidates"]) == 4
    assert len({c["id"] for c in result["candidates"]}) == 4
    assert all(len(c["query_ids"]) == 2 for c in result["candidates"])
    for collection in collections.values():
        assert len(collection.calls) == 4
    assert validate_search(result, QUERIES) == result


@pytest.mark.parametrize("failure", ["lexical", "semantic", "rerank", "context", "read"])
def test_independent_search_failure_keeps_useful_corpus_and_does_not_claim_complete(failure):
    result = search(failure)
    assert result["state"] == "partial" and result["issues"]
    assert any(c["kind"] == "judgment" for c in result["candidates"])
    if failure != "read": assert any(c["kind"] == "provision" for c in result["candidates"])
    if failure == "rerank": assert all(c["score"] is None for c in result["candidates"] if c["kind"] == "provision")
    assert validate_search(result, QUERIES) == result


def test_judgment_role_metadata_is_preserved_without_becoming_a_holding_verdict():
    collection = Collection("judgment")
    collection.rows[0]["atom_type"] = "argument"
    result = HybridSearcher({"judgment": collection}).search(QUERIES)
    assert {c["source"]["atom_type"] for c in result["candidates"]} == {"argument", "holding"}
    assert all(c["legal_status"] == "candidate_unassessed" for c in result["candidates"])


def test_query_variants_share_one_complete_dispute_rerank_inquiry():
    collection = Collection()
    received = []
    collection.rerank = lambda pairs: received.extend(pairs) or [0.5] * len(pairs)
    queries = [dict(q, context="Original account with limiting condition.") for q in QUERIES]
    HybridSearcher({"provision": collection}).search(queries)
    assert len(received) == len(collection.rows)
    for inquiry, passage in received:
        assert inquiry.count("Original account with limiting condition.") == 1
        assert all(q["text"] in inquiry for q in queries)
        assert passage.startswith("Act\n")


def test_missing_row_does_not_remove_readable_peers():
    collection = Collection()
    del collection.rows[0]
    result = HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "partial"
    assert len([c for c in result["candidates"] if c["kind"] == "provision"]) == 1


class Tokenizer:
    def __call__(self, text, **kwargs):
        assert kwargs["truncation"] is False
        return {"offset_mapping": [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]}


def test_exact_windows_cover_long_text_tail_and_original_whitespace_without_prefix_truncation():
    text = "  " + "  ".join(f"token{i}" for i in range(1100)) + "\nTAIL QUALIFICATION\n"
    windows = token_windows(text, Tokenizer(), 120, overlap=20)
    covered = set()
    for start, end, words in windows:
        assert words == text[start:end]
        covered.update(range(start, end))
    assert covered == set(range(len(text))) and "TAIL QUALIFICATION" in windows[-1][2]


@pytest.mark.parametrize("damage", ["text", "position", "revision", "query", "status", "kind", "duplicate"])
def test_changed_exact_source_or_foreign_query_cannot_replay(damage):
    result = search()
    c = result["candidates"][0]
    if damage == "text": c["text"] = "Invented"
    elif damage == "position": c["position"] += 1
    elif damage == "revision": c["corpus_revision"] = "other"
    elif damage == "query": c["query_ids"] = ["foreign:q1"]
    elif damage == "status": c["legal_status"] = "law_checked"
    elif damage == "kind": c["kind"] = "other"
    else: result["candidates"].append(deepcopy(c))
    with pytest.raises((ValueError, SearchUnavailable)): validate_search(result, QUERIES)


@pytest.mark.parametrize("damage", ["context_words", "context_section", "context_anchor", "score", "stages", "empty_ready"])
def test_context_and_stage_coverage_are_not_opaque_self_certification(damage):
    result = search()
    c = next(c for c in result["candidates"] if c["kind"] == "provision")
    if damage == "context_words": c["context"]["segments"][0]["row"]["full_text"] = "Invented context"
    elif damage == "context_section": c["context"]["segments"][0]["row"]["section_number"] = "999"
    elif damage == "context_anchor": c["context"]["segments"] = []
    elif damage == "score": c["score"] = float("inf")
    elif damage == "stages": result["stages"] = []
    else:
        result.update(corpus_revisions={"provision":None,"judgment":None},stages=[],candidates=[])
    with pytest.raises((ValueError, SearchUnavailable)): validate_search(result, QUERIES)


def test_corpus_change_during_search_discards_only_that_changed_corpus():
    collection = Collection()
    revisions = iter(["before", "after"])
    collection.revision = lambda: next(revisions)
    result = HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "partial" and {c["kind"] for c in result["candidates"]} == {"judgment"}


def local(tmp_path, monkeypatch, missing="vector"):
    import hashlib
    import numpy as np
    db = tmp_path / "chunks.db"
    with sqlite3.connect(db) as connection:
        connection.execute("create table chunks(doc_type text,pos integer,chunk_id text,blob text)")
        connection.execute("insert into chunks values (?,?,?,?)",("bare_act",0,"repeated",json.dumps(row())))
    words = tmp_path / "words"
    words.mkdir()
    params = json.dumps({"num_docs":1}).encode()
    if missing != "words": (words / "params.index.json").write_bytes(params)
    if missing != "vector": (tmp_path / "vector").write_bytes(b"IxFI"+struct.pack("<i",DIMENSIONS)+struct.pack("<q",1))
    manifest={"schema":1,"doc_type":"bare_act","model":EMBED_MODEL,"dimensions":DIMENSIONS,"passages":1,
        "vector_index":{"path":"vector","vectors":1,"bytes":16},
        "bm25":{"path":"words","num_docs":1,"params_sha256":hashlib.sha256(params).hexdigest()},
        "passage_store":{"path":"chunks.db"},"verified":{"sampled":1,"same_vector":1,"mean_similarity":1}}
    lineage=tmp_path/"lineage.json"
    lineage.write_text(json.dumps(manifest))
    word_index=SimpleNamespace(vocab_dict={"first":0,"legal":1,"route":2},get_scores=lambda tokens: np.array([1.]))
    monkeypatch.setitem(sys.modules,"bm25s",SimpleNamespace(BM25=SimpleNamespace(load=lambda *a,**k:word_index)))
    vector=SimpleNamespace(search=lambda values,depth:(np.ones((len(values),1)),np.zeros((len(values),1),dtype=int)))
    monkeypatch.setitem(sys.modules,"faiss",SimpleNamespace(IO_FLAG_MMAP_IFC=1,IO_FLAG_READ_ONLY=2,read_index=lambda *a:vector))
    class Models:
        def encode(self, queries): return np.ones((len(queries),DIMENSIONS)),[(i,i+1) for i in range(len(queries))]
        def _model(self, which): raise SearchUnavailable("Reranker deliberately unavailable")
    return LocalCollection(corpus_dir=tmp_path,lineage=lineage,doc_type="bare_act",models=Models())


@pytest.mark.parametrize("missing",["vector","words"])
def test_real_reader_surviving_index_does_not_depend_on_other_index_or_reranker(tmp_path,monkeypatch,missing):
    collection=local(tmp_path,monkeypatch,missing)
    result=HybridSearcher({"provision":collection,"judgment":Collection("judgment")}).search(QUERIES[:1])
    assert any(c["kind"]=="provision" for c in result["candidates"])
    assert result["state"]=="partial" and any(i["stage"]=="rerank" for i in result["issues"])
    assert validate_search(result,QUERIES[:1])==result


def test_wal_commit_changes_revision_even_without_main_database_change(tmp_path,monkeypatch):
    collection=local(tmp_path,monkeypatch)
    with sqlite3.connect(tmp_path/"chunks.db") as db:
        db.execute("pragma journal_mode=WAL")
        db.execute("update chunks set blob=blob")
        db.commit()
        before=collection.revision()
        db.execute("update chunks set blob=?",(json.dumps(row(text="Changed source words.")),))
        db.commit()
        assert collection.revision()!=before


def test_query_tokenizer_matches_the_recorded_index_compounds():
    tokens=bm25_tokens("Section 138 and Article 59; Order XXXIX Rule 1")
    assert {"section_138","article_59","order_xxxix_rule_1"} <= set(tokens)
