"""Searches running side by side never share a tokenizer, and a matter's questions searched
together each find what they find alone (owner, 20 Oct 2026: step 1; four searches at once had
lost a judgment ranking to a shared tokenizer's settings)."""
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from nm.core_engine import retrieval
from tests.test_core_rerank_window_reuse import CountingTokenizer, Predictor, long_pairs, reference_rerank
from tests.test_current_brain_retrieval import Collection, QUERIES

pytestmark = pytest.mark.class_a


class Forbidden:
    """A model's own tokenizer, which only its prediction may use."""

    def __call__(self, *args, **kwargs):
        raise AssertionError("text preparation used the model's own tokenizer")

    encode = num_special_tokens_to_add = __call__


def test_text_is_prepared_with_a_borrowed_copy_never_the_models_own_tokenizer(tmp_path):
    model, copy, expected = Predictor(), CountingTokenizer(), Predictor()
    model.tokenizer = Forbidden()
    lent = []

    @contextmanager
    def borrowed(which):
        lent.append(which)
        yield copy
    models = SimpleNamespace(_model=lambda _: model, lock=threading.RLock(), borrowed=borrowed)
    collection = retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
                                           doc_type="bare_act", models=models)
    pairs = long_pairs()
    assert collection.rerank(pairs) == reference_rerank(pairs, expected)
    assert model.calls == expected.calls and lent == ["reranking"] and copy.calls


class Tokenizer:
    """Stands in for a model's tokenizer: each copy is its own object."""


def models(monkeypatch, tmp_path):
    held = retrieval._Models(tmp_path)
    owned = {which: SimpleNamespace(tokenizer=Tokenizer()) for which in ("embedding", "reranking")}
    monkeypatch.setattr(held, "_model", lambda which: owned[which])
    return held, owned


def test_borrowed_copies_are_never_shared_and_stay_within_their_number(monkeypatch, tmp_path):
    held, owned = models(monkeypatch, tmp_path)
    count = retrieval.TOKENIZER_COPIES
    inside, all_in, release, lent = threading.Lock(), threading.Barrier(count + 1, timeout=10), threading.Event(), []

    def borrow():
        with held.borrowed("reranking") as tokenizer:
            with inside:
                lent.append(tokenizer)
            all_in.wait()
            release.wait(10)
    threads = [threading.Thread(target=borrow) for _ in range(count)]
    for thread in threads:
        thread.start()
    all_in.wait()
    assert len({id(t) for t in lent}) == count and all(t is not owned["reranking"].tokenizer for t in lent)
    waiting = threading.Thread(target=lambda: lent.append(held._borrow("reranking")))
    waiting.start()
    waiting.join(0.3)
    assert waiting.is_alive()  # one more borrower waits for a copy to come back
    release.set()
    for thread in threads:
        thread.join(10)
    waiting.join(10)
    assert lent[-1] in lent[:count] and held._made["reranking"] == count


def test_the_startup_load_makes_the_copies_and_later_borrows_reuse_them(monkeypatch, tmp_path):
    held, _ = models(monkeypatch, tmp_path)
    held.load()
    assert held._made == {"embedding": retrieval.TOKENIZER_COPIES, "reranking": retrieval.TOKENIZER_COPIES}
    made = [id(t) for t in held._spare["reranking"]]
    with held.borrowed("reranking") as tokenizer:
        assert id(tokenizer) in made
    held.load()
    assert held._made["reranking"] == retrieval.TOKENIZER_COPIES


def searcher():
    return retrieval.HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")})


QUESTIONS = [(QUERIES, None), (QUERIES[:1], None), ([{"query_id": "dispute:2:q1", "text": "another route"}], None)]


def test_a_matters_questions_searched_together_each_find_what_they_find_alone():
    together = searcher()
    finished = []
    futures = together.search_many(QUESTIONS, results={"provision": 2}, done=lambda: finished.append(1))
    alone = searcher()
    assert [future.result() for future in futures] == [
        alone.search(queries, instruments, results={"provision": 2}) for queries, instruments in QUESTIONS]
    assert len(finished) == len(QUESTIONS)


def test_a_failing_question_keeps_its_own_failure_and_its_peers_their_results():
    together = searcher()
    original = together.search

    def search(queries, instruments=None, **kw):
        if queries[0]["query_id"] == "dispute:2:q1":
            raise retrieval.SearchUnavailable("This question's search failed")
        return original(queries, instruments, **kw)
    together.search = search
    futures = together.search_many(QUESTIONS)
    assert futures[0].result()["candidates"] and futures[1].result()["candidates"]
    with pytest.raises(retrieval.SearchUnavailable, match="This question"):
        futures[2].result()


def test_a_progress_report_that_fails_changes_no_search():
    def broken():
        raise RuntimeError("display unavailable")
    futures = searcher().search_many(QUESTIONS[:1], done=broken)
    assert futures[0].result() == searcher().search(*QUESTIONS[0])


def test_no_questions_search_nothing():
    assert searcher().search_many([]) == []
