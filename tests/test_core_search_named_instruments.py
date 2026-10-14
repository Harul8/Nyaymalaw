"""Search inside the Acts a research plan names, and the blended provision order
(owner decision, 12 Oct 2026; search contract v6, carried into v7).

A named Act proposes held instruments by the shared instrument key: its exact key,
else every held key with the same title apart from the year. Word and vector search
inside those instruments joins each formulation's legs. An unreadable register costs
only the named legs, with an explicit gap. Provisions are ordered by blending the
reranker's order with the fused shortlist's order; each candidate keeps the
reranker's own score. Saved v5 and v6 records replay unchanged.
"""
from copy import deepcopy
import json

import pytest

from nm.core_engine import retrieval
from nm.core_engine.retrieval import HybridSearcher, validate_search
from tests.test_core_statute_readback import _local, _row
from tests.test_current_brain_retrieval import Collection, QUERIES

ROWS = [_row("contract-act", "170", "Bailee's particular lien over goods bailed."),
        _row("other-act", "1", "Words that share the advocate's vocabulary."),
        _row("other-act", "2", "More words that share the advocate's vocabulary."),
        _row("consumer-1986", "2", "Old consumer definitions."),
        _row("consumer-2019", "2", "New consumer definitions.")]
DOCUMENTS = {
    "contract-act": {"role": "kept", "group": "indian contract act 1872", "shown_title": "The Indian Contract Act, 1872"},
    "other-act": {"role": "kept", "group": "other act 1999", "shown_title": "Other Act, 1999"},
    "consumer-1986": {"role": "kept", "group": "consumer protection act 1986", "shown_title": "Consumer Protection Act, 1986"},
    "consumer-2019": {"role": "kept", "group": "consumer protection act 2019", "shown_title": "Consumer Protection Act, 2019"},
}


def collection(tmp_path, monkeypatch, documents=DOCUMENTS, *, general=(1, 2), rerank=None):
    held = _local(tmp_path, ROWS)
    path = tmp_path / "instrument_copies.json"
    path.write_text(json.dumps({"schema": 1, "documents": documents}), encoding="utf-8")
    held.copies = path
    calls = []
    monkeypatch.setattr(held, "lexical", lambda query, depth: list(general))
    monkeypatch.setattr(held, "semantic", lambda query, depth: list(general))
    monkeypatch.setattr(held, "lexical_within",
                        lambda query, depth, allowed: calls.append(("words", sorted(allowed))) or sorted(allowed))
    monkeypatch.setattr(held, "semantic_many_within",
                        lambda queries, depth, allowed: calls.append(("vectors", sorted(allowed))) or [sorted(allowed) for _ in queries])
    monkeypatch.setattr(held, "rerank", rerank or (lambda pairs, *, anchors=None: [1.0] * len(pairs)))
    return held, calls


def search(held, instruments, queries=QUERIES):
    return HybridSearcher({"provision": held, "judgment": Collection("judgment")}).search(queries, instruments)


def test_a_named_act_is_searched_inside_and_its_section_reaches_the_shortlist(tmp_path, monkeypatch):
    held, calls = collection(tmp_path, monkeypatch)
    result = search(held, ["Indian Contract Act"])
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v7"
    assert result["instruments"] == [{"name": "Indian Contract Act", "candidates": ["indian contract act 1872"]}]
    assert ("words", [0]) in calls and ("vectors", [0]) in calls
    assert 0 in {c["position"] for c in result["candidates"] if c["kind"] == "provision"}
    assert {(s["query_id"], s["stage"]) for s in result["stages"] if s["stage"].startswith("named_")} == {
        (q["query_id"], leg) for q in QUERIES for leg in ("named_lexical", "named_semantic")}
    assert validate_search(result, QUERIES, ["Indian Contract Act"]) == result


def test_a_name_without_a_year_keeps_every_held_candidate(tmp_path, monkeypatch):
    held, calls = collection(tmp_path, monkeypatch)
    result = search(held, ["Consumer Protection Act"])
    assert result["instruments"][0]["candidates"] == ["consumer protection act 1986", "consumer protection act 2019"]
    assert ("words", [3, 4]) in calls
    assert validate_search(result, QUERIES, ["Consumer Protection Act"]) == result


def test_an_unheld_name_adds_no_legs_and_still_records_the_name(tmp_path, monkeypatch):
    held, calls = collection(tmp_path, monkeypatch)
    result = search(held, ["Code of Civil Procedure"])
    assert result["instruments"] == [{"name": "Code of Civil Procedure", "candidates": []}]
    assert not calls and not any(s["stage"].startswith("named_") for s in result["stages"])
    assert result["state"] == "ready"
    assert validate_search(result, QUERIES, ["Code of Civil Procedure"]) == result


def test_an_unreadable_register_costs_only_the_named_legs(tmp_path, monkeypatch):
    held, calls = collection(tmp_path, monkeypatch)
    held.copies.write_text("not json", encoding="utf-8")
    result = search(held, ["Indian Contract Act"])
    assert not calls
    assert {"kind": "provision", "query_id": None, "stage": "instruments", "reason": "SearchUnavailable"} in result["issues"]
    assert result["state"] == "partial" and any(c["kind"] == "provision" for c in result["candidates"])
    assert validate_search(result, QUERIES, ["Indian Contract Act"]) == result


