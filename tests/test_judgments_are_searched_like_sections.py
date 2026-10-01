"""Judgments are searched exactly the way bare-act sections are. LB-106.

Owner, 30 September 2026: *"extend to judgements also, both acts and judgements should be
retrieved same way"*.

THE RULES:
1. One mechanism: the same wordings reach the same two legs, merged by rank and reranked
   by the same model -- loaded ONCE for both searches.
2. Only the court's own reasoning competes: facts, counsel's arguments and unclassified
   paragraphs are set aside before reranking, and counted.
3. One paragraph per judgment, the best; each turned into a judgment Finding by the one
   owner of that -- binding computed from court and year, treatment from the citator, the
   denylist applied -- and returned as a CANDIDATE: searched, ranked, no support verdict,
   its applicability unassessed and said.
4. The judgment index is used only as its lineage record says: vectors past the last
   passage only where the record counts them, and none of them ever mapped to a passage;
   without a record the search does not run, and says why.
5. On a turn, each dispute's own words reach the judgment search; a judgment the needs
   read relies on becomes a citable passage; a search that cannot run is said.

The real artefacts were measured separately (30 September 2026, recorded in the plan):
vectors 0 to 1,015,779 answer to passages 0 to 1,015,779 with BAAI/bge-large-en-v1.5,
the last 63 vectors have no passage, and both word indexes hold each sampled passage at
its own position.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import threading
from datetime import date

import pytest

from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.retrieve import hybrid_judgments as judgments
from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from nm.Archives.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter
from nm.Archives.legal_brain.retrieve.evidence_port import (
    Binding,
    Origin,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest
from nm.Archives.legal_brain.retrieve.section_search_port import SectionSearch
from tests.test_a_disclosure_is_served_not_recorded import THREE_AT_ONCE, TODAY
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a

ON = date(2026, 9, 30)


def _row(case, chunk, kind, text, *, court="Supreme Court of India", year="2010"):
    return (chunk, {"case_id": case, "case_name": f"{case} v. State", "court": court,
                    "year": year, "paragraph_type": kind, "full_text": text})


class _Parts:
    """Stand-in for the loaded judgment index and models: fixed lists and scores."""

    def __init__(self, rows, *, ranked, scores):
        self._rows, self._ranked, self._scores = rows, list(ranked), scores
        self.reranked: list[str] = []
        self.asked: list = []

    def vector_top(self, wordings, depth):
        self.asked.append(("vectors", tuple(wordings)))
        return [list(self._ranked) for _ in wordings]

    def bm25_top(self, wording, depth):
        self.asked.append(("bm25", wording))
        return list(self._ranked)

    def rows(self, positions):
        return {p: self._rows[p] for p in positions if p in self._rows}

    def rerank(self, wordings, texts):
        self.reranked.extend(texts)
        return [self._scores.get(t, 0.1) for t in texts]


def _reader(tmp_path, denied=(), unread=(), stale=(), shadowed=()):
    if denied:
        (tmp_path / "contamination_denylist.json").write_text(
            json.dumps({"chunk_ids": list(denied)}), encoding="utf8")
    authority = tmp_path / "authority.db"
    with sqlite3.connect(authority) as con:
        con.execute("create table paras (case_id text, chunk_id text, para_type text, "
                    "text text, case_name text, court text, year text)")
        for chunk, doc in ROWS.values():
            if chunk not in unread:
                con.execute("insert into paras values (?, ?, ?, ?, ?, ?, ?)",
                            (doc["case_id"], chunk, doc["paragraph_type"],
                             "older text" if chunk in stale else doc["full_text"],
                             doc["case_name"], doc["court"], doc["year"]))
                if chunk in shadowed:
                    con.execute("insert into paras values (?, ?, ?, ?, ?, ?, ?)",
                                (doc["case_id"], chunk, doc["paragraph_type"],
                                 "later conflicting text", doc["case_name"],
                                 doc["court"], doc["year"]))
    return CorpusEvidenceAdapter(
        tmp_path, Manifest(()), authority_index=authority).judgment_findings


def _search(tmp_path, parts, denied=(), unread=(), stale=(), shadowed=()):
    return judgments.HybridJudgments(
        tmp_path, read_judgments=_reader(tmp_path, denied, unread, stale, shadowed),
        models=hybrid.SearchModels(tmp_path), lineage=tmp_path / "none.json", parts=parts)


ROWS = {
    1: _row("case_a", "a_p1", "facts", "the facts of case a"),
    2: _row("case_a", "a_p2", "ratio", "case a holds the point"),
    3: _row("case_a", "a_p3", "reasoning", "case a reasons toward it"),
    4: _row("case_b", "b_p1", "arguments", "counsel for b submitted the point"),
    5: _row("case_b", "b_p2", "order", "case b orders it"),
    6: _row("case_c", "c_p1", "unknown", "an unclassified paragraph of case c"),
}
SCORES = {"case a holds the point": 0.91, "case a reasons toward it": 0.95,
          "case b orders it": 0.62, "the facts of case a": 0.99,
          "counsel for b submitted the point": 0.99}


# ===================== 1-2. one mechanism; the court's own words ==================

def test_only_the_courts_reasoning_is_reranked_and_what_was_set_aside_is_counted(tmp_path):
    parts = _Parts(ROWS, ranked=[1, 2, 3, 4, 5, 6], scores=SCORES)
    found = _search(tmp_path, parts).search("the dispute's words", similar=("a wording",),
                                            as_of=ON, jurisdiction="Telangana")
    assert found.ran
    assert sorted(parts.reranked) == sorted(
        ["case a holds the point", "case a reasons toward it", "case b orders it"]), (
        "a paragraph that is not the court deciding, reasoning or ordering competed")
    assert "3 ranked paragraph(s) were facts, counsel's arguments or unclassified" in found.note
    assert ("bm25", "a wording") in parts.asked
    assert ("vectors", ("the dispute's words", "a wording")) in parts.asked


def test_one_paragraph_per_judgment_the_best_the_reranker_found(tmp_path):
    parts = _Parts(ROWS, ranked=[2, 3, 5], scores=SCORES)
    found = _search(tmp_path, parts).search("words", as_of=ON, jurisdiction="Telangana")
    assert [f.locator for f in found.candidates] == ["case_a::a_p3::reasoning",
                                                     "case_b::b_p2::order"]


# ======================= 3. a judgment Finding, as a candidate =====================

def test_each_candidate_is_a_judgment_finding_from_the_one_owner(tmp_path):
    parts = _Parts(ROWS, ranked=[2], scores=SCORES)
    candidate, = _search(tmp_path, parts).search("words", as_of=ON,
                                                 jurisdiction="Telangana").candidates
    assert candidate.source_kind is SourceKind.AUTHORITY
    assert candidate.ref.startswith("case_a v. State (Supreme Court of India, 2010")
    assert candidate.store == "authority_index", "the reader must be able to open it"
    assert candidate.para_kind is ParaKind.ATTRIBUTABLE
    assert candidate.binding is Binding.BINDING, "binding is computed from court and year"
    assert candidate.origin is Origin.SEARCHED and candidate.confidence == 0.91
    assert candidate.supports is None and not candidate.usable and candidate.quotable
    assert candidate.binding_reason.endswith(
        "whether it applies to this dispute has not been assessed")


def test_a_denylisted_paragraph_is_held_back_and_counted(tmp_path):
    parts = _Parts(ROWS, ranked=[2, 3, 5], scores=SCORES)
    found = _search(tmp_path, parts, denied=("b_p2",)).search("words", as_of=ON,
                                                              jurisdiction="Telangana")
    assert [f.locator for f in found.candidates] == ["case_a::a_p3::reasoning"]
    assert "1 were held back because the corpus's own contamination denylist" in found.note


def test_a_ranked_paragraph_the_reader_cannot_open_is_set_aside_and_said(tmp_path):
    parts = _Parts(ROWS, ranked=[2, 5], scores=SCORES)
    found = _search(tmp_path, parts, unread=("b_p2",)).search(
        "words", as_of=ON, jurisdiction="Telangana")
    assert [f.locator for f in found.candidates] == ["case_a::a_p2::ratio"]
    assert "1 ranked judgment paragraph(s) could not be verified" in found.note


def test_a_paragraph_whose_reader_text_disagrees_is_set_aside_and_said(tmp_path):
    parts = _Parts(ROWS, ranked=[2, 5], scores=SCORES)
    found = _search(tmp_path, parts, stale=("b_p2",)).search(
        "words", as_of=ON, jurisdiction="Telangana")
    assert [f.locator for f in found.candidates] == ["case_a::a_p2::ratio"]
    assert "1 ranked judgment paragraph(s) could not be verified" in found.note


def test_a_duplicate_reader_locator_must_agree_with_the_passage_it_opens(tmp_path):
    parts = _Parts(ROWS, ranked=[2, 5], scores=SCORES)
    found = _search(tmp_path, parts, shadowed=("b_p2",)).search(
        "words", as_of=ON, jurisdiction="Telangana")
    assert [f.locator for f in found.candidates] == ["case_a::a_p2::ratio"]
    assert "1 ranked judgment paragraph(s) could not be verified" in found.note


def test_a_reader_with_different_court_cannot_lend_binding_to_a_search_hit(tmp_path):
    read = _reader(tmp_path)
    chunk, doc = ROWS[2]
    found, held = read(
        [(doc["case_id"], doc["case_name"], "Telangana High Court", doc["year"],
          doc["paragraph_type"], chunk, doc["full_text"], 0.9)],
        proposition="words", jurisdiction="Telangana", governing_date=ON)
    assert not found and held == 0


def test_without_the_paragraph_reader_the_search_does_not_offer_unopenable_citations(tmp_path):
    parts = _Parts(ROWS, ranked=[2], scores=SCORES)
    missing_reader = CorpusEvidenceAdapter(tmp_path, Manifest(())).judgment_findings
    search = judgments.HybridJudgments(
        tmp_path, read_judgments=missing_reader,
        models=hybrid.SearchModels(tmp_path), lineage=tmp_path / "none.json", parts=parts)
    found = search.search("words", as_of=ON, jurisdiction="Telangana")
    assert not found.ran and not found.candidates
    assert "paragraph reader is unavailable" in found.note


def test_the_word_search_and_the_meaning_search_build_a_judgment_the_same_way(tmp_path):
    """ONE OWNER: the older word search builds its Findings through the same method."""
    reader = _reader(tmp_path).__self__
    found, held = reader.judgment_findings(
        [("case_a", "case_a v. State", "Supreme Court of India", "2010", "ratio", "a_p2",
          "case a holds the point", 0.5),
         ("case_b", "case_b v. State", "Supreme Court of India", "2010", "facts", "b_p1",
          "the facts", 0.9)],
        proposition="words", jurisdiction="Telangana", governing_date=ON)
    assert set(found) == {"a_p2"} and held == 0, "a paragraph of facts became a Finding"
    import inspect

    source = inspect.getsource(CorpusEvidenceAdapter._fetch_authority)
    assert "self._judgment_finding(" in source and "Finding(" not in source, (
        "the word search builds judgment Findings its own way")


# ===================== 4. the lineage, and the models loaded once ===================

def _artefacts(tmp_path, *, vectors, passages):
    import faiss
    import numpy as np

    index = faiss.IndexFlatIP(hybrid.DIMENSIONS)
    rows = np.random.default_rng(2).standard_normal((vectors, hybrid.DIMENSIONS)).astype("float32")
    index.add(rows / np.linalg.norm(rows, axis=1, keepdims=True))
    faiss.write_index(index, str(tmp_path / "cases.index"))
    (tmp_path / "bm25").mkdir()
    params = tmp_path / "bm25" / "params.index.json"
    params.write_text(json.dumps({"num_docs": passages}))
    with sqlite3.connect(tmp_path / "chunks.db") as con:
        con.execute("create table chunks (doc_type, pos, chunk_id, act_id, case_id, "
                    "parent_chunk_id, atom_type, section_number, blob)")
        for pos in range(passages):
            con.execute("insert into chunks values ('case_law', ?, ?, null, 'c', null, "
                        "'ratio', null, '{}')", (pos, f"c{pos}"))
    return {"schema": 1, "doc_type": "case_law", "model": hybrid.EMBED_MODEL,
            "dimensions": hybrid.DIMENSIONS, "passages": passages,
            "vectors_without_passage": vectors - passages,
            "vector_index": {"path": "cases.index", "vectors": vectors,
                             "bytes": (tmp_path / "cases.index").stat().st_size},
            "bm25": {"path": "bm25", "num_docs": passages,
                     "params_sha256": hashlib.sha256(params.read_bytes()).hexdigest()},
            "passage_store": {"path": "chunks.db"}}


def test_vectors_past_the_last_passage_are_accepted_only_as_recorded(tmp_path):
    record = _artefacts(tmp_path, vectors=5, passages=3)
    assert hybrid.check_lineage(record, tmp_path, doc_type="case_law") == []
    for miscounted in (0, 1, 3):
        assert hybrid.check_lineage({**record, "vectors_without_passage": miscounted},
                                    tmp_path, doc_type="case_law"), (
            f"{miscounted} vector(s) without a passage was accepted for an index with 2")
    assert hybrid.check_lineage(record, tmp_path), "a judgment record passed as bare acts"


def test_fewer_vectors_than_passages_is_refused(tmp_path):
    record = _artefacts(tmp_path, vectors=3, passages=4)
    assert hybrid.check_lineage(record, tmp_path, doc_type="case_law")


@pytest.mark.parametrize("no_indexed,own_position", [(1, 0), (0, 0)])
def test_lineage_is_not_written_when_the_word_index_cannot_verify_a_passage(
        tmp_path, monkeypatch, no_indexed, own_position):
    from pipeline import record_retrieval_lineage as lineage

    (tmp_path / "cases.index").write_bytes(struct.pack("<4siq", b"IxFI", 1024, 1))
    (tmp_path / "bm25").mkdir()
    (tmp_path / "bm25" / "params.index.json").write_text(
        json.dumps({"num_docs": 1}), encoding="utf8")
    with sqlite3.connect(tmp_path / "chunks.db") as con:
        con.execute("create table chunks (doc_type text, pos integer)")
        con.execute("insert into chunks values ('case_law', 0)")
    monkeypatch.setattr(lineage, "VECTOR_STORE", tmp_path)
    monkeypatch.setattr(lineage, "LINEAGE", tmp_path / "records")
    monkeypatch.setattr(lineage, "verify_vectors", lambda *_: {
        "sampled": 1, "same_vector": 1, "lowest_similarity": 1.0,
        "mean_similarity": 1.0, "cut_at": [256], "device": "cpu"})
    monkeypatch.setattr(lineage, "verify_words", lambda *_: {
        "sampled": 1, "own_position": own_position, "no_indexed_words": no_indexed})
    collection = lineage.Collection("test", "case_law", "cases.index", "bm25", (256,))
    assert lineage.record_one(collection, samples=1, check=False) == 1
    assert not collection.out.exists(), "a lineage record was written without word evidence"


def test_a_vector_past_the_last_passage_is_never_mapped():
    import faiss
    import numpy as np

    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1, 0], [0.9, 0.1], [0.8, 0.2]], dtype="float32"))

    class _Encoder:
        def encode(self, texts, **_):
            return np.array([[1.0, 0.0]] * len(texts), dtype="float32")

    parts = hybrid._Parts(index, None, None, _Encoder(), None, 2, doc_type="case_law")
    assert parts.vector_top(["q"], 3) == [[0, 1]]


def test_without_a_lineage_record_the_judgment_search_does_not_run_and_says_why(tmp_path):
    search = judgments.HybridJudgments(tmp_path, read_judgments=_reader(tmp_path),
                                       models=hybrid.SearchModels(tmp_path),
                                       lineage=tmp_path / "none.json")
    found = search.search("words", as_of=ON, jurisdiction="Telangana")
    assert not found.ran and "lineage" in found.note
    assert search.readiness().startswith("unavailable:")


def test_both_searches_load_one_set_of_models_once(tmp_path, monkeypatch):
    models = hybrid.SearchModels(tmp_path)
    opened = []
    gate = threading.Barrier(4)

    def open_once():
        opened.append(1)
        return ("embedder", "reranker", threading.Lock())

    monkeypatch.setattr(models, "_open", open_once)
    sections = hybrid.HybridSections(tmp_path, Manifest(()), read_provision=None,
                                     models=models, lineage=tmp_path / "a.json")
    cases = judgments.HybridJudgments(tmp_path, read_judgments=None, models=models,
                                      lineage=tmp_path / "b.json")
    assert sections._models is cases._models is models

    def load():
        gate.wait()
        models.load()

    workers = [threading.Thread(target=load) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert len(opened) == 1, "the models were loaded more than once"
    assert models.load()[2] is models.load()[2], "the two searches would not share one lock"


# =============================== 5. on the served turn ==============================

class _Port:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def search(self, words, *, similar=(), as_of, jurisdiction, limit=4):
        self.calls.append(words)
        if self.result is not None:
            return self.result
        return SectionSearch(True, (finding(
            proposition="words", source_kind=SourceKind.AUTHORITY,
            ref="Searched v. State (Supreme Court of India, 2010)",
            span="A searched judgment's reasoning.",
            locator=f"searched::p{len(self.calls)}::ratio", store="authority_index",
            para_kind=ParaKind.ATTRIBUTABLE, treatment=Treatment.not_checked("no entry"),
            valid_from=None, origin=Origin.SEARCHED, confidence=0.9, supports=None,
            binding_reason="found by search -- whether it applies has not been assessed"),),
            note="searched")

    def readiness(self):
        return "ready"


def _relying_needs(user):
    """A controlled needs read that relies on the searched judgment it was given."""
    shown = "Searched v. State" in user
    return json.dumps({"requirements": [{
        "need": "Show the court's condition is met on this file.",
        "why": "The judgment found by search sets it.",
        "span": "A searched judgment's reasoning.",
        "source": "Searched v. State (Supreme Court of India, 2010)",
        "force": "required", "answer": "", "answer_quote": "", "due_expression": ""}]
        if shown else []})


def test_each_dispute_is_searched_for_judgments_and_a_relied_judgment_is_citable(
        tmp_path, monkeypatch):
    from nm.shared.model_scripted import SCRIPTED_READS

    monkeypatch.setitem(SCRIPTED_READS, "requirements", _relying_needs)
    port = _Port()
    engine, _ = build(tmp_path, evidence=_Evidence())
    engine.inner._judgments = port
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(port.calls) == len(set(port.calls)) == len(out.matter.threads) == 3, (
        "a dispute was not searched for judgments on its own words")
    shown = [e for e in out.answer.elements if "A searched judgment" in e.text]
    assert shown, "a judgment the needs relied on did not reach the reply"
    for element in shown:
        assert element.disclosure and element.source is not None
        assert element.refs == (element.source.locator,)
        assert "Found by search for this dispute; whether it applies has not been " \
               "confirmed." in element.text
    for thread in out.matter.threads:
        assert not any(f.locator.startswith("searched::") for f in thread.authorities), (
            "a judgment candidate was recorded as law the dispute rests on")


def test_a_judgment_search_that_cannot_run_is_said_on_the_dispute(tmp_path):
    port = _Port(SectionSearch(False, note="the search index has no lineage record"))
    engine, _ = build(tmp_path, evidence=_Evidence())
    engine.inner._judgments = port
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    said = [e for e in out.answer.elements
            if "could not search the judgments by meaning" in e.text]
    assert len(said) == 3 and all(e.disclosure for e in said)
    assert "no lineage record" in said[0].text


def test_the_served_app_wires_both_searches_on_one_set_of_models(
        tmp_path, monkeypatch, scripted_application_environment):
    """On the composition root, not on a hand-built engine (CLAUDE.md section 8)."""
    from pathlib import Path

    from nm.app.composition import Application
    from nm.arrive.store_directory import FileDirectory
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_immutable_corpus_publication import _scripted_model
    from tests.test_turn_contract import KEY

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "bareacts_v3.index").write_bytes(b"not loaded at start")
    (corpus / "caselaws_v2.index").write_bytes(b"not loaded at start")
    monkeypatch.setenv("NM_CORPUS_DIR", str(corpus))
    for name in ("NM_AUTHORITY_INDEX", "NM_IDENTITY_INDEX"):
        monkeypatch.delenv(name, raising=False)
    app = Application(root=Path(__file__).resolve().parents[1],
                      store=FileMatterStore(tmp_path / "matters", key=KEY),
                      directory=FileDirectory(tmp_path / "matters", key=KEY),
                      model=_scripted_model())
    assert app.judgments is not None and app.engine._judgments is app.judgments
    assert app.sections.inner._models is app.judgments.inner._models, (
        "the two searches would load the models twice")
    assert app.health()["judgment_search"] == "not loaded", (
        "nothing may load at construction, and the health line must say so")


def test_a_stopped_turn_searches_no_judgments(tmp_path):
    port = _Port()
    engine, _ = build(tmp_path, evidence=_Evidence())
    engine.inner._judgments = port
    out = engine.run(TurnInput(advocate_id="adv",
                               message="a cheque was dishonoured on 3 March"))
    assert out.answer.blocked and port.calls == []
