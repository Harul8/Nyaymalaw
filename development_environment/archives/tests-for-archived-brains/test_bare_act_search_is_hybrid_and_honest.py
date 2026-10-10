"""The bare-act search: the existing index, BM25 and passages, searched by meaning and by
words, reranked -- and honest about what it is. LB-106.

Owner, 29 September 2026: *"Reuse the existing bare-act vector index ... we should get
the entire vector store, BM 25, search, rerank mechanism"* -- the same data and the same
two models, the code rebuilt here; the imagined-passage search off ("use only my words
... we can use words similar to my words").

THE RULES:
1. Nothing is removed before ranking; every leg's list is merged, and no passage type is
   scored down for being unlisted (the earlier system's B-25 and Article 59 defects).
2. A set whose members disagree -- vectors, BM25, passages, the recorded model -- is
   refused, and a missing lineage record is refused, each SAID (B-05, S11).
3. What the search finds are CANDIDATES: read word for word by the one reader of
   provisions, searched and ranked, with no support verdict and the limit in their
   basis -- never the Act that governs. Acts outside the curated list, or not in force on
   the date, are set aside and said.
4. The similar wordings are anchored to the advocate's own phrases and name no law.
5. On a turn, every dispute's search results reach it as candidates; a search that
   cannot run is said on the dispute; a stopped turn searches nothing.

The real index and models were measured separately (29 September 2026, recorded in the
plan): 60 of 60 sampled passages match the vector stored at their own position, and the
four Farah Begum disputes rank Article 65/64, the Easements Act and wrongful restraint,
BNS s.115 and TPA s.53A / Registration Act s.49 first.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

import pytest

from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, Origin
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.Archives.legal_brain.retrieve.section_search_port import SectionSearch
from nm.Archives.legal_brain.understand.similar_words import interpret
from tests.test_a_disclosure_is_served_not_recorded import THREE_AT_ONCE, TODAY
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a

ON = date(2026, 9, 29)
MANIFEST = Manifest((
    ManifestEntry("Synthetic Relief Act, 1963", ("synthetic_relief_act_1963",), ("1-44",),
                  in_force_from=date(1963, 1, 1)),
    ManifestEntry("Old Penal Code, 1860", ("old_penal_code_1860",), ("1-511",),
                  in_force_from=date(1860, 1, 1), in_force_to=date(2024, 6, 30)),
))


class _Parts:
    """Stand-in for the loaded index and models: fixed lists and scores."""

    def __init__(self, passages, *, bm25=(), vectors=(), scores=None):
        self._passages = {p.position: p for p in passages}
        self._bm25, self._vectors = list(bm25), list(vectors)
        self._scores = scores or {}
        self.asked = []

    def vector_top(self, wordings, depth):
        self.asked.append(("vectors", tuple(wordings)))
        return [list(self._vectors) for _ in wordings]

    def bm25_top(self, wording, depth):
        self.asked.append(("bm25", wording))
        return list(self._bm25)

    def passages(self, positions):
        return [self._passages[p] for p in positions if p in self._passages]

    def rerank(self, wordings, texts):
        return [self._scores.get(t, 0.1) for t in texts]


def _passage(pos, act_id, section, text):
    return hybrid.Passage(pos, act_id, act_id, section, text)


def _reader(calls):
    def read(act, section, as_of):
        calls.append((act, section))
        return EvidenceResult(coverage=Coverage.ANSWERED, findings=(finding(
            proposition=f"{act} s.{section}", ref=f"{act} s.{section}",
            span=f"The text of {act} s.{section}.", locator=f"{act}::{section}",
            store=act, binding_reason="the current text of this provision as held"),),
            searched_stores=(act,))
    return read


def _search(parts, calls=None):
    return hybrid.HybridSections(
        ".", MANIFEST, read_provision=_reader([] if calls is None else calls),
        models=".", lineage="missing.json", parts=parts)


# ============================ 1. nothing removed ==============================

def test_every_leg_is_merged_and_nothing_is_removed_before_ranking():
    merged = hybrid.fused([[5, 1, 9], [9, 2], [7]])
    assert set(merged) == {1, 2, 5, 7, 9}, "a ranked position was dropped before ranking"
    assert merged[9] > merged[5] and merged[9] > merged[7], (
        "a passage both legs rank must outrank one only one leg ranks")


def test_an_unusual_passage_type_is_ranked_on_its_score_alone():
    """The Article 59 defect: a type missing from a priors table scored below all others."""
    parts = _Parts(
        [_passage(1, "synthetic_relief_act_1963", "Article_59", "a schedule article"),
         _passage(2, "synthetic_relief_act_1963", "10", "an ordinary section")],
        bm25=[2, 1], vectors=[2, 1],
        scores={"a schedule article": 0.97, "an ordinary section": 0.40})
    found = _search(parts).search("the dispute's words", as_of=ON)
    assert found.ran and found.candidates[0].ref.endswith("Article_59")


# ========================= 2. refused, and said so ============================

def _artefacts(tmp_path, *, vectors=3, docs=3, passages=3):
    import faiss
    import numpy as np

    index = faiss.IndexFlatIP(hybrid.DIMENSIONS)
    rows = np.random.default_rng(1).standard_normal((vectors, hybrid.DIMENSIONS)).astype("float32")
    index.add(rows / np.linalg.norm(rows, axis=1, keepdims=True))
    faiss.write_index(index, str(tmp_path / "bare.index"))
    (tmp_path / "bm25").mkdir()
    params = tmp_path / "bm25" / "params.index.json"
    params.write_text(json.dumps({"num_docs": docs}))
    with sqlite3.connect(tmp_path / "chunks.db") as con:
        con.execute("create table chunks (doc_type, pos, chunk_id, act_id, case_id, "
                    "parent_chunk_id, atom_type, section_number, blob)")
        for pos in range(passages):
            con.execute("insert into chunks values ('bare_act', ?, ?, 'a', null, null, "
                        "'section_head', '1', '{}')", (pos, f"c{pos}"))
    return {"schema": 1, "doc_type": "bare_act", "model": hybrid.EMBED_MODEL,
            "dimensions": hybrid.DIMENSIONS, "passages": 3,
            "vector_index": {"path": "bare.index", "vectors": 3,
                             "bytes": (tmp_path / "bare.index").stat().st_size},
            "bm25": {"path": "bm25", "num_docs": 3,
                     "params_sha256": hashlib.sha256(params.read_bytes()).hexdigest()},
            "passage_store": {"path": "chunks.db"}}


def test_a_consistent_set_passes_its_lineage(tmp_path):
    assert hybrid.check_lineage(_artefacts(tmp_path), tmp_path) == []


def test_bm25_parameters_changed_without_changing_the_count_are_refused(tmp_path):
    record = _artefacts(tmp_path)
    (tmp_path / "bm25" / "params.index.json").write_text(
        json.dumps({"num_docs": 3, "method": "changed"}))
    assert any("BM25 parameters changed" in problem
               for problem in hybrid.check_lineage(record, tmp_path))


@pytest.mark.parametrize("change", ["vectors", "bm25", "passages", "model", "resized"])
def test_a_set_that_disagrees_with_its_lineage_is_refused(tmp_path, change):
    record = _artefacts(tmp_path, vectors=4 if change == "vectors" else 3,
                        docs=4 if change == "bm25" else 3,
                        passages=4 if change == "passages" else 3)
    if change == "vectors":
        record["vector_index"]["bytes"] = (tmp_path / "bare.index").stat().st_size
    if change == "model":
        record["model"] = "sentence-transformers/all-MiniLM-L6-v2"
    if change == "resized":
        record["vector_index"]["bytes"] += 1
    assert hybrid.check_lineage(record, tmp_path), f"a changed {change} was not refused"


def test_with_no_lineage_record_the_search_does_not_run_and_says_why(tmp_path):
    search = hybrid.HybridSections(tmp_path, MANIFEST, read_provision=_reader([]),
                                   models=tmp_path, lineage=tmp_path / "none.json")
    found = search.search("words", as_of=ON)
    assert not found.ran and "lineage" in found.note
    assert search.readiness().startswith("unavailable:")


def test_a_vector_with_no_passage_is_dropped_not_remapped():
    import faiss
    import numpy as np

    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1, 0], [0.9, 0.1], [0.8, 0.2]], dtype="float32"))

    class _Encoder:
        def encode(self, texts, **_):
            return np.array([[1.0, 0.0]] * len(texts), dtype="float32")

    parts = hybrid._Parts(index, None, None, _Encoder(), None, passages=2)
    assert parts.vector_top(["q"], 3) == [[0, 1]], "a vector past the passage store was kept"


# ======================== 3. candidates, never law ============================

def test_found_sections_are_read_exactly_and_returned_as_candidates():
    calls = []
    parts = _Parts([_passage(1, "synthetic_relief_act_1963", "10", "section ten text")],
                   bm25=[1], vectors=[1], scores={"section ten text": 0.9})
    found = _search(parts, calls).search("the dispute's words", as_of=ON)
    assert calls == [("Synthetic Relief Act, 1963", "10")], (
        "the section's text must come from the one reader of provisions")
    candidate = found.candidates[0]
    assert candidate.origin is Origin.SEARCHED and candidate.confidence == 0.9
    assert candidate.supports is None and not candidate.usable and candidate.quotable
    assert "whether it governs has not been assessed" in candidate.binding_reason


def test_acts_outside_the_curated_list_or_not_in_force_are_set_aside_and_said():
    parts = _Parts(
        [_passage(1, "some_other_act_1999", "4", "outside"),
         _passage(2, "old_penal_code_1860", "323", "repealed"),
         _passage(3, "synthetic_relief_act_1963", "6", "kept")],
        bm25=[1, 2, 3], vectors=[1, 2, 3],
        scores={"outside": 0.99, "repealed": 0.98, "kept": 0.5})
    found = _search(parts).search("words", as_of=ON)
    assert [c.ref for c in found.candidates] == ["Synthetic Relief Act, 1963 s.6"]
    assert "not in force on 2026-09-29" in found.note and "Old Penal Code" in found.note
    assert "outside the curated Acts" in found.note and "some_other_act_1999" in found.note


def test_the_similar_wordings_are_searched_beside_the_advocate_s_words():
    parts = _Parts([_passage(1, "synthetic_relief_act_1963", "6", "t")], bm25=[1], vectors=[1])
    _search(parts).search("he took my land", similar=("dispossession of immovable property",),
                          as_of=ON)
    assert ("bm25", "dispossession of immovable property") in parts.asked
    assert ("vectors", ("he took my land", "dispossession of immovable property")) in parts.asked


# ===================== 4. similar words: anchored, no law =====================

def test_a_wording_must_be_anchored_to_the_advocate_s_words_and_name_no_law():
    words = "He pushed her down and injured her knee near the gate."
    data = {"phrases": [
        {"quoted": "pushed her down and injured her knee",
         "wordings": ["voluntarily causing hurt", "Bharatiya Nyaya Sanhita hurt",
                      "section 115 hurt", "assault or criminal force"]},
        {"quoted": "stole her car", "wordings": ["theft of a motor vehicle"]},
    ]}
    assert interpret(data, words) == (
        "pushed her down and injured her knee", "voluntarily causing hurt",
        "assault or criminal force")


def test_each_later_anchored_phrase_gets_query_space_before_extra_variants():
    phrases = ("first event", "second event", "third event", "fourth event")
    words = "; ".join(phrases)
    data = {"phrases": [
        {"quoted": phrase, "wordings": [f"{name} description",
                                          f"{name} alternative", f"{name} additional"]}
        for phrase, name in zip(phrases, ("alpha", "beta", "gamma", "delta"))
    ]}
    chosen = interpret(data, words)
    assert len(chosen) == 8
    assert chosen[:4] == phrases
    assert chosen[4:] == tuple(f"{name} description" for name in
                               ("alpha", "beta", "gamma", "delta"))
    parts = _Parts([_passage(1, "synthetic_relief_act_1963", "6", "t")],
                   bm25=[1], vectors=[1])
    _search(parts).search(words, similar=chosen, as_of=ON)
    assert ("vectors", (words, *chosen)) in parts.asked


def test_an_unanchored_or_law_naming_variant_cannot_use_the_search_budget():
    words = "The owner blocked the gate, and the visitor fell."
    data = {"phrases": [
        {"quoted": "blocked the gate", "wordings": [
            "obstructed entry", "section 341 wrongful restraint"]},
        {"quoted": "stole a car", "wordings": ["vehicle theft"]},
        {"quoted": "the visitor fell", "wordings": ["personal injury"]},
    ]}
    chosen = interpret(data, words)
    assert chosen == ("blocked the gate", "the visitor fell",
                      "obstructed entry", "personal injury")
    assert "vehicle theft" not in chosen
    assert "section 341 wrongful restraint" not in chosen


def test_only_an_exact_fragment_of_an_imprecise_model_quote_is_searched():
    words = ("She signed an unregistered agreement dated years ago and later "
             "asked for a sale deed.")
    data = {"phrases": [
        {"quoted": "unregistered agreement for sale",
         "wordings": ["registration required for a sale contract"]},
        {"quoted": "forged title to the property",
         "wordings": ["fraudulent conveyance"]},
    ]}
    chosen = interpret(data, words)
    assert chosen == ("unregistered agreement",)
    assert "registration required for a sale contract" not in chosen
    assert "fraudulent conveyance" not in chosen


# ========================== 5. on the served turn =============================

class _Port:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def search(self, words, *, similar=(), as_of, limit=5):
        self.calls.append(words)
        if self.result is not None:
            return self.result
        return SectionSearch(True, (finding(
            proposition="Searched Act, 1990 s.9", ref="Searched Act, 1990 s.9",
            span="A searched section's words.", locator=f"searched::9::{len(self.calls)}",
            origin=Origin.SEARCHED, confidence=0.9, supports=None,
            binding_reason="found by search -- whether it governs has not been assessed"),),
            note="searched")

    def readiness(self):
        return "ready"


def _engine(tmp_path, port):
    engine, store = build(tmp_path, evidence=_Evidence())
    engine.inner._sections = port
    return engine


def _relying_needs(user):
    """A controlled needs read that relies on the searched section it was given."""
    shown = "Searched Act, 1990 s.9" in user
    return json.dumps({"requirements": [{
        "need": "Show the searched section's condition is met on this file.",
        "why": "The section found by search sets it.",
        "span": "A searched section's words.", "source": "Searched Act, 1990 s.9",
        "force": "required", "answer": "", "answer_quote": "", "due_expression": ""}]
        if shown else []})


def test_a_searched_section_reaches_the_reply_only_where_the_disputes_needs_rely_on_it(
        tmp_path, monkeypatch):
    """THE RULE CHANGED, BY THE OWNER, 30 September 2026 (LB-76 change 4). Sections
    found by search were held back and never reached a reply, so the Farah Begum
    reply quoted no law at all. Now a searched section is shown -- its words, its
    saved passage for the reader, and the limit that it was found by search with
    its applicability unconfirmed -- WHERE THE DISPUTE'S NEEDS READ, reading the
    passage against the dispute, RELIES ON IT. Shown by rerank order alone, a push
    was answered with homicide and acid-attack sections. Search ranks; the reading
    decides what is shown; neither decides which Act governs."""
    from nm.shared.model_scripted import SCRIPTED_READS

    port = _Port()
    out = _engine(tmp_path, port).run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE,
                                                today=TODAY))
    assert len(port.calls) == len(out.matter.threads) == 3, "a dispute was not searched"
    assert not [e for e in out.answer.elements if "A searched section" in e.text], (
        "a searched section nothing relied on reached the reply")

    monkeypatch.setitem(SCRIPTED_READS, "requirements", _relying_needs)
    port = _Port()
    out = _engine(tmp_path / "relied", port).run(TurnInput(
        advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    shown = [e for e in out.answer.elements if "A searched section" in e.text]
    assert shown, "a searched section the needs relied on did not reach the reply"
    for e in shown:
        assert e.disclosure and e.source is not None and e.refs == (e.source.locator,)
        assert "Found by search for this dispute; whether it applies has not been " \
               "confirmed." in e.text
    for thread in out.matter.threads:
        assert not any("searched::" in f.locator for f in thread.authorities), (
            "a search candidate was recorded as law the dispute rests on")


def test_a_search_that_cannot_run_is_said_on_the_dispute(tmp_path):
    port = _Port(SectionSearch(False, note="the search models are not installed on this machine"))
    out = _engine(tmp_path, port).run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE,
                                                today=TODAY))
    said = [e for e in out.answer.elements
            if "could not search the bare acts by meaning" in e.text]
    assert said and all(e.disclosure for e in said)
    assert "not installed" in said[0].text


def test_a_stopped_turn_searches_nothing(tmp_path):
    port = _Port()
    out = _engine(tmp_path, port).run(TurnInput(advocate_id="adv",
                                                message="a cheque was dishonoured on 3 March"))
    assert out.answer.blocked and port.calls == []


def test_the_served_app_admits_the_search_and_reports_it(tmp_path, monkeypatch,
                                                         scripted_application_environment):
    from pathlib import Path

    from nm.app.composition import Application
    from nm.arrive.store_directory import FileDirectory
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_immutable_corpus_publication import _scripted_model
    from tests.test_turn_contract import KEY

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "bareacts_v3.index").write_bytes(b"not loaded at start")
    monkeypatch.setenv("NM_CORPUS_DIR", str(corpus))
    for name in ("NM_AUTHORITY_INDEX", "NM_IDENTITY_INDEX"):
        monkeypatch.delenv(name, raising=False)
    app = Application(root=Path(__file__).resolve().parents[1],
                      store=FileMatterStore(tmp_path / "matters", key=KEY),
                      directory=FileDirectory(tmp_path / "matters", key=KEY),
                      model=_scripted_model())
    assert app.sections is not None and app.engine._sections is app.sections
    assert app.health()["section_search"] == "not loaded", (
        "nothing may load at construction, and the health line must say so")