def test_provisions_blend_the_reranker_order_with_the_shortlist_order(tmp_path, monkeypatch):
    words = {"Bailee": 0.5, "Words": 0.1, "More": 0.9}

    def rerank(pairs, *, anchors=None):
        return [next(score for start, score in words.items() if text.startswith(start)) for _, text in pairs]
    held, _ = collection(tmp_path, monkeypatch, rerank=rerank)
    result = search(held, ["Indian Contract Act"])
    order = [c["position"] for c in result["candidates"] if c["kind"] == "provision"]
    scores = {c["position"]: c["score"] for c in result["candidates"] if c["kind"] == "provision"}
    # Shortlist: 0 (first in both named legs), 1, 2. Reranker alone: 2, 0, 1.
    blended = {0: 1 / 61 + 1 / 62, 1: 1 / 62 + 1 / 63, 2: 1 / 63 + 1 / 61}
    assert order == sorted(blended, key=lambda p: -blended[p]) == [0, 2, 1]
    assert scores == {0: 0.5, 1: 0.1, 2: 0.9}


def test_the_record_keeps_the_names_its_plan_gave(tmp_path, monkeypatch):
    held, _ = collection(tmp_path, monkeypatch)
    result = search(held, ["Indian Contract Act"])
    with pytest.raises(ValueError, match="named"):
        validate_search(result, QUERIES, ["Specific Relief Act"])
    with pytest.raises(ValueError, match="named"):
        validate_search(result, QUERIES)
    saved_v6 = deepcopy(result)  # v7 changed only the judgment order
    saved_v6["contract"] = retrieval.NAMED_CONTRACT
    assert validate_search(saved_v6, QUERIES, ["Indian Contract Act"]) == saved_v6
    saved_v5 = deepcopy(result)
    saved_v5["contract"] = retrieval.RERANK_ORDER_CONTRACT
    del saved_v5["instruments"]
    saved_v5["stages"] = [s for s in saved_v5["stages"] if not s["stage"].startswith("named_")]
    assert validate_search(saved_v5, QUERIES) == saved_v5
    with pytest.raises(ValueError, match="historical"):
        validate_search(saved_v5, QUERIES, ["Indian Contract Act"])


@pytest.mark.parametrize("instruments", [["Same"] * 2, [" "], "Indian Contract Act", [3]])
def test_named_instruments_must_be_distinct_nonblank_names(tmp_path, monkeypatch, instruments):
    held, _ = collection(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="distinct nonblank"):
        search(held, instruments)


def bare(tmp_path, count):
    from types import SimpleNamespace
    item = retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
                                     doc_type="bare_act", models=SimpleNamespace())
    item._open = lambda: ({}, None, count)
    return item


def test_word_search_within_named_instruments_ranks_only_their_passages(tmp_path):
    np = pytest.importorskip("numpy")
    from types import SimpleNamespace
    item = bare(tmp_path, 6)
    scores = np.array([9.0, 0.0, 3.0, 3.0, 7.0, 1.0])
    item._word_index = lambda: SimpleNamespace(vocab_dict={"lien": 0}, get_scores=lambda tokens: scores)
    # Position 0 scores highest overall but is outside the named Acts; ties keep stored order.
    assert item.lexical_within("bailee's lien", 3, {1, 2, 3, 5}) == [2, 3, 5]
    assert item.lexical_within("bailee's lien", 10, {1}) == []  # a zero score is no hit
    assert item.lexical_within("unknown words", 10, {2}) == []


def test_vector_search_within_named_instruments_is_an_exact_selection(tmp_path):
    np = pytest.importorskip("numpy")
    faiss = pytest.importorskip("faiss")
    from types import SimpleNamespace
    item = bare(tmp_path, 4)
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0], [0.6, 0.8]], dtype="float32"))
    item._vector_index = lambda: index
    # Two formulations; the second spans two windows, fused by reciprocal ranks.
    item.models = SimpleNamespace(encode=lambda queries: (np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]], dtype="float32"),
                                                          [(0, 1), (1, 3)]))
    first, second = item.semantic_many_within(("lien", "dispossession"), 3, {1, 2, 3})
    assert first == [1, 3, 2]  # position 0 is the global best but not named
    assert set(second) == {1, 2, 3} and second[0] in (2, 3)
    assert item.semantic_many_within(("lien",), 3, set()) == [[]]


def test_named_instruments_offer_kept_copies_and_only_the_sections_a_copy_keeps(tmp_path):
    rows = [_row("kept-act", "1"), _row("kept-act", "2"), _row("copy-act", "1"), _row("copy-act", "3"),
            _row("excluded-act", "1")]
    held = _local(tmp_path, rows)
    path = tmp_path / "instrument_copies.json"
    path.write_text(json.dumps({"schema": 1, "documents": {
        "kept-act": {"role": "kept", "group": "kept act 2000"},
        "copy-act": {"role": "copy", "group": "kept act 2000", "kept_sections": ["3"]},
        "excluded-act": {"role": "excluded", "group": "andhra area act 1956", "kept_sections": []}}}), encoding="utf-8")
    held.copies = path
    assert held.instrument_keys() == frozenset({"kept act 2000"})
    assert held.instrument_positions({"kept act 2000"}) == frozenset({0, 1, 3})
    assert held.instrument_positions({"andhra area act 1956"}) == frozenset()
